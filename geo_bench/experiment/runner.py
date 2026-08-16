"""Execute one arm under fixed or reindexed, against a frozen live pool.

Hash verification runs before EVERY experiment and raises on mismatch.
Protocol lock diffs are recorded (loud warning, not silent).
Routing decides fixed eligibility; every query runs reindexed.
"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..api.base import Passage
from ..config import CONFIG, Config
from ..generation import Generator
from ..retrieval import Retriever, load_index
from ..retrieval.chunker import make_passages
from ..search import LiveRetriever
from .protocol import check_lock
from .routing import load_routing, route_query, write_routing_csv
from .run_store import RunStore


def passage_align_key(p: Passage) -> Tuple[str, int]:
    """Stable join key: source URL/file + chunk ordinal."""
    loc = str(p.file)
    parts = p.id.split(":")
    if len(parts) < 4:
        raise ValueError(f"unparseable passage id: {p.id!r}")
    try:
        chunk_i = int(parts[-2])
    except ValueError as e:
        raise ValueError(f"unparseable chunk ordinal in {p.id!r}") from e
    return loc, chunk_i


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
                    f"fixed/reindexed swap: no arm passage for file={key[0]!r} "
                    f"chunk={key[1]} (baseline id={p.id})."
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
                f"Set mode to openai/anthropic, or pass --allow-demo."
            )
        if self.cfg.mode == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it or put it in a .env "
                "file at the project root (gitignored)."
            )

    def _require_heldout(self, arm: str, heldout: bool, final: bool) -> None:
        if not heldout:
            return
        if not final:
            raise RuntimeError(
                "Held-out queries are locked until the end of the study. "
                "Pass --final (and only then) to run queries/heldout.csv. "
                "They must never be used to tune anything."
            )
        if arm not in self.cfg.heldout_arms:
            raise RuntimeError(
                f"Held-out may only run on arms {self.cfg.heldout_arms}; "
                f"got arm={arm!r}."
            )

    def _run_budget(self, once: bool) -> Tuple[tuple, int]:
        if once or self.cfg.mode == "offline" or (
                self.cfg.mode not in self.cfg.reportable_modes):
            why = "once" if once else self.cfg.mode
            print(f"  {why}: 1 seed x 1 run per query "
                  f"(full design is {len(self.cfg.seeds)}x{self.cfg.runs_per_query})")
            return self.cfg.seeds[:1], 1
        return self.cfg.seeds, self.cfg.runs_per_query

    def freeze_live(self, arm: str = "baseline", queries_path: Path = None,
                    refresh: bool = False, allow_demo: bool = False,
                    heldout: bool = False, final: bool = False) -> RunStore:
        """Capture search (depth 20) + fetch/QC all captured pages."""
        self._require_reportable(allow_demo)
        if heldout and not final:
            raise RuntimeError(
                "Freezing held-out queries exposes their SERPs mid-study. "
                "They stay untouched until the final validation; pass "
                "--final only at that point.")
        store = RunStore.create("live", arm, "fixed", self.cfg, refresh=refresh)
        live = LiveRetriever(self.cfg, refresh=refresh, store=store)
        queries = self._load_queries(queries_path)
        for qi, row in enumerate(queries, 1):
            print(f"  freeze [{qi}/{len(queries)}] {row['id']} ...", flush=True)
            pool = live.freeze_query(row["id"], row["query"], store=store)
            print(f"    fc_in_capture={pool.fc_in_capture}  "
                  f"fc_rank={pool.fc_search_rank}  "
                  f"usable={pool.brands_usable}  "
                  f"missing={pool.brands_missing_usable}")
        store.write_manifest()
        store.set_active()
        write_routing_csv(store, self.cfg)
        print(f"  freeze complete -> {store.root}")
        print(f"  manifest -> {store.manifest_path()}")
        print(f"  routing  -> {self.cfg.routing_path()}")
        return store

    def _open_freeze(self, from_run: Optional[str],
                     accept_drift: bool = False) -> RunStore:
        store = RunStore.resolve(from_run, self.cfg)
        store.verify_frozen_pages()
        meta_path = store.root / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        check_lock(store, self.cfg, metadata=meta, strict=not accept_drift)
        store.write_json(meta_path, meta)
        if not self.cfg.routing_path().exists():
            write_routing_csv(store, self.cfg)
        return store

    def _prepare_answers(self, path: Path, run_id: str) -> Set[Tuple[str, int, int]]:
        """Resume if answers belong to this freeze; otherwise archive them."""
        if not path.exists() or path.stat().st_size == 0:
            return set()
        recs = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                recs.append(json.loads(line))
        rids = {r.get("run_id") for r in recs if r.get("run_id")}
        if rids and rids != {run_id}:
            bak = path.with_name(
                f"{path.stem}.1x1_archive{path.suffix}")
            n = 1
            while bak.exists():
                n += 1
                bak = path.with_name(
                    f"{path.stem}.1x1_archive{n}{path.suffix}")
            path.rename(bak)
            print(f"  archived prior answers -> {bak}")
            return set()
        done = {(r["query_id"], int(r.get("seed") or 1), int(r["run"]))
                for r in recs}
        if done:
            print(f"  resume {path.name}: {len(done)} rows already written")
        return done

    def _low_usable_flag(self, store: RunStore, query_id: str) -> Dict:
        routing = load_routing(self.cfg)
        row = routing.get(query_id) or route_query(store, query_id, self.cfg)
        return {
            "usable_docs": int(row.get("usable_docs") or 0),
            "low_usable": int(row.get("low_usable") or 0),
            "fc_best_rank": row.get("fc_best_rank", ""),
            "route": row.get("route", ""),
            "eligible_fixed": int(row.get("eligible_fixed") or 0),
        }

    def _run_fixed(self, arm: str, store: RunStore,
                   queries: List[Dict], seeds, runs) -> Path:
        if arm != "baseline":
            raise RuntimeError(
                f"fixed arm={arm!r} requires optimisation pages; "
                "not part of baseline lock. Run baseline only.")
        live = LiveRetriever(self.cfg, refresh=False, store=store)
        routing = load_routing(self.cfg)
        out_path = store.answers_jsonl(arm, "fixed")
        mirror = self.cfg.answers_path(arm, "fixed")
        if self.cfg.mode not in self.cfg.reportable_modes:
            mirror = self.cfg.demo_dir / mirror.name
        mirror.parent.mkdir(parents=True, exist_ok=True)
        done = self._prepare_answers(out_path, store.run_id)
        done |= self._prepare_answers(mirror, store.run_id)
        mode = "a" if done else "w"

        skipped = []
        n_wrote = 0
        with out_path.open(mode, encoding="utf-8") as fh, \
                mirror.open(mode, encoding="utf-8") as mh:
            for qi, row in enumerate(queries, 1):
                qid = row["id"]
                route = routing.get(qid) or route_query(store, qid, self.cfg)
                if not int(route.get("eligible_fixed") or 0):
                    skipped.append(qid)
                    print(f"  [{qi}/{len(queries)}] {qid}  SKIP fixed "
                          f"(route={route.get('route')} fc_usable="
                          f"{route.get('fc_usable')})")
                    continue
                pending = [(s, r) for s in seeds for r in range(1, runs + 1)
                           if (qid, s, r) not in done]
                if not pending:
                    print(f"  [{qi}/{len(queries)}] {qid}  already done")
                    continue
                pool = live.pool_from_freeze(qid, row["query"], store=store)
                pool = live.substitute_fc(pool, arm)
                if not pool.passages:
                    raise RuntimeError(f"fixed pool empty for {qid}")
                flags = self._low_usable_flag(store, qid)
                for seed, run in pending:
                    rec = self.generator.run_once(
                        row, pool.passages, arm=arm, variant="fixed",
                        seed=seed, run=run)
                    payload = rec.as_dict()
                    # Pool meta must NEVER clobber the record: the record's
                    # retrieved_* fields are in post-shuffle order (what the
                    # model actually saw); pool meta is pre-shuffle.
                    payload.update({k: v for k, v in pool.meta_dict().items()
                                    if k not in payload})
                    payload["pool_brands"] = [p.brand for p in pool.passages]
                    payload.update(flags)
                    payload["run_id"] = store.run_id
                    line = json.dumps(payload, ensure_ascii=False)
                    fh.write(line + "\n")
                    mh.write(line + "\n")
                    fh.flush()
                    mh.flush()
                    store.write_generation(arm, qid, run, seed, {
                        **payload,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                    n_wrote += 1
                print(f"  [{qi}/{len(queries)}] {qid}  "
                      f"fc_rank={pool.fc_search_rank}  "
                      f"usable_docs={flags['usable_docs']}")
        if skipped:
            print(f"  fixed skipped (not eligible): {', '.join(skipped)}")
        return out_path

    def _run_reindexed(self, arm: str, store: RunStore,
                       queries: List[Dict], seeds, runs) -> Path:
        try:
            index = load_index(arm, self.cfg, required_run_id=store.run_id)
        except (FileNotFoundError, OSError):
            from ..retrieval import build_index
            print(f"  building freeze index for arm={arm} ...")
            index = build_index(arm, self.cfg, store=store)
        retriever = Retriever(index, self.cfg)
        arm_passages = None
        if arm != "baseline":
            raise RuntimeError(
                f"reindexed arm={arm!r} requires optimisation pages; "
                "not part of baseline lock. Run baseline only.")

        out_path = store.answers_jsonl(arm, "reindexed")
        mirror = self.cfg.answers_path(arm, "reindexed")
        if self.cfg.mode not in self.cfg.reportable_modes:
            mirror = self.cfg.demo_dir / mirror.name
        mirror.parent.mkdir(parents=True, exist_ok=True)
        done = self._prepare_answers(out_path, store.run_id)
        done |= self._prepare_answers(mirror, store.run_id)
        mode = "a" if done else "w"

        with out_path.open(mode, encoding="utf-8") as fh, \
                mirror.open(mode, encoding="utf-8") as mh:
            for qi, row in enumerate(queries, 1):
                pending = [(s, r) for s in seeds for r in range(1, runs + 1)
                           if (row["id"], s, r) not in done]
                if not pending:
                    print(f"  [{qi}/{len(queries)}] {row['id']}  already done")
                    continue
                retrieved = retriever.retrieve(row["query"])
                if arm_passages is not None:
                    retrieved = self._swap_fc_text(retrieved, arm_passages)
                if not retrieved:
                    raise RuntimeError(
                        f"reindexed retrieval empty for {row['id']}")
                flags = self._low_usable_flag(store, row["id"])
                brands = [p.brand for p in retrieved]
                for seed, run in pending:
                    rec = self.generator.run_once(
                        row, retrieved, arm=arm, variant="reindexed",
                        seed=seed, run=run)
                    payload = rec.as_dict()
                    payload.update(flags)
                    # Pre-shuffle retrieval order (RRF rank) for retrieval_rank.
                    payload["pool_brands"] = [p.brand for p in retrieved]
                    payload["run_id"] = store.run_id
                    line = json.dumps(payload, ensure_ascii=False)
                    fh.write(line + "\n")
                    mh.write(line + "\n")
                    fh.flush()
                    mh.flush()
                    store.write_generation(arm, row["id"], run, seed, {
                        **payload,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                print(f"  [{qi}/{len(queries)}] {row['id']}  "
                      f"brands={brands}  usable_docs={flags['usable_docs']}")
        return out_path

    def run(self, arm: str, variant: str = "reindexed",
            queries_path: Path = None, allow_demo: bool = False,
            once: bool = False, refresh: bool = False,
            from_run: Optional[str] = None,
            heldout: bool = False, final: bool = False,
            accept_drift: bool = False) -> Path:
        self._require_reportable(allow_demo)
        self._require_heldout(arm, heldout, final)
        if variant == "live":
            print("WARNING: --variant live is retired; using fixed "
                  "(frozen analysis pool).")
            variant = "fixed"
        if variant not in self.cfg.retrieval_variants:
            raise RuntimeError(
                f"unknown variant={variant!r}; "
                f"allowed={self.cfg.retrieval_variants}")
        qpath = self.cfg.heldout_file if heldout else queries_path
        queries = self._load_queries(qpath)
        seeds, runs = self._run_budget(once)
        store = self._open_freeze(from_run, accept_drift=accept_drift)
        print(f"  freeze RUN_ID={store.run_id}")
        print(f"  budget: {len(seeds)} seeds x {runs} runs x "
              f"{len(queries)} queries  model={self.cfg.gen_model}")
        if variant == "fixed":
            return self._run_fixed(arm, store, queries, seeds, runs)
        return self._run_reindexed(arm, store, queries, seeds, runs)
