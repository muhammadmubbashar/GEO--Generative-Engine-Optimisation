# geo_bench — Controlled Benchmark for Generative Engine Optimisation

**Flight Centre Travel Group × QUT Capstone Team 62 · IFN735 / IFN736**  
**Package:** `geo-bench-fc` v0.1.0 · Python ≥ 3.10 · MIT License

Does changing a travel brand’s web content measurably alter how often an AI
answer engine retrieves and cites it?

> **BASELINE v2 LOCKED** — freeze `20260815_live_baseline_fixed_9b573c71`
> (50 queries), protocol `2026-08-14T22:00:03Z`, 2×5 generation + selection +
> judge complete. v1 answers archived in `results/_archive_v1_pre_audit/`.
> Do **not** recapture Brave or change `config.py` without a
> `decisions_log.md` entry and a new lock. Optimisation arms have **not**
> started. See `BASELINE_LOCK.md`.

---

## 1. The problem

People increasingly ask AI assistants travel questions instead of using search
engines. Those systems retrieve a handful of web pages, synthesise an answer,
and cite a few sources. Flight Centre is rarely one of them; competitors are.

Semester 1 diagnosed why. Semester 2 measures what fixing it is worth.

## 2. Why a controlled environment, not live ChatGPT

Flight Centre’s pages cannot be substituted inside a live AI engine — it reads
the public web. Without a substitution there is no before-and-after, so no
difference can be attributed to our change rather than to something a
competitor did that week. Live platforms are also non-deterministic,
personalised, and change without notice.

We therefore freeze a real search snapshot (Brave AU), fetch and clean those
pages, and run a working copy of an AI answer engine on that freeze. Flight
Centre text can then be swapped or re-indexed without the open web moving
underneath us.

**We claim relative citation under this retrieval + generation stack**, not
absolute visibility on any live platform. Deliverable “what to fund first”
means **priority candidates for a live pilot**, not a guaranteed production lift.

---

## 3. Two kinds of finding

| | Type A — Access & infrastructure | Type B — Content & structure |
|---|---|---|
| Question | Can the AI reach, fetch and read the page at all? | Once it is a candidate beside rivals, is the content good enough to be cited? |
| Examples | search rank, robots.txt, client-side rendering, page speed, sitemap, MCP | entity density, JSON-LD, FAQ, authority signals |
| Who can act | Mostly **Flight Centre only**. **CSR/SSR is testable here** as arm `ssr_visible` (FC-only visible text; Brave rank still frozen). Search rank itself is not. | **Testable here**, with measured evidence |

Type A remains the higher commercial priority: it is a gate. Interaction
between Type A and Type B (good content partially compensating for marginal
crawlability) is reported as an open question.

**Baseline evidence already shows both types.** On the Brave freeze, Flight
Centre is often absent from the top-20, especially on secondary “why use an
agent” queries (Type A). When FC is forced into the analysis pool (`fixed`),
it is usually cited — but still shares the conversation with `other` domains
(Type B / coverage).

---

## 4. Literature position

| Paper | Finding |
|---|---|
| Aggarwal et al., **GEO**, SIGKDD 2024 · arXiv:2311.09735 | Content optimisation raises visibility by up to 40% |
| Puerto et al., **C-SEO Bench**, NeurIPS 2025 D&B · arXiv:2506.11097 | Most methods largely ineffective; retrieval rank ≈ 7.6× more influential |
| Wu et al., **AutoGEO**, ICLR 2026 | Extends methods with accuracy-preservation constraint |

**Our contribution.** Neither benchmark evaluates HTML structure. No prior work
tests a single commercial brand against its real competitors using the brand’s
own customer queries. A null result is publishable: it corroborates NeurIPS
in a new domain.

---

## 5. What we replicate, adapt and add

**Adopted from Aggarwal et al.** Two-step retrieve→generate engine · 5 answers
× seeds · temperature 0.7, top_p 1 · their Listing 1 prompt · one source
optimised at a time · methods alone before combination.

**Adapted**

