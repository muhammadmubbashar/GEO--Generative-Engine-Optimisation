"""LLM helper for statistics_addition and cite_sources.

Records the temperature the API actually accepted. Does not modify
geo_bench/api or geo_bench/generation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Tuple

from ..config import CONFIG, Config


@dataclass
class LlmCall:
    text: str
    requested_temperature: float
    actual_temperature: float
    fallback: bool
    prompt_chars: int
    output_chars: int


def estimate_cost_usd(n_calls: int, prompt_chars: int, output_chars: int,
                      cfg: Config = CONFIG) -> float:
    # ~4 chars/token, conservative.
    in_tok = (prompt_chars / 4.0) * n_calls
    out_tok = (output_chars / 4.0) * n_calls
    return (in_tok / 1000.0) * cfg.optimisation_usd_per_1k_input + (
        out_tok / 1000.0) * cfg.optimisation_usd_per_1k_output


_consecutive_failures = 0
_skip_remaining = False


def generate_optimised(prompt: str, cfg: Config = CONFIG) -> LlmCall:
    """Call the optimisation model; log fallback if 0.3 is rejected."""
    import time
    from openai import (
        APIConnectionError, APITimeoutError, BadRequestError, OpenAI,
        RateLimitError,
    )

    global _consecutive_failures, _skip_remaining
    if _skip_remaining:
        raise RuntimeError("LLM disabled after repeated timeouts this run")

    requested = float(cfg.optimisation_temperature)
    client = OpenAI()
    messages = [{"role": "user", "content": prompt}]

    def _call(use_sampling: bool):
        if use_sampling:
            return client.chat.completions.create(
                model=cfg.optimisation_model, temperature=requested,
                top_p=1.0, messages=messages, timeout=25.0)
        return client.chat.completions.create(
            model=cfg.optimisation_model, messages=messages, timeout=25.0)

    last = None
    resp = None
    fallback = False
    actual = requested
    for i in range(2):
        try:
            try:
                resp = _call(True)
                actual = requested
                fallback = False
            except BadRequestError as exc:
                msg = str(exc).lower()
                if "temperature" not in msg and "top_p" not in msg:
                    raise
                resp = _call(False)
                actual = 1.0
                fallback = True
                print(f"  WARNING: {cfg.optimisation_model} rejected temperature="
                      f"{requested}; used API default. Record actual_temperature="
                      f"{actual} in arm metadata.")
            break
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            last = exc
            wait = min(45, 2 ** i)
            print(f"  [llm retry {i+1}/5 in {wait}s] {exc}", flush=True)
            time.sleep(wait)
    if resp is None:
        _consecutive_failures += 1
        if _consecutive_failures >= 2:
            _skip_remaining = True
            print("  WARNING: disabling further LLM calls this run after "
                  "repeated timeouts; using visible fact spans only.")
        raise last
    _consecutive_failures = 0

    text = (resp.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    return LlmCall(
        text=text, requested_temperature=requested,
        actual_temperature=actual, fallback=fallback,
        prompt_chars=len(prompt), output_chars=len(text),
    )


def confirm_cost(n_calls: int, est_usd: float, cfg: Config = CONFIG) -> None:
    print(f"  estimated LLM calls: {n_calls}")
    print(f"  estimated cost:      ${est_usd:.4f}  "
          f"(cap ${cfg.optimisation_cost_cap_usd:.2f})")
    if est_usd > cfg.optimisation_cost_cap_usd:
        raise RuntimeError(
            f"estimated cost ${est_usd:.4f} exceeds cap "
            f"${cfg.optimisation_cost_cap_usd:.2f}. Halt."
        )
    ans = input("  type yes to generate LLM arm content: ").strip().lower()
    if ans != "yes":
        raise RuntimeError("LLM generation cancelled (no 'yes').")


def parse_patches(text: str) -> List[dict]:
    """JSON [{old, new}, ...] from the model. Empty list if unusable."""
    raw = (text or "").strip()
    if not raw or raw in ("[]", "null"):
        return []
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: List[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        old = str(item.get("old") or "").strip()
        new = str(item.get("new") or "").strip()
        if 10 <= len(old) <= 180 and new and new != old:
            out.append({"old": old, "new": new})
    return out[:12]


def apply_patches(html: str, patches: List[dict]) -> Tuple[str, int]:
    """Replace phrases in original HTML, including text nodes split from tags."""
    from bs4 import BeautifulSoup, NavigableString

    out = html or ""
    applied = 0
    for p in patches:
        old, new = p["old"], p["new"]
        if old in out:
            out = out.replace(old, new, 1)
            applied += 1
            continue
        soup = BeautifulSoup(out, "html.parser")
        hit = False
        key = old if len(old) <= 48 else old[:48]
        if len(key) < 12:
            continue
        for node in soup.find_all(string=True):
            parent = getattr(node, "parent", None)
            if parent is not None and parent.name in ("script", "style"):
                continue
            if key in node:
                node.replace_with(NavigableString(node.replace(key, new, 1)))
                hit = True
                break
        if hit:
            out = str(soup)
            applied += 1
    return out, applied


def append_before_body_end(html: str, snippet: str) -> str:
    blob = html or ""
    idx = blob.lower().rfind("</body>")
    if idx >= 0:
        return blob[:idx] + snippet + blob[idx:]
    return blob + snippet
