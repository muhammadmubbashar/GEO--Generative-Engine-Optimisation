"""Rebuild corpus/manifest_<arm>.csv from the files actually on disk.

Needed after pages are collected manually (view-source saves) rather than by
the scripted fetcher: the manifest is the freeze record, and `geo verify`
compares file hashes against it. Columns match crawler.fetcher.ManifestRow.

URL reconstruction:
  view-source_*.html   Chrome view-source saves: 'view-source_https___host_a_b.html'
                       -> https://host/a/b, matched against queries/urls.csv
                       (with and without a trailing .html).
  other *.html         scripted fetches named quote(url)[-80:]: unquoted name is
                       a suffix of the original URL, matched by endswith.

Usage:  python scripts/refresh_manifest.py [arm]
"""
import csv
import datetime as _dt
import hashlib
import sys
import urllib.parse
from pathlib import Path

CORPUS = Path("corpus")
URLS_CSV = Path("queries/urls.csv")


def load_url_rows():
    rows = []
    with URLS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["url"].strip().startswith("http"):
                rows.append({k: v.strip() for k, v in row.items()})
    return rows


def match_url(path: Path, brand: str, url_rows):
    candidates = [r for r in url_rows if r["brand"] == brand]
    name = path.name
    if name.startswith("view-source_"):
        stem = name[len("view-source_"):]
        if stem.endswith(".html"):
            stem = stem[:-5]
        rebuilt = stem.replace("https___", "https://").replace("_", "/")
        for r in candidates:
            if r["url"] in (rebuilt, rebuilt + ".html"):
                return r["url"], r["page_type"], "manual-view-source"
        return rebuilt, "", "manual-view-source"
    tail = urllib.parse.unquote(name[:-5] if name.endswith(".html") else name)
    # truncation can slice into a %XX escape, leaving junk before "www."
    tails = [tail] + ([tail[tail.find("www."):]] if "www." in tail else [])
    for t in tails:
        for r in candidates:
            if r["url"].endswith(t):
                return r["url"], r["page_type"], "script"
    return tail, "", "script"


def main(arm: str = "baseline"):
    url_rows = load_url_rows()
    out_rows = []
    unmatched = 0
    for brand_dir in sorted((CORPUS / arm).iterdir()):
        if not brand_dir.is_dir():
            continue
        for p in sorted(brand_dir.glob("*.html")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            url, page_type, method = match_url(p, brand_dir.name, url_rows)
            if not page_type:
                unmatched += 1
                print(f"  [no urls.csv match — recorded rebuilt URL] {p.name}")
            out_rows.append({
                "url": url, "brand": brand_dir.name, "page_type": page_type,
                "file": str(p),
                "fetched_at": _dt.datetime.fromtimestamp(
                    p.stat().st_mtime).isoformat(timespec="seconds"),
                "http_status": 200, "method": method,
                "words": len(text.split()),
                "sha256": hashlib.sha256(text.encode()).hexdigest()[:16],
            })
    out = CORPUS / f"manifest_{arm}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nManifest rebuilt: {out}  ({len(out_rows)} files, "
          f"{unmatched} without a urls.csv match)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "baseline")
