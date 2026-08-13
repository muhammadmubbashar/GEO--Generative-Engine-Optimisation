"""Split page text into overlapping passages with stable identifiers.

Overlap exists so a fact spanning a boundary still appears whole somewhere.

IDs embed a hash of the passage's own text, so identical text always yields the
same ID across rebuilds. That is what makes the reproducibility control test
meaningful — otherwise "same chunks" could not be checked.
"""
import hashlib
from pathlib import Path
from typing import List

from ..api.base import Passage
from ..config import CONFIG, Config


def split_text(text: str, cfg: Config = CONFIG) -> List[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= cfg.chunk_words:
        return [" ".join(words)]
    step = cfg.chunk_words - cfg.chunk_overlap
    return [" ".join(words[i:i + cfg.chunk_words])
            for i in range(0, len(words) - cfg.chunk_overlap, step)]


def make_passages(text: str, brand: str, path: Path,
                  cfg: Config = CONFIG) -> List[Passage]:
    out = []
    for i, chunk in enumerate(split_text(text, cfg)):
        digest = hashlib.sha1(chunk.encode()).hexdigest()[:8]
        out.append(Passage(
            id=f"{brand}:{Path(path).name[:24]}:{i}:{digest}",
            brand=brand, text=chunk, file=str(path), words=len(chunk.split())))
    return out
