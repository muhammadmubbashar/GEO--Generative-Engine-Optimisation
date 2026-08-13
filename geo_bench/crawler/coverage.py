"""Sought-vs-found grid — the evidence behind every zero.

When Flight Centre scores nothing on a query there are two possible causes:

    (a) the brand genuinely has no such page  -> a finding
    (b) we failed to collect the page         -> our sampling error

Only this grid distinguishes them. A cell is never blank: it holds a URL, or
"NONE" together with the date it was searched for. That converts an absence
from an assumption into a dated observation.

It also exposes the one bias that actually threatens this study — collecting
one brand thoroughly and another carelessly — because the same page-type
checklist is applied to every brand.
"""
import csv
import datetime as _dt
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from ..config import CONFIG, Config

# Literal sentinel in urls.csv meaning "searched, not found".
_ABSENT = "NONE"


def _real_urls(urls: List[str]) -> List[str]:
    """Drop empty cells and explicit NONE sentinels."""
    out = []
    for u in urls:
        u = (u or "").strip()
        if not u or u.upper() == _ABSENT:
            continue
        out.append(u)
    return out


class CoverageGrid:
    def __init__(self, cfg: Config = CONFIG):
        self.cfg = cfg

    def build(self, urls_csv: Path) -> List[Dict]:
        today = _dt.date.today().isoformat()
        have = defaultdict(list)
        notes = {}
        for r in csv.DictReader(open(urls_csv, encoding="utf-8")):
            brand = r["brand"].strip()
            ptype = r.get("page_type", "").strip()
            url = r["url"].strip()
            have[(brand, ptype)].append(url)
            if url.upper() == _ABSENT and r.get("note"):
                notes[(brand, ptype)] = r["note"].strip()

        grid: List[Dict] = []
        for brand in self.cfg.brands:
            for ptype in self.cfg.page_types:
                raw = have.get((brand, ptype), [])
                urls = _real_urls(raw)
                absent_recorded = any((u or "").strip().upper() == _ABSENT for u in raw)
                if urls:
                    status = "found"
                elif absent_recorded or raw:
                    status = "NONE"
                else:
                    status = "NONE"
                grid.append({
                    "brand": brand,
                    "page_type": ptype,
                    "status": status,
                    "n_urls": len(urls),
                    "urls": " | ".join(urls) if urls else _ABSENT,
                    "searched_on": "" if urls else today,
                    "method": ("" if urls else "sitemap + site: search"),
                    "note": notes.get((brand, ptype), ""),
                })
        return grid

    def write(self, grid: List[Dict]) -> Path:
        self.cfg.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.cfg.results_dir / "coverage_grid.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(grid[0].keys()))
            w.writeheader(); w.writerows(grid)
        return path

    def summary(self, grid: List[Dict]) -> str:
        lines = [f"{'brand':<16}{'found':>7}{'none':>7}{'pages':>8}", "-" * 38]
        for brand in self.cfg.brands:
            rows = [g for g in grid if g["brand"] == brand]
            found = sum(1 for g in rows if g["status"] == "found")
            lines.append(f"{brand:<16}{found:>7}{len(rows) - found:>7}"
                         f"{sum(g['n_urls'] for g in rows):>8}")
        lines.append("")
        lines.append("Unequal counts are EXPECTED and are a finding. What must "
                     "not differ is\nhow hard we looked: every NONE requires a "
                     "recorded search date.")
        lines.append("Literal url=NONE in urls.csv is an evidenced absence, "
                     "not a found page.")
        return "\n".join(lines)
