"""Boilerplate removal — turn raw HTML into the content an engine would judge.

WHY THIS MATTERS MORE THAN IT SOUNDS

Navigation, footers, cookie banners and newsletter forms repeat on every page
of a site. Left in, they cause three distinct problems:

1. VOLUME INFLATION. A brand with ten pages gets its footer ten times, adding
   chunks that carry no information but still occupy the candidate pool.

2. FALSE MATCHES. Flight Centre's footer lists "Qantas Emirates Singapore
   Airlines Qatar Airways" as navigation links with no route context — exactly
   the Semester 1 finding. Uncleaned, that footer is retrievable and would
   match airline queries. We would be measuring a navigation menu competing on
   content questions.

3. UNEQUAL TREATMENT. Sites with heavier chrome are penalised or flattered
   arbitrarily, depending on whether their boilerplate happens to match a query.

TWO PASSES

Pass 1 — structural. Remove elements that are boilerplate by definition
    (<nav>, <header>, <footer>, <aside>, <form>) and elements whose class or id
    marks them as chrome (cookie, banner, menu, breadcrumb, newsletter, modal).

Pass 2 — cross-page. Any line appearing on most of a brand's pages is
    boilerplate by evidence, whatever its markup. This is the robust pass: it
    catches chrome that uses no semantic tags at all, which is common on
    JavaScript-heavy commercial sites.

JSON-LD IS ALWAYS PRESERVED. Structured data is one of the interventions under
test; dropping it would make the schema arm untestable by construction.

APPLIED IDENTICALLY TO EVERY BRAND. No brand-specific rules, ever — that is
what keeps the comparison fair.
"""
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup

# Removed by definition
BOILERPLATE_TAGS = ["script", "style", "noscript", "nav", "header", "footer",
                    "aside", "form", "button", "svg", "iframe"]

# Removed when a class/id *token* matches chrome (not raw substring — "subheader"
# must not strip real content on competitor pages we download live).
_CHROME_TOKENS = {
    "cookie", "consent", "banner", "nav", "menu", "breadcrumb", "newsletter",
    "subscribe", "modal", "popup", "drawer", "sidebar", "footer", "header",
    "social", "share", "skiplink", "skip-link", "toolbar",
}


def _tokens(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw = " ".join(str(v) for v in value)
    else:
        raw = str(value)
    parts = re.split(r"[\s_]+", raw.lower())
    out: List[str] = []
    for p in parts:
        out.append(p)
        out.extend(p.split("-"))
    return [t for t in out if t]


def _is_chrome_attr(value) -> bool:
    for tok in _tokens(value):
        if tok in _CHROME_TOKENS:
            return True
        # cookie-banner, nav-item, footer-links, etc.
        if any(tok.startswith(c + "-") or tok.endswith("-" + c)
               for c in _CHROME_TOKENS if c != "nav"):
            return True
        if tok in ("navbar", "navitem", "navlink", "siteheader", "sitefooter",
                   "mainnav", "topnav", "breadcrumbs"):
            return True
    return False

# A line on this share of a brand's pages or more is treated as boilerplate
CROSS_PAGE_THRESHOLD = 0.6
MIN_PAGES_FOR_CROSS_PAGE = 3      # below this the signal is unreliable


def extract_jsonld(soup: BeautifulSoup) -> str:
    return " ".join(s.get_text(" ", strip=True)
                    for s in soup.find_all("script", {"type": "application/ld+json"}))


def clean_html(html: str) -> Tuple[str, str]:
    """Pass 1. Returns (body_text, jsonld_text)."""
    soup = BeautifulSoup(html, "html.parser")
    jsonld = extract_jsonld(soup)

    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()

    # decompose() destroys descendants too; skip elements already removed
    # (find_all returns a static list, so destroyed children can still appear)
    for el in soup.find_all(attrs={"class": True}):
        if el.decomposed:
            continue
        if _is_chrome_attr(el.get("class")):
            el.decompose()
    for el in soup.find_all(attrs={"id": True}):
        if el.decomposed:
            continue
        if _is_chrome_attr(el.get("id")):
            el.decompose()

    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    return text, jsonld


def find_repeated_lines(texts: List[str]) -> set:
    """Pass 2. Lines appearing on most pages of one brand are chrome."""
    if len(texts) < MIN_PAGES_FOR_CROSS_PAGE:
        return set()
    counts: Counter = Counter()
    for t in texts:
        for line in {s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", t) if s.strip()}:
            if 3 <= len(line.split()) <= 25:      # short repeated strings only
                counts[line] += 1
    cutoff = max(2, int(len(texts) * CROSS_PAGE_THRESHOLD))
    return {line for line, n in counts.items() if n >= cutoff}


def strip_lines(text: str, drop: set) -> str:
    if not drop:
        return text
    kept = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip() not in drop]
    return " ".join(kept).strip()


def clean_brand_pages(paths: List[Path]) -> Dict[Path, str]:
    """Both passes for one brand. Returns path -> cleaned text (JSON-LD appended)."""
    raw = {p: clean_html(p.read_text(encoding="utf-8", errors="ignore")) for p in paths}
    repeated = find_repeated_lines([body for body, _ in raw.values()])
    out: Dict[Path, str] = {}
    for p, (body, jsonld) in raw.items():
        cleaned = strip_lines(body, repeated)
        out[p] = (cleaned + " " + jsonld).strip()
    return out


def cleaning_report(paths: List[Path]) -> str:
    """What was removed, so the decision is auditable rather than invisible."""
    raw_words, clean_words = 0, 0
    for p in paths:
        html = p.read_text(encoding="utf-8", errors="ignore")
        raw_words += len(BeautifulSoup(html, "html.parser").get_text(" ").split())
    for text in clean_brand_pages(paths).values():
        clean_words += len(text.split())
    removed = raw_words - clean_words
    pct = (removed / raw_words * 100) if raw_words else 0
    return (f"{len(paths):>3} pages   raw {raw_words:>7,} words   "
            f"cleaned {clean_words:>7,}   removed {removed:>7,} ({pct:.0f}%)")
