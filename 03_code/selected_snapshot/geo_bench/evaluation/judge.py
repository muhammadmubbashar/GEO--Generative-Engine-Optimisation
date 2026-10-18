"""Machine judge for relevance and response quality.

Rubric text is loaded verbatim from SCORING_RUBRICS.md (sections 4–5).
Do not paraphrase. One answer per call. Temperature 0.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from ..api import get_client
from ..api.base import Passage
from ..config import CONFIG, Config

_STUDY_BRANDS: Tuple[Tuple[str, str], ...] = (
    ("flightcentre.com.au", "Brand A"),
    ("www.flightcentre.com.au", "Brand A"),
    ("flightcentre.com", "Brand A"),
    ("flight centre's", "Brand A's"),
    ("flight-centre's", "Brand A's"),
    ("flightcenter's", "Brand A's"),
    ("flight centre", "Brand A"),
    ("flight-centre", "Brand A"),
    ("flightcenter", "Brand A"),
    ("flightcentre", "Brand A"),
    ("skyscanner.com.au", "Brand B"),
    ("skyscanner.com", "Brand B"),
    ("skyscanner's", "Brand B's"),
    ("skyscanner", "Brand B"),
    ("webjet.com.au", "Brand C"),
    ("webjet.com", "Brand C"),
    ("webjet's", "Brand C's"),
    ("webjet", "Brand C"),
    ("expedia.com.au", "Brand D"),
    ("expedia.com", "Brand D"),
    ("expedia's", "Brand D's"),
    ("expedia", "Brand D"),
)

_SURVIVOR_CORE = r"flight[\s\-]?cent(?:re|er)|flightcentre|skyscanner|webjet|expedia"


def _survivor_re(cfg: Config = CONFIG) -> re.Pattern:
    """Study brands plus every extra masked brand — nothing may survive."""
    extras = [re.escape(b.strip()) for b in cfg.extra_mask_brands if b.strip()]
    return re.compile("|".join([_SURVIVOR_CORE, *extras]), re.I)


def load_rubric_verbatim(cfg: Config = CONFIG) -> str:
    path = Path(cfg.rubric_file)
    text = path.read_text(encoding="utf-8")
    start = text.index("## 4. RELEVANCE")
    end = text.index("## 6. Machine scoring")
    return text[start:end].strip()


def _apply_pair(text: str, src: str, dst: str) -> str:
    return re.sub(re.escape(src), dst, text, flags=re.I)


def mask_brands(text: str, cfg: Config = CONFIG) -> str:
    """Flight Centre → Brand A, Skyscanner → B, Webjet → C, Expedia → D.

    Other named commercial travel brands → Brand E, F, … in config order.
    Airlines, government and reference sites are not masked.
    """
    out = text or ""
    for src, dst in _STUDY_BRANDS:
        out = _apply_pair(out, src, dst)
    letter = ord("E")
    for extra in cfg.extra_mask_brands:
        extra = extra.strip()
        if not extra:
            continue
        tag = f"Brand {chr(letter)}"
        out = _apply_pair(out, extra + "'s", tag + "'s")
        out = _apply_pair(out, extra, tag)
        letter += 1
        if letter > ord("Z"):
            break
    return out


def verify_masking(text: str, cfg: Config = CONFIG) -> bool:
    """False if any masked-brand string survives (possessives, case, URLs)."""
    return _survivor_re(cfg).search(text or "") is None


def verify_all(texts: Sequence[str], cfg: Config = CONFIG) -> None:
    bad = [i for i, t in enumerate(texts) if not verify_masking(t, cfg)]
    if bad:
        raise RuntimeError(
            f"MASKING VERIFICATION FAILED on {len(bad)}/{len(texts)} texts "
            f"(indices {bad[:20]}). Abort scoring. Brand strings must not "
            "survive, including possessives, lowercase, and URLs."
        )


def response_quality(accuracy: float, completeness: float,
                     clarity: float, attribution: float) -> float:
    return round(
        (accuracy * 0.40 + completeness * 0.30
         + clarity * 0.20 + attribution * 0.10) * 5,
        4,
    )


def _parse_json(raw: str) -> Dict:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError(f"judge did not return JSON: {raw[:300]!r}")
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise RuntimeError(f"judge JSON is not an object: {data!r}")
    return data


def score_answer(answer: str, sources: Sequence[Passage], query: str,
                 cfg: Config = CONFIG) -> Dict:
    """One call per answer. Rubric pasted verbatim. Structured JSON out."""
    rubric = load_rubric_verbatim(cfg)
    masked_answer = mask_brands(answer, cfg)
    masked_sources = []
    for i, p in enumerate(sources, 1):
        body = mask_brands(p.text, cfg)
        label = mask_brands(p.brand.replace("_", " "), cfg)
        masked_sources.append(f"[{i}] ({label}) {body}")
    verify_all([masked_answer, *masked_sources], cfg)

    prompt = (
        "You are scoring one AI-generated travel answer. Use ONLY the rubric "
        "below. Do not use outside knowledge. Graders check claims against the "
        "supplied source documents only.\n\n"
        "Return a single JSON object with exactly these keys:\n"
        "  relevance (integer 0, 1 or 2),\n"
        "  accuracy (integer 0, 1 or 2),\n"
        "  completeness (integer 0, 1 or 2),\n"
        "  clarity (integer 0, 1 or 2),\n"
        "  attribution (integer 0, 1 or 2),\n"
        "  notes (short string).\n\n"
        "RUBRIC (verbatim):\n"
        f"{rubric}\n\n"
        f"Question: {mask_brands(query, cfg)}\n\n"
        f"Masked answer:\n{masked_answer}\n\n"
        "Masked source documents:\n"
        + "\n\n".join(masked_sources)
    )
    judge_cfg = replace(cfg, gen_model=cfg.judge_model)
    client = get_client(judge_cfg)
    raw = client.generate(prompt, cfg.judge_temperature, 1.0)
    data = _parse_json(raw)
    rel = int(data.get("relevance", 0))
    acc = int(data.get("accuracy", 0))
    comp = int(data.get("completeness", 0))
    cla = int(data.get("clarity", 0))
    att = int(data.get("attribution", 0))
    for name, val in (("relevance", rel), ("accuracy", acc),
                      ("completeness", comp), ("clarity", cla),
                      ("attribution", att)):
        if val not in (0, 1, 2):
            raise RuntimeError(f"judge {name}={val} not in {{0,1,2}}")
    return {
        "relevance": rel,
        "accuracy": acc,
        "completeness": comp,
        "clarity": cla,
        "attribution": att,
        "response_quality": response_quality(acc, comp, cla, att),
        "notes": str(data.get("notes") or ""),
        # Verbatim judge output, kept for audit (re-parse without re-calling).
        "judge_raw": raw,
        "judge_model": client.name,
        "rubric_version": cfg.rubric_version,
    }
