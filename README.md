# Flight Centre GEO — final handover, 25 October 2026

This is the public companion to the private **GEO_Final_Handover.zip**. The ZIP includes raw evidence and START_HERE.html; this repository intentionally contains only scoped public artefacts.

- [FC leadership PPT](presentation/FC_GEO_Leadership_Final.pptx)
- [Professor PPT with demo](presentation/Professor_Final_With_Working_Demo.pptx)
- [Revised technical report](docs/GEO_Technical_Report_and_Handover_Guide_Team62.pdf)
- [Artefact inventory](docs/ARTEFACTS.md)
- [Reproduction instructions](docs/REPRODUCING.md)

## Authoritative current files
- presentation/FC_GEO_Leadership_Final.pptx — corrected FC leadership briefing and embedded notes.
- presentation/Professor_Final_With_Working_Demo.pptx — retained professor assessment presentation with saved-evidence demo.
- docs/GEO_Technical_Report_and_Handover_Guide_Team62.pdf — revised supplied report, with corrected interpretation and FC implementation appendix.
- docs/Artefact_Agreement_List_for_Tutor.pdf — current delivery inventory; not proof of acceptance.
- docs/Validation_Record.md — checks performed and unresolved limits.

## Agreed artefacts
1. Experiment/optimisation software: 03_code, including selected and individual snapshots.
2. Page demonstrator: 52 optimised outputs and baseline comparisons in 04_evidence/pages and comparison views.
3. Results/reproducibility pack: queries, captured page database, saved answers, source maps and result summaries in 04_evidence.
4. Technical report/handover: current PDF, claim ledger, assessment mapping and checking instructions in 02_documentation.
5. Presentations/notes: both labelled decks and professor demo/preparation materials in 01_presentation.

## Verified results and limits
Combined: baseline 116/290 (40.0%), initial treatment 143/290 (49.3%), repeat 152/290 (52.4%). The selected repeat gain is +12.4 percentage points, approximately +31.0% relative. The individual-method baseline is 114/290. Do not swap controls or add method gains.

The selected stack contains rendered-content processing, a joint fact/question block and FAQ restoration/repositioning. These are three content groups and four technical operations; they are the same implementation. Added schema, external enrichment, generic rewrite and source-position manipulation are separate experiments, not part of this stack.

Citation inclusion is not brand recommendation, factual support, relevance, live discovery or revenue. Historical baseline reuse, capture differences and iterative development constrain interpretation. Secondary retrieval and reworded-query evidence remain available and are not pooled with the headline. Human citation-support review remains outstanding.

## Offline reproduction
Run with Python 3.10+ (standard library):
```
python 03_code/verify_results.py
python 03_code/verify_repeated_runs.py
```
The final FAQ-stage rebuild needs dependencies in 03_code/refinement_requirements.txt; see 03_code/README.md. Live generation requires provider credentials and original runtime configuration and may incur costs. No paid experiment was run for this release.

## Versions and publication boundary
Historical code, locks, records and preparation documents preserve what existed at the time. They are evidence, not current production instructions. Earlier preparation PDFs can refer to older slide counts; use the delivered professor deck and its matching notes for that presentation. Neither preparation material nor prior assessment mapping governs the FC leadership deck.

FC implementation is normal template/content work with routine monitoring. Repeating our sandbox or achieving 52.4% on live platforms is not a prerequisite or a promise.

GitHub contains the same current decks/report, code snapshots and public aggregates. Full third-party captures and generated-answer archives are private handover material and are intentionally excluded from public GitHub. Historical repository commits remain historical. MANIFEST_SHA256.json verifies this package; HANDOVER_ALIGNMENT.json identifies shared deliverables.

Public numerical check: `python scripts/verify_public_counts.py`. Private ZIP checks need the separately delivered evidence.
