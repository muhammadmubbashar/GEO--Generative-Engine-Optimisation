# Reproduction and handover

## Public numerical check — no API or dependencies

From this repository root run:

```sh
python scripts/verify_public_counts.py
```

This recomputes totals and intervals from the public question-level counts. It does **not** independently rescore original answers. Use the assessment package for that stronger check.

## Raw-record audit in the separate assessment package

Extract `GEO_Semester_2_Assessment_Package.zip`, open `START_HERE.html`, and run from its submission root:

```sh
python 03_code/verify_results.py
python 03_code/verify_repeated_runs.py
```

Those commands use the package's `04_evidence` inputs. They are not expected to run on this smaller public checkout without those inputs. The same verifier source is retained here for inspection. The final-stage rebuild has separate dependencies in `03_code/refinement_requirements.txt`; follow the package instructions. Historical live-generation scripts require original assets and provider access and are not the offline demonstration.

Inspect both an improving and a declining question in the results explorer. Check each citation against its trial-specific source list. Review claim support separately from citation presence.

## Alignment checks

`PUBLIC_MANIFEST_SHA256.json` identifies every public handover file. `HANDOVER_ALIGNMENT.json` records the exact PowerPoint SHA-256, matching the assessment-package deck. No presentation results were regenerated or edited for publication.

Before submission, obtain the full assessment rubric and confirm the artefact agreement, perform the independent human citation review, and rehearse on the presentation computer. Prepared documents do not imply tutor/client approval or personal contribution claims.
