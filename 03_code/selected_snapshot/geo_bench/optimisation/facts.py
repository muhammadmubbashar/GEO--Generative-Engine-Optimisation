"""Verified fact table: load, query, extract candidates, assert-grounded.

Sprint A extracts *candidate* rows from frozen Flight Centre pages only.
The verifier accepts only rows with status=verified (human sign-off).
No external fetches.
"""
from __future__ import annotations

import csv
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from bs4 import BeautifulSoup

from ..config import CONFIG, Config
from ..retrieval.cleaner import extract_jsonld

FACT_FIELDS = (
    "fact_id", "subject", "claim", "value", "unit", "source_url",
    "source_type", "verified_by", "verified_on", "status", "claim_type",
    "scope",
)

# Boilerplate that repeats near-identically across many route pages (company
# tenure, footer trust copy). Tagged scope="brand" so FactTable.for_page can
# use it on pages that have no route-specific fact of their own, instead of
# leaving ~half the corpus untreated. Still 100% quoted from a freeze page —
# nothing here is invented.
_BRAND_BOILERPLATE_RE = re.compile(
    r"\b(?:business|industry|experience)\b", re.I)

_NETWORK_UNITS = frozenset({"destinations", "countries", "airlines"})
_ORG_SIZE_UNITS = frozenset({
    "stores", "consultants", "offices", "locations", "experts",
    "advisers", "advisors", "agents",
})

USABLE_CLAIM_TYPES = frozenset({"price", "percent", "quantity", "date"})

# Marketing chrome that is not a travel fact even if it contains a digit.
_SKIP_NUMERIC = re.compile(
    r"(?:copyright|©|\b20[0-3]\d\b|\b19[0-9]{2}\b|phone|tel:|call\s+1[38]|"
    r"abn\b|acn\b|version|viewport|width=|height=|rgb\(|#"
    r"[0-9a-f]{3,8})",
    re.I,
)

PRICE_RE = re.compile(
    r"(?:(?:from|starting\s+(?:from|at)|fares?\s+from)\s+)?"
    r"(?:AU\$|A\$|AUD\s*)?"
    r"(?<![A-Za-z0-9_.])\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?",
    re.I,
)
PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
QUANTITY_RE = re.compile(
    r"\b(\d{1,4}(?:,\d{3})*)\s+"
    r"(stores?|consultants?|destinations?|offices?|locations?|"
    r"years?|hours?|airlines?|countries|cities|experts?|advisers?|"
    r"advisors?|agents?)\b",
    re.I,
)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+)?"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.I,
)
# Broader numeric spans for coverage counting (not all become CSV rows).
NUMERIC_SPAN_RE = re.compile(
    r"\$\s*\d[\d,]*(?:\.\d+)?|\bAUD\s*\d[\d,]*|\b\d{1,3}(?:\.\d+)?\s?%"
    r"|\b\d{1,4}(?:,\d{3})*\b",
)

CABIN_NAMES = (
    "premium economy", "business class", "first class", "economy class",
    "mixed class",
)
BRAND_SKIP = re.compile(
    r"\b(flight\s*centre|skyscanner|webjet|expedia|facebook|instagram|"
    r"twitter|linkedin|cookie|privacy)\b",
    re.I,
)
CAP_PHRASE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
)


