"""Arm interface and page records.

FrozenPage wraps one freeze document. OptimisedPage is the arm output,
always written beside the freeze, never over it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .facts import FactTable


@dataclass
class FrozenPage:
    url: str
    html: str
    clean: str
    sha256: str
    clean_sha256: str
    words: int
    brand: str
    page_type: str = "generic"
    title: str = ""
    queries_served: tuple = ()
    fc_best_rank: Optional[int] = None
    eligible_layers: tuple = ()
    usable: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AddedClaim:
    """One span introduced by an arm, mapped to a fact_id when grounded."""
    span: str
    fact_id: str = ""
    source_url: str = ""
    kind: str = ""


@dataclass
class OptimisedPage:
    url: str
    arm: str
    html: str
    clean: str
    content_hash: str
    baseline_sha256: str
    baseline_words: int
    optimised_words: int
    page_type: str = "generic"
    claims: List[AddedClaim] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)

    @property
    def words_delta(self) -> int:
        return int(self.optimised_words) - int(self.baseline_words)

    @property
    def pct_change(self) -> float:
        if not self.baseline_words:
            return 0.0
        return 100.0 * self.words_delta / self.baseline_words


class Arm(ABC):
    """One named intervention. `optimise` must not touch competitor pages."""

    name: str
    needs_verified_facts: bool = False
    uses_llm: bool = False
    preserves_length: bool = False

    @abstractmethod
    def optimise(self, page: FrozenPage, facts: "FactTable") -> OptimisedPage:
        raise NotImplementedError
