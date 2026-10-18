"""Deterministic, source-traced fare clarification.

The treatment adds one page-specific verified fare statement immediately
after its matching visible fare. There is no LLM, temperature fallback,
brand-wide fallback, or append-at-end path. If no verified fare can be
anchored in the baseline HTML, the page is deliberately unchanged.
"""
from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

from ..base import AddedClaim, Arm, FrozenPage, OptimisedPage
from ..facts import Fact, FactTable
from ...retrieval.cleaner import clean_html


def _fare_fact(page: FrozenPage, facts: FactTable) -> Fact | None:
    for fact in facts.for_url(page.url, verified_only=True):
        if fact.claim_type == "price" and fact.value:
            return fact
    return None


def _fare_anchor(fact: Fact) -> re.Pattern:
    amount = re.escape(fact.value.replace(",", ""))
    return re.compile(r"\$\s*" + amount + r"(?:\.0+)?\b")


def insert_after_fare(html: str, fact: Fact, text: str, element_id: str) -> tuple[str, bool]:
    """Insert one labelled block after the first visible matching fare."""
    soup = BeautifulSoup(html or "", "html.parser")
    anchor = _fare_anchor(fact)
    for node in soup.find_all(string=True):
        if node.parent and node.parent.name in {"script", "style", "noscript"}:
            continue
        if not anchor.search(str(node)):
            continue
        block = soup.new_tag("section", id=element_id)
        block["aria-label"] = "Fare information"
        heading = soup.new_tag("h2")
        heading.string = "Fare information"
        para = soup.new_tag("p")
        para.string = text
        block.append(heading)
        block.append(para)
        node.parent.insert_after(block)
        return str(soup), True
    return html, False


class StatisticsAdditionArm(Arm):
    name = "statistics_addition"
    needs_verified_facts = True
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        fact = _fare_fact(page, facts)
        html, inserted, added_text = page.html, False, ""
        claims = []
        if fact:
            added_text = fact.visible_sentence()
            html, inserted = insert_after_fare(
                html, fact, added_text, "geo-statistics-addition")
            if inserted:
                claims.append(AddedClaim(
                    span=added_text, fact_id=fact.fact_id, source_url=fact.source_url,
                    kind="statistic_baseline_fact"))
        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest(),
            baseline_sha256=page.sha256, baseline_words=page.words,
            optimised_words=len(clean.split()), page_type=page.page_type, claims=claims,
            notes={
                "preserves_length": False,
                "treatment": "deterministic_page_specific_fare_clarification",
                "llm": None,
                "append_mode": False,
                "inserted": inserted,
                "fact_id": fact.fact_id if fact and inserted else "",
                "source_url": fact.source_url if fact and inserted else "",
                "added_text": added_text if inserted else "",
                "unchanged_reason": "no_anchorable_page_specific_verified_price" if not inserted else "",
                "claims": [{"span": c.span, "fact_id": c.fact_id,
                            "source_url": c.source_url, "kind": c.kind} for c in claims],
            },
        )
