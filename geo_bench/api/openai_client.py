"""OpenAI-backed provider — the real experiment."""
import time
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

    def _retry(self, fn, *, attempts: int = 10):
        from openai import APIConnectionError, APITimeoutError, RateLimitError
        last = None
        for i in range(attempts):
            try:
                return fn()
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                last = exc
                wait = min(90, 2 ** i)
                print(f"  [openai retry {i+1}/{attempts} in {wait}s] {exc}",
                      flush=True)
                time.sleep(wait)
        raise last

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 100):           # stay inside batch limits
            batch = list(texts[i:i + 100])
            print(f"  embed {i // 100 + 1}/{(len(texts) + 99) // 100} "
                  f"({len(batch)} texts)", flush=True)
            resp = self._retry(lambda b=batch: self._client.embeddings.create(
                model=self._embed_model, input=b))
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

        def _call(use_sampling: bool):
            if use_sampling:
                return self._client.chat.completions.create(
                    model=self._gen_model, temperature=temperature, top_p=top_p,
                    messages=messages)
            return self._client.chat.completions.create(
                model=self._gen_model, messages=messages)

        def _once():
            try:
                return _call(True)
            except BadRequestError as exc:
                msg = str(exc).lower()
                if "temperature" not in msg and "top_p" not in msg:
                    raise
                return _call(False)

        resp = self._retry(_once)
        return resp.choices[0].message.content or ""
