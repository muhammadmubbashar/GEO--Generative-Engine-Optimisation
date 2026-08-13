"""Expand one client query into N search phrasings (original always kept)."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import List

from ..api import get_client
from ..config import CONFIG, Config
from .cache import SearchCache

FANOUT_PROMPT = (
    "Rewrite the user travel search question into {n} alternative web-search "
    "queries. Rules:\n"
    "- Preserve intent and all named entities (cities, airports, cabin class, "
    "routes, countries).\n"
    "- Do NOT change the topic (no hotels, cars, or unrelated products).\n"
    "- Each line must be a short search query suitable for a web search engine.\n"
    "- Return ONLY a JSON array of {n} strings, no markdown.\n\n"
    "Question: {query}"
)


def _parse_variants(raw: str, n: int) -> List[str]:
    text = raw.strip()
    # Strip markdown fences if the model wraps them anyway.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: one query per non-empty line
        lines = [ln.strip(" -\t\"'") for ln in text.splitlines() if ln.strip()]
        data = lines
    if not isinstance(data, list):
        raise RuntimeError(f"fan-out did not return a JSON array: {raw[:200]!r}")
    out = [str(x).strip() for x in data if str(x).strip()]
    if len(out) < n:
        raise RuntimeError(
            f"fan-out returned {len(out)} variants, need {n}: {out}")
    return out[:n]


def fanout_queries(query: str, cfg: Config = CONFIG,
                   cache: SearchCache | None = None) -> List[str]:
    """Return [original, paraphrase_1, ...] length == fanout_variants."""
    n = cfg.fanout_variants
    if n <= 1:
        return [query]

    cache = cache or SearchCache(cfg)
    cached = cache.get_fanout(query, n, cfg.fanout_model)
    if cached:
        # Guarantee original is first.
        variants = list(cached)
        if variants[0] != query:
            variants = [query] + [v for v in variants if v != query]
        return variants[:n]

    fan_cfg = replace(cfg, gen_model=cfg.fanout_model)
    client = get_client(fan_cfg)
    prompt = FANOUT_PROMPT.format(n=n - 1, query=query)
    # Temperature 0 for determinism; some models reject it — fall back.
    try:
        raw = client.generate(prompt, temperature=0.0, top_p=1.0)
    except Exception:
        raw = client.generate(prompt, temperature=cfg.temperature, top_p=cfg.top_p)

    paraphrases = _parse_variants(raw, n - 1)
    variants = [query] + paraphrases
    # Deduplicate while preserving order.
    seen = set()
    unique: List[str] = []
    for v in variants:
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    while len(unique) < n:
        unique.append(f"{query} flights")
    unique = unique[:n]
    cache.put_fanout(query, n, cfg.fanout_model, unique)
    return unique
