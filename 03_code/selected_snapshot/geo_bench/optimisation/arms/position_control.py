"""position_control — no content change.

The intervention is runtime (generator.force_first). This arm freezes
byte-identical Flight Centre pages so T2/hash checks have an arm tree
to compare against.
"""
from __future__ import annotations

import hashlib

from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable


class PositionControlArm(Arm):
    name = "position_control"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = True

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        raw = page.html.encode("utf-8", errors="replace")
        digest = hashlib.sha256(raw).hexdigest()
        if page.sha256 and digest != page.sha256:
            raise RuntimeError(
                f"position_control: freeze HTML hash drifted for {page.url} "
                f"(stored={page.sha256[:12]} now={digest[:12]})"
            )
        return OptimisedPage(
            url=page.url, arm=self.name, html=page.html, clean=page.clean,
            content_hash=digest, baseline_sha256=page.sha256,
            baseline_words=page.words, optimised_words=page.words,
            page_type=page.page_type,
            notes={"preserves_length": True, "byte_identical": True},
        )
