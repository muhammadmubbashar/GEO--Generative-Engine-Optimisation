"""Execute one arm under one retrieval variant.

THE VARIANTS

  fixed      Baseline retrieval candidate set; FC text swapped (Aggarwal-style).
  reindexed  Index rebuilt per arm (retrieval + representation).
  live       Frozen live-search pool; FC text may be substituted (E1/E2).

Live protocol: freeze retrieval+pages into runs/<RUN_ID>/ first, verify hashes,
then generate against that freeze. Competitor pages are byte-identical across
arms by construction.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..api.base import Passage
from ..config import CONFIG, Config
from ..generation import Generator
from ..retrieval import Retriever, load_index
from ..search import LiveRetriever
from .run_store import RunStore


def passage_align_key(p: Passage) -> Tuple[str, int]:
    """Stable join key across arms: source filename + chunk ordinal."""
    name = Path(p.file).name
    parts = p.id.split(":")
    if len(parts) < 4:
        raise ValueError(f"unparseable passage id (need brand:file:i:hash): {p.id!r}")
    try:
        chunk_i = int(parts[-2])
    except ValueError as e:
        raise ValueError(f"unparseable chunk ordinal in passage id: {p.id!r}") from e
    return name, chunk_i


class ExperimentRunner:
    def __init__(self, cfg: Config = CONFIG):
        self.cfg = cfg
        self.generator = Generator(cfg)

    def _load_queries(self, path: Path = None) -> List[Dict]:
        p = path or self.cfg.queries_file
        return list(csv.DictReader(p.open(encoding="utf-8")))

    def _swap_fc_text(self, retrieved: List[Passage],
                      arm_passages: List[Passage]) -> List[Passage]:
        arm_fc = {
            passage_align_key(p): p
            for p in arm_passages if p.brand == self.cfg.our_brand
        }
        out: List[Passage] = []
        for p in retrieved:
            if p.brand != self.cfg.our_brand:
                out.append(p)
                continue
            key = passage_align_key(p)
            replacement = arm_fc.get(key)
            if replacement is None:
                raise RuntimeError(
                    f"fixed swap: no arm passage for file={key[0]!r} chunk={key[1]} "
                    f"(baseline id={p.id}). Chunk boundaries likely shifted under "
                    f"the intervention — keep edits length-neutral or freeze spans."
                )
            out.append(Passage(
                id=p.id, brand=p.brand, text=replacement.text,
                file=p.file, words=replacement.words))
        return out

    def _require_reportable(self, allow_demo: bool) -> None:
        if allow_demo:
            return
        if self.cfg.mode not in self.cfg.reportable_modes:
            raise RuntimeError(
                f"mode={self.cfg.mode!r} is not reportable "
                f"(allowed: {self.cfg.reportable_modes}). "
                f"Set mode to openai/anthropic for scored results, or pass "
                f"allow_demo=True / --allow-demo for pipeline smoke tests only."
            )

    def _run_budget(self, once: bool) -> Tuple[tuple, int]:
        if once or self.cfg.mode == "offline" or (
                self.cfg.mode not in self.cfg.reportable_modes):
            why = "once" if once else self.cfg.mode
            print(f"  {why}: 1 seed × 1 run per query "
                  f"(full design is {len(self.cfg.seeds)}×{self.cfg.runs_per_query})")
            return self.cfg.seeds[:1], 1
        return self.cfg.seeds, self.cfg.runs_per_query

    def freeze_live(self, arm: str = "baseline", queries_path: Path = None,
                    refresh: bool = False,
                    allow_demo: bool = False) -> RunStore:
        """Capture search (depth 20) + fetch/clean analysis pages (depth 10)."""
        self._require_reportable(allow_demo)
        store = RunStore.create("live", arm, "live", self.cfg, refresh=refresh)
        live = LiveRetriever(self.cfg, refresh=refresh, store=store)
        queries = self._load_queries(queries_path)
        for qi, row in enumerate(queries, 1):
            print(f"  freeze [{qi}/{len(queries)}] {row['id']} ...", flush=True)
            pool = live.freeze_query(row["id"], row["query"], store=store)
            print(f"    fc_in_capture={pool.fc_in_capture}  "
                  f"fc_rank={pool.fc_search_rank}  "
                  f"usable={pool.brands_usable}  "
                  f"missing={pool.brands_missing_usable}")
        print(f"  freeze complete → {store.root}")
        return store

    def _run_live(self, arm: str, queries_path: Path = None,
                  allow_demo: bool = False, once: bool = False,
                  refresh: bool = False,
                  from_run: Optional[str] = None) -> Path:
        queries = self._load_queries(queries_path)
        seeds, runs = self._run_budget(once)

        if from_run:
            store = RunStore.open(from_run, self.cfg)
            # Arm generation under same freeze; nest under generation/<arm>/
            print(f"  using freeze RUN_ID={store.run_id}")
        else:
            # Freeze then generate in one RUN_ID
            store = self.freeze_live(arm=arm, queries_path=queries_path,
                                     refresh=refresh, allow_demo=allow_demo)

        live = LiveRetriever(self.cfg, refresh=False, store=store)
        out_path = store.answers_jsonl(arm, "live")
        # Also mirror to results/ for existing score CLI
        mirror = self.cfg.answers_path(arm, "live")
        if self.cfg.mode not in self.cfg.reportable_modes:
            mirror = self.cfg.demo_dir / mirror.name
        mirror.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", encoding="utf-8") as fh, \
                mirror.open("w", encoding="utf-8") as mh:
            for qi, row in enumerate(queries, 1):
                pool = live.pool_from_freeze(row["id"], row["query"], store=store)
                pool = live.substitute_fc(pool, arm)
                if not pool.passages:
                    raise RuntimeError(
                        f"live pool has zero passages for {row['id']}")
                for seed in seeds:
                    for run in range(1, runs + 1):
                        rec = self.generator.run_once(
                            row, pool.passages, arm=arm, variant="live",
                            seed=seed, run=run)
                        payload = rec.as_dict()
                        payload.update(pool.meta_dict())
                        payload["run_id"] = store.run_id
                        line = json.dumps(payload, ensure_ascii=False)
                        fh.write(line + "\n")
                        mh.write(line + "\n")
                        store.write_generation(arm, row["id"], run, seed, {
                            **payload,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "documents_used": [
                                {"id": p.id, "brand": p.brand, "url": p.file,
                                 "words": p.words}
                                for p in pool.passages
                            ],
                        })
                print(f"  [{qi}/{len(queries)}] {row['id']}  "
                      f"fc_in_capture={pool.fc_in_capture}  "
                      f"fc_rank={pool.fc_search_rank}  "
                      f"usable={pool.brands_usable}  "
                      f"missing={pool.brands_missing_usable}")
        return out_path

    def _run_local(self, arm: str, variant: str, queries_path: Path = None,
                   allow_demo: bool = False, once: bool = False) -> Path:
        store = RunStore.create("local", arm, variant, self.cfg, refresh=False)
        retrieval_arm = "baseline" if variant == "fixed" else arm
        index = load_index(retrieval_arm, self.cfg)
        retriever = Retriever(index, self.cfg)
        arm_passages = (load_index(arm, self.cfg).passages
                        if variant == "fixed" and arm != "baseline" else None)

        queries = self._load_queries(queries_path)
        seeds, runs = self._run_budget(once)
        out_path = store.answers_jsonl(arm, variant)
        mirror = self.cfg.answers_path(arm, variant)
        if self.cfg.mode not in self.cfg.reportable_modes:
            mirror = self.cfg.demo_dir / mirror.name
        mirror.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", encoding="utf-8") as fh, \
                mirror.open("w", encoding="utf-8") as mh:
            for qi, row in enumerate(queries, 1):
                retrieved = retriever.retrieve(row["query"])
                if arm_passages is not None:
                    retrieved = self._swap_fc_text(retrieved, arm_passages)
                brands = [p.brand for p in retrieved]
                store.write_retrieval(row["id"], {
                    "query_id": row["id"],
                    "query": row["query"],
                    "variant": variant,
                    "retrieval_arm": retrieval_arm,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "retrieved_ids": [p.id for p in retrieved],
                    "retrieved_brands": brands,
                    "retrieved_files": [p.file for p in retrieved],
                })
                for seed in seeds:
                    for run in range(1, runs + 1):
                        rec = self.generator.run_once(
                            row, retrieved, arm=arm, variant=variant,
                            seed=seed, run=run)
                        payload = rec.as_dict()
                        payload["run_id"] = store.run_id
                        line = json.dumps(payload, ensure_ascii=False)
                        fh.write(line + "\n")
                        mh.write(line + "\n")
                        store.write_generation(arm, row["id"], run, seed, {
                            **payload,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        })
                print(f"  [{qi}/{len(queries)}] {row['id']}")
        return out_path

    def run(self, arm: str, variant: str = "reindexed",
            queries_path: Path = None, allow_demo: bool = False,
            once: bool = False, refresh: bool = False,
            from_run: Optional[str] = None) -> Path:
        self._require_reportable(allow_demo)
        if variant not in self.cfg.retrieval_variants:
            raise RuntimeError(
                f"unknown variant={variant!r}; "
                f"allowed={self.cfg.retrieval_variants}")
        if variant == "live":
            return self._run_live(
                arm, queries_path=queries_path, allow_demo=allow_demo,
                once=once, refresh=refresh, from_run=from_run)
        return self._run_local(
            arm, variant, queries_path=queries_path,
            allow_demo=allow_demo, once=once)
