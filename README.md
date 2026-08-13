# geo_bench — Controlled Benchmark for Generative Engine Optimisation

**Flight Centre Travel Group × QUT Capstone Team 62 · IFN735 / IFN736**

Does changing a travel brand's web content measurably alter how often an AI
answer engine retrieves and cites it?

---

## 1. The problem

People increasingly ask AI assistants travel questions instead of using search
engines. Those systems retrieve a handful of web pages, synthesise an answer,
and cite a few sources. Flight Centre is rarely one of them; competitors are.

Semester 1 diagnosed why. Semester 2 measures what fixing it is worth.

## 2. Why a controlled environment, not live ChatGPT

Flight Centre's pages cannot be substituted inside a live AI engine — it reads
the public web. Without a substitution there is no before-and-after, so no
difference can be attributed to our change rather than to something a
competitor did that week. Live platforms are also non-deterministic,
personalised, and change without notice.

We therefore build a working copy of an AI answer engine that runs on saved
copies of real pages, which we control. Live platforms are still used, but for
a different job: checking whether our environment ranks brands the way they do.

**We claim relative citation under this retrieval+generation stack**, not
absolute visibility on any live platform. Deliverable “what to fund first”
means **priority candidates for a live pilot**, not a guaranteed production lift.

---

## 3. Two kinds of finding

| | Type A — Access & infrastructure | Type B — Content & structure |
|---|---|---|
| Question | Can the AI reach, fetch and read the page at all? | Once it is a candidate beside rivals, is the content good enough to be cited? |
| Examples | robots.txt, client-side rendering, page speed, sitemap, MCP | entity density, JSON-LD, FAQ, authority signals |
| Who can act | **Flight Centre only** | **Testable here**, with measured evidence |

Type A remains the higher commercial priority: it is a gate. Interaction
between Type A and Type B (good content partially compensating for marginal
crawlability) is **untestable** on a frozen no-JS corpus and is reported as an
open question.

---

## 4. Literature position

| Paper | Finding |
|---|---|
| Aggarwal et al., **GEO**, SIGKDD 2024 · arXiv:2311.09735 | Content optimisation raises visibility by up to 40% |
| Puerto et al., **C-SEO Bench**, NeurIPS 2025 D&B · arXiv:2506.11097 | Most methods largely ineffective; retrieval rank ≈ 7.6× more influential |
| Wu et al., **AutoGEO**, ICLR 2026 | Extends methods with accuracy-preservation constraint |

**Our contribution.** Neither benchmark evaluates HTML structure. No prior work
tests a single commercial brand against its real competitors using the brand's
own customer queries. A null result is publishable: it corroborates NeurIPS
in a new domain.

---

## 5. What we replicate, adapt and add

**Adopted from Aggarwal et al.** Two-step retrieve→generate engine · 5 answers
× 5 seeds · temperature 0.7, top_p 1 · their Listing 1 prompt · one source
optimised at a time · methods alone before combination.

**Adapted**

| Element | Theirs | Ours | Why |
|---|---|---|---|
| Source acquisition | Google top-5, live | Frozen local corpus, hybrid retrieval | Competitor drift |
| Candidates | 5 | **5, capped at 2 per brand** | Four brands; cap forces ≥3 brands in context |
| Granularity | Whole page | 350-word passages | Real engines chunk; locate which part is cited |
| Fact grounding | Invented stats allowed | **Verified facts only** | Client ethics; **conservative vs adversarial GEO** (limitation) |
| Metrics | PAWC + subjective | Counted metrics **+ PAWC** | Reproducibility + comparability |

**Added.** `schema_only` / `faq_structure_only` · passage shuffle ·
`position_control` · coverage-gap + monopoly reporting · `fixed` text swap by
**file+chunk identity** · T3 rank-isolation control.

PAWC uses the same *formula* as Aggarwal; the *document unit* is a passage, not
a whole page — cross-paper numeric comparison is therefore not apples-to-apples.
Position decay is inherited from the paper, not independently validated. Client
scorecards lead with counted metrics.

---

## 6. Design parameters

| Parameter | Value |
|---|---|
| Product line | Flights |
| Queries | **32** in `queries.csv` (22 primary Flights + 10 secondary trust/agent) · **7** held-out |
| Brands | Flight Centre · Skyscanner · Webjet · Expedia |
| Chunking | 350 words, 40 overlap, content-hash IDs |
| Retrieval | BM25 + dense, RRF, **top-5**, **max 2 per brand** |
| Generation | 5 runs × 5 seeds, temperature 0.7, shuffled passages |
| Reportable modes | **`openai` / `anthropic` only** (offline/ollama → `results/_demo/` via `--allow-demo`) |
| Statistics | Per-query Wilcoxon · bootstrap 95% CIs · Holm within primary family |

### Pre-registered primary analysis family

Confirmatory inference is locked to:

- **stratum** `primary` (Q01–Q22)
- **metric** `pawc`
- **variant** `reindexed`

