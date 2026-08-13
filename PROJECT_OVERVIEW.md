# GEO Benchmark — Project Overview

## What is this project? (one paragraph)

When someone asks ChatGPT or Perplexity "I'm looking for flights from Melbourne
to London", the AI answers by reading a handful of web pages and citing them.
**Generative Engine Optimisation (GEO)** asks: *what can a brand change on its
website to get cited more often in those AI answers?* This project builds a
small, controlled copy of that whole process — a mini AI search engine — so we
can test GEO techniques (adding schema, FAQs, statistics, citations, keyword
stuffing) on **Flight Centre** pages and measure, with real numbers, whether
each technique helps, hurts, or does nothing.

## How it works (the pipeline)

1. **Collect** — download ~90 real flight pages from 4 brands (Flight Centre,
   Skyscanner, Webjet, Expedia) and freeze them (SHA-256 hashes) so every
   experiment runs on identical input.
2. **Clean** — strip navigation, footers, cookie banners; keep real content
   and JSON-LD structured data.
3. **Chunk + index** — split pages into ~350-word passages; all brands go
   into ONE shared pool per arm.
4. **Retrieve** — for each query, hybrid search (BM25 + embeddings) picks the
   **top 5** passages, **max 2 per brand** (Aggarwal-aligned top-5; forces
   ≥3 brands in context).
5. **Generate** — an LLM answers the query using those passages and must cite
   sources like [1], [2]. Reportable runs require `openai` or `anthropic`.
6. **Measure** — count how often Flight Centre is retrieved, cited, at what
   position, and its PAWC score (Aggarwal et al., KDD 2024 eq. 3).
7. **Compare arms** — repeat with modified Flight Centre pages (one technique
   at a time, competitors never change).

## Query design

| File | Count | Role |
|---|---|---|
| `queries/queries.csv` | **32** | **Primary Q01–Q22** (flight consideration) + **Secondary Q23–Q32** (agent-value / trust) |
| `queries/heldout.csv` | **7** | Paraphrases + advice — run after arms lock (`geo run … --heldout`) |

**Pre-registered primary family** (confirmatory; Holm across arms only here):
`primary_stratum=primary`, `primary_metric=pawc`, `primary_variant=reindexed`
(see `geo_bench/config.py`). All other tables are exploratory.

Monopoly-of-coverage (only one brand in the candidate set) is flagged per
answer and summarised via `geo monopoly` — that is a coverage win, not a
Type-B content contest.

## What each folder does

| Folder | What it does |
|---|---|
| `corpus/baseline/<brand>/` | Frozen HTML pages — the mini-web. |
| `corpus/manifest_baseline.csv` | Freeze record: URL, fetch date, hash. |
| `queries/queries.csv` | 32 client queries (primary + secondary). |
| `queries/heldout.csv` | 7 held-out paraphrases / advice queries. |
| `queries/urls.csv` | Collected pages, page types, NONE absences. |
| `geo_bench/config.py` | Every experimental setting + primary family. |
| `results/_demo/` | Offline/ollama smoke outputs — **not** deliverables. |
| `results/` | Indexes and reportable answers/scores only. |

## Controls (must all pass)

T1 determinism · T2 fairness · **T3 isolation** (competitor passage IDs
unchanged, FC IDs change, competitor-only BM25 ranks stable on probes) ·
T4 reproducibility.

`fixed` variant swaps FC text by **file + chunk ordinal**, not list position;
mismatch fails loudly if interventions shift chunk boundaries.

## Current status and next steps

- Offline/ollama results are demo-only (`--allow-demo` → `results/_demo/`).
- Switch `mode` in `config.py` to `"openai"` or `"anthropic"`, then:
  `geo controls` → `geo all baseline` → intervention arms.
- Pending: 2 Expedia pages (Brisbane, Perth) still listed to save manually.

## Command cheat-sheet

```
geo coverage
geo verify
geo index baseline
geo controls
geo all baseline                    # requires reportable mode
geo run baseline --allow-demo       # smoke only → results/_demo/
geo quarantine-demo                 # move old offline files out of results/
geo stats                           # defaults to primary family
geo stats --stratum secondary       # exploratory
geo monopoly baseline --variant reindexed
geo run baseline --heldout          # after arms locked
```
