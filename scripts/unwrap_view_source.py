"""One-off repair tool: convert Chrome 'view-source:' page saves back to raw HTML.

Saving Chrome's view-source: tab with Ctrl+S produces a wrapper document where
every line of the original source sits HTML-escaped inside
<td class="line-content"> cells. Parsed naively, the whole page source
(tags, JS, JSON) becomes visible text and would poison the corpus.

This script extracts the line-content cells, strips Chrome's syntax-highlight
spans, unescapes the entities, and writes the reconstructed original HTML back
in place. Files that already look like raw HTML are left untouched.

Usage:  python scripts/unwrap_view_source.py corpus/baseline/skyscanner corpus/baseline/expedia
"""
import html
import re
import sys
from pathlib import Path

CELL = re.compile(r'<td class="line-content">(.*?)</td>', re.S)
TAG = re.compile(r"<[^>]+>")


def is_view_source_save(text: str) -> bool:
    return 'class="line-content"' in text[:2000] or (
        text.lstrip().startswith("<!-- saved from url=") and 'class="line-content"' in text)


def unwrap(text: str) -> str:
    lines = []
    for cell in CELL.findall(text):
        lines.append(html.unescape(TAG.sub("", cell)))
    return "\n".join(lines)


def main(folders):
    for folder in folders:
        for p in sorted(Path(folder).glob("*.html")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            if not is_view_source_save(text):
                print(f"  [skip - already raw] {p.name}")
                continue
            raw = unwrap(text)
            if len(raw) < 1000 or "<html" not in raw.lower():
                print(f"  [FAILED to unwrap - left unchanged] {p.name}")
                continue
            p.write_text(raw, encoding="utf-8")
            print(f"  [unwrapped {len(text):>9,} -> {len(raw):>9,} chars] {p.name}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["corpus/baseline/skyscanner", "corpus/baseline/expedia"])
