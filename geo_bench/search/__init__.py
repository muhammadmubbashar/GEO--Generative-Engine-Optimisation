"""Live web-search retrieval layer (Aggarwal-style generation-stage pool).

Local fixed/reindexed variants are unchanged. This package builds a candidate
Passage list from live search so downstream generation/metrics stay identical.
"""
from .live_retriever import LivePool, LiveRetriever

__all__ = ["LiveRetriever", "LivePool"]
