# Week 6: Complete product and feature freeze (2026-11-09 to 2026-11-13)

Goal: the product is complete, runs with one command, and is frozen for evaluation.

Gate (Friday): follow-ups v2 merged; UI complete (data page, rating buttons, error/empty states); `make up` starts Qdrant + backend + frontend; runbooks merged; user study protocol ready and sessions scheduled; feature freeze declared; tag `v0.6-rc`.

After Thursday (feature freeze), only bug fixes are merged until W8.

## W6-D1
Monday 2026-11-09 · D26

### DAT (@Tdat10052499)

#### W6-D1-DAT-1 Follow-up suggestions v2
- Module: `agent/src/scitech_agent/followups.py`, `agent/prompts/followups.md`
- Do: generate candidates from retrieved-but-unused chunks and the conversation; keep only suggestions whose own retrieval top score passes `RETRIEVAL_MIN_SCORE` (so suggested questions are answerable); avoid near-duplicates of asked questions; keep v1 behind `FOLLOWUPS_VERSION=1|2`.
- Done when: tests; 10 manual examples compared v1 vs v2 in the PR.
- Depends on: W4-D3-DAT-1, W5-D4-DAT-1

### FAO (@F4ol4n)

#### W6-D1-FAO-1 Corpus statistics for the UI
- Module: `pipelines/src/scitech_pipelines/stats.py`
- Do: produce `data/processed/corpus_stats.json` (documents, chunks, sources, date range, per-year and per-category counts, last incremental update time); open a contract-change issue proposing `GET /stats` that returns this JSON (DAT implements it in W6-D3-DAT-2).
- Done when: stats command merged; contract issue opened with a JSON example.
- Depends on: W5-D4-FAO-1

### LDN (@Yui-Mika)

#### W6-D1-LDN-1 UI polish
- Module: `frontend/`
- Do: consistent layout and typography, empty state with example questions, loading and error states, readable at phone width, keyboard submit.
- Done when: checklist of these states in the PR with screenshots.
- Depends on: W4-D3-LDN-1

## W6-D2
Tuesday 2026-11-10 · D27

### DAT (@Tdat10052499)

#### W6-D2-DAT-1 Performance and caching
- Module: `agent/`, `backend/`
- Do: cache query embeddings and identical-question responses (in-memory with TTL); measure p50/p95 latency for 30 golden questions (time to first token and total); set timeouts so the UI never waits silently.
- Done when: numbers before/after in `docs/runbooks/performance.md`.
- Depends on: W5-D4-DAT-1

### FAO (@F4ol4n)

#### W6-D2-FAO-1 Scaling measurements
- Module: `pipelines/reports/scaling.md`
- Do: build indexes at 3 corpus sizes (for example 10%, 50%, 100%) and record build time, disk, RAM and query latency; this is the "big data" evidence for the report.
- Done when: table and method in the report; raw numbers saved as CSV/JSON in `pipelines/reports/`.
- Depends on: W3-D5-FAO-1

### LDN (@Yui-Mika)

#### W6-D2-LDN-1 Data page and rating buttons
- Module: `frontend/`
- Do: "About the data" page reading `/stats`; thumbs up/down on each answer and on each follow-up click, posted to `POST /feedback`. Open a contract-change issue for `POST /feedback` (DAT implements it in W6-D3-DAT-2). Until the endpoints exist, use a stub with the agreed JSON.
- Done when: UI works against the stub; contract issue opened. Final check (ratings appear in `data/logs/feedback.jsonl`) is part of W6-D3-DAT-2.
- Depends on: W6-D1-FAO-1, W6-D1-LDN-1

## W6-D3
Wednesday 2026-11-11 · D28

### DAT (@Tdat10052499)