| Element | Theirs | Ours | Why |
|---|---|---|---|
| Source acquisition | Google top-5, live | **Brave AU freeze** (capture 20 / analyse 10) | Real-web gate; dated, reproducible pool |
| Candidates (`fixed`) | 5 whole pages | Frozen analysis-pool docs; **cleaned full page** per URL (cap 24k chars) | Aggarwal / C-SEO / AutoGEO generation effect |
| Candidates (`reindexed`) | 5 | Hybrid BM25 + dense over **all freeze pages**, **top-5**, **max 2 per brand** | Full effect including retrieval |
| Granularity | Whole page | **`fixed`: whole page. `reindexed`: 350-word chunks (40 overlap)** | Papers measure rewrites on full docs; real engines also retrieve passages |
| Fact grounding | Invented stats allowed | **Verified facts only** | Client ethics; **conservative vs adversarial GEO** |
| Metrics | PAWC + subjective | Counted metrics **+ PAWC** + judged relevance / quality | Reproducibility + comparability |

**Added.** `schema_only` / `faq_structure_only` · passage shuffle ·
`position_control` · coverage-gap + monopoly reporting · `fixed` text swap by
**file identity** (one source per URL) · T3 rank-isolation control · Common Crawl exact-URL
fallback for thin / 429 pages · query fan-out (3 variants) · FC position
routing · freeze QC + protocol lock · brand-masked judged metrics
(`SCORING_RUBRICS.md`).

PAWC uses the same *formula* as Aggarwal. On `fixed` the document unit is the
**whole page** (paper-comparable). On `reindexed` it remains a passage.
Position decay is inherited from the paper, not independently validated. Client
scorecards lead with counted metrics.

---

## 6. Status snapshot (what is done vs not done)

### Done

| Workstream | Status |
|---|---|
| Query set | **50** client prompts (Q01–Q50) + **7** held-out |
| Brand field | Flight Centre · Skyscanner · Webjet · Expedia (AU market) |
| Live retrieval layer | Brave AU, fan-out ×3, capture 20 / analyse 10, freeze into `runs/` |
| Archive fallback | Exact-URL Common Crawl when live fetch is thin / 429 (logged) |
| Freeze QC + routing | Usable-content QC; FC position → `fixed` vs `reindexed` eligibility |
| Protocol lock | `protocol_lock.json` hashed on the freeze |
| Cleaning + chunking + hybrid index | BM25 + `text-embedding-3-small`, RRF, cap 2, top-5 · over freeze pages |
| Control tests T1–T4 | **All passed** on this freeze (`geo controls`) |
| Generation stack | Aggarwal Listing 1 prompt · OpenAI / Anthropic / Ollama / offline |
| Judged metrics | Relevance (0–2) + RQ (0–10); brand-masked; rubric v1.0; **800 answers scored** |
| Human calibration export | 60-row CSVs ready (`results/calibration_sample_*.csv`) — graders not yet filled |
| **Baseline `reindexed`** | 50 queries, **2×5**, judged, freeze `20260815_live_baseline_fixed_9b573c71` |
| **Baseline `fixed`** | 30 eligible queries, **2×5**, judged, same freeze |
| **Selection** | 50 queries, **2×5**, frozen capture-20 title+snippet gatekeeper |

### Not done yet (optimisation phase — do not start until `BASELINE_LOCK.md` is signed)

- Human κ (two independent graders fill the calibration CSVs, then `geo kappa`)
- Intervention pages (`ssr_visible`, `position_control`, `schema_only`,
  `faq_structure_only`, `statistics_addition`, `cite_sources`,
  `keyword_stuffing`, `full_stack`)
- Arm runs on the **same freeze** (fixed + reindexed, 2×5 + judge)
- `geo stats` Holm families; held-out `--final` only at the end

---

## 7. Design parameters

| Parameter | Value |
|---|---|
| Product line | Flights |
| Queries | **50** in `queries/queries.csv` (Q01–Q50) · **7** in `queries/heldout.csv` |
| Brands | Flight Centre · Skyscanner · Webjet · Expedia |
| Chunking | `reindexed` only: 350 words, 40 overlap, content-hash IDs |
| Search freeze | Brave, region AU, language en, fan-out **3**, capture **20**, analyse **10** |
| `reindexed` retrieval | BM25 + dense over all freeze pages, RRF k=60, **top-5**, **max 2 per brand** |
| `fixed` retrieval | Frozen analysis-pool **full pages**; FC text swapped by URL |
| Generation | **2 seeds × 5 runs**, temperature 0.7, shuffled passages |
| Model (reportable) | `gpt-5.6-luna` + embeddings `text-embedding-3-small` |
| Reportable modes | **`openai` / `anthropic` only** (offline/ollama → `results/_demo/`) |
| Judge | same model, temperature **0**, rubric `SCORING_RUBRICS.md` v1.0 |
| Statistics | Per-query Wilcoxon · bootstrap 95% CIs · Holm within endpoint families |

