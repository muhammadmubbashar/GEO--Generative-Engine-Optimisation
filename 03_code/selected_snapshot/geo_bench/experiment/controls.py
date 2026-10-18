"""Four control tests against the frozen live pool.

T1 DETERMINISM      Retrieval identical on repeat.
T2 FAIRNESS         Non-FC freeze pages byte-identical across arms (hash).
T3 ISOLATION        FC marker: competitor IDs unchanged, FC IDs change,
                    competitor-only BM25 ranks stable on probes.
T4 REPRODUCIBILITY  Re-chunk freeze → identical passage IDs.
"""
import hashlib
from dataclasses import dataclass
from typing import List, Sequence

from rank_bm25 import BM25Okapi

from ..api.base import Passage
from ..api.offline_client import tokenize
from ..config import CONFIG, Config
from ..retrieval import Retriever, load_index
from ..retrieval.index import passages_from_store
from ..search.live_retriever import brand_for_url
from .run_store import RunStore

_ISO_MARKER = "\n<!--geo-isolation-->\n" + ("zzmarkerzz " * 50)

_DEFAULT_PROBES: tuple = (
    "flights from melbourne to london",
    "i’m looking for flights from sydney to tokyo",
    "i’m looking to book a business class flight",
    "i’m looking for multi city flight tickets",
    "i’m looking for flights from perth to bali",
)


@dataclass
class ControlResult:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"{self.name:<22}{'PASS' if self.passed else 'FAIL'}  ({self.detail})"


def t1_determinism(cfg: Config, query: str,
                   run_id: str = None) -> ControlResult:
    try:
        r = Retriever(load_index("baseline", cfg, required_run_id=run_id), cfg)
    except FileNotFoundError:
        return ControlResult(
            "T1 determinism", False,
            "no/stale freeze index - run: geo index baseline --from-run <RUN_ID>")
    a = [p.id for p in r.retrieve(query)]
    b = [p.id for p in r.retrieve(query)]
    return ControlResult("T1 determinism", a == b,
                         f"{len(a)} passages, identical on repeat: {a == b}")


def t2_fairness(cfg: Config, store: RunStore) -> ControlResult:
    """Non-FC freeze page hashes must match the manifest.

    Cross-arm identity: only FC text may change. Until a second arm exists,
    verify freeze non-FC hashes against the manifest (and skip if no manifest).
    """
    store.verify_frozen_pages()
    fc = cfg.our_brand
    n_comp = 0
    for meta in store.iter_page_metas():
        url = meta.get("url") or ""
        brand = meta.get("brand") or brand_for_url(url, cfg)
        if brand == fc:
            continue
        n_comp += 1
        d = store.page_dir(meta.get("url") or "")
        raw = d / "raw.html"
        if not raw.exists():
            return ControlResult("T2 fairness", False,
                                 f"missing competitor page {meta.get('url')}")
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        if digest != (meta.get("sha256") or ""):
            return ControlResult(
                "T2 fairness", False,
                f"competitor hash drift: {meta.get('url')}")
    return ControlResult(
        "T2 fairness", True,
        f"{n_comp} non-FC freeze pages hash-match manifest/meta "
        "(only one arm exists - cross-arm check when arms are added)")


def _bm25_competitor_ranks(passages: List[Passage], query: str,
                           cfg: Config) -> List[str]:
    comp = [p for p in passages if p.brand != cfg.our_brand]
    if not comp:
        return []
    bm25 = BM25Okapi([tokenize(p.text) for p in comp])
    scores = bm25.get_scores(tokenize(query))
    order = sorted(range(len(comp)), key=lambda i: (-scores[i], comp[i].id))
    return [comp[i].id for i in order]


def t3_isolation(cfg: Config, store: RunStore,
                 probe_queries: Sequence[str] = _DEFAULT_PROBES) -> ControlResult:
    base = passages_from_store(store, cfg)
    test = passages_from_store(store, cfg, fc_suffix=_ISO_MARKER)
    fc = cfg.our_brand
    n_marked = sum(1 for p in test if p.brand == fc)
    if n_marked == 0:
        return ControlResult("T3 isolation", False, "no Flight Centre freeze pages to mark")

    comp = lambda ps: sorted(p.id for p in ps if p.brand != fc)
    fcid = lambda ps: sorted(p.id for p in ps if p.brand == fc)
    comp_same = comp(base) == comp(test)
    fc_changed = fcid(base) != fcid(test)

    rank_failures: List[str] = []
    for q in probe_queries:
        if _bm25_competitor_ranks(base, q, cfg) != _bm25_competitor_ranks(test, q, cfg):
            rank_failures.append(q)
    ranks_ok = not rank_failures
    passed = comp_same and fc_changed and ranks_ok
    detail = (f"competitors unchanged: {comp_same}, FC changed: {fc_changed}, "
              f"competitor-only BM25 ranks stable on {len(probe_queries)} "
              f"probes: {ranks_ok}")
    if rank_failures:
        detail += f"; rank drift on: {rank_failures[:2]}"
    return ControlResult("T3 isolation", passed, detail)


def t4_reproducibility(cfg: Config, store: RunStore) -> ControlResult:
    try:
        before = [p.id for p in load_index(
            "baseline", cfg, required_run_id=store.run_id).passages]
    except FileNotFoundError:
        return ControlResult(
            "T4 reproducibility", False,
            "no/stale freeze index - run: geo index baseline --from-run <RUN_ID>")
    after = [p.id for p in passages_from_store(store, cfg)]
    return ControlResult("T4 reproducibility", before == after,
                         f"{len(after)} passages, IDs identical after rebuild")


def run_control_tests(cfg: Config = CONFIG,
                      probe_query: str = "flights from melbourne to london",
                      run_id: str = None) -> List[ControlResult]:
    store = RunStore.resolve(run_id, cfg)
    store.verify_frozen_pages()
    probes = (probe_query,) + tuple(q for q in _DEFAULT_PROBES if q != probe_query)
    return [
        t1_determinism(cfg, probe_query, run_id=store.run_id),
        t2_fairness(cfg, store),
        t3_isolation(cfg, store, probes),
        t4_reproducibility(cfg, store),
    ]
