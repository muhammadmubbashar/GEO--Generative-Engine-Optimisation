"""HTML to the text an AI crawler would actually read.

Thin wrapper over `cleaner`, kept so callers have one obvious entry point.
Cleaning is deliberately a separate module: it carries the most consequential
judgement calls in the pipeline and deserves to be read and reviewed on its own.
"""
from pathlib import Path
from typing import Dict, List

from .cleaner import clean_brand_pages, clean_html, cleaning_report

__all__ = ["page_text", "clean_brand_pages", "cleaning_report"]


def page_text(path: Path) -> str:
    """Single-page cleaning (structural pass only).

    Prefer `clean_brand_pages` where possible: cross-page boilerplate detection
    needs several pages from the same brand to work, and it is the pass that
    catches chrome using no semantic tags.
    """
    body, jsonld = clean_html(Path(path).read_text(encoding="utf-8", errors="ignore"))
    return (body + " " + jsonld).strip()