@dataclass
class Fact:
    fact_id: str
    subject: str
    claim: str
    value: str
    unit: str
    source_url: str
    source_type: str = "freeze_page"
    verified_by: str = ""
    verified_on: str = ""
    status: str = "candidate"
    claim_type: str = ""
    scope: str = "page"

    def as_row(self) -> Dict[str, str]:
        return {k: str(getattr(self, k) or "") for k in FACT_FIELDS}

    def visible_sentence(self) -> str:
        """Short grounded sentence for FAQ / statistics / cite. Not the raw CSV claim.

        Templated per claim_type/unit so distinct facts read as distinct
        sentences instead of every arm reusing the one price template.
        """
        if self.claim_type == "price":
            shown = _format_money(self.value)
            unit = (self.unit or "AUD").strip() or "AUD"
            return (
                f"Flight Centre lists fares on this page from {shown} {unit}."
            )
        if self.claim_type == "quantity":
            unit = (self.unit or "").strip().lower()
            if unit == "years":
                return (
                    f"Flight Centre has more than {self.value} years of "
                    f"experience in the travel industry."
                )
            if unit == "hours":
                return f"This route takes approximately {self.value} hours to fly."
            if unit in _NETWORK_UNITS:
                return (
                    f"Flight Centre and its airline partners connect "
                    f"travellers to {self.value} {unit}."
                )
            if unit in _ORG_SIZE_UNITS:
                return f"Flight Centre operates {self.value} {unit} across Australia."
        claim = re.sub(r"\s+", " ", (self.claim or "")).strip()
        if len(claim) > 220:
            claim = claim[:217].rstrip() + "..."
        return claim or f"{self.value} {self.unit}".strip()

    @property
    def is_verified(self) -> bool:
        return self.status == "verified"

    @property
    def is_usable(self) -> bool:
        return self.claim_type in USABLE_CLAIM_TYPES


@dataclass
class ExtractResult:
    facts: List[Fact]
    numeric_claims_found: int
    named_entities: List[str]


class FactTable:
    """In-memory fact table. Only `verified` rows are queryable for arms."""

    def __init__(self, facts: Sequence[Fact] | None = None,
                 cfg: Config = CONFIG):
        self.cfg = cfg
        self.facts: List[Fact] = list(facts or [])

    @classmethod
    def load(cls, path: Path | None = None, cfg: Config = CONFIG) -> "FactTable":
        p = path or cfg.facts_file
        if not p.exists():
            return cls([], cfg)
        rows = list(csv.DictReader(p.open(encoding="utf-8")))
        facts = []
        for r in rows:
            facts.append(Fact(
                fact_id=(r.get("fact_id") or "").strip(),
                subject=(r.get("subject") or "").strip(),
                claim=(r.get("claim") or "").strip(),
                value=(r.get("value") or "").strip(),
                unit=(r.get("unit") or "").strip(),
                source_url=(r.get("source_url") or "").strip(),
                source_type=(r.get("source_type") or "freeze_page").strip(),
                verified_by=(r.get("verified_by") or "").strip(),
                verified_on=(r.get("verified_on") or "").strip(),
                status=(r.get("status") or "candidate").strip(),
                claim_type=(r.get("claim_type") or "").strip(),
                scope=(r.get("scope") or "page").strip() or "page",
            ))
        return cls(facts, cfg)

    def save(self, path: Path | None = None) -> Path:
        p = path or self.cfg.facts_file
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FACT_FIELDS)
            w.writeheader()
            for fact in self.facts:
                w.writerow(fact.as_row())
        return p

    def verified(self) -> List[Fact]:
        return [f for f in self.facts if f.is_verified]

    def for_url(self, url: str, verified_only: bool = True) -> List[Fact]:
        rows = self.verified() if verified_only else self.facts
        return [f for f in rows if f.source_url == url]

    def brand_facts(self, verified_only: bool = True) -> List[Fact]:
        """Company-wide facts (scope='brand'), deduped by value.

        These repeat near-identically across dozens of route pages (e.g.
        "40 years in the business"), so one canonical row per distinct value
        is kept, in fact_id order, for use as a fallback on pages that carry
        no route-specific verified fact of their own.
        """
        rows = self.verified() if verified_only else self.facts
        out: List[Fact] = []
        seen = set()
        for f in sorted(rows, key=lambda f: f.fact_id):
            if f.scope != "brand":
                continue
            key = (f.claim_type, f.value, f.unit)
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
        return out

    def for_page(self, page, verified_only: bool = True) -> List[Fact]:
        """Route-specific facts for this page; brand facts only if it has none.

        Fixes the "half the corpus gets no fact at all" gap: a page with no
        verified route-specific fact still gets the same genuine, on-page,
        company-wide facts every other FC page carries in its footer/FAQ
        boilerplate — never an invented one.
        """
        page_specific = self.for_url(page.url, verified_only=verified_only)
        if page_specific:
            return page_specific
        return self.brand_facts(verified_only=verified_only)

    def by_id(self, fact_id: str) -> Optional[Fact]:
        for f in self.facts:
            if f.fact_id == fact_id:
                return f
        return None

    def assert_grounded(self, span: str, page_text: str,
                        url: str = "") -> Optional[Fact]:
        """Return the verified fact that grounds `span`, or None."""
        span_n = _norm(span)
        page_n = _norm(page_text)
        if span_n and span_n in page_n:
            return None  # already on the source page; not a new claim
        for fact in self.verified():
            if url and fact.source_url and fact.source_url != url:
                continue
            if span_n in _norm(fact.claim) or span_n in _norm(fact.value):
                return fact
            if fact.value and fact.value in span:
                return fact
        return None

    def facts_block(self, url: str) -> str:
        return render_facts_block(self.for_url(url, verified_only=True))


