# Decisions log

Any change to `geo_bench/config.py`, `SCORING_RUBRICS.md`, the freeze, or
pre-registered endpoints must be dated here. Silent parameter drift voids the
experiment.

---

## 2026-08-10 — Brave AU freeze captured

- **Decision:** Freeze `20260810_live_baseline_live_9b573c71` is the only
  corpus. Brave AU, fan-out ×3, capture 20 / analyse 10.
- **Why:** Live web is not reproducible; substitution requires a dated snapshot.
- **Consequence:** Recapture needs `--refresh` and a new RUN_ID; not comparable
  without re-baselining.

## 2026-08-13 — Old 4-brand sitemap corpus retired

- **Decision:** Delete sitemap/coverage/fetcher corpus pipeline. Index and
  controls read only `runs/<RUN_ID>/pages`.
- **Why:** Client study is live-search GEO, not a private 4-brand mini-web.
- **Consequence:** `corpus/` is archival only; do not use it as a fallback.

## 2026-08-13 — Retrieval variants locked to `fixed` + `reindexed`

- **Decision:** Retire `--variant live` (live generation). `fixed` = frozen
  Brave analysis pool (FC text swap only). `reindexed` = hybrid BM25 +
  `text-embedding-3-small` over all freeze pages, top-5, cap 2/brand.
- **Why:** Two questions (generation given Brave shortlist vs our retriever).
  Mixing them into one number is invalid.
- **Routing:** `fixed` only if FC is usable in Brave top-10 (18/32 queries).
  All 32 run `reindexed`.

## 2026-08-13 — Protocol lock + chunk cap

- **Decision:** Write `protocol_lock.json`. Add `chunk_max_chars=12000` so
  space-free JS/JSON blobs cannot exceed the embedding 8192-token limit.
- **Why:** Cheapflights-style pages produced 350 “words” of huge tokens.
- **Lock:** `locked_at=2026-08-13T09:01:57Z`. Config diffs warn; do not abort.

## 2026-08-13 — Baseline 2×5 + judge completed

- **Decision:** Reportable budget is 2 seeds × 5 runs (`gpt-5.6-luna`). Judge
  uses the same model at temperature 0, rubric `SCORING_RUBRICS.md` v1.0,
  brand-masked, one answer per call.
- **Counts:** reindexed 320 answers; fixed 180 answers; 500 judged.
- **Human κ:** sample exported; graders not yet run. Judged metrics stay
  secondary until κ ≥ 0.6.
- **Held-out:** still locked; `--final` only at end of study.

## 2026-08-14 — Baseline signed off; optimisation not started

- **Decision:** Freeze + 2×5 + judge + routing + controls are the locked
  baseline. Optimisation arms must not begin until `BASELINE_LOCK.md` is
  followed. Only FC text may change; competitor freeze bytes stay identical.

## 2026-08-14 — JS-rendered FC text is an optimisation arm, not a freeze recapture

- **Decision:** Baseline freeze stays **no JavaScript** (bot / typical RAG
  fetch). Do **not** recapture Brave or Playwright-render competitor pages.
  Planned arm `ssr_visible`: substitute **Flight Centre URLs only** with a
  dated browser-rendered (or prerender/SSR) dump of the **same freeze URLs**.
  Store under `runs/<RUN_ID>/arms/ssr_visible/`. Competitors keep freeze bytes.
- **Why:** Semester 1 finding — much FC “content” lives behind client JS, so a
  crawler/LLM fetcher never sees what a human sees. That is Type A
  (crawlability / SSR), testable here as a site change FC could ship. Rendering
  everyone would confound the treatment and break “same bytes.”
- **Freeze fact (do not overclaim):** the **19 FC URLs Brave actually returned**
  are already usable without JS (609–1183+ words, all `browser-ua`). The gap is
  (1) interactive/deal text still missing from those HTML shells, and (2) other
  FC URLs that never entered this freeze. `ssr_visible` measures exposing the
  *visible* page, not magically adding FC to Brave’s shortlist.
