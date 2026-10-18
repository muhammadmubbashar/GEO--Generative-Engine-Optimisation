# Claim–evidence ledger

Evidence identifiers below refer to the separately supplied assessment package. Code paths beginning `03_code/` are also available here.

## C01: The tested question is conditional FC citation inclusion.

Classification: Definition

Check: Inspect record_metrics and shared prompt.

Boundary: Not an operational definition of recommendation, relevance or sales.

Package evidence: `03_code/selected_snapshot/geo_bench/baseline_v2.py`, `03_code/selected_snapshot/geo_bench/generation/prompts.py`

## C02: The main fixed comparison has 29 questions and 290 answers per condition.

Classification: Verified observation

Check: Rescore raw records; group by query and verify 10 pairs each.

Boundary: 29 selected eligible questions, not 290 independent customer tasks.

Package evidence: `04_evidence/selected/queries.csv`, `02_documentation/Offline_Verification.json`

## C03: The pipeline chooses source packs; the model chooses answer wording and citations.

Classification: Verified implementation

Check: Inspect full prompt and numbered evidence.

Boundary: Not unrestricted live search; instructions require citations to supplied sources.

Package evidence: `03_code/selected_snapshot/geo_bench/generation/prompts.py`, `04_evidence/selected/baseline/Q06_fixed_s2_r4.json`

## C04: The repeated selected run has 116 baseline versus 152 treatment citing answers.

Classification: Verified observation

Check: Independent standard-library rescoring.

Boundary: Historical baseline; treatment development and capture dates differ.

Package evidence: `04_evidence/selected/baseline`, `04_evidence/selected/optimised`, `02_documentation/Offline_Verification.json`

## C05: The initial unchanged-page generation has 143 citations, while the repeat has 152.

Classification: Verified observation

Check: Verify original record identities, identical initial/repeat prompts and sources, then rescore.

Boundary: Both are development evidence; neither is an untouched independent holdout.

Package evidence: `04_evidence/selected/initial`, `04_evidence/Independent_Repeat_Analysis.json`

## C06: Reporting only 52.4% could overstate consistency.

Classification: Interpretation

Check: Display both unchanged-page runs against the same control.

Boundary: Do not select a maximum as the expected production rate or pool runs as a new experiment.

Package evidence: `04_evidence/Independent_Repeat_Analysis.json`

## C07: The repeat difference is +12.41 percentage points.

Classification: Verified calculation

Check: (152−116)/290 × 100.

Boundary: Relative increase is 31.03%; it is not 22%.

Package evidence: `02_documentation/Offline_Verification.json`

## C08: Independent question-bootstrap uncertainty is positive for the selected repeat.

Classification: Verified calculation

Check: Resample whole questions with saved random seed and 20,000 draws.

Boundary: Unadjusted exploratory interval. The original run summary uses a slightly different Monte Carlo lower endpoint; do not describe a new interval as copied from it.

Package evidence: `04_evidence/Independent_Repeat_Analysis.json`, `02_documentation/Offline_Verification.json`

## C09: All headline pairs preserve source order and competitor text.

Classification: Verified implementation

Check: Check query equality, source URLs/order and competitor text.

Boundary: FC input is intentionally changed; its factual equivalence is not established.

Package evidence: `02_documentation/Offline_Verification.json`

## C10: All 330 FC source occurrences match the selected cleaned outputs under the character cap.

Classification: Verified implementation

Check: Compare delivered text with the matching output prefix.

Boundary: Does not prove those pages were current, correct or served by a public AI engine.

Package evidence: `02_documentation/Offline_Verification.json`, `04_evidence/pages/outputs.json`

## C11: The final FAQ refinement rebuild matches 52 saved page outputs.

Classification: Verified implementation

Check: Run deterministic final-stage rebuild; compare HTML and cleaned-text hashes.

Boundary: Rebuild covers the final stage, not initial crawl or all earlier transformations.

Package evidence: `02_documentation/Refinement_Rebuild.json`, `03_code/rebuild_final_refinement.py`

## C12: FAQ-stage validation preserves existing answers, cards, metadata and links.

Classification: Verified scoped observation

Check: Inspect invariant checks and saved results.

