# 0007. Embedding model: bge-small-en-v1.5 with the query instruction

- Status: accepted (2026-10-20, DAT's review on #59; table B from the 30 answerable golden items of #56)
- Date: 2026-10-17
- Deciders: FAO (author), DAT (reviewer), LDN (harness and golden set)

## Context
The dense index needs one embedding model for the chunks (W3-D2-FAO-1) and the same model, with the same query handling, on the query side (DAT's dense retriever, W3-D2-DAT-1). The model is read from `EMBEDDING_MODEL`; this ADR fixes its value.

Constraints:
- The corpus is English: titles and abstracts of arXiv `cs.CL`, 121,860 documents in 121,926 chunks of `<title>. <abstract window>` (ADR 0003, W3-D1-FAO-1, `CHUNK_MAX_WORDS` 320).
- Open models only, run by us. The full embedding run must fit one free GPU session (Kaggle T4); queries are embedded on the backend machine, possibly without a GPU.
- The index (Qdrant, W3-D3-FAO-1) must fit the RAM of a member's laptop next to the backend.
- Evidence for quality is small: the golden set has 30 answerable items (#56, W2-D3-LDN-1). Recall@5 on this many questions is a coarse signal; differences of one or two questions are within noise.

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

Run: Kaggle notebook "ADR 0007 comparison", Version 2, 2026-10-18, CPU only (Accelerator None), this script at `df77466`, sentence-transformers as installed by `pip` that day (version not recorded). Golden set: LDN's batch on #56 at `5f1dbfb` (`golden.jsonl` sha256 `a21855e5183ea08aef98eb3c522527a02a5a81d6350fc028f9e1175180968378`, as the harness run files record it), 32 items, of which 30 answerable English dev items are scored (2 unanswerable excluded); 37 query texts: the 32 questions and the standalone rewrites of the 5 follow-up items. Index: the 121,926 vectors of table A for each model.

| Model | Query instruction | recall@1 | recall@5 (95% CI) | recall@10 | MRR | recall@5, standalone queries |
|---|---|---:|---:|---:|---:|---:|
| `BAAI/bge-base-en-v1.5` | yes | 0.300 | 0.317 (0.167-0.483) | 0.450 | 0.367 | 0.417 |
| `BAAI/bge-base-en-v1.5` | no | 0.200 | 0.300 (0.150-0.450) | 0.417 | 0.266 | 0.400 |
| `BAAI/bge-small-en-v1.5` | yes | 0.183 | **0.283** (0.133-0.450) | 0.317 | **0.253** | **0.417** |
| `BAAI/bge-small-en-v1.5` | no | 0.183 | 0.283 (0.133-0.450) | 0.300 | 0.243 | 0.383 |

Recall is per question (the share of its relevant documents found), averaged over the 30 items; the 95% interval is the harness's bootstrap. Items missed at 5 with the instruction: bge-base 19 (gs-001, 002, 003, 004, 007, 008, 012, 014, 015, 018, 019, 022, 023, 024, 025, 026, 028, 029, 030), bge-small 21 (the same except gs-030, plus gs-005, 020 and 021).

First look, kept for the record: Version 1 of the same notebook (2026-10-17, script `56196dd`, #56 at `f0015d1`, 21 answerable items) gave recall@5 with the instruction 0.405 (bge-base) and 0.310 (bge-small), MRR 0.458 and 0.290. That met the rule below by exactly 2.0 questions. The 9 items added since (gs-022 to gs-030) went the other way: bge-small found 2.0 of them at 5, bge-base 1.0. This is the noise the Context warns about.

**C. Chunks longer than the model's input.** Same script: every chunk text tokenized with the model's tokenizer (special tokens included) and compared with `max_seq_length`. Longer chunks were cut when embedded, so their end is not in the vector.

| Model | max_seq_length | Chunks over | Documents over | Max tokens | p99 | Median |
|---|---:|---:|---:|---:|---:|---:|
| `BAAI/bge-base-en-v1.5` | 512 | 82 of 121,926 (0.067%) | 81 | 780 | 429 | 250 |
| `BAAI/bge-small-en-v1.5` | 512 | 82 of 121,926 (0.067%) | 81 | 780 | 429 | 250 |

Both models use the same tokenizer, so the counts are identical. 82 chunks lose their last tokens (`CHUNK_MAX_WORDS` 320 words is usually under 512 tokens, median 250, but not for text with many symbols or numbers).

## Decision
**`BAAI/bge-small-en-v1.5`, with the query instruction `Represent this sentence for searching relevant passages: ` on queries and no passage prefix. `CHUNK_MAX_WORDS` stays at 320.**

By the rule below, written before the first run and applied unchanged to the 30-item run:
- Recall@5 with the instruction: bge-base 0.317, bge-small 0.283. Over 30 items that is 9.5 against 8.5 questions (0.317 x 30 and 0.283 x 30), a difference of 1.0, under the bar of 2. So the rule picks bge-small.
- bge-base is ahead on the other columns (recall@1 0.300 against 0.183, recall@10 0.450 against 0.317, MRR 0.367 against 0.253), but the rule makes recall@5 the deciding number because the agent answers from the top 5 chunks (`RETRIEVAL_TOP_K=5`); MRR only guards against a worse ranking for the winner. These leads are recorded here so the follow-up measurements below can check them.
- For bge-small the instruction does not lower any metric and helps MRR (0.243 to 0.253), recall@10 (0.300 to 0.317) and the standalone queries (0.383 to 0.417), so the query side uses it.
- Table C: 82 chunks (0.067%) are over 512 tokens, under the 0.1% threshold, so they stay as embedded and no re-chunking is needed.
- The evidence is weak: 30 items, and the 95% intervals of the two models overlap almost completely. The 21-item run picked the other model by the same rule, so neither result is a clear win; the rule decides, and on a near tie it takes the cheaper model.

Rule set before the first run, so the numbers do not pick the rule:
- **`bge-base-en-v1.5`** only if its recall@5 (questions as asked, with the query instruction) is higher than bge-small's by at least 2 questions of the answerable set, and its MRR is not lower.
- Otherwise **`bge-small-en-v1.5`**: half the index memory and about 3 times faster query encoding on a CPU (inferred from the throughput ratio in table A), with quality we cannot tell apart on 30 questions.
- The query side uses the instruction above unless table B shows the run without it scoring higher for the chosen model. Passages get no prefix (`passage_prefix` is empty in `_embed_state.json`, as the model card says).
- If table C shows chunks over the limit, lower `CHUNK_MAX_WORDS`, re-run `chunk` and re-embed the chosen model before the load (W3-D3-FAO-1), unless they are under 0.1% of chunks; then they stay and the number is recorded here.

## Consequences
- `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` in every environment. Its vectors already exist (table A, 198 MB, output of the "Embedding job" notebook), so the load on D09 needs no new GPU run.
- The query side must apply the instruction of table B. The dense retriever (W3-D2-DAT-1) reads it from configuration, next to `EMBEDDING_MODEL`; adding that variable to `.env.example` is DAT's call in that task.
- The model is English-only. Per `evaluation/PLAN.md` (issue #7), the Vietnamese question group is dropped, because no multilingual model was part of the D08 run. Revisit only if a multilingual model is embedded later.
- Switching later is cheap: the bge-base vectors exist too (385 MB), so a switch is one reload into Qdrant and one configuration change, with no GPU run. Re-measure with W3-D4-LDN-1 (dense vs BM25 vs hybrid, D09) and the 45- and 60-item golden sets: if bge-base then passes the rule above on the larger set, this ADR is superseded and the index is reloaded with it.
- Revisit if the chunk size changes (`CHUNK_MAX_WORDS`), since table C depends on it.
