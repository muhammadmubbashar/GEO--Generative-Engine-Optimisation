"""On-disk freeze for live search responses and fetched pages.

Without this cache every re-run pulls a different web and no result is
reproducible. It plays the role the frozen corpus plays in the local layer.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import CONFIG, Config


def _hash_key(*parts: str) -> str:
    blob = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


class SearchCache:
    def __init__(self, cfg: Config = CONFIG, refresh: bool = False):
        self.cfg = cfg
        self.refresh = refresh
        self.search_dir = Path(cfg.search_cache_dir)
        self.page_dir = Path(cfg.fetch_cache_dir)
        self.fanout_dir = Path(cfg.fanout_cache_dir)
        for d in (self.search_dir, self.page_dir, self.fanout_dir):
            d.mkdir(parents=True, exist_ok=True)
        if refresh:
            print("WARNING: --refresh set — bypassing live-search cache "
                  "(results will NOT match a prior freeze).")

    # ---- search responses ---------------------------------------------
    def search_path(self, query: str, provider: str, region: str,
                    count: int) -> Path:
        key = _hash_key(query, provider, region, str(count))
        return self.search_dir / f"{key}.json"

    def get_search(self, query: str, provider: str, region: str,
                   count: int) -> Optional[Dict[str, Any]]:
        if self.refresh:
            return None
        path = self.search_path(query, provider, region, count)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put_search(self, query: str, provider: str, region: str, count: int,
                   results: list) -> Dict[str, Any]:
        payload = {
            "query": query,
            "provider": provider,
            "region": region,
            "count": count,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "results": results,
        }
        path = self.search_path(query, provider, region, count)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return payload

    # ---- fetched pages ------------------------------------------------
    def page_path(self, url: str) -> Path:
        key = _hash_key(url)
        return self.page_dir / f"{key}.json"

    def get_page(self, url: str) -> Optional[Dict[str, Any]]:
        if self.refresh:
            return None
        path = self.page_path(url)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put_page(self, url: str, html: str, status: int,
                 method: str = "script",
                 fetch_user_agent: str = "") -> Dict[str, Any]:
        payload = {
            "url": url,
            "http_status": status,
            "method": method,
            "fetch_user_agent": fetch_user_agent,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "html": html,
        }
        path = self.page_path(url)
        path.write_text(json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8")
        return payload

    # ---- fan-out paraphrases ------------------------------------------
    def fanout_path(self, query: str, n: int, model: str) -> Path:
        key = _hash_key(query, str(n), model)
        return self.fanout_dir / f"{key}.json"

    def get_fanout(self, query: str, n: int, model: str) -> Optional[list]:
        if self.refresh:
            return None
        path = self.fanout_path(query, n, model)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("variants")

    def put_fanout(self, query: str, n: int, model: str,
                   variants: list) -> Path:
        payload = {
            "query": query,
            "n": n,
            "model": model,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "variants": variants,
        }
        path = self.fanout_path(query, n, model)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path