### Pre-registered endpoint families

Confirmatory inference is locked to stratum `primary` (Q01–Q22), variant
`reindexed`:

| Family | Endpoints | Holm |
|---|---|---|
| **Primary** | `pawc`, `citation_share` | Across arms × these endpoints |
| **Secondary** | `relevance`, `response_quality`, `inclusion`, `retrieval_rank` | Separate family |

Other metric × variant × stratum tables are **exploratory** and must be labelled
as such (`geo stats` prints `family=primary|exploratory`).

### Arms (planned; only `baseline` exists on disk)

`baseline` · `ssr_visible` · `position_control` · `schema_only` ·
`faq_structure_only` · `statistics_addition` · `cite_sources` ·
`keyword_stuffing` · `full_stack`

| Arm | Role |
|---|---|
| `baseline` | Unmodified freeze pages (**no JS** — crawler/bot HTML) |
| `ssr_visible` | **Type A.** FC-only: same URLs, browser-rendered / prerender text so the engine sees what a human sees. Competitors stay freeze bytes. Does **not** recapture Brave. |
| `position_control` | Force one FC passage to context position 1; no text edit (C-SEO rank check) |
| `schema_only` | JSON-LD / structured data only — **our contribution, untested by prior papers** |
| `faq_structure_only` | FAQ markup / Q&A structure only — **our contribution** |
| `statistics_addition` | Aggarwal method, **verified facts only** |
| `cite_sources` | Aggarwal method, real sources only |
| `keyword_stuffing` | Negative control (both papers report failure) |
| `full_stack` | Combination after singles |

### Two retrieval variants

`--variant live` is retired. Freeze is upstream; experiments use:

| Variant | Behaviour | Purpose |
|---|---|---|
| `fixed` | Frozen analysis-pool **full pages**; FC text swapped by URL | Aggarwal / C-SEO / AutoGEO generation effect |
| `reindexed` | Index rebuilt over all freeze pages per arm | Full effect including retrieval |

Difference ≈ retrieval contribution (the disputed quantity). Report
`Δ_reindexed − Δ_fixed` only after fixed swap identity checks pass.

**Routing.** Every query is eligible for `reindexed`. `fixed` requires FC in
the Brave analysis top-10 **and** usable page text. Queries where FC is absent
or only ranks 11–20 are Type A and are skipped for `fixed`, not silently
imputed.

### Selection stage (`geo select`) — engine-realistic gatekeeper

Real engines (documented for ChatGPT Search) read the SERP metadata and
decide which pages to open before any content is read. `geo select` replays
that decision over the **frozen** capture-20 rows (title + snippet exactly as
captured — zero live traffic): the LLM picks ≤5 results it would open, 2×5
per query. Measured: `P(FC selected | FC in capture)` and FC's rank within
the picks (`results/selection_baseline.csv`). Future arms can swap FC's
title/snippet (meta-description rewriting, a Type-B intervention) and measure
the selection delta. Baseline-only until such arms exist.

---

## 8. Methods — how the pipeline works

1. **Freeze** — fan-out query → Brave AU → capture 20 → fetch/clean → analyse
   10 → **full cleaned page** per analysis URL. Thin / 429 pages: exact-URL Common Crawl
   (logged as a dated confound).
2. **Verify** — re-hash freeze pages; fail on mismatch.
3. **QC** — flag usable vs thin / bot-walled / unobtainable. Do not auto-exclude;
   record and report. Human review before results are seen.
4. **Lock** — write `protocol_lock.json` (model, depths, seeds, endpoints, …).
5. **Route** — FC search rank → `top10` / `rank11-20` / `absent`; sets `fixed`
   eligibility.
6. **Index** — 350-word passages, 40 overlap; hybrid BM25 + dense over the
   freeze pool (**`reindexed` only**).
7. **Retrieve (`reindexed`)** — RRF, top-5, cap 2 per brand.
8. **Retrieve (`fixed`)** — frozen analysis-pool **pages**; FC text may be
   substituted after freeze.
9. **Generate** — Aggarwal Listing 1 prompt; every sentence must cite `[n]`;
   sources shuffled per seed; `position_control` forces FC first.
   `fixed` budget `page_prompt_chars`; `reindexed` budget `passage_prompt_chars`.
