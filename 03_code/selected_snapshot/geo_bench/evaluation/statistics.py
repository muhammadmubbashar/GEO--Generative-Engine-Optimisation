"""Statistical comparison of arms against the baseline.

Per-query aggregation · two-tailed Wilcoxon · bootstrap 95% CIs ·
Bonferroni-Holm across arms within each endpoint family.

Primary family:   PAWC, citation share
Secondary family: relevance, response quality, inclusion, retrieval rank

A null result is inconclusive, not evidence of absence. Detectable effect
size (approx. Cohen's d, 80% power, α=0.05 two-sided) is reported per layer.
"""
import collections
import csv
import math
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
    metric: str
    n: int
    mean_diff: float
    relative_pct: float
    ci_low: float
    ci_high: float
    p_value: float
    p_holm: float = 1.0
    family: str = ""
    mde_d: float = float("nan")
    # Matched-pairs rank-biserial correlation (observed effect size,
    # -1..1); complements the a-priori MDE.
    rank_biserial: float = float("nan")

    @property
    def significant(self) -> bool:
        return self.p_holm < 0.05


def _per_query(rows: List[Dict], metric: str) -> Dict[str, float]:
    agg = collections.defaultdict(list)
    for r in rows:
        val = r.get(metric, "")
        if val != "" and val is not None:
            try:
                agg[r["query_id"]].append(float(val))
            except (TypeError, ValueError):
                continue
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


def detectable_d(n: int) -> float:
    """Approx. min. detectable paired Cohen's d (80% power, α=0.05 two-sided)."""
    if n <= 0:
        return float("nan")
    return 2.80 / math.sqrt(n)


def rank_biserial(diffs: List[float]) -> float:
    """Matched-pairs rank-biserial r = (W+ − W−) / (W+ + W−).

    Ranks |diff| over non-zero pairs (average ranks on ties), signs them,
    and normalises. +1 = every pair favours the arm; −1 = every pair
    favours baseline.
    """
    nz = [d for d in diffs if d != 0]
    if not nz:
        return float("nan")
    order = sorted(range(len(nz)), key=lambda i: abs(nz[i]))
    ranks = [0.0] * len(nz)
    i = 0
    while i < len(order):
        j = i
        while (j + 1 < len(order)
               and abs(nz[order[j + 1]]) == abs(nz[order[i]])):
            j += 1
        avg = (i + j) / 2 + 1          # average 1-based rank across the tie
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_pos = sum(r for r, d in zip(ranks, nz) if d > 0)
    w_neg = sum(r for r, d in zip(ranks, nz) if d < 0)
    total = w_pos + w_neg
    return (w_pos - w_neg) / total if total else float("nan")


def compare_arms(variant: str = "reindexed", metric: str = "pawc",
                 cfg: Config = CONFIG,
                 stratum: Optional[str] = None,
                 drop_monopoly: bool = False) -> List[ArmResult]:
    """Single-metric comparison (legacy). Prefer compare_family for reporting."""
    family = _family_for(metric, variant, stratum, cfg)
    return _compare(variant, [metric], family, cfg, stratum, drop_monopoly)


def _family_for(metric: str, variant: str, stratum: Optional[str],
                cfg: Config) -> str:
    stratum = stratum or cfg.primary_stratum
    if (variant == cfg.primary_variant and stratum == cfg.primary_stratum
            and metric in cfg.primary_endpoints):
        return "primary"
    if metric in cfg.secondary_endpoints:
        return "secondary"
    return "exploratory"


