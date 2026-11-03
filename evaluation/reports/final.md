# Evaluation report, Week 7 (final.md draft)

Task: W7-D5-LDN-1. Status: **draft for review** (FAO reviews the numbers against the run files, W7-D5-FAO-1). Drafted with AI assistance (Claude); LDN is responsible for the final text.

Every number below comes from a stored file in the repository. Paragraphs marked **Measured** report a result with its sample size. Paragraphs marked **Interpretation** say what the team thinks the result means; they are not measurements and may be wrong. The plan these runs follow is `evaluation/PLAN.md`; the run list is `evaluation/RUNS.md` section 7.

## 1. Summary

| Question | Result (measured) | Reading (interpretation) |
|---|---|---|
| RQ1: is hybrid retrieval better than dense or BM25 alone? | On 60 questions, hybrid recall@5 0.508 [0.383, 0.625], dense 0.458, BM25 0.508. Hybrid beats dense on recall@10 (0.583 against 0.492, the only difference whose interval excludes 0). Hybrid and BM25 do not differ. | Hybrid is not better than BM25 on this golden set. It is better than dense on recall@10 only. |
| RQ2: do query rewriting and the evidence check improve faithfulness? | Faithfulness (macro, judge `qwen2.5:7b`): MVP 0.491 [0.39, 0.59], +rewrite 0.527 [0.43, 0.62]. Paired difference on 53 shared answers: +0.031 [-0.009, 0.082]. The evidence check refused 60 of 60 answerable questions, with and without rewriting. | Rewriting may help follow-up questions; the data does not show a reliable effect. The evidence check, as built, is unusable with the 3B generator. |
| RQ3: are the follow-up suggestions useful? | Not evaluated. The user study was cancelled (ADR 0013). | Future work (section 9). |
| Is the judge close to human labels? | On 55 sentences labelled by hand, agreement 0.855, Cohen's kappa 0.734. On 22 relevance ratings, agreement 0.682, kappa 0.389. | The faithfulness judge agrees with the two annotators on most sentences. The relevance numbers are too few to say more. |

Two findings matter for the product more than the comparison between conditions:

- **Most unsupported sentences have no citation.** In A2, 64 of the 85 sentences labelled "not supported" (75%) carry no `[n]`. The sentences that do cite a passage are supported 67 times out of 88 (0.76). Faithfulness is low partly because of a citation-format failure of the 3B generator, not only because of unsupported claims.
- **Follow-up and multi-hop questions are where retrieval fails.** Hybrid recall@5 is 0.09 on follow-up questions (n = 11) and 0.32 on multi-hop questions (n = 11), against 0.85 on factual questions (n = 13). The agent rewrites follow-ups before searching; the retrieval runs do not, so R1 to R3 understate the product on follow-ups (section 3).

## 2. Setup

### 2.1 System under test

