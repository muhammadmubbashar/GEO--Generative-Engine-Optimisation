"""ssr_visible_twin — per-page dose-matched control for ssr_visible.

Same rationale as `statistics_addition_twin` (G8): a control that adds the
same words in a different place, or a different dose, is not isolating
"real price content" from "word count" — it's comparing two different
treatments. This arm reads `ssr_visible`'s own build record for each page
(`runs/<RID>/arms/ssr_visible/pages/<hash>/meta.json`) and appends the exact
same number of words at the exact same insertion point (before `</body>`),
except the words are neutral filler (the page's own baseline text, same
convention as `padding_control`) instead of real captured price/deal
content. A page `ssr_visible` left untouched (no relevant new span found)
is left untouched by the twin too.

Must be built AFTER `ssr_visible` for the same `--from-run`.
"""
from __future__ import annotations

import hashlib
import json
from typing import List

from ...config import CONFIG
from ...experiment.run_store import RunStore, url_hash
from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from ..llm import append_before_body_end
from ...retrieval.cleaner import clean_html

SOURCE_ARM = "ssr_visible"


def _seed_words(page: FrozenPage) -> List[str]:
    words = (page.clean or page.html or "").split()[:40]
    return words or ["Flight", "Centre"]


def _junk(page: FrozenPage, n_words: int) -> str:
    if n_words <= 0:
        return ""
    seed = _seed_words(page)
    copies = max(1, (n_words + len(seed) - 1) // len(seed))
    return " ".join((seed * copies)[:n_words])


class SsrVisibleTwinArm(Arm):
    name = "ssr_visible_twin"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        store = RunStore.resolve(None, CONFIG)
        meta_path = (store.root / "arms" / SOURCE_ARM / "pages"
                     / url_hash(page.url) / "meta.json")
        if not meta_path.exists():
            raise RuntimeError(
                f"ssr_visible_twin: no built {SOURCE_ARM} page for "
                f"{page.url}. Run `geo optimise {SOURCE_ARM}` first."
            )
        source_notes = json.loads(
            meta_path.read_text(encoding="utf-8")).get("notes") or {}
        spans = source_notes.get("spans") or []
        target_words = len(" ".join(spans).split()) if spans else 0

        html = page.html
        did_append = False
        if target_words:
            junk = _junk(page, target_words)
            if junk:
                html = append_before_body_end(
                    html, f'\n<p class="geo-ssr-visible-twin">{junk}</p>\n')
                did_append = True

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
                "preserves_length": not did_append,
                "mirrors_arm": SOURCE_ARM,
                "mirrored_target_words": target_words,
                "mirrored_append": did_append,
                "words_added": max(0, len(clean.split()) - page.words),
            },
        )
