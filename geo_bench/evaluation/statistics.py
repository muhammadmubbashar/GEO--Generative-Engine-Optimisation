"""Statistical comparison of arms against the baseline.

Three deliberate choices, each traceable:

1. PER-QUERY AGGREGATION. Five runs of one query are repeated measurements of
   the same thing, not five independent trials. We average to query level and
   test on n = number of queries. Pooling runs inflates significance.

2. TWO-TAILED TESTS. Puerto et al. (2025) found these methods "not only
   largely ineffective but frequently have a negative impact" — the Statistics
   method decreased rankings in 19 of 24 settings. A one-tailed test could not
   detect that.

3. BONFERRONI-HOLM. Applied across arms within ONE pre-registered family
   (primary_metric × primary_variant × primary_stratum in config.py). Other
   metric/variant/stratum tables are exploratory and must be labelled as such.
   Correcting only within one compare_arms() call without a registered family
   understates the multiple-comparisons problem (≈56 cells if all are mined).

Bootstrap confidence intervals are reported alongside p-values: with roughly
twenty primary queries, an interval is more useful to the client than a bare p.
"""
import collections
import csv
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..config import CONFIG, Config
from .metrics import filter_rows

try:
    from scipy.stats import wilcoxon
except ImportError:                                   # pragma: no cover
    wilcoxon = None


@dataclass
class ArmResult:
    arm: str
    n: int
    mean_diff: float
    relative_pct: float
    ci_low: float
    ci_high: float
    p_value: float
    p_holm: float = 1.0
    family: str = ""

    @property
    def significant(self) -> bool:
        return self.p_holm < 0.05


def _per_query(rows: List[Dict], metric: str) -> Dict[str, float]:
    agg = collections.defaultdict(list)
    for r in rows:
        if r[metric] != "":
            agg[r["query_id"]].append(float(r[metric]))
    return {q: sum(v) / len(v) for q, v in agg.items()}


def _bootstrap_ci(diffs: List[float], n: int = 5000, seed: int = 1):
    rng = random.Random(seed)
    means = sorted(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs)
                   for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def _holm(pvals: List[float]) -> List[float]:
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m, adjusted, running = len(pvals), [1.0] * len(pvals), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adjusted[i] = running
    return adjusted


def _load(arm: str, variant: str, cfg: Config) -> Optional[List[Dict]]:
    answers = cfg.resolve_answers_path(arm, variant)
    path = cfg.resolve_scores_path(arm, variant, answers)
    if not path.exists():
        path = cfg.scores_path(arm, variant)
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else None


def compare_arms(variant: str = "reindexed", metric: str = "pawc",
                 cfg: Config = CONFIG,
                 stratum: Optional[str] = None,
                 drop_monopoly: bool = False) -> List[ArmResult]:
    """Compare each arm to baseline.

    When variant/metric/stratum match the pre-registered primary family,
    results are tagged family='primary' (confirmatory). Otherwise
    family='exploratory'.
    """
    if stratum is None:
        stratum = cfg.primary_stratum
    is_primary = (variant == cfg.primary_variant
                  and metric == cfg.primary_metric
                  and stratum == cfg.primary_stratum)
    family = "primary" if is_primary else "exploratory"

    base_rows = _load("baseline", variant, cfg)
    if base_rows is None:
        raise FileNotFoundError("Score the baseline first.")
    base_rows = filter_rows(base_rows, stratum=stratum, drop_monopoly=drop_monopoly)
    base = _per_query(base_rows, metric)

    results: List[ArmResult] = []
    for arm in cfg.arms[1:]:
        rows = _load(arm, variant, cfg)
        if rows is None:
            continue
        rows = filter_rows(rows, stratum=stratum, drop_monopoly=drop_monopoly)
        arm_scores = _per_query(rows, metric)
        common = sorted(set(arm_scores) & set(base))
        if not common:
            continue
        diffs = [arm_scores[q] - base[q] for q in common]
        mean_diff = sum(diffs) / len(diffs)
        base_mean = sum(base[q] for q in common) / len(common)
        lo, hi = _bootstrap_ci(diffs)
        if wilcoxon is not None and any(d != 0 for d in diffs):
            p = float(wilcoxon([arm_scores[q] for q in common],
                               [base[q] for q in common],
                               alternative="two-sided").pvalue)
        else:
            p = 1.0
        results.append(ArmResult(
            arm=arm, n=len(common), mean_diff=mean_diff,
            relative_pct=(mean_diff / base_mean * 100) if base_mean else float("nan"),
            ci_low=lo, ci_high=hi, p_value=p, family=family))

    for r, adj in zip(results, _holm([r.p_value for r in results])):
        r.p_holm = adj
    return results


def render(results: List[ArmResult], metric: str, variant: str) -> str:
    family = results[0].family if results else "?"
    head = (f"\nMetric: {metric}   Variant: {variant}   "
            f"family={family}   n = queries (runs averaged)\n"
            f"{'arm':<22}{'n':>4}{'mean diff':>12}{'rel %':>9}"
            f"{'95% CI':>24}{'p':>8}{'p(Holm)':>10}  sig\n" + "-" * 93)
    if family == "exploratory":
        head += ("\nNOTE: exploratory table — not the pre-registered primary "
                 "family; do not treat sig as confirmatory.\n")
    lines = [head]
    for r in results:
        sig = "*" if r.significant else ""
        lines.append(
            f"{r.arm:<22}{r.n:>4}{r.mean_diff:>12.4f}{r.relative_pct:>8.1f}%"
            f"  [{r.ci_low:>7.4f}, {r.ci_high:>7.4f}]"
            f"{r.p_value:>8.4f}{r.p_holm:>10.4f}  {sig}")
    return "\n".join(lines)
