"""schema_markup — inject JSON-LD into <head>. Visible body unchanged.

Values come from the page itself (title, canonical, prices already in HTML).
Route pages use WebPage + Offer, not schema.org Flight (booking pages are
not flight instances).

This is a markup-only intervention. Its evaluated clean text is deliberately
the baseline clean text: JSON-LD must not become extra BM25/embedding tokens
or prompt text in a benchmark with no schema-aware consumer. That would test
keyword injection, not structured data.
"""
from __future__ import annotations

import hashlib
import json
import re

from bs4 import BeautifulSoup

from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable, PRICE_RE, _price_value
from ...retrieval.cleaner import clean_html


def _title(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return (fallback or "").strip()


def _meta_description(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return ""


_FROM_PRICE_RE = re.compile(
    r"(?:from|starting\s+(?:from|at)|fares?\s+from)\s+"
    r"(?:AU\$|A\$|AUD\s*)?\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?",
    re.I,
)


def _first_price(html: str, clean: str, title: str = "") -> tuple[str, str]:
    """Visible fare only. Skip raw HTML (JS like i.$9) and parse scraps like from $1."""
    surfaces = [title, _meta_description(html), clean or ""]
    min_fare = 20.0
    for blob in surfaces:
        for m in _FROM_PRICE_RE.finditer(blob or ""):
            value, currency = _price_value(m.group(0))
            try:
                if float(value) >= min_fare:
                    return value, currency
            except ValueError:
                continue
    for blob in surfaces:
        for m in PRICE_RE.finditer(blob or ""):
            value, currency = _price_value(m.group(0))
            try:
                if float(value) >= min_fare:
                    return value, currency
            except ValueError:
                continue
    return "", ""


def build_jsonld(page: FrozenPage, facts: FactTable) -> tuple[dict, list]:
    title = _title(page.html, page.title) or "Flight Centre"
    desc = _meta_description(page.html)
    price, currency = _first_price(page.html, page.clean, title)
    webpage = {
        "@type": "WebPage",
        "name": title,
        "url": page.url,
    }
    if desc:
        webpage["description"] = desc

    org = {"@type": "Organization", "name": "Flight Centre", "url": page.url}
    claims = []

    if page.page_type == "cabin":
        product = {"@type": "Product", "name": title, "url": page.url}
        if desc:
            product["description"] = desc
        nodes = [product, org]
        if price:
            nodes.append({
                "@type": "Offer",
                "url": page.url,
                "price": price,
                "priceCurrency": currency or "AUD",
            })
        return {"@context": "https://schema.org", "@graph": nodes}, claims

    if page.page_type == "generic":
        return {"@context": "https://schema.org", "@graph": [webpage, org]}, claims

    # route (and anything else treated as a booking landing page)
    nodes = [webpage, org]
    if price:
        nodes.append({
            "@type": "Offer",
            "url": page.url,
            "price": price,
            "priceCurrency": currency or "AUD",
            "name": title,
        })
    return {"@context": "https://schema.org", "@graph": nodes}, claims


def inject_jsonld(html: str, payload: dict) -> str:
    block = (
        '<script id="geo-schema-jsonld" type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "</script>\n"
    )
    lower = html.lower()
    # Last </head> — an earlier match can sit inside CSS/content strings.
    idx = lower.rfind("</head>")
    if idx >= 0:
        return html[:idx] + block + html[idx:]
    idx = lower.find("<body")
    if idx >= 0:
        return html[:idx] + "<head>" + block + "</head>" + html[idx:]
    return "<head>" + block + "</head>" + html


class SchemaMarkupArm(Arm):
    name = "schema_markup"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = True

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        payload, claims = build_jsonld(page, facts)
        html = inject_jsonld(page.html, payload)
        clean = page.clean
        digest = hashlib.sha256(
            html.encode("utf-8", errors="replace")).hexdigest()
        notes = {
            "preserves_length": True,
            "evaluation_representation": "baseline_clean_text",
            "jsonld_excluded_from_text_evaluation": True,
            "schema_types": [
                n.get("@type") for n in payload.get("@graph", [])
                if isinstance(n, dict)
            ],
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
