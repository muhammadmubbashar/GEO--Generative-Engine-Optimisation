# Full project report
# Generative Engine Optimisation (GEO) — Flight Centre × QUT

**Team:** Flight Centre Travel Group × QUT Capstone Team 62 (IFN735 / IFN736)  
**Software:** `geo-bench-fc`  
**Date of this report:** 16 August 2026  
**Status:** Baseline locked. No Flight Centre page has been rewritten yet.

**Locked freeze:** `20260815_live_baseline_fixed_9b573c71`

Three measurement stages, all complete, never averaged:

| Stage | What it is | n |
|---|---|---|
| **Selection** | Would the AI open Flight Centre from the frozen title and snippet alone? | 500 decisions |
| **Reindexed** (open contest) | Snippet retrieval over the whole freeze, then write | 500 answers |
| **Fixed** (fair contest) | Whole pages from the Brave top-10 pack, then write | 300 answers |

`fixed` = cleaned **whole pages**. That is the current and only `fixed` result: named **38%**.

---

# PART A — What we are doing

## A1. The problem in plain language

Travellers increasingly type questions like “I’m looking for flights from Melbourne to London” into AI assistants (ChatGPT, Perplexity, Copilot) instead of only using Google.

Those assistants do not invent a brand out of nowhere. They:

1. look up the question in a search engine,
2. open a handful of web pages,
3. write a combined answer,
4. name a few sources.

Flight Centre is rarely one of those named sources. Competitors and “everyone else” (airlines, blogs, aggregators) usually are.

**Generative Engine Optimisation (GEO)** asks: if Flight Centre changes what is on its website, does the AI name Flight Centre more often?

That is this project.

## A2. The research question

**Does changing a travel brand’s web content measurably alter how often an AI answer engine retrieves and cites it?**

- Semester 1 asked *why* Flight Centre is weakly visible.
- Semester 2 measures *what a fix is worth*, with numbers, against real competitors.

## A3. What we will claim, and what we will not

**We will claim:** on this controlled engine, against a frozen competitor field, specified website changes change how often Flight Centre is retrieved and cited, by a measured amount — and which change is the best candidate for a live pilot.

**We will not claim:** “this is exactly what ChatGPT does in production,” or “do this and live ChatGPT share will rise by X%,” or that rewriting copy can fix search rank and crawl blocks by itself.

## A4. Why we built a laboratory instead of asking live ChatGPT

We cannot swap Flight Centre’s page inside live ChatGPT. ChatGPT reads the public web. If we changed a page live:

- competitors might also change that week,
- search rankings would move,
- the model is personalised and non-deterministic,
- we would not know whether *our* change caused any difference.

So we took a **photograph** of Australian search on a dated freeze, downloaded those pages, and built a working copy of an AI answer engine on that photograph. Later we will change **only Flight Centre** text. Competitor pages stay identical. Then any movement in citations can be attributed to us.

Everyday analogy: you cannot A/B-test a shop-window rewrite if the street, the neighbours, and the weather all change every night. You photograph the street, then you change only one window.

## A5. Two kinds of problem (do not mix them)

### Access problem (Type A)

Can the AI even **find and open** Flight Centre?

Examples: not in the search top 20; title/snippet not worth opening; page blocked from crawlers; real content hidden behind JavaScript.

If this fails, better FAQs never get read. On-page GEO cannot help until access improves.

**Who owns it:** mostly Flight Centre’s search/SEO/engineering. Search rank itself cannot be “fixed” inside this freeze (Brave results are locked). Crawlability of *the same URLs* can be tested later as “show the human-visible page.”

### Content problem (Type B)

The AI **did** read Flight Centre, sitting next to rivals. Did it still skip them?

Examples: thin copy, no facts, no FAQs, weak entity/authority signals, rivals simply more useful.

This is the lab where rewriting the page can be measured.

**Baseline already shows both.** Access fails often on “why use a travel agent” questions. Content fails on several flight questions where the whole Flight Centre page was in the reading pack and still never named.

## A6. The four gates (the design in one picture)

A traveller’s question has to pass four gates. Fail an early gate, later gates never happen. **Never average these four percentages into one number.** They are different problems with different owners.

| Gate | Everyday meaning | What we measure |
|---|---|---|
| 1. Search list | Are we even on the results page? | Flight Centre URL in Brave top 10 / top 20 |
| 2. Click | From the title and snippet alone, would the AI bother to open us? | P(open Flight Centre given it was listed) |
| 3. Read | Of everything captured, does the engine actually pull Flight Centre into the shortlist it will write from? | Open contest: snippet in top 5 |
| 4. Credit | Does the finished answer **name** Flight Centre, and how much of the answer is their voice? | Named rate, share of names, PAWC |

## A7. Three stages, never mixed

We run **three** locked measurements. A future website change is compared to baseline **inside one stage**. Subtracting one from another is invalid — they are not a treatment.

### Stage 1 — Selection (`geo select`)

**Question it answers:** “From the title and snippet alone, would the AI bother to open Flight Centre?”

How: the model sees the frozen Brave top-20 **titles and snippets only** (no page body, no live search). It picks up to 5 results it would open. Same 2×5 schedule as generation.

This is the ChatGPT Search–style gatekeeper. Future title / meta rewrites are measured here.

Runs on **all 50 questions** → **500 decisions**.

