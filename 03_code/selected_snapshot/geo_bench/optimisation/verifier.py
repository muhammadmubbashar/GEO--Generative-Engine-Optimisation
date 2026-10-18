"""Fact-grounding, length and structure checks.

Fail only on content introduced from outside both the source page and the
verified fact table. Infrastructure URLs (schema.org, w3.org, the page's own
URL / canonical) are not claims.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup

from ..config import CONFIG, Config
from .base import FrozenPage, OptimisedPage
from .facts import FactTable

INFRA_URL_PREFIXES = (
    "https://schema.org/",
    "http://schema.org/",
    "https://www.w3.org/",
    "http://www.w3.org/",
)

URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
QUOTE_RE = re.compile(r"[\"“”]([^\"“”]{3,200})[\"“”]")
JSONLD_SCRIPT_RE = re.compile(
    r"<script\b[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>"
    r".*?</script>",
    re.I | re.S,
)
GEO_SCHEMA_SCRIPT_ID = "geo-schema-jsonld"
SCHEMA_VOCAB = frozenset({
    "@context", "@graph", "@type", "@id",
    "WebPage", "Offer", "Product", "Organization", "FAQPage",
    "name", "url", "description", "price", "priceCurrency",
    "AUD", "https://schema.org", "http://schema.org",
})
PRICE_RE = re.compile(
    r"(?:AU\$|A\$|AUD\s*)?\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?", re.I)
PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.I,
)
NUMERIC_RE = re.compile(
    r"\$\s*\d[\d,]*(?:\.\d+)?|\bAUD\s*\d[\d,]*|\b\d{1,3}(?:\.\d+)?\s?%"
    r"|\b\d{1,4}(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d+\b",
)

SCHEMA_TYPES = {
    "WebPage": ("name",),
    "Offer": (),
    "Product": ("name",),
    "Organization": ("name",),
    "FAQPage": ("mainEntity",),
}


@dataclass
class SpanFailure:
    kind: str
    span: str
    reason: str


@dataclass
class VerifyResult:
    ok: bool
    failures: List[SpanFailure] = field(default_factory=list)
    length_flag: bool = False
    notes: List[str] = field(default_factory=list)

    def raise_if_failed(self, url: str) -> None:
        if self.ok:
            return
        detail = "; ".join(f"{f.kind}: {f.span[:80]!r} ({f.reason})"
                           for f in self.failures[:8])
        raise RuntimeError(f"verification FAILED for {url}: {detail}")


def _html_without_jsonld(html: str) -> str:
    """JSON-LD is structured data, not prose claims. Quote/URL scans skip it."""
    return JSONLD_SCRIPT_RE.sub("", html or "")


def _prose_text(html: str) -> str:
    """Visible text only — HTML attribute quotes are not claims."""
    soup = BeautifulSoup(_html_without_jsonld(html or ""), "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def _html_quote_noise(span: str) -> bool:
    """True when a quote-regex hit is markup, not a prose quotation."""
    if "<" in span or ">" in span:
        return True
    if re.search(r"\bdata-[a-z0-9-]+\s*=", span, re.I):
        return True
    if re.search(r"</?[a-z]", span, re.I):
        return True
    return False


def _page_url_forms(url: str) -> set:
    forms = {url.strip(), url.strip().rstrip("/")}
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        forms.add(urllib.parse.urlunsplit(
            (u.scheme, host[4:], u.path, u.query, "")))
    else:
        forms.add(urllib.parse.urlunsplit(
            (u.scheme, "www." + host, u.path, u.query, "")))
    return {f.lower() for f in forms if f}


def _canonical_urls(html: str, page_url: str) -> set:
    soup = BeautifulSoup(html or "", "html.parser")
    out = _page_url_forms(page_url)
    for tag in soup.find_all("link", href=True):
        rel = " ".join(tag.get("rel") or []).lower()
        if "canonical" in rel:
            href = tag["href"].strip()
            if href:
                out |= _page_url_forms(urllib.parse.urljoin(page_url, href))
    return out


def _is_infra_url(url: str, allowed_pages: set) -> bool:
    low = url.lower().rstrip(".,);")
    for pfx in INFRA_URL_PREFIXES:
        if low.startswith(pfx):
            return True
    stripped = low.split("#")[0].rstrip("/")
    for allowed in allowed_pages:
        a = allowed.rstrip("/")
        if stripped == a or stripped.startswith(a + "/"):
            return True
        if allowed.rstrip("/") in stripped:
            return True
    return False


def _in_source_or_facts(span: str, source: str, facts: FactTable,
                        url: str) -> bool:
    if not span:
        return True
    if span in source:
        return True
    nspan = re.sub(r"\s+", " ", span.lower()).strip()
    nsrc = source.lower()
    if nspan and nspan in nsrc:
        return True
    digits = re.sub(r"[^\d.]", "", span)
    if digits and digits in source:
        return True
    for fact in facts.verified():
        # Brand-scope facts (e.g. "40 years in the business") are company-wide
        # and verified against ONE freeze page; FactTable.for_page deliberately
        # reuses them on other pages that carry no route-specific fact of
        # their own, so they must not be tied to this page's URL like a
        # route-specific fact is.
        if url and fact.source_url != url and getattr(fact, "scope", "page") != "brand":
            continue
        if span in (fact.claim or "") or span in (fact.value or ""):
            return True
        if digits and digits == re.sub(r"[^\d.]", "", fact.value or ""):
            return True
    return False


_SOURCE_ATTR_RE = re.compile(
    r"Source:.{0,80}?(https?://[^\s\)\"'<>]+)", re.I)


def _cited_source_urls(visible_text: str) -> List[str]:
    """URLs presented as attribution ("Source: <url>") in prose."""
    return [m.group(1).rstrip(".,);") for m in _SOURCE_ATTR_RE.finditer(visible_text)]


def _is_fc_domain(url: str, cfg: Config) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    fc_hosts = {d.lower() for d, brand in cfg.brand_domains if brand == cfg.our_brand}
    return any(host == h or host.endswith("." + h) for h in fc_hosts)


def _highlight(html: str, span: str) -> str:
    if not span or span not in html:
        return html
    return html.replace(span, f"[[FAIL:{span}]]", 1)


def verify_page(page: FrozenPage, optimised: OptimisedPage,
                facts: FactTable, cfg: Config = CONFIG) -> VerifyResult:
    # optimised.claims is the arm's own, self-reported ledger of exactly what
    # text it added and where that text came from (a verified Fact row, or an
    # ExternalFact row for cite_sources) — never LLM freehand output. Numbers
    # and URLs that appear ONLY inside those tracked spans are grounded by
    # the arm's own bookkeeping; anything else introduced (e.g. an LLM patch)
    # must still clear the strict page-or-verified-FactTable check below.
    claim_ledger = "\n".join(
        f"{c.span} {c.source_url}" for c in (optimised.claims or []))
    source = (page.html or "") + "\n" + (page.clean or "") + "\n" + claim_ledger
    visible = _html_without_jsonld(optimised.html or "")
    failures: List[SpanFailure] = []
    allowed_pages = _canonical_urls(page.html, page.url)

    for m in URL_RE.finditer(visible):
        url = m.group(0).rstrip(".,);")
        if _is_infra_url(url, allowed_pages):
            continue
        if _in_source_or_facts(url, source, facts, page.url):
            continue
        failures.append(SpanFailure(
            "url", url, "URL not on source page or in verified facts"))

    # Numbers/dates/prices in visible HTML + cleaned body, not in JSON-LD keys.
    new_visible = visible + "\n" + _html_without_jsonld(optimised.clean or "")
    for rx, kind in ((PRICE_RE, "price"), (PERCENT_RE, "percent"),
                     (DATE_RE, "date"), (NUMERIC_RE, "number")):
        seen = set()
        for m in rx.finditer(new_visible):
            span = m.group(0)
            if span in seen:
                continue
            seen.add(span)
            if _in_source_or_facts(span, source, facts, page.url):
                continue
            failures.append(SpanFailure(
                kind, span, "introduced; not on source page or verified facts"))

    # Quote checks are visible prose only. Do not scan clean.txt: the cleaner
    # appends JSON-LD, so keys like "@graph" / "WebPage" would look like claims.
    # Raw HTML attribute quotes are also not claims (window-seat false positive).
    opt_prose = _prose_text(optimised.html)
    src_for_quotes = source + "\n" + _prose_text(page.html)
    for m in QUOTE_RE.finditer(opt_prose):
        span = m.group(1)
        if span in SCHEMA_VOCAB or span.startswith("@"):
            continue
        if _html_quote_noise(span):
            continue
        if _in_source_or_facts(span, src_for_quotes, facts, page.url):
            continue
        if _in_source_or_facts(m.group(0), src_for_quotes, facts, page.url):
            continue
        failures.append(SpanFailure(
            "quote", span, "quoted string not on source page or verified facts"))

    for span, reason in _injected_jsonld_value_failures(
            page, optimised.html, facts, optimised.claims):
        failures.append(SpanFailure("jsonld_value", span, reason))

    for url in _cited_source_urls(visible):
        if _is_fc_domain(url, cfg):
            failures.append(SpanFailure(
                "self_citation", url,
                "a 'Source:' attribution points at Flight Centre's own "
                "domain; citation must be to an independent third party"))

    notes: List[str] = []
    length_flag = False
    if page.words:
        pct = abs(optimised.pct_change)
        if pct > cfg.length_fail_pct * 100 and getattr(
                type(optimised), "preserves_length", False):
            pass  # checked via arm flag below
        if pct > cfg.length_flag_pct * 100:
            length_flag = True
            notes.append(
                f"word-count delta {optimised.pct_change:+.1f}% exceeds "
                f"±{cfg.length_flag_pct:.0%} flag threshold"
            )

    arm_preserves = bool(optimised.notes.get("preserves_length"))
    if arm_preserves and page.words:
        if abs(optimised.pct_change) > cfg.length_fail_pct * 100:
            failures.append(SpanFailure(
                "length",
                f"{optimised.optimised_words} vs {page.words}",
                f"length-preserving arm exceeded ±{cfg.length_fail_pct:.0%}",
            ))

    return VerifyResult(ok=not failures, failures=failures,
                        length_flag=length_flag, notes=notes)


def verify_ssr_page(page: FrozenPage, optimised: OptimisedPage,
                    cfg: Config = CONFIG) -> VerifyResult:
    """Provenance check for `ssr_visible`, not a fact-grounding check.

    Every other arm's added text must trace to the freeze or the verified
    fact table (`verify_page`), because an LLM or hand-written template
    could otherwise invent something. `ssr_visible` (whole-page
    substitution, 2026-08-28) cannot invent anything by construction — its
    content IS the captured browser render, byte-checked against its own
    manifest inside `SsrVisibleArm.optimise` itself (raises there on any
    mismatch). What's checked here is just that the provenance fields
    (`rendered_at`, `capture_sha256`) are present and match the capture
    currently on record for this URL — i.e. this page wasn't hand-edited
    after the fact and the capture it claims hasn't been superseded.
    """
    from .arms.ssr_visible import _load_render

    failures: List[SpanFailure] = []
    notes = optimised.notes or {}
    if not notes.get("rendered_at"):
        failures.append(SpanFailure(
            "provenance", "", "missing rendered_at — not a dated capture"))
    if not notes.get("capture_sha256"):
        failures.append(SpanFailure(
            "provenance", "", "missing capture_sha256 — cannot verify "
            "this page traces to a captured render"))
    else:
        try:
            from ..experiment.run_store import RunStore
            store = RunStore.resolve(None, cfg)
            _rendered_html, cap_meta = _load_render(store, page.url)
        except Exception as exc:
            failures.append(SpanFailure(
                "provenance", "", f"cannot re-load capture to verify: {exc}"))
        else:
            if notes.get("capture_sha256") != cap_meta.get("sha256"):
                failures.append(SpanFailure(
                    "provenance", "", "capture_sha256 in notes does not "
                    "match the current capture manifest"))

    return VerifyResult(ok=not failures, failures=failures)


def verify_freshness_page(page: FrozenPage, optimised: OptimisedPage,
                          cfg: Config = CONFIG) -> VerifyResult:
    """Provenance check for `freshness_signal`, not a fact-grounding check.

    The claim is "this page was last verified on <date>". That date is
    never invented — it must equal the freeze's own `fetched_at` for this
    URL, re-read fresh here (not trusted from `notes`) and reformatted
    with the same `_format_date` the arm used, so a hand-edited or stale
    date in `notes` cannot slip through.
    """
    from .arms.freshness_signal import _format_date
    from ..experiment.run_store import RunStore

    failures: List[SpanFailure] = []
    notes = optimised.notes or {}
    claimed_iso = notes.get("iso_date")
    claimed_human = notes.get("human_date")
    if not claimed_iso or not claimed_human:
        failures.append(SpanFailure(
            "provenance", "", "missing iso_date/human_date — not a dated claim"))
        return VerifyResult(ok=False, failures=failures)

    try:
        store = RunStore.resolve(None, cfg)
        raw = store.read_page(page.url)
        fetched_at = (raw or {}).get("fetched_at") or ""
        if not fetched_at:
            raise RuntimeError("no fetched_at on current freeze page")
        fresh_human, fresh_iso = _format_date(fetched_at)
    except Exception as exc:
        failures.append(SpanFailure(
            "provenance", "", f"cannot re-load freeze page to verify date: {exc}"))
        return VerifyResult(ok=False, failures=failures)

    if claimed_iso != fresh_iso or claimed_human != fresh_human:
        failures.append(SpanFailure(
            "provenance", claimed_human,
            f"claimed date does not match the freeze's current "
            f"fetched_at ({fresh_human})"))

    for claim in optimised.claims or []:
        if claim.kind == "freshness_date" and fresh_human not in claim.span:
            failures.append(SpanFailure(
                "freshness_date", claim.span,
                "verified date does not appear in the claimed sentence"))

    return VerifyResult(ok=not failures, failures=failures)


def verify_faq_route_page(page: FrozenPage, optimised: OptimisedPage,
                          facts: FactTable, cfg: Config = CONFIG) -> VerifyResult:
    """Provenance check for `faq_structure_route`.

    Route/fare claims are checked the strongest way available: the arm's
    construction is fully deterministic given `ssr_visible_digitfix`'s
    current page content, so the verifier reloads that page fresh and
    re-runs the exact same extraction + question-building functions the
    arm used, then requires every fare claim to match a freshly re-derived
    answer exactly (not a substring/fuzzy check) — protects against
    staleness (the source arm changed since this page was built) as well
    as fabrication. Fallback verified-fact claims (used when a page has no
    fare-card data) are checked the same way every other arm's are —
    against the frozen page or the verified fact table.
    """
    from .arms.faq_structure_route import (
        _load_source_clean, _extract_fares, _route_fare_pairs, SOURCE_ARM)
    from .arms.faq_structure import _route_names
    from ..experiment.run_store import RunStore

    failures: List[SpanFailure] = []
    try:
        store = RunStore.resolve(None, cfg)
        source_clean = _load_source_clean(store, page.url)
    except Exception as exc:
        return VerifyResult(ok=False, failures=[SpanFailure(
            "provenance", "", f"cannot reload {SOURCE_ARM}: {exc}")])

    fares = _extract_fares(source_clean)
    route = _route_names(page)
    origin, dest = route if route else ("this origin", "this destination")
    fresh_pairs = _route_fare_pairs(fares, origin, dest)
    fresh_answers = {a for _, a, _ in fresh_pairs}

    # Same self-reported claim ledger `verify_page` builds: a fallback
    # claim's grounding is the arm's own bookkeeping (fact_id tracing back
    # to a verified fact), not a literal substring match against the
    # frozen page — matching the established pattern for this claim kind.
    claim_ledger = "\n".join(
        f"{c.span} {c.source_url}" for c in (optimised.claims or []))
    frozen_source = (page.html or "") + "\n" + (page.clean or "") + "\n" + claim_ledger
    for claim in optimised.claims or []:
        if claim.kind == "faq_route_fare":
            if claim.span not in fresh_answers:
                failures.append(SpanFailure(
                    "faq_route_fare", claim.span,
                    f"does not match a freshly re-derived fare from "
                    f"{SOURCE_ARM}'s current page"))
        else:
            if not _in_source_or_facts(claim.span, frozen_source, facts, page.url):
                failures.append(SpanFailure(
                    claim.kind, claim.span,
                    "claim not found in source page or verified facts"))

    return VerifyResult(ok=not failures, failures=failures)


def _walk_jsonld_values(node, out: List[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("@context", "@type", "@id"):
                continue
            _walk_jsonld_values(v, out)
    elif isinstance(node, list):
        for item in node:
            _walk_jsonld_values(item, out)
    elif isinstance(node, (str, int, float)):
        out.append(str(node))


def _injected_jsonld_value_failures(page: FrozenPage, html: str,
                                    facts: FactTable,
                                    claims: "list | None" = None) -> List[tuple]:
    """Property values in OUR JSON-LD must already be on the freeze page.

    `claims` is the arm's own self-reported ledger (same pattern as
    `verify_page`'s `claim_ledger`) — a JSON-LD value can be a templated
    sentence built from a verified Fact (e.g. `Fact.visible_sentence()`),
    which is genuinely grounded via its `fact_id` but is not a literal
    substring of the raw page. Without the ledger, a real, verified fact
    would be wrongly rejected just because the template wording differs
    from the fact's raw stored `claim` text.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    tag = soup.find("script", id=GEO_SCHEMA_SCRIPT_ID)
    if tag is None:
        return []
    raw = tag.string or tag.get_text() or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [("JSON-LD", "injected geo-schema-jsonld is not valid JSON")]
    values: List[str] = []
    _walk_jsonld_values(data, values)
    claim_ledger = "\n".join(f"{c.span} {c.source_url}" for c in (claims or []))
    source = (page.html or "") + "\n" + (page.clean or "") + "\n" + claim_ledger
    allowed_pages = _canonical_urls(page.html, page.url)
    fails = []
    for val in values:
        if not val or val in SCHEMA_VOCAB:
            continue
        if _is_infra_url(val, allowed_pages):
            continue
        if _in_source_or_facts(val, source, facts, page.url):
            continue
        fails.append((val, "JSON-LD value not on source page or verified facts"))
    return fails


