"""Prompt construction.

GENERATION_PROMPT is reproduced near-verbatim from Aggarwal et al. (KDD 2024),
Listing 1. Keeping their wording matters: if we wrote our own prompt, any
difference between our results and theirs could be attributed to prompt
phrasing rather than to the interventions. Using theirs removes that confound.
"""
from typing import Sequence

from ..api.base import Passage

GENERATION_PROMPT = (
    "Write an accurate and concise answer for the given user question, using "
    "only the provided summarized web search results. The answer should be "
    "correct, high-quality, and written by an expert using an unbiased and "
    "journalistic tone. The answer should be informative, interesting, and "
    "engaging. The answer's logic and reasoning should be rigorous and "
    "defensible. Every sentence in the answer should be immediately followed "
    "by an in-line citation to the search result(s). The cited search "
    "result(s) should fully support all the information in the sentence. "
    "Search results need to be cited using [index]. When citing several "
    "search results, use [1][2][3] format rather than [1, 2, 3].\n\n"
    "Question: {query}\n\nSearch Results:\n{sources}"
)

# Fallback only; the runner passes Config.page_prompt_chars (fixed) or
# Config.passage_prompt_chars (reindexed).
MAX_PASSAGE_CHARS = 2600


def build_prompt(query: str, passages: Sequence[Passage],
                 max_chars: int = 0) -> str:
    """Render passages as numbered sources. Brand names are NOT stripped here —
    the model sees pages as a real engine would."""
    budget = int(max_chars) or MAX_PASSAGE_CHARS
    block = "\n\n".join(f"[{i}] {p.text[:budget]}"
                        for i, p in enumerate(passages, 1))
    return GENERATION_PROMPT.format(query=query, sources=block)


def prompt_sha256() -> str:
    """Fingerprint of the frozen prompt template (for the protocol lock)."""
    import hashlib
    return hashlib.sha256(GENERATION_PROMPT.encode("utf-8")).hexdigest()
