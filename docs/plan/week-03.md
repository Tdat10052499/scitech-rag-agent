# Week 3 (phase 3 of 8): Chunking, embeddings, index and retrieval (2026-10-20 to 2026-10-22)

> Replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md). This phase has 3 working days (D07-D09).
> Task IDs are unchanged. Lines starting with **Replan:** say what changed.

Goal: the full corpus is searchable with dense, keyword and hybrid retrieval, and the first retrieval numbers exist.

Gate (D09, Thu 2026-10-22, end of day): chunks valid against `chunk.schema.json`; embeddings for the full corpus (or a documented subset) loaded into Qdrant; dense, BM25 and hybrid retrievers implement the `Retriever` protocol; `evaluation/reports/retrieval-v1.md` compares the three on the golden set; ADR 0007 and ADR 0009 merged (ADR 0008 moved to Week 5).

Critical chain of this phase: chunker (D07) -> embedding run (D08, overnight) -> load (D09 morning) -> evaluation and ADR 0009 (D09 afternoon). Any delay here moves the whole plan; report it in the tracking issue the same hour.

## D07
Tuesday 2026-10-20

### DAT (@Tdat10052499)

#### W3-D1-DAT-1 [blocking] Qdrant store module
- Module: `agent/src/scitech_agent/store.py`, `docker-compose.yml` (pin the Qdrant image version)
- Do: functions to create the collection (vector size from config, cosine distance, payload indexes on `source`, `categories`, `published_at`), upsert batches, search with filters. Integration test marked `@pytest.mark.integration` that runs only when `QDRANT_URL` is reachable.
- Done when: unit tests pass in CI; integration test passes locally with `make up`.
- Depends on: W2-D3-DAT-1

#### W3-D2-DAT-1 Dense retriever
- Module: `agent/src/scitech_agent/retrieval/dense.py`
- Do: embed the query with the same model as the corpus (shared embedding helper, prefix rules if the model needs them), search Qdrant, return `ScoredChunk` list; respect `RETRIEVAL_TOP_K` and filters.
- Done when: unit tests with a fake store (D07); manual test against the loaded index after FAO's load (D09 morning).
- Depends on: W3-D1-DAT-1

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