All Week 7 runs use the frozen stack of `evaluation/SNAPSHOT.md`. The code of the R and A runs is commit `3a2b92d` (`main` after #166, #168 and #160).

| Item | Value |
|---|---|
| Corpus | arXiv `cs.CL` titles and abstracts, Kaggle snapshot version 307 (`kaggle-arxiv-v307-cs.CL-2026-10-10`): 121,860 documents, 121,926 chunks |
| Chunking and embedding | at most 320 words per chunk with 48 words of overlap; `BAAI/bge-small-en-v1.5`, 384 dimensions, cosine |
| Index | Qdrant 1.19.2, collection `scitech_chunks`, exact search; BM25 index built from the same chunks |
| Retrieval | hybrid (dense + BM25, reciprocal rank fusion) is the product default (ADR 0009); top 5 chunks go to the answer |
| Generator | `llama3.2:3b` (Q4_K_M, digest `a80c4f17acd5`), temperature 0, 512 answer tokens |
| Judge | `qwen2.5:7b` (digest `845dbda0ea48`), temperature 0, different from the generator |
| Host | DAT's laptop (Ryzen AI 7 350, 31 GB RAM, RTX 5060 Laptop 8 GB, Ollama 0.40.13), Qdrant native at `127.0.0.1:6333` |
| Index snapshot id | `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` |

### 2.2 Golden set

`evaluation/golden_set/golden.jsonl` (sha256 `1d05086d…`): 65 items, all English. 60 are answerable and are used for retrieval and for the answer metrics. 5 are unanswerable (`gs-u01` to `gs-u05`) and are used only for the correct-refusal check. No Vietnamese items were written, so no Vietnamese run exists.

| Type | Answerable items | of which dev (items 1-30) | of which test (items 31-60) |
|---|---:|---:|---:|
| factual | 13 | 6 | 7 |
| explanatory | 17 | 10 | 7 |
| comparison | 8 | 4 | 4 |
| multi_hop | 11 | 5 | 6 |
| follow_up | 11 | 5 | 6 |
| **Total** | **60** | **30** | **30** |

Per-type cells hold 8 to 17 items. Differences between types are descriptive.

### 2.3 Runs

All runs have 0 errors and use the same code, index snapshot and golden file (`evaluation/RUNS.md` section 7). Run files are in `evaluation/runs/`.

| Run | What | Run file (timestamp and name) |
|---|---|---|
| R1 | hybrid retrieval, k = 1, 5, 10 | `20261102T111427Z-retrieval-final-hybrid` |
| R2 | dense retrieval | `20261102T111434Z-retrieval-final-dense` |
| R3 | BM25 retrieval | `20261102T111435Z-retrieval-final-bm25` |
| A1 | answers, MVP (`AGENT_REWRITE=off`, `AGENT_SELF_CHECK=off`) | `20261102T111436Z-answers-w7-a1-mvp` |
| A2 | + rewrite (the product configuration) | `20261102T112100Z-answers-w7-a2-rewrite` |
| A3 | + evidence check | `20261102T112723Z-answers-w7-a3-check` |
| A4 | full agent (rewrite and evidence check) | `20261102T112800Z-answers-w7-a4-full` |
| V1, V2 | answer relevance of A1 and A2 | `<A1 or A2 file>.relevance.json` |
| L1 | latency on 30 golden questions | `docs/runbooks/performance.md`, run B `20261030T083604Z` |
| S1 | index scaling at 10%, 50%, 100% | `pipelines/reports/scaling.md` |
| U1 | user study | cancelled (ADR 0013) |
| X1 | closed-book check of prior knowledge | not run (optional in `RUNS.md` section 6) |

Each condition was run once. LLM output is not fully deterministic, and the run-to-run variation was not measured, so small differences between A1 and A2 are not interpreted as effects.

### 2.4 Metrics and sample sizes

Recall@k, MRR, faithfulness, answer relevance, refusal rate and cited-document recall are defined in `evaluation/PLAN.md` section 4. Intervals are 95% bootstrap intervals over questions (1,000 resamples). Faithfulness is "supported by the cited chunks", not "true". Refused answers are not scored; their number is reported next to the refusal rate.

## 3. Retrieval (RQ1)

**Measured.** 60 questions, the raw `question` field as query, one run per retriever (`retrieval-final-compare.txt`).

| Metric | Hybrid (R1) | Dense (R2) | BM25 (R3) |
|---|---|---|---|
| recall@1 | 0.358 [0.250, 0.475] | 0.300 [0.183, 0.417] | 0.358 [0.250, 0.467] |
| recall@5 | 0.508 [0.383, 0.625] | 0.458 [0.350, 0.575] | 0.508 [0.392, 0.633] |
| recall@10 | 0.583 [0.458, 0.700] | 0.492 [0.383, 0.600] | 0.567 [0.450, 0.692] |
| MRR | 0.474 [0.363, 0.590] | 0.420 [0.309, 0.529] | 0.486 [0.375, 0.601] |

Paired differences on the same 60 questions (the interval is for the mean difference):

| Comparison | recall@5 | recall@10 | MRR |
|---|---|---|---|
| dense minus hybrid | -0.050 [-0.133, +0.033], 3 wins, 7 losses | -0.092 [-0.167, -0.025], 1 win, 8 losses | -0.054 [-0.128, +0.013] |
| BM25 minus hybrid | 0.000 [-0.075, +0.075], 5 wins, 5 losses | -0.017 [-0.092, +0.058], 4 wins, 5 losses | +0.012 [-0.059, +0.083] |

Only the dense-minus-hybrid difference at recall@10 has an interval that excludes 0. The other differences are inside the noise of a 60-question set.

By question type (recall@5 / recall@10 / MRR):

| Type | n | Hybrid | Dense | BM25 |
|---|---:|---|---|---|
| factual | 13 | 0.85 / 0.85 / 0.76 | 0.69 / 0.69 / 0.62 | 0.92 / 0.92 / 0.85 |
| explanatory | 17 | 0.65 / 0.76 / 0.59 | 0.71 / 0.71 / 0.56 | 0.53 / 0.59 / 0.51 |
| comparison | 8 | 0.50 / 0.62 / 0.44 | 0.31 / 0.50 / 0.41 | 0.50 / 0.62 / 0.60 |
| multi_hop | 11 | 0.32 / 0.36 / 0.36 | 0.27 / 0.32 / 0.38 | 0.32 / 0.36 / 0.35 |
| follow_up | 11 | 0.09 / 0.18 / 0.10 | 0.09 / 0.09 / 0.02 | 0.18 / 0.27 / 0.08 |

**Development and test items (measured).** The plan says not to use the test items for decisions and to report both. The two halves differ a lot:

| Retriever | dev (30 items): recall@5, MRR | test (30 items): recall@5, MRR |
|---|---|---|
| Hybrid | 0.333, 0.301 | 0.683, 0.646 |
| Dense | 0.283, 0.253 | 0.633, 0.588 |
| BM25 | 0.350, 0.370 | 0.667, 0.601 |

All three retrievers find the relevant documents about twice as often on the test items. The conclusion about the three retrievers is the same on both halves (hybrid and BM25 close, dense lowest), but the absolute level of the 60-item numbers depends on which half is taken.

**Why retrieval misses (measured and read by FAO, `evaluation/reports/retrieval-errors-w7.md`).** Of the 60 questions, hybrid has every relevant document in its top 5 for 28 and misses 32. The main causes among those 32: a follow-up question searched without its history (10), the question uses everyday words where the abstract uses the technical term (7), a crowded topic where other papers rank higher (7), and retriever-dependent misses (6). No relevant document is missing from the index (all 78 are in the chunks and in Qdrant) and none is split across chunks.

**Interpretation.**
- RQ1: the expectation that hybrid is at least as good as the better single retriever holds (it ties BM25), but the expectation that BM25 is only competitive on exact technical terms is too weak: BM25 matches hybrid on this set. The questions were written from abstracts, which can favour keyword matching (section 8).
- The follow-up numbers (0.09 for hybrid) are not a measure of the product. The agent rewrites a follow-up into a standalone query before searching, and R1 to R3 search with the last turn only. On answered follow-up items, retrieved-document recall is 0.125 without rewriting (A1, n = 8) and 0.44 with rewriting (A2, n = 9). The two sets of answered items differ and n is small, so this is an indication, not a measured effect. Retrieval on the golden `standalone_query` was not run.

## 4. Answers and ablations (RQ2)

### 4.1 Overall results

**Measured.** 60 answerable questions and 5 unanswerable, one run per condition.

| Measure | A1 MVP | A2 +rewrite | A3 +check | A4 full |
|---|---|---|---|---|
| Answers judged | 54 | 55 | 0 | 0 |
| Answerable questions refused | 6/60 (0.10) | 5/60 (0.08) | 60/60 | 60/60 |
| Unanswerable questions refused | 4/5 (`gs-u05` answered) | 4/5 (`gs-u05` answered) | 5/5 | 5/5 |
| Faithfulness, macro [95% CI] | 0.491 [0.39, 0.59] | 0.527 [0.43, 0.62] | not scorable | not scorable |
| Faithfulness, micro (supported / checkable sentences) | 0.408 (62/152) | 0.441 (67/152) | - | - |
| Share of answers with faithfulness 1 | 0.222 | 0.273 | - | - |
| Cited-document recall [95% CI] | 0.398 [0.27, 0.53] | 0.427 [0.30, 0.55] | - | - |
| Retrieved-document recall (sources) | 0.546 [0.42, 0.68] | 0.591 [0.46, 0.71] | - | - |
| Invalid citations | 0 | 0 | - | - |
| Relevance (1 to 3), mean [95% CI], judge | 2.31 [2.11, 2.52], n = 54 | 2.44 [2.24, 2.62], n = 55 | - | - |
| Relevance ratings 1 / 2 / 3 | 11 / 15 / 28 | 8 / 15 / 32 | - | - |
| Answer time for 65 items | 266 s | 264 s | 28.5 s | 28.9 s |

Faithfulness by question type (macro mean, number of judged answers in brackets):

| Type | A1 | A2 |
|---|---|---|
| factual | 0.58 (11) | 0.58 (11) |
| explanatory | 0.54 (17) | 0.54 (17) |
| comparison | 0.36 (8) | 0.36 (8) |
| multi_hop | 0.42 (10) | 0.42 (10) |
| follow_up | 0.48 (8) | 0.70 (9) |

Development and test items (macro faithfulness, judged answers in brackets): A1 0.556 (25) on dev and 0.436 (29) on test; A2 0.576 (25) on dev and 0.487 (30) on test. Here the test half is lower, the opposite of retrieval (section 3), so the 60-item average hides a split that goes in different directions for the two measures.

### 4.2 Rewriting (A1 against A2)

**Measured.** The only types where A1 and A2 differ are follow-up questions, because the rewrite changes only follow-up turns. On the 53 answers judged in both runs, the paired faithfulness difference is +0.031 [-0.009, 0.082] (A2 better on 4 answers, worse on 1, equal on 48). The relevance difference on the same 53 answers is +0.094 [0.000, 0.208]. Over-refusal goes from 6/60 to 5/60.

**Interpretation.** The direction is the one the plan expected (rewriting helps follow-ups). The gain on follow-ups (0.48 to 0.70) rests on 8 and 9 answers, and the two sets of answered items are not the same (A1 refused `gs-018`, A2 answered `gs-022` and `gs-060` additionally). Each condition was run once, so differences like these are inside the run-to-run variation the plan warns about. We report the numbers and do not claim an effect.

### 4.3 Evidence check (A3 and A4)

**Measured.** With `AGENT_SELF_CHECK=on`, every answerable question (60/60) and every unanswerable question (5/5) was refused, with and without rewriting. This repeats the dev-split result of the earlier ablation (`evaluation/reports/ablations-v1.md`, 32 of 32).

**Interpretation.** The check as built, with `llama3.2:3b`, answers NO whatever the sources. The runs do not say whether the cause is the model size, the prompt, or the 8-token limit on the reply (`self_check_max_tokens`), because the raw reply is not stored. A3 and A4 cannot be scored on faithfulness. The result supports keeping the check off in the product (SNAPSHOT section 2).

### 4.4 Where unfaithfulness comes from (A2)

**Measured** (`evaluation/reports/answer-errors-w7.md`, rule-based causes from the run fields; no case was re-read by a person):

- 12 of the 20 worst cases are "missing citations", 5 are over-refusals, 3 are retrieval misses.
- In all 12 "missing citations" cases at least one relevant document was among the sources.
- Counting only sentences that carry a citation, micro faithfulness would be 0.76 instead of 0.44. The two numbers answer different questions; the report keeps the all-sentence rate as the headline because an uncited claim cannot be checked.
- Faithfulness does not follow retrieval: answers with no relevant document in their sources average 0.53 (n = 20), the others 0.52 (n = 35). This is expected from the metric, which checks support by the cited passage and not correctness.

**Interpretation.** Part of the low faithfulness is the generator not putting `[n]` on a sentence that may be correct or may come from its own knowledge. These runs cannot separate the two, because that needs the answer text and the passages, which are not in the run files.

### 4.5 Unanswerable questions

**Measured.** A1 and A2 refused 4 of 5 unanswerable items and answered `gs-u05` (the parameter count of Gemini). Three retrieved abstracts mention Gemini near the word "parameter" without giving its size (FAO, #168). A3 and A4 refused all 5, which says nothing because they refuse everything. With 5 items, each is 20 points.

## 5. Judge against human labels

**Measured.** The faithfulness and relevance judges were checked on a 20% sample of the answers that enter the metrics (seed 20261031): 11 answers per run for A1 and A2, split between LDN (part 1/2) and FAO (part 2/2). A3 and A4 have no answer to sample. Human files: `evaluation/pilot/w7-sample/<run>/labels-LDN.csv`, `relevance-LDN.csv`, `labels-FAO.csv`, `relevance-FAO.csv`. Each annotator labelled every sentence and rated every answer by hand with the written procedure of `PLAN.md` sections 5 and 4.2 and did not see the judge output. Labelling took about 13 minutes (A1) and 3 minutes (A2) for LDN, and about 57 and 16 minutes of active time for FAO.

Faithfulness (three labels: supported, not supported, not checkable):

| Run | Annotator | n sentences | Raw agreement | Cohen's kappa |
|---|---|---:|---:|---:|
| A1 | LDN | 18 | 16/18 = 0.889 | 0.769 |
| A1 | FAO | 11 | 9/11 = 0.818 | 0.686 |
| A1 | both | 29 | 25/29 = 0.862 | 0.733 |
| A2 | LDN | 13 | 12/13 = 0.923 | 0.847 |
| A2 | FAO | 13 | 10/13 = 0.769 | 0.594 |
| A2 | both | 26 | 22/26 = 0.846 | 0.720 |
| A1 + A2 | both | 55 | 47/55 = 0.855 | 0.734 |

Judge against human, sentence labels (rows: human, columns: judge; order supported, not supported, not checkable):

| A1 | supported | not supported | not checkable |
|---|---:|---:|---:|
| supported | 8 | 1 | 0 |
| not supported | 2 | 16 | 0 |
| not checkable | 1 | 0 | 1 |

| A2 | supported | not supported | not checkable |
|---|---:|---:|---:|
| supported | 12 | 2 | 0 |
| not supported | 1 | 9 | 1 |
| not checkable | 0 | 0 | 1 |

Relevance (ratings 1 to 3):

| Run | n answers | Raw agreement | Cohen's kappa | Weighted kappa | Within 1 point |
|---|---:|---:|---:|---:|---:|
| A1 | 11 | 5/11 = 0.455 | 0.057 | -0.093 | 8/11 |
| A2 | 11 | 10/11 = 0.909 | 0.810 | 0.893 | 11/11 |
| A1 + A2 | 22 | 15/22 = 0.682 | 0.389 | 0.285 | 19/22 |

Judge against human, relevance (rows: human rating, columns: judge rating 1, 2, 3):

| A1 | 1 | 2 | 3 |
|---|---:|---:|---:|
| 1 | 0 | 0 | 0 |
| 2 | 0 | 1 | 1 |
| 3 | 3 | 2 | 4 |

| A2 | 1 | 2 | 3 |
|---|---:|---:|---:|
| 1 | 1 | 0 | 0 |
| 2 | 0 | 2 | 0 |
| 3 | 0 | 1 | 7 |

Macro faithfulness on the same 11 answers per run, human labels against judge labels: A1 0.394 against 0.500, A2 0.523 against 0.583. Mean relevance on the same answers: A1 2.82 (human) against 2.18 (judge), A2 2.64 against 2.55.

**Which numbers are the headline.** The plan says that where judge and human differ, the human label is used. The human labels cover only the 11 answers per run, so the headline faithfulness and relevance numbers in sections 1 and 4 are judge numbers on all answers, and this section gives the human numbers on the sample next to them.

**Interpretation.**
- The faithfulness judge agrees with the humans on about 85% of sentences (kappa 0.73, on 55 sentences). On the sampled answers it gave higher faithfulness than the humans (0.50 against 0.39 for A1, 0.58 against 0.52 for A2), so the judge faithfulness numbers in section 4 may be somewhat optimistic. With 11 answers per run the difference is within noise.
- The relevance judge and the humans agree poorly in A1 and well in A2. In A1 the humans rated nine answers 3, and the judge rated five of them 1 or 2. Eleven ratings per run are too few to say which one is closer to the rule of `PLAN.md` section 4.2, and the two readings differ more in A1 than in A2. Relevance means in section 4 carry this caveat.
- With one annotator per sentence there is no human-human agreement. The differences between LDN's rows and FAO's rows cannot be told apart from differences between the two halves of the sample.
- An earlier check on 24 pilot sentences (`evaluation/pilot/faithfulness/`) gave 18 of 24 agreement between LDN and FAO (kappa 0.58). It was not a blind comparison (FAO's file had changed after #136, and LDN's had gone through a rule check), and it is not part of the numbers above.

## 6. Efficiency

**Measured.** Latency on the first 30 golden questions (L1, run B `20261030T083604Z`, `v0.6-rc`, DAT's laptop, `QDRANT_URL=127.0.0.1`, n = 30, one run; `docs/runbooks/performance.md`):

| Time (ms) | p50 | p95 | max |
|---|---:|---:|---:|
| First token | 422 | 2,632 | 5,016 |
| Answer complete | 1,328 | 3,196 | - |
| Total | 4,304 | 6,025 | 9,125 |

Retrieval is 31 ms at the median (p95 47 ms). The follow-up suggestions take about 2.9 s after the answer is on screen. With `localhost` instead of `127.0.0.1` on Windows, 6 of 30 retrievals took about 2 s (run A); the rest of the runs use `127.0.0.1`. L1 was measured before the Week 7 runs and was not repeated on the final commit; `RUNS.md` section 4 records that the change since then (#167, a regex) does not touch the timed steps.

Index scaling (S1, FAO's laptop, 100 queries, k = 10, exact search; `pipelines/reports/scaling.md`):

| Size | Chunks | Qdrant load (s) | BM25 build (s) | Hybrid latency p50 / p95 (ms) | Qdrant disk (MiB) |
|---|---:|---:|---:|---|---:|
| 10% | 12,162 | 18.2 | 1.8 | 89.6 / 131.0 | 465.0 |
| 50% | 61,067 | 51.3 | 9.8 | 97.7 / 135.2 | 412.7 |
| 100% | 121,926 | 135.2 | 36.7 | 120.4 / 134.6 | 609.9 |

**Interpretation.** Hybrid latency grows slowly with the index size (p50 from about 90 ms to 120 ms for a tenfold larger index), and answer generation dominates the response time. The scaling run is on one laptop at three sizes and one repetition; it supports "the index is not the bottleneck at this size", not a statement about much larger corpora.

## 7. Error analysis

The detailed analyses are in `evaluation/reports/retrieval-errors-w7.md` (FAO, retrieval) and `evaluation/reports/answer-errors-w7.md` (DAT, answers). The main findings are in sections 3 and 4. In short:

1. **Missing citations** are the largest single cause of low faithfulness (12 of the 20 worst A2 cases), and in all of them the right document was retrieved.
2. **Follow-up questions without their history** and **vocabulary mismatch** are the two largest causes of retrieval misses (17 of hybrid's 32 misses). Neither is solved by a better ranker; both need a better query.
3. **Multi-hop and comparison questions** need two papers, so one missing paper counts as a miss. Question decomposition, which targeted them, was cut (ADR 0010).
4. **The evidence check refuses everything** with the 3B generator (section 4.3).
5. **Near misses.** 6 of hybrid's 32 misses have the relevant document at ranks 6 to 10, which never reach the answer because only the top 5 are shown.

## 8. Threats to validity and limitations

- **Small sample.** 60 answerable questions, per-type cells of 8 to 17, and 11 answers per run in the manual sample. Intervals are wide, and one question moves a recall figure by 1.7 points. No claim of significance is made for small differences.
- **Development and test halves differ.** Retrieval recall@5 is 0.33 on the dev items and 0.68 on the test items for hybrid (section 3), and faithfulness goes the other way (section 4.1). The 60-item average hides this. The reason is not established. One observation, not a test: 6 of the 7 vocabulary-mismatch questions that FAO found among the retrieval misses are dev items (`gs-001` to `gs-004`, `gs-028`, `gs-029`).
- **One run per condition.** The run-to-run variation of the LLM was not measured, so A1 against A2 is not interpreted as an effect.
- **Single-author bias in the golden set.** Most items were written by one person from abstracts, which can favour keyword matching; BM25 ties hybrid here. FAO checked part of the items.
- **Incomplete relevance labels.** Only the documents the writer found are labelled, so recall and MRR are conservative.
- **Prior knowledge.** The 3B model knows the field. A correct sentence from memory counts as unsupported if its citation does not say it, and a sentence can be faithful to an irrelevant chunk. Faithfulness is not correctness. The closed-book check (X1) was not run.
- **Judge.** `qwen2.5:7b` is a 7B model. On the 11 answers per run, the judge faithfulness was higher than the human labels, and its relevance ratings were lower than the humans' in A1. It was checked on 55 sentences and 22 ratings only.
- **Two annotators on different halves.** No double annotation, so human-human agreement is unknown. DAT did not annotate because he built the agent. LDN's and FAO's labels use one written procedure; the 24-sentence pilot (`evaluation/pilot/faithfulness/`) showed differences on partly supported sentences (rules 2 and 7 of `PLAN.md` section 5).
- **Evaluation of follow-ups.** Retrieval is evaluated on the raw question, which understates the product on follow-up turns (section 3).
- **Corpus.** Titles and abstracts of one `cs.CL` snapshot; questions that need the full text are out of scope. Incremental ingestion after the freeze is not part of the evaluated index.
- **Simplified system.** Reranking and decomposition were cut (ADR 0010). The results describe the reduced system.
- **Hosts.** The answer runs and R1 to R3 ran on DAT's laptop; the scaling measurements on FAO's laptop. Timings are not comparable between hosts. The generator ran locally, so the earlier Kaggle numbers (ADR 0006) are not comparable answer by answer.
- **Unanswerable group.** 5 items, one writer; the correct-refusal rate has a resolution of 20 points.
- **User study.** None. RQ3 is not evaluated (section 9).

## 9. RQ3 was dropped

RQ3 asked whether users rate the suggested follow-up questions as useful and click them. The only planned evidence was a user study with 4 to 6 participants on 3 to 4 November. On 3 November, before the first session, the team was told that the study is not needed, and ADR 0013 cancelled it. No session was held and no study data exists. The suggestions stay in the product and are described in the report chapters on the system; their usefulness is not measured. The rating buttons and `POST /feedback` stay in the product and are not used for evaluation.

## 10. Future work

1. **Citation enforcement.** After generation, find the sentences without `[n]` and either ask the model once to add the marker from the sources or drop the sentence and say so. Measure it with the same A2 setting and report faithfulness for cited sentences and for all sentences.
2. **A stronger generator.** Run A2 with `qwen2.5:7b` or a hosted model as generator and another model as judge, to see how much of the unfaithfulness and of the evidence-check failure comes from the 3B model.
3. **Retrieval for multi-hop, comparison and follow-up questions.** Question decomposition, retrieval per named entity, and an evaluation on the rewritten query (`standalone_query` in the golden set).
4. **Evidence check calibration.** Store the raw reply, raise `self_check_max_tokens`, and try a larger model before using the check again.
5. **A user study for RQ3** with 5 or more participants, the planned protocol (`evaluation/user_study/PROTOCOL.md`) and descriptive statistics only.
6. **More annotation.** Double annotation of a sample for human-human agreement, and a larger manual sample for the relevance judge.

## Appendix: provenance

- Code: `3a2b92d` (`main` after #166, #168 and #160) for all seven R and A runs. Each run file records the commit that holds the previous run files, as `RUNS.md` section 7 explains; `git diff 3a2b92d 01da803 -- . ':!evaluation/runs'` is empty. R2 and R3 record `+dirty` because untracked run files were counted; no tracked file changed.
- Golden file sha256: `1d05086d71904dcc479793c930b7586fd2afb0a0e4c1543b30c46f0ed3ec50bc` in all seven files.
- Relevance runs: `relevance-w7.yaml`, `qwen2.5:7b` (digest `845dbda0ea48`), commits `4036333` (V1) and `61e7e42` (V2).
- Manual sample: `make-sheet --sample 0.2 --seed 20261031 --part 1/2` (LDN) and `2/2` (FAO); sample files in `evaluation/pilot/w7-sample/<run>/` (PRs #190 and #185).
- Agreement numbers (section 5) and the paired differences, dev and test splits and per-type tables (sections 3 and 4) were computed from these files with a script that is not in the repository.
