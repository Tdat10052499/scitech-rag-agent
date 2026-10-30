# Retrieval v1: hybrid vs dense vs BM25 on the dev golden set

Task: W3-D4-LDN-1. Status: **draft, not reviewed**. Review by FAO is required before merge. Drafted with AI assistance (Claude); LDN read section 6 and is responsible for the final text.

## 1. What this report is

A comparison of three retrievers on the 30 answerable dev questions of the golden set, to support the default-retrieval decision in ADR 0009 (`docs/decisions/0009-default-retrieval.md`). It measures retrieval only (are the relevant papers in the top k). It says nothing about answer quality or faithfulness.

## 2. Setup and provenance

| Item | Value |
|---|---|
| Run by | FAO, 2026-10-21, on his Windows laptop (PR #106) |
| Code | commit `ad8f333a2b69` (`main` with #90 merged, clean tree) |
| Dataset | `kaggle-arxiv-v307-cs.CL-2026-10-10` |
| Index snapshot | `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` (121,926 points) |
| Golden set | 30 answerable items, `split: dev`, `language: en`; 2 unanswerable items excluded; questions used as asked |
| Retrievers | A hybrid (dense + BM25, RRF), B dense only, C BM25 only |
| Parameters | exact Qdrant search; RRF_K = 60; per-retriever top 50; BM25 k1 = 1.2, b = 0.75 |
| Intervals | 95% bootstrap, 1000 resamples, seed 0 |
| Run files | `evaluation/runs/20261021T1254{02,21,23}Z-retrieval-v1-{hybrid,dense,bm25}.json`, `evaluation/runs/retrieval-v1-compare.txt` |

Note on hashes: `golden.sha256` is `215992869ee9…` in the Windows (CRLF) checkout and `f5b763f6…` in an LF checkout. The content is the same; only line endings differ.

Chunks are title + abstract only. A paper counts as retrieved if any of its chunks is in the top k. Recall is the fraction of an item's relevant papers found; 9 of the 30 items have two relevant papers, so recall can be 0.5.

## 3. Results (N = 30)

Mean [95% CI].

| Metric | A hybrid | B dense | C BM25 |
|---|---|---|---|
| recall@1 | 0.250 [0.100, 0.400] | 0.183 [0.050, 0.317] | 0.283 [0.133, 0.433] |
| recall@5 | 0.333 [0.167, 0.500] | 0.283 [0.133, 0.450] | 0.350 [0.183, 0.517] |
| recall@10 | 0.383 [0.200, 0.567] | 0.317 [0.167, 0.483] | 0.400 [0.233, 0.583] |
| MRR | 0.301 [0.153, 0.464] | 0.253 [0.111, 0.406] | 0.370 [0.210, 0.540] |

The dense numbers equal ADR 0007 table B; the BM25 numbers equal ADR 0009 table A.

### 3.1 Paired difference against hybrid

Same 30 questions, difference of per-question scores. "Questions" = difference × 30. Wins/losses = questions where the retriever scored higher/lower than hybrid.

| Metric | Dense − hybrid | Wins/losses | BM25 − hybrid | Wins/losses |
|---|---|---|---|---|
| recall@1 | −0.067 (−2.0 q) [−0.167, 0.000] | 0 / 2 | +0.033 (+1.0 q) [−0.083, +0.133] | 3 / 1 |
| recall@5 | −0.050 (−1.5 q) [−0.183, +0.067] | 1 / 3 | +0.017 (+0.5 q) [−0.083, +0.117] | 2 / 1 |
| recall@10 | −0.067 (−2.0 q) [−0.183, +0.017] | 1 / 3 | +0.017 (+0.5 q) [−0.083, +0.117] | 2 / 1 |
| MRR | −0.049 [−0.113, +0.003] | 2 / 5 | +0.069 [−0.033, +0.189] | 4 / 3 |

Every interval includes 0.

### 3.2 By question type

N per type is small (4 to 10). Cells below 10 items are **not compared** (`evaluation/PLAN.md` 4.1); the values are shown only so the reader can see where the hits come from.

| Type | n | recall@5 hybrid | recall@5 dense | recall@5 BM25 |
|---|---|---|---|---|
| explanatory | 10 | 0.500 | 0.500 | 0.400 |
| factual | 6 | 0.667 | 0.500 | 0.833 |
| comparison | 4 | 0.250 | 0.125 | 0.250 |
| multi_hop | 5 | 0.000 | 0.000 | 0.100 |
| follow_up | 5 | 0.000 | 0.000 | 0.000 |

Measured fact: none of the three retrievers found any relevant paper in the top 10 for the 5 `follow_up` items; dense found one partial hit at k = 10 for `multi_hop`, BM25 one at k = 5. Descriptive only, not a test.

### 3.3 Where the retrievers differ (question ids)

- At recall@5, hybrid found a relevant paper and dense did not on gs-005, gs-008, gs-020; dense found one and hybrid did not on gs-030.
- At recall@5, BM25 found one and hybrid did not on gs-007, gs-012; hybrid found one and BM25 did not on gs-020.
- Counting items with at least one relevant paper in the top 5: hybrid 11, dense 9, BM25 12, union of all three 14 of 30. In 16 of 30 items none of the three found anything at k = 5.

These are counts of questions, not explanations. Why each question was missed is not established here.

### 3.4 Latency

Search time per question, from the run files (median; p95 excluding the first question, which includes the embedding-model load, 15.3 s hybrid and 14.3 s dense):

| | hybrid | dense | BM25 |
|---|---|---|---|
| median | 0.098 s | 0.080 s | 0.009 s |
| p95 (excl. first) | 0.111 s | 0.085 s | 0.016 s |

Separate measurement by FAO (`index_profile.md`, 100 queries, k = 10), p50/p95: dense 82.5/88.5 ms, BM25 7.1/14.2 ms, hybrid 107.2/149.1 ms. All are far under the 1 s guard in ADR 0009. Both measurements were made on one Windows laptop; to be rechecked on the backend machine in W6.

## 4. What the numbers do and do not show

Measured:
- Each retriever finds a relevant paper in the top 10 for at most 13 of 30 questions (BM25 13, hybrid 12, dense 11); the three together find one for 15. Absolute retrieval quality on this set is low for all of them.
- No difference between retrievers is distinguishable from noise: every paired interval includes 0.
- The point estimates order BM25 ≥ hybrid ≥ dense on every metric.

Decision (ADR 0009, accepted 2026-10-22; rule fixed before the numbers): default stays hybrid, `RETRIEVAL_TOP_K` = 5, `RETRIEVAL_MIN_SCORE` = 0.0. No single retriever reached the required +2.0 questions at recall@5 with a non-negative MRR difference (BM25: +0.5 questions). recall@10 − recall@5 for hybrid is 0.05 (1.5 questions), below the 3-question threshold for raising k. Fallback if needed: `RETRIEVER=bm25`.

Hypotheses (not measured):
- BM25 may be favoured because the golden questions were written from abstracts, so they share keywords with the chunks (`golden_set/FORMAT.md` rule 4). Testing this needs questions written without looking at the abstract.
- The 0.0 scores on `follow_up` may come from searching the question as asked, without using the conversation context. Not checked; the same code path was used for all three retrievers.

## 5. Limitations

- N = 30, one author's questions (single-author bias), one dev set. Intervals are wide (about ±0.15 on recall).
- One run per retriever, one index snapshot, one machine; run-to-run variability not measured.
- Relevance labels may be incomplete: a paper not marked relevant may still be a good answer, which would lower all recalls.
- The decision rule was applied to the same dev data the numbers were measured on (selection on the evaluation data, see `evaluation/PLAN.md` section 7).
- Chunks contain title + abstract only, so the results do not transfer to full-text retrieval.
- Simplified system (`evaluation/PLAN.md` section 7). Questions were searched as asked; whether `follow_up` and `multi_hop` need components not in this version is a hypothesis, not tested. The `follow_up` items were searched as typed; query rewriting (`AGENT_REWRITE`, #126) has merged since these runs, so the W7 runs may change that row, and 0.0 on `follow_up` is not a final result.
- Dataset snapshot is from 2026-10-10 and is cs.CL only; year bias is possible.

## 6. Dense misses and likely causes

Method: for each of the three questions where dense lost to hybrid at recall@5 (gs-005, gs-008, gs-020), the abstracts of the relevant papers and of the one or two papers dense ranked highest were read (arXiv abstract pages). Lower-ranked papers were not read. The causes below are hypotheses from reading, not tested; each ends with what was not checked.

### gs-005 (comparison; relevant 2407.19794, 2501.16952)

Question: "In RAG, how does the chunk size affect answer quality, and can chunks at several levels (multi-sentence, paragraph, section, document) do better than one level?"

- Dense found 2407.19794 (chunk size and RAG question answering) only at rank 10 and did not find 2501.16952 (multiple abstraction levels) in the top 10. Hybrid had them at ranks 3 and 6; BM25 at ranks 6 and 1.
- Dense ranks 1 and 2 are 2607.24767 ("The Effect of Text Chunk Size on Retrieval-Augmented Generation Performance") and 2402.05131 ("Financial Report Chunking for Effective Retrieval Augmented Generation"). Both are on topic (chunking in RAG) but are not the papers marked relevant.
- Likely cause (hypothesis): the index holds several papers on chunking for RAG, and the dense retriever ranks them by overall topic similarity. The multi-level paper's title says "abstraction level", not "chunk size", so the second half of the question may not match it closely in embedding space. BM25 ranked it first, which fits an exact match on "levels", "multi-sentence", "paragraph", "section" and "document".
- Not checked: whether 2607.24767 would also be an acceptable answer (relevance labels may be incomplete, see section 5); ranks 3 to 9 of dense.

### gs-008 (factual; relevant 2512.24058)

Question: "Is there a single score that combines calibration, robustness and uncertainty to measure how reliable an LLM is?"

- The relevant paper is "Beyond Hallucinations: A Composite Score for Measuring Reliability in Open-Source Large Language Models". Dense did not return it in the top 10; hybrid had it at rank 3 and BM25 at rank 2.
- Dense ranks 1 and 2 are 2601.13885 ("Confident Rankings with Fewer Items: Adaptive LLM Evaluation with Continuous Scores") and 2403.09849 ("Self-Consistency Boosts Calibration for Math Reasoning"). Each shares one idea with the question (evaluating LLMs, or calibration) but neither proposes a combined reliability score.
- Likely cause (hypothesis): the question lists three concepts, and dense similarity was pulled toward papers about one of them (calibration) or about LLM evaluation in general. The relevant abstract contains all three terms together, which a keyword match rewards; this may explain why BM25 and hybrid found it.
- Not checked: the other dense results (ranks 3 to 10); whether a question phrased closer to the abstract ("composite reliability score") changes dense's result.

### gs-020 (explanatory; relevant 2606.06178)

Question: "How can a system route questions to different language models while respecting each user's own balance between cost and quality?"

- The relevant paper is "Learning to Route LLMs from Implicit Cost-Performance Preferences via Meta-Learning" (MetaRouter). Dense did not return it in the top 10; hybrid had it at rank 4; BM25 at rank 10.
- Dense ranks 1 and 2 are 2403.09704 ("Alignment Studio: Aligning Large Language Models to Particular Contextual Regulations") and 2509.25369 ("Generative Value Conflicts Reveal LLM Priorities"). Both are about adapting a model to values or conflicting requirements, not about routing queries between models.
- Likely cause (hypothesis): the phrases "respecting each user's own balance" and "cost and quality" resemble the language of values, preferences and trade-offs, so dense matched that part of the question and gave less weight to "route ... to different language models". The question does not use the paper's own terms ("preference", "routing" as a noun), only the verb "route".
- Not checked: dense ranks 3 to 10; whether adding "LLM routing" to the question changes the result. Note that BM25 also ranked the paper only at 10, so for this item the keyword route was weak too, and hybrid's rank 4 came from combining both lists.

### Common pattern (tentative)

In all three questions dense ranked papers that match one part of a multi-part question, or the general topic, above the paper that matches the whole question. This is consistent with a small embedding model (bge-small) on short abstracts, but three questions are too few to say it is the main reason dense scored lower overall, and it was not tested.

## 7. Review

Reviewer: FAO. Checks: numbers match the run files; limitations complete; wording matches ADR 0009.

Drafted by Claude (Claude Sonnet 5.5) for LDN.
