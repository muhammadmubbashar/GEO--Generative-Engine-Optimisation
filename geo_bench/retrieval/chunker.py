"""Split page text into overlapping passages with stable identifiers.

Overlap exists so a fact spanning a boundary still appears whole somewhere.

IDs embed a hash of the passage's own text, so identical text always yields the
same ID across rebuilds. That is what makes the reproducibility control test
meaningful — otherwise "same chunks" could not be checked.
"""
import hashlib
from pathlib import Path
from typing import List, Union

from ..api.base import Passage
from ..config import CONFIG, Config


def _explode_long_tokens(words: List[str], max_token_chars: int = 80) -> List[str]:
    """Split space-free blobs (minified JS/JSON) so word windows stay real."""
    out: List[str] = []
    for w in words:
        if len(w) <= max_token_chars:
            out.append(w)
            continue
        out.extend(w[i:i + max_token_chars]
                   for i in range(0, len(w), max_token_chars))
    return out


def split_text(text: str, cfg: Config = CONFIG) -> List[str]:
    words = _explode_long_tokens((text or "").split())
    if not words:
        return []
    if len(words) <= cfg.chunk_words:
        chunks = [" ".join(words)]
    else:
        step = cfg.chunk_words - cfg.chunk_overlap
        chunks = [" ".join(words[i:i + cfg.chunk_words])
                  for i in range(0, len(words) - cfg.chunk_overlap, step)]
    max_chars = int(cfg.chunk_max_chars)
    if max_chars <= 0:
        return chunks
    out: List[str] = []
    overlap_c = min(400, max(0, max_chars // 20))
    step_c = max(1, max_chars - overlap_c)
    for chunk in chunks:
        if len(chunk) <= max_chars:
            out.append(chunk)
            continue
        for i in range(0, len(chunk), step_c):
            piece = chunk[i:i + max_chars].strip()
            if piece:
                out.append(piece)
            if i + max_chars >= len(chunk):
                break
    return out


def _id_stem(path: Union[Path, str]) -> str:
    loc = str(path)
    if loc.startswith("http://") or loc.startswith("https://"):
        return hashlib.sha1(loc.encode("utf-8")).hexdigest()[:12]
    return Path(loc).name[:24]


def make_passages(text: str, brand: str, path: Union[Path, str],
                  cfg: Config = CONFIG) -> List[Passage]:
    out = []
    loc = str(path)
    stem = _id_stem(loc)
    for i, chunk in enumerate(split_text(text, cfg)):
        digest = hashlib.sha1(chunk.encode()).hexdigest()[:8]
        out.append(Passage(
            id=f"{brand}:{stem}:{i}:{digest}",
            brand=brand, text=chunk, file=loc, words=len(chunk.split())))
    return out
