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

    def _stable_order(self, scores: np.ndarray) -> List[int]:
        """Descending by score; ties broken by passage id (deterministic)."""
        idx = list(range(len(scores)))
        idx.sort(key=lambda i: (-float(scores[i]), self.index.passages[i].id))
        return idx[:50]

    def _dense_order(self, query: str) -> List[int]:
        qv = np.asarray(self._client.embed([query])[0], dtype=np.float32)
        dim = self.index.vectors.shape[1]
        if qv.shape[0] < dim:                    # offline vocab may have grown
            qv = np.pad(qv, (0, dim - qv.shape[0]))
        qv = qv[:dim] / (np.linalg.norm(qv[:dim]) + 1e-9)
        return self._stable_order(self.index.vectors @ qv)

    def _cap_key(self, p: Passage) -> str:
        """Budget key for the per-source cap. Default scope 'brand' pools all
        unlisted domains under `other`; 'domain' (sensitivity only) budgets
        each registrable domain separately."""
        if getattr(self.cfg, "cap_scope", "brand") == "domain":
            from urllib.parse import urlparse
            host = urlparse(str(p.file)).netloc.lower()
            return host.removeprefix("www.") or p.brand
        return p.brand

    def retrieve(self, query: str) -> List[Passage]:
        dense = self._dense_order(query)
        if self.cfg.use_hybrid:
            lex = self._stable_order(
                np.asarray(self.index.bm25.get_scores(tokenize(query))))
            fused: dict = {}
            for order in (dense, lex):
                # Standard RRF: 1/(k + rank) with rank starting at 1
                # (Cormack et al. 2009).
                for rank, idx in enumerate(order, 1):
                    fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (self.cfg.rrf_k + rank)
            ranked = [i for i, _ in sorted(
                fused.items(),
                key=lambda kv: (-kv[1], self.index.passages[kv[0]].id))]
        else:
            ranked = [int(i) for i in dense]

        picked: List[Passage] = []
        per_key: dict = {}
        for idx in ranked:
            p = self.index.passages[idx]
            key = self._cap_key(p)
            if self.cfg.cap_per_brand and per_key.get(key, 0) >= self.cfg.cap_per_brand:
                continue
            picked.append(p)
            per_key[key] = per_key.get(key, 0) + 1
            if len(picked) == self.cfg.top_k:
                break
        return picked
