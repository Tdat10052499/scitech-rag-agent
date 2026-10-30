# W7-D7-DAT-1 BM25 reload in the backend and `ingest` compose service

- Area: backend | agent | infra
- Milestone: Week 7 (work on a branch), merged in Week 8 after Gate W7
- Depends on: W7-D6-DAT-1; the `ingest` image from W7-D6-FAO-1 for the compose part

## Goal
The running backend uses the BM25 index that the scheduled ingestion rebuilds, without a restart, and `make up` starts the 2-hourly ingestion next to Qdrant (ADR 0011). With the default settings, behaviour is exactly the frozen one.

## Context to read
- `docs/decisions/0011-scheduled-ingestion.md`
- `backend/src/app/main.py` (`_real_agent`, `lru_cache`), `agent/src/scitech_agent/retrieval/hybrid.py`, `agent/src/scitech_agent/retrieval/keyword.py` (`BM25Index.load`)
- `docker-compose.yml`, `Makefile`, `docs/runbooks/` (stack runbook)

## Inputs and outputs
- Inputs: `BM25_INDEX_DIR` (live: `data/index/bm25-live`), new `BM25_RELOAD_SECONDS` (default `0` = off).
- Outputs: reload logic in the keyword retriever or the agent factory; `ingest` service in `docker-compose.yml` using `docker/ingest/`; `.env.example` and the stack runbook updated.

## Scope
- May change: `agent/src/scitech_agent/retrieval/`, `backend/src/app/`, `docker-compose.yml`, `Makefile`, `.env.example`, `docs/runbooks/`.
- Must not change: `docs/contracts/` (no new endpoint or field), `evaluation/`, the frozen collection and BM25 directory.

## Acceptance criteria
- [ ] With `BM25_RELOAD_SECONDS=0` nothing changes: existing tests pass unchanged and no file is watched.
- [ ] With `BM25_RELOAD_SECONDS=N` > 0, a request after the live index switched (manifest changed) is answered with the new index within N seconds; requests in flight finish on the old one; a broken new index is logged and the old one kept.
- [ ] `make up` starts `ingest` only when `INGEST_ENABLED=1` (default off), with `INGEST_COLLECTION=scitech_chunks_live`; `make down` stops it; its log goes to `data/logs/incremental.log`.
- [ ] Unit test of the reload with a fake clock and two tiny indexes; `make lint test` passes.

## How to test
```bash
make lint test
INGEST_ENABLED=1 BM25_RELOAD_SECONDS=60 make up
# ask a question about a paper announced today; after the next scheduled run it is cited
```

## Notes / risks
- Swap the whole retriever object under a lock, never mutate the index in place.
- Shared files (`docker-compose.yml`, `Makefile`) change through the issue opened in W7-D6-DAT-1.