Boundary: Does not establish global price parity or factual truth of inherited material.

Package evidence: `04_evidence/pages/validation.json`, `03_code/selected_snapshot/optimisation_v3/flight_first_refinement.py`

## C13: The six individual content families have different outcomes.

Classification: Verified observation

Check: Rescore featured primary fixed records against their 114/290 control.

Boundary: Historical controls and multiple variants; cannot add gains or infer component contributions.

Package evidence: `04_evidence/individual_methods.json`, `02_documentation/Offline_Verification.json`

## C14: External enrichment’s aggregate gain does not identify an enrichment effect.

Classification: Interpretation

Check: Inspect changed versus unchanged prompts; retain audit diagnosis.

Boundary: 80 changed prompts had no net gain; an independent reviewer should confirm the subset analysis.

Package evidence: `02_documentation/historical/V3_INDIVIDUAL_AND_COMBINED_AUDIT_2026-09-20.md`, `04_evidence/individual/optimisation_v3_external_refined_v2/records`

## C15: The tested schema variant changed both visible content and markup.

Classification: Verified implementation

Check: Inspect the transformation and delivered input.

Boundary: No isolated JSON-LD causal effect.

Package evidence: `03_code/individual_snapshots/optimisation_v3_schema_structured_v1/optimisation_v3/arms.py`

## C16: The rewrite trial is not a reproduction of AutoGEO preference learning.

Classification: Scope correction

Check: Distinguish generic rewriting from learned engine-preference optimisation.

Boundary: Do not label it as a validated AutoGEO implementation.

Package evidence: `03_code/individual_snapshots/optimisation_v3_autogeo_reviewed_repeat1/optimisation_v3/arms.py`

## C17: Corrected position preserves source text and competitor relative order.

Classification: Verified observation

Check: Check all 290 matched corrected-position pairs.

Boundary: Context positioning is not web rank or a page treatment in the final package.

Package evidence: `02_documentation/Offline_Verification.json`

## C18: The reindexed and fresh-wording checks do not establish broad generalisation.

Classification: Interpretation

Check: Inspect the separate intervals, task definitions and denominators.

Boundary: These tests are not interchangeable with fixed-source citation inclusion.

Package evidence: `04_evidence/secondary/r5_original_unchanged_reindexed_repeat_20260929/summary.json`, `04_evidence/secondary/new29_fixed_paired_20261009/summary.json`

## C19: A governed content-template pilot is a reasonable application to investigate.

Classification: Proposed application

Check: Use the working transformation as a prototype with live governance and new evaluation.

Boundary: Not a proven production or revenue result.

Package evidence: `04_evidence/pages/outputs.json`

## C20: Citation correctness and booking recommendation require further human review.

Classification: Unresolved limitation

Check: Blind review of complete answers and cited sources using an explicit rubric.

Boundary: Presence of a reference does not establish support or commercial endorsement.

Package evidence: `04_evidence/Results_Explorer.html`

## C21: Assessment 5 guide and rubric are now available and mapped; handover approval remains unconfirmed.

Classification: Verified document review

Check: Read the user-supplied Assessment 5 guide and rubric; map slides to requirements.

Boundary: Rehearsal, truthful contributions, AI acknowledgement and handover acceptance remain team responsibilities.

Package evidence: `02_documentation/Assessment_Mapping.json`, `02_documentation/Artefact_Agreement_List.html`

## C22: Semester 1 described broader evaluation than was established in the final fixed result.

Classification: Scope correction

Check: Compare proposed relevance/judge/external-validation stages with actual output evidence.

Boundary: Do not claim all proposed measures were implemented or calibrated.

Package evidence: `02_documentation/research_sources/Pillar_4.json`

## C23: Universal FAQ-schema extraction priority and universal no-JavaScript crawler behaviour are not established.

Classification: Unsupported generalisations excluded

Check: Compare Semester 1 wording with official Google documentation.

Boundary: Google describes rendering and no special AI schema requirement; behaviour cannot be generalised across every provider.

Package evidence: `02_documentation/research_sources/Pillar_3.json`, `https://developers.google.com/search/docs/appearance/ai-features`, `https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics`
