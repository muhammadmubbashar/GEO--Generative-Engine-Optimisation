"""Hybrid retrieval with a per-brand cap.

WHY HYBRID: dense vectors match meaning but are weak on exact strings —
"Jetstar", "MEL", "22h 5m", "$1,189". Those strings are precisely what the
entity-enrichment intervention adds. A dense-only retriever would fail to
detect the method we most want to measure, producing a false negative.

Rankings are combined with Reciprocal Rank Fusion, which needs no score
calibration between the two systems and is the standard choice for this.

WHY THE CAP: without it a brand with fifteen pages beats a brand with three by
volume alone, and we would be measuring page count rather than content.
"""
from typing import List

import numpy as np

from ..api import get_client
from ..api.base import Passage
from ..api.offline_client import tokenize
from ..config import CONFIG, Config
from .index import Index


class Retriever:
    def __init__(self, index: Index, cfg: Config = CONFIG):
        self.index = index
        self.cfg = cfg
        self._client = get_client(cfg)

    def _dense_order(self, query: str) -> np.ndarray:
        qv = np.asarray(self._client.embed([query])[0], dtype=np.float32)
        dim = self.index.vectors.shape[1]
        if qv.shape[0] < dim:                    # offline vocab may have grown
            qv = np.pad(qv, (0, dim - qv.shape[0]))
        qv = qv[:dim] / (np.linalg.norm(qv[:dim]) + 1e-9)
        return np.argsort(-(self.index.vectors @ qv))[:50]

    def retrieve(self, query: str) -> List[Passage]:
        dense = self._dense_order(query)
        if self.cfg.use_hybrid:
            lex = np.argsort(-self.index.bm25.get_scores(tokenize(query)))[:50]
            fused = {}
            for order in (dense, lex):
                for pos, idx in enumerate(order):
                    fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (self.cfg.rrf_k + pos)
            ranked = [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])]
        else:
            ranked = [int(i) for i in dense]

        picked: List[Passage] = []
        per_brand: dict = {}
        for idx in ranked:
            p = self.index.passages[idx]
            if self.cfg.cap_per_brand and per_brand.get(p.brand, 0) >= self.cfg.cap_per_brand:
                continue
            picked.append(p)
            per_brand[p.brand] = per_brand.get(p.brand, 0) + 1
            if len(picked) == self.cfg.top_k:
                break
        return picked
