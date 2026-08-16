"""Turn frozen pages into a searchable pool, and retrieve from it.

    parser      HTML -> clean text (keeps JSON-LD, since schema is under test)
    chunker     text -> overlapping passages with content-hash IDs
    index       passages -> dense vectors + BM25, in ONE shared pool
    retriever   hybrid retrieval with a per-brand cap

FAIRNESS RULE ENFORCED HERE: identical processing for every brand, and a
single shared index. Flight Centre never gets a private pool — it competes
passage-for-passage, as it would in a real answer engine.
"""
from .index import Index, build_index, load_index, passages_from_store
from .retriever import Retriever

__all__ = ["Index", "build_index", "load_index", "passages_from_store",
           "Retriever"]
