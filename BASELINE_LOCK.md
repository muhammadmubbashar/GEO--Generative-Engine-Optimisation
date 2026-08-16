# Baseline lock — sign-off before optimisation

Freeze: `20260815_live_baseline_fixed_9b573c71`  
Protocol lock: `2026-08-14T22:00:03Z` (`runs/<RUN_ID>/protocol_lock.json`)  
ACTIVE: `runs/ACTIVE` → this freeze  
Queries: 50 (Q01–Q50)

v1 freeze `20260810_live_baseline_live_9b573c71` is archive only.

**Current `fixed` is whole-page** (`fixed_source_unit=full_page`): 300 answers, cited **38%**, PAWC **0.0234**.  
**Selection** is a third locked stage: 500 title+snippet decisions, P(open | listed) **23%**.  
**Reindexed** is unchanged: 500 answers, cited **9%**.

Do **not** start intervention arms until every row below is done. Recapturing
Brave or editing experimental parameters without a `decisions_log.md` entry
voids comparability.

| Gate | Status | Evidence |
|---|---|---|
| Freeze pages hash-verify | **Done** | `geo verify --from-run 20260815_live_baseline_fixed_9b573c71` · 953 pages |
| Usable-content QC (flag, do not auto-drop) | **Done** | `results/qc_pages.csv` · 688 usable · Q28/Q30 `low_usable` |
| Protocol lock written | **Done** | `runs/.../protocol_lock.json` · sha256 `1dd1be8ec110e8a2…` |
| FC routing (all 50 queries) | **Done** | `results/routing.csv` · fixed eligible **30** · rank 11–20 **6** · absent **14** |
| Brave retrieval table (search layer) | **Done** | README §11 · top-10 **60%** (72% primary / 10% secondary) · top-20 **72%** |
| Hybrid index over freeze | **Done** | 5,585 passages · `results/index_baseline.pkl` |
| Controls T1–T4 | **Done** | All PASS (`geo controls`) |
| Generation 2×5 `reindexed` | **Done** | 500 answers · `results/answers_baseline_reindexed.jsonl` |
| Generation 2×5 `fixed` | **Done** | 300 whole-page answers (30 queries) · cited **38%** |
| Selection 2×5 | **Done** | 500 calls · `results/selection_baseline.csv` · P(selected\|in capture) **23%** |
| Counted metrics + PAWC | **Done** | `results/scores_baseline_*.csv` |
| Judge (mask + rubric v1.0) | **Done** | 800 generation answers · relevance **2.00** · RQ **8.16 / 7.82** |
| Calibration sample exported | **Done** | `results/calibration_sample_baseline_reindexed.csv` + `_fixed.csv` (60 each) |
| Bot-UA probe | **Done** | `results/bot_ua_probe.csv` · Expedia 31/31 blocked; Skyscanner 1-word shell |
| Bing cross-check (descriptive) | **Done** | `results/bing_crosscheck.csv` · 50/50 SERPs · FC top-10 overlap 21 |
| Human κ (two graders) | **Pending** | Fill human columns → `geo kappa <csv>` · κ ≥ 0.6 before confirmatory quality claims |
| Held-out | **Locked** | `queries/heldout.csv` · only with `--final` after arms, baseline + `full_stack` only |
| Optimisation arms | **Not started** | Only FC text may change; competitors stay freeze bytes |

## Three stages (do not average)

| Layer | What it measures | Rate |
|---|---|---|
| Brave freeze | FC URL in search top-10 / top-20 | **60% / 72%** of 50 queries |
| **Selection** | LLM would open FC from frozen title+snippet | **23%** of calls where FC is listed (360/500 listed) |
| `reindexed` | FC passage in hybrid top-5 | **20%** of 500 answers; cited **9%** |
| `fixed` | FC whole page in frozen analysis pool | **100%** of 300 answers (30 queries); cited **38%** |

Compare future arms to **baseline inside one stage**. Never treat selection vs fixed vs reindexed as the treatment effect.

## After this lock

1. (Recommended) Two graders complete the calibration CSVs; report κ.
2. Build one arm at a time. First content arm may be `ssr_visible` (FC-only
   browser-visible text; Type A) or `position_control` (no text edit).
   Do not Playwright-render the freeze or competitors.
3. Run `geo run <arm> --variant reindexed|fixed --from-run 20260815_live_baseline_fixed_9b573c71` (2×5, no `--once`).
4. `geo score … --judge` then `geo stats` (Holm on primary PAWC + citation share).
5. Held-out last: `--heldout --final` on baseline and `full_stack` only.
