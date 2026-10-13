# Project brief

## Goal
Build an interactive website where users explore a science and technology topic by asking questions. An AI agent reasons over evidence retrieved from a large corpus, answers with citations, and proposes relevant follow-up questions.

## Context
Final project of a course on Big Data / AI. Duration: 2026-10-13 to 2026-11-06 (22 working days in 8 phases, see `docs/decisions/0010-compressed-schedule.md`). Team members work in parallel, each with their own AI coding tools.

## In scope
- Domain: science and technology, narrowed to the sub-domain **large language models and natural language processing (LLM/NLP)** (decided by the team on 2026-10-13, task W1-D2-DAT-1).
  - Core corpus: arXiv papers in `cs.CL`, including `cs.LG` and `cs.AI` papers cross-listed to `cs.CL` (titles and abstracts). Background: Wikipedia articles on NLP/LLM topics. The first year included is set in ADR 0003 from measured volume, so the full embedding run fits in one night (ADR 0010).
  - Reasons: (1) it maps onto an existing arXiv category, so the corpus is defined by category rather than a keyword filter, and the `source` values in `docs/contracts/chunk.schema.json` need no change; (2) the volume is large enough for the course's big-data requirement, with daily new papers for incremental ingestion; (3) golden-set authors and user-study participants (AI students) ask questions this corpus can answer.
  - Alternatives considered and rejected: Software (arXiv `cs.SE` is research about software engineering, not the practical backend/frontend/API knowledge users would ask about); IoT (no arXiv category, keyword filtering adds noise, smaller volume); Reinforcement learning + UAV (no category for UAV, the intersection is a niche whose size was not verified, harder golden set and user study).
  - Known risk: the LLM has strong prior knowledge of this topic and may answer from it instead of from retrieved evidence; the faithfulness evaluation must account for this (see `evaluation/PLAN.md`, threats to validity).
- Retrieval-augmented question answering with citations.
- Follow-up question suggestions (LLM-generated from context in the MVP).
- Batch ingestion from open datasets; streaming ingestion of newly published items only if time allows.
- LLM access through an OpenAI-compatible interface, with a hybrid setup (self-hosted open-source model on external GPU or locally, plus an API as fallback). See `docs/decisions/0001-hybrid-llm-backend.md`.
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

## Open questions (owner: maintainer)
- Team size and module ownership.
- Instructor requirements (mandatory tools such as Spark/Kafka, repo visibility, deliverable format).
- Available GPU resources (the development laptop has only an integrated GPU).
- Corpus size and first year included (sub-domain decided: LLM/NLP; numbers come from W1-D2-FAO-1 and ADR 0003).
