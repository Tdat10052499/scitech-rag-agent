# Plan overview

> Replanned on 2026-10-13: the project runs from Tuesday 2026-10-13 to Friday 2026-11-06 (22 working days, Monday to Saturday, Sundays as buffer; internal deadline, `v1.0`), followed by presentation preparation (D23-D24) and the product presentation on **Tuesday 2026-11-10 (D25)**. Reasons and scope cuts: [ADR 0010](../decisions/0010-compressed-schedule.md).

## Final deliverables (frozen Friday 2026-11-06, D22; presented Tuesday 2026-11-10, D25)

1. **Working web app**: user asks a science/technology question, gets a streamed answer with numbered citations to retrieved sources, an explicit "insufficient evidence" answer when retrieval is weak, up to 4 clickable follow-up questions, and rating buttons.
2. **Reproducible big-data pipeline**: open dataset to cleaned Parquet to chunks to embeddings to vector + keyword index; incremental ingestion of new items if kept at the Week 5 gate (otherwise its design is described in the report).
3. **Evaluation report** (`evaluation/reports/final.md`): retrieval metrics (recall@k, MRR) for dense, BM25 and hybrid, answer faithfulness, ablations of agent steps (MVP, +rewrite, +evidence check, full), latency and scaling measurements, follow-up suggestion ratings from a small user study (n >= 5), with sample sizes and limitations stated.
4. **Final report** (`docs/report/`) and **presentation** (slides + recorded demo video as fallback).
5. **Repository** that a stranger can clone and run from the README (`v1.0` tag).

## Roles

| Code | GitHub | Primary responsibility | Reviews |
|---|---|---|---|
| DAT | @Tdat10052499 | Agent loop, backend API, contracts, LLM serving, integration, project management | pipelines, frontend |
| FAO | @F4ol4n | Data pipeline end to end, big-data processing, index, incremental ingestion, retrieval quality | agent, evaluation |
| LDN | @Yui-Mika | Frontend, evaluation harness, golden set, user study | backend, evaluation |

Review rule: approvals are not enforced by GitHub; the author may merge once CI is green. PRs of [blocking] tasks, contract changes and evaluation runs are reviewed by another member before merging (see `CONTRIBUTING.md`). With gates every 2-3 days, review requested PRs within half a working day.

## Phases and gates

"Week N" is now phase N. The last day of each phase is its gate day. If a gate is not met, the next phase starts by finishing it (see cut list).

| Week | Dates | Days | Phase | Gate (must be true on `main` at the end of the gate day) |
|---|---|---|---|---|
| W1 | 10-13 to 10-15 | D01-D03 | Foundations | Sub-domain and sources verified (ADR 0003); contracts frozen and tested in CI; all 3 members ran the quick start; evaluation plan merged; ADR 0004 and ADR 0005 merged |
| W2 | 10-16 to 10-19 | D04-D06 | Batch data + skeletons | Clean Parquet dataset with data profile; LLM client + fake; `/chat` streams contract-valid fake events; UI renders them; golden set >= 30; eval harness computes recall@k/MRR on toy data; ADR 0006 |
| W3 | 10-20 to 10-22 | D07-D09 | Retrieval | Full corpus (or documented subset) chunked, embedded, loaded into Qdrant; dense, BM25 and hybrid retrievers; first retrieval metrics for 3 configurations; ADR 0007, ADR 0009 |
| W4 | 10-23 to 10-26 | D10-D12 | RAG MVP | End-to-end demo: question to cited streamed answer to follow-ups, with a real LLM; tag `v0.4-mvp`; demo video v1; user-study invitations sent |
| W5 | 10-27 to 10-28 | D13-D14 | Agent v2 (reduced) | Query rewriting, evidence check, step limits, per-request traces, `Agent.run_batch`; golden set >= 60; answer runner works; incremental ingestion kept or cut (decision recorded) |
| W6 | 10-29 to 10-30 | D15-D16 | Complete product | Rating buttons + `POST /feedback`, UI states, one-command stack (`make up`), runbooks, study protocol and participants confirmed; feature freeze; tag `v0.6-rc`; `SNAPSHOT.md`, `RUNS.md` |
| W7 | 10-31 to 11-03 | D17-D19 | Evaluation | All experiments run on the frozen system; user study done; `evaluation/reports/final.md` draft (merged by D20 10:00 at the latest) |
| W8 | 11-04 to 11-10 | D20-D25 | Delivery and presentation | D22: report, demo video, clean-clone reproduction check, tag `v1.0`. D23-D24: slides, rehearsal, dry run. D25: product presentation |