- **Confound to log:** rendered dump date ≠ freeze date. Record `rendered_at`
  per URL. Same UA policy as freeze. No live Brave refresh.
- **Consequence:** README invariant is “no JS on baseline fetch,” not “JS is
  out of the study.” `config.py` `arms` now includes `ssr_visible`. Protocol
  lock will warn on next `geo lock` check — expected; do not recapture.

## 2026-08-15 — Baseline v2: P0 data-integrity fixes + full audit remediation

- **P0 bug 1 (fixed variant):** `runner.py` let `pool.meta_dict()` overwrite
  the generator’s post-shuffle `retrieved_brands` with the unshuffled pool
  order — 173/180 fixed rows had wrong brand↔[n] maps, corrupting PAWC,
  citation share and the judge’s source labels. Fixed: pool meta can no
  longer clobber record fields.
- **P0 bug 2 (both variants):** `retrieved_texts` was stored pre-shuffle
  while `retrieved_brands` was post-shuffle, so the judge saw wrongly
  numbered sources. Fixed: the generator now records texts in the exact
  order the model saw (`[n]` == `retrieved_texts[n-1]`).
- **Consequence:** all v1 answers/scores/judgments are void. Archived to
  `results/_archive_v1_pre_audit/` and `runs/<RID>/_archive_v1/`. Baseline
  v2 regenerates everything on the SAME freeze (no recapture).
- **Prompt budget:** `passage_prompt_chars` 1200 → 2600 so the full 350-word
  chunk reaches the model (closer to Aggarwal’s whole-source protocol). This
  alone requires re-generation; bundled into v2.
- **retrieval_rank redefined:** now computed from `pool_brands` (pre-shuffle
  retrieval order — RRF rank on reindexed, Brave analysis slot on fixed).
  Previously it silently measured the post-shuffle context slot.
- **Retrieval determinism:** RRF is now 1-based (Cormack et al. 2009) with
  deterministic tie-breaks (score desc, passage id asc); BM25 k1=1.5 b=0.75
  pinned; index pickle stores a parameter fingerprint and refuses to load on
  drift. Existing index verified identical (same chunks, same BM25 params)
  and stamped — no re-embedding.
- **Protocol lock hardened:** config drift now ABORTS reportable runs
  (`--accept-drift` for explicitly exploratory runs, drift recorded). Lock
  payload gains git commit, prompt SHA-256, temperature/top_p, chunk and
  retrieval parameters. Freezing held-out queries now requires `--final`.
- **Statistics:** scipy is required (no silent p=1.0); matched-pairs
  rank-biserial effect size reported alongside the a-priori MDE.
- **Judge:** masking verifier now also fails on surviving extra-mask brands;
  raw judge JSON persisted per answer (`judge_raw`) for audit.
- **New stage — selection (`geo select`):** LLM gatekeeper reads the FROZEN
  capture-20 title+snippet rows per query and picks ≤5 results it would
  open, 2×5 per query; measures P(FC selected | in capture) and selection
  rank. Mirrors ChatGPT Search’s open-the-page decision; enables future
  title/meta-description arms. Baseline-only until arms exist.
- **Query expansion prepared:** `queries/queries_expansion.csv` adds Q33–Q50
  (18 primary flights-consideration queries, same client-intent family,
  chosen blind to all results, no held-out overlap). NOT yet frozen — needs
  `BRAVE_API_KEY`; freezing them creates a new RUN_ID and requires
  re-baselining reindexed over the enlarged corpus (planned as Freeze v2).
- **Bing:** Bing Search API retired (Aug 2025) → Bing cannot be a frozen
  engine. `scripts/bing_crosscheck.py` gives a one-off descriptive Bing-AU
  vs Brave brand-rank comparison (external validity only, never pooled).
- **Bot-UA probe:** `scripts/bot_ua_probe.py` fetches each frozen URL once
  with OAI-SearchBot/GPTBot UAs to quantify the Type-A access gap per brand.
  Diagnostic only; frozen corpus untouched.
- **Re-lock:** new `protocol_lock.json` written after this entry.