def render_facts_block(rows: Sequence[Fact]) -> str:
    if not rows:
        return "(none)"
    lines = []
    for f in rows:
        lines.append(
            f"- [{f.fact_id}] {f.claim}  value={f.value} {f.unit}  "
            f"source={f.source_url}"
        )
    return "\n".join(lines)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _context(text: str, match: re.Match, radius: int = 90) -> str:
    a = max(0, match.start() - radius)
    b = min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def _format_money(value: str) -> str:
    raw = (value or "").replace(",", "").strip()
    try:
        n = float(raw)
    except ValueError:
        return value or ""
    if n >= 1000:
        return f"${n:,.0f}"
    if n == int(n):
        return f"${int(n)}"
    return f"${n:.2f}"


def _price_value(span: str) -> tuple[str, str]:
    digits = re.sub(r"[^\d.]", "", span)
    return digits, "AUD"


def extract_jsonld_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return extract_jsonld(soup)


def extract_named_entities(url: str, clean: str) -> List[str]:
    """Conservative entities already on the page or in the URL slug."""
    found: List[str] = []
    path = urllib.parse.urlsplit(url).path.lower()
    for part in path.split("/"):
        if not part:
            continue
        bits = [b for b in part.split("-") if b and b not in
                {"au", "nsw", "vic", "qld", "wa", "sa", "nt", "tas", "act",
                 "gb", "eng", "us", "id", "ba", "jp", "tok", "nz", "in",
                 "flights", "class", "of", "travel", "to", "from"}]
        for b in bits:
            if len(b) >= 4 and b.isalpha():
                found.append(b.replace("_", " ").title())
    blob = clean or ""
    low = blob.lower()
    for cabin in CABIN_NAMES:
        if cabin in low:
            found.append(cabin)
    for m in CAP_PHRASE_RE.finditer(blob):
        phrase = m.group(1).strip()
        if BRAND_SKIP.search(phrase):
            continue
        if len(phrase.split()) < 2:
            continue
        if phrase.lower() in {"Book Now", "Learn More", "Find Out"}:
            continue
        found.append(phrase)
    # unique, stable order
    seen = set()
    out = []
    for e in found:
        key = e.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out[:40]


def count_numeric_spans(text: str) -> int:
    n = 0
    for m in NUMERIC_SPAN_RE.finditer(text or ""):
        span = m.group(0)
        ctx = _context(text, m, 40)
        if _SKIP_NUMERIC.search(ctx) and not PRICE_RE.search(span):
            continue
        # Drop bare years and tiny IDs.
        if re.fullmatch(r"20[0-3]\d|19\d{2}", span):
            continue
        n += 1
    return n


