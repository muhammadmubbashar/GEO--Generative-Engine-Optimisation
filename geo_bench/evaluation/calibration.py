"""Human calibration export and Cohen's kappa vs machine scores.

Sample: 60 answers, stratified across queries (and arms when present),
including high and low machine scores, chosen before graders see them.
"""
from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..config import CONFIG, Config

DIMENSIONS = (
    "relevance", "accuracy", "completeness", "clarity", "attribution",
)


def _kappa_band(kappa: float, threshold: float) -> str:
    if kappa >= threshold:
        return "substantial - proceed; report kappa"
    if kappa >= 0.4:
        return ("moderate - identify disagreements, clarify wording, "
                "re-version, re-score")
    return "poor - the rubric is the problem; rewrite before reporting"


def export_calibration_sample(scores_rows: List[Dict],
                              cfg: Config = CONFIG,
                              path: Optional[Path] = None,
                              seed: int = 1) -> Path:
    """Stratified sample → CSV for two independent human graders."""
    n = min(cfg.calibration_sample_size, len(scores_rows))
    by_q: Dict[str, List[Dict]] = defaultdict(list)
    for r in scores_rows:
        by_q[str(r.get("query_id") or "")].append(r)
    rng = random.Random(seed)
    # Prefer a mix of high/low response_quality when present.
    ranked = []
    for r in scores_rows:
        try:
            rq = float(r.get("response_quality") or "")
        except (TypeError, ValueError):
            rq = None
        ranked.append((rq, r))
    with_rq = [r for rq, r in ranked if rq is not None]
    without = [r for rq, r in ranked if rq is None]
    with_rq.sort(key=lambda r: float(r.get("response_quality") or 0))
    sample: List[Dict] = []
    if with_rq:
        lo = with_rq[: max(1, n // 4)]
        hi = with_rq[-max(1, n // 4):]
        mid = with_rq[len(with_rq) // 3: 2 * len(with_rq) // 3] or with_rq
        pool = lo + hi + mid
        rng.shuffle(pool)
        sample.extend(pool)
    # One row per query when possible.
    for qid, rows in by_q.items():
        if len(sample) >= n:
            break
        if any(r in sample for r in rows):
            continue
        sample.append(rng.choice(rows))
    leftover = [r for r in scores_rows if r not in sample]
    rng.shuffle(leftover)
    sample.extend(leftover)
    sample = sample[:n]

    if path is None:
        arm = (scores_rows[0].get("arm") if scores_rows else "") or "baseline"
        variant = (scores_rows[0].get("variant") if scores_rows else "") or "reindexed"
        dest = cfg.results_dir / f"calibration_sample_{arm}_{variant}.csv"
    else:
        dest = path
    dest.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "query_id", "arm", "variant", "seed", "run", "stratum",
        "machine_relevance", "machine_accuracy", "machine_completeness",
        "machine_clarity", "machine_attribution", "machine_response_quality",
        "human1_relevance", "human1_accuracy", "human1_completeness",
        "human1_clarity", "human1_attribution",
        "human2_relevance", "human2_accuracy", "human2_completeness",
        "human2_clarity", "human2_attribution",
    ]
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sample:
            w.writerow({
                "query_id": r.get("query_id", ""),
                "arm": r.get("arm", ""),
                "variant": r.get("variant", ""),
                "seed": r.get("seed", ""),
                "run": r.get("run", ""),
                "stratum": r.get("stratum", ""),
                "machine_relevance": r.get("relevance", ""),
                "machine_accuracy": r.get("accuracy", ""),
                "machine_completeness": r.get("completeness", ""),
                "machine_clarity": r.get("clarity", ""),
                "machine_attribution": r.get("attribution", ""),
                "machine_response_quality": r.get("response_quality", ""),
                "human1_relevance": "", "human1_accuracy": "",
                "human1_completeness": "", "human1_clarity": "",
                "human1_attribution": "",
                "human2_relevance": "", "human2_accuracy": "",
                "human2_completeness": "", "human2_clarity": "",
                "human2_attribution": "",
            })
    return dest


def _cohen_kappa(a: Sequence[int], b: Sequence[int]) -> float:
    """Unweighted Cohen's kappa for ordinal integer labels."""
    n = len(a)
    if n == 0 or len(b) != n:
        return float("nan")
    labels = sorted(set(a) | set(b))
    idx = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    mat = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        mat[idx[x]][idx[y]] += 1
    po = sum(mat[i][i] for i in range(k)) / n
    row = [sum(mat[i]) / n for i in range(k)]
    col = [sum(mat[i][j] for i in range(k)) / n for j in range(k)]
    pe = sum(r * c for r, c in zip(row, col))
    if abs(1 - pe) < 1e-12:
        return 1.0 if abs(1 - po) < 1e-12 else 0.0
    return (po - pe) / (1 - pe)


def kappa_report(calibration_csv: Path, cfg: Config = CONFIG) -> str:
    rows = list(csv.DictReader(calibration_csv.open(encoding="utf-8")))
    lines = [
        f"CALIBRATION  n={len(rows)}  file={calibration_csv}",
        f"kappa threshold = {cfg.kappa_threshold}  rubric v{cfg.rubric_version}",
        "",
        f"{'dimension':<16}{'κ H1↔H2':>10}{'κ H1↔M':>10}{'κ H2↔M':>10}  action",
        "-" * 72,
    ]
    any_human = False
    for dim in DIMENSIONS:
        h1, h2, m = [], [], []
        for r in rows:
            a, b, c = r.get(f"human1_{dim}", ""), r.get(f"human2_{dim}", ""), r.get(f"machine_{dim}", "")
            if a == "" or b == "" or c == "":
                continue
            try:
                h1.append(int(float(a))); h2.append(int(float(b))); m.append(int(float(c)))
            except ValueError:
                continue
        if not h1:
            lines.append(f"{dim:<16}{'-':>10}{'-':>10}{'-':>10}  fill human columns first")
            continue
        any_human = True
        k12 = _cohen_kappa(h1, h2)
        k1m = _cohen_kappa(h1, m)
        k2m = _cohen_kappa(h2, m)
        band = _kappa_band(k12, cfg.kappa_threshold)
        lines.append(
            f"{dim:<16}{k12:>10.3f}{k1m:>10.3f}{k2m:>10.3f}  {band}")
    if not any_human:
        lines.append(
            "\nNo human scores yet. Two graders score independently using "
            "SCORING_RUBRICS.md only, then re-run geo kappa."
        )
    return "\n".join(lines)
