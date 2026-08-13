"""Metrics.

COUNTED (ours) — plain counting, no model, no judgement, fully deterministic:
    retrieval_rate   did any FC passage reach the candidate set?
    inclusion        was FC cited in the finished answer?
    position         rank at which FC was first cited
    citation_share   FC citations / all citations

PAPER METRIC — Position-Adjusted Word Count, Aggarwal et al. (2024) eq. 3:

    Imp_pwc(c, r) = SUM_{s in S_c} |s| * exp(-pos(s)/|S|)  /  SUM_{s in S_r} |s|

    the words in sentences citing FC, discounted exponentially by how far into
    the answer they appear, over total answer words. A sentence citing several
    sources splits its word count equally between them.

    WHY ADD IT: a yes/no citation flag cannot be compared against published
    numbers. PAWC makes our results directly comparable to the benchmark.

COVARIATE — mean FC context position. C-SEO Bench found context rank dominates
    content edits, so it is logged rather than assumed away.

STRATUM / MONOPOLY — primary vs secondary queries are scored separately.
    monopoly_retrieval=1 when only one brand appears in the candidate set:
    that is a coverage win, not a content contest, and must not be pooled
    into Type-B contribution claims.
"""
import csv
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional

from ..config import CONFIG, Config


def _sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def position_adjusted_word_count(answer: str, brand_by_index: Dict[int, str],
                                 brand: str) -> float:
    sents = _sentences(answer)
    if not sents:
        return 0.0
    total_words = sum(len(s.split()) for s in sents) or 1
    n, score = len(sents), 0.0
    for pos, sent in enumerate(sents, 1):
        # Deduplicate citation indices before splitting mass.
        idxs = list(dict.fromkeys(
            i for i in (int(x) for x in re.findall(r"\[(\d+)\]", sent))
            if i in brand_by_index))
        if not idxs:
            continue
        share = len(sent.split()) / len(idxs)      # split across co-citations
        decay = math.exp(-pos / n)
        score += sum(share * decay for i in idxs if brand_by_index[i] == brand)
    return score / total_words


def _load_query_meta(cfg: Config) -> Dict[str, Dict[str, str]]:
    """id -> {stratum, group, intent} from queries.csv (+ heldout if present)."""
    meta: Dict[str, Dict[str, str]] = {}
    for path in (cfg.queries_file, cfg.heldout_file):
        if not Path(path).exists():
            continue
        for row in csv.DictReader(open(path, encoding="utf-8")):
            meta[row["id"]] = {
                "stratum": row.get("stratum", ""),
                "group": row.get("group", ""),
                "intent": row.get("intent", ""),
            }
    return meta


def score_arm(arm: str, variant: str, cfg: Config = CONFIG,
              answers_path: Optional[Path] = None) -> List[Dict]:
    fc = cfg.our_brand
    qmeta = _load_query_meta(cfg)
    rows: List[Dict] = []
    answers = Path(answers_path) if answers_path else cfg.resolve_answers_path(
        arm, variant)
    with answers.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            brand_by_index = {i: b for i, b in enumerate(rec["retrieved_brands"], 1)}
            cited = rec["cited_brands"]
            ctx = rec.get("fc_context_positions", [])
            brands = rec["retrieved_brands"]
            n_brands = len(set(brands))
            retrieved = int(fc in brands)
            inclusion = int(fc in cited)
            # Analysis-pool position of FC (1-based among retrieved_brands).
            fc_analysis_pos = (
                brands.index(fc) + 1 if fc in brands else None)
            qm = qmeta.get(rec["query_id"], {})
            brand_ranks = rec.get("brand_ranks") or {}
            rows.append({
                "query_id": rec["query_id"], "group": rec["group"],
                "stratum": qm.get("stratum") or rec.get("stratum", ""),
                "arm": arm, "variant": variant,
                "seed": rec.get("seed", 1), "run": rec["run"],
                "model": rec.get("model", ""),
                "run_id": rec.get("run_id", ""),
                "retrieval_rate": retrieved,
                "inclusion": inclusion,
                "position": (cited.index(fc) + 1) if fc in cited else "",
                "citation_share": round(cited.count(fc) / len(cited), 4) if cited else 0.0,
                "pawc": round(position_adjusted_word_count(
                    rec["answer"], brand_by_index, fc), 5),
                "fc_context_position": round(sum(ctx) / len(ctx), 2) if ctx else "",
                "n_brands_retrieved": n_brands,
                "monopoly_retrieval": int(n_brands == 1),
                # Conditional / capture metrics (live layer; blank if absent).
                "p_cited_given_retrieved": (
                    inclusion if retrieved else ""),
                "p_cited_given_top3": (
                    inclusion if (
                        fc_analysis_pos is not None and fc_analysis_pos <= 3)
                    else ""),
                "fc_search_rank": rec.get("fc_search_rank", ""),
                "fc_in_capture": int(bool(rec["fc_in_capture"]))
                if "fc_in_capture" in rec else (
                    int(bool(rec.get("fc_present"))) if "fc_present" in rec else ""),
                "fc_present": int(fc in brands),
                "n_distinct_domains": rec.get("n_distinct_domains", ""),
                "rank_flightcentre": brand_ranks.get("flightcentre", ""),
                "rank_skyscanner": brand_ranks.get("skyscanner", ""),
                "rank_webjet": brand_ranks.get("webjet", ""),
                "rank_expedia": brand_ranks.get("expedia", ""),
                # Uneven competition: known brands without usable page text.
                "brands_usable": ";".join(rec.get("brands_usable") or []),
                "brands_missing_usable": ";".join(
                    rec.get("brands_missing_usable") or []),
                "missing_flightcentre": int(
                    "flightcentre" in (rec.get("brands_missing_usable") or [])),
                "missing_skyscanner": int(
                    "skyscanner" in (rec.get("brands_missing_usable") or [])),
                "missing_webjet": int(
                    "webjet" in (rec.get("brands_missing_usable") or [])),
                "missing_expedia": int(
                    "expedia" in (rec.get("brands_missing_usable") or [])),
            })
    if not rows:
        raise FileNotFoundError(f"No answers to score at {answers}")

    path = cfg.resolve_scores_path(arm, variant, answers)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    # Mirror into runs/<run_id>/scores/ when present
    run_ids = {r.get("run_id") for r in rows if r.get("run_id")}
    for rid in run_ids:
        run_scores = Path(cfg.runs_dir) / rid / "scores" / f"scores_{arm}_{variant}.csv"
        run_scores.parent.mkdir(parents=True, exist_ok=True)
        with run_scores.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows([r for r in rows if r.get("run_id") == rid])
    return rows


