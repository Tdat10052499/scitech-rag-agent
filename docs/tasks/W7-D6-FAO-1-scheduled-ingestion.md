# W7-D6-FAO-1 Scheduled ingestion: `incremental-run` every 2 hours with BM25 rebuild

- Area: data | infra
- Milestone: Week 7 (work on a branch), merged in Week 8 after Gate W7
- Depends on: W7-D6-DAT-1 (ADR 0011 accepted, issue opened)

## Goal
New arXiv `cs.CL` papers reach the serving index automatically, at most about 2 hours after arXiv publishes their metadata, for both halves of hybrid retrieval, without touching the frozen evaluation index (ADR 0011).

## Context to read
- `docs/decisions/0011-scheduled-ingestion.md`, `docs/decisions/0008-incremental-ingestion.md`
- `pipelines/src/scitech_pipelines/incremental_run.py`, `pipelines/AGENTS.md` (`incremental-run`)
- `docs/runbooks/data-pipeline.md` section 6, issue #119 (BM25 not rebuilt)

## Inputs and outputs
- Inputs: watermark `data/state/incremental.json`; live collection `scitech_chunks_live`; live BM25 dir `data/index/bm25-live`.
- Outputs:
  - `incremental-run` options: `--until today|yesterday` (default `yesterday`, as now), `--rebuild-bm25 <dir>`, a lock file `data/state/incremental.lock`, a per-record filter against the last run's `(id, datestamp)` pairs.
  - A one-time setup command or script that creates `scitech_chunks_live` and `data/index/bm25-live` as copies of the frozen collection and BM25 index.
  - `docker/ingest/Dockerfile` (Python, Java 17 JRE) and its entry script, a scheduler loop `scitech_pipelines.schedule`; the compose service itself is added by DAT (shared file).
  - `docs/runbooks/data-pipeline.md` section 6 updated (schedule, logs, how to stop it).

## Scope
- May change: `pipelines/`, `docker/ingest/` (new), `docs/runbooks/data-pipeline.md`, `.env.example` (new variables with safe placeholders: `INGEST_EVERY_HOURS` (default 2), `INGEST_COLLECTION`, `FROZEN_COLLECTION`, `BM25_LIVE_DIR`).
- Must not change: `docs/contracts/`, the frozen collection `scitech_chunks`, `data/index/bm25`, `evaluation/`.

## Acceptance criteria
- [ ] `incremental-run --until today` fetches up to today (UTC); the next run starts at the watermark day as before (ADR 0008 point 1).
- [ ] Only records whose `(id, datestamp)` is new or changed since the last successful run go to clean, embed and load. When none is left, the run skips those steps, keeps the watermark and logs `incremental: nothing changed`.
- [ ] After a successful load the run's raw fetch file is deleted and its manifests are kept (C: has about 2 GB free on the serving laptop).
- [ ] A second run started while one holds the lock exits at once with a clear message and a non-zero code; a stale lock (process gone) is taken over.
- [ ] `--rebuild-bm25 <dir>` builds the BM25 index from the live collection's chunks (old text of replaced papers gone) into a new directory and switches to it atomically; a failed build leaves the old index in use.
- [ ] `incremental-run` refuses `--collection` equal to `FROZEN_COLLECTION`.
- [ ] Unit tests with fakes for the new rules (until today, nothing changed, lock, refuse frozen, BM25 switch); `make lint test` passes.
- [ ] One real end-to-end run in the `ingest` container against `scitech_chunks_live`, numbers recorded in the runbook (records, chunks, points before/after, wall time, BM25 build time).

## How to test
```bash
make lint test
PYTHONPATH=pipelines/src:agent/src python -m scitech_pipelines incremental-run \
  --collection scitech_chunks_live --until today --rebuild-bm25 data/index/bm25-live \
  --model BAAI/bge-small-en-v1.5 --device cpu
# run the same command again at once: expect "nothing changed" in a few seconds
```

## Notes / risks
- BM25 is built by scrolling the live collection's payloads (decided on #149): after replacements they are the source of truth, and no incremental `chunks.parquet` has to be kept. Record the build time in the PR.
- Peak memory of a BM25 build is about 1.2 GB (`docs/runbooks/data-pipeline.md`); record the Docker Desktop memory limit and the measured peak in the runbook on the first real run.
- No merge before Gate W7 (D19): Week 7 runs must not see any change.
