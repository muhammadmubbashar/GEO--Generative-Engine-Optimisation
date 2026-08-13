"""Return the client the configuration asks for."""
from functools import lru_cache

from ..config import CONFIG, Config
from .base import LLMClient


@lru_cache(maxsize=4)
def get_client(cfg: Config = CONFIG) -> LLMClient:
    if cfg.mode == "openai":
        from .openai_client import OpenAIClient
        return OpenAIClient(cfg.gen_model, cfg.embed_model)
    if cfg.mode == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(cfg.gen_model, cfg.embed_model)
    if cfg.mode == "ollama":
        from .ollama_client import OllamaClient
        return OllamaClient(cfg.gen_model, cfg.embed_model, cfg.ollama_host)
    from .offline_client import OfflineClient
    return OfflineClient()