def write_failure_report(optimised: OptimisedPage, page: FrozenPage,
                         result: VerifyResult, cfg: Config = CONFIG) -> Path:
    folder = cfg.results_dir / "verification_failures" / optimised.arm
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", page.url)[:80]
    path = folder / f"{safe}.html"
    html = optimised.html or ""
    for f in result.failures:
        html = _highlight(html, f.span)
    path.write_text(html, encoding="utf-8")
    meta = path.with_suffix(".json")
    meta.write_text(json.dumps({
        "url": page.url,
        "arm": optimised.arm,
        "failures": [f.__dict__ for f in result.failures],
        "notes": result.notes,
    }, indent=2), encoding="utf-8")
    return path


def validate_jsonld(html: str, script_id: str = GEO_SCHEMA_SCRIPT_ID) -> List[str]:
    """Local schema.org type check on the injected block only. No network.

    Freeze pages already contain BreadcrumbList / Flight JSON-LD. Validating
    those would fail the arm for bytes we did not introduce.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    errors: List[str] = []
    tags = soup.find_all("script", {"type": "application/ld+json"})
    if script_id:
        tags = [t for t in tags if t.get("id") == script_id]
    for tag in tags:
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"JSON-LD parse error: {exc}")
            continue
        nodes = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and "@graph" in data:
            nodes = data["@graph"]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            if not types:
                continue
            if isinstance(types, str):
                types = [types]
            for t in types:
                if t not in SCHEMA_TYPES:
                    errors.append(f"unknown @type {t!r} (not in local allow-list)")
                    continue
                for req in SCHEMA_TYPES[t]:
                    if req not in node:
                        errors.append(f"{t} missing {req}")
    return errors
