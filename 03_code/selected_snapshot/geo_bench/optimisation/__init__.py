"""Flight Centre page optimisation — content arms against the locked freeze.

Only Flight Centre documents are modified. Competitor freeze bytes stay
identical. Candidate facts are extracted from freeze pages; the verifier
accepts only rows with status=verified.
"""
from .base import Arm, FrozenPage, OptimisedPage
from .facts import FactTable
from .builder import extract_facts, optimise_arm

__all__ = [
    "Arm", "FrozenPage", "OptimisedPage", "FactTable",
    "extract_facts", "optimise_arm",
]
