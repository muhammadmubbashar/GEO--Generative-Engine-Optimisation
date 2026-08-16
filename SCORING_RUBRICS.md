# SCORING RUBRICS — Relevance and Response Quality

> **Frozen before scoring begins.** Version 1.0.
> Any change after scoring has started requires a new version number, a dated
> entry in `decisions_log.md`, and re-scoring of everything already scored.
>
> These two metrics complete the four required by the client brief:
> inclusion rate, relevance, ranking position, response quality.

---

## 1. Why these are separate from the counted metrics

The counted metrics — inclusion, citation share, citation position, PAWC —
answer *"was Flight Centre used?"* They say nothing about whether the answer
was any good, or whether it addressed what was asked.

Relevance and response quality require judgement. That makes them less
reproducible than counting, so three safeguards apply throughout:

1. **Brand masking.** Every brand name is replaced before scoring. A grader who
   knows which answer is "the optimised Flight Centre one" cannot be neutral,
   however careful they are.
2. **Fixed rubric, frozen in advance.** Written before any answer is seen, so
   the criteria cannot drift toward whatever the results happen to look like.
3. **Human calibration.** Two people independently score a sample; agreement is
   measured with Cohen's kappa. If agreement is poor, the rubric is at fault,
   not the graders.

---

## 2. What is scored, and what is not

**Scored:** the generated answer, as a whole.

**Not scored:** the source documents, the brands, or whether Flight Centre
appears. Those are already covered by the counted metrics. A grader must be
able to score an answer without knowing which brand it favours — that is the
point of masking.

**Unit:** one score per generated answer. With 2 seeds × 5 runs, each query
yields 10 scored answers per arm. Aggregate to the query level before testing,
exactly as with the counted metrics.

---

## 3. Masking — applied before any scoring

Replace, in the answer text and in any quoted source label:

| Real | Masked |
|---|---|
| Flight Centre, flightcentre, flightcentre.com.au | Brand A |
| Skyscanner | Brand B |
| Webjet | Brand C |
| Expedia | Brand D |
| Any other named commercial travel brand | Brand E, F, … |

Airlines, government sites and reference sites (Qantas, Wikipedia, Smartraveller)
are **not** masked — they are context, not experimental subjects, and masking
them would damage readability without removing bias.

**A masking verification test must run over 100% of answers before scoring
begins and fail if any brand string survives**, including possessives
("Flight Centre's"), lowercase forms, and URLs.

---

## 4. RELEVANCE — 0 / 1 / 2

*Does the answer address what was actually asked?*

This is about the fit between question and answer. It is **not** about accuracy,
writing quality, or which sources were used.

| Score | Label | Criteria |
|---|---|---|
| **2** | Fully relevant | Addresses the specific question asked. If the query names a route, cabin class or destination, the answer is about that. A traveller would consider the question answered. |
| **1** | Partially relevant | Addresses the general topic but misses the specifics — answers about flights generally when a particular route was asked, or covers only part of a two-part question. |
| **0** | Not relevant | Does not address the question, answers a different question, or declines to answer. |

### Worked examples

Query: *"i'm looking for flights from sydney to london"*

- **2** — discusses Sydney–London flights: airlines, durations, fares, or booking options for that route
- **1** — discusses international flights from Australia, or flights to London from anywhere, without addressing the specific pairing
- **0** — discusses hotels in London, or says it cannot help

Query: *"i'm looking to book a business class flight"*

- **2** — addresses business class specifically: what it includes, where to book it, typical fares
- **1** — addresses flight booking generally, with business class mentioned only in passing
- **0** — addresses economy fares or an unrelated topic

### Edge cases — decide once, apply always

- **Answer is relevant but factually wrong** → still relevant. Accuracy belongs to response quality.
- **Answer is relevant but very short** → still relevant if it addresses the question. Completeness belongs to response quality.
- **Answer hedges heavily** ("prices vary, check with providers") → score 1 if the topic is addressed but no substantive content is given.

---

## 5. RESPONSE QUALITY — weighted 0–10

*Is this a good answer, independent of whom it favours?*

