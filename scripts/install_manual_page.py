"""Install a manually saved view-source HTML file into a freeze page.

Usage:
  1. Open the URL in Chrome, Ctrl+U, Ctrl+S as UTF-8 HTML.
  2. python scripts/install_manual_page.py RUN_ID path/to/saved.html --url EXACT_URL

Exact URL must match the freeze page URL (normalised).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

from geo_bench.config import CONFIG
from geo_bench.experiment.run_store import RunStore
from geo_bench.retrieval.cleaner import clean_html
from geo_bench.search.live_retriever import LiveRetriever, normalise_url


def unwrap_chrome_view_source(raw: str) -> str:
    """Chrome Ctrl+U → Save often stores the view-source UI, not the page.

    Inner HTML lives in td.line-content cells. Using the wrapper as-is would
    inflate word counts with pretty-printed tags and bias the brand.
    """
    if "line-content" not in raw or "line-gutter-backdrop" not in raw:
        return raw
    soup = BeautifulSoup(raw, "html.parser")
    lines = soup.select("td.line-content")
    if not lines:
        return raw
    inner = "\n".join(td.get_text("", strip=False) for td in lines)
    low = inner.lower()
    if "<html" in low or "<!doctype" in low:
        return inner
    return raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("html_path", type=Path)
    ap.add_argument("--url", required=True, help="exact live URL from the freeze")
    args = ap.parse_args()

    html = unwrap_chrome_view_source(
        args.html_path.read_text(encoding="utf-8", errors="replace"))
    body, jl = clean_html(html)
    clean = (body + " " + jl).strip()
    words = len(clean.split())
    if words < CONFIG.live_fetch_min_words:
        raise SystemExit(f"cleaned text too thin ({words} words); not installing")

    store = RunStore.open(args.run_id, CONFIG)
    page = store.read_page(args.url)
    if page is None:
        raise SystemExit(f"URL not in freeze pages: {args.url}")
    if normalise_url(page["url"]) != normalise_url(args.url):
        raise SystemExit("URL normalisation mismatch")

    store.write_page(
        args.url, html, clean, http_status=200, method="manual-view-source",
        extra={
            "content_ok": True,
            "fallback": True,
            "fallback_live_url": args.url,
            "fetch_user_agent": CONFIG.live_fetch_user_agent,
            "manual_source_path": str(args.html_path),
            "note": "Manual Chrome view-source save; capture date = today.",
        },
    )
    LiveRetriever(CONFIG, store=store)._refresh_retrieval_coverage(store)
    print(f"installed words={words} method=manual-view-source url={args.url}")


if __name__ == "__main__":
    main()
