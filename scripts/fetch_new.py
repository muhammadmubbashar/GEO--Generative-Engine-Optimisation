"""Fetch ONLY urls.csv rows that are not yet in the corpus manifest.

`geo fetch` re-downloads every row and rewrites the whole manifest, which
would overwrite the frozen pages (including the manual view-source saves that
scripted fetching cannot reproduce). This script is the safe way to add pages
after the initial freeze: it fetches just the new scriptable rows, then you
re-run scripts/refresh_manifest.py to extend the freeze record.

Only flightcentre and webjet are scriptable; skyscanner and expedia block
non-browser fetchers and must be saved manually via view-source.

Usage:  python scripts/fetch_new.py
"""
import csv
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo_bench.crawler.fetcher import Fetcher

URLS_CSV = Path("queries/urls.csv")
MANIFEST = Path("corpus/manifest_baseline.csv")
CORPUS = Path("corpus/baseline")
SCRIPTABLE = {"flightcentre", "webjet"}


def main() -> None:
    have = {r["url"] for r in csv.DictReader(MANIFEST.open(encoding="utf-8"))}
    todo = [r for r in csv.DictReader(URLS_CSV.open(encoding="utf-8"))
            if r["url"].strip().startswith("http")
            and r["url"].strip() not in have
            and r["brand"].strip() in SCRIPTABLE]
    if not todo:
        print("Nothing to fetch — every scriptable URL is already in the manifest.")
        return

    fetcher = Fetcher()
    ok = failed = 0
    for i, row in enumerate(todo, 1):
        url, brand = row["url"].strip(), row["brand"].strip()
        print(f"[{i}/{len(todo)}] {url}")
        resp = fetcher.fetch_one(url)
        if resp is None or resp.status_code != 200:
            status = "robots/network" if resp is None else f"HTTP {resp.status_code}"
            print(f"  [FAILED {status}] — not saved")
            failed += 1
            continue
        folder = CORPUS / brand
        folder.mkdir(parents=True, exist_ok=True)
        name = urllib.parse.quote(url, safe="")[-80:] + ".html"
        (folder / name).write_text(resp.text, encoding="utf-8")
        print(f"  saved {name}  ({len(resp.text.split()):,} words)")
        ok += 1
        import time
        time.sleep(fetcher.delay)

    print(f"\nDone: {ok} saved, {failed} failed.")
    print("Next: python scripts/refresh_manifest.py  (extend the freeze record)")


if __name__ == "__main__":
    main()