## Critical path

`W1 sources + contracts (D03)` -> `W2 clean data (D06)` -> `W3 index + retrieval (D09)` -> `W4 RAG MVP (D12)` -> `W5 agent v2 + traces (D14)` -> `W6 freeze (D16)` -> `W7 evaluation (D19)` -> `W8 report + v1.0 (D22)` -> `presentation (D25, 2026-11-10)`.
Anything off this path must never delay it. The tightest link is W3: chunker (D07) -> overnight embedding (D08) -> load (D09 morning).

## Fixed technical defaults

These are defaults so tasks can be concrete. They change only through an ADR in `docs/decisions/`.

- Python 3.10+, FastAPI backend, Server-Sent Events for streaming (contract: `docs/contracts/api.openapi.yaml`).
- Vector store: Qdrant via `docker-compose.yml`. Keyword search: BM25 library over chunk texts.
- Hybrid fusion: reciprocal rank fusion (RRF). No reranker (cut in ADR 0010).
- LLM: open-source model served with an OpenAI-compatible server (Ollama or vLLM) on an external GPU (Colab/Kaggle/university), hosted API as fallback (ADR 0001). Model chosen by measurement in ADR 0006.
- Embedding model: chosen in ADR 0007; must handle the query language users will type (check Vietnamese if users ask in Vietnamese).
- Frontend: Streamlit unless ADR 0004 decides otherwise.
- Big-data engine: PySpark in local mode preferred for the processing tier (brief), confirmed or rejected against DuckDB/Polars in ADR 0005 with measured numbers.
- Incremental ingestion: scheduled batch with a watermark; no Kafka (ADR 0010; decision recorded in the brief).

## Planned ADRs (owner, due)

| ADR | Topic | Owner | Due |
|---|---|---|---|
| 0003 | Sub-domain and data sources | FAO (with DAT) | D03 (2026-10-15) |
| 0004 | Frontend framework | LDN | D02 (2026-10-14) |
| 0005 | Big-data processing engine | FAO | D03 (2026-10-15) |
| 0006 | LLM model and serving | DAT | D06 (2026-10-19) |
| 0007 | Embedding model | FAO | D08 (2026-10-21) |
| 0008 | Incremental ingestion design | FAO | D13 (2026-10-27) |
| 0009 | Default retrieval configuration | DAT (with LDN numbers) | D09 (2026-10-22), accepted by D10 09:00 at the latest |
| 0010 | Compressed schedule and scope cuts | DAT | D01 (2026-10-13) |
| 0011 | Scheduled incremental ingestion every 2 hours (exception to the feature freeze) | DAT (with FAO) | D17 (2026-10-31) |

## Cut list

Applied on 2026-10-13 (ADR 0010):

1. Kafka: **cut** (keep scheduled incremental ingestion)
2. Reranker: **cut**
3. UI extras (data page, `GET /stats`, step/status display, debug view): **cut**
4. Query decomposition: **cut** (keep rewriting and evidence check)
5. User study size: **applied**, 5-6 participants
6. Incremental ingestion: **decision at the Week 5 gate (D14)**; if cut, keep the batch pipeline and describe the design in the report. Kept (ADR 0008); scheduled every 2 hours from D20 (ADR 0011), first thing to switch off if the soak test fails

Additional cuts (outside the original list, proposed in ADR 0010): follow-ups v2, response caching.

If the schedule slips further, the next items to drop, in this order: demo video v2 (W6-D5-DAT-1), multi-turn items beyond 45 golden items (W5-D1-LDN-1, state the smaller n), scaling at 3 sizes reduced to 2 (W6-D2-FAO-1). Never cut evaluation (W7) or the report (W8).

## Rhythm

- Each phase start (D01, D04, D07, D10, D13, D15, D17, D20): 10 minutes: read the phase file, confirm tasks, raise blockers.
- Daily: journal entry; push work in progress at least once a day (draft PR is fine).
- Gate days (D03, D06, D09, D12, D14, D16, D19, D22; presentation D25): gate checklist, merge, short demo to each other (10 minutes), close milestone, retro notes in `docs/journal/`.
- Sundays: buffer only (catch up, unattended long runs).

## Former open questions

Settled by the team on 2026-10-13 (the instructor does not answer design questions): see "Decisions on former open questions" in `docs/00-project-brief.md`. Still open: corpus size and first year included (ADR 0003, D03). If a later decision changes a default above, write an ADR and update this file.
