"""Usable-content QC for frozen live pages.

Do not auto-exclude anything. Flag, record, report. The team decides
exclusion before results are seen.

Fetch methods (canonical, stored per page):
    browser-ua · manual-view-source · common-crawl · bot-walled · unobtainable
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

from ..config import CONFIG, Config

if TYPE_CHECKING:
    from ..experiment.run_store import RunStore

FETCH_METHODS = (
    "browser-ua",
    "manual-view-source",
    "common-crawl",
    "bot-walled",
    "unobtainable",
)


def canonical_fetch_method(method: str, kind: str = "",
                           words: int = 0,
                           cfg: Config = CONFIG) -> str:
    """Map any historical/internal label onto the five spec methods."""
    m = (method or "").strip().lower()
    k = (kind or "").strip().lower()
    w = int(words or 0)

    if m in ("manual-view-source", "manual"):
        return "manual-view-source"
    if m in ("common-crawl", "common-crawl-exact-url"):
        return "common-crawl"
    if (
        m == "bot-walled"
        or k == "bot-wall"
        or m.endswith("bot-wall")
        or "bot-wall" in m
    ):
        return "bot-walled"
    if m in ("unobtainable",) or k in ("empty", "js-shell"):
        return "unobtainable"
    if k == "thin" or m.endswith("-thin") or m.endswith("-empty") or m.endswith("-js-shell"):
        return "unobtainable"
    if m in ("browser-ua", "cache") or m.startswith("browser-ua"):
        if k in ("empty", "js-shell", "thin") and w < cfg.live_fetch_min_words:
            return "unobtainable"
        if k == "bot-wall":
            return "bot-walled"
        return "browser-ua"
    if not m:
        return "unobtainable"
    if w < cfg.live_fetch_min_words:
        return "unobtainable"
    return "browser-ua"


def needs_review(words: int, cfg: Config = CONFIG) -> bool:
    return int(words or 0) < cfg.thin_page_word_threshold


def is_usable(words: int, method: str, cfg: Config = CONFIG) -> bool:
    """Usable for routing / usable-doc counts. Never used to drop a page."""
    if canonical_fetch_method(method, words=words, cfg=cfg) in (
            "bot-walled", "unobtainable"):
        return False
    return int(words or 0) >= cfg.thin_page_word_threshold


def qc_fields(words: int, method: str, kind: str = "",
              cfg: Config = CONFIG) -> Dict:
    canon = canonical_fetch_method(method, kind=kind, words=words, cfg=cfg)
    w = int(words or 0)
    return {
        "method": canon,
        "words": w,
        "needs_review": needs_review(w, cfg),
        "content_ok": is_usable(w, canon, cfg),
        "live_kind": kind or "",
    }


@dataclass
class QueryQC:
    query_id: str
    usable_docs: int
    n_docs: int
    low_usable: bool
    needs_review_n: int


@dataclass
class FreezeQCReport:
    pages: List[Dict] = field(default_factory=list)
    queries: List[QueryQC] = field(default_factory=list)

    def render(self, cfg: Config = CONFIG) -> str:
        lines = [
            "=" * 64,
            "USABLE-CONTENT QC (freeze)",
            f"word floor = {cfg.thin_page_word_threshold}  "
            f"min usable docs / query = {cfg.min_usable_docs_per_query}",
            "Do not auto-exclude. Flag, record, report.",
            "=" * 64,
            f"{'url':<48}{'words':>7}{'method':>16}  review  usable",
            "-" * 90,
        ]
        for p in self.pages:
            url = (p.get("url") or "")[:48]
            lines.append(
                f"{url:<48}{int(p.get('words') or 0):>7}"
                f"{str(p.get('method') or ''):>16}  "
                f"{'YES' if p.get('needs_review') else 'no':>6}  "
                f"{'YES' if p.get('content_ok') else 'no'}"
            )
        review_n = sum(1 for p in self.pages if p.get("needs_review"))
        usable_n = sum(1 for p in self.pages if p.get("content_ok"))
        lines += [
            "",
            f"pages={len(self.pages)}  needs_review={review_n}  usable={usable_n}",
            "",
            "=" * 64,
            "PER-QUERY USABLE DOCUMENTS (analysis pool)",
            "=" * 64,
            f"{'query':<8}{'usable':>8}{'docs':>8}{'review':>8}  flag",
            "-" * 48,
        ]
        for q in self.queries:
            flag = ("LOW_USABLE" if q.low_usable else "")
            lines.append(
                f"{q.query_id:<8}{q.usable_docs:>8}{q.n_docs:>8}"
                f"{q.needs_review_n:>8}  {flag}"
            )
        n_low = sum(1 for q in self.queries if q.low_usable)
        lines.append(
            f"\nlow_usable queries: {n_low}/{len(self.queries)} "
            f"(threshold < {cfg.min_usable_docs_per_query})"
        )
        return "\n".join(lines)


def run_freeze_qc(store: "RunStore", cfg: Config = CONFIG,
                  write_csv: bool = True) -> FreezeQCReport:
    """Inspect every frozen page + per-query analysis-pool usable counts."""
    pages: List[Dict] = []
    by_url: Dict[str, Dict] = {}
    for meta_path in sorted(store.pages_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        words = int(meta.get("words") or 0)
        method = canonical_fetch_method(
            str(meta.get("method") or ""),
            kind=str(meta.get("live_kind") or ""),
            words=words, cfg=cfg)
        row = {
            "url": meta.get("url") or "",
            "brand": meta.get("brand") or "",
            "words": words,
            "method": method,
            "needs_review": needs_review(words, cfg),
            "content_ok": is_usable(words, method, cfg),
            "http_status": meta.get("http_status", ""),
            "sha256": (meta.get("sha256") or "")[:16],
        }
        pages.append(row)
        if row["url"]:
            by_url[row["url"]] = row

    queries: List[QueryQC] = []
    for rpath in sorted(store.retrieval_dir.glob("*.json")):
        data = json.loads(rpath.read_text(encoding="utf-8"))
        qid = data.get("query_id") or rpath.stem
        analysis = list(data.get("analysis_urls") or [])
        if not analysis:
            analysis = [r["url"] for r in (data.get("results") or [])[
                : cfg.search_analysis_depth]]
        usable = 0
        review = 0
        for url in analysis:
            rec = by_url.get(url)
            if rec is None:
                page = store.read_page(url)
                if page is None:
                    continue
                w = int(page.get("words") or 0)
                m = canonical_fetch_method(
                    str(page.get("method") or ""),
                    kind=str(page.get("live_kind") or ""),
                    words=w, cfg=cfg)
                rec = {
                    "needs_review": needs_review(w, cfg),
                    "content_ok": is_usable(w, m, cfg),
                }
            if rec.get("content_ok"):
                usable += 1
            if rec.get("needs_review"):
                review += 1
        queries.append(QueryQC(
            query_id=qid,
            usable_docs=usable,
            n_docs=len(analysis),
            low_usable=usable < cfg.min_usable_docs_per_query,
            needs_review_n=review,
        ))

    report = FreezeQCReport(pages=pages, queries=queries)
    if write_csv:
        cfg.results_dir.mkdir(parents=True, exist_ok=True)
        path = cfg.results_dir / "qc_pages.csv"
        if pages:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(pages[0].keys()))
                w.writeheader()
                w.writerows(pages)
        qpath = cfg.results_dir / "qc_queries.csv"
        with qpath.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f, fieldnames=["query_id", "usable_docs", "n_docs",
                               "low_usable", "needs_review_n"])
            w.writeheader()
            for q in queries:
                w.writerow({
                    "query_id": q.query_id,
                    "usable_docs": q.usable_docs,
                    "n_docs": q.n_docs,
                    "low_usable": int(q.low_usable),
                    "needs_review_n": q.needs_review_n,
                })
    return report


def query_usable_docs(store: "RunStore", query_id: str,
                      cfg: Config = CONFIG) -> int:
    data = store.read_retrieval(query_id)
    analysis = list(data.get("analysis_urls") or [])
    if not analysis:
        analysis = [r["url"] for r in (data.get("results") or [])[
            : cfg.search_analysis_depth]]
    n = 0
    for url in analysis:
        page = store.read_page(url)
        if page is None:
            continue
        w = int(page.get("words") or 0)
        m = canonical_fetch_method(
            str(page.get("method") or ""),
            kind=str(page.get("live_kind") or ""),
            words=w, cfg=cfg)
        if is_usable(w, m, cfg):
            n += 1
    return n
