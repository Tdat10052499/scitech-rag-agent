# Week 3: Chunking, embeddings, index and retrieval (2026-10-19 to 2026-10-23)

Goal: the full corpus is searchable with dense, keyword and hybrid retrieval, and the first retrieval numbers exist.

Gate (Friday): chunks valid against `chunk.schema.json`; embeddings for the full corpus (or a documented subset) loaded into Qdrant; dense, BM25 and hybrid retrievers implement the `Retriever` protocol; `evaluation/reports/retrieval-v1.md` compares the three on the golden set; ADR 0007, 0008, 0009 merged.

## W3-D1
Monday 2026-10-19 · D11

### DAT (@Tdat10052499)

#### W3-D1-DAT-1 [blocking] Qdrant store module
- Module: `agent/src/scitech_agent/store.py`, `docker-compose.yml` (pin the Qdrant image version)
- Do: functions to create the collection (vector size from config, cosine distance, payload indexes on `source`, `categories`, `published_at`), upsert batches, search with filters. Integration test marked `@pytest.mark.integration` that runs only when `QDRANT_URL` is reachable.
- Done when: unit tests pass in CI; integration test passes locally with `make up`.
- Depends on: W2-D3-DAT-1

### FAO (@F4ol4n)

#### W3-D1-FAO-1 [blocking] Chunker
- Module: `pipelines/src/scitech_pipelines/chunk.py`
- Do: create chunks from title + abstract (and other text fields if in scope): configurable max length and overlap, `chunk_id = <doc_id>#<chunk_index>`, all metadata copied per `chunk.schema.json`. Write `data/processed/chunks/` as Parquet.
- Done when: test validates every fixture chunk against the JSON schema; full run done with chunk count and length stats in the journal.
- Depends on: W2-D2-FAO-1, W1-D4-DAT-1

### LDN (@Yui-Mika)

