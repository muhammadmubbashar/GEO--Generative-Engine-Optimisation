"""Metrics and statistics.

    metrics     four counted metrics + Position-Adjusted Word Count
    statistics  per-query pairing, two-tailed tests, Bonferroni-Holm, CIs
"""
from .metrics import (score_arm, summarise, position_adjusted_word_count,
                      filter_rows, monopoly_report)
from .statistics import compare_arms

__all__ = ["score_arm", "summarise", "position_adjusted_word_count",
           "compare_arms", "filter_rows", "monopoly_report"]
