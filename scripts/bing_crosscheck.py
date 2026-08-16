"""Descriptive Bing vs Brave cross-check (external validity, one-off).

Brave stays the frozen study engine (decisions_log: Bing's Search API was
retired in Aug 2025, so no reproducible Bing freeze is possible). This
script answers one narrower question: "would the brand landscape look
similar if the engine were Bing?" — by fetching each study query's public
Bing AU SERP once, extracting organic results, and comparing brand
presence/ranks against the frozen Brave capture.

Raw HTML is cached under cache/bing/ so re-runs are free and auditable.
If Bing serves a bot-wall for a query, the row is marked blocked=1 and the
comparison excludes it (or set SERPAPI_KEY to use SerpAPI instead).

Usage:  python scripts/bing_crosscheck.py [RUN_ID]
Output: results/bing_crosscheck.csv (+ printed summary)
"""
import csv
import hashlib
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from geo_bench.config import CONFIG
from geo_bench.experiment.run_store import RunStore
from geo_bench.search.live_retriever import brand_for_url

CACHE = Path("cache/bing")
DELAY_S = 2.5
TIMEOUT_S = 25
TOP_N = 10

_HEADERS = {
    "User-Agent": CONFIG.live_fetch_user_agent,
    "Accept-Language": "en-AU,en;q=0.9",
}

_LINK_RE = re.compile(
    r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="([^"]+)"', re.S)


def _ascii_query(query: str) -> str:
    """Normalise smart quotes to ASCII; the query intent is unchanged."""
    return (query.replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"'))


_PREFIXES = (
    "i'm looking to book ",
    "i'm looking for ",
    "i'm looking to ",
    "find me ",
    "advise on ",
)


def core_intent(query: str) -> str:
    """Bing's no-JS HTML endpoint ranks conversational queries by their
    leading tokens only ('i am ...' returns AM radio; 'looking for ...'
    returns the TV series) — a degraded pathway, not the real ranker.
    For this descriptive brand-landscape check we therefore query Bing with
    the core intent (conversational prefix stripped). The form actually
    sent is recorded per row in the `bing_query` column."""
    q = _ascii_query(query).strip()
    low = q.lower()
    for p in _PREFIXES:
        if low.startswith(p):
            return q[len(p):].strip()
    return q


def _cache_path(query: str) -> Path:
    h = hashlib.sha256(_ascii_query(query).encode("utf-8")).hexdigest()[:16]
    return CACHE / f"{h}.html"


def fetch_bing_html(query: str) -> str:
    p = _cache_path(query)
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    url = ("https://www.bing.com/search?q="
           + urllib.parse.quote(_ascii_query(query))
           + "&cc=AU&setlang=en&count=20")
    resp = requests.get(url, headers=_HEADERS, timeout=TIMEOUT_S)
    resp.raise_for_status()
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(resp.text, encoding="utf-8")
    time.sleep(DELAY_S)
    return resp.text


def fetch_bing_serpapi(query: str, key: str) -> list:
    resp = requests.get("https://serpapi.com/search.json", params={
        "engine": "bing", "q": query, "cc": "AU", "count": 20,
        "api_key": key}, timeout=TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    return [r.get("link", "") for r in data.get("organic_results", [])]


def parse_bing_links(html: str) -> list:
    links = []
    for href in _LINK_RE.findall(html):
        href = href.replace("&amp;", "&")
        # Bing wraps some results in a redirect.
        if href.startswith("https://www.bing.com/ck/"):
            m = re.search(r"[?&]u=a1([^&]+)", href)
            if m:
                import base64
                pad = m.group(1) + "=" * (-len(m.group(1)) % 4)
                try:
                    href = base64.urlsafe_b64decode(pad).decode(
                        "utf-8", errors="replace")
                except Exception:
                    continue
        if href.startswith("http"):
            links.append(href)
    # de-dup preserving order
    seen, out = set(), []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def brave_brand_ranks(store: RunStore, qid: str) -> dict:
    data = store.read_retrieval(qid)
    return data.get("brand_ranks") or {}


def main() -> int:
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    store = RunStore.resolve(run_id, CONFIG)
    queries = list(csv.DictReader(
        CONFIG.queries_file.open(encoding="utf-8")))
    serpapi_key = os.environ.get("SERPAPI_KEY", "")
    print(f"Bing cross-check over {len(queries)} queries "
          f"(engine of record stays Brave, freeze {store.run_id})")
    if serpapi_key:
        print("  using SerpAPI (SERPAPI_KEY set)")

    rows = []
    for qi, row in enumerate(queries, 1):
        qid, query = row["id"], row["query"]
        # SerpAPI reaches the real ranker -> verbatim query; the no-JS HTML
        # endpoint needs the core-intent form (see core_intent docstring).
        bing_query = _ascii_query(query) if serpapi_key else core_intent(query)
        blocked, links = 0, []
        try:
            if serpapi_key:
                links = fetch_bing_serpapi(bing_query, serpapi_key)
            else:
                html = fetch_bing_html(bing_query)
                links = parse_bing_links(html)
                if not links:
                    blocked = 1
        except requests.RequestException:
            blocked = 1
        bing_ranks = {}
        for rank, url in enumerate(links[:TOP_N], 1):
            b = brand_for_url(url, CONFIG)
            if b != "other" and b not in bing_ranks:
                bing_ranks[b] = rank
        try:
            brave = brave_brand_ranks(store, qid)
        except FileNotFoundError:
            brave = {}
        rec = {"query_id": qid, "query": query, "bing_query": bing_query,
               "blocked": blocked, "bing_n_organic": len(links)}
        for b in CONFIG.brands:
            rec[f"bing_rank_{b}"] = bing_ranks.get(b, "")
            rec[f"brave_rank_{b}"] = brave.get(b, "")
        rows.append(rec)
        fc_b = bing_ranks.get(CONFIG.our_brand, "-")
        fc_v = brave.get(CONFIG.our_brand, "-")
        print(f"  [{qi}/{len(queries)}] {qid}  FC bing={fc_b} brave={fc_v}"
              f"{'  BLOCKED' if blocked else ''}", flush=True)

    out = CONFIG.results_dir / "bing_crosscheck.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwritten: {out}")

    ok = [r for r in rows if not r["blocked"]]
    print(f"\nusable Bing SERPs: {len(ok)}/{len(rows)}")

    def _rank(v, top=None):
        # brand_ranks stores explicit nulls for absent brands.
        if v in ("", None, "None"):
            return None
        v = int(v)
        return v if (top is None or v <= top) else None

    if ok:
        for b in CONFIG.brands:
            pairs = [(_rank(r[f"bing_rank_{b}"], 10),
                      _rank(r[f"brave_rank_{b}"], 10)) for r in ok]
            both = sum(1 for g, v in pairs if g and v)
            bing_only = sum(1 for g, v in pairs if g and not v)
            brave_only = sum(1 for g, v in pairs if v and not g)
            print(f"  {b:<14} top-10 on both: {both:>3}   "
                  f"bing-only: {bing_only:>3}   brave-only: {brave_only:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