10. **Score** — counted metrics + PAWC (eq. 3) + monopoly / capture covariates
    + optional judged relevance / response quality (brand-masked).
11. **Compare** — per-query means, two-sided Wilcoxon, bootstrap 95% CI, Holm
    within each endpoint family.

### Metrics

**Counted:** retrieval rate · inclusion · citation position · citation share ·
`monopoly_retrieval` (single-brand candidate set)

**Paper:** PAWC (Aggarwal eq. 3). Words in sentences citing FC, discounted
`exp(-pos / |S|)`, co-citation mass split equally (duplicate indices deduped
before split).

**Covariate:** mean FC context position (C-SEO: rank dominates content).

**Freeze extras:** `fc_in_capture` (top-20), `fc_search_rank`,
`P(cited | retrieved)`, `P(cited | top-3)`, brands usable vs missing (bot-wall).

**Judged** (`SCORING_RUBRICS.md` v1.0, brand-masked):

- **Relevance** 0 / 1 / 2 — does the answer address what was asked?
- **Response quality** 0–10 — weighted accuracy 40% · completeness 30% ·
  clarity 20% · attribution 10%

### Control tests

| Test | Proves |
|---|---|
| T1 Determinism | Repeat retrieval → identical passages |
| T2 Fairness | Competitor freeze pages byte-identical across arms |
| T3 Isolation | FC marker: competitor **IDs** unchanged, FC IDs change, competitor **ranks** stable on probes |
| T4 Reproducibility | Rebuild freeze chunks → identical passage IDs |

### Freeze QC fetch methods

`browser-ua` · `manual-view-source` · `common-crawl` · `bot-walled` ·
`unobtainable`

Usable text requires ≥ 200 cleaned words and a non-blocked method. Pages under
the floor are flagged (`needs_review`), not auto-dropped. A query with fewer
than 5 usable docs is flagged `low_usable`.

---

## 9. Queries

All primary/secondary prompts come from the **FCAU client prompt list**.

| File | Count | Role |
|---|---|---|
| `queries/queries.csv` | 50 | Q01–Q22 + Q33–Q50 primary flights; Q23–Q32 agent-value / trust / insurance / hard route |
| `queries/heldout.csv` | 7 | Paraphrases + advice (H01–H07) — run after arms lock |
| `queries/live10.csv` | 10 | Smoke subset of Q01–Q10 for live-pool probes |

**Primary (Q01–Q22, Q33–Q50)** — e.g. “i’m looking for flights from melbourne to london”,
business class, multi-city, RTW, premium economy, Australia→Japan / Bali / Europe,
plus 18 expansion routes (Singapore, Auckland, Fiji, India, domestic hubs, first class).

**Secondary (Q23–Q32)** — “Why consult a travel professional…”, visas, luxury
agent, Europe insurance, Canberra→Hong Kong. These stress **coverage**, not a
fair Type-B content contest, and must be reported separately (`geo monopoly`,
`--stratum secondary`).

---

## 10. Brave freeze (baseline)

**Run id (v2, study corpus):** `20260815_live_baseline_fixed_9b573c71`  
**Queries:** 50 (Q01–Q50) · **pages:** 953 (688 usable) · **passages:** 5,585  
**Provider:** Brave Search · region AU · language en · fan-out 3 · capture 20 ·
analyse 10  
**Protocol lock:** `2026-08-14T22:00:03Z`

Freeze v1 (`20260810_live_baseline_live_9b573c71`, 32 queries) is archived for
audit only. The per-query table below is the v1 snapshot; v2 routing is
`results/routing.csv` (fixed-eligible **30/50**, rank 11–20 **6**, absent **14**).

Competitor HTML that returned 429 / thin was replaced by exact-URL Common Crawl
and **logged** (`results/corpus_fallback_log.jsonl`) — dated confound, not silent.

### FC position routing (`results/routing.csv`)

| Route | n / 32 | Meaning | `fixed` eligible? |
|---|---:|---|---|
| `top10` | **18** | FC in Brave analysis depth | Yes, if page usable (all 18 are) |
| `rank11-20` | **3** | In capture, outside analyse k=10 | No — Type A / k-sensitivity |
| `absent` | **11** | Not in Brave top-20 | No — Type A gate |

