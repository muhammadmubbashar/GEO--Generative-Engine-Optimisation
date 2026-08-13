"""Build the prompt, generate the cited answer, apply arm-specific treatments.

Selection and generation happen together inside the model, deliberately. We do
not build our own reranking formula: a scoring rule that rewarded the same
features our interventions add (author names, dates, schema) would guarantee
its own result. Letting the model choose keeps the measurement honest.
"""
from .prompts import GENERATION_PROMPT, build_prompt
from .generator import Generator, GenerationRecord

__all__ = ["GENERATION_PROMPT", "build_prompt", "Generator", "GenerationRecord"]
