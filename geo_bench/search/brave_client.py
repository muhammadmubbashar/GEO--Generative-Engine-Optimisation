"""Brave Search API client.

Key from BRAVE_API_KEY environment variable only — never from a file.
"""
from __future__ import annotations

import os
import time
from typing import List

import requests

from .base import SearchClient, SearchResult

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_RETRIES = 5


class BraveClient(SearchClient):
    def __init__(self) -> None:
        key = os.environ.get("BRAVE_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "BRAVE_API_KEY is not set. Export it in the shell before "
                "running the live retrieval layer "
                "(e.g. $env:BRAVE_API_KEY = '...' on PowerShell)."
            )
        self._key = key

    @property
    def name(self) -> str:
        return "brave"

    def search(self, query: str, count: int, region: str,
               language: str) -> List[SearchResult]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._key,
        }
        # Brave uses country codes; AU market + English.
        params = {
            "q": query,
            "count": min(count, 20),
            "country": region.upper(),
            "search_lang": language.lower(),
            "text_decorations": 0,
            "spellcheck": 1,
        }
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(BRAVE_URL, headers=headers, params=params,
                                    timeout=45)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  [brave] rate limited; backoff {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Brave search failed HTTP {resp.status_code}: "
                        f"{resp.text[:300]}")
                data = resp.json()
                web = (data.get("web") or {}).get("results") or []
                if not web:
                    raise RuntimeError(
                        f"Brave returned zero web results for query={query!r}. "
                        "Refusing empty pool.")
                out: List[SearchResult] = []
                for i, item in enumerate(web[:count], 1):
                    url = (item.get("url") or "").strip()
                    if not url:
                        continue
                    out.append(SearchResult(
                        url=url,
                        title=(item.get("title") or "").strip(),
                        snippet=(item.get("description") or "").strip(),
                        rank=i,
                        source_query=query,
                    ))
                if not out:
                    raise RuntimeError(
                        f"Brave results had no usable URLs for query={query!r}.")
                return out
            except (requests.RequestException, RuntimeError) as exc:
                last_err = exc
                wait = 2 ** attempt
                print(f"  [brave] attempt {attempt + 1}/{MAX_RETRIES} failed: "
                      f"{exc}; retry in {wait}s")
                time.sleep(wait)
        raise RuntimeError(
            f"Brave search failed after {MAX_RETRIES} attempts for "
            f"query={query!r}: {last_err}")
