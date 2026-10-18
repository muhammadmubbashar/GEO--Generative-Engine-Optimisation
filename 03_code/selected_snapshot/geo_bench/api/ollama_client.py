"""Ollama-backed provider — local models, no API key, no per-token cost.

Talks to the Ollama server (default http://localhost:11434) over its REST API:
  /api/embed  for embeddings (use a dedicated embedding model, e.g.
              nomic-embed-text — generation models produce poor vectors)
  /api/chat   for generation

num_ctx is raised explicitly because Ollama's default context window (4096
tokens) is smaller than our prompt: 10 passages x 1200 chars plus the
instruction block. Without this the tail passages would be silently truncated
and citation counts would be biased against whatever shuffled to the end.

SYSTEM_PROMPT exists because small local Llama models refuse flight-price
questions as "real-time data" requests (observed: 2/2 refusals for llama3.2:3b
on the bare Aggarwal prompt). The system message frames the task as answering
from supplied search results; the Aggarwal et al. generation prompt itself is
passed through verbatim as the user message, so prompt comparability with the
paper is preserved. Larger API models do not need this.
"""
from typing import List, Sequence

import requests

from .base import LLMClient

DEFAULT_HOST = "http://localhost:11434"
SYSTEM_PROMPT = (
    "You are the answer-generation component of an AI search engine. "
    "You are given a user question and a set of web search results that were "
    "retrieved for it. The search results are current and are your only "
    "source of truth. Always produce an answer synthesised from them, with "
    "in-line [index] citations as instructed. Do not refuse, do not mention "
    "real-time data or your own limitations."
)
NUM_CTX = 8192
EMBED_BATCH = 64
GEN_TIMEOUT_S = 600
EMBED_TIMEOUT_S = 300


class OllamaClient(LLMClient):
    def __init__(self, gen_model: str, embed_model: str,
                 host: str = DEFAULT_HOST) -> None:
        self._host = host.rstrip("/")
        self._gen_model = gen_model
        self._embed_model = embed_model
        self._check_server()

    def _check_server(self) -> None:
        try:
            resp = requests.get(f"{self._host}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Ollama server not reachable at {self._host}. "
                "Start it with 'ollama serve' (or launch the Ollama app)."
            ) from exc
        available = {m["name"] for m in resp.json().get("models", [])}
        for wanted in (self._gen_model, self._embed_model):
            if wanted not in available and f"{wanted}:latest" not in available:
                raise RuntimeError(
                    f"Model '{wanted}' not found in Ollama. "
                    f"Install it with: ollama pull {wanted}. "
                    f"Installed: {sorted(available)}"
                )

    @property
    def name(self) -> str:
        return f"ollama/{self._gen_model}"

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            resp = requests.post(
                f"{self._host}/api/embed",
                json={"model": self._embed_model,
                      "input": list(texts[i:i + EMBED_BATCH])},
                timeout=EMBED_TIMEOUT_S)
            resp.raise_for_status()
            out.extend(resp.json()["embeddings"])
        return out

    def generate(self, prompt: str, temperature: float, top_p: float) -> str:
        resp = requests.post(
            f"{self._host}/api/chat",
            json={"model": self._gen_model,
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": prompt}],
                  "stream": False,
                  "options": {"temperature": temperature,
                              "top_p": top_p,
                              "num_ctx": NUM_CTX}},
            timeout=GEN_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()["message"]["content"] or ""
