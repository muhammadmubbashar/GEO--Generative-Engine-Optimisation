# Query selection and citation results — questions and answers

## Why not all approximately 130 client prompts?
The delivered experiment records contain 50 queries, labelled as 40 primary and 10 secondary. The delivered files do not establish that this is a statistically representative sample of every client prompt, or verify the approximately 130 total. Do not invent a random-sampling explanation. The headline experiment is a scoped content comparison, not a complete audit of the client prompt universe. The retained query CSV identifies its sources.

## Why 29 rather than 50?
The main content comparison uses 29 eligible primary questions with FC in the saved supplied-source pool. Ten of the 50 are labelled secondary. Eleven of the 40 primary questions are outside this eligible comparison. This design asks whether changing supplied FC content affects citation selection; it does not measure whether FC will first be found for every question. The excluded queries must not disappear from an overall discovery assessment.

## Why 290 answers?
29 questions × 2 source orders × 5 repetitions = 290 answers per condition. These are repeated answers to 29 questions, not 290 independent customer questions. Uncertainty resamples whole questions, keeping repeats together.

## What exactly counts as a citation?
Each saved answer has its own numbered source list. The scorer extracts bracketed numbers such as [7], checks that they index an existing source, and looks up whether that source is labelled flightcentre. If at least one does, the answer scores 1; otherwise 0. Multiple FC citations in one answer still score 1. A plain brand mention without a valid numbered FC reference does not count under this scorer.

## Does it measure copied words?
No. It does not compare wording, count copied words, or measure how much FC contributed. An answer could paraphrase a substantial FC passage, cite a tiny detail, or even attach an unsupported FC citation: all can score 1 if the numbered source mapping is valid. One copied word without the numbered reference scores 0. This is a deliberate narrow measure of source-reference inclusion, not a measure of useful contribution.

## Are those final citations relevant and correct?
The headline metric does not establish that. We have saved examples, but a systematic independent review of citation support and answer relevance is not established by the count verifier. Review must ask whether the cited page supports the specific claim, whether qualifications and prices are correct, and whether the answer addresses the question. Do not claim that every counted citation passed that review.

## What does [7] mean?
Source seven in that particular answer's supplied list. It is not seventh place in a recommendation ranking. Source numbers can refer to different websites in different answers; the scorer uses the source list saved with each answer.

## What did the model choose itself?
It wrote the answer and chose which supplied sources to reference. Our pipeline controlled the question, saved source texts, order and page substitutions. The model did not independently browse the live web during this content test, and it was not instructed to cite FC.

## Is the result still useful?
Yes, for its stated scope: valid numbered FC source references appeared in a larger share of the selected answers. That shows an observed improvement in source visibility under the supplied-source setup. It does not establish improved usefulness, recommendation, unique factual contribution, discovery or conversion. Present the metric with that boundary rather than treating it as a proxy already proven to predict bookings.

## What is the result?
116/290 baseline = 40.0%; 152/290 selected optimised repeat = 52.4%. Difference: 12.4 percentage points, about 31.0% relative. 21 question averages improved, 6 declined and 2 were unchanged. The earlier same-page treatment run was 143/290 = 49.3%. Independent question-level bootstrap interval for the selected difference: approximately +5.2 to +20.0 points. The analysis is exploratory.

## Why not claim causality or a guaranteed live uplift?
The source URLs/order and competitor text match within the selected pairs. However, historical baseline reuse, different page capture dates and fares, generation variability, iterative development and result selection constrain inference. The result is not an independent held-out confirmation or a fresh simultaneous production experiment.

## What concrete evidence can we show?
The saved Melbourne–London pair Q06_fixed_s2_r4 has no FC [7] reference in its original answer and three FC references in its optimised answer. The improved answer contains a fare matching the supplied page. Count that as one citing answer, not three. Across ten trials for Q06, the counts are 2 versus 8. This is one illustrative pair, not proof that all statements are supported or that FC was recommended as a booking agent.

## Was FC's page empty without JavaScript?
The dated test found missing deal-card content without JavaScript; other page text, including some FAQ text, remained. Different crawlers can behave differently. Robots permission and a successful HTTP status do not prove a genuine crawler retrieved or understood the page. Avoid generalising the presented deck's shorthand to an entirely empty page or every AI engine.

## What should be reviewed next if stronger claims are wanted?
Audit citation support and answer relevance separately, ideally using independent reviewers and a written rubric. Count explicit FC booking/adviser recommendations separately. Use an untouched, documented query sample for generalisation; assess real discovery and customer outcomes with their own appropriate design. None of these checks has been silently added to the existing 40.0%–52.4% result.

## Where can we verify the counts?
Private package: `python 03_code/verify_results.py` and `python 03_code/verify_repeated_runs.py`. These use saved records and make no model calls. Public GitHub: `python scripts/verify_public_counts.py` checks published question-level aggregates; it does not rescore the private raw answers.
