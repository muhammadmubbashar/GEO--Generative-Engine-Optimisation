"""Versioned experiment transport: explicit sampling, full response provenance.

Provider defaults are an explicit design choice; no unsupported-parameter
fallback and no assertion that a shuffle seed seeds model sampling.
"""
import time
from datetime import datetime, timezone
from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError


class ObservedClient:
    def __init__(self, model):
        self.model = model
        self.client = OpenAI(max_retries=0, timeout=180.0)

    def generate(self, prompt):
        attempts = []
        for attempt in range(3):
            start = time.monotonic()
            timestamp = datetime.now(timezone.utc).isoformat()
            try:
                response = self.client.chat.completions.create(
                    model=self.model, messages=[{"role": "user", "content": prompt}],
                    store=False)
                elapsed = time.monotonic() - start
                attempts.append({"started_at": timestamp, "latency_s": elapsed,
                                 "status": "success"})
                if not response.choices:
                    raise RuntimeError("Provider returned no choice")
                return {"answer": response.choices[0].message.content or "",
                        "api": {"requested_model": self.model,
                                "returned_model": response.model,
                                "response_id": response.id,
                                "request_id": getattr(response, "_request_id", None),
                                "sampling": "provider_defaults; no API seed",
                                "finish_reason": response.choices[0].finish_reason,
                                "system_fingerprint": getattr(response, "system_fingerprint", None),
                                "usage": response.usage.model_dump() if response.usage else None,
                                "attempts": attempts,
                                "response": response.model_dump(mode="json")}}
            except (APIConnectionError, APITimeoutError, RateLimitError) as exc:
                attempts.append({"started_at": timestamp,
                                 "latency_s": time.monotonic()-start,
                                 "status": type(exc).__name__})
                if "insufficient_quota" in str(exc).lower() or attempt == 2:
                    raise
                time.sleep(2 ** attempt)
