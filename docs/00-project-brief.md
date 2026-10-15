# Project brief

## Goal
Build an interactive website where users explore a science and technology topic by asking questions. An AI agent reasons over evidence retrieved from a large corpus, answers with citations, and proposes relevant follow-up questions.

## Context
Final project of a course on Big Data / AI. Duration: 2026-10-13 to 2026-11-06 (22 working days in 8 phases, see `docs/decisions/0010-compressed-schedule.md`), then presentation preparation until the product presentation on **Tuesday 2026-11-10**. Team members work in parallel, each with their own AI coding tools.

The instructor does not answer design questions during the project: the team decides, records each decision here or in an ADR, and presents the final product on 2026-11-10.

## In scope
- Domain: science and technology, narrowed to the sub-domain **large language models and natural language processing (LLM/NLP)** (decided by the team on 2026-10-13, task W1-D2-DAT-1).
  - Core corpus: arXiv papers in `cs.CL`, including `cs.LG` and `cs.AI` papers cross-listed to `cs.CL` (titles and abstracts). Background: Wikipedia articles on NLP/LLM topics. Corpus fixed in ADR 0003 (accepted 2026-10-14): every arXiv record whose `categories` contains `cs.CL` (primary or cross-list), all years, no year filter: 121,860 records on the 2026-10-10 Kaggle snapshot. Processing has two tiers: the processing tier reads the whole snapshot (3,205,432 records, 5.61 GB), the index holds only `cs.CL`. The full embedding run is estimated at 14-41 min on a T4, inside one night (ADR 0003, ADR 0010).
  - Reasons: (1) it maps onto an existing arXiv category, so the corpus is defined by category rather than a keyword filter, and the `source` values in `docs/contracts/chunk.schema.json` need no change; (2) the volume is large enough for the course's big-data requirement, with daily new papers for incremental ingestion (measured in ADR 0003: 121,860 `cs.CL` records, 23,762 new in 2025, about 460 per week; the big-data argument is the two-tier processing of the 5.61 GB snapshot); (3) golden-set authors and user-study participants (AI students) ask questions this corpus can answer.
  - Alternatives considered and rejected: Software (arXiv `cs.SE` is research about software engineering, not the practical backend/frontend/API knowledge users would ask about); IoT (no arXiv category, keyword filtering adds noise, volume expected to be smaller but not measured); Reinforcement learning + UAV (no category for UAV, the intersection is a niche whose size was not verified, harder golden set and user study).
  - Known risk: the LLM has strong prior knowledge of this topic and may answer from it instead of from retrieved evidence; the faithfulness evaluation must account for this (see `evaluation/PLAN.md`, threats to validity).
- Retrieval-augmented question answering with citations.
- Follow-up question suggestions (LLM-generated from context in the MVP).
- Batch ingestion from open datasets; incremental ingestion of newly published items as a scheduled batch (no streaming platform), decided at the Week 5 gate.
- LLM access through an OpenAI-compatible interface, with a hybrid setup (self-hosted open-source model on external GPU, plus an API as fallback). See `docs/decisions/0001-hybrid-llm-backend.md`.
- Experimental evaluation of retrieval, answers and suggestions.

## Out of scope (unless re-decided via an issue)
- Training or fine-tuning a model.
- User accounts, payments, production-grade scaling.
- Medical, legal or other high-stakes advice.
- Science and technology topics outside LLM/NLP (for example software engineering, IoT, UAV, and reinforcement learning as a field; RL papers are included only when cross-listed to `cs.CL`, e.g. RLHF), and full-text PDFs.

## Success criteria
1. A working web demo that answers questions with cited sources and shows follow-up suggestions.
2. A reproducible pipeline from open data to an indexed corpus.
3. A written evaluation with stated sample sizes, methods and limitations.
4. Code, docs and project history that let an outsider rebuild and understand the system.

## Decisions on former open questions (2026-10-13, task W1-D1-DAT-2)
The instructor sets no requirements beyond presenting the final product, so these were decided by the team.

| Question | Decision | Reason / where it is settled |
|---|---|---|
| Team size and module ownership | 3 members: DAT, FAO, LDN | `docs/plan/README.md` (Team) |
| Big-data processing tool (Spark?) | **PySpark** in local mode (free, no cluster) for the processing tier; DuckDB for checks and as fallback | A course on Big Data is evaluated on big-data tooling; the comparison itself is a result. ADR 0005 (accepted 2026-10-16): same job on a synthetic file about the size of the snapshot, PySpark 35 s and 1.1 GB peak memory, DuckDB 5.3 s; Polars ruled out (estimated 30-35 GB in eager mode). Spark needs Java 17+, so it runs in WSL2 or Colab, not natively on Windows. Revisit if PySpark on the real snapshot takes more than 15 min or 8 GB |
| Frontend framework | **React + Vite + TypeScript**, Node 22 | Clickable citations `[n]`, a sources panel and the insufficient-evidence state are ordinary component code; streaming `POST /chat` is read with `fetch`. ADR 0004 (accepted 2026-10-14) |
| Streaming platform (Kafka?) | **No Kafka.** Incremental ingestion is a scheduled batch with a watermark | arXiv announces new papers in daily batches, so Kafka adds infrastructure without benefit. ADR 0010 (cut-list item 1), ADR 0008 |
| Must the LLM run fully locally? | **No.** Open-weights model on a free external GPU (Kaggle/Colab) behind an OpenAI-compatible server, plus a hosted API as fallback for the demo | The development laptop has only an integrated GPU (ADR 0001). Model and fallback chosen by measurement in ADR 0006 (DAT, D06); the report states that "self-hosted" means self-controlled weights |
| Available GPU resources | Free Kaggle/Colab sessions; time-limited and can end | ADR 0001; runbook `docs/runbooks/llm-serving.md` (W1-D3-DAT-1) |
| Repository visibility and licence | Public repository; code under the MIT licence (`LICENSE`, the three members); data keeps its source licence (arXiv metadata CC0 1.0, Wikipedia CC BY-SA 4.0 with attribution) | Public also lets the "Protect main" ruleset apply on a free plan. `docs/03-data-sources.md` |
| Report format | Markdown chapters in `docs/report/`, exported to PDF | W7-D5-DAT-1 (outline), W8-D4-LDN-1 (export) |
| Presentation | Tuesday 2026-11-10: about 15 minutes plus a 3-5 minute recorded demo video as fallback for the live demo | Team default; adjust if the course announces a different length |
| Deadlines | `v1.0` and the final report on Friday 2026-11-06 (internal deadline, D22); slides and rehearsal 2026-11-07 to 2026-11-09 (D23-D24); presentation 2026-11-10 (D25) | `docs/plan/calendar.md`, ADR 0010 |

Corpus size and first year: settled in ADR 0003 (all years, 121,860 records). Checked at gate W1 (2026-10-16, W1-D5-DAT-1): no question in this table is still open. Decisions still to come are planned ADRs (`docs/plan/00-overview.md`): 0006 LLM model and serving (D06), 0007 embedding model (D08), 0009 default retrieval configuration (D09), 0008 incremental ingestion (D13).
