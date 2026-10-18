"""Generate one cited answer, with arm-specific passage treatments.

Two treatments are applied here rather than in retrieval, because both concern
what the model SEES rather than what was found:

SHUFFLE  Language models over-weight whatever appears first and last in a
    prompt. Without shuffling, whichever brand happened to rank first would
    gain an advantage unrelated to its content. Seeded, so it is reproducible.

POSITION CONTROL  Puerto et al. (NeurIPS 2025) found the rank of a document in
    the model's context matters far more than any content edit — a
    retrieval-position baseline measured roughly 7.6x more effective than the
    best content method. This arm forces one Flight Centre passage to position
    one and edits nothing, so "being placed first" can be compared directly
    against "being written better".
"""
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from ..api import get_client
from ..api.base import Passage
from ..config import CONFIG, Config
from .prompts import build_prompt


def prompt_char_budget(variant: str, cfg: Config = CONFIG) -> int:
    """fixed = whole page; reindexed = one retrieved chunk."""
    if variant == "fixed":
        return int(cfg.page_prompt_chars)
    return int(cfg.passage_prompt_chars)


@dataclass
class GenerationRecord:
    query_id: str
    query: str
    group: str
    stratum: str
    arm: str
    variant: str
    seed: int
    run: int
    model: str
    retrieved_brands: List[str]
    retrieved_ids: List[str]
    # Texts in the exact order the model saw them ([n] == retrieved_texts[n-1]).
    retrieved_texts: List[str]
    fc_context_positions: List[int]
    cited_indices: List[int]
    cited_brands: List[str]
    answer: str
    n_brands_retrieved: int = 0
    monopoly_retrieval: int = 0
    prompt: str = ""
    retrieved_urls: List[str] = field(default_factory=list)
    source_original_chars: List[int] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return self.__dict__.copy()


def shuffle_passages(passages: Sequence[Passage], seed: int) -> List[Passage]:
    out = list(passages)
    random.Random(seed).shuffle(out)
    return out


def force_first(passages: Sequence[Passage], brand: str) -> List[Passage]:
    """Move the first passage belonging to `brand` to position one."""
    target = next((p for p in passages if p.brand == brand), None)
    if target is None:
        return list(passages)
    return [target] + [p for p in passages if p is not target]


class Generator:
    def __init__(self, cfg: Config = CONFIG):
        self.cfg = cfg
        self._client = get_client(cfg)

    def run_once(self, query_row: Dict, passages: Sequence[Passage], *,
                 arm: str, variant: str, seed: int, run: int) -> GenerationRecord:
        ordered = list(passages)
        if self.cfg.shuffle_passages:
            ordered = shuffle_passages(ordered, seed * 10_000 + run)
        if arm == "position_control":
            ordered = force_first(ordered, self.cfg.our_brand)

        prompt = build_prompt(query_row["query"], ordered,
                              max_chars=prompt_char_budget(variant, self.cfg))
        answer = self._client.generate(prompt, self.cfg.temperature, self.cfg.top_p)

        cited = [int(n) for n in re.findall(r"\[(\d+)\]", answer)
                 if 1 <= int(n) <= len(ordered)]
        brands = [p.brand for p in ordered]
        n_brands = len(set(brands))
        return GenerationRecord(
            query_id=query_row["id"], query=query_row["query"],
            group=query_row.get("group", ""),
            stratum=query_row.get("stratum", ""),
            arm=arm, variant=variant,
            seed=seed, run=run, model=self._client.name,
            retrieved_brands=brands,
            retrieved_ids=[p.id for p in ordered],
            retrieved_texts=[p.text[:prompt_char_budget(variant, self.cfg)] for p in ordered],
            fc_context_positions=[i for i, p in enumerate(ordered, 1)
                                  if p.brand == self.cfg.our_brand],
            cited_indices=cited,
            cited_brands=[ordered[n - 1].brand for n in cited],
            answer=answer,
            prompt=prompt,
            retrieved_urls=[p.file for p in ordered],
            source_original_chars=[len(p.text) for p in ordered],
            n_brands_retrieved=n_brands,
            monopoly_retrieval=int(n_brands == 1))
