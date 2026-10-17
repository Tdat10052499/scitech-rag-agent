# 0007. Embedding model: bge-base-en-v1.5 with the query instruction

- Status: proposed (table B from 21 answerable golden items; re-run when the set has 30)
- Date: 2026-10-17
- Deciders: FAO (author), DAT (reviewer), LDN (harness and golden set)

## Context
The dense index needs one embedding model for the chunks (W3-D2-FAO-1) and the same model, with the same query handling, on the query side (DAT's dense retriever, W3-D2-DAT-1). The model is read from `EMBEDDING_MODEL`; this ADR fixes its value.

Constraints:
- The corpus is English: titles and abstracts of arXiv `cs.CL`, 121,860 documents in 121,926 chunks of `<title>. <abstract window>` (ADR 0003, W3-D1-FAO-1, `CHUNK_MAX_WORDS` 320).
- Open models only, run by us. The full embedding run must fit one free GPU session (Kaggle T4); queries are embedded on the backend machine, possibly without a GPU.
- The index (Qdrant, W3-D3-FAO-1) must fit the RAM of a member's laptop next to the backend.
- Evidence for quality is small: the golden set has 23 items in #56 (21 answerable), 30 by D08 (W2-D3-LDN-1). Recall@5 on this many questions is a coarse signal; differences of one or two questions are within noise.

## Options considered
The two candidates measured in ADR 0003 (W1-D2-FAO-1):
1. **`BAAI/bge-small-en-v1.5`**: 384 dimensions, 33M parameters.
2. **`BAAI/bge-base-en-v1.5`**: 768 dimensions, 109M parameters.

Both are English-only, take at most 512 tokens, and expect the instruction `Represent this sentence for searching relevant passages: ` before each query (not before the passages). A multilingual model (for Vietnamese questions, `evaluation/PLAN.md`) was not measured; see Consequences.

## Measurement
**A. Throughput: full corpus, 2026-10-17.** Kaggle notebook "Embedding job W3-D2-FAO-1 [blocking]", Version 1, Tesla T4 (the code uses one GPU), `embed` at `c09fcf5` (#50), sentence-transformers 5.7.0, torch 2.11.0, batch size 64, no passage prefix. Both runs wrote 15 parts and passed the output check (count, distinct ids, dimension).

| Model | Dimension | Chunks | Encode time | Chunks/s | Vectors on disk |
|---|---:|---:|---:|---:|---:|
| `BAAI/bge-small-en-v1.5` | 384 | 121,926 | 863 s (14.4 min) | 141.2 | 198 MB |
| `BAAI/bge-base-en-v1.5` | 768 | 121,926 | 2,629 s (43.8 min) | 46.4 | 385 MB |

Both match the ADR 0003 estimates (about 14 and 41 min). Raw float32 vectors in memory: 187 MB (small) and 375 MB (base) for 121,926 chunks (chunks x dimension x 4 bytes); Qdrant adds its own overhead, measured in W3-D5-FAO-1.

**B. Retrieval quality: golden set, exact search.** `pipelines/scripts/compare_embeddings.py` embeds the golden questions with each model, ranks all 121,926 chunk vectors of table A by dot product (exact cosine search over the whole index, so the result does not depend on Qdrant settings), and scores the rankings with LDN's harness (`scitech_eval`, canned retriever; recall@k and MRR by `doc_id`, answerable English dev items only, unanswerable items excluded). Each model runs with and without the query instruction. "Standalone queries" uses the rewritten query of the follow-up items (the agent sends that one); every other item keeps its question.

Run: Kaggle notebook "ADR 0007 comparison", Version 1, 2026-10-17, CPU only (Accelerator None), this script at `56196dd`, sentence-transformers as installed by `pip` that day (version not recorded). Golden set: LDN's batch on #56 at `f0015d1`, 23 items, of which 21 answerable English dev items are scored (2 unanswerable excluded); 25 query texts: the 23 questions and the standalone rewrites of the 2 follow-up items. Index: the 121,926 vectors of table A for each model.

| Model | Query instruction | recall@1 | recall@5 (95% CI) | recall@10 | MRR | recall@5, standalone queries |
|---|---|---:|---:|---:|---:|---:|
| `BAAI/bge-base-en-v1.5` | yes | 0.381 | **0.405** (0.214-0.595) | 0.500 | **0.458** | 0.452 |
| `BAAI/bge-base-en-v1.5` | no | 0.238 | 0.333 (0.143-0.524) | 0.476 | 0.312 | 0.381 |
| `BAAI/bge-small-en-v1.5` | yes | 0.214 | 0.310 (0.119-0.524) | 0.333 | 0.290 | 0.405 |
| `BAAI/bge-small-en-v1.5` | no | 0.214 | 0.310 (0.119-0.524) | 0.333 | 0.290 | 0.357 |

Recall is per question (the share of its relevant documents found), averaged over the 21 items; the 95% interval is the harness's bootstrap. Items missed at 5 with the instruction: bge-base 11 (gs-001, 002, 003, 004, 007, 008, 012, 014, 015, 018, 019), bge-small 14 (the same 11 plus gs-005, gs-020 and gs-021). For bge-small the instruction left every question-as-asked metric unchanged and only moved the standalone queries (0.357 to 0.405); for bge-base it helped on every column.

**C. Chunks longer than the model's input.** Same script: every chunk text tokenized with the model's tokenizer (special tokens included) and compared with `max_seq_length`. Longer chunks were cut when embedded, so their end is not in the vector.

| Model | max_seq_length | Chunks over | Documents over | Max tokens | p99 | Median |
|---|---:|---:|---:|---:|---:|---:|
| `BAAI/bge-base-en-v1.5` | 512 | 82 of 121,926 (0.067%) | 81 | 780 | 429 | 250 |
| `BAAI/bge-small-en-v1.5` | 512 | 82 of 121,926 (0.067%) | 81 | 780 | 429 | 250 |

Both models use the same tokenizer, so the counts are identical. 82 chunks lose their last tokens (`CHUNK_MAX_WORDS` 320 words is usually under 512 tokens, median 250, but not for text with many symbols or numbers).

## Decision
**`BAAI/bge-base-en-v1.5`, with the query instruction `Represent this sentence for searching relevant passages: ` on queries and no passage prefix. `CHUNK_MAX_WORDS` stays at 320.**

By the rule below, written before the run:
- Recall@5 with the instruction: bge-base 0.405, bge-small 0.310. Over 21 items that is 8.5 against 6.5 (0.405 x 21 and 0.310 x 21), a difference of 2.0, so the "at least 2 questions" bar is met (exactly, not by a margin). MRR is higher too (0.458 against 0.290), and bge-base is ahead on every other column of table B.
- The instruction helps bge-base on every metric (recall@5 0.333 to 0.405, MRR 0.312 to 0.458), so the query side uses it.
- Table C: 82 chunks (0.067%) are over 512 tokens, under the 0.1% threshold, so they stay as embedded and no re-chunking is needed.
- The evidence is weak: 21 items, and the 95% intervals of the two models overlap almost completely. The rule exists so that this does not become a judgement call; bge-base costs twice the memory and about 3 times the CPU time per query (table A), which is affordable at this corpus size.

Rule set before the run, so the numbers do not pick the rule:
- **`bge-base-en-v1.5`** only if its recall@5 (questions as asked, with the query instruction) is higher than bge-small's by at least 2 questions of the answerable set, and its MRR is not lower.
- Otherwise **`bge-small-en-v1.5`**: half the index memory and about 3 times faster query encoding on a CPU (inferred from the throughput ratio in table A), with quality we cannot tell apart on 30 questions.
- The query side uses the instruction above unless table B shows the run without it scoring higher for the chosen model. Passages get no prefix (`passage_prefix` is empty in `_embed_state.json`, as the model card says).
- If table C shows chunks over the limit, lower `CHUNK_MAX_WORDS`, re-run `chunk` and re-embed the chosen model before the load (W3-D3-FAO-1), unless they are under 0.1% of chunks; then they stay and the number is recorded here.

## Consequences
- `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5` in every environment. Its vectors already exist (table A, 385 MB), so the load on D09 needs no new GPU run.
- The query side must apply the instruction of table B. The dense retriever (W3-D2-DAT-1) reads it from configuration, next to `EMBEDDING_MODEL`; adding that variable to `.env.example` is DAT's call in that task.
- The model is English-only. Per `evaluation/PLAN.md` (issue #7), the Vietnamese question group is dropped, because no multilingual model was part of the D08 run. Revisit only if a multilingual model is embedded later.
- Re-run table B when the golden set has 30 items (same notebook, a new version); if bge-base then misses the rule, this ADR switches to bge-small before the load. Recall on 21-30 questions is preliminary. W3-D4-LDN-1 (dense vs BM25 vs hybrid) and the 45- and 60-item golden sets re-measure the chosen model; if recall there is far below table B, revisit this ADR.
- Revisit if the chunk size changes (`CHUNK_MAX_WORDS`), since table C depends on it.
