# 0007. Embedding model: TBD (bge-small-en-v1.5 or bge-base-en-v1.5)

- Status: proposed (draft: the recall table is filled from the Kaggle run of `pipelines/scripts/compare_embeddings.py`)
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

TBD: paste `summary.md` from the Kaggle run (notebook, date, golden-set commit and item count).

**C. Chunks longer than the model's input.** Same script: every chunk text tokenized with the model's tokenizer (special tokens included) and compared with `max_seq_length`. Longer chunks were cut when embedded, so their end is not in the vector.

TBD: paste the token table from the same run.

## Decision
TBD after table B. Rule set before the run, so the numbers do not pick the rule:
- **`bge-base-en-v1.5`** only if its recall@5 (questions as asked, with the query instruction) is higher than bge-small's by at least 2 questions of the answerable set, and its MRR is not lower.
- Otherwise **`bge-small-en-v1.5`**: half the index memory and about 3 times faster query encoding on a CPU (inferred from the throughput ratio in table A), with quality we cannot tell apart on 30 questions.
- The query side uses the instruction above unless table B shows the run without it scoring higher for the chosen model. Passages get no prefix (`passage_prefix` is empty in `_embed_state.json`, as the model card says).
- If table C shows chunks over the limit, lower `CHUNK_MAX_WORDS`, re-run `chunk` and re-embed the chosen model before the load (W3-D3-FAO-1), unless they are under 0.1% of chunks; then they stay and the number is recorded here.

## Consequences
- `EMBEDDING_MODEL` is set to the chosen model in every environment. The vectors of both models already exist (table A), so the load on D09 needs no new GPU run unless table C asks for re-chunking.
- The query side must apply the same instruction as table B. The dense retriever (W3-D2-DAT-1) reads it from configuration, next to `EMBEDDING_MODEL`; adding that variable to `.env.example` is DAT's call in that task.
- The model is English-only. Per `evaluation/PLAN.md` (issue #7), the Vietnamese question group is dropped, because no multilingual model was part of the D08 run. Revisit only if a multilingual model is embedded later.
- Recall@5 on 30 questions is preliminary. W3-D4-LDN-1 (dense vs BM25 vs hybrid) and the 45- and 60-item golden sets re-measure the chosen model; if recall there is far below table B, revisit this ADR.
- Revisit if the chunk size changes (`CHUNK_MAX_WORDS`), since table C depends on it.
