# Plan overview

## Final deliverables (due Friday 2026-11-27, D40)

1. **Working web app**: user asks a science/technology question, gets a streamed answer with numbered citations to retrieved sources, an explicit "insufficient evidence" answer when retrieval is weak, and up to 4 clickable follow-up questions.
2. **Reproducible big-data pipeline**: open dataset to cleaned Parquet to chunks to embeddings to vector + keyword index, plus incremental ingestion of new items.
3. **Evaluation report** (`evaluation/reports/final.md`): retrieval metrics (recall@k, MRR) for several configurations, answer faithfulness, ablations of agent steps, latency and scaling measurements, follow-up suggestion ratings from a small user study, with sample sizes and limitations stated.
4. **Final report** (`docs/report/`) and **presentation** (slides + recorded demo video as fallback).
5. **Repository** that a stranger can clone and run from the README (`v1.0` tag).

## Roles

| Code | GitHub | Primary responsibility | Reviews |
|---|---|---|---|
| DAT | @Tdat10052499 | Agent loop, backend API, contracts, LLM serving, integration, project management | pipelines, frontend |
| FAO | @F4ol4n | Data pipeline end to end, big-data processing, index, incremental ingestion, retrieval quality | agent, evaluation |
| LDN | @Yui-Mika | Frontend, evaluation harness, golden set, user study | backend, evaluation |

Review rule: every PR gets one approval from a member other than its author (CODEOWNERS requests reviewers).

## Phases and weekly gates

Every Friday is a gate. If a gate is not met, the next week starts by finishing it (see cut list).

| Week | Dates | Phase | Gate (must be true on `main` by Friday) |
|---|---|---|---|
| W1 | 10-05 to 10-09 | Foundations | Sub-domain and sources verified (ADR 0003); contracts frozen and tested in CI; all 3 members ran the quick start; evaluation plan merged; frontend framework chosen (ADR 0004) |
| W2 | 10-12 to 10-16 | Batch data + skeletons | Clean Parquet dataset with data profile; LLM client + fake; `/chat` streams contract-valid fake events; UI renders them; golden set >= 30 items; eval harness computes recall@k/MRR on toy data |
| W3 | 10-19 to 10-23 | Retrieval | Full corpus chunked, embedded, loaded into Qdrant; dense, BM25 and hybrid retrievers; first retrieval metrics for 3 configurations |
| W4 | 10-26 to 10-30 | RAG MVP | End-to-end demo: question to cited streamed answer to follow-ups, with a real LLM; tag `v0.4-mvp`; demo video v1 |
| W5 | 11-02 to 11-06 | Agent v2 | Query rewriting, decomposition, evidence check, step limits, per-request traces; incremental ingestion runs; agent v2 vs MVP pilot comparison |
| W6 | 11-09 to 11-13 | Complete product | Follow-ups v2, full UI incl. data page and rating buttons, one-command stack (`make up`), runbooks; feature freeze; tag `v0.6-rc` |
| W7 | 11-16 to 11-20 | Evaluation | All experiments run on the frozen system; user study done; `evaluation/reports/final.md` draft |
| W8 | 11-23 to 11-27 | Delivery | Report, slides, demo video, clean-clone reproduction check; tag `v1.0`; submission |

## Critical path

`W1 sources + contracts` -> `W2 clean data` -> `W3 index + retrieval` -> `W4 RAG MVP` -> `W5 agent v2` -> `W6 freeze` -> `W7 evaluation` -> `W8 report`.
Anything off this path (reranker, Kafka, UI extras) must never delay it.

## Fixed technical defaults

These are defaults so tasks can be concrete. They change only through an ADR in `docs/decisions/`.

- Python 3.10+, FastAPI backend, Server-Sent Events for streaming (contract: `docs/contracts/api.openapi.yaml`).
- Vector store: Qdrant via `docker-compose.yml`. Keyword search: BM25 library over chunk texts.
- Hybrid fusion: reciprocal rank fusion (RRF).
- LLM: open-source model served with an OpenAI-compatible server (Ollama or vLLM) on an external GPU (Colab/Kaggle/university), hosted API as fallback (ADR 0001). Model chosen by measurement in ADR 0006.
- Embedding model: chosen in ADR 0007; must handle the query language users will type (check Vietnamese if users ask in Vietnamese).
- Frontend: Streamlit unless ADR 0004 decides otherwise.
- Big-data engine: PySpark or DuckDB/Polars, chosen in ADR 0005 with measured numbers.
- Incremental ingestion: scheduled batch with a watermark; Kafka only if the instructor requires it (ADR 0008).

## Planned ADRs (owner, due)

| ADR | Topic | Owner | Due |
|---|---|---|---|
| 0003 | Sub-domain and data sources | FAO (with DAT) | W1-D3 |
| 0004 | Frontend framework | LDN | W1-D2 |
| 0005 | Big-data processing engine | FAO | W1-D5 |
| 0006 | LLM model and serving | DAT | W2-D4 |
| 0007 | Embedding model | FAO | W3-D2 |
| 0008 | Incremental ingestion design | FAO | W3-D4 |
| 0009 | Default retrieval configuration | DAT (with LDN numbers) | W3-D5 |

## Cut list

If the schedule slips, drop items in this order (top first). Never cut evaluation (W7) or the report (W8).

1. Kafka (keep scheduled incremental ingestion)
2. Reranker
3. UI extras: data page, step/status display
4. Query decomposition (keep rewriting and evidence check)
5. User study size (minimum 5 participants)
6. Incremental ingestion (keep batch pipeline; describe design in report)

## Weekly rhythm

- Monday 15 minutes: read the week file, confirm tasks, raise blockers.
- Daily: journal entry; push work in progress at least once a day (draft PR is fine).
- Friday: gate checklist, merge, demo to each other (10 minutes), close milestone, retro notes in `docs/journal/`.

## Open questions to settle in W1 (owner DAT)

Instructor requirements (mandatory tools such as Spark/Kafka, fully local LLM or not, report format, presentation length, licence and repo visibility), GPU access, exact sub-domain. Answers go into `docs/00-project-brief.md`; if they change a default above, write an ADR and update this file.
