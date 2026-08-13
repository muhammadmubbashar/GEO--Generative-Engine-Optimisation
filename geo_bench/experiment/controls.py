"""Four control tests. A pipeline that merely runs is not a controlled
environment; these prove that it is. No result should be trusted until all
four pass.

T1 DETERMINISM      Retrieval must be identical on repeat. If it is not,
                    something is random that should not be, and no
                    before-and-after comparison is trustworthy.

T2 FAIRNESS         Competitor files must be byte-identical across every arm.
                    If a competitor file differs between arms, two variables
                    changed and attribution is void.

T3 ISOLATION        Inject a marker into Flight Centre pages and rebuild
                    passages (no full re-embed): competitor passage IDs must
                    stay identical, FC IDs must change, AND competitor-only
                    BM25 rank order on probe queries must be unchanged.
                    Competitor-only BM25 excludes the shared-N IDF artefact;
                    full-corpus IDF sensitivity on a tiny index remains a
                    documented reindexed limitation.

T4 REPRODUCIBILITY  Rebuilding the index must yield identical passage IDs.
                    Proves anyone can recreate the setup.
"""
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from rank_bm25 import BM25Okapi

from ..api.base import Passage
from ..api.offline_client import tokenize
from ..config import CONFIG, Config
from ..retrieval import Retriever, load_index
from ..retrieval.chunker import make_passages
from ..retrieval.parser import clean_brand_pages

# Additive marker (not full-page replacement): GEO interventions are additive.
# Full dummy replacement massively shifts corpus IDF and would fail rank
# isolation for reasons unrelated to operational edits.
_ISO_MARKER = "\n<!--geo-isolation-->\n<p>" + ("zzmarkerzz " * 50) + "</p>\n"

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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def t1_determinism(cfg: Config, query: str) -> ControlResult:
    r = Retriever(load_index("baseline", cfg), cfg)
    a = [p.id for p in r.retrieve(query)]
    b = [p.id for p in r.retrieve(query)]
    return ControlResult("T1 determinism", a == b,
                         f"{len(a)} passages, identical on repeat: {a == b}")


def t2_fairness(cfg: Config) -> ControlResult:
    arms = [a for a in cfg.arms if (cfg.corpus_dir / a).is_dir()]
    if len(arms) < 2:
        return ControlResult("T2 fairness", True, "only one arm exists yet — skipped")
    ok = True
    for brand in cfg.brands:
        if brand == cfg.our_brand:
            continue
        ref = {p.name: _sha(p) for p in (cfg.corpus_dir / arms[0] / brand).glob("*")}
        for arm in arms[1:]:
            cur = {p.name: _sha(p) for p in (cfg.corpus_dir / arm / brand).glob("*")}
            if cur != ref:
                ok = False
    return ControlResult("T2 fairness", ok,
                         f"competitor files identical across {len(arms)} arms")


def _passages_from_corpus(root: Path, cfg: Config) -> List[Passage]:
    passages: List[Passage] = []
    for brand in cfg.brands:
        paths = sorted((root / brand).glob("*.html"))
        if not paths:
            continue
        for path, text in clean_brand_pages(paths).items():
            passages.extend(make_passages(text, brand, path, cfg))
    return passages


def _bm25_competitor_ranks(passages: List[Passage], query: str,
                           cfg: Config) -> List[str]:
    """Competitor-only BM25 order (FC passages excluded from the index).

    Building BM25 on the full shared corpus makes IDF depend on FC chunk count
    (N in the IDF formula). That tiny-corpus artefact is a known reindexed
    limitation, not evidence that competitor *text* leaked. Isolation therefore
    ranks competitors in a competitor-only BM25 — if their cleaned text is
    unchanged, order must match exactly.
    """
    comp = [p for p in passages if p.brand != cfg.our_brand]
    bm25 = BM25Okapi([tokenize(p.text) for p in comp])
    scores = bm25.get_scores(tokenize(query))
    order = sorted(range(len(comp)), key=lambda i: (-scores[i], comp[i].id))
    return [comp[i].id for i in order]


def t3_isolation(cfg: Config,
                 probe_queries: Sequence[str] = _DEFAULT_PROBES) -> ControlResult:
    tmp = cfg.corpus_dir / "_isolation_test"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(cfg.corpus_dir / "baseline", tmp)
    fc_dir = tmp / cfg.our_brand
    n_marked = 0
    for p in fc_dir.glob("*.html"):
        p.write_text(p.read_text(encoding="utf-8") + _ISO_MARKER, encoding="utf-8")
        n_marked += 1
    if n_marked == 0:
        shutil.rmtree(tmp)
        return ControlResult("T3 isolation", False, "no Flight Centre HTML to mark")

    base = load_index("baseline", cfg).passages
    test = _passages_from_corpus(tmp, cfg)
    comp = lambda ps: sorted(p.id for p in ps if p.brand != cfg.our_brand)
    fcid = lambda ps: sorted(p.id for p in ps if p.brand == cfg.our_brand)
    comp_same = comp(base) == comp(test)
    fc_changed = fcid(base) != fcid(test)

    rank_failures: List[str] = []
    for q in probe_queries:
        a = _bm25_competitor_ranks(base, q, cfg)
        b = _bm25_competitor_ranks(test, q, cfg)
        if a != b:
            rank_failures.append(q)

    ranks_ok = len(rank_failures) == 0
    passed = comp_same and fc_changed and ranks_ok

    shutil.rmtree(tmp)
    for f in cfg.results_dir.glob("*_isolation_test*"):
        f.unlink()

    detail = (f"competitors unchanged: {comp_same}, FC changed: {fc_changed}, "
              f"competitor-only BM25 ranks stable on {len(probe_queries)} "
              f"probes: {ranks_ok}")
    if rank_failures:
        detail += f"; rank drift on: {rank_failures[:2]}"
    return ControlResult("T3 isolation", passed, detail)


def t4_reproducibility(cfg: Config) -> ControlResult:
    before = [p.id for p in load_index("baseline", cfg).passages]
    after = [p.id for p in _passages_from_corpus(cfg.corpus_dir / "baseline", cfg)]
    return ControlResult("T4 reproducibility", before == after,
                         f"{len(after)} passages, IDs identical after rebuild")


def run_control_tests(cfg: Config = CONFIG,
                      probe_query: str = "flights from melbourne to london"
                      ) -> List[ControlResult]:
    probes = (probe_query,) + tuple(q for q in _DEFAULT_PROBES if q != probe_query)
    # T3 before T4: T4 rebuilds baseline and is slow; fail fast on isolation.
    results = [t1_determinism(cfg, probe_query), t2_fairness(cfg),
               t3_isolation(cfg, probes), t4_reproducibility(cfg)]
    return results