#### W6-D3-DAT-1 [blocking] One-command stack
- Module: `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `Makefile`, `README.md`
- Do: services for Qdrant, backend and frontend with healthchecks and `.env`; `make up` starts all; README quick start updated; LLM remains external (URL in `.env`).
- Done when: on a clean clone, `make up` plus a loaded index gives a working app (FAO and LDN each confirm on their machines).
- Depends on: W6-D1-LDN-1

#### W6-D3-DAT-2 Approve feedback and stats endpoints
- Module: `docs/contracts/api.openapi.yaml`, `backend/`
- Do: review the contract issues from FAO and LDN; update the contract; implement `GET /stats` (serves `corpus_stats.json`) and `POST /feedback` (appends to `data/logs/feedback.jsonl`) with tests.
- Done when: merged; LDN confirmed the UI works against the real endpoints and ratings appear in the log.
- Depends on: W6-D1-FAO-1, W6-D2-LDN-1

### FAO (@F4ol4n)

#### W6-D3-FAO-1 Data pipeline runbook final
- Module: `docs/runbooks/data-pipeline.md`
- Do: finalise with incremental ingestion, scaling notes and troubleshooting.
- Done when: LDN followed it for a `--limit` rebuild without help.
- Depends on: W4-D5-FAO-1, W5-D4-FAO-1

### LDN (@Yui-Mika)

#### W6-D3-LDN-1 User study protocol
- Module: `evaluation/user_study/PROTOCOL.md`
- Do: 5-10 participants (classmates); consent text (what is logged, anonymity); tasks (explore a topic with at least 5 questions, use follow-ups); post-task questionnaire (usefulness of answers and follow-ups on a 1-5 scale, open comments); schedule sessions for W7-D3 and W7-D4.
- Done when: DAT reviewed; participants confirmed.
- Depends on: W6-D2-LDN-1

## W6-D4
Thursday 2026-11-12 · D29 · Feature freeze

### DAT (@Tdat10052499)

#### W6-D4-DAT-1 Bug bash and freeze
- Do: 1-hour bug bash with a shared checklist (normal questions, follow-ups, refusal, long conversation, backend down, LLM down, Vietnamese input if supported); triage; declare feature freeze in the tracking issue at the end of the day.
- Done when: all P0 bugs assigned; freeze announced.
- Depends on: W6-D3-DAT-1

### FAO (@F4ol4n)

#### W6-D4-FAO-1 Fix P0 data/retrieval bugs; freeze index snapshot
- Do: fix P0s; then produce the frozen index snapshot for evaluation (record snapshot id, document and chunk counts, embedding model) in `evaluation/SNAPSHOT.md`.
- Done when: snapshot recorded; no further index changes until W8 unless approved.
- Depends on: W6-D4-DAT-1

### LDN (@Yui-Mika)

#### W6-D4-LDN-1 Fix P0 UI bugs; dry-run the user study
- Do: fix P0s; run the full study protocol with one teammate as a pilot participant; adjust timing and questions.
- Done when: protocol updated after the pilot.
- Depends on: W6-D3-LDN-1

## W6-D5
Friday 2026-11-13 · D30 · Gate day

### DAT (@Tdat10052499)

#### W6-D5-DAT-1 Release candidate
- Do: gate checklist; tag `v0.6-rc`; freeze model, prompts and config values in `evaluation/SNAPSHOT.md` (with FAO's index snapshot); record demo video v2.
- Done when: tag pushed; snapshot complete.
- Depends on: W6-D4-FAO-1

### FAO (@F4ol4n)

#### W6-D5-FAO-1 Report section draft: data and big-data processing
- Module: `docs/report/02-data.md`
- Do: draft the data chapter: sources and licences, volume, pipeline design, engine choice (ADR 0005), incremental ingestion, scaling results.
- Done when: draft PR open (numbers may be updated in W7).
- Depends on: W6-D2-FAO-1

### LDN (@Yui-Mika)

#### W6-D5-LDN-1 Evaluation run plan for Week 7
- Module: `evaluation/RUNS.md`
- Do: list every experiment to run in W7 with config files ready: retrieval configs, agent ablations, faithfulness runs, latency runs (DAT), scaling (FAO, done), user study.
- Done when: DAT and FAO confirmed their parts.
- Depends on: W6-D5-DAT-1