Holm correction applies across arms **inside this family only**. Other metric ×
variant × stratum tables are **exploratory** and must be labelled as such
(`geo stats` prints `family=primary|exploratory`).

### Arms

`baseline` · `position_control` · `schema_only` · `faq_structure_only` ·
`statistics_addition` · `cite_sources` · `keyword_stuffing` · `full_stack`

### Two retrieval variants

| Variant | Behaviour | Purpose |
|---|---|---|
| `fixed` | Baseline candidates frozen; FC text swapped by **filename + chunk ordinal** | Aggarwal-comparable generation effect |
| `reindexed` | Index rebuilt per arm | Full effect including retrieval |

Difference ≈ retrieval contribution (the disputed quantity). Report
`Δ_reindexed − Δ_fixed` only after fixed swap identity checks pass.

---

## 7. Metrics

**Counted:** retrieval rate · inclusion · citation position · citation share ·
`monopoly_retrieval` (single-brand candidate set)

**Paper:** PAWC (eq. 3), co-citation mass split equally (duplicate indices
deduped before split)

**Covariate:** mean FC context position

---

## 8. Install

```bash
pip install -e .              # offline/ollama smoke OK with --allow-demo
pip install -e ".[openai]"    # for reportable runs
```

Set `mode` / `gen_model` in `geo_bench/config.py`. Export `OPENAI_API_KEY` for
openai mode.

## 9. Workflow

```bash
geo coverage
geo verify
geo qc
geo index baseline
geo controls                  # must print ALL CONTROL TESTS PASSED
# set mode=openai|anthropic, then:
geo all baseline
geo stats                     # primary family defaults
geo monopoly baseline --variant reindexed
geo quarantine-demo           # relocate any leftover offline scorecards
```

Held-out (after arms locked): `geo run <arm> --heldout`

### Control tests

| Test | Proves |
|---|---|
| T1 Determinism | Repeat retrieval → identical passages |
| T2 Fairness | Competitor files byte-identical across arms |
| T3 Isolation | FC marker: competitor **IDs** unchanged, FC IDs change, competitor **ranks** stable on probes |
| T4 Reproducibility | Rebuild → identical passage IDs |

---

## 10. Package layout

```
geo_bench/
  config.py       frozen dataclass — parameters + primary family
  api/            offline · ollama · openai · anthropic
  crawler/        discovery · coverage (NONE ≠ found) · fetcher · quality
  retrieval/      parser · cleaner · chunker · index · retriever
  generation/     prompts · generator
  evaluation/     metrics · statistics
  experiment/     runner (identity-matched fixed swap) · controls
  cli.py
```

### Outputs

```
corpus/manifest_baseline.csv
results/coverage_grid.csv
results/answers_<arm>_<variant>.jsonl   # reportable modes only
results/scores_<arm>_<variant>.csv
results/_demo/                          # offline/ollama smoke — not deliverables
```

---

## 11. Invariants

- No JavaScript during fetch/parse
- One shared index per arm — brands compete passage-for-passage
- At most `cap_per_brand` (2) passages per brand; `top_k` = 5
- Passage order shuffled per run
- Parameters live in `config.py` (crawler constants documented separately)
- Corpus checksummed; never re-fetch after freeze
- No hand-built ranking formula for citations
- Fixed swap fails if chunk identity cannot be matched

---

## 12. Collection rules

- Queries drive pages, never the reverse
- Every absence is **NONE with a search date** — literal `url=NONE` is an
  evidenced gap, not a found page
- Unequal page counts expected; search effort must not differ
- Pages under 200 cleaned words require human CSR vs blocked labelling

---

## 13. Scope and limitations

- Models an AI answer engine; omits proprietary rerankers
- Competitor content is a dated freeze
- Optimised pages are never published live
- Type A audited, not experimentally tested
- Freshness untestable on a frozen corpus
- Verified-facts-only is stricter than Aggarwal (conservative bias)
- Secondary queries may reward **coverage monopoly** — report separately via
  `geo monopoly` and `--stratum secondary`
- n≈22 primary queries: large consistent effects detectable after Holm; small
  mixed effects often look null — CIs are the client deliverable
- Shared BM25 IDF depends on corpus size: FC edits that change chunk count can
  mildly shift full-corpus competitor scores. T3 checks competitor-*only* BM25
  order; residual full-corpus IDF sensitivity is a tiny-corpus artefact

**We will claim:** specified content changes change how often FC is cited, by a
measured amount, against a fixed competitor field in this stack — and which
change contributes most *as a pilot candidate*.

**We will not claim:** absolute live-platform visibility, or that content alone
resolves Type A access issues.

---

## 14. Deliverables

1. Baseline scorecard — relative visibility on primary prompts
2. Per-method contribution with CIs — **priority candidates for a live pilot**
3. Implementation guide — markup and wording
4. Coverage gap + monopoly report
5. Type A schedule
6. Reproducibility package

---

*GenAI acknowledgement: scaffolding and documentation drafted with AI
assistance; reviewed and validated by the team.*