Result: Flight Centre is listed on 360/500 calls (72%). Of those, it is opened on **23%** (84/360). Median pick rank **3**. On agent-value questions: **0%**. Brave rank 1 does not guarantee a click (Q06, Q07, Q47 are #1 and still 0/10).

### Stage 2 — Open contest (`reindexed`)

**Question it answers:** “When everything in the photograph competes, does Flight Centre get chosen to read, then named?”

How: split all 953 freeze pages into overlapping ~350-word snippets (5,585 snippets). Search them with keyword matching plus meaning embeddings. Take the five best, at most two per brand. The model writes an answer from those five.

Runs on **all 50 questions** → **500 answers**.

### Stage 3 — Fair contest (`fixed`)

**Question it answers:** “If we already force the AI to read Flight Centre’s **whole page** next to the other top-10 pages, does it name them?”

How: for questions where Flight Centre is already in Brave’s top 10 with usable text, feed the cleaned **full page** of each of those ~10 URLs (cap 24,000 characters). Shuffle order. Write an answer. This matches Aggarwal / C-SEO Bench / AutoGEO (they feed whole documents).

Runs on **30 eligible questions** → **300 answers**. Named in **38%**.

If Flight Centre is missing from the top 10, this contest is **skipped**, not silently filled in. Those questions are access failures.

## A8. Who is in the study

**Named brands:** Flight Centre, Skyscanner, Webjet, Expedia (Australian market).

**Everyone else** (`other`): airlines, blogs, aggregators, Kayak, Booking, Google Flights. They share one label. They are not a fifth named brand. Adding Kayak would need a new freeze and a new baseline.

## A9. The questions

All main prompts are Flight Centre AU customer-style questions, plus a same-family expansion chosen **blind to results**.

**Primary (40) — flights consideration.** These are the confirmatory family.

Q01 flights to Melbourne  
Q02 Sydney → Melbourne  
Q03 Sydney → London  
Q04 Australia → London  
Q05 multi-city tickets  
Q06 Melbourne → London  
Q07 Perth → Bali  
Q08 Australia → United States  
Q09 business class  
Q10 Melbourne → Tokyo  
Q11 round the world  
Q12 flights to Perth  
Q13 Australia → Thailand  
Q14 Sydney → Tokyo  
Q15 flights to Brisbane  
Q16 flights to Sydney  
Q17 Melbourne → Sydney  
Q18 premium economy  
Q19 Australia → Vietnam  
Q20 Australia → Japan  
Q21 Australia → Bali  
Q22 Australia → Europe  
Q33 Sydney → Singapore  
Q34 Melbourne → Singapore  
Q35 Sydney → Auckland  
Q36 Australia → New Zealand  
Q37 Australia → Fiji  
Q38 Sydney → Los Angeles  
Q39 Brisbane → Auckland  
Q40 Perth → Singapore  
Q41 Australia → India  
Q42 Australia → Singapore  
Q43 flights to Adelaide  
Q44 flights to Cairns  
Q45 flights to Gold Coast  
Q46 flights to Hobart  
Q47 Darwin → Bali  
Q48 Adelaide → Melbourne  
Q49 first class  
Q50 last-minute Melbourne  

**Secondary (10) — agent-value / trust.** Reported separately. Do not pool with primary.

Q23 Why consult a travel professional instead of booking online?  
Q24 What unique services do travel consultants offer that DIY sites can’t match?  
Q25 How can a travel agent save me money on my trip?  
Q26 What makes a travel agency worth its service fee?  
Q27 When is it most beneficial to engage a professional agency versus self-booking?  
Q28 What questions should I ask a travel agent before booking?  
Q29 Who provides expert guidance on visas, health, and entry requirements?  
Q30 Why hire an agent for luxury or specialty travel?  
Q31 Advise on travel insurance options for a trip to Europe  
Q32 Find me a cheap flight from Canberra to Hong Kong  

**Held-out (7) — locked until the end.** Not used to choose methods.

H01 cheap flights from Sydney to Melbourne  
H02 Melbourne to London flights  
H03 business class flights from Australia  
H04 round the world airfare  
H05 flights from Australia to the USA  
H06 what’s the difference between non-stop, direct and connecting flights  
H07 what should I do if my flight is cancelled  

## A10. The photograph (freeze)

| Setting | Value |
|---|---|
| Engine | Brave Search |
| Region / language | Australia / English |
| Wording variants | 3 per question (to build the list, not counted as extra samples) |
| Capture | top 20 |
| Analyse | top 10 |
| Unique pages | 953 |
| Usable pages (≥200 words) | 688 |
| Snippets in the open-contest index | 5,585 |
| Baseline fetch | browser identity, **no JavaScript** |
| Thin / blocked pages | exact-URL Common Crawl, logged |
| Active freeze | `20260815_live_baseline_fixed_9b573c71` |

Q01–Q32 reuse Brave captures from 9–10 August 2026. Q33–Q50 were captured 15 August. Internally consistent. We **do not recapture Brave**.

## A11. How an answer is written and scored

1. Build the reading pack (open contest or fair contest).
2. Shuffle source order (controlled, same shuffle for the same seed×run so later website changes sit in the same seats).
3. Ask the model to write using the published GEO prompt. Every sentence must cite a source number like `[2]`.
4. Repeat **10 times per question** (2 starting points × 5 repeats) so one lucky answer cannot fool us.
5. Count: was Flight Centre in the pack, were they named, what share of names, how early, PAWC.
6. Judge quality with brand names hidden: on-topic 0–2; usefulness 0–10 (accuracy 40%, completeness 30%, clarity 20%, attribution 10%).
7. Reportable model: `gpt-5.6-luna`. Judge at temperature 0.

**PAWC (plain English):** of the words in the answer, how much is in sentences that name Flight Centre, with extra weight if they are named early. It is the published GEO paper’s visibility score. For executives, lead with **named %** and **share of names**. Keep PAWC for the academic comparison.

**Confirmatory statistics (when website changes exist):** primary questions, open contest, PAWC + share of names, Holm correction. Other tables are exploratory. Fair contest vs open contest is never a treatment effect.

## A12. Selection is a full stage, not a footnote

Same freeze, same 50 questions, same 2×5 schedule as `reindexed` and `fixed`. It does **not** write an answer. It only decides which of the frozen top-20 results to open from title+snippet.

That is why it sits beside the two generation contests, not inside them. Title/meta arms later compare to this baseline **inside selection**, not by mixing with `fixed` or `reindexed`.

## A13. Fairness checks (all passed)

| Test | Meaning |
|---|---|
| T1 Determinism | Repeat retrieval → identical snippets |
| T2 Fairness | Competitor freeze pages are byte-identical |
| T3 Isolation | Changing Flight Centre would not reshuffle competitor IDs/ranks |
| T4 Reproducibility | Rebuild snippets → identical IDs |

Protocol is locked. Changing experimental settings without a dated log entry voids comparability. Held-out cannot be run without an explicit final flag.

## A14. Planned website changes (none run yet)

Only Flight Centre may change. Competitors stay freeze bytes.

| Change | What it tests |
|---|---|
| Seat test (`position_control`) | Put FC first in the reading pack, change no words. Published research: seat beats wording. |
| Human-visible page (`ssr_visible`) | Same FC URLs, the text a person sees in a browser, not only crawler HTML. |
| Schema only | Structured data (papers did not test this). |
| FAQ structure only | Q&A markup. |
| Statistics | Add verified facts only. |
| Cite sources | Add real sources only. |
| Keyword stuffing | Negative control (papers say this fails). |
| Full combination | After singles; held-out last. |

## A15. Papers we follow

| Paper | Finding | What we copied |
|---|---|---|
| Aggarwal et al., GEO, KDD 2024 | Rewrites can raise visibility up to ~40% in their tests | Retrieve-then-write, their prompt, one source changed at a time, 5 answers × seeds, **whole documents** in generation |
| Puerto et al., C-SEO Bench, NeurIPS 2025 | Most rewrites barely work; reading-pack rank ~7.6× more influential | Seat test before copywriting |
| Wu et al., AutoGEO, ICLR 2026 | Same, with accuracy must not collapse | Verified facts only |

**Our extras:** one real brand vs real competitors; the brand’s own customer questions; HTML/FAQ/schema as future tests; a search freeze; a click gate; verified-facts-only (stricter than Aggarwal). A null result is still publishable.

---

# PART B — What we did, from the start

## B1. Semester 1 — diagnosis

Flight Centre is weakly visible in AI answers. A lot of what a human sees on FC pages lives behind client-side JavaScript, so a typical crawler never sees it. That is an access problem. It will be tested later as “human-visible page,” **not** by recapturing search.

## B2. Early Semester 2 — retired mini-web

First idea: a private four-brand sitemap corpus. **Retired.** The client study is live-search GEO. The freeze is the corpus. Old `corpus/` is archival only.

## B3. 10 August 2026 — Freeze v1 (void)

Brave AU freeze, 32 questions. Baseline answers were generated and judged. **Those scores must not be quoted.** An audit found two bugs: on the fair contest, stored brand labels did not match the shuffled source numbers the model actually used; the judge was shown texts in the wrong order. Archived. Do not mix with current numbers.

## B4. 13–15 August 2026 — protocol hardened

- Two contests locked; live generation retired.
- Protocol lock, snippet size cap, retrieval rules pinned.
- Click-from-title stage added.
- 18 more flight questions (Q33–Q50) added **blind to results**, then frozen as one 50-query corpus so the open-contest index is not patched.

## B5. 15 August 2026 — Freeze v2 (the study corpus)

Freeze `20260815_live_baseline_fixed_9b573c71`:

- 50 questions
- 953 pages, 688 usable
- 5,585 snippets
- routing: 30 in top 10, 6 in 11–20, 14 missing
- controls T1–T4 passed
- **selection:** 500 title+snippet decisions, judged as a third stage
- **reindexed:** 500 answers, judged
- **fixed:** 300 whole-page answers, judged
- bot-crawler probe and Bing comparison completed

## B6. 16 August 2026 — `fixed` locked as whole pages

`fixed` feeds cleaned **full pages** (paper protocol). 300/300 judged. Named **38%**. Mean seat 5.3. `reindexed` and **selection** unchanged.

**No optimisation arm has been run.**

## B7. Completed vs not

**Done:** questions; freeze; QC; lock; routing; index; four lab checks; **selection 500**; **reindexed 500**; **fixed 300 whole-page**; counted metrics + PAWC; quality judge; bot probe; Bing table; human-check sheets exported.

**Not done:** two people filling the human-check sheets; any website rewrite; seat test / human-visible page / FAQ / stats / sources / stuffing / full stack; held-out run; implementation guide for the web team.

---

# PART C — All locked results, with explanation

## C1. Headline

Flight Centre’s problem is **visibility**, not answer quality.

| Finding | Number | What it means |
|---|---|---|
| Named in the open contest | **9%** of 500 answers | When everything competes, FC almost never gets the credit |
| Named in the fair contest | **38%** of 300 answers | Even after we force the whole page into the pack, skipped more than half the time |
| Everyone else’s share in the fair contest | **67.5%** | Airlines, blogs, aggregators take most names — not mainly the three OTAs |
| On-topic score | **2.00 / 2** every answer | The quality rubric is too easy; do not treat this as a GEO win |

**Explanation.** The AI writes decent travel answers. It rarely gives Flight Centre the credit. Sometimes it never even looks. Rewriting the homepage tomorrow cannot fix questions where Flight Centre never enters the search list. Rewriting *can* be measured on the 30 questions where the page is already in the pack — and even there, 38% is the starting line, not a success.

## C2. Four gates (do not average)

| Gate | FC rate | Sample | Explanation |
|---|---|---|---|
| Search list — top 10 | **60%** (30/50) | 50 questions | Six in ten questions, Brave already lists FC in the first 10. Access is not zero. |
| Search list — top 20 | **72%** (36/50) | 50 questions | Another 6 questions are “almost in.” 14 questions never appear. |
| Click from title | **23%** | 84 of 360 times FC was listed | Even when listed, the title/snippet is usually not chosen to open. Median pick rank 3 when it is chosen. Title/meta is a real leak. |
| Open contest — read | **20%** | 500 answers | Being in Brave’s top 10 does not mean our snippet engine picks FC. Search rank ≠ passage rank once everyone else is in the pile. |
| Open contest — named | **9%** | 500 answers | Of the times it is read, it is still not always named. Overall, named in fewer than 1 in 11 answers. |
| Fair contest — in pack | **100%** by design | 300 answers, 30 questions | We only run this where FC is already in the top 10. |
| Fair contest — named | **38%** | 300 answers | Content problem: the page was read and still unused 62% of the time. |

**Do not say “average visibility is 30%.”** Gate 1 is a search-team problem. Gate 2 is a title problem. Gates 3–4 are retrieval and copy.

## C3. Full scorecard

Primary = 40 flight questions. Secondary = 10 agent-value questions. Fair contest only on 30 eligible questions.

| Metric | Open all 50 | Open flights 40 | Open agent 10 | Fair 30 | Fair flights 29 | What it means |
|---|---:|---:|---:|---:|---:|---|
| Answers | 500 | 400 | 100 | 300 | 290 | 10 per question |
| FC read / in pack | **20%** | **20%** | **20%** | **100%** | **100%** | Open contest rarely reads FC; fair contest always does |
| FC named | **9%** | **11%** | **0%** | **38%** | **37%** | Agent family: never named in the open contest |
| Share of names | **2.3%** | **2.9%** | **0.0%** | **6.7%** | **6.6%** | Even when named, FC is a small slice of the answer |
| PAWC | **0.0087** | **0.0108** | **0.0000** | **0.0234** | **0.0237** | Paper visibility score; still very small |
| Name position when named | 3.6 | 3.6 | never | 4.9 | 4.9 | Named late, not first |
| Seat in reading pack | 2.8 | 2.9 | 2.1 | 5.3 | 5.3 | Fair contest: typically mid-pack (slot ~5 of 10) |
| Named given it was read | 44% | 55% | 0% | 38% | 37% | Reading ≠ naming |
| Named given seat in first 3 | 42% | 61% | 0% | **60%** | 59% | When seated early in the fair contest, named 60% — supports the seat test |
| Monopoly answers | 10% | 0% | 50% | 0% | 0% | Half of agent-value open-contest answers have only one brand in the pack (coverage monopoly) |
| Brave top 10 | 30/50 | 29/40 | 1/10 | n/a | n/a | Agent-value almost invisible in search |
| Brave top 20 | 36/50 | 34/40 | 2/10 | n/a | n/a | 8 of 10 agent questions never appear |
| On-topic | 2.00 | 2.00 | 2.00 | 2.00 | 2.00 | Ignore as a GEO outcome |
| Usefulness / 10 | 8.16 | 8.23 | 7.88 | 7.82 | 7.81 | Answers are fine; FC is invisible |

Only Q32 from the agent family is fair-contest eligible (10 answers). Do not pool.

## C4. Selection results (third stage)

Same 50 questions × 10 repeats = **500 decisions**. The model sees only frozen titles and snippets. It does not read the page.

| Slice | Calls | FC listed in top 20 | Opened given listed | Opened of all calls | Median pick rank |
|---|---:|---:|---:|---:|---:|
| All 50 | 500 | 360 (72%) | **23%** (84/360) | 17% | 3 |
| Flights 40 | 400 | 340 (85%) | **25%** (84/340) | 21% | 3 |
| Agent-value 10 | 100 | 20 (20%) | **0%** (0/20) | 0% | never |

Always opened (10/10): Q11 round the world, Q12 Perth, Q18 premium economy, Q44 Cairns, Q49 first class.

Never opened despite being listed: including Brave **#1** rows Q06 Melbourne–London, Q07 Perth–Bali, Q47 Darwin–Bali; also Q14, Q15, Q19, Q32, Q34, Q38, Q40, Q42, Q43, Q45, Q48 and the rank 11–20 rows.

Agent-value: Q28 and Q32 are listed and still **0/10**.

**Explanation.** Selection is a full experimental stage, not a side check. A #1 search rank can still lose the click. Title/meta rewrites compare to **this** baseline, inside selection, not by mixing with `fixed` or `reindexed`.

## C5. Who gets the citations — and why this matters

| Brand | Open names | Share of 3,713 | Fair names | Share of 2,926 |
|---|---:|---:|---:|---:|
| Everyone else | 1,986 | 53.5% | 1,976 | **67.5%** |
| Skyscanner | 1,075 | 29.0% | 543 | 18.6% |
| Webjet | 285 | 7.7% | 164 | 5.6% |
| Expedia | 272 | 7.3% | 65 | 2.2% |
| **Flight Centre** | **95** | **2.6%** | **178** | **6.1%** |

**Explanation.** The instinct “Skyscanner is killing us” is incomplete. In the fair contest, **two-thirds of names go to everyone else** — Qantas-style airline pages, blogs, aggregators, Kayak/Booking/Google Flights sitting in `other`. GEO that only “beats Webjet” can still lose the answer. Any rewrite has to be more citable than that whole field.

In the open contest Skyscanner is stronger (29%) because snippet retrieval likes their pages. In the fair contest, once full pages are in, everyone else dominates even more.

## C6. Fair contest by question — with explanation

10 answers each. Restricted to the 30 questions where FC is in Brave top 10 with usable text.

### Never named (0/10) — content failure

The page **was in the prompt**. The model still never named Flight Centre.

| ID | Question | Seat | Explanation |
|---|---|---:|---|
| Q01 | flights to Melbourne | 4.1 | Generic destination query; rival hubs/OTAs/airlines are enough; FC adds no unique fact |
| Q03 | Sydney → London | 6.2 | Long-haul; many strong airline/OTA pages; FC seated late (~6) |
| Q07 | Perth → Bali | 5.2 | High-competition leisure route |
| Q40 | Perth → Singapore | 6.2 | Same pattern; seated late |

These are the cleanest Type-B targets: access already happened.

### Almost always named (80–100%)

| ID | Question | Named | Share | Explanation |
|---|---|---:|---:|---|
| Q09 | business class | 100% | 23.7% | Cabin pages are a Flight Centre strength; unique inventory/wording |
| Q45 | Gold Coast | 90% | 24.3% | Destination hub where FC copy is used |
| Q22 | Australia → Europe | 90% | 9.6% | Broad long-haul; FC still named often but share is smaller (many co-citations) |
| Q49 | first class | 90% | 19.6% | Same cabin-page pattern as Q09 |
| Q11 | round the world | 80% | 17.7% | Product FC actually sells; rivals thinner |
| Q43 | Adelaide | 80% | 22.4% | Destination hub |

**Explanation.** GEO is not uniform. Cabin and some destination hubs already get named. Commodity routes (Melbourne, Sydney–London, Bali, Singapore) do not. Optimisation should not be judged on Q09 alone.

### Weak but not zero (10–40%)

Q02 30% · Q05 30% · Q06 30% · Q10 20% · Q14 20% · Q15 40% · Q16 40% · Q17 40% · Q18 70% · Q19 10% · Q32 60% · Q33 20% · Q34 10% · Q35 10% · Q38 10% · Q42 10% · Q46 50% · Q47 10% · Q48 30%.

**Explanation.** Premium economy (Q18 70%) behaves more like cabin queries. Many Asia/NZ routes sit at 10%: the page is present, almost unused. Q32 (Canberra–Hong Kong) is the only agent-family question in this contest (60%) — a hard route, not a “why use an agent” prompt.

Full table:

| ID | Intent | Named | PAWC | Share | Seat |
|---|---|---:|---:|---:|---:|
| Q01 | flights to Melbourne | 0% | 0.000 | 0.0% | 4.1 |
| Q02 | Sydney → Melbourne | 30% | 0.008 | 3.3% | 4.1 |
| Q03 | Sydney → London | 0% | 0.000 | 0.0% | 6.2 |
| Q05 | multi-city | 30% | 0.016 | 2.7% | 5.2 |
| Q06 | Melbourne → London | 30% | 0.015 | 2.0% | 5.2 |
| Q07 | Perth → Bali | 0% | 0.000 | 0.0% | 5.2 |
| Q09 | business class | 100% | 0.044 | 23.7% | 5.3 |
| Q10 | Melbourne → Tokyo | 20% | 0.005 | 1.9% | 5.3 |
| Q12 | flights to Perth | 70% | 0.074 | 16.5% | 6.2 |
| Q11 | round the world | 80% | 0.082 | 17.7% | 5.2 |
| Q14 | Sydney → Tokyo | 20% | 0.006 | 2.3% | 4.1 |
| Q15 | flights to Brisbane | 40% | 0.019 | 6.4% | 5.8 |
| Q16 | flights to Sydney | 40% | 0.019 | 5.5% | 6.2 |
| Q17 | Melbourne → Sydney | 40% | 0.014 | 4.4% | 4.1 |
| Q18 | premium economy | 70% | 0.048 | 13.9% | 5.2 |
| Q19 | Australia → Vietnam | 10% | 0.005 | 0.8% | 4.4 |
| Q22 | Australia → Europe | 90% | 0.026 | 9.6% | 6.2 |
| Q32 | Canberra → Hong Kong | 60% | 0.017 | 8.3% | 4.4 |
| Q33 | Sydney → Singapore | 20% | 0.004 | 1.5% | 4.6 |
| Q34 | Melbourne → Singapore | 10% | 0.000 | 0.7% | 5.3 |
| Q35 | Sydney → Auckland | 10% | 0.000 | 1.1% | 5.3 |
| Q38 | Sydney → Los Angeles | 10% | 0.003 | 0.7% | 7.9 |
| Q40 | Perth → Singapore | 0% | 0.000 | 0.0% | 6.2 |
| Q42 | Australia → Singapore | 10% | 0.000 | 0.8% | 5.3 |
| Q43 | Adelaide | 80% | 0.088 | 22.4% | 5.8 |
| Q45 | Gold Coast | 90% | 0.122 | 24.3% | 5.8 |
| Q46 | Hobart | 50% | 0.039 | 6.8% | 5.3 |
| Q47 | Darwin → Bali | 10% | 0.000 | 0.8% | 5.2 |
| Q48 | Adelaide → Melbourne | 30% | 0.011 | 2.8% | 4.1 |
| Q49 | first class | 90% | 0.039 | 19.6% | 5.3 |

Q38 seat 7.9 is unusually late — consistent with 10% named. When FC sits first-three in this contest, named rate is 60% (n=106). That is why the **seat test** is first.

## C7. Open contest — only 10 questions ever surface Flight Centre

The other **40 never retrieve FC**, including several where Brave ranked FC in the top 10.

| ID | Intent | Family | Read | Named | Explanation |
|---|---|---|---:|---:|---|
| Q05 | multi-city | flights | 10/10 | 6/10 | Product pages match the query; still not always named |
| Q11 | round the world | flights | 10/10 | 10/10 | Strongest open-contest row: retrieved and always named |
| Q12 | flights to Perth | flights | 10/10 | 10/10 | Same |
| Q18 | premium economy | flights | 10/10 | 10/10 | Cabin inventory |
| Q19 | Australia → Vietnam | flights | 10/10 | 4/10 | Read every time; named only 4/10 |
| Q25 | agent saves money | agent | 10/10 | **0/10** | Retrieved, never credited — access happened, content/coverage failed |
| Q28 | questions for an agent | agent | 10/10 | **0/10** | Same |
| Q34 | Melbourne → Singapore | flights | 10/10 | **0/10** | Read every time, never named |
| Q35 | Sydney → Auckland | flights | 10/10 | **0/10** | Same |
| Q42 | Australia → Singapore | flights | 10/10 | 4/10 | Read always, named 4/10 |

**Explanation.** On-page GEO cannot create citations the retriever never surfaces. For the 40 questions with 0/10 retrieval, the next lever is search rank, title/snippet, or crawl — not FAQs. For Q34/Q35/Q25/Q28, retrieval already happened and naming still failed — those can be content tests on the open contest too.

## C8. Access map of all 50 questions

| Mode | n | Questions | What to do |
|---|---:|---|---|
| Never in top 20 | 14 | Q04, Q08, Q20, Q23, Q24, Q25, Q26, Q27, Q29, Q30, Q31, Q36, Q37, Q41 | Search/coverage. On-page GEO cannot help on this freeze. |
| Top 20 but outside top 10 | 6 | Q13 (19), Q21 (19), Q28 (11), Q39 (15), Q44 (11), Q50 (19) | Sensitive to how deep the engine reads. Title/snippet and rank 11→10 matter. |
| In the top-10 pack | 30 | remaining flights + Q32 | Content lab. Whole-page rewrite is measurable here. |

| Slice | n | Top 10 | Top 20 | Missing | Explanation |
|---|---:|---:|---:|---:|---|
| All | 50 | 60% | 72% | 28% | Overall, FC is often listed on flight queries |
| Flights (40) | 40 | 72% | 85% | 15% | Access is mostly OK for booking questions |
| Agent-value (10) | 10 | 10% | 20% | **80%** | “Why use an agent” is a coverage monopoly for non-brand sites. Do not mix into the flight family. |

Brave rank (1 = best):  
Q01 3 · Q02 3 · Q03 4 · Q04 — · Q05 1 · Q06 1 · Q07 1 · Q08 — · Q09 5 · Q10 5 · Q11 1 · Q12 4 · Q13 19 · Q14 3 · Q15 7 · Q16 6 · Q17 3 · Q18 1 · Q19 8 · Q20 — · Q21 19 · Q22 2 · Q23 — · Q24 — · Q25 — · Q26 — · Q27 — · Q28 11 · Q29 — · Q30 — · Q31 — · Q32 8 · Q33 9 · Q34 5 · Q35 10 · Q36 — · Q37 — · Q38 2 · Q39 15 · Q40 4 · Q41 — · Q42 5 · Q43 6 · Q44 11 · Q45 4 · Q46 10 · Q47 1 · Q48 3 · Q49 5 · Q50 19.

**Explanation.** Several #1 Brave ranks (Q05, Q06, Q07, Q11, Q18, Q47) still do not guarantee open-contest retrieval or fair-contest naming (Q07 is Brave #1 and fair-contest 0%). Rank is necessary, not sufficient.

## C9. Selection by question (10 decisions each)

Opened / 10 when listed. `—` = not in the frozen top 20.

Q01 7 · Q02 2 · Q03 4 · Q04 — · Q05 2 · Q06 **0** (Brave #1) · Q07 **0** (Brave #1) · Q08 — · Q09 3 · Q10 1 · Q11 **10** · Q12 **10** · Q13 0 (rank 19) · Q14 0 · Q15 0 · Q16 4 · Q17 2 · Q18 **10** · Q19 0 · Q20 — · Q21 0 (rank 19) · Q22 7 · Q23–Q27 — · Q28 0 (rank 11) · Q29–Q31 — · Q32 0 · Q33 0 · Q34 0 · Q35 0 · Q36 — · Q37 — · Q38 0 (rank 2) · Q39 0 (rank 15) · Q40 0 · Q41 — · Q42 0 · Q43 0 · Q44 **10** (rank 11) · Q45 0 · Q46 2 · Q47 **0** (Brave #1) · Q48 0 · Q49 **10** · Q50 0 (rank 19).

Q44 is rank 11 and still opened every time — title/snippet can beat rank. Q06/Q07/Q47 are rank 1 and never opened.

## C10. Quality scores — what actually varies

| Subscore | Open 500 | Fair 300 | Explanation |
|---|---|---|---|
| On-topic | 500 × 2 | 300 × 2 | Rubric too easy for underspecified “I’m looking for flights…” prompts. **Not a GEO endpoint.** |
| Accuracy | 0: 7; 1: 385; 2: 108 | 0: 18; 1: 258; 2: 24 | This *does* move. Fair contest slightly worse (longer, noisier pages). |
| Completeness | 1: 33; 2: 467 | 1: 10; 2: 290 | Mostly complete |
| Clarity | 500 × 2 | 300 × 2 | Stuck at max; ignore |
| Usefulness mean | 8.16 | 7.82 (4.0–10.0) | Fine answers; visibility is the gap |

Human agreement (two graders, κ ≥ 0.6) is **pending**. Until then, judged quality is secondary. Counted named-rate / share / PAWC are the GEO outcomes.

## C11. Corpus and crawlers

| Brand | Pages | Usable | As a ChatGPT crawler |
|---|---:|---:|---|
| Flight Centre | 52 | 52/52 | ≈ browser (~1,060 words) |
| Webjet | 39 | 39/39 | ≈ browser |
| Skyscanner | 77 | 75/77 | HTTP 200, often a 1-word empty shell |
| Expedia | 31 | 15/31 | 31/31 blocked, 0 words |
| Everyone else | 754 | 507/754 | mixed |
| **Total** | **953** | **688/953** | freeze used a **browser** identity |

Thin packs: Q28 (3 pages), Q30 (4 pages). Thin pages are flagged, not deleted.

**Explanation.** Our photograph used a normal browser, so Skyscanner and Expedia look **stronger** than a real GPTBot/OAI-SearchBot would see. Flight Centre’s citation deficit is therefore **conservative** (the real bot gap may be even more in FC’s favour on those two rivals, and still FC loses). Do not claim “we simulated ChatGPT’s crawler.” We simulated a browser-visible web, then probed the bot gap separately.

## C12. Bing (descriptive only)

Bing AU vs Brave, 50/50 questions returned. FC in **both** engines’ top 10 on **21** questions. Never pooled with Brave. Bing’s API is retired; this is a one-off “are we only seeing a Brave quirk?” check. Overlap 21/50 says the access pattern is not unique to Brave, but ranks differ query by query.

## C13. What the results mean for optimisation

1. **Seat test first** (fair contest). Mean seat 5.3. When in first three, named 60%. Change no words. If this does not move PAWC/share, wording will struggle (C-SEO finding).
2. **Human-visible FC pages next.** Same URLs. Do not recapture Brave. Do not render competitors.
3. **Then rewrite** statistics, sources, FAQs on the **whole** FC page — now measurable.
4. **Title/snippet** can be tested on the click gate without a new freeze.
5. **Do not** treat agent-value questions as a writing contest until they appear in search.
6. **Held-out last.**

---

# PART D — Design of the experiment (complete specification)

This is the design, written so someone who has never seen the code can understand the logic.

**Aim.** Measure whether Flight Centre website changes change AI retrieval and citation, holding the rest of the web still.

**Units.** One customer question is the unit. Ten answers per question are averaged before any statistical test (no pretending 500 answers are 500 independent questions).

**Population of questions.** 50 client-style prompts: 40 flight (confirmatory), 10 agent-value (exploratory, separate). 7 held-out unused until the end.

**Intervention.** Only Flight Centre HTML/text for freeze URLs. Competitors frozen. Search lists frozen.

**Controls.** Same questions, same competitor bytes, same model, same prompt, paired shuffles, four lab tests, protocol lock, brand-masked judge.

**Outcomes.**

- Primary confirmatory (later, when arms exist): open contest, flight questions, PAWC and share of names.
- Always reported: named rate (inclusion), gates 1–4, fair contest as the content lab, agent-value separately.
- Quality: usefulness and accuracy; on-topic is recorded but known to be collapsed.

**Three stages.** Selection = would-open from title+snippet. Open contest (`reindexed`) = retrieval + generation. Fair contest (`fixed`) = generation from a forced whole-page pack. Never subtract them.

**Blinding.** Judge does not see brand names. Expansion queries chosen blind to results. Held-out locked.

**Stopping rule for this phase.** Baseline locked when freeze verified, routing done, 2×5 selection + reindexed + fixed complete, controls passed. That is now true. Arms start only after this lock.

**Limitations (stated up front).**

- Not production ChatGPT.
- Freeze is dated (August 2026 Brave AU).
- Browser fetch overstates some rivals vs a real AI crawler.
- `other` cap (at most 2 of 5 open-contest slots) slightly inflates named-brand visibility; constant across arms, so arm-vs-baseline is still valid; absolute % is optimistic for study brands.
- Same model family judges its own answers; human κ pending.
- Verified-facts-only is stricter than the original GEO paper (conservative).
- n = 40 flight questions: large consistent effects can be seen; small mixed effects may look null.

---

# PART E — Bottom line

The laboratory exists. The photograph is locked. The starting line is measured on 50 questions, 800 judged answers, and 500 click decisions.

Flight Centre is often on the search list, rarely opened from the title, rarely chosen in the open contest, and still skipped more than half the time even when the whole page is in the reading pack.

**That is the baseline.** The next report is the first website change on this same freeze.

---

# PART F — Detailed prompt for the design experiment

Paste everything in the box below into a video tool, Gamma, or another AI, and ask it to produce the design-experiment explainer. Numbers are locked. Do not let the tool invent metrics.

```
DETAILED DESIGN-EXPERIMENT PROMPT
Flight Centre × QUT  |  Generative Engine Optimisation (GEO) baseline
Audience: executives and sponsors who do not know AI retrieval.
Task: explain HOW THE EXPERIMENT IS DESIGNED, then show WHAT WE FOUND.
Do not pitch. Do not invent numbers. Do not say we already rewrote the website.

============================================================
0. ROLE AND STYLE
============================================================
You are a motion-design director + science communicator.

Length: 3 minutes 30 seconds if video; or 18 slides if a deck.
Format: 16:9, kinetic infographic, paper cut-out search cards, one traveller
silhouette, a four-gate funnel. Flight Centre red / white / charcoal, QUT blue
accent. No robot faces, no Matrix code, no stock-photo montages, no fake
ChatGPT UI that implies this IS ChatGPT.

Voice: calm Australian English. One idea per shot. Every on-screen number
must match the voiceover. If a technical word appears, gloss it in the same
sentence.

Forbidden unless instantly translated: PAWC, reindexed, fixed, BM25, RRF,
JSONL, Type A, Type B, freeze ID. Use instead: open contest, fair contest,
access problem, content problem, photograph of search, named, reading pack.

============================================================
1. WHAT THIS PROJECT IS (0:00–0:25)
============================================================
Title: “When someone asks AI for flights, who gets named?”
Subtitle: “GEO baseline  |  Flight Centre × QUT  |  Starting line, not finish”

Narration:
People type “I’m looking for flights from Melbourne to London” into AI
assistants. The AI reads a few web pages and names a few sources. Flight
Centre is rarely one of them. This project asks: if Flight Centre changes
its website, does the AI name them more often? We have measured the
starting line. We have not rewritten any page yet.

Visual: traveller → question bubble → AI answer card with three source chips
(airline, blog, Skyscanner-style) and a dashed empty chip “Flight Centre?”

============================================================
2. WHY A LAB, NOT LIVE CHATGPT (0:25–0:50)
============================================================
Narration:
We cannot swap Flight Centre’s page inside live ChatGPT. The live web
moves every day. Competitors change. We would never know what caused a
difference.

So we took a photograph of Australian search, downloaded those pages, and
built a working copy of an AI answer engine on that photograph. Later we
will change only Flight Centre. Neighbours stay frozen.

Visual: left = shuffling live web with a red X. Right = camera shutter
locks a stack of result cards. Padlock. Caption: “15 August 2026 · Australia
· 953 pages · 50 questions.”

Do not claim this is production ChatGPT. Caption: “A controlled copy of
retrieve-then-write. Ranking what to pilot live.”

============================================================
3. THE FOUR GATES — THIS IS THE DESIGN (0:50–1:35)
============================================================
This is the heart of the design experiment. Draw a funnel. 50 balls
(questions) fall through four trays. Never average the four percentages.

Gate 1 — SEARCH LIST
“Are we even on the results page?”
Flight Centre in Brave top 10: 30 of 50 = 60%.
Top 20: 36 of 50 = 72%.
Missing entirely: 14 of 50 = 28%.

Split the tray:
Flight booking questions (40): 72% top 10, 85% top 20.
Why-use-an-agent questions (10): 10% top 10, 20% top 20, 8 of 10 missing.
Caption: “Do not mix these two families.”

Gate 2 — SELECTION (third locked stage, 500 decisions)
“From the title and snippet alone, would the AI bother to open us?”
Same 50 questions × 10 repeats as the other two stages.
Flight Centre listed on 360/500 calls (72%). Opened on 23% of those (84/360).
Flights 25%. Agent-value 0%. Median pick rank 3.
Brave #1 can still lose the click (Melbourne–London, Perth–Bali, Darwin–Bali:
rank 1, opened 0/10). Cairns is rank 11 and opened 10/10.
Caption: “Selection is its own experiment. A weak title loses before the page
is read. Title/meta changes are measured here, not mixed with the other two.”

Gate 3 — READ
Three stages total. After selection, two generation contests as parallel pipes.
Never subtract them.

OPEN CONTEST / reindexed (left pipe):
“When everything in the photograph competes, does the engine pull a
Flight Centre snippet into the five pages it will write from?”
Method: 5,585 snippets from 953 pages; pick five; at most two per brand.
Result: Flight Centre is read in 20% of 500 answers.
Only 10 of 50 questions ever surface them.
Caption: “Search rank is not the same as being chosen to read.”

FAIR CONTEST / fixed (right pipe):
“If we already force the AI to read Flight Centre’s WHOLE PAGE next to
the other top-10 pages, does it name them?”
Runs only on 30 questions where Flight Centre is already in the top 10.
300 answers. Whole pages. Matches the published research papers.
Named in 38%.
Caption: “This is the content laboratory.”

Gate 4 — CREDIT
“Does the finished answer name Flight Centre?”
Open contest: named in 9% of 500 answers (11% on flight questions, 0% on
agent questions).
Fair contest: named in 38% of 300 answers — still skipped more than half
the time.
Share of all names: 2.3% open contest, 6.7% fair contest.
When they are named, it is late (about 4th–5th mention).
In the fair contest the page usually sits around seat 5 of 10. When it
sits in the first three seats, it is named 60% of the time.
Caption: “Reading is not naming. Seat matters.”

Big caption under the funnel:
“Fail an early gate, later gates never get a chance.”

============================================================
4. HOW WE KEPT IT FAIR (1:35–2:05)
============================================================
Icons left to right, one beat each:

- 50 real customer questions (40 flight, 10 agent-value)
- 7 extra questions locked in a vault until the very end
- 4 named brands + everyone else (airlines, blogs, aggregators)
- Photograph: 953 pages, 688 with enough text
- Selection, reindexed, and fixed each asked 10 times per question
- Same competitor pages every time
- Quality scores hide brand names
- Four lab checks: all passed
- Only Flight Centre will later change

Caption: “Same questions. Same neighbours. Same model. Three stages. One window changes.”

============================================================
5. TWO PROBLEMS, TWO OWNERS (2:05–2:20)
============================================================
Two doors.

ACCESS door: “Can AI find and open us?”
14 questions never in the top 20. Agent-value 8/10 missing. Title opened
only 23%. You cannot FAQ your way through a locked door.

CONTENT door: “Once they read us, do they name us?”
Four questions had the whole Flight Centre page in the pack and still
named them 0 of 10 times: flights to Melbourne, Sydney–London, Perth–Bali,
Perth–Singapore.
Cabin and some hubs already work: business class 100%, Gold Coast 90%,
first class 90%, round the world 80%.

Caption: “Access is the bigger commercial gate. Content is what this lab
can test next.”

============================================================
6. WHO GETS THE CREDIT (2:20–2:40)
============================================================
Stacked bar, fair contest, 2,926 names:

Everyone else 67.5%  (wide grey)  — airlines, blogs, aggregators
Skyscanner     18.6%
Flight Centre   6.1%  (thin red)
Webjet          5.6%
Expedia         2.2%

Caption: “We are not mainly losing to Skyscanner, Webjet and Expedia.
We are losing to the rest of the web.”

Second small bar, open contest, 3,713 names:
everyone else 53.5%, Skyscanner 29.0%, Webjet 7.7%, Expedia 7.3%,
Flight Centre 2.6%.

============================================================
7. QUALITY IS NOT THE ISSUE (2:40–2:50)
============================================================
Giant 8/10 usefulness. Tiny footnote: on-topic score is maxed on every
answer — the rubric is too easy; ignore it. Accuracy is not perfect.
Two humans have not yet double-checked a sample.

Caption: “The AI writes a decent travel answer. Flight Centre is invisible.”

============================================================
8. CRAWLER FOOTNOTE (2:50–3:00)
============================================================
One line, do not over-claim:
Our photograph used a normal browser. A real ChatGPT crawler: Expedia
blocked 31 of 31 pages; Skyscanner often returns an empty shell; Flight
Centre looks similar to a browser. Rivals in our lab look stronger than
a real bot might see. Flight Centre’s gap is conservative.

============================================================
9. WHAT HAPPENS NEXT (3:00–3:20)
============================================================
Roadmap, three arrows, none completed:

1. SEAT TEST — put Flight Centre first in the reading pack, change no
   words. (Published research: seat beats wording.)
2. SHOW THE HUMAN PAGE — same Flight Centre URLs, the text a person sees.
   Do not recapture search. Do not change competitors.
3. THEN REWRITE — facts, sources, FAQs on the whole page.

Vault: held-out questions stay locked until the end.
Red box: “We are not claiming live ChatGPT lift. We are ranking what to
pilot.”
Grey box: “No page has been rewritten yet.”

============================================================
10. END CARD (3:20–3:30)
============================================================
Three numbers only:

9%   named in the open contest
38%  named when the whole page was already in the pack
67.5% of fair-contest credit goes to everyone else

Line: “Starting line. Visibility, not quality.”
Wordmark: Flight Centre × QUT  |  Freeze locked  |  Optimisation next

============================================================
LOCKED NUMBERS — DO NOT CHANGE, DO NOT ADD
============================================================
Freeze: 20260815_live_baseline_fixed_9b573c71
50 questions, 10 answers each
953 pages, 688 usable, 5,585 snippets
Search: 60% top 10, 72% top 20
Flights 40: 72% / 85%. Agent 10: 10% / 20%, 8/10 missing
Click: 23% of listed calls, median rank 3
Open contest 500 answers: read 20%, named 9% (flights 11%, agent 0%),
share 2.3%, PAWC 0.0087
Fair contest 300 answers, 30 questions, WHOLE PAGES: named 38%
(flights 37%), share 6.7%, PAWC 0.0234, seat 5.3
When fair-contest seat in first 3: named 60%
Selection 500: listed 72%, opened given listed 23% (flights 25%, agent 0%),
median rank 3. Always 10/10: Q11, Q12, Q18, Q44, Q49. Rank-1 never opened:
Q06, Q07, Q47.
Open citation mass: other 1986, Skyscanner 1075, Webjet 285, Expedia 272,
FC 95 (n=3713)
Fair citation mass: other 1976, Skyscanner 543, FC 178, Webjet 164,
Expedia 65 (n=2926)
Zero-name fair contest: Q01, Q03, Q07, Q40
Strong fair contest: Q09 100%, Q22 90%, Q45 90%, Q49 90%, Q11 80%, Q43 80%
Open contest only 10 queries retrieve FC: Q05, Q11, Q12, Q18, Q19, Q25,
Q28, Q34, Q35, Q42
Quality: on-topic 2.00 all; usefulness 8.16 open / 7.82 fair
Bot probe: Expedia 31/31 blocked; Skyscanner 1-word shell
Bing: 50/50, FC top-10 overlap 21 (descriptive only)
Optimisation: not started
Held-out: locked

============================================================
SLIDE/SHOT CHECKLIST (if building a deck instead of video)
============================================================
1 Title
2 The traveller’s question
3 Why not live ChatGPT
4 Four gates overview
5 Gate 1 search list + flights vs agent
6 Gate 2 selection (500 decisions)
7 Gate 3 reindexed + fixed explained
8 Gate 4 named 9% vs 38%
9 How we kept it fair
10 Access vs content doors
11 Who gets the credit (stacked bars)
12 Zero-name vs cabin-hub questions
13 Quality is not the issue
14 Crawler footnote
15 Done vs not done
16 Next: seat, human page, rewrite
17 What we claim / do not claim
18 End card 9% / 38% / 67.5%
```
