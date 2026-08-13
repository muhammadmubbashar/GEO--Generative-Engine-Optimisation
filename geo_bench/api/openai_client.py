"""OpenAI-backed provider — the real experiment."""
from typing import List, Sequence

from .base import LLMClient


class OpenAIClient(LLMClient):
    def __init__(self, gen_model: str, embed_model: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:                    # pragma: no cover
            raise RuntimeError(
                "openai not installed: pip install 'geo-bench-fc[openai]'"
            ) from exc
        self._client = OpenAI()
        self._gen_model = gen_model
        self._embed_model = embed_model

    @property
    def name(self) -> str:
        return self._gen_model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 100):           # stay inside batch limits
            resp = self._client.embeddings.create(
                model=self._embed_model, input=list(texts[i:i + 100]))
            out.extend(d.embedding for d in resp.data)
        return out

    def generate(self, prompt: str, temperature: float, top_p: float) -> str:
        """Generate an answer.

        Some models (e.g. gpt-5.x) only accept the default temperature and
        reject custom temperature/top_p. We try Aggarwal settings first, then
        fall back to model defaults so the run still completes.
        """
        from openai import BadRequestError

        messages = [{"role": "user", "content": prompt}]
        try:
            resp = self._client.chat.completions.create(
                model=self._gen_model, temperature=temperature, top_p=top_p,
                messages=messages)
        except BadRequestError as exc:
            msg = str(exc).lower()
            if "temperature" not in msg and "top_p" not in msg:
                raise
            resp = self._client.chat.completions.create(
                model=self._gen_model, messages=messages)
        return resp.choices[0].message.content or ""
