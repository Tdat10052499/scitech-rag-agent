# Project brief

## Goal
Build an interactive website where users explore a science and technology topic by asking questions. An AI agent reasons over evidence retrieved from a large corpus, answers with citations, and proposes relevant follow-up questions.

## Context
Final project of a course on Big Data / AI. Duration: 8 weeks. Team members work in parallel, each with their own AI coding tools.

## In scope
- Domain: science and technology. The exact sub-domain is to be narrowed in Week 1 (see `docs/tasks/W01-01-scope-and-data-survey.md`).
- Retrieval-augmented question answering with citations.
- Follow-up question suggestions (LLM-generated from context in the MVP).
- Batch ingestion from open datasets; streaming ingestion of newly published items only if time allows.
- LLM access through an OpenAI-compatible interface, with a hybrid setup (self-hosted open-source model on external GPU or locally, plus an API as fallback). See `docs/decisions/0001-hybrid-llm-backend.md`.
- Experimental evaluation of retrieval, answers and suggestions.

## Out of scope (unless re-decided via an issue)
- Training or fine-tuning a model.
- User accounts, payments, production-grade scaling.
- Medical, legal or other high-stakes advice.

## Success criteria
1. A working web demo that answers questions with cited sources and shows follow-up suggestions.
2. A reproducible pipeline from open data to an indexed corpus.
3. A written evaluation with stated sample sizes, methods and limitations.
4. Code, docs and project history that let an outsider rebuild and understand the system.

## Open questions (owner: maintainer)
- Team size and module ownership.
- Instructor requirements (mandatory tools such as Spark/Kafka, repo visibility, deliverable format).
- Available GPU resources (the development laptop has only an integrated GPU).
- Final sub-domain and corpus size.