| Stratum | `top10` | `rank11-20` | `absent` |
|---|---:|---:|---:|
| Primary Q01–Q22 | 17 | 2 (Q13, Q21) | 3 (Q04, Q08, Q20) |
| Secondary Q23–Q32 | 1 (Q32) | 1 (Q28) | 8 |

**`fixed` skipped (14 queries):** Q04, Q08, Q13, Q20, Q21, Q23–Q31.

### Brave FC retrieval — all 32 queries

This is **search retrieval** (Brave freeze), not hybrid-index retrieval and not
citation. Rank is 1-based in the merged capture (top-20).

| Query | Stratum | Brave FC rank | Top-10 | Top-20 |
|---|---|---:|:---:|:---:|
| Q01 | primary | 3 | Y | Y |
| Q02 | primary | 3 | Y | Y |
| Q03 | primary | 4 | Y | Y |
| Q04 | primary | — | | |
| Q05 | primary | 1 | Y | Y |
| Q06 | primary | 1 | Y | Y |
| Q07 | primary | 1 | Y | Y |
| Q08 | primary | — | | |
| Q09 | primary | 5 | Y | Y |
| Q10 | primary | 5 | Y | Y |
| Q11 | primary | 1 | Y | Y |
| Q12 | primary | 4 | Y | Y |
| Q13 | primary | 19 | | Y |
| Q14 | primary | 3 | Y | Y |
| Q15 | primary | 7 | Y | Y |
| Q16 | primary | 6 | Y | Y |
| Q17 | primary | 3 | Y | Y |
| Q18 | primary | 1 | Y | Y |
| Q19 | primary | 8 | Y | Y |
| Q20 | primary | — | | |
| Q21 | primary | 19 | | Y |
| Q22 | primary | 2 | Y | Y |
| Q23 | secondary | — | | |
| Q24 | secondary | — | | |
| Q25 | secondary | — | | |
| Q26 | secondary | — | | |
| Q27 | secondary | — | | |
| Q28 | secondary | 11 | | Y |
| Q29 | secondary | — | | |
| Q30 | secondary | — | | |
| Q31 | secondary | — | | |
| Q32 | secondary | 8 | Y | Y |

| Slice | n | Brave top-10 | Brave top-20 | Absent |
|---|---:|---:|---:|---:|
| **All 32** | 32 | **18 / 32 = 56%** | **21 / 32 = 66%** | **11 / 32 = 34%** |
| Primary Q01–Q22 | 22 | **17 / 22 = 77%** | **19 / 22 = 86%** | 3 / 22 = 14% |
| Secondary Q23–Q32 | 10 | **1 / 10 = 10%** | **2 / 10 = 20%** | 8 / 10 = 80% |

### Usable-doc QC (`geo qc`)

Most queries have 6–9 usable analysis-pool docs. Two secondary queries are
`low_usable` (< 5): Q28 (3) and Q30 (4).

---

## 11. Baseline performance (what we have measured)

**Freeze v2** · `20260815_live_baseline_fixed_9b573c71` · 50 queries · 2 seeds × 5 runs  
· generator `gpt-5.6-luna` · `fixed` = whole pages (`page_prompt_chars=24000`) ·
`reindexed` snippets (`passage_prompt_chars=2600`) · **selection** 500 calls.
Arm = **`baseline` only**. No GEO intervention scored yet.

### 11.1 Three stages — `selection` · `reindexed` · `fixed`

Row-level rates (answers equally weighted). Primary = Q01–Q22 + Q33–Q50.

| Metric | Reindexed · all 50 | Reindexed · primary 40 | Reindexed · secondary 10 | Fixed · 30 eligible | Fixed · primary 29 |
|---|---:|---:|---:|---:|---:|
| Answers (2×5) | 500 | 400 | 100 | 300 | 290 |
| FC retrieved | **20%** | **20%** | **20%** | **100%** (by construction) | **100%** |
| FC inclusion (cited) | **9%** | **11%** | **0%** | **38%** | **37%** |
| FC citation share | **2.3%** | **2.9%** | **0.0%** | **6.7%** | **6.6%** |
| FC PAWC | **0.0087** | **0.0108** | **0.0000** | **0.0234** | **0.0237** |
| Mean cite position (when cited) | 3.6 | 3.6 | never | 4.9 | 4.9 |
| Mean FC context position | 2.8 | 2.9 | 2.1 | 5.3 | 5.3 |
| P(cited \| retrieved) | 44% (n=100) | 55% (n=80) | 0% (n=20) | 38% (n=300) | 37% (n=290) |
| Monopoly answers | **10%** | **0%** | **50%** | **0%** | **0%** |
| Brave FC in top-10 | **60%** (30/50) | **72%** (29/40) | **10%** (1/10) | n/a (eligible only) | n/a |
| Brave FC in top-20 | **72%** (36/50) | **85%** (34/40) | **20%** (2/10) | n/a | n/a |
| **Relevance (0–2)** | **2.00** | **2.00** | **2.00** | **2.00** | **2.00** |
| **Response quality (0–10)** | **8.16** | **8.23** | **7.88** | **7.82** | **7.81** |

