# Week 6 (phase 6 of 8): Complete product and feature freeze (2026-10-29 to 2026-10-30)

> Replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md). This phase has 2 working days (D15, D16).
> Task IDs are unchanged. Lines starting with **Replan:** say what changed.

Goal: the product is complete for the reduced scope, runs with one command, and is frozen for evaluation.

Gate (D16, Fri 2026-10-30, end of day): UI complete for the reduced scope (rating buttons, empty/loading/error states); `POST /feedback` writes to `data/logs/feedback.jsonl`; `make up` starts Qdrant + backend + frontend; runbooks merged; user study protocol ready and 5-6 participants confirmed for D18-D19; feature freeze declared; tag `v0.6-rc`; `evaluation/SNAPSHOT.md` complete; `evaluation/RUNS.md` ready.

Feature freeze is declared on D16 after the bug bash. From then on, only bug fixes are merged until the end of the project.

## D15
Thursday 2026-10-29

### DAT (@Tdat10052499)

#### W6-D3-DAT-1 [blocking] One-command stack
- Module: `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `Makefile`, `README.md`
- Do: services for Qdrant, backend and frontend with healthchecks and `.env`; `make up` starts all; README quick start updated; LLM remains external (URL in `.env`).
- **Replan:** dependency changed from UI polish (W6-D1-LDN-1, same day) to the working frontend of W4-D5-LDN-1; polish changes do not affect the Dockerfile.
- Done when: on a clean clone, `make up` plus a loaded index gives a working app (FAO and LDN each confirm on their machines, D16 morning at the latest).
- Depends on: W4-D5-LDN-1

#### W6-D3-DAT-2 Approve the feedback endpoint
- Module: `docs/contracts/api.openapi.yaml`, `backend/`
- **Replan:** reduced: only `POST /feedback`; `GET /stats` is cut with the data page (cut-list item 3).
- Do: review LDN's contract issue; update the contract; implement `POST /feedback` (appends to `data/logs/feedback.jsonl`) with tests.
- Done when: merged; LDN confirmed the UI works against the real endpoint and ratings appear in the log.
- Depends on: W6-D2-LDN-1

### FAO (@F4ol4n)

#### W6-D2-FAO-1 Scaling measurements
- Module: `pipelines/reports/scaling.md`
- Do: build indexes at 3 corpus sizes (for example 10%, 50%, 100%) and record build time, disk, RAM and query latency; this is the "big data" evidence for the report.
- **Replan:** reuse the vectors already computed in Week 3 (load subsets into separate collections) so no re-embedding is needed; report embedding throughput from W3 separately and say the two were measured at different times.
- Done when: table and method in the report; raw numbers saved as CSV/JSON in `pipelines/reports/`.
- Depends on: W3-D5-FAO-1

### LDN (@Yui-Mika)

#### W6-D1-LDN-1 UI polish
- Module: `frontend/`
- Do: consistent layout and typography, empty state with example questions, loading and error states, readable at phone width, keyboard submit.
- Done when: checklist of these states in the PR with screenshots.
- Depends on: W4-D3-LDN-1

#### W6-D2-LDN-1 Rating buttons
- Module: `frontend/`
- **Replan:** reduced: the "About the data" page is cut (cut-list item 3); rating buttons stay because the user study needs them.
- Do (open the contract issue in the morning): thumbs up/down on each answer and on each follow-up click, posted to `POST /feedback`. Open a contract-change issue for `POST /feedback` (DAT implements it in W6-D3-DAT-2). Until the endpoint exists, use a stub with the agreed JSON.
- Done when: UI works against the stub; contract issue opened. Final check (ratings appear in `data/logs/feedback.jsonl`) is part of W6-D3-DAT-2.
- Depends on: W6-D1-LDN-1

#### W6-D3-LDN-1 User study protocol
- Module: `evaluation/user_study/PROTOCOL.md`
- Do: 5-6 participants (classmates, invited on D12); consent text (what is logged, anonymity); tasks (explore a topic with at least 5 questions, use follow-ups); post-task questionnaire (usefulness of answers and follow-ups on a 1-5 scale, open comments); schedule sessions for D18 (Mon 2026-11-02) and D19 (Tue 2026-11-03).
- **Replan:** participant range reduced to 5-6 (cut-list item 5); analysis is descriptive only.
- Done when: DAT reviewed; participants confirmed.
- Depends on: W6-D2-LDN-1

## D16
Friday 2026-10-30 · Feature freeze and gate day

### DAT (@Tdat10052499)

#### W6-D4-DAT-1 Bug bash and freeze
- Do (morning): 1-hour bug bash with a shared checklist (normal questions, follow-ups, refusal, long conversation, backend down, LLM down, Vietnamese input if supported); triage; declare feature freeze in the tracking issue by 15:00.
- Done when: all P0 bugs assigned; freeze announced.
- Depends on: W6-D3-DAT-1

#### W6-D5-DAT-1 Release candidate
- Do (end of day): gate checklist; tag `v0.6-rc`; freeze model, prompts and config values in `evaluation/SNAPSHOT.md` (with FAO's index snapshot); record demo video v2 only if time remains (v1 from D12 is the fallback).
- Done when: tag pushed; snapshot complete.
- Depends on: W6-D4-FAO-1

### FAO (@F4ol4n)

#### W6-D3-FAO-1 Data pipeline runbook final
- Module: `docs/runbooks/data-pipeline.md`
- Do: finalise with incremental ingestion (or the cut decision), scaling notes and troubleshooting.
- Done when: LDN followed it for a `--limit` rebuild without help.
- Depends on: W4-D5-FAO-1, W5-D4-FAO-1

#### W6-D4-FAO-1 Fix P0 data/retrieval bugs; freeze index snapshot
- Do: fix P0s from the bug bash; then produce the frozen index snapshot for evaluation (record snapshot id, document and chunk counts, embedding model) in `evaluation/SNAPSHOT.md`.
- Done when: snapshot recorded; no further index changes until D22 unless approved.
- Depends on: W6-D4-DAT-1

### LDN (@Yui-Mika)

#### W6-D4-LDN-1 Fix P0 UI bugs; dry-run the user study
- Do: fix P0s; run the full study protocol with one teammate as a pilot participant; adjust timing and questions.
- Done when: protocol updated after the pilot.
- Depends on: W6-D3-LDN-1

#### W6-D5-LDN-1 Evaluation run plan for Week 7
- Module: `evaluation/RUNS.md`
- Do: list every experiment to run in W7 with config files ready: retrieval configs (dense, BM25, hybrid), agent ablations (MVP, +rewrite, +evidence check, full), faithfulness runs, latency runs (DAT), scaling (FAO, done), user study.
- **Replan:** dependency changed from the RC tag to the freeze, so configs are ready before the evening tag and runs can start on D17 morning.
- Done when: DAT and FAO confirmed their parts.
- Depends on: W6-D4-DAT-1

## Cut or merged in the replan

| Task | Decision | Where it went / reason |
|---|---|---|
| W6-D1-DAT-1 Follow-up suggestions v2 | Cut (additional, outside the original cut list) | No time in a 2-day phase; v1 (W4-D3-DAT-1) is the evaluated version. Recorded in ADR 0010 for team approval. |
| W6-D1-FAO-1 Corpus statistics for the UI | Cut | Only fed the data page and `GET /stats` (cut-list item 3). Corpus numbers for the report come from `data_profile.md` and `scaling.md`. |
| W6-D2-DAT-1 Performance and caching | Moved and reduced | Caching cut (it would also distort repeated latency measurements); the p50/p95 latency measurement moves to D18 on the frozen system. |
| W6-D5-FAO-1 Report section draft: data | Merged | Into W7-D4-FAO-1 (D19): one pass with final numbers. |
