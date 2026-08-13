"""One-query end-to-end smoke test for the Ollama provider.

Retrieves for a single real query against the baseline index, generates one
answer with the configured local model, and prints what was retrieved and
cited. Verifies the plumbing without the cost of a full `geo run`.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo_bench.config import CONFIG
from geo_bench.generation import Generator
from geo_bench.retrieval import Retriever, load_index

QUERY = {"id": "SMOKE", "query": "flights from melbourne to london", "group": "smoke"}


def main() -> None:
    print(f"mode={CONFIG.mode}  gen={CONFIG.gen_model}  embed={CONFIG.embed_model}\n")

    t0 = time.time()
    retriever = Retriever(load_index("baseline", CONFIG), CONFIG)
    retrieved = retriever.retrieve(QUERY["query"])
    print(f"Retrieved {len(retrieved)} passages in {time.time() - t0:.1f}s:")
    for i, p in enumerate(retrieved, 1):
        print(f"  [{i}] {p.brand:<14} {p.text[:70]!r}")

    t0 = time.time()
    rec = Generator(CONFIG).run_once(QUERY, retrieved, arm="baseline",
                                     variant="reindexed", seed=1, run=1)
    print(f"\nGenerated in {time.time() - t0:.1f}s  (model recorded: {rec.model})")
    print(f"FC context positions: {rec.fc_context_positions}")
    print(f"Cited indices: {rec.cited_indices}")
    print(f"Cited brands:  {rec.cited_brands}")
    print("\n--- ANSWER " + "-" * 47)
    print(rec.answer)


if __name__ == "__main__":
    main()