**Selection** (third stage; frozen capture-20 title+snippet, 500 calls): FC is
listed on 72% of calls; **P(FC selected | in capture) = 23%** (primary 84/340
= 25%; secondary **0%**); median selection rank 3 when picked. Always opened
10/10: Q11, Q12, Q18, Q44, Q49. Brave #1 and never opened: Q06, Q07, Q47.

**Headline.** Brave top-10 ≠ selection ≠ hybrid retrieval ≠ citation. On
`reindexed`, FC is cited on **9%**. On `fixed` (whole page already in the
analysis pool) it is cited on **38%**. Selection would open FC only **23%**
of the times it is listed. `other` domains still take most of the sentence
mass. The gap is **visibility**, not answer quality.

### 11.2 `reindexed` — interpretation

Hybrid retrieval over the full freeze (airlines, blogs, aggregators, OTAs)
rarely selects Flight Centre. Queries where FC is retrieved in all 10 runs:

| Query | Text | Cited in 10 runs |
|---|---|---|
| Q05 | multi-city | 6/10 |
| Q11 | round-the-world | 10/10 |
| Q12 | flights to Perth | 10/10 |
| Q18 | premium economy | 10/10 |
| Q19 | Australia → Vietnam | 4/10 |
| Q25 | (secondary) travel-agent savings | 0/10 |
| Q28 | (secondary) questions for an agent | 0/10 |
| Q34 | Melbourne → Singapore | 0/10 |
| Q35 | Sydney → Auckland | 0/10 |
| Q42 | Australia → Singapore | 4/10 |

The other 40 queries never retrieve FC in this layer, including several where
Brave ranked FC in the top-10. Rank in search ≠ rank in the hybrid passage
index once `other` pages are in the pool.

**Citation mass (all 500 `reindexed` answers):** `other` 1986 · Skyscanner 1075 ·
Webjet 285 · Expedia 272 · **Flight Centre 95**.

### 11.3 `fixed` — interpretation

300 answers, cleaned **whole page** per analysis URL. Restricted to the 30
queries where FC is in Brave top-10 with usable text. Retrieval rate is 100%
by design. Inclusion **38%**: FC is *seen* and still unused more than half
the time. Mean context position ~5.3 is consistent with C-SEO: rank still
dominates.

Only **Q32** from the secondary stratum is `fixed`-eligible (10 answers).
Do not pool secondary into the primary family.

**Citation mass (300 `fixed` answers):** `other` 1976 · Skyscanner 543 ·
**Flight Centre 178** · Webjet 164 · Expedia 65.

### 11.4 Type A failure modes on freeze v2 (n=50)

| Mode | n | Meaning |
|---|---:|---|
| **A** Never in Brave top-20 | 14 | Type A gate — on-page GEO cannot help until rank improves |
| **B** In top-20 but outside analyse k=10 | 6 | Sensitivity to k |
| **C** In analysis pool (`fixed` eligible) | 30 | Type B lab |

Secondary queries: **8/10 absent** from Brave top-20. Agent-value / trust
prompts are a coverage monopoly for non-brand domains.

### 11.5 What this baseline implies for GEO work

1. **`fixed` is the Type-B lab.** Once FC is in the pool, it is cited on **38%**.
   Content edits can be measured here without live rank.
2. **`reindexed` over the open freeze is a Type-A + retrieval gate.** FC is
   retrieved on only 10/50 queries. On-page GEO alone cannot create citations
   that retrieval never surfaces.
3. **Selection is a third locked stage** (500 decisions), not a footnote.
   Even when FC is in the frozen SERP, the model would open it only 23% of
   the time (0% on agent-value). Title/snippet arms compare inside selection.
4. **Live search is also a Type-A gate.** On primary, 6/40 never enter top-20.
   On secondary, FC is almost invisible (8/10 absent).
