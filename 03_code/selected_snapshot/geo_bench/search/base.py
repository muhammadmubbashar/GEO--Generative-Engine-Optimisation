"""Provider-agnostic search interfaces (mirrors geo_bench/api/)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    rank: int           # rank within its own search (1-based)
    source_query: str   # which fan-out phrasing produced it


class SearchClient(ABC):
    """Contract every search provider must satisfy."""

    @abstractmethod
    def search(self, query: str, count: int, region: str,
               language: str) -> List[SearchResult]:
        """Return ranked results. Must raise on failure — never return []."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider id recorded in cache keys and logs."""