#### W3-D2-LDN-1 Sources panel and evidence states
- Module: `frontend/`
- Do: sources list with title, year, categories, score and link; highlight citation numbers `[n]` in the answer and link them to the sources list; distinct style for the "insufficient evidence" answer.
- **Replan:** LDN is away 2026-10-23 to 2026-10-26 and back on D13 (#10). Merged with W4-D1-LDN-1 into one D07 task, because both build the same component: sources panel, progressive token rendering with Markdown, clickable `[n]` references. No stop button. Done when: works against the backend with the fake LLM; screenshot or GIF in the PR. LDN leaves a hand-over note in the LDN journal on D07.
- Done when: works with the stub events; screenshot in PR.
- Depends on: W2-D2-LDN-1

## D08
Wednesday 2026-10-21

### DAT (@Tdat10052499)

#### W3-D3-DAT-1 Keyword (BM25) retriever
- Module: `agent/src/scitech_agent/retrieval/keyword.py`
- Do: build a BM25 index over chunk texts from `data/processed/chunks/` (simple tokenisation, lowercasing, stop words optional), persist it to `data/index/bm25/`, search returns `ScoredChunk`s.
- Done when: unit tests on a toy corpus; build time and memory for the full corpus recorded.
- Depends on: W3-D1-FAO-1

#### W3-D4-DAT-1 Hybrid retriever (RRF)
- Module: `agent/src/scitech_agent/retrieval/hybrid.py`
- Do: reciprocal rank fusion of dense and BM25 results with configurable constant and per-retriever top-k; deduplicate by `chunk_id`; expose as the default `Retriever` behind a config switch `RETRIEVER=dense|bm25|hybrid`.
- Done when: unit tests for fusion order on a hand-made example.
- Depends on: W3-D2-DAT-1, W3-D3-DAT-1

### FAO (@F4ol4n)

#### W3-D2-FAO-1 [blocking] ADR 0007 and embedding job
- Module: `docs/decisions/0007-embedding-model.md`, `pipelines/src/scitech_pipelines/embed.py`
- Do: compare 2 candidate open embedding models on 30 golden questions using a small index (quick recall@5 with LDN's harness) and on throughput (chunks/second on your hardware or Colab). If users will ask in Vietnamese, include Vietnamese test queries. Then implement `embed`: batched, resumable, writes vectors + `chunk_id` to Parquet, records model name in `embedding_model`.
- **Replan:** the full embedding run must start before the end of D08 and run overnight. If the measured throughput says it will not finish by D09 08:00, embed a documented subset (state size and reason in the ADR) rather than delay the load. Recall@5 on 30 questions is a coarse signal; say so in the ADR.
- Done when: ADR 0007 merged; full embedding run started (or done) with throughput logged.
- Depends on: W3-D1-FAO-1, W2-D4-LDN-1

### LDN (@Yui-Mika)

- (preparation, no new task ID) Run the ADR 0007 recall@5 comparison with FAO; start writing the 15 new golden items of W3-D4-LDN-1 (see D09) so only the comparison table is left for D09.

## D09
Thursday 2026-10-22 · Gate day

### DAT (@Tdat10052499)

#### W3-D5-DAT-1 ADR 0009 and Week 3 gate
- Module: `docs/decisions/0009-default-retrieval.md`
- Do: manual test of the dense retriever on the loaded index (end of W3-D2-DAT-1); choose default retriever and k from LDN's report (state that the evidence is preliminary); run the gate checklist; merge; close milestone.
- **Replan:** if LDN's comparison lands late in the evening, merge ADR 0009 as "proposed" on D09 and switch it to "accepted" by D10 09:00; W4-D1-DAT-1 can start with `RETRIEVER=hybrid` meanwhile.
- Done when: ADR merged; gate status recorded.
- Depends on: W3-D4-LDN-1

### FAO (@F4ol4n)

#### W3-D3-FAO-1 [blocking] Load index into Qdrant
- Module: `pipelines/src/scitech_pipelines/load.py`
- Do (morning): idempotent upsert of embeddings + payload into Qdrant using DAT's store module; resume from last batch; final count check (points == chunks).
- Done when: full corpus (or documented subset with reason) loaded; counts match; load time logged; snapshot id written to a manifest the eval runs can cite.
- Depends on: W3-D2-FAO-1, W3-D1-DAT-1

#### W3-D5-FAO-1 Retrieval latency and filters check
- Module: `pipelines/reports/index_profile.md`
- Do (afternoon): measure index size on disk, RAM use of Qdrant, query latency (p50/p95 over 100 queries) for dense, BM25, hybrid; check filters by year/category work.
- Done when: report merged with method and hardware stated.
- Depends on: W3-D3-FAO-1, W3-D4-DAT-1

### LDN (@Yui-Mika)

#### W3-D3-LDN-1 First dense-retrieval evaluation
- Module: `evaluation/runs/`, `evaluation/reports/`
- Do: run the harness with the dense retriever on the 30-item golden set; inspect 5 failures (wrong or missing documents) and note likely causes.
- **Replan:** inspect 3 failures instead of 5 (LDN may be busy on D08-D09, #10).
- Done when: run file committed (small JSON) and failure notes in the journal.
- Depends on: W3-D2-DAT-1, W3-D3-FAO-1

#### W3-D4-LDN-1 Compare dense, BM25, hybrid; golden set to 45
- Module: `evaluation/reports/retrieval-v1.md`, `evaluation/golden_set/`
- Do: run all three retrievers; table of recall@1/5/10 and MRR with sample size; short discussion of differences and their limits (small n). Add 15 golden items (total 45; drafted on D08).
- **Replan:** run on the 30 dev items (ADR 0009 cites dev numbers). Golden items 31-45 are written on D04-D07 if possible; if not, the D14 gate asks for >= 45 and the set reaches 60 by D16 (see W5-D1-LDN-1). **Plan B:** if LDN cannot run the comparison on D09, FAO or DAT runs the three retrievers with LDN's harness and pastes the table; LDN writes the discussion on D13, and ADR 0009 may merge as "proposed" (see W3-D5-DAT-1).
- Done when: report merged and reviewed by FAO.
- Depends on: W3-D4-DAT-1, W3-D3-LDN-1

## Cut or merged in the replan

| Task | Decision | Where it went / reason |
|---|---|---|
| W3-D4-FAO-1 ADR 0008: incremental ingestion design | Moved | To Week 5, D13, right before its implementation (W5-D2-FAO-1). Not on the W3 critical chain. |
| W3-D5-LDN-1 Retrieval debug view (optional) or UI polish | Cut | Cut-list item 3 (UI extras). UI polish happens in W6-D1-LDN-1. |