5. **`other` domains dominate answers.** Any GEO claim must compete with
   airlines, blogs, and aggregators, not only the three named OTAs.
6. **Do not pool secondary into the primary family.** Coverage monopoly would
   inflate or deflate “content” effects that are actually rank / IA.
7. **Do not mix `fixed` vs `reindexed` as a treatment effect.** Same metrics,
   different retrievers. Compare each future arm to baseline **inside one
   variant**.
8. **Bot-UA probe (Type A access).** Expedia hard-blocks AI crawlers (31/31);
   Skyscanner serves a 1-word shell; Flight Centre and Webjet serve browser-
   equivalent text. The freeze used a browser UA, so competitor content in
   the baseline is, if anything, *stronger* than a real ChatGPT Search bot
   would see.

---

## 12. Install

```bash
pip install -e .              # offline/ollama smoke OK with --allow-demo
pip install -e ".[openai]"    # for reportable runs
```

Set `mode` / `gen_model` in `geo_bench/config.py`. Export:

- `OPENAI_API_KEY` — generation + embeddings (openai mode; embeddings also for anthropic)
- `ANTHROPIC_API_KEY` — if `mode=anthropic`
- `BRAVE_API_KEY` — live retrieval / freeze

## 13. Workflow

```bash
geo freeze-live                          # Brave capture → runs/<RUN_ID>/
geo verify --from-run <RUN_ID>
geo qc --from-run <RUN_ID>
geo lock --from-run <RUN_ID>
geo route --from-run <RUN_ID>
geo index baseline --from-run <RUN_ID>
geo controls --from-run <RUN_ID>         # must print ALL CONTROL TESTS PASSED
# set mode=openai|anthropic, then:
geo run baseline --variant reindexed --from-run <RUN_ID>
geo run baseline --variant fixed --from-run <RUN_ID>
geo select baseline --from-run <RUN_ID>  # frozen-SERP gatekeeper (title+snippet)
geo score baseline --variant reindexed --stratum primary
geo score baseline --variant reindexed --judge
geo stats                                # primary + secondary endpoint families
geo monopoly baseline --variant reindexed
geo calibrate baseline --variant reindexed
geo kappa results/calibration_sample.csv
geo quarantine-demo                      # relocate any leftover offline scorecards
```

Held-out (after arms locked): `geo run <arm> --heldout --final --from-run <RUN_ID>`

Live dry-run (no generation): `geo live-pool --n 10` or `--urls-only`.

Repair thin/429 pages in a freeze: `geo repair-freeze <RUN_ID>`.

### Helper scripts

| Script | Job |
|---|---|
| `scripts/run_pipeline_v2.py` | Full pipeline on ACTIVE freeze: index → 2×5 both variants → selection → judge |
| `scripts/run_judge_baseline.py` | Replay judge on baseline answers |
| `scripts/bot_ua_probe.py` | Fetch frozen URLs with OAI-SearchBot/GPTBot UAs → Type-A access gap |
| `scripts/bing_crosscheck.py` | One-off Bing-AU vs Brave brand-rank table (descriptive only) |
| `scripts/analyse_live_baseline.py` | Print live baseline failure modes |
| `scripts/cc_cluster_lookup.py` | Exact-URL Common Crawl index lookup |
| `scripts/smoke_test_ollama.py` | Local LLM smoke |

Invariant tests (no network): `python -m pytest tests/ -q`

---

## 14. Package layout

```
geo_bench/
  config.py       frozen dataclass — parameters + endpoint families
  api/            offline · ollama · openai · anthropic
  crawler/        quality (freeze QC)
  retrieval/      chunker · index · retriever
  search/         Brave · fan-out · live retriever · Common Crawl · cache
  generation/     prompts (Aggarwal Listing 1) · generator
  evaluation/     metrics · statistics · judge · calibration
  experiment/     runner · controls · run_store · routing · protocol lock
  cli.py
queries/          queries.csv · heldout.csv · live10.csv
results/          indexes, answers, scores, routing, qc                 (gitignored)
runs/             freeze RUN_IDs (search + pages + generation)         (gitignored)
cache/            search · pages · fanout · commoncrawl                (gitignored)
scripts/          CC / live probe / analyse / 2x5 + judge replay
SCORING_RUBRICS.md
BASELINE_LOCK.md
decisions_log.md
```

