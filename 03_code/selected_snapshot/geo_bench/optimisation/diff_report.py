"""Human-readable before/after for one URL."""
from __future__ import annotations

import difflib
from typing import List

from .base import FrozenPage, OptimisedPage
from .facts import FactTable


def render_diff(page: FrozenPage, optimised: OptimisedPage,
                facts: FactTable) -> str:
    old = (page.html or "").splitlines()
    new = (optimised.html or "").splitlines()
    lined = list(difflib.unified_diff(
        old, new, fromfile="baseline", tofile=optimised.arm, lineterm=""))
    if not lined:
        body = "(no HTML diff — byte-identical or whitespace-only)"
    else:
        # Cap for terminal readability; full files live on disk.
        if len(lined) > 200:
            lined = lined[:200] + [f"... ({len(lined) - 200} more diff lines)"]
        body = "\n".join(lined)

    claims = []
    for c in optimised.claims:
        fact = facts.by_id(c.fact_id) if c.fact_id else None
        src = (fact.source_url if fact else c.source_url) or "(none)"
        fid = c.fact_id or "(ungrounded)"
        claims.append(f"  [{fid}] {c.span[:160]!r}\n      source={src}")
    if not claims:
        claim_block = "  (no added claims recorded)"
    else:
        claim_block = "\n".join(claims)

    return (
        f"URL: {page.url}\n"
        f"arm: {optimised.arm}  page_type={page.page_type}\n"
        f"words: {page.words} → {optimised.optimised_words}  "
        f"delta={optimised.words_delta:+d} ({optimised.pct_change:+.1f}%)\n"
        f"baseline sha256: {page.sha256[:16]}...\n"
        f"arm sha256:      {optimised.content_hash[:16]}...\n"
        f"\n--- added claims ---\n{claim_block}\n"
        f"\n--- HTML unified diff ---\n{body}\n"
    )
