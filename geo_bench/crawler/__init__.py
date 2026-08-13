"""Acquire and freeze the corpus.

The corpus defines the population every later number is drawn from, and it is
the only irreversible stage in the project. Four responsibilities:

    discovery  find every candidate page a brand has, per page type
    coverage   record sought-vs-found, so an absence is evidenced not assumed
    fetcher    download exactly as an AI crawler sees it, then freeze
    quality    distinguish a genuinely empty page from a failed fetch
"""
from .fetcher import Fetcher
from .coverage import CoverageGrid
from .quality import QualityReport

__all__ = ["Fetcher", "CoverageGrid", "QualityReport"]
