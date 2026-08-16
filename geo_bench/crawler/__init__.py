"""Fetch QC for the frozen live pool.

The old four-brand sitemap corpus has been retired. Pages now come from the
Brave freeze under runs/<RUN_ID>/.
"""
from .quality import (
    FETCH_METHODS,
    FreezeQCReport,
    canonical_fetch_method,
    is_usable,
    needs_review,
    qc_fields,
    run_freeze_qc,
)

__all__ = [
    "FETCH_METHODS",
    "FreezeQCReport",
    "canonical_fetch_method",
    "is_usable",
    "needs_review",
    "qc_fields",
    "run_freeze_qc",
]