Four components, scored 0–2 each, then weighted.

### 5.1 Accuracy — weight 40%

Are the claims supported by the cited sources, and internally consistent?

| Score | Criteria |
|---|---|
| **2** | Claims traceable to cited sources; no internal contradictions; figures consistent |
| **1** | Mostly supported, but at least one claim is unsupported by any cited source, or two figures conflict |
| **0** | Substantially unsupported, or contains a clear factual contradiction |

*Graders check claims against the supplied source documents, not against
outside knowledge. An answer faithful to a source that is itself wrong scores 2
— the answer did its job.*

### 5.2 Completeness — weight 30%

Does it give enough to act on?

| Score | Criteria |
|---|---|
| **2** | Covers the main aspects a traveller would need; specific enough to act on |
| **1** | Covers the topic but omits an obvious dimension, or stays generic where specifics were available in the sources |
| **0** | Minimal — a sentence or two with no substantive content |

### 5.3 Clarity — weight 20%

Is it well written and easy to follow?

| Score | Criteria |
|---|---|
| **2** | Clear structure, plain language, easy to follow |
| **1** | Understandable but repetitive, disorganised, or padded |
| **0** | Confusing, contradictory in structure, or hard to follow |

### 5.4 Attribution — weight 10%

Are citations placed where they belong?

| Score | Criteria |
|---|---|
| **2** | Citations follow the sentences they support; every substantive claim is attributed |
| **1** | Citations present but loosely placed, or some claims unattributed |
| **0** | Citations absent, or bearing no relation to the sentences they follow |

### Composite

```
response_quality = (accuracy   × 0.40
                  + completeness × 0.30
                  + clarity      × 0.20
                  + attribution  × 0.10) × 5      → 0–10
```

**Record all four sub-scores, not only the composite.** If an intervention moves
accuracy but not clarity, that is a finding — and a composite alone would hide it.

---

## 6. Machine scoring

- Same model as generation (`gpt-5.6-luna`), **temperature 0**
- Structured JSON output: `{relevance, accuracy, completeness, clarity, attribution, notes}`
- One answer per call. Never batch several answers into one prompt — scores
  drift toward each other when the model sees them together
- The rubric text above is pasted verbatim into the prompt. Do not paraphrase it
- Source documents are supplied alongside the answer, so accuracy and
  attribution can actually be checked
- The prompt is stored in the repository and versioned with the rubric

---

## 7. Human calibration — required, not optional

An automated judge is only credible if humans demonstrably agree with it.

**Sample.** 60 answers, stratified across queries and arms. Include some the
machine scored high and some it scored low, chosen before the graders see them.

**Procedure.** Two graders score independently, no discussion, using this
document only. Neither may be the person who wrote the optimised content —
that separation is not negotiable.

**Agreement.** Cohen's kappa on relevance (ordinal, 0/1/2) and on each quality
sub-score.

| Kappa | Reading | Action |
|---|---|---|
| ≥ 0.6 | Substantial | Proceed; report kappa |
| 0.4 – 0.6 | Moderate | Identify the disagreements, clarify the wording, re-version, re-score |
| < 0.4 | Poor | The rubric is the problem. Rewrite before any results are reported |

**Two rounds:** once on baseline answers, once on optimised answers. The second
round exists to show the judge did not drift in favour of the treatment.

Disagreements are **not** resolved by discussion and re-scoring — that inflates
agreement artificially. Record them, and if they cluster, fix the rubric.

---

## 8. How these metrics are reported

Relevance and response quality are **secondary endpoints**. The primary
endpoints remain PAWC and citation share, fixed before arms were run.

They answer a different question: *does optimisation degrade answer quality
while raising visibility?* An intervention that raises Flight Centre's citation
share while lowering accuracy is not a success, and without these metrics you
could not tell.

Report per arm: mean relevance, mean response quality, all four sub-scores, and
kappa for each round. Report any arm where quality falls while citation rises —
that is a finding in its own right.

---

## 9. Version history

| Version | Date | Change |
|---|---|---|
| 1.0 | — | Initial. Frozen before scoring. |
