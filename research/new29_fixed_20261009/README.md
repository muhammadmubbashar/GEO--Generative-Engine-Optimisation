# New-wording robustness check: fixed-context GEO

Completed 9 October 2026. This is a separate follow-up to the selected baseline-versus-optimised page comparison, not a replacement or a pooled result.

## Results

- Fresh baseline: **199/290 (68.62%)** answers cited Flight Centre.
- Unchanged optimised pages: **223/290 (76.90%)**.
- Observed difference: **+8.28 percentage points**, or **12.06% relative uplift**.
- Question-level 95% bootstrap interval: **−1.03 to +17.93 percentage points**.
- Two-sided question-level sign-flip test: **p = 0.1163**.
- Questions improved / declined / unchanged: **14 / 6 / 9**.

The observed direction is positive, but this follow-up does not establish a statistically significant improvement at the 5% threshold. It does not prove no effect either. Do not describe this as conclusive independent validation or as booking/revenue growth.

## What was tested

29 assistant-authored, unbranded questions preserve the travel intent of the original 29 fixed-eligible topics. The questions were frozen before generation after a historical wording check. Familiar topics and source pools remain: this is new-wording robustness, not independent customer data or unseen destinations.

Both conditions received fresh generations. Each question had ten trials per condition: two source-order seed labels and five repetitions. Source identities and ordering were matched, competitor text unchanged, and the selected optimised pages unchanged. The model was `gpt-5.6-luna`, using provider defaults without an API sampling seed. There was no new retrieval or live web browsing. The measured endpoint is whether a valid citation marker maps to Flight Centre, not whether that citation supports the claim or recommends a booking provider.

All 580 records passed the existing integrity checks; no empty answers or detected invalid/grouped citation formats were reported. A credit interruption after 320 answers was followed by resumption of only the missing answers. Historical page-capture differences and model/provider variability remain limitations.

## Reproduce the statistics

Requires Python and NumPy (`pip install numpy`). From the repository root:

```sh
python research/new29_fixed_20261009/reproduce_statistics.py
```

The script makes no API calls. It reproduces the counts, effect, 50,000-draw paired question-bootstrap interval and 100,000-draw sign-flip p-value from `citation_outcomes.csv`, with seed 20261009. Repeated answers are nested within questions; they are not treated as 290 independent questions. Sign-flip inference assumes symmetry/exchangeability of paired question effects under the null.

- `queries.csv`: all 29 questions and original topic mappings.
- `citation_outcomes.csv`: all 580 binary citation indicators with condition, question and trial labels.
- `PROTOCOL.md`: protocol frozen before generation.
- `statistics.json`: machine-readable reproduced statistics.
- `provenance.json`: experiment identifiers, publication boundaries and checksums.

The public package deliberately excludes credentials, raw provider responses, source-page copies, full prompts, local paths, caches and presentation material. It supports **statistical reproduction**, not a standalone regeneration of the private corpus experiment or independent re-scoring of the raw answers. Existing local generation code and sealed source artifacts were preserved outside this package.
