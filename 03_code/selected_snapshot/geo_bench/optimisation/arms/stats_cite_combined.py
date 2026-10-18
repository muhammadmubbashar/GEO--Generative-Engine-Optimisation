"""stats_cite_combined — Aggarwal et al. (KDD 2024) Section 5.3's own
combination-of-methods design, applied to our two already-real,
no-fabrication GEO methods.

The original paper's Section 5.3 found combining GEO methods on the same
document outperforms any single method (their best pair, Fluency + Statistics,
beat the best single method by >5.5%), and specifically found Cite Sources —
weak alone in their results — jumps to a 31.4% average effect when combined
with another method. That analysis was run under their fabrication license
(invented statistics, invented sources). This arm tests the same combination
idea under our project's no-invention constraint: both ingredients are
already-built, already-verified-grounded arms
(`statistics_addition`: a real verified fact patched into the prose;
`cite_sources`: a real external Wikipedia-sourced attribution, gated to pages
where it's actually relevant) — nothing new is invented to make the
combination bigger.

Mechanics: run `StatisticsAdditionArm.optimise()` on the true frozen page
first (unchanged from how it runs standalone), then feed its *html* output
into `CiteSourcesArm.optimise()` as if it were the page. Cite Sources'
relevance gate (`ExternalFactTable.for_page`) is evaluated against the
ORIGINAL page's `.clean` text, not the statistics-patched intermediate —
deliberately: gating should reflect what's genuinely on the page, not an
artifact of which arm happened to run first. `baseline_sha256`/
`baseline_words` on the output point at the true original frozen page, so
volume/verification metrics measure the full combined delta, not a
double-counted intermediate.

No twin: per this project's established preference (direct arm-vs-baseline
comparison), this arm is compared straight against baseline, not a
dose-matched placebo — twins built so far (`ssr_visible_twin`,
`statistics_addition_twin`) share a documented keyword-reinforcement flaw
in their filler convention (2026-08-27/28 decisions_log entries) and building
a third one before that's fixed would just propagate the same confound.
"""
from __future__ import annotations

from dataclasses import replace

from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from .cite_sources import CiteSourcesArm
from .statistics_addition import StatisticsAdditionArm


class StatsCiteCombinedArm(Arm):
    name = "stats_cite_combined"
    needs_verified_facts = True
    uses_llm = True
    preserves_length = False

    def __init__(self) -> None:
        self._stats = StatisticsAdditionArm()
        self._cite = CiteSourcesArm()

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        stats_out = self._stats.optimise(page, facts)
        intermediate = replace(page, html=stats_out.html)
        cite_out = self._cite.optimise(intermediate, facts)

        claims = list(stats_out.claims) + list(cite_out.claims)
        notes = {
            "combined_arms": ["statistics_addition", "cite_sources"],
            "statistics_addition_notes": stats_out.notes,
            "cite_sources_notes": cite_out.notes,
            "claims": [
                {"span": c.span, "fact_id": c.fact_id,
                 "source_url": c.source_url, "kind": c.kind}
                for c in claims
            ],
        }
        return OptimisedPage(
            url=page.url, arm=self.name, html=cite_out.html,
            clean=cite_out.clean, content_hash=cite_out.content_hash,
            baseline_sha256=page.sha256, baseline_words=page.words,
            optimised_words=cite_out.optimised_words,
            page_type=page.page_type, claims=claims, notes=notes,
        )
