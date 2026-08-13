"""Deterministic stand-in used when no API key is available.

Embeddings are bag-of-words vectors; answers are templated. Enough to exercise
every code path, verify the control tests and demo the system.

LIMITATION: the offline generator always cites the first three passages in
order, so the position_control arm cannot show an effect here. That is an
artefact of the stub, not a result. Position effects require mode="openai".
"""
import re
from typing import Dict, List, Sequence

from .base import LLMClient


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9$]+", text.lower())


class OfflineClient(LLMClient):
    def __init__(self) -> None:
        self._vocab: Dict[str, int] = {}

    @property
    def name(self) -> str:
        return "offline-deterministic"

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        for t in texts:                    # vocabulary grows monotonically so
            for w in set(tokenize(t)):     # query vectors align with documents
                self._vocab.setdefault(w, len(self._vocab))
        dim = len(self._vocab)
        out: List[List[float]] = []
        for t in texts:
            v = [0.0] * dim
            for w in tokenize(t):
                if w in self._vocab:
                    v[self._vocab[w]] += 1.0
            out.append(v)
        return out

    def generate(self, prompt: str, temperature: float, top_p: float) -> str:
        blocks = re.findall(r"\[(\d+)\]\s(.+?)(?=\n\n\[|\Z)", prompt, re.S)
        cited = blocks[:3]
        if not cited:
            return "No sources were supplied."
        return "Based on the retrieved sources: " + " ".join(
            f"{txt.strip()[:110]}... [{idx}]" for idx, txt in cited)
