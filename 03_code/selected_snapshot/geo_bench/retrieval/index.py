"""Build and load the shared index for one experimental arm.

Corpus = every unique page in the frozen live pool (runs/<RUN_ID>/pages),
all queries together. Brand tagging by domain; anything unrecognised is
`other`. Hybrid retrieval code is unchanged.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

import numpy as np
from rank_bm25 import BM25Okapi

from ..api import get_client
from ..api.base import Passage
from ..api.offline_client import tokenize
from ..config import CONFIG, Config
from .chunker import make_passages

if TYPE_CHECKING:
    from ..experiment.run_store import RunStore


@dataclass
class Index:
    passages: List[Passage]
    vectors: np.ndarray
    bm25: BM25Okapi
    arm: str

    def volume_table(self, cfg: Config = CONFIG) -> str:
        brands = list(cfg.brands) + ["other"]
        extra = sorted({p.brand for p in self.passages} - set(brands))
        order = brands + extra
        lines = [f"{'brand':<16}{'pages':>7}{'chunks':>8}{'words':>10}", "-" * 42]
        for b in order:
            rows = [p for p in self.passages if p.brand == b]
            if not rows and b == "other":
                continue
            pages = len({p.file for p in rows})
            lines.append(f"{b:<16}{pages:>7}{len(rows):>8}"
                         f"{sum(p.words for p in rows):>10,}")
        lines.append(f"\nTotal passages: {len(self.passages)} "
                     f"(all freeze pages in ONE shared pool)")
        return "\n".join(lines)


def _passages_from_store(store: "RunStore", cfg: Config,
                         fc_suffix: str = "",
                         arm: str = "baseline") -> List[Passage]:
    """Chunk every unique frozen URL. Do not drop thin pages.

    For optimisation arms, Flight Centre pages are overlaid from
    runs/<RUN_ID>/arms/<arm>/pages when present. Competitors stay freeze bytes.
    """
    from ..search.live_retriever import brand_for_url, normalise_url
    arm_fc: Dict[str, str] = {}
    if arm != "baseline":
        from ..optimisation.builder import load_arm_clean_map
        arm_fc = load_arm_clean_map(store, arm)
        n_urls = len({u for u in arm_fc if u.startswith("http")})
        print(f"  arm={arm}: overlaying {n_urls} FC optimised page texts "
              f"into the index")

    seen: set = set()
    passages: List[Passage] = []
    n_swapped = 0
    for meta in store.iter_page_metas():
        url = (meta.get("url") or "").strip()
        if not url:
            continue
        key = normalise_url(url)
        if key in seen:
            continue
        seen.add(key)
        page = store.read_page(url)
        if page is None:
            continue
        text = (page.get("clean") or "").strip()
        if not text and page.get("html"):
            from .cleaner import clean_html
            body, jsonld = clean_html(page["html"])
            text = (body + " " + jsonld).strip()
        if not text:
            continue
        brand = meta.get("brand") or brand_for_url(url, cfg)
        if brand == cfg.our_brand and arm_fc:
            overlay = arm_fc.get(url) or arm_fc.get(key)
            if overlay:
                text = overlay
                n_swapped += 1
        if fc_suffix and brand == cfg.our_brand:
            text = (text + " " + fc_suffix).strip()
        passages.extend(make_passages(text, brand, url, cfg))
    if not passages:
        raise ValueError(f"No freeze pages to index at {store.root}")
    if arm != "baseline" and n_swapped == 0:
        raise RuntimeError(
            f"arm={arm!r}: no FC freeze URLs matched optimised pages"
        )
    if arm != "baseline":
        print(f"  arm={arm}: swapped {n_swapped} FC freeze URLs")
    return passages


def index_params(cfg: Config, arm_content_sha256: str = "") -> dict:
    """Everything that changes what the index contains or how it ranks.
    Stored in the pickle; a mismatch at load time forces a rebuild."""
    return {
        "chunk_words": cfg.chunk_words,
        "chunk_overlap": cfg.chunk_overlap,
        "chunk_max_chars": cfg.chunk_max_chars,
        "embed_model": cfg.embed_model,
        "bm25_k1": cfg.bm25_k1,
        "bm25_b": cfg.bm25_b,
        "arm_content_sha256": arm_content_sha256,
    }


def build_index(arm: str = "baseline", cfg: Config = CONFIG,
                store: Optional["RunStore"] = None,
                run_id: Optional[str] = None) -> Index:
    from ..experiment.run_store import RunStore
    if store is None:
        store = RunStore.resolve(run_id, cfg)
    store.verify_frozen_pages()
    if arm != "baseline" and arm not in cfg.optimisation_arms:
        raise RuntimeError(
            f"unknown arm={arm!r}; baseline or one of {cfg.optimisation_arms}"
        )
    arm_sha = ""
    if arm != "baseline":
        from ..optimisation.builder import arm_content_sha256
        arm_sha = arm_content_sha256(store, arm)

    # position_control is a byte-identical FC copy: reuse baseline index.
    if arm == "position_control":
        base_idx = cfg.index_path("baseline")
        base_vec = cfg.vectors_path("baseline")
        if base_idx.exists() and base_vec.exists():
            import shutil
            cfg.results_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base_idx, cfg.index_path(arm))
            shutil.copy2(base_vec, cfg.vectors_path(arm))
            # Rewrite arm name inside pickle.
            with cfg.index_path(arm).open("rb") as f:
                blob = pickle.load(f)
            blob_run = blob.get("run_id")
            if blob_run != store.run_id:
                raise RuntimeError(
                    f"baseline index run_id={blob_run!r} != {store.run_id}"
                )
            blob["params"] = index_params(cfg, arm_sha)
            with cfg.index_path(arm).open("wb") as f:
                pickle.dump(blob, f)
            print(f"  arm={arm}: copied baseline index "
                  f"({len(blob['passages'])} passages; text-identical)")
            return Index(blob["passages"],
                         np.load(cfg.vectors_path(arm))["vecs"],
                         blob["bm25"], arm)

    passages = _passages_from_store(store, cfg, arm=arm)

    if cfg.mode == "openai" and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it or put it in a .env "
            "file at the project root (gitignored). Needed for embeddings."
        )

    client = get_client(cfg)
    vecs = np.asarray(client.embed([p.text for p in passages]), dtype=np.float32)
    vecs /= (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    bm25 = BM25Okapi([tokenize(p.text) for p in passages],
                     k1=cfg.bm25_k1, b=cfg.bm25_b)

    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(cfg.vectors_path(arm), vecs=vecs)
    with cfg.index_path(arm).open("wb") as f:
        pickle.dump({"passages": passages, "bm25": bm25,
                     "run_id": store.run_id,
                     "params": index_params(cfg, arm_sha)}, f)
    return Index(passages, vecs, bm25, arm)


def load_index(arm: str, cfg: Config = CONFIG,
               required_run_id: Optional[str] = None) -> Index:
    vecs = np.load(cfg.vectors_path(arm))["vecs"]
    with cfg.index_path(arm).open("rb") as f:
        blob = pickle.load(f)
    blob_run = blob.get("run_id")
    if required_run_id and blob_run != required_run_id:
        raise FileNotFoundError(
            f"stale index at {cfg.index_path(arm)} "
            f"(run_id={blob_run!r}, need {required_run_id})")
    arm_sha = ""
    if arm != "baseline":
        from ..experiment.run_store import RunStore
        from ..optimisation.builder import arm_content_sha256
        store = RunStore.resolve(required_run_id, cfg)
        arm_sha = arm_content_sha256(store, arm)
    expected = index_params(cfg, arm_sha)
    saved = blob.get("params")
    if saved is not None and saved != expected:
        drift = {k: (saved.get(k), v) for k, v in expected.items()
                 if saved.get(k) != v}
        raise FileNotFoundError(
            f"index at {cfg.index_path(arm)} was built with different "
            f"parameters {drift} — rebuild with: geo index {arm}")
    return Index(blob["passages"], vecs, blob["bm25"], arm)


def passages_from_store(store: "RunStore", cfg: Config = CONFIG,
                        fc_suffix: str = "") -> List[Passage]:
    """Chunk freeze pages without embedding (control tests)."""
    return _passages_from_store(store, cfg, fc_suffix=fc_suffix)