def extract_candidates(url: str, html: str, clean: str,
                       page_type: str, start_id: int) -> ExtractResult:
    """Pull candidate facts from freeze HTML + cleaned text. No invention."""
    jsonld = extract_jsonld_text(html)
    corpus = " ".join(x for x in (clean, jsonld) if x)
    facts: List[Fact] = []
    n_id = start_id

    def _add(claim_type: str, span: str, value: str, unit: str, ctx: str,
             scope: str = "page"):
        nonlocal n_id
        key = (_norm(span), _norm(value), claim_type)
        if any((_norm(f.claim) == key[0] or _norm(f.value) == key[1])
               and f.claim_type == claim_type and f.source_url == url
               for f in facts):
            return
        n_id += 1
        facts.append(Fact(
            fact_id=f"F{n_id:04d}",
            subject=page_type or url,
            claim=ctx or span,
            value=value,
            unit=unit,
            source_url=url,
            source_type="freeze_page",
            verified_by="",
            verified_on="",
            status="candidate",
            claim_type=claim_type,
            scope=scope,
        ))

    for m in PRICE_RE.finditer(corpus):
        span = m.group(0).strip()
        val, unit = _price_value(span)
        if not val:
            continue
        _add("price", span, val, unit, _context(corpus, m))

    # JSON-LD structured prices (e.g. "price": "262")
    for m in re.finditer(r'"price"\s*:\s*"?([\d,.]+)"?', jsonld or "", re.I):
        val = re.sub(r"[^\d.]", "", m.group(1))
        if val:
            _add("price", m.group(0), val, "AUD", m.group(0))

    for m in PERCENT_RE.finditer(corpus):
        # A digit run immediately preceded by "%" is URL percent-encoding
        # (e.g. "Banner%20%282%29.png" false-matches "20%" and "282%"), not
        # a percentage in prose. Reject it here rather than downstream.
        if m.start() > 0 and corpus[m.start() - 1] == "%":
            continue
        span = m.group(0).strip()
        val = re.sub(r"[^\d.]", "", span)
        _add("percent", span, val, "percent", _context(corpus, m))

    for m in QUANTITY_RE.finditer(corpus):
        val = m.group(1).replace(",", "")
        unit = m.group(2).lower()
        ctx = _context(corpus, m)
        scope = "brand" if _BRAND_BOILERPLATE_RE.search(ctx) else "page"
        _add("quantity", m.group(0).strip(), val, unit, ctx, scope=scope)

    for m in DATE_RE.finditer(corpus):
        span = m.group(0).strip()
        _add("date", span, span, "date", _context(corpus, m))

    entities = extract_named_entities(url, clean)
    numeric = count_numeric_spans(corpus)
    return ExtractResult(facts=facts, numeric_claims_found=numeric,
                         named_entities=entities)


def merge_preserving_verified(existing: FactTable,
                              incoming: List[Fact]) -> FactTable:
    """Keep human-verified rows; add/replace candidates by (url, type, value)."""
    verified_keys = {}
    kept: List[Fact] = []
    for f in existing.facts:
        key = (f.source_url, f.claim_type, f.value)
        if f.is_verified:
            verified_keys[key] = f
            kept.append(f)
    n = 0
    for f in incoming:
        key = (f.source_url, f.claim_type, f.value)
        if key in verified_keys:
            continue
        n += 1
        f.fact_id = f"F{n:04d}"
        # shift ids after verified count
        kept.append(f)
    # Re-number candidates only; leave verified ids stable if present.
    out = []
    next_id = 1
    used = {f.fact_id for f in kept if f.is_verified}
    for f in kept:
        if f.is_verified:
            out.append(f)
            continue
        while f"F{next_id:04d}" in used:
            next_id += 1
        f.fact_id = f"F{next_id:04d}"
        used.add(f.fact_id)
        next_id += 1
        out.append(f)
    return FactTable(out, existing.cfg)
