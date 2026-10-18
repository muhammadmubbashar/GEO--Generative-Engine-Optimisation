"""Neutral, position/dose-matched evaluation control for statistics addition.

Unlike the retired twin, this never repeats page-opening words, titles, route
names, or query-like text. It mirrors the real arm's block at the same fare
anchor using fixed nonce tokens. It is a lab-only placebo, not deployable web
content.
"""
from __future__ import annotations

import hashlib
import json

from ...config import CONFIG
from ...experiment.run_store import RunStore, url_hash
from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from .statistics_addition import _fare_fact, insert_after_fare
from ...retrieval.cleaner import clean_html

SOURCE_ARM = "statistics_addition"
_NEUTRAL = ("alba brin cador delm eris fane gilo hest iora juno keld luma "
            "moro nira ordo pava quim rilo sarn tavi ulmo vira wexi yaro zeni").split()


def _source_notes(url: str) -> dict:
    store = RunStore.resolve(None, CONFIG)
    path = store.root / "arms" / SOURCE_ARM / "pages" / url_hash(url) / "meta.json"
    if not path.exists():
        raise RuntimeError(f"statistics_addition_twin requires built {SOURCE_ARM} for {url}")
    return json.loads(path.read_text(encoding="utf-8")).get("notes") or {}


def _neutral_text(n_words: int) -> str:
    if n_words <= 0:
        return ""
    return " ".join((_NEUTRAL * ((n_words + len(_NEUTRAL) - 1) // len(_NEUTRAL)))[:n_words])


class StatisticsAdditionTwinArm(Arm):
    name = "statistics_addition_twin"
    needs_verified_facts = True
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        notes = _source_notes(page.url)
        real_text = str(notes.get("added_text") or "")
        fact = _fare_fact(page, facts)
        html, inserted = page.html, False
        if notes.get("inserted") and fact and real_text:
            html, inserted = insert_after_fare(
                html, fact, _neutral_text(len(real_text.split())),
                "geo-statistics-addition-twin")
        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest(),
            baseline_sha256=page.sha256, baseline_words=page.words,
            optimised_words=len(clean.split()), page_type=page.page_type,
            notes={"preserves_length": False, "mirrors_arm": SOURCE_ARM,
                   "evaluation_only_neutral_control": True, "inserted": inserted,
                   "words_added": max(0, len(clean.split()) - page.words)},
        )
