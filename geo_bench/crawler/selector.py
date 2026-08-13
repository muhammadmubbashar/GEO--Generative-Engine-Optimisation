"""Turn a raw sitemap sweep into a defensible candidate list.

THE PROBLEM

A sweep of flightcentre.com.au returns ~28,000 flight URLs: the site generates
a page for every origin-destination pair, including routes with no Australian
leg, suburb-to-suburb pairs, and same-city pairs. Webjet returns ~26,000 on a
different URL grammar. Fetching all of them is impossible, and would let the
brand with more programmatic pages win the retrieval pool on volume alone.

THE RULE

Queries drive pages, never the reverse. A route page is kept only when BOTH
endpoint city slugs appear in the client's query set, matched WHOLE. Structural
pages (cabin class, multi-city, round-the-world, airline and airport hubs,
deals, advice) are kept up to a small cap each.

WHOLE-SLUG MATCHING MATTERS. Matching word fragments admitted
"za-ec-east-london" (East London, South Africa) on the token "london", and
"au-vic-melbourne-st-kilda" on "melbourne". Both are wrong destinations. Slugs
are therefore compared in full, with a small set of accepted aliases.

BRAND-AGNOSTIC GRAMMARS. Different sites express the same page type differently
(Flight Centre: /flights/au-vic-melbourne/gb-eng-london; Webjet:
/cheap-flights/albany-sydney/). Both grammars are recognised. What must never
differ between brands is the SELECTION RULE, only the pattern that reads it.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..config import CONFIG, Config

# --- route grammars, tried in order ---------------------------------------
# Flight Centre style: /flights/{cc}-{region}-{city}/{cc}-{region}-{city}
FC_ROUTE = re.compile(
    r"/flights?/([a-z]{2})-[a-z0-9]+-([a-z-]+?)/([a-z]{2})-[a-z0-9]+-([a-z-]+?)/?$", re.I)
# Webjet style: /cheap-flights/{origin}-{destination}/  (two city slugs)
WJ_ROUTE = re.compile(r"/cheap-flights/([a-z-]+?)-([a-z-]+?)/?$", re.I)
# Single-city hub: /cheap-flights/{city}/ or /flights/{city}/
CITY_HUB = re.compile(r"/(?:cheap-)?flights?/([a-z-]+?)/?$", re.I)

# Structural page types. ROUTE IS TESTED FIRST so a route URL containing
# "cheap-flights" is not misfiled as a deal.
TYPE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("cabin_class",     re.compile(r"(class-of-travel|business-class|first-class|"
                                   r"premium-economy|economy-class|mixed-class|cabin)", re.I)),
    ("multi_city_rtw",  re.compile(r"(multi-city|multicity|round-the-world|rtw)", re.I)),
    ("airline",         re.compile(r"/airlines?(/|$)", re.I)),
    ("flight_advice",   re.compile(r"(window-seat|/blog/|guide|advice|tips|faq|"
                                   r"baggage|when-to-book|check-in)", re.I)),
    ("deals_sale",      re.compile(r"(/deals?|sale|specials)", re.I)),
    ("destination_hub", re.compile(r"/flights?/(to-|destinations?/)", re.I)),
]

# Query words that are not places, so they never validate a city slug.
STOPWORDS = {"looking", "flights", "flight", "from", "book", "booking", "the",
             "for", "class", "city", "world", "round", "multi", "ticket",
             "tickets", "business", "premium", "economy", "cheap", "deals"}

# A few slugs whose query wording differs from the URL wording.
ALIASES = {"united-states": {"usa", "united", "states", "america"},
           "new-york": {"newyork"}, "ho-chi-minh-city": {"saigon"}}


def _slug_matches(slug: str, vocab: Set[str]) -> bool:
    """Whole-slug match only. 'east-london' must not pass on 'london'."""
    slug = slug.strip("-").lower()
    if slug in vocab:
        return True
    if slug in ALIASES and ALIASES[slug] & vocab:
        return True
    # allow a multi-word slug when the query used the same multi-word phrase
    return slug.replace("-", " ") in {v.replace("-", " ") for v in vocab}


def classify_structural(url: str) -> Optional[str]:
    for name, pattern in TYPE_PATTERNS:
        if pattern.search(url):
            return name
    return None


def parse_route(url: str) -> Optional[Tuple[str, str, str, str]]:
    """Return (origin_country, origin_city, dest_country, dest_city).

    Country is "" for grammars that do not encode it (e.g. Webjet)."""
    m = FC_ROUTE.search(url)
    if m:
        return (m.group(1).lower(), m.group(2).lower(),
                m.group(3).lower(), m.group(4).lower())
    m = WJ_ROUTE.search(url)
    if m:
        return ("", m.group(1).lower(), "", m.group(2).lower())
    return None


def cities_in_queries(queries_csv: Path) -> Set[str]:
    """Place vocabulary derived from the client's queries, not a hand-written
    list — so selection stays tied to client demand."""
    words: Set[str] = set()
    for row in csv.DictReader(queries_csv.open(encoding="utf-8")):
        tokens = [t for t in re.findall(r"[a-z]{3,}", row["query"].lower())
                  if t not in STOPWORDS]
        words.update(tokens)
        words.update(f"{a}-{b}" for a, b in zip(tokens, tokens[1:]))
    return words


def select(urls: List[str], queries_csv: Path, *,
           require_domestic_origin: str = "au",
           max_per_type: int = 6) -> List[Dict]:
    vocab = cities_in_queries(queries_csv)

    # Cities that exist in the domestic country, learned from the URLs
    # themselves. If "sydney" appears as an Australian origin, then a query
    # asking for flights TO sydney means the Australian one — not Sydney,
    # Nova Scotia. Same for Melbourne, Australia vs Melbourne, Florida.
    domestic_cities: Set[str] = set()
    if require_domestic_origin:
        for u in urls:
            r = parse_route(u)
            if r and r[0] == require_domestic_origin:
                domestic_cities.add(r[1])
            if r and r[2] == require_domestic_origin:
                domestic_cities.add(r[3])

    chosen: List[Dict] = []
    seen_types: Dict[str, int] = defaultdict(int)
    seen: Set[str] = set()
    rejected: Dict[str, int] = defaultdict(int)

    for url in urls:
        if url in seen:
            continue

        ptype = None
        route = parse_route(url)
        if route is not None:
            o_country, o_city, d_country, d_city = route
            if o_city == d_city or d_city.startswith(o_city + "-"):
                rejected["same-city"] += 1          # melbourne -> melbourne-st-kilda
                continue
            if (require_domestic_origin and o_country
                    and o_country != require_domestic_origin):
                rejected["foreign-origin"] += 1     # dubai -> prague
                continue
            if (require_domestic_origin and d_city in domestic_cities
                    and d_country and d_country != require_domestic_origin):
                rejected["wrong-country-city"] += 1   # Melbourne FL, Sydney NS
                continue
            if _slug_matches(o_city, vocab) and _slug_matches(d_city, vocab):
                ptype = "route"
            else:
                # Not a route the client asked about. It may still be a
                # structural page whose URL merely LOOKS like a route
                # (e.g. /cheap-flights/business-class-london/), so fall
                # through rather than discarding it outright.
                ptype = classify_structural(url)
                if ptype is None:
                    rejected["not-in-queries"] += 1
                    continue

        if ptype is None:
            ptype = classify_structural(url)
        if ptype is None:
            m = CITY_HUB.search(url)
            if m and _slug_matches(m.group(1), vocab):
                ptype = "destination_hub"
            else:
                continue
        if ptype != "route" and seen_types[ptype] >= max_per_type:
            continue

        seen_types[ptype] += 1
        seen.add(url)
        chosen.append({"url": url, "page_type": ptype})

    select.last_rejections = dict(rejected)          # surfaced by report()
    return chosen


def write_candidates(rows: List[Dict], brand: str, out: Path,
                     append: bool = True) -> Path:
    exists = out.exists()
    with out.open("a" if (append and exists) else "w", newline="",
                  encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["brand", "url", "page_type", "note"])
        if not exists or not append:
            w.writeheader()
        for r in rows:
            w.writerow({"brand": brand, "url": r["url"],
                        "page_type": r["page_type"], "note": "auto-selected"})
    return out


def report(rows: List[Dict], total_discovered: int) -> str:
    counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["page_type"]] += 1
    lines = [f"discovered {total_discovered:,} URLs -> selected {len(rows)}", ""]
    for ptype in CONFIG.page_types:
        lines.append(f"  {ptype:<18}{counts.get(ptype, 0):>4}")

    rejections = getattr(select, "last_rejections", {})
    if rejections:
        lines += ["", "  routes rejected:"]
        for reason, n in sorted(rejections.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {reason:<18}{n:>7,}")

    missing = [p for p in CONFIG.page_types if not counts.get(p)]
    if missing:
        lines += ["", "  NOT FOUND: " + ", ".join(missing),
                  "  Record these as NONE in the coverage grid with today's date,",
                  "  or add them by hand after a site: search."]
    if total_discovered == 0:
        lines += ["", "  NO SITEMAP AVAILABLE for this domain.",
                  "  Collect by hand: run `site:<domain> <each query>` and add the",
                  "  top result to queries/urls.csv with its page_type."]
    return "\n".join(lines)