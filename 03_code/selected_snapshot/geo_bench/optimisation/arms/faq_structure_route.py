"""Visible, server-rendered Q&A from baseline page facts only.

This replaces the compound FAQ arm. It never reads another arm, evaluation
queries, or SSR fare data, and it does not add FAQPage JSON-LD. The treatment
is solely visible Q&A grounded in human-verified facts from this exact frozen
page. Pages without such a fact remain unchanged rather than borrowing a
brand-wide claim from a different URL.
"""
from __future__ import annotations

import hashlib
import html as htmlmod

from ...config import CONFIG
from ..base import AddedClaim, Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from .faq_structure import _question_for
from ...retrieval.cleaner import clean_html


class FaqStructureRouteArm(Arm):
    name = "faq_structure_route"
    needs_verified_facts = True
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        # `for_url`, rather than `for_page`: no cross-page brand fallback.
        page_facts = facts.for_url(page.url, verified_only=True)
        ordered = sorted(page_facts, key=lambda f: 0 if f.claim_type == "price" else 1)
        pairs, claims, seen = [], [], set()
        for fact in ordered:
            if len(pairs) >= CONFIG.max_faq_pairs:
                break
            question = _question_for(fact, page)
            if question in seen:
                continue
            seen.add(question)
            answer = fact.visible_sentence()
            pairs.append((question, answer))
            claims.append(AddedClaim(
                span=answer, fact_id=fact.fact_id, source_url=fact.source_url,
                kind="faq_baseline_fact"))

        html = page.html
        if pairs:
            items = "\n".join(
                f"<h3>{htmlmod.escape(question)}</h3>\n<p>{htmlmod.escape(answer)}</p>"
                for question, answer in pairs)
            section = (
                '\n<section id="geo-faq-route" aria-label="Frequently asked questions">\n'
                "<h2>Frequently asked questions</h2>\n" + items + "\n</section>\n")
            idx = html.lower().rfind("</body>")
            html = html[:idx] + section + html[idx:] if idx >= 0 else html + section

        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest(),
            baseline_sha256=page.sha256, baseline_words=page.words,
            optimised_words=len(clean.split()), page_type=page.page_type, claims=claims,
            notes={
                "preserves_length": False,
                "faq_scope": "visible_qa_from_baseline_page_facts_only",
                "faq_jsonld_added": False,
                "source_arm": "baseline",
                "faq_pairs_generated": len(pairs),
                "unchanged_reason": "no_page_specific_verified_fact" if not pairs else "",
                "claims": [{"span": c.span, "fact_id": c.fact_id,
                            "source_url": c.source_url, "kind": c.kind} for c in claims],
            },
        )
