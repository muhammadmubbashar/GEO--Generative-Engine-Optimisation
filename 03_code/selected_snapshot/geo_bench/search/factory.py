"""Select a search provider from config."""
from functools import lru_cache

from ..config import CONFIG, Config
from .base import SearchClient


@lru_cache(maxsize=4)
def get_search_client(cfg: Config = CONFIG) -> SearchClient:
    provider = cfg.search_provider.lower().strip()
    if provider == "brave":
        from .brave_client import BraveClient
        return BraveClient()
    if provider == "serper":
        raise NotImplementedError(
            "serper_client not implemented yet; set search_provider='brave'")
    if provider == "tavily":
        raise NotImplementedError(
            "tavily_client not implemented yet; set search_provider='brave'")
    raise ValueError(f"unknown search_provider={provider!r}")
