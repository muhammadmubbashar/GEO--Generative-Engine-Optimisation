"""Anthropic (Claude)-backed provider.

Claude generates the answers. Anthropic has NO embeddings endpoint, so the
retrieval embeddings still come from OpenAI's embedding API. Running in this
mode therefore needs BOTH keys:

    ANTHROPIC_API_KEY   for generation (the model under test)
    OPENAI_API_KEY      for embeddings only (retrieval infrastructure)

This split is methodologically fine: embeddings are part of the fixed
retrieval apparatus, identical across arms; the engine being measured is the
generator.
"""
from typing import List, Sequence

from .base import LLMClient

MAX_ANSWER_TOKENS = 1024


class AnthropicClient(LLMClient):
    def __init__(self, gen_model: str, embed_model: str) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:                    # pragma: no cover
            raise RuntimeError(
                "anthropic not installed: pip install anthropic") from exc
        try:
            from openai import OpenAI
        except ImportError as exc:                    # pragma: no cover
            raise RuntimeError(
                "openai is required for embeddings in anthropic mode: "
                "pip install openai") from exc
        self._client = Anthropic()                    # reads ANTHROPIC_API_KEY
        self._embedder = OpenAI()                     # reads OPENAI_API_KEY
        self._gen_model = gen_model
        self._embed_model = embed_model

    @property
    def name(self) -> str:
        return self._gen_model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 100):           # stay inside batch limits
            resp = self._embedder.embeddings.create(
                model=self._embed_model, input=list(texts[i:i + 100]))
            out.extend(d.embedding for d in resp.data)
        return out

    def generate(self, prompt: str, temperature: float, top_p: float) -> str:
        resp = self._client.messages.create(
            model=self._gen_model,
            max_tokens=MAX_ANSWER_TOKENS,
            temperature=temperature,
            top_p=top_p,
            messages=[{"role": "user", "content": prompt}])
        return "".join(block.text for block in resp.content
                       if block.type == "text")
