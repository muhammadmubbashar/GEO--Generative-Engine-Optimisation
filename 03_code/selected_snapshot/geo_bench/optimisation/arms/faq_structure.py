"""faq_structure — append server-rendered Q&A from verified facts only.

v1 wrote the exact evaluation-query string into the <h3> as the "question".
Since reindexed retrieval is BM25 + embeddings over those same query strings,
that pasted the exam paper into the textbook: the ablation in
scripts/faq_ablation_retrieval.py shows stripping the questions back out
destroys ~90% of the arm's measured retrieval gain. v2 synthesizes questions
from the page/fact itself — never from queries.csv — so retrieval can only
respond to genuine answer content, not a copy of what will be asked.

Questions come from verified facts for this page, falling back to Flight
Centre's brand-wide verified facts (FactTable.for_page) when the page has no
route-specific one, so pages are no longer left untreated just because they
carry no price fact.
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import re

from ...config import CONFIG
from ..base import AddedClaim, Arm, FrozenPage, OptimisedPage
from ..facts import Fact, FactTable
from ...retrieval.cleaner import clean_html

_ROUTE_TITLE_RE = re.compile(
    r"from\s+(.+?)\s+to\s+(.+?)\s*(?:\s+from\s+\$\d|[-|]|$)", re.I)


def _route_names(page: FrozenPage) -> tuple[str, str] | None:
    m = _ROUTE_TITLE_RE.search(page.title or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def _question_for(fact: Fact, page: FrozenPage) -> str:
    """A natural question for this fact, independent of any eval query text."""
    if fact.claim_type == "price":
        route = _route_names(page)
        if route:
            return f"How much does a flight from {route[0]} to {route[1]} cost?"
        return "How much do fares on this page cost?"
    unit = (fact.unit or "").strip().lower()
    if fact.claim_type == "quantity" and unit == "years":
        return "How long has Flight Centre been in business?"
    if fact.claim_type == "quantity" and unit == "hours":
        return "How long does this route take to fly?"
    if fact.claim_type == "quantity":
        return f"How many {unit} does Flight Centre's network cover?"
    if fact.claim_type == "percent":
        return "What does this figure mean for my booking?"
    if fact.claim_type == "date":
        return "When does this apply?"
    return "Frequently asked question"


class FaqStructureArm(Arm):
    name = "faq_structure"
    needs_verified_facts = True
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        page_facts = facts.for_page(page, verified_only=True)
        # Price first (answers the question a route page exists to answer),
        # then other claim types, capped and deduplicated by question text.
        ordered = sorted(
            page_facts, key=lambda f: 0 if f.claim_type == "price" else 1)

        pairs = []
        claims = []
        seen_q = set()
        for fact in ordered:
            if len(pairs) >= CONFIG.max_faq_pairs:
                break
            question = _question_for(fact, page)
            if question in seen_q:
                continue
            seen_q.add(question)
            answer = fact.visible_sentence()
            pairs.append((question, answer))
            claims.append(AddedClaim(
                span=answer, fact_id=fact.fact_id,
                source_url=fact.source_url, kind="faq_answer"))

        if pairs:
            items = []
            for q, a in pairs:
                items.append(
                    f"<h3>{htmlmod.escape(q)}</h3>\n"
                    f"<p>{htmlmod.escape(a)}</p>"
                )
            section = (
                '\n<section id="geo-faq">\n'
                "<h2>Frequently asked questions</h2>\n"
                + "\n".join(items)
                + "\n</section>\n"
            )
            html = page.html
            low = html.lower()
            idx = low.rfind("</body>")
            if idx >= 0:
                html = html[:idx] + section + html[idx:]
            else:
                html = html + section
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
            page_type=page.page_type, claims=claims,
            notes={
                "preserves_length": False,
                "faq_pairs_generated": len(pairs),
                "claims": [
                    {"span": c.span, "fact_id": c.fact_id,
                     "source_url": c.source_url, "kind": c.kind}
                    for c in claims
                ],
            },
        )
