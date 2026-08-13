"""Corpus quality control — three checks, each catching a specific failure.

CHECK 1  EMPTY-SHELL AMBIGUITY (the dangerous one)
    A genuinely client-side-rendered Flight Centre page and a failed fetch look
    identical on disk: almost no text. One is the study's headline finding, the
    other is broken data. Every page under the word floor is flagged for a
    human to confirm in a browser. Never assume.

CHECK 2  NEAR-DUPLICATES
    Templated pages inflate one brand's chunk count and hand it extra tickets
    in the retrieval draw.

CHECK 3  VOLUME
    Pages, words and chunks per brand. Recording the asymmetry openly turns a
    possible criticism into a stated finding.
"""
import itertools
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from ..config import CONFIG, Config
from ..retrieval.parser import page_text

WORD_FLOOR = 200
DUPLICATE_THRESHOLD = 0.85


@dataclass
class QualityReport:
    thin_pages: List[Tuple[str, int]]
    duplicates: List[Tuple[str, str, float]]
    volume: Dict[str, Dict[str, int]]

    def render(self) -> str:
        out = ["=" * 62, "CHECK 1 — pages below the word floor", "=" * 62]
        if not self.thin_pages:
            out.append("None. For Flight Centre this would be surprising — "
                       "verify the fetcher is not executing JavaScript.")
        for path, words in self.thin_pages:
            out.append(f"  {words:>5} words  {path}")
        if self.thin_pages:
            out += ["", "  ACTION: open each in Chrome, press Ctrl+U, and record",
                    "     confirmed-csr-empty  (a finding — keep it)",
                    "     fetch-failed         (re-collect, manually if needed)"]

        out += ["", "=" * 62, "CHECK 2 — near-duplicate pages", "=" * 62]
        if not self.duplicates:
            out.append("None found.")
        for a, b, sim in self.duplicates:
            out.append(f"  {sim:.0%} similar: {Path(a).name}  <->  {Path(b).name}")

        out += ["", "=" * 62, "CHECK 3 — volume by brand (report this openly)",
                "=" * 62, f"{'brand':<16}{'pages':>7}{'words':>10}{'chunks':>9}",
                "-" * 42]
        for brand, v in self.volume.items():
            out.append(f"{brand:<16}{v['pages']:>7}{v['words']:>10,}{v['chunks']:>9}")
        return "\n".join(out)


def run_quality_checks(arm: str = "baseline", cfg: Config = CONFIG) -> QualityReport:
    root = cfg.corpus_dir / arm
    records = []
    for brand in cfg.brands:
        for path in sorted((root / brand).glob("*.html")):
            text = page_text(path)
            records.append({"brand": brand, "path": str(path),
                            "words": len(text.split()), "text": text})

    thin = [(r["path"], r["words"]) for r in records if r["words"] < WORD_FLOOR]

    dupes = []
    for a, b in itertools.combinations(records, 2):
        if a["brand"] != b["brand"]:
            continue
        sa, sb = set(a["text"].split()), set(b["text"].split())
        if sa and sb:
            jac = len(sa & sb) / len(sa | sb)
            if jac >= DUPLICATE_THRESHOLD:
                dupes.append((a["path"], b["path"], jac))

    step = cfg.chunk_words - cfg.chunk_overlap
    volume: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"pages": 0, "words": 0, "chunks": 0})
    for r in records:
        v = volume[r["brand"]]
        v["pages"] += 1
        v["words"] += r["words"]
        v["chunks"] += max(1, -(-r["words"] // step))
    return QualityReport(thin, dupes, dict(volume))
