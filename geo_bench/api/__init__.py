"""LLM provider abstraction.

Every external model call goes through this package, so no other module
imports a vendor SDK directly. Two consequences:

1. The pipeline runs offline with no API key — the team can test the plumbing
   and demo the system for free.
2. Swapping provider is a config change, not a refactor. The original study
   used gpt-3.5-turbo, now obsolete; this is not a hypothetical need.
"""
from .base import LLMClient, Passage
from .factory import get_client

__all__ = ["LLMClient", "Passage", "get_client"]
