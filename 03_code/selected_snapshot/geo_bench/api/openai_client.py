"""OpenAI-backed provider — the real experiment."""
import queue
import threading
import time
from typing import List, Sequence

from .base import LLMClient

# Without an explicit per-request timeout, a stalled connection blocks
# indefinitely instead of raising APITimeoutError into _retry's backoff loop
# (this is what geo_bench/optimisation/llm.py already does for the
# optimisation-arm LLM calls; generate()/embed() here had none, and a single
# stuck reindexed-generation request silently hung a multi-hour regeneration
# run). `fixed` prompts are much larger (page_prompt_chars, up to 24k chars)
# than `reindexed` chunks, so it gets a longer budget.
_REINDEXED_TIMEOUT_S = 60.0
_FIXED_TIMEOUT_S = 120.0
_EMBED_TIMEOUT_S = 60.0


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

    def _retry(self, fn, *, attempts: int = 10, wall_clock_s: float = 0.0):
        """Retry with backoff. `wall_clock_s`, if set, is a hard deadline

        enforced independently of whatever timeout `fn` itself passed to the
        SDK — observed in production: a `timeout=` kwarg on .create() did
        not bound a stuck request (the connection sat completely silent, no
        retry/error, for 35+ minutes on one call during a real regeneration
        run), so this can't rely on the SDK's own timeout alone.

        `fn` runs on a daemon `threading.Thread`, not
        `concurrent.futures.ThreadPoolExecutor`: the executor's module-level
        atexit hook joins every worker thread it ever created before the
        interpreter is allowed to exit, so one abandoned hung call would
        make the whole process un-killable at shutdown even after the retry
        loop itself had moved on and finished everything else. A daemon
        thread is simply dropped, unjoined, at interpreter exit.
        """
        from openai import APIConnectionError, APITimeoutError, RateLimitError
        last = None
        for i in range(attempts):
            try:
                if wall_clock_s > 0:
                    q: queue.Queue = queue.Queue(maxsize=1)

                    def _worker(fn=fn, q=q):
                        try:
                            q.put(("ok", fn()))
                        except BaseException as exc:  # noqa: BLE001
                            q.put(("err", exc))

                    threading.Thread(target=_worker, daemon=True).start()
                    try:
                        kind, payload = q.get(timeout=wall_clock_s)
                    except queue.Empty:
                        raise TimeoutError(
                            f"wall-clock timeout after {wall_clock_s:.0f}s "
                            "(SDK-level timeout did not fire)"
                        ) from None
                    if kind == "err":
                        raise payload
                    return payload
                return fn()
            except (RateLimitError, APITimeoutError, APIConnectionError,
                    TimeoutError) as exc:
                # Quota/billing exhaustion will never recover with backoff.
                msg = str(exc).lower()
                if "insufficient_quota" in msg or "credit_balance_exhausted" in msg:
                    raise
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
            resp = self._retry(
                lambda b=batch: self._client.embeddings.create(
                    model=self._embed_model, input=b, timeout=_EMBED_TIMEOUT_S),
                wall_clock_s=_EMBED_TIMEOUT_S + 30.0)
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
        # No variant flag reaches this interface; a full `fixed` page prompt
        # (up to page_prompt_chars=24000) is the only case this long, so
        # length alone distinguishes it from a `reindexed` chunk prompt.
        timeout = _FIXED_TIMEOUT_S if len(prompt) > 8000 else _REINDEXED_TIMEOUT_S

        def _call(use_sampling: bool):
            if use_sampling:
                return self._client.chat.completions.create(
                    model=self._gen_model, temperature=temperature, top_p=top_p,
                    messages=messages, timeout=timeout)
            return self._client.chat.completions.create(
                model=self._gen_model, messages=messages, timeout=timeout)

        def _once():
            try:
                return _call(True)
            except BadRequestError as exc:
                msg = str(exc).lower()
                if "temperature" not in msg and "top_p" not in msg:
                    raise
                return _call(False)

        resp = self._retry(_once, wall_clock_s=timeout + 30.0)
        return resp.choices[0].message.content or ""
