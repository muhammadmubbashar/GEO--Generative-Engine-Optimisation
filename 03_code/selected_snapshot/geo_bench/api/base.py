"""Provider-agnostic interfaces."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class Passage:
    """One source in the generation prompt.

    `fixed`: cleaned full page. `reindexed`: one 350-word chunk.
    """
    id: str
    brand: str
    text: str
    file: str = ""
    words: int = 0


class LLMClient(ABC):
    """Contract every provider must satisfy."""

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Return one vector per text."""

    @abstractmethod
    def generate(self, prompt: str, temperature: float, top_p: float) -> str:
        """Return the model's answer to a fully-formed prompt."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Exact model identifier, recorded in results for reproducibility."""
