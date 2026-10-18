"""freshness_signal — visible "last verified" date + dateModified JSON-LD
(Pillar 2, Method 9 — FSA framework, the "Freshness" leg; new arm, not
lead_placement, not previously tested).

Grounding: the Pillar 2 audit's FSA framework names Freshness as one of
three drivers of AI citation ("the more current the information is, the
more likely LLMs will be to trust it... regularly updated flight prices...
increases the possibility of Flight Centre pages being referenced").
Parallel 2026 industry research (Writesonic, "How Content Freshness Affects
AI Citations in 2026"; AuthorityTech, "Content Freshness in 2026") reports
freshness as a top-3 AI-citation signal, and specifically that the
dateModified schema property is the most heavily-weighted freshness signal,
followed by a visible on-page "last updated" date.

Design: adds exactly one honest, provenance-checkable sentence plus a
minimal WebPage `dateModified` JSON-LD block. The date used is never
"today" and never invented — it is this freeze's own real capture
timestamp (`store.read_page(url)["fetched_at"]`), so the claim "last
verified on X" is literally true, re-checked against a fresh reload of
that same timestamp at verify time (`verify_freshness_page`), the same
provenance pattern `ssr_visible` uses for its capture.

Insertion point deliberately matches the convention every other tested arm
this session already uses (`idx = low.rfind("</body>")`) rather than
introducing a second, uncontrolled variable — placement is being tested
separately later (`lead_placement`, deferred). This arm isolates the
freshness signal alone.
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import json
from datetime import datetime

from ...config import CONFIG
from ...experiment.run_store import RunStore
from ..base import AddedClaim, Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from ...retrieval.cleaner import clean_html

FRESH_SCRIPT_ID = "geo-freshness-jsonld"


def _format_date(fetched_at: str) -> tuple[str, str]:
    """('15 August 2026', '2026-08-15') from an ISO timestamp string.

    Avoids `%-d`/`%#d` strftime flags (platform-specific, breaks on
    Windows) by building the day number as a plain int.
    """
    dt = datetime.fromisoformat(fetched_at)
    human = f"{dt.day} {dt.strftime('%B')} {dt.year}"
    return human, dt.date().isoformat()


class FreshnessSignalArm(Arm):
    name = "freshness_signal"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        store = RunStore.resolve(None, CONFIG)
        raw = store.read_page(page.url)
        fetched_at = (raw or {}).get("fetched_at") or ""
        if not fetched_at:
            raise RuntimeError(
                f"freshness_signal: no fetched_at on freeze page for {page.url}")
        human, iso_date = _format_date(fetched_at)

        sentence = (
            f"Prices and travel information on this page were last "
            f"verified by Flight Centre on {human}."
        )
        para = f'\n<p id="geo-freshness">{htmlmod.escape(sentence)}</p>\n'

        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": page.title or page.url,
            "url": page.url,
            "dateModified": iso_date,
        }
        script = (
            f'\n<script type="application/ld+json" '
            f'id="{FRESH_SCRIPT_ID}">'
            f'{json.dumps(schema, ensure_ascii=False)}</script>\n'
        )

        html = page.html
        low = html.lower()
        idx = low.rfind("</body>")
        insert = para + script
        html = html[:idx] + insert + html[idx:] if idx >= 0 else html + insert

        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        digest = hashlib.sha256(
            html.encode("utf-8", errors="replace")).hexdigest()

        claims = [AddedClaim(
            span=sentence, fact_id="", source_url=page.url,
            kind="freshness_date")]

        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=digest, baseline_sha256=page.sha256,
            baseline_words=page.words, optimised_words=len(clean.split()),
            page_type=page.page_type, claims=claims,
            notes={
                "preserves_length": False,
                "fetched_at": fetched_at,
                "human_date": human,
                "iso_date": iso_date,
            },
        )
