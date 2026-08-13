"""Build and load the shared index for one experimental arm."""
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
from rank_bm25 import BM25Okapi

from ..api import get_client
from ..api.base import Passage
from ..api.offline_client import tokenize
from ..config import CONFIG, Config
from .chunker import make_passages
from .parser import clean_brand_pages


@dataclass
class Index:
    passages: List[Passage]
    vectors: np.ndarray
    bm25: BM25Okapi
    arm: str

    def volume_table(self, cfg: Config = CONFIG) -> str:
        lines = [f"{'brand':<16}{'pages':>7}{'chunks':>8}{'words':>10}", "-" * 42]
        for b in cfg.brands:
            rows = [p for p in self.passages if p.brand == b]
            pages = len({p.file for p in rows})
            lines.append(f"{b:<16}{pages:>7}{len(rows):>8}"
                         f"{sum(p.words for p in rows):>10,}")
        lines.append(f"\nTotal passages: {len(self.passages)} "
                     f"(all brands in ONE shared pool)")
        return "\n".join(lines)


def build_index(arm: str = "baseline", cfg: Config = CONFIG) -> Index:
    root = cfg.corpus_dir / arm
    if not root.is_dir():
        raise FileNotFoundError(f"No corpus at {root}")

    passages: List[Passage] = []
    for brand in cfg.brands:
        paths = sorted((root / brand).glob("*.html"))
        if not paths:
            continue
        # Two-pass cleaning is brand-aware: cross-page boilerplate can only be
        # detected by comparing pages from the SAME brand.
        for path, text in clean_brand_pages(paths).items():
            passages.extend(make_passages(text, brand, path, cfg))
    if not passages:
        raise ValueError(f"No pages found under {root}")

    client = get_client(cfg)
    vecs = np.asarray(client.embed([p.text for p in passages]), dtype=np.float32)
    vecs /= (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    bm25 = BM25Okapi([tokenize(p.text) for p in passages])

    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(cfg.vectors_path(arm), vecs=vecs)
    with cfg.index_path(arm).open("wb") as f:
        pickle.dump({"passages": passages, "bm25": bm25}, f)
    return Index(passages, vecs, bm25, arm)


def load_index(arm: str, cfg: Config = CONFIG) -> Index:
    vecs = np.load(cfg.vectors_path(arm))["vecs"]
    with cfg.index_path(arm).open("rb") as f:
        blob = pickle.load(f)
    return Index(blob["passages"], vecs, blob["bm25"], arm)
