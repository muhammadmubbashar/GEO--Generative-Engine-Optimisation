"""Three-stage probe: before retrieval -> after retrieval -> generation.

Builds each pool once (uses warm search/page cache), then generates.
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

from geo_bench.config import CONFIG
from geo_bench.evaluation import score_arm, summarise
from geo_bench.generation import Generator
from geo_bench.search import LiveRetriever

QUERIES = Path("queries/live10.csv")


def main() -> None:
    queries = list(csv.DictReader(QUERIES.open(encoding="utf-8")))

    print("=" * 64)
    print("STAGE 1 - BEFORE RETRIEVAL (queries only)")
    print("=" * 64)
    print(f"n_queries={len(queries)}  arm=baseline  variant=live")
    print(f"search_provider={CONFIG.search_provider}  "
          f"pool_k={CONFIG.search_results_per_query}")
    print(f"fanout_variants={CONFIG.fanout_variants}  "
          f"region={CONFIG.search_region}")
    print(f"gen_model={CONFIG.gen_model}  runs=1x1 (--once)")
    for row in queries:
        print(f"  {row['id']}: {row['query']}")

    print()
    print("=" * 64)
    print("STAGE 2 - AFTER RETRIEVAL (frozen search cache -> pool)")
    print("=" * 64)
    live = LiveRetriever(CONFIG, refresh=False)
    pools = []
    brand_counts: collections.Counter = collections.Counter()
    fc_ranks = []
    for row in queries:
        print(f"  retrieving {row['id']} ...", flush=True)
        pool = live.build_pool(row["query"])
        pools.append((row, pool))
        brand_counts.update(pool.retrieved_brands)
        if pool.fc_search_rank is not None:
            fc_ranks.append(pool.fc_search_rank)
        brands = dict(collections.Counter(pool.retrieved_brands))
        print(
            f"  {row['id']}: fc_present={pool.fc_present}  "
            f"fc_rank={pool.fc_search_rank}  "
            f"domains={pool.n_distinct_domains}  brands={brands}",
            flush=True,
        )

    n = len(pools)
    n_fc = sum(1 for _, p in pools if p.fc_present)
    print()
    print("COLLECTIVE RETRIEVAL")
    print(f"  FC in pool:     {n_fc}/{n} ({n_fc / n:.0%})")
    if fc_ranks:
        mid = sorted(fc_ranks)[len(fc_ranks) // 2]
        print(
            f"  FC best rank:   min={min(fc_ranks)} "
            f"median={mid} max={max(fc_ranks)}"
        )
    else:
        print("  FC best rank:   n/a")
    print(
        f"  Mean domains:   "
        f"{sum(p.n_distinct_domains for _, p in pools) / n:.1f}"
    )
    print(f"  Brand slots:    {dict(brand_counts)}")
    total_slots = sum(brand_counts.values()) or 1
    print(
        f"  Other share:    "
        f"{brand_counts.get('other', 0) / total_slots:.0%} of pool slots"
    )

    print()
    print("=" * 64)
    print("STAGE 3 - GENERATION (baseline live, 1 seed x 1 run)")
    print("=" * 64)
    generator = Generator(CONFIG)
    out_path = CONFIG.answers_path("baseline", "live")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for i, (row, pool) in enumerate(pools, 1):
            if not pool.passages:
                raise RuntimeError(f"empty pool for {row['id']}")
            print(f"  generating {row['id']} ({i}/{n}) ...", flush=True)
            rec = generator.run_once(
                row, pool.passages, arm="baseline", variant="live",
                seed=CONFIG.seeds[0], run=1)
            payload = rec.as_dict()
            payload.update(pool.meta_dict())
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"wrote {out_path}")

    ids = {r["id"] for r in queries}
    rows = [r for r in score_arm("baseline", "live") if r.get("query_id") in ids]

    print()
    print("PER-QUERY GENERATION")
    print(f"{'id':<6}{'fc_ret':>7}{'fc_inc':>7}{'cite%':>8}{'pawc':>8}  cited")
    for r in rows:
        cited = ",".join(r.get("cited_brands") or []) or "-"
        print(
            f"{r['query_id']:<6}"
            f"{r['retrieval_rate']:>7}"
            f"{r['inclusion']:>7}"
            f"{r['citation_share']:>8.0%}"
            f"{r['pawc']:>8.4f}  "
            f"{cited[:60]}"
        )

    print()
    print("COLLECTIVE GENERATION")
    for key, value in summarise(rows).items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
