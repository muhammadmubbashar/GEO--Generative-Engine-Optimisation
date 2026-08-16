"""FC position routing — eligibility for fixed vs reindexed layers."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional

from ..config import CONFIG, Config
from ..crawler.quality import (
    canonical_fetch_method,
    is_usable,
    query_usable_docs,
)
from ..search.live_retriever import brand_for_url
from .run_store import RunStore


def _fc_page_usable(store: RunStore, url: str, cfg: Config) -> bool:
    page = store.read_page(url)
    if page is None:
        return False
    words = int(page.get("words") or 0)
    method = canonical_fetch_method(
        str(page.get("method") or ""),
        kind=str(page.get("live_kind") or ""),
        words=words, cfg=cfg)
    return is_usable(words, method, cfg)


def route_query(store: RunStore, query_id: str,
                cfg: Config = CONFIG) -> Dict:
    """Assign layer eligibility from frozen capture + QC.

    Routing decides eligibility, not exclusion. Every query is eligible for
    reindexed. fixed requires FC in the analysis top-10 *and* usable text.
    """
    data = store.read_retrieval(query_id)
    results = list(data.get("results") or [])
    analysis_depth = int(data.get("analysis_depth")
                         or cfg.search_analysis_depth)
    capture_depth = int(data.get("capture_depth")
                        or cfg.search_capture_depth)
    fc = cfg.our_brand

    fc_rank: Optional[int] = None
    fc_url: Optional[str] = None
    for i, row in enumerate(results, 1):
        brand = row.get("brand") or brand_for_url(row.get("url") or "", cfg)
        if brand == fc:
            fc_rank = i
            fc_url = row.get("url")
            break
    if fc_rank is None and data.get("fc_search_rank") not in (None, ""):
        try:
            fc_rank = int(data["fc_search_rank"])
        except (TypeError, ValueError):
            fc_rank = None

    fc_usable = bool(fc_url) and _fc_page_usable(store, fc_url, cfg)
    # Present by URL but failed QC → not usable for routing.
    if fc_url and not fc_usable:
        fc_usable = False

    if fc_rank is None:
        route = "absent"
        note = "Type-A coverage - FC absent from Brave top-20"
    elif fc_rank <= analysis_depth:
        route = "top10"
        note = "" if fc_usable else "FC in top-10 by URL but failed QC (not usable)"
    elif fc_rank <= capture_depth:
        route = "rank11-20"
        note = ""
    else:
        route = "absent"
        note = "Type-A coverage - FC outside capture depth"

    eligible_fixed = route == "top10" and fc_usable
    usable_docs = query_usable_docs(store, query_id, cfg)
    low_usable = usable_docs < cfg.min_usable_docs_per_query

    return {
        "query_id": query_id,
        "fc_best_rank": fc_rank if fc_rank is not None else "",
        "fc_usable": int(fc_usable),
        "route": route,
        "eligible_fixed": int(eligible_fixed),
        "eligible_reindexed": 1,
        "usable_docs": usable_docs,
        "low_usable": int(low_usable),
        "note": note,
    }


def write_routing_csv(store: RunStore, cfg: Config = CONFIG) -> Path:
    queries = sorted(p.stem for p in store.retrieval_dir.glob("*.json"))
    rows = [route_query(store, qid, cfg) for qid in queries]
    path = cfg.routing_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["query_id", "fc_best_rank", "fc_usable", "route",
              "eligible_fixed", "eligible_reindexed", "usable_docs",
              "low_usable", "note"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    store.write_json(store.root / "routing.json", rows)
    return path


def load_routing(cfg: Config = CONFIG) -> Dict[str, Dict]:
    path = cfg.routing_path()
    if not path.exists():
        return {}
    return {r["query_id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}


def render_routing(rows: List[Dict], cfg: Config = CONFIG) -> str:
    lines = [
        "FC POSITION ROUTING",
        f"analysis k={cfg.search_analysis_depth}  "
        f"capture k={cfg.search_capture_depth}  "
        f"min usable docs={cfg.min_usable_docs_per_query}",
        "",
        f"{'query':<8}{'rank':>6}{'usable':>8}  {'route':<12}"
        f"{'fixed':>7}{'reidx':>7}{'docs':>6}  note",
        "-" * 80,
    ]
    for r in rows:
        rank = r.get("fc_best_rank", "")
        lines.append(
            f"{r['query_id']:<8}{str(rank):>6}"
            f"{'Y' if int(r.get('fc_usable') or 0) else 'N':>8}  "
            f"{str(r.get('route') or ''):<12}"
            f"{'Y' if int(r.get('eligible_fixed') or 0) else 'N':>7}"
            f"{'Y':>7}"
            f"{int(r.get('usable_docs') or 0):>6}  "
            f"{r.get('note') or ''}"
        )
    n = len(rows)
    n_fixed = sum(int(r.get("eligible_fixed") or 0) for r in rows)
    n_absent = sum(1 for r in rows if r.get("route") == "absent")
    n_mid = sum(1 for r in rows if r.get("route") == "rank11-20")
    n_low = sum(int(r.get("low_usable") or 0) for r in rows)
    lines += [
        "",
        f"n={n}  eligible_fixed={n_fixed}  rank11-20={n_mid}  "
        f"absent(Type-A)={n_absent}  low_usable={n_low}",
        "Every query is eligible for reindexed. "
        "fixed runs only where FC is usable in analysis top-10.",
    ]
    return "\n".join(lines)
