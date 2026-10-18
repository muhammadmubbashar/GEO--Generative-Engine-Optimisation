"""ssr_visible_digitfix — sensitivity companion to ssr_visible.

Identical to `ssr_visible` (same capture, same whole-page substitution)
except prices are rejoined ("$150" instead of "$ 1 5 0" — see
`ssr_visible.py`'s module docstring for why that split happens and why it
is genuinely ambiguous whether a real crawler's extractor would rejoin it).

This is the "best-case extractor" bound; `ssr_visible` is the "as-extracted,
zero-intervention" bound. Both are compared against the same untouched
baseline. If the finding holds across both, it does not depend on an
extraction-fidelity assumption this project cannot verify either way.
"""
from __future__ import annotations

import hashlib
import re

from ...config import CONFIG
from ...experiment.run_store import RunStore
from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from ...retrieval.cleaner import clean_html
from .ssr_visible import _load_render

_SPLIT_DIGITS_RE = re.compile(r"\$\s*((?:\d\s*){2,})")


def _rejoin_split_prices(text: str) -> str:
    return _SPLIT_DIGITS_RE.sub(
        lambda m: "$" + re.sub(r"\s+", "", m.group(1)), text)


class SsrVisibleDigitfixArm(Arm):
    name = "ssr_visible_digitfix"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        store = RunStore.resolve(None, CONFIG)
        html, cap_meta = _load_render(store, page.url)

        body, jsonld = clean_html(html)
        clean = _rejoin_split_prices((body + " " + jsonld).strip())
        digest = hashlib.sha256(
            html.encode("utf-8", errors="replace")).hexdigest()
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=digest, baseline_sha256=page.sha256,
            baseline_words=page.words, optimised_words=len(clean.split()),
            page_type=page.page_type,
            notes={
                "preserves_length": False,
                "rendered_at": cap_meta.get("rendered_at"),
                "capture_sha256": cap_meta.get("sha256"),
                "words_added": max(0, len(clean.split()) - page.words),
            },
        )
