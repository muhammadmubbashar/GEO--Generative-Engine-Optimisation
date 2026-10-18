"""cite_sources — add real, checkable, THIRD-PARTY source attribution.

v1 of this arm cited each fact back to the page's own URL, which passed
verification (a page may legitimately reference itself) but is not what
"citation" or "authority attribution" means in the GEO literature this arm is
meant to test — pointing at yourself is not evidence. v2 sources exclusively
from `external_facts.py`, a small curated table of independent, checkable
facts (Wikipedia-sourced at build time; see data/external_facts.csv), matched
to a page only when the page's own content makes the fact relevant.
No LLM call: the attribution is a deterministic append, so there is nothing
for a model to invent or drift on temperature.
"""
from __future__ import annotations

import hashlib
import html as htmlmod

from ..base import AddedClaim, Arm, FrozenPage, OptimisedPage
from ..external_facts import ExternalFactTable
from ..facts import FactTable
from ...retrieval.cleaner import clean_html


class CiteSourcesArm(Arm):
    name = "cite_sources"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        ext = ExternalFactTable.load()
        matches = ext.for_page(page)
        claims = []
        if matches:
            bits = []
            for f in matches[:3]:
                bits.append(
                    f"{f.visible_sentence()} "
                    f"Source: {f.source_name} — {f.source_url}."
                )
                claims.append(AddedClaim(
                    span=bits[-1], fact_id=f.fact_id,
                    source_url=f.source_url, kind="citation"))
            para = (
                '\n<p class="geo-cite-sources">'
                + htmlmod.escape(" ".join(bits)) + "</p>\n"
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
        notes = {
            "preserves_length": False,
            "external_facts_matched": len(matches),
            "claims": [
                {"span": c.span, "fact_id": c.fact_id,
                 "source_url": c.source_url, "kind": c.kind}
                for c in claims
            ],
        }
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=digest, baseline_sha256=page.sha256,
            baseline_words=page.words, optimised_words=len(clean.split()),
            page_type=page.page_type, claims=claims, notes=notes,
        )