### Outputs (reportable)

```
runs/<RUN_ID>/                             # freeze + per-query generation JSON
runs/<RUN_ID>/protocol_lock.json
results/routing.csv
results/qc_pages.csv · qc_queries.csv
results/index_baseline.pkl · vecs_baseline.npz
results/answers_<arm>_<variant>.jsonl
results/scores_<arm>_<variant>.csv
results/corpus_fallback_log.jsonl          # live 429 / CC substitutions
results/calibration_sample.csv             # copy of reindexed 60-row sample
results/calibration_sample_baseline_*.csv  # reindexed + fixed grader sheets
results/_demo/                             # offline/ollama smoke — not deliverables
```

---

## 15. Invariants

- No JavaScript during **baseline freeze** fetch/parse. JS/prerender is allowed
  only as FC-only arm `ssr_visible` on the same freeze URLs; never recapture
  Brave or render competitor pages
- Freeze first; experiments run only on that dated snapshot
- At most `cap_per_brand` (2) passages per brand on `reindexed`; `top_k` = 5
- Live: one user-agent for every brand; exact-URL archive fallback only
- Passage order shuffled per run
- Parameters live in `config.py`; protocol lock must match before generation
- Freeze checksummed; never re-fetch after freeze without `--refresh`
- No hand-built ranking formula for citations
- Fixed swap fails if chunk identity cannot be matched
- Offline/ollama never write scored deliverables without `--allow-demo`
- Judged metrics: brand-mask before scoring; rubric frozen in
  `SCORING_RUBRICS.md`

---

## 16. Scope and limitations

- Models an AI answer engine; omits proprietary rerankers
- Competitor content is a dated freeze (10 Aug 2026 Brave AU)
- Optimised pages are never published live
- Type A audited and observed on the freeze, not experimentally “fixed”
- Freshness untestable on a frozen search snapshot
- Verified-facts-only is stricter than Aggarwal (conservative bias)
- Secondary queries may reward **coverage monopoly** — report separately
- n≈40 primary queries: large consistent effects detectable after Holm; small
  mixed effects often look null — CIs are the client deliverable
- Shared BM25 IDF depends on freeze size: FC edits that change chunk count can
  mildly shift competitor scores. T3 checks competitor-*only* BM25 order
- Expedia 429 → Common Crawl fallback is a logged confound
- `gpt-5.x` may ignore custom temperature; documented in the OpenAI client
- Judged metrics need human κ calibration before they are confirmatory

**We will claim:** specified content changes change how often FC is cited, by a
measured amount, against a fixed competitor field in this stack — and which
change contributes most *as a pilot candidate*.

**We will not claim:** absolute live-platform visibility, or that content alone
resolves Type A access issues.

---

## 17. Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | Baseline scorecard — relative visibility on primary prompts | **Locked** (this README §10–11 + `BASELINE_LOCK.md`) |
| 2 | Per-method contribution with CIs — priority candidates for a live pilot | Not started (arms missing) |
| 3 | Implementation guide — markup and wording | Not started |
| 4 | Coverage gap + monopoly report | **Brave 32-query table + routing + monopoly in §10–11** |
| 5 | Type A schedule | Evidence collected; schedule not written |
| 6 | Reproducibility package | Code + freeze hashes + lock + 2×5 answers/scores + controls |

---

## 18. How to read “performance” in one paragraph

We have not yet tested GEO interventions. The **unmodified Flight Centre
baseline** is locked on freeze `20260810_live_baseline_live_9b573c71` (2×5,
judged). Brave places FC in the top-10 on **56%** of all queries (**77%**
primary, **10%** secondary). In `reindexed` (hybrid BM25+dense over the freeze,
top-5, cap 2), FC is retrieved on **18%** of primary answers and cited on
**16%**, share **6%**, PAWC **0.022**. In `fixed` (FC already in Brave’s
analysis pool; 17 primary queries), retrieval is 100% by design and inclusion
is **67%**, share **14%**, PAWC **0.058**. Judge relevance is **2.00** and
response quality **~7.4–8.0 / 10** — answers are good; FC is rarely visible.
Eleven of 32 queries never enter Brave top-20. Next: human κ, then one FC
intervention at a time on **this freeze**, compare to baseline **inside** each
variant, Holm on primary PAWC + citation share.

---

*GenAI acknowledgement: scaffolding and documentation drafted with AI
assistance; reviewed and validated by the team.*
