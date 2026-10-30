# Evaluation snapshot

What every Week 7 run uses. After the feature freeze (W6-D4, D16, Fri 2026-10-30), nothing below
changes until D22 unless the team approves it in the tracking issue. W7-D1-DAT-1 checks the
stack against this file before the first run.

<!-- The index section is final as of D16 (2026-10-30); section 2 is DAT's (W6-D5-DAT-1). -->

## 1. Index (W6-D4-FAO-1)

| Item | Value | Source |
|---|---|---|
| `index_snapshot` | `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37` | `data/processed/index/_load_manifest.json` |
| `dataset_snapshot` | `kaggle-arxiv-v307-cs.CL-2026-10-10` | Kaggle `Cornell-University/arxiv` version 307, updated 2026-10-10 (`docs/03-data-sources.md`) |
| Documents | 121,860 `cs.CL` records, cross-lists included | `_clean_manifest.json`, `pipelines/reports/data_profile.md` |
| Chunks = vectors = points | 121,926 | `_chunk_manifest.json`, `_embed_manifest.json`, `_load_manifest.json` |
| Chunking | at most 320 words per chunk, 48 words of overlap (the defaults of `chunk`) | ADR 0007, `pipelines/src/scitech_pipelines/chunk.py` |
| Embedding model | `BAAI/bge-small-en-v1.5`, 384 dimensions, cosine | ADR 0007 |
| Query prefix | `Represent this sentence for searching relevant passages:` (no passage prefix) | ADR 0007 |
| Vector store | Qdrant 1.19.2 (`docker-compose.yml`), collection `scitech_chunks`, exact search (`QDRANT_SEARCH_EXACT=true`) | #101, `pipelines/reports/index_profile.md` |
| BM25 index | `data/index/bm25`, 121,926 chunks, built from the same `chunks.parquet` (its `chunked_at` is the `chunked-` part of the id) | `_bm25_manifest.json`, `index_profile.md` |
| Where it lives | FAO's laptop (Docker Qdrant and `data/`); the documents, chunks and vectors also sit in FAO's private Kaggle dataset and notebook output (`pipelines/README.md`) | |

Rules for the frozen index:
- **Incremental loads never touch it.** `incremental-run` (ADR 0008) adds to the collection it is
  given, so it is never pointed at `scitech_chunks` before D22 (`docs/runbooks/data-pipeline.md`
  §6). Its live test (#124) ran on a copy on Kaggle, not on this collection.
- **A rebuild must give the same id.** Any rebuild for evaluation must end with the
  `index_snapshot` above and 121,926 points, or the runs are not comparable. `compare` warns when
  two runs name different snapshots.
- **Golden coverage:** every `relevant_doc_ids` of the golden set must be in the collection
  (`pipelines/scripts/golden_coverage.py --qdrant`, W7-D1-FAO-1). On 2026-10-27 all 57 ids of the
  47 items were found both in the chunks and in Qdrant `scitech_chunks`; W7-D1 runs it again on
  the final set (at least 60 items).

How to check that a machine serves this index (repository root, Qdrant up, PowerShell):

```powershell
$m = Get-Content data/processed/index/_load_manifest.json | ConvertFrom-Json
$m.index_snapshot; $m.counts
(Get-Content data/index/bm25/_bm25_manifest.json | ConvertFrom-Json).chunked_at
(Invoke-RestMethod -Method Post -Uri http://localhost:6333/collections/scitech_chunks/points/count -ContentType application/json -Body '{"exact": true}').result.count
```

The id must match the table, the BM25 `chunked_at` must be `2026-10-17T05:19:12`, and the count
must be 121926.

Checked on FAO's laptop on 2026-10-27: the id matched the table, the load manifest gave 121,926
points in 15 parts (0 resumed), the BM25 `chunked_at` was `2026-10-17T05:19:12+00:00`, and Qdrant
counted 121,926 points.
Checked again on 2026-10-30 through the `make up` stack (#146): Qdrant counted 121,926 points, so
the user-study host serves this exact index.

## 2. Model, prompts and configuration (W6-D5-DAT-1)

### Faithfulness judge (decided on #142, 2026-10-27)

| Field | Value | Source |
|---|---|---|
| Judge model | `qwen2.5:7b`, Q4_K_M, Ollama digest `845dbda0ea48` (read on D08) | ADR 0006 table note, #142 |
| Served by | the same Kaggle Ollama session as the generator (`llama3.2:3b`); a different model family, as `evaluation/PLAN.md` section 5 requires | #142 |
| How the runner calls it | `OpenAICompatibleLLM` with its own variables `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `JUDGE_MODEL` (values only in local `.env`) | #142 |
| Settings | temperature 0, one sentence per call, prompt `evaluation/prompts/faithfulness-judge.md`; `max_tokens` and the prompt commit are recorded in each run file; an unreadable reply is `judge_error`, not retried, not counted | #142 |
| Switch rule | only if a hosted key arrives before D17: switch once, re-run the 10 pilot questions, recompute agreement; never mix judges across W7 conditions | #142 |

<!-- TODO(W6-D5-DAT-1): generator model, tag, quantisation and Ollama version (ADR 0006); judge
model; prompts commit; RETRIEVER, RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE and other flags; tag
v0.6-rc. -->
