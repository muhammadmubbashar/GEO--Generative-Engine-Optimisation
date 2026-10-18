"""Selective rendered-content exposure: surgical extraction, not a whole-page swap.

Every rendered variant so far in this project (V3's rendered_content_exposure/
semantic/organised, and the legacy geo_bench arm ssr_visible) substitutes the
ENTIRE browser-rendered capture for the baseline page. Measured directly:
V3's rendered_content_organised adds a mean +281.7 words/FC page (~20%
inflation, results/optimisation_v3_rendered_organised_v1/pages.json vs
results/baseline_v2_1_repeat_20260909/pages.json); the legacy ssr_visible
adds +29.2% (results/arms/ssr_visible/volume_summary.json). Both are
carousels, deal tiles and cross-sell widgets from the DOM, not isolated
JS-revealed substance. Reindexed (BM25) length-normalises, so diluting term
density with promotional/navigational text costs retrieval even as the
extra real content helps the fixed layer once FC is already in context --
exactly the shape both heavy-dose treatments show (V3 organised: fixed
+6.55pp, reindexed -3.50pp).

Correction to an earlier claim in this project's own history: a 2026-08-27
decisions_log entry describes a "surgical extraction" design for
ssr_visible (word-diff against baseline, keep only new price-bearing spans,
cap 2, ~90 chars context) reporting +5.4% mean delta. That design was
replaced the very next day (2026-08-29 entry) by the current plain
whole-page ssr_visible before it was ever generation-tested end to end --
the +5.4% number describes a page-build measurement only, never an actual
answer-generation result. So this is a genuinely new experiment, not a
re-run of something already validated.

This module ports that abandoned design and actually tests it: word-diff
the rendered capture's cleaned text against the frozen baseline, keep only
genuinely NEW word spans that (a) contain a visible price/fare pattern and
(b) mention this page's own destination entities (never an unrelated
cross-sell price for a different route -- reuses geo_bench's own entity
extractor, the same filter the legacy design specified), cap at 2 spans
with a small word-window of context each, and merge them into the baseline
HTML as one visible, clearly-labelled paragraph. Everything else about the
page -- and every other page's traffic and content -- is untouched. Every
added word is byte-traceable to the frozen dated capture (source_sha256 /
raw_sha256 on the rendered() call this reuses for validation).
"""
from __future__ import annotations

import difflib
import html as htmlmod
import re

from .arms import Source, append_body, cleaned, rendered, sha
from geo_bench.optimisation.facts import extract_named_entities

ARM = 'rendered_content_selective'
PRICE_RE = re.compile(r'(?<![\w$])\$\s?\d[\d,]*(?:\.\d+)?')
MAX_SPANS = 2
CONTEXT_WORDS = 8


def _entity_tokens(url: str, clean: str) -> set:
    toks = set()
    for e in extract_named_entities(url, clean):
        toks.update(w.lower() for w in re.findall(r'[A-Za-z]+', e) if len(w) > 2)
    return toks


def selective_rendered(source: Source, raw: bytes, meta: dict) -> dict:
    full = rendered(source, raw, meta)  # reuses canonical/hash/blocked-page validation
    base_words = source.clean.split()
    full_words = full['clean'].split()
    sm = difflib.SequenceMatcher(None, base_words, full_words, autojunk=False)
    entity_toks = _entity_tokens(source.url, source.clean)

    candidates = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag not in ('insert', 'replace'):
            continue
        # Find each price-looking TOKEN inside the changed range and window
        # tightly around its own position -- a changed/reordered block can
        # span hundreds of words, and we must not treat the whole block as
        # one candidate span just because a price appears somewhere in it.
        for k, w in enumerate(full_words[j1:j2]):
            if not PRICE_RE.search(w):
                continue
            abs_idx = j1 + k
            lo = max(0, abs_idx - CONTEXT_WORDS)
            hi = min(len(full_words), abs_idx + CONTEXT_WORDS + 1)
            span_text = ' '.join(full_words[lo:hi])
            if entity_toks and not any(t in span_text.lower() for t in entity_toks):
                continue
            candidates.append(span_text)
    chosen = []
    seen = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        chosen.append(c)
        if len(chosen) >= MAX_SPANS:
            break

    if not chosen:
        raw_html = source.html
        text = source.clean
    else:
        block = ' '.join(chosen)
        raw_html = append_body(
            source.html,
            '\n<p id="geo-v3-rendered-selective">' + htmlmod.escape(block) + '</p>\n',
        )
        text = cleaned(raw_html)

    return {
        'arm': ARM, 'url': source.url, 'html': raw_html, 'clean': text,
        'source_sha256': sha(source.clean), 'raw_sha256': sha(raw_html),
        'clean_sha256': sha(text), 'evidence': [],
        'notes': {
            'rendered_at': meta.get('rendered_at'),
            'capture_sha256': meta.get('sha256'),
            'spans_found': len(candidates), 'spans_used': len(chosen),
            'requested_extra_words': sum(len(c.split()) for c in chosen),
            'actual_extra_words': max(0, len(text.split()) - len(base_words)),
            'interpretation': (
                'surgical extraction of new price-bearing, destination-matched '
                'spans from the dated render, not a whole-page substitution'
            ),
        },
    }
