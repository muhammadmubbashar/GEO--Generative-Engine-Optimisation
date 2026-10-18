"""ssr_visible — whole-page substitution: what an AI sees if Flight Centre's
page is genuinely server/JS-rendered, versus the frozen no-JS capture
(Type A / Gate 1 arm, not a content rewrite).

Per decisions_log.md (2026-08-14): the baseline freeze stays no-JS. This arm
answers the direct question — with the exact same generation pipeline,
prompts, and competitor pages as baseline, does the model's answer change
when Flight Centre's URL is what a browser actually renders (captured by
`scripts/capture_ssr_render.py`,
`runs/<RID>/arms/ssr_visible/rendered_raw/`) instead of what a non-JS
crawler currently sees? Nothing else changes: competitors stay freeze
bytes, `generator.py`/`prompts.py` are untouched, only the FC page text the
index overlays is different.

Design note (2026-08-29, two-variant split): FC's price widgets render each
digit in its own DOM node (a genuine Material-UI odometer component on
FC's real site, confirmed by reading the raw DOM — not something this
pipeline invented). BeautifulSoup's `get_text(" ")` — the SAME extractor
`baseline` and every other arm already uses, unmodified — turns that into
"$ 1 5 0" instead of "$150". An earlier version of this arm patched that
with `_rejoin_split_prices`, applied to this arm only. On review that was
an asymmetric intervention: baseline never receives any equivalent repair
(verified: 0/52 baseline pages contain a split-digit price at all, because
the animated widget doesn't exist without JS in the first place, not
because baseline got a cleaner pass), and there is no way to know whether a
real production crawler's text extractor would join those digits or not —
the digits sit inside block-level `<div>` wrappers, not bare adjacent
`<span>`s, so a "smarter" extractor joining them is an assumption, not a
fact.

Rather than bake in either assumption, this is now the AS-EXTRACTED
variant: plain `clean_html(html)`, zero post-processing, identical
treatment to every other arm and to baseline. `ssr_visible_digitfix.py` is
the companion variant with the rejoin applied, so the two together bound
the result across the range of "worst case extractor" to "best case
extractor" instead of silently picking one.
"""
from __future__ import annotations

import hashlib
import json

from ...config import CONFIG
from ...experiment.run_store import RunStore, url_hash
from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from ...retrieval.cleaner import clean_html


def _load_render(store: RunStore, url: str) -> tuple[str, dict]:
    h = url_hash(url)
    cap_dir = store.root / "arms" / "ssr_visible" / "rendered_raw" / h
    meta_path, html_path = cap_dir / "meta.json", cap_dir / "rendered.html"
    if not meta_path.exists():
        raise RuntimeError(
            f"ssr_visible: no captured render for {url}. "
            f"Run scripts/capture_ssr_render.py first.")
    cap_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if cap_meta.get("status") != "ok" or not html_path.exists():
        raise RuntimeError(
            f"ssr_visible: capture failed for {url} "
            f"({cap_meta.get('status')}); cannot build this page.")
    raw = html_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != cap_meta.get("sha256"):
        raise RuntimeError(
            f"ssr_visible: on-disk render for {url} does not match its own "
            f"capture manifest (tampered or re-saved). Refusing.")
    return raw.decode("utf-8", errors="replace"), cap_meta


class SsrVisibleArm(Arm):
    name = "ssr_visible"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        store = RunStore.resolve(None, CONFIG)
        html, cap_meta = _load_render(store, page.url)

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
                "rendered_at": cap_meta.get("rendered_at"),
                "capture_sha256": cap_meta.get("sha256"),
                "words_added": max(0, len(clean.split()) - page.words),
            },
        )