#### W3-D1-LDN-1 Run configuration and run log format
- Module: `evaluation/`
- Do: YAML config for runs (retriever type, k, embedding model, index snapshot, notes); every run stores config, commit hash, dataset snapshot id (from FAO's manifest) and timings; add `python -m scitech_eval compare run1 run2` printing a metrics table.
- Done when: tests pass on toy runs.
- Depends on: W2-D4-LDN-1

## W3-D2
Tuesday 2026-10-20 · D12

### DAT (@Tdat10052499)

#### W3-D2-DAT-1 Dense retriever
- Module: `agent/src/scitech_agent/retrieval/dense.py`
- Do: embed the query with the same model as the corpus (shared embedding helper, prefix rules if the model needs them), search Qdrant, return `ScoredChunk` list; respect `RETRIEVAL_TOP_K` and filters.
- Done when: unit tests with a fake store; manual test against the loaded index after FAO's load (D13).
- Depends on: W3-D1-DAT-1

### FAO (@F4ol4n)

#### W3-D2-FAO-1 [blocking] ADR 0007 and embedding job
- Module: `docs/decisions/0007-embedding-model.md`, `pipelines/src/scitech_pipelines/embed.py`
- Do: compare 2 candidate open embedding models on 30 golden questions using a small index (quick recall@5 with LDN's harness) and on throughput (chunks/second on your hardware or Colab). If users will ask in Vietnamese, include Vietnamese test queries. Then implement `embed`: batched, resumable, writes vectors + `chunk_id` to Parquet, records model name in `embedding_model`.
- Done when: ADR 0007 merged; full embedding run started (or done) with throughput logged.
- Depends on: W3-D1-FAO-1, W2-D4-LDN-1

### LDN (@Yui-Mika)

#### W3-D2-LDN-1 Sources panel and evidence states
- Module: `frontend/`
- Do: sources list with title, year, categories, score and link; highlight citation numbers `[n]` in the answer and link them to the sources list; distinct style for the "insufficient evidence" answer.
- Done when: works with the stub events; screenshot in PR.
- Depends on: W2-D2-LDN-1

## W3-D3
Wednesday 2026-10-21 · D13

### DAT (@Tdat10052499)

#### W3-D3-DAT-1 Keyword (BM25) retriever
- Module: `agent/src/scitech_agent/retrieval/keyword.py`
- Do: build a BM25 index over chunk texts from `data/processed/chunks/` (simple tokenisation, lowercasing, stop words optional), persist it to `data/index/bm25/`, search returns `ScoredChunk`s.
- Done when: unit tests on a toy corpus; build time and memory for the full corpus recorded.
- Depends on: W3-D1-FAO-1

### FAO (@F4ol4n)

#### W3-D3-FAO-1 [blocking] Load index into Qdrant
- Module: `pipelines/src/scitech_pipelines/load.py`
- Do: idempotent upsert of embeddings + payload into Qdrant using DAT's store module; resume from last batch; final count check (points == chunks).
- Done when: full corpus (or documented subset with reason) loaded; counts match; load time logged; snapshot id written to a manifest the eval runs can cite.
- Depends on: W3-D2-FAO-1, W3-D1-DAT-1

### LDN (@Yui-Mika)

#### W3-D3-LDN-1 First dense-retrieval evaluation
- Module: `evaluation/runs/`, `evaluation/reports/`
- Do: run the harness with the dense retriever on the 30-item golden set; inspect 5 failures (wrong or missing documents) and note likely causes.
- Done when: run file committed (small JSON) and failure notes in the journal.
- Depends on: W3-D2-DAT-1, W3-D3-FAO-1

## W3-D4
Thursday 2026-10-22 · D14

### DAT (@Tdat10052499)

#### W3-D4-DAT-1 Hybrid retriever (RRF)
- Module: `agent/src/scitech_agent/retrieval/hybrid.py`
- Do: reciprocal rank fusion of dense and BM25 results with configurable constant and per-retriever top-k; deduplicate by `chunk_id`; expose as the default `Retriever` behind a config switch `RETRIEVER=dense|bm25|hybrid`.
- Done when: unit tests for fusion order on a hand-made example.
- Depends on: W3-D2-DAT-1, W3-D3-DAT-1

### FAO (@F4ol4n)

#### W3-D4-FAO-1 ADR 0008: incremental ingestion design
- Module: `docs/decisions/0008-incremental-ingestion.md`, `pipelines/src/scitech_pipelines/incremental.py`
- Do: design ingestion of new items since a stored watermark (date or token) through the same clean -> chunk -> embed -> load steps; decide scheduling (manual command, cron/Task Scheduler, or GitHub Actions without data) and whether Kafka is required (instructor answer). Prototype fetching the latest day of new items.
- Done when: ADR merged; prototype fetches and cleans one day of new items.
- Depends on: W2-D2-FAO-1

### LDN (@Yui-Mika)

#### W3-D4-LDN-1 Compare dense, BM25, hybrid; golden set to 45
- Module: `evaluation/reports/retrieval-v1.md`, `evaluation/golden_set/`
- Do: run all three retrievers; table of recall@1/5/10 and MRR with sample size; short discussion of differences and their limits (small n). Add 15 golden items (total 45).
- Done when: report merged and reviewed by FAO.
- Depends on: W3-D4-DAT-1, W3-D3-LDN-1

## W3-D5
Friday 2026-10-23 · D15 · Gate day

### DAT (@Tdat10052499)

#### W3-D5-DAT-1 ADR 0009 and Week 3 gate
- Module: `docs/decisions/0009-default-retrieval.md`
- Do: choose default retriever and k from LDN's report (state that the evidence is preliminary); run the gate checklist; merge; close milestone.
- Done when: ADR merged; gate status recorded.
- Depends on: W3-D4-LDN-1

### FAO (@F4ol4n)

#### W3-D5-FAO-1 Retrieval latency and filters check
- Module: `pipelines/reports/index_profile.md`
- Do: measure index size on disk, RAM use of Qdrant, query latency (p50/p95 over 100 queries) for dense, BM25, hybrid; check filters by year/category work.
- Done when: report merged with method and hardware stated.
- Depends on: W3-D3-FAO-1, W3-D4-DAT-1

### LDN (@Yui-Mika)

#### W3-D5-LDN-1 Retrieval debug view (optional) or UI polish
- Module: `frontend/`
- Do: if time allows, a hidden/debug toggle that shows retrieval scores and chunk text for each source; otherwise fix open UI issues.
- Done when: PR merged or issues closed.
- Depends on: W3-D2-LDN-1
