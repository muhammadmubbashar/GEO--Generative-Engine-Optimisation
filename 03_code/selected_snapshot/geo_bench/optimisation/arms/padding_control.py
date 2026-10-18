"""padding_control — volume confound.

For each URL, pad freeze text (words already on that page) up to that URL's
longest content-adding arm (schema_markup, keyword_stuffing, faq_structure).
No global mean — cabins must not be doubled to match hub-page averages.

Filler source (fixed 2026-09-07): earlier drew each page's own first 40
words as filler, the same convention used by ssr_visible_twin and
statistics_addition_twin. That was found to be a mild, unintentional form
of keyword reinforcement, not a neutral placebo, for the reindexed layer —
FC's own page titles are literally "Cheap flights from X to Y" and the
eval queries are phrased the same way, so repeating a page's own opening
words accidentally repeats the query itself (2026-08-27/28 decisions_log
entries: the twin significantly beat its own real arm on retrieval/
inclusion for exactly this reason). Filler now comes from one fixed,
unrelated FC page (`_PRIMARY_FILLER_URL`, a generic multi-city page with no
destination pair in its own text, so it shares no route-name phrasing with
any query) instead of the page being padded — same "real page text, no
invention" principle, just sourced off-topic instead of self-referentially.
"""
from __future__ import annotations

import csv
import hashlib
import html as htmlmod
from typing import Dict, List, Tuple

from ...config import CONFIG
from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from ...retrieval.cleaner import clean_html

_CONTENT_ARMS = ("faq_structure", "schema_markup", "keyword_stuffing")
_WORDS_CACHE: Dict[str, Dict[str, int]] = {}

_PRIMARY_FILLER_URL = "https://www.flightcentre.com.au/flights/multi-city"
_FALLBACK_FILLER_URL = "https://www.flightcentre.com.au/flights/round-the-world"
_FILLER_TEXT_CACHE: Dict[str, str] = {}


def _filler_text(url: str, cfg=CONFIG) -> str:
    if url not in _FILLER_TEXT_CACHE:
        from ...experiment.run_store import RunStore
        store = RunStore.resolve(None, cfg)
        p = store.read_page(url)
        _FILLER_TEXT_CACHE[url] = (p or {}).get("clean", "") or ""
    return _FILLER_TEXT_CACHE[url]


def _neutral_filler_words(page_url: str, cfg=CONFIG) -> List[str]:
    # A page can't be its own off-topic filler source; use the fallback
    # generic page only for that one page's own padding.
    source = _FALLBACK_FILLER_URL if page_url == _PRIMARY_FILLER_URL else _PRIMARY_FILLER_URL
    words = _filler_text(source, cfg).split()
    return words or ["Flight", "Centre"]


def _words_by_url(arm: str, cfg=CONFIG) -> Dict[str, int]:
    path = cfg.arm_results_dir(arm) / "volume.csv"
    key = str(path)
    if key in _WORDS_CACHE:
        return _WORDS_CACHE[key]
    if not path.exists():
        _WORDS_CACHE[key] = {}
        return _WORDS_CACHE[key]
    out: Dict[str, int] = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        url = (r.get("url") or "").strip()
        if url:
            out[url] = int(r["optimised_words"])
    _WORDS_CACHE[key] = out
    return out


def _target_for_url(url: str, cfg=CONFIG) -> Tuple[str, int]:
    best_name, best_words = "", -1
    found_any = False
    for name in _CONTENT_ARMS:
        by_url = _words_by_url(name, cfg)
        if not by_url:
            continue
        found_any = True
        w = by_url.get(url)
        if w is None:
            continue
        if w > best_words:
            best_name, best_words = name, w
    if not found_any:
        raise RuntimeError(
            "padding_control: no content-adding arm volume.csv yet. "
            "Run faq_structure / schema_markup / keyword_stuffing first."
        )
    if best_words < 0:
        raise RuntimeError(f"padding_control: {url} missing from content-arm volume files")
    return best_name, best_words


class PaddingControlArm(Arm):
    name = "padding_control"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        source_arm, target_words = _target_for_url(page.url)
        pad_words = _neutral_filler_words(page.url)[:40]
        need = max(0, int(target_words) - page.words)
        extra = ""
        if need:
            copies = max(1, (need + len(pad_words) - 1) // len(pad_words))
            extra = " ".join((" ".join(pad_words * copies)).split()[:need])
        if extra:
            para = (
                f'\n<p class="geo-padding-control">'
                f"{htmlmod.escape(extra)}</p>\n"
            )
            html = page.html
            low = html.lower()
            idx = low.rfind("</body>")
            html = html[:idx] + para + html[idx:] if idx >= 0 else html + para
        else:
            html = page.html
        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        digest = hashlib.sha256(
            html.encode("utf-8", errors="replace")).hexdigest()
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=digest, baseline_sha256=page.sha256,
            baseline_words=page.words, optimised_words=len(clean.split()),
            page_type=page.page_type,
            notes={
                "preserves_length": False,
                "padded_to_arm": source_arm,
                "target_words": target_words,
                "words_added": max(0, len(clean.split()) - page.words),
                "filler_source": (
                    _FALLBACK_FILLER_URL if page.url == _PRIMARY_FILLER_URL
                    else _PRIMARY_FILLER_URL
                ),
            },
        )