## 2026-08-15 — Freeze v2: 50 queries, one corpus, supersedes Freeze v1

- **Decision:** Freeze `20260815_live_baseline_fixed_9b573c71` is now the
  study corpus: all 50 queries (Q01–Q32 original + Q33–Q50 expansion),
  953 pages, 688 usable, routing 30/50 fixed-eligible, 14/50 Type-A absent,
  2/50 low-usable. Locked `2026-08-14T22:00:03Z` (UTC).
- **Why:** ~50 queries were needed for statistical power (MDE ~0.44d on
  n≈40 primary vs ~0.60d on n=22). Adding queries changes the shared
  reindexed corpus, so the whole baseline is generated once on v2 rather
  than patching v1.
- **Two-date confound (recorded):** SERPs for Q01–Q32 replay the cached
  2026-08-09/10 Brave captures; Q33–Q50 SERPs are live 2026-08-15. Pages
  whose v1 cache was empty/bot-walled/stale-method were refetched
  2026-08-15 (or exact-URL Common Crawl, logged per page in
  `page_fetch_log`). Freeze v2 is internally consistent; v1↔v2 numbers are
  never mixed.
- **Consequence:** Baseline v2 (2×5 fixed+reindexed + selection + judge)
  runs entirely on this freeze. The partial 32-query rerun on Freeze v1 was
  discarded before scoring. Freeze v1 remains on disk for audit only.

## 2026-08-15 — Baseline v2 generation + judge complete

- **Counts:** reindexed 500 answers; fixed 300 answers (30 eligible queries);
  selection 500 calls; 800 judged. All `run_id=20260815_live_baseline_fixed_9b573c71`.
- **Primary rates (reindexed):** retrieval 20%, inclusion 11%, PAWC 0.0108,
  citation share 2.9%. **Fixed:** inclusion 42%, PAWC 0.0289, citation share 7.2%.
- **Selection:** P(FC selected | in capture) = 23% (primary 25%).
- **Judge:** relevance 2.00, RQ ≈ 8.2. Human κ still pending.
## 2026-08-16 — `fixed` feeds whole pages (paper protocol); drop chunk-on-fixed

- **Decision:** `fixed` now puts the **cleaned full page** of each analysis-pool
  URL into the generator (Aggarwal KDD 2024; Puerto et al. NeurIPS 2025;
  Wu et al. ICLR 2026). Cap `page_prompt_chars=24000`. `reindexed` still
  retrieves **350-word chunks** (`passage_prompt_chars=2600`).
- **Removed:** `_best_chunk` (BM25-best 350-word slice on the Brave pool).
  That path could not measure FAQ/schema/stats added outside the lucky
  chunk. Also deleted superseded v1 scripts: `run_baseline_2x5.py`,
  `run_baseline_v2.py` (hardcoded Freeze v1), `live_probe_10.py` (retired
  `--variant live`). Use `scripts/run_pipeline_v2.py`.
- **Consequence:** locked Baseline v2 `fixed` answers (300 rows) used chunks
  and must **not** be mixed with a new full-page `fixed` run. Archived to
  `results/_archive_fixed_chunks_v2/` before regenerating. `reindexed`
  scores are unchanged (still chunks). Re-lock (`geo lock`) before the next
  reportable `fixed` generation. No Brave recapture.

## 2026-08-16 — Full-page `fixed` baseline regenerated (300 answers)

- **Decision:** `fixed` 2×5 on freeze `20260815_live_baseline_fixed_9b573c71`
  regenerated with cleaned whole pages. 300/300 judged. Do not mix with
  archived chunk-`fixed` scores.
- **Counts:** inclusion 38%, citation share 6.7%, PAWC 0.0234, RQ 7.82,
  relevance still 2.00. Versus archived chunks on the same 30 queries:
  inclusion 44% → 38%, PAWC 0.0290 → 0.0234.
- **Why lower:** rival full pages now occupy the prompt; FC context slot
  unchanged (mean 5.3). This is the paper-faithful Type-B lab going forward.
- **`reindexed`:** unchanged (chunks, 500 judged).


