"""Brave freeze → frozen live pool → fixed / reindexed retrieval.

The old four-brand sitemap corpus is retired. Generation-stage candidates
come from the freeze under runs/<RUN_ID>/ only.
"""
from .live_retriever import LivePool, LiveRetriever, page_source

__all__ = ["LiveRetriever", "LivePool", "page_source"]
