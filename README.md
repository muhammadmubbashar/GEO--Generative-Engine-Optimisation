# Flight Centre GEO — Semester 2 assessment handover

This is the public companion to the **18 October 2026 professor presentation**: 18 main slides, 8 backup slides, 20 minutes. It replaces the outdated baseline-era landing page. Earlier commits remain historical, not the current instructions.

## Research question and conclusion

When Flight Centre information is already supplied alongside competitors, does changing its page representation increase **answer-level citation inclusion**?

The matched historical baseline has **116/290 citing answers (40.0%)**. The unchanged selected treatment produced **143/290 (49.3%) initially** and **152/290 (52.4%) on repeat**. The gains are **9.3 and 12.4 percentage points**, respectively. Both runs are shown; the higher run is not a guaranteed production rate. These are exploratory fixed-context results, not proof of increased booking recommendations, live discovery or revenue.

## Start here

- [Exact presentation](presentation/GEO_Semester_2_Final_Presentation.pptx)
- [Six timed presenter scripts](presentation/Speaking_Guide.html) — download to open HTML in a browser
- [Experiment and slide alignment](docs/EXPERIMENT.md)
- [Claims and evidence boundaries](docs/CLAIMS.md)
- [Reproduction and artefact handover](docs/REPRODUCING.md)
- [Selected historical implementation](03_code/selected_snapshot)
- [Individual implementation snapshots](03_code/individual_snapshots)
- [Question-level initial/repeat counts](results/Independent_Repeat_Analysis.json)
- [Individual method results, including unsuccessful methods](results/individual_methods.json)

## What is controlled?

29 eligible questions × 2 source arrangements × 5 repeats = 290 answers per condition. The fixed comparison matches questions, source identities/order, competitor text and instructions. The pipeline supplies evidence; the model chooses wording and citations. It is a RAG-style saved-context test, without live browsing or fine-tuning during generation.

A citing answer contains at least one valid citation to a supplied Flight Centre source. Multiple FC references in one answer still count once. Presence does not establish citation correctness or a recommendation.

## Selected implementation

Captured rendered content, semantic cleanup, grounded facts/questions and a final FAQ extraction refinement. The selected outputs retain original rendered offers; they are **not** the later price-matched treatment. External enrichment, added schema, broad automatic rewriting and source-position manipulation are not components of this selected stack.

The individual-method control is **114/290 (39.3%)**, distinct from the combined comparison's 116/290. Do not swap controls or add method gains together. Some historical modules contain other methods to preserve their imports/provenance; their presence does not make them part of the final stack.

## Important boundaries

Historical baseline reuse, capture/product differences, iterative selection, related questions and one saved model configuration limit causal and external validity. Whole-question bootstrap intervals do not remove these limitations. Reindexed and secondary evidence did not establish a general discovery or recommendation improvement. Independent human review of substantive citation support remains necessary.

## Public repository versus assessment package

This repository contains necessary presentation, project code and numerical summaries. The separately delivered **GEO_Semester_2_Assessment_Package.zip** includes the full answers, source maps, captured page evidence, report and offline raw-record checks. Full third-party captures and generated-answer archives are not newly published here. The public aggregate check is not a substitute for that raw-record audit.

No credentials, personal documents, local caches, draft decks or full working-directory dump are included. No new API experiment was run for this handover. Historical commits are preserved and may contain earlier public material.
