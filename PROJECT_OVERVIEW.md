# GEO Benchmark — Project Overview

## What is this project? (one paragraph)

When someone asks ChatGPT or Perplexity "I'm looking for flights from Melbourne
to London", the AI answers by reading a handful of web pages and citing them.
**Generative Engine Optimisation (GEO)** asks: *what can a brand change on its
website to get cited more often in those AI answers?* This project freezes a
real Brave AU search snapshot, runs a controlled retrieve→generate engine on
that freeze, and (next) edits **only Flight Centre** text so we can measure
whether exposing browser-visible/SSR content, schema, FAQs, statistics,
citations, or keyword stuffing change citations — with numbers, against a
fixed competitor field.

## How it works (the pipeline)

1. **Freeze** — Brave AU, fan-out ×3, capture 20 / analyse 10, fetch + QC into
   `runs/<RUN_ID>/`. Thin / 429 → exact-URL Common Crawl (logged).
2. **Verify + lock** — re-hash pages; write `protocol_lock.json`.
3. **Route** — FC Brave rank → `top10` / `rank11-20` / `absent`. Sets `fixed`
   eligibility. Every query runs `reindexed`.
4. **Index** — 350-word passages (40 overlap, max 12k chars); hybrid BM25 +
   `text-embedding-3-small` over **all freeze pages** (study brands + `other`).
5. **Retrieve `fixed`** — frozen Brave analysis-pool **full pages**; FC text may
   be swapped later by URL.
6. **Retrieve `reindexed`** — RRF top-5, max 2 per brand, from the freeze index
   (350-word chunks).
7. **Select** — frozen title+snippet gatekeeper (≤5 opens), 2×5. Third stage.
8. **Generate** — Aggarwal Listing 1 prompt; 2 seeds × 5 runs; citations `[n]`.
9. **Score** — counted metrics + PAWC + brand-masked judge (relevance 0–2,
   response quality 0–10).
10. **Compare arms** (not started) — one FC technique at a time; competitors
    never change. Holm within pre-registered endpoint families.

The old four-brand sitemap corpus is **retired**. The freeze is the corpus.

## Query design

| File | Count | Role |
|---|---|---|
| `queries/queries.csv` | **50** | Q01–Q32 original + Q33–Q50 expansion (primary flights-consideration) |
| `queries/heldout.csv` | **7** | Paraphrases + advice — `--heldout --final` after arms lock only |

**Pre-registered confirmatory family:** stratum `primary`, variant `reindexed`,
endpoints PAWC + citation share (Holm across arms). Secondary family:
relevance, response quality, inclusion, retrieval rank. Do not pool secondary
into primary. Do not treat `fixed` vs `reindexed` as a treatment effect.

## What each folder does

| Path | What it does |
|---|---|
| `runs/<RUN_ID>/` | Freeze: search JSON, pages, hashes, lock, generation |
| `results/` | Index, answers, scores, routing, QC, calibration CSVs |
| `queries/` | 50 main + 7 held-out + live10 smoke |
| `geo_bench/config.py` | Every experimental setting + endpoint families |
| `SCORING_RUBRICS.md` | Frozen judge rubric v1.0 |
| `BASELINE_LOCK.md` | Sign-off before optimisation |
| `decisions_log.md` | Dated parameter / freeze decisions |
| `results/_demo/` | Offline/ollama smoke — **not** deliverables |

## Controls (must all pass)

T1 determinism · T2 fairness (non-FC freeze hashes) · T3 isolation (FC marker:
competitor IDs unchanged, FC IDs change, competitor-only BM25 ranks stable) ·
T4 reproducibility.

`fixed` swaps FC text by **URL + chunk ordinal**; mismatch fails loudly.

## Current status

**Full report:** `FULL_REPORT.md`

**Baseline locked** on freeze `20260815_live_baseline_fixed_9b573c71`
(50 queries, 2×5). Three stages: selection **23%** opened when listed;
reindexed cited **9%**; fixed whole-page cited **38%**. Optimisation has
**not** started.

**Next:** human κ on the 60-row calibration CSVs, then optimisation arms
(`position_control` then `ssr_visible` first), same freeze, same variants,
Holm vs baseline. `ssr_visible` = FC-only browser-visible text; baseline
stays no-JS.

## Command cheat-sheet

```
geo verify --from-run <RUN_ID>
geo qc --from-run <RUN_ID>
geo lock --from-run <RUN_ID>
geo route --from-run <RUN_ID>
geo index baseline --from-run <RUN_ID>
geo controls --from-run <RUN_ID>
geo run baseline --variant reindexed --from-run <RUN_ID>
geo run baseline --variant fixed --from-run <RUN_ID>
geo score baseline --variant reindexed --judge
geo stats
geo monopoly baseline --variant reindexed
geo calibrate baseline --variant reindexed
geo kappa results/calibration_sample_baseline_reindexed.csv
geo run baseline --heldout --final --from-run <RUN_ID>   # end of study only
```
