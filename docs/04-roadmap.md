# Roadmap (8 phases, 22 working days)

Detailed day-by-day tasks per member: [docs/plan/](plan/README.md). Replanned on 2026-10-13 ([ADR 0010](decisions/0010-compressed-schedule.md)): work starts Tuesday 2026-10-13; `v1.0` and final report Friday 2026-11-06; product presentation Tuesday 2026-11-10. Working days are Monday to Saturday; Sundays are buffer days.

Milestones `Week 1` to `Week 8` (one per phase) are created by the "Bootstrap project" GitHub Action with the gate dates below as due dates.

| Week (phase) | Dates | Goal | Deliverable |
|---|---|---|---|
| 1 | 10-13 to 10-15 | Narrow scope, verify data sources, freeze contracts, dev environment | Updated brief, `03-data-sources.md`, frozen contracts, working `make` commands |
| 2 | 10-16 to 10-19 | Batch pipeline: download, clean, store | Clean dataset and descriptive statistics |
| 3 | 10-20 to 10-22 | Chunking, embeddings, vector store, hybrid search | Retrieval working without an LLM |
| 4 | 10-23 to 10-26 | LLM backend, RAG with citations | Chat MVP (`v0.4-mvp`) |
| 5 | 10-27 to 10-28 | Agent: query rewriting, evidence check, traces; incremental ingestion decision | Multi-step agent (reduced) |
| 6 | 10-29 to 10-30 | Follow-up suggestions (v1), complete UI, one-command stack, freeze | Feature-complete demo (`v0.6-rc`) |
| 7 | 10-31 to 11-03 | Experimental evaluation | Evaluation report with sample sizes and limitations |
| 8 | 11-04 to 11-10 | Polish, final report, demo; presentation preparation; presentation on 11-10 | Final deliverables (`v1.0`), presentation |

Rule: every phase ends with something runnable on `main`. Reduce scope before sacrificing phases 7-8 (evaluation and report).
