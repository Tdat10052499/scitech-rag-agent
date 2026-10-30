# 0011. Scheduled incremental ingestion every 2 hours on a separate serving index

- Status: accepted (2026-10-30, FAO's review on #149)
- Date: 2026-10-30
- Deciders: DAT (author), FAO (pipelines owner, reviewer), LDN (evaluation impact)

## Context
The course requirement asks for data that is collected "in real time", which the team reads as an automatic update every 1 to 3 hours, not per second. ADR 0008 built the code for incremental ingestion (`incremental-run`, live test passed on 2026-10-27) but decided in point 6: "one manual command, run on demand; no unattended schedule for v1.0".

Facts (sources in brackets):
- arXiv announces new papers in one daily batch, around 22:30 ET Sunday to Thursday, and updates OAI-PMH metadata nightly (ADR 0008, Context). New data therefore appears about once a day whatever the polling interval.
- `incremental-run` fetches from the watermark day to **yesterday (UTC)** (`pipelines/src/scitech_pipelines/incremental_run.py`, `run_incremental`). With a 2-hour schedule, most runs would fetch the watermark day again and re-embed it: 177 papers in 1 min 13 s on a Kaggle CPU (ADR 0008, live test, run 2).
- Rate limit of arXiv: one request every 3 s, one connection (ADR 0008). A day is one or two requests, so a 2-hour schedule is far inside the limit.
- `incremental-run` does not rebuild BM25, so the default retriever (`RETRIEVER=hybrid`) sees new papers only through its dense half, and BM25 keeps the old text of replaced papers (#119, `docs/runbooks/data-pipeline.md` section 6).
- The backend loads the BM25 index once per process (`agent_from_env` behind `lru_cache` in `backend/src/app/main.py`), so a rebuilt index is not seen without a restart.
- The serving machine (FAO's laptop) has Java 8; `clean` needs Java 17+ (ADR 0005, ADR 0008 point 6).
- Feature freeze was declared on D16 (2026-10-30). The evaluation index is frozen from W6-D4 to D22 (`docs/plan/week-06.md`), and Week 7 allows no feature work on the evaluated system (`docs/plan/week-07.md`).

## Options considered
Schedule:
1. Keep ADR 0008 point 6 (manual) and describe a schedule as future work.
2. Daily cron after arXiv's nightly update (the line already written in ADR 0008 point 6).
3. Cron every 2 hours, fetching up to **today** (UTC) so that records are picked up within 2 hours of their OAI-PMH datestamp, and processing only the records that are new or changed since the last run.

Where it runs:
- a. WSL2 with Java 17 on the serving laptop, with a cron line.
- b. A new `ingest` service in `docker-compose.yml` (Python + Java 17 JRE + a cron runner) next to Qdrant, started by `make up`.
- c. GitHub Actions: rejected for the same reason as in ADR 0008 (no data, no Qdrant in CI).

Which index:
- i. The evaluation collection `scitech_chunks`: rejected, it is frozen until D22.
- ii. A separate serving collection `scitech_chunks_live` and BM25 directory `data/index/bm25-live`, created as copies of the frozen ones, used by the demo backend.

## Decision
**Option 3 + b + ii**, as a controlled exception to the feature freeze:
- `incremental-run` gets `--until today`, a per-record filter (only ids whose `(id, datestamp)` differs from the last run go to `clean`, embed and load; when none is left, the run stops there: "nothing changed"), a lock so two runs never overlap, and an optional BM25 rebuild of the live index after a successful load (`--rebuild-bm25 <dir>`), written to a new directory and switched atomically.
- An `ingest` compose service runs it every 2 hours (`0 */2 * * *`, configurable with `INGEST_CRON`) against `scitech_chunks_live`. It carries Java 17, so the laptop's Java 8 no longer matters.
- The backend reloads the BM25 index when the live index changes, only when `BM25_RELOAD_SECONDS` > 0 (default 0: today's behaviour, so the frozen evaluation setup is unchanged).
- `incremental-run` refuses the collection named as frozen (`FROZEN_COLLECTION`, default `scitech_chunks`).
- Work happens on branches during Week 7 and is merged only after Gate W7 (D19), so no Week 7 run is affected.

Replaces ADR 0008 point 6 once accepted; points 1 to 5 of ADR 0008 stay.

## Consequences
- The demo and `v1.0` show a corpus that grows automatically; the report states that freshness is bounded by arXiv's daily announcement, not by the 2-hour interval ("near real time").
- Evaluation numbers keep referring to the frozen `scitech_chunks` and `data/index/bm25` (`evaluation/SNAPSHOT.md`); the live index is never evaluated.
- Cost per run: one or two OAI-PMH requests; on a day with new records about 300 papers embedded on CPU (about 2 min, ADR 0008 point 3) plus a BM25 rebuild (36.7 s on FAO's laptop, `pipelines/reports/index_profile.md`); otherwise a few seconds.
- The `ingest` image carries PySpark (about 480 MB, ADR 0005) and a CPU build of sentence-transformers: a large image; build time and size are recorded in the runbook.
- Two copies of the index on disk: about 610 MiB of Qdrant and 177 MiB of BM25 more (`index_profile.md` section 4). On FAO's laptop Docker's disk is on D:, while `data/` is on C: with about 2 GB free (FAO, #149), so a run deletes its raw fetch file after a successful load and keeps only its manifests.
- During a BM25 reload the backend briefly holds two copies of the index; a build peaks at about 1.2 GB (`docs/runbooks/data-pipeline.md`). The Docker Desktop memory limit and the measured peak go into the runbook on the first real run.
- The schedule runs only while the serving laptop is awake: Docker Desktop's cron does not run during Windows sleep.
- Known gaps kept from ADR 0008: deleted arXiv records stay until a full rebuild; replaced papers have no points for 0.3 to 2.4 s during a load.
- Revisit if the soak test (2 days, at least 12 runs logged in `data/logs/incremental.log`; a gap while the serving laptop sleeps is an uptime gap, not a failed run) shows failed runs, overlapping runs or backend errors during a BM25 switch; then fall back to option 2 (daily) or option 1.