def _compare(variant: str, metrics: List[str], family: str,
             cfg: Config, stratum: Optional[str],
             drop_monopoly: bool) -> List[ArmResult]:
    if stratum is None:
        stratum = cfg.primary_stratum
    base_rows = _load("baseline", variant, cfg)
    if base_rows is None:
        raise FileNotFoundError("Score the baseline first.")
    base_rows = filter_rows(base_rows, stratum=stratum, drop_monopoly=drop_monopoly)

    results: List[ArmResult] = []
    for metric in metrics:
        base = _per_query(base_rows, metric)
        # NOTE: iterates cfg.optimisation_arms (the arms actually built and
        # run this sprint), not cfg.arms[1:] (the locked baseline-protocol
        # tuple, which still carries never-built placeholders schema_only /
        # faq_structure_only and has no entry for schema_markup /
        # faq_structure / padding_control at all — that mismatch silently
        # dropped 3 of 7 arms from every `geo stats` report).
        for arm in cfg.optimisation_arms:
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
            if any(d != 0 for d in diffs):
                if wilcoxon is None:
                    raise RuntimeError(
                        "scipy is required for the pre-registered Wilcoxon "
                        "test (pip install scipy). Refusing to silently "
                        "report p=1.0.")
                p = float(wilcoxon([arm_scores[q] for q in common],
                                   [base[q] for q in common],
                                   alternative="two-sided").pvalue)
            else:
                p = 1.0
            results.append(ArmResult(
                arm=arm, metric=metric, n=len(common), mean_diff=mean_diff,
                relative_pct=(mean_diff / base_mean * 100) if base_mean else float("nan"),
                ci_low=lo, ci_high=hi, p_value=p, family=family,
                mde_d=detectable_d(len(common)),
                rank_biserial=rank_biserial(diffs)))

    for r, adj in zip(results, _holm([r.p_value for r in results])):
        r.p_holm = adj
    return results


def compare_family(variant: str, family: str,
                   cfg: Config = CONFIG,
                   stratum: Optional[str] = None,
                   drop_monopoly: bool = False) -> List[ArmResult]:
    if family == "primary":
        metrics = list(cfg.primary_endpoints)
        stratum = stratum or cfg.primary_stratum
        variant = variant or cfg.primary_variant
    elif family == "secondary":
        metrics = list(cfg.secondary_endpoints)
        stratum = stratum or cfg.primary_stratum
    else:
        raise ValueError(f"unknown family={family!r}")
    return _compare(variant, metrics, family, cfg, stratum, drop_monopoly)


def render(results: List[ArmResult], metric: str = "",
           variant: str = "") -> str:
    if not results:
        return "No arm comparisons (score baseline + at least one other arm)."
    family = results[0].family
    n_vals = sorted({r.n for r in results})
    mde = detectable_d(n_vals[0]) if n_vals else float("nan")
    head = (
        f"\nFamily: {family}   variant={variant or '?'}   "
        f"n = queries (runs averaged)\n"
        f"Approx. min. detectable paired d (80% power, α=0.05): {mde:.2f} "
        f"(n≈{n_vals[0] if n_vals else 0}). "
        "A non-significant result is inconclusive, not evidence of absence.\n"
    )
    if family == "exploratory":
        head += ("NOTE: exploratory - not a pre-registered family; "
                 "do not treat sig as confirmatory.\n")
    head += (
        f"{'arm':<22}{'metric':<18}{'n':>4}{'mean diff':>12}{'rel %':>9}"
        f"{'95% CI':>24}{'p':>8}{'p(Holm)':>10}{'r_rb':>7}  sig\n" + "-" * 118
    )
    lines = [head]
    for r in results:
        sig = "*" if r.significant else ""
        rel = f"{r.relative_pct:8.1f}%" if math.isfinite(r.relative_pct) else f"{'n/a':>9}"
        rb = f"{r.rank_biserial:7.2f}" if math.isfinite(r.rank_biserial) else f"{'-':>7}"
        lines.append(
            f"{r.arm:<22}{r.metric:<18}{r.n:>4}{r.mean_diff:>12.4f}{rel}"
            f"  [{r.ci_low:>7.4f}, {r.ci_high:>7.4f}]"
            f"{r.p_value:>8.4f}{r.p_holm:>10.4f}{rb}  {sig}")
    return "\n".join(lines)


def render_families(variant: str, cfg: Config = CONFIG,
                    stratum: Optional[str] = None,
                    drop_monopoly: bool = False) -> str:
    blocks = []
    for family in ("primary", "secondary"):
        try:
            results = compare_family(variant, family, cfg, stratum, drop_monopoly)
        except FileNotFoundError as e:
            blocks.append(f"\nFamily {family}: {e}")
            continue
        if not results:
            blocks.append(
                f"\nFamily {family}: no other arms scored yet "
                f"(endpoints={list(cfg.primary_endpoints if family == 'primary' else cfg.secondary_endpoints)})."
            )
            continue
        blocks.append(render(results, variant=variant))
    return "\n".join(blocks)
