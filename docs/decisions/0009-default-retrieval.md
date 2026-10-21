# 0009. Default retrieval configuration

- Status: draft (decision rule set on 2026-10-20, before the hybrid numbers exist; numbers come from W3-D4-LDN-1 on D09)
- Date: 2026-10-20 (rule); D09 2026-10-22 (numbers and decision)
- Deciders: DAT (author), LDN (numbers, `evaluation/reports/retrieval-v1.md`), FAO (index and latency, `pipelines/reports/index_profile.md`)

## Context
The agent retrieves once per question and answers from the top `RETRIEVAL_TOP_K` chunks. Three retrievers implement the `Retriever` protocol on the same index snapshot (121,926 chunks, `chunked_at` 2026-10-17T05:19:12+00:00):
- **dense**: `bge-small-en-v1.5` with the query instruction (ADR 0007), Qdrant cosine search (#77, #78);
- **bm25**: Okapi BM25, `k1` 1.2, `b` 0.75, English stop words dropped (#79);
- **hybrid**: reciprocal rank fusion of the two, `rrf_k` 60, top 50 from each retriever before fusion (#82).

`RETRIEVER` selects one (default `hybrid` in code until this ADR decides). This ADR fixes `RETRIEVER` and `RETRIEVAL_TOP_K`.

Constraints:
- **Evidence is small.** The 30 answerable `dev` items of the golden set (`evaluation/PLAN.md` section 3.4: items 1-30 may be used for decisions). One question is 0.033 of recall; the bootstrap intervals of ADR 0007 overlapped almost completely at this size.
- **The rule must come before the numbers.** The dense and BM25 numbers on the same items are already partly known (table A), so the rule below is written now, before any hybrid run.
- **Answer quality depends on k only indirectly.** More chunks raise recall but lengthen the prompt of a 3B model (`llama3.2:3b`, ADR 0006), whose faithfulness on long contexts is not measured yet (W4-D4-LDN-1).

## Evidence already seen when the rule was written
**A. Single retrievers on the 30 answerable dev items, questions as asked.** Not the official run: different scripts, and dense used exact search over all vectors instead of Qdrant.

| Retriever | Source | recall@1 | recall@5 | recall@10 | MRR |
|---|---|---:|---:|---:|---:|
| dense (`bge-small`, instruction) | ADR 0007 table B | 0.183 | 0.283 | 0.317 | 0.253 |
| bm25 | `bm25_golden_check.py`, DAT journal D07 | 0.283 | 0.350 | 0.400 | not computed |

The two lists find different items (bm25 finds 13 of 30 at 10; dense misses 21 at 5, ADR 0007), which is the case where fusion can help. This is an expectation, not a measured result: whether the items overlap was not checked.

## Options considered
1. **`RETRIEVER=hybrid`**: needs both Qdrant and the BM25 index in memory (BM25 index 177 MB on disk; build peak 1,184 MB working set on DAT's laptop; load not measured yet), and two searches per question.
2. **`RETRIEVER=bm25`**: no Qdrant and no embedding model at query time; misses paraphrased questions (exact word match only).
3. **`RETRIEVER=dense`**: one search; weakest of the two on table A.

`RETRIEVAL_TOP_K` candidates: **5** (current default) and **10**.

RRF settings (`rrf_k` 60, per-retriever top 50) are **not tuned** here: with 30 questions, tuning them on the same items the decision uses would fit noise. They stay at the literature default and are recorded as fixed.

## Decision rule (set 2026-10-20, before the hybrid numbers)
Confirmed before any number existed: LDN on 2026-10-21 (#85, including both bars); FAO's answer on the latency guard pending. The wording below was clarified to match `compare` output on 2026-10-21, without changing the rule.

Numbers: LDN's run (W3-D4-LDN-1, `evaluation/reports/retrieval-v1.md`), 30 answerable dev items, questions as asked, same index snapshot for all three, `k` in {1, 5, 10}. "Questions" below means recall × 30; a difference in questions is the sum over the 30 items of the per-question recall difference (the `questions` column of `scitech_eval compare`, #90), so it can be fractional for items with two relevant papers.

**Retriever.**
1. **hybrid**, unless one single retriever has a recall@5 higher than hybrid's by **at least 2.0 questions** and an MRR that is not lower (point value of the mean MRR difference, 0 or positive; the bootstrap interval of the difference is reported but not used by the rule). The 2-question bar is the one ADR 0007 used for the same reason (noise at n = 30).
2. If that happens, the single retriever that passes it. If both pass, the one with the higher recall@5; if still tied, the one with the higher MRR. `compare` pairs each single retriever with hybrid only, so this step and the k step below use the per-run means of the metrics table in `retrieval-v1.md`.
3. Latency guard: the chosen retriever's p95 query latency from W3-D5-FAO-1 must be under **1 s** on the machine that will run the backend. If hybrid fails only this guard, choose the single retriever with the higher recall@5 and record the gap. *(1 s is a proposal: retrieval is one step before a 1.5 s median LLM answer, ADR 0006; to be confirmed in review.)*

On a near tie the rule prefers hybrid, because it covers both failure modes seen so far (paraphrase for bm25, exact technical terms for dense) at the cost of one extra in-memory search.

**k.**
- `RETRIEVAL_TOP_K` stays **5**, unless the chosen retriever's recall@10 is higher than its recall@5 by **at least 3 questions**. Then use 10, and W4-D4-LDN-1 checks faithfulness with 10 chunks before the final runs.
- The bar is higher than for the retriever (3, not 2) because a larger k has a cost the golden set does not measure (prompt length, answer latency, faithfulness on long context). *(Proposal; to be confirmed in review.)*

**`RETRIEVAL_MIN_SCORE`.** Not set by this ADR. Its scale depends on the retriever (cosine, BM25 or RRF, at most about 0.033 for hybrid), so it stays 0.0. Until W5 the "insufficient evidence" path depends on the answer prompt (W4-D1-DAT-1) and then the evidence check (W5-D3-DAT-1), not on a score threshold.

## Measurements
*(D09: fill in from `evaluation/reports/retrieval-v1.md` and `pipelines/reports/index_profile.md`.)*

**B. Retrieval quality, official run, exact search (`QDRANT_SEARCH_EXACT=true` for all three runs, recorded in the run files).** Run file, commit, golden set sha256, index snapshot:

| Retriever | recall@1 | recall@5 (95% CI) | recall@10 | MRR | questions where it beats / loses to hybrid at 5 |
|---|---:|---:|---:|---:|---:|
| dense | | | | | |
| bm25 | | | | | |
| hybrid | | | | | — |

**C. Latency and memory** (W3-D5-FAO-1): p50 / p95 per retriever, RAM of Qdrant and of the BM25 index after load, machine.

## Decision
*(D09: apply the rule to tables B and C, unchanged. State that the evidence is preliminary: 30 dev items, one index snapshot.)*

## Consequences
*(D09.)* To be written with the decision. Already known:
- Whatever is chosen, the other two retrievers stay available through `RETRIEVER` for the final comparison (RQ1, W7), which uses the test items 31-60, not these dev items.
- Revisit when the golden set reaches 60 items, if the embedding model changes (ADR 0007), or if the chunking changes.
- If the decision lands late on D09, this ADR merges as "proposed" and becomes "accepted" by D10 09:00 (W3-D5-DAT-1 replan); W4-D1-DAT-1 starts with `RETRIEVER=hybrid` meanwhile.