def filter_rows(rows: List[Dict], stratum: Optional[str] = None,
                drop_monopoly: bool = False) -> List[Dict]:
    out = rows
    if stratum:
        out = [r for r in out if r.get("stratum") == stratum]
    if drop_monopoly:
        out = [r for r in out if not int(r.get("monopoly_retrieval") or 0)]
    return out


def summarise(rows: List[Dict]) -> Dict[str, str]:
    if not rows:
        return {"answers": "0"}
    n = len(rows)
    pos = [r["position"] for r in rows if r["position"] != ""]
    ctx = [r["fc_context_position"] for r in rows if r["fc_context_position"] != ""]
    mono = sum(int(r.get("monopoly_retrieval") or 0) for r in rows)
    given_ret = [int(r["p_cited_given_retrieved"])
                 for r in rows if r.get("p_cited_given_retrieved") != ""]
    given_top3 = [int(r["p_cited_given_top3"])
                  for r in rows if r.get("p_cited_given_top3") != ""]
    in_cap = [int(r["fc_in_capture"])
              for r in rows if r.get("fc_in_capture") != ""]
    ranks = [int(r["fc_search_rank"])
             for r in rows
             if r.get("fc_search_rank") not in ("", None)]
    out = {
        "answers": str(n),
        "FC retrieved": f"{sum(r['retrieval_rate'] for r in rows) / n:.0%}",
        "FC inclusion": f"{sum(r['inclusion'] for r in rows) / n:.0%}",
        "FC citation share": f"{sum(r['citation_share'] for r in rows) / n:.1%}",
        "FC PAWC": f"{sum(r['pawc'] for r in rows) / n:.4f}",
        "FC cite position": f"{sum(pos) / len(pos):.1f}" if pos else "never",
        "FC context position": f"{sum(ctx) / len(ctx):.1f}" if ctx else "-",
        "monopoly answers": f"{mono}/{n} ({mono / n:.0%})",
    }
    if given_ret:
        out["P(cited|retrieved)"] = f"{sum(given_ret) / len(given_ret):.0%} (n={len(given_ret)})"
    if given_top3:
        out["P(cited|top3)"] = f"{sum(given_top3) / len(given_top3):.0%} (n={len(given_top3)})"
    if in_cap:
        out["FC in capture (top20)"] = f"{sum(in_cap) / len(in_cap):.0%}"
    if ranks:
        out["FC search rank (median)"] = str(sorted(ranks)[len(ranks) // 2])
    return out


def monopoly_report(rows: List[Dict]) -> str:
    """Per-query monopoly flags (averaged over runs): coverage wins vs contests."""
    from collections import defaultdict
    by_q = defaultdict(list)
    for r in rows:
        by_q[r["query_id"]].append(r)
    lines = [
        f"{'query':<8}{'stratum':<12}{'monopoly%':>10}{'brands':>8}  note",
        "-" * 60,
    ]
    for qid in sorted(by_q):
        rs = by_q[qid]
        mono = sum(int(r.get("monopoly_retrieval") or 0) for r in rs) / len(rs)
        brands = sum(int(r.get("n_brands_retrieved") or 0) for r in rs) / len(rs)
        stratum = rs[0].get("stratum", "")
        note = ("COVERAGE MONOPOLY — not a content contest" if mono >= 0.5
                else "multi-brand contest")
        lines.append(f"{qid:<8}{stratum:<12}{mono:>9.0%}{brands:>8.1f}  {note}")
    return "\n".join(lines)
