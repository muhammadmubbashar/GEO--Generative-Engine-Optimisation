"""Analyse live baseline 1x1 — no local comparison."""
from __future__ import annotations

import json
from collections import Counter
from urllib.parse import urlsplit

from geo_bench.evaluation import score_arm, summarise
from geo_bench.evaluation.metrics import filter_rows


def host(url: str) -> str:
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def main() -> None:
    rows = score_arm("baseline", "live")
    ans = [
        json.loads(l)
        for l in open("results/answers_baseline_live.jsonl", encoding="utf-8")
    ]
    byid = {a["query_id"]: a for a in ans}

    print("=== COLLECTIVE (live baseline, 1x1, n=32) ===")
    for k, v in summarise(rows).items():
        print(f"{k}: {v}")

    print("\n=== BY STRATUM ===")
    for s in ("primary", "secondary"):
        fr = filter_rows(rows, stratum=s)
        if not fr:
            continue
        print(f"-- {s} n={len(fr)}")
        for k, v in summarise(fr).items():
            print(f"  {k}: {v}")

    print("\n=== PER QUERY ===")
    hdr = (
        f"{'id':<5}{'stratum':<10}{'cap':>4}{'anl':>4}{'rank':>5}"
        f"{'inc':>4}{'cite%':>7}{'pawc':>8}  cited"
    )
    print(hdr)
    for r in rows:
        a = byid[r["query_id"]]
        cited = ",".join(a.get("cited_brands") or []) or "-"
        rank = a.get("fc_search_rank")
        rank_s = "-" if rank is None else str(rank)
        print(
            f"{r['query_id']:<5}"
            f"{(r.get('stratum') or '')[:9]:<10}"
            f"{'Y' if a.get('fc_in_capture') else 'N':>4}"
            f"{'Y' if r['retrieval_rate'] else 'N':>4}"
            f"{rank_s:>5}"
            f"{r['inclusion']:>4}"
            f"{r['citation_share']:>7.0%}"
            f"{r['pawc']:>8.4f}  "
            f"{cited[:56]}"
        )

    never_cap, in_cap_not_anl, anl_not_cited, cited_ok = [], [], [], []
    for r in rows:
        a = byid[r["query_id"]]
        cap = bool(a.get("fc_in_capture"))
        anl = r["retrieval_rate"] == 1
        inc = r["inclusion"] == 1
        if not cap:
            never_cap.append(r["query_id"])
        elif not anl:
            in_cap_not_anl.append((r["query_id"], a.get("fc_search_rank")))
        elif not inc:
            anl_not_cited.append(
                (r["query_id"], a.get("fc_search_rank"),
                 a.get("fc_context_positions"))
            )
        else:
            cited_ok.append(
                (r["query_id"], a.get("fc_search_rank"),
                 r["citation_share"], r["pawc"])
            )

    print("\n=== FAILURE MODES (mutually exclusive) ===")
    print(f"A  never in Brave top-20:              {len(never_cap):2}  {never_cap}")
    print(f"B  in top-20 but outside analyse k=10: {len(in_cap_not_anl):2}  {in_cap_not_anl}")
    print(f"C  in analysis pool, NOT cited:        {len(anl_not_cited):2}  {anl_not_cited}")
    print(f"D  cited:                              {len(cited_ok):2}")
    for x in cited_ok:
        print(f"     {x[0]}  rank={x[1]}  cite_share={x[2]:.0%}  pawc={x[3]:.4f}")

    c = Counter()
    for a in ans:
        c.update(a.get("cited_brands") or [])
    print("\n=== CITED BRAND COUNTS ===")
    for brand, n in c.most_common():
        print(f"  {brand:<14} {n}")
    print(
        "answers with zero citations:",
        sum(1 for a in ans if not a.get("cited_brands")),
    )

    thin = 0
    words = []
    for a in ans:
        for i, brand in enumerate(a.get("retrieved_brands") or []):
            # passage words not in answer meta; skip
            pass
    # thin from generation docs if present
    from pathlib import Path
    run = Path("runs/20260810_live_baseline_live_9b573c71/generation/baseline")
    if run.exists():
        for p in sorted(run.glob("Q*_seed1_run01.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            for d in data.get("documents_used") or []:
                w = int(d.get("words") or 0)
                words.append((d.get("brand"), w, d.get("url")))
                if w < 50:
                    thin += 1
        print(f"\n=== PAGE DENSITY (analysis docs) ===")
        print(f"thin passages (<50w): {thin}/{len(words)}")
        by_b = Counter()
        thin_b = Counter()
        for b, w, _u in words:
            by_b[b] += 1
            if w < 50:
                thin_b[b] += 1
        for b in sorted(by_b):
            print(f"  {b:<14} slots={by_b[b]:3}  thin={thin_b[b]:3}  "
                  f"({thin_b[b]/by_b[b]:.0%})")

    dom = Counter()
    for a in ans:
        for u in a.get("retrieved_urls") or []:
            dom[host(u)] += 1
    print("\n=== TOP DOMAINS IN ANALYSIS POOLS ===")
    for d, n in dom.most_common(12):
        print(f"  {n:3}  {d}")


if __name__ == "__main__":
    main()
