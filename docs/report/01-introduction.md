# 1. Introduction

<!-- Draft (W8-D1-DAT-1, written early on D16, 2026-10-30). Page budget 2 (00-outline.md).
Sources: docs/00-project-brief.md, evaluation/PLAN.md, ADR 0010. TODOs name the task that fills them. -->

## 1.1 Problem

Researchers and students who start on a topic in large language models (LLMs) and natural
language processing (NLP) face a fast-growing literature. The arXiv category `cs.CL` alone holds
121,860 records, cross-lists included, on the snapshot of 2026-10-10. About 460 new records arrive
per week (ADR 0003). Keyword search returns lists of papers, but the reader still has to open them
to answer a question. A general-purpose chatbot answers fluently, but it does not show where an
answer comes from, and it may state things that no paper says.

This project builds an interactive website where a user asks questions about LLM/NLP research and
an AI agent answers. The agent answers from evidence retrieved from the corpus, cites the papers it
used, says so when the evidence is insufficient, and suggests follow-up questions so the user can
keep exploring.

## 1.2 Goals and success criteria

The project brief (`docs/00-project-brief.md`) sets four success criteria:
1. A working web demo that answers questions with cited sources and shows follow-up suggestions.
2. A reproducible pipeline from open data to an indexed corpus.
3. A written evaluation with stated sample sizes, methods and limitations.
4. Code, documentation and project history that let an outsider rebuild and understand the system.

The approach is retrieval-augmented generation (RAG), not training on the corpus
(ADR 0002). The corpus is indexed once, and new papers can be added without retraining. Every
answer can point to its evidence. RAG reduces hallucination but does not remove it, so the agent
also checks whether the evidence is sufficient, and the evaluation measures how often answers are
supported by the passages they cite (chapter 4).

## 1.3 Scope

In scope:
- **Domain.** LLM/NLP research: every arXiv record whose categories contain `cs.CL`, all years,
  **titles and abstracts only** (ADR 0003). Wikipedia background articles were cut from the
  index on 2026-10-17.
- **Question answering** with citations, an evidence check and follow-up suggestions.
- **Big-data processing.** A two-tier pipeline. The processing tier reads the whole arXiv metadata
  snapshot (3,205,432 records, 5.61 GB) with PySpark. The index holds only `cs.CL` (chapter 2).
- **Incremental ingestion** of newly announced papers, as a batch job (ADR 0008). A scheduled run
  every 2 hours was added as a controlled exception after the feature freeze (ADR 0011).
- **LLM access** through an OpenAI-compatible interface, with an open-weights model served by the
  team (ADR 0001, ADR 0006).
- **Evaluation** of retrieval, answers and follow-up suggestions.

Out of scope:
- training or fine-tuning a model;
- full-text PDFs;
- user accounts and production-grade scaling;
- high-stakes advice;
- topics outside LLM/NLP.

Because the corpus has abstracts only, the system can answer what a paper does and reports in its
abstract, but not details found only in the full text. Section 3.8 and chapter 4 return to this
limit.

## 1.4 Research questions

The evaluation answers three questions, fixed before the runs (`evaluation/PLAN.md` §2):

- **RQ1 (retrieval).** Does hybrid retrieval (dense + BM25, reciprocal rank fusion) give higher
  recall@k and MRR than dense-only or BM25-only retrieval on the golden set?
- **RQ2 (agent steps).** Do query rewriting and the evidence check improve faithfulness compared
  with a plain retrieve-then-answer pipeline? Four conditions are compared: MVP, +rewrite,
  +evidence check, and full agent.
- **RQ3 (follow-up suggestions).** Do users rate the suggested follow-up questions as useful, and
  do they click them? The user study is small, so RQ3 is answered with descriptive statistics only.

Answer latency and the behaviour of the index as the corpus grows are measured too
(`docs/runbooks/performance.md`, `evaluation/reports/scaling.md`). They are reported as properties
of the system on the stated hardware, not as research questions.

## 1.5 How the project was run

- **Team.** Three members worked in parallel by module:
  - DAT owned the agent, the backend, the API contracts and LLM serving, and was maintainer;
  - FAO owned the data pipeline and indexing;
  - LDN owned the frontend and the evaluation.
- **Contracts first.** The modules talk only through written contracts:
  - the chunk schema;
  - the HTTP API (`docs/contracts/api.openapi.yaml`);
  - the LLM client interface.

  So each member could build and test against the others' contracts before the real
  implementations existed.
- **Decisions.** Every design decision is recorded as an ADR in `docs/decisions/`, with the options
  considered and, where possible, a decision rule fixed before the measurement that applies it.
- **Schedule.** The project ran from 2026-10-13 to the presentation on 2026-11-03.
  TODO(W8-D5-DAT-1): confirm the final dates. The original plan of 8 weeks was compressed into
  22 working days in 8 phases. Five features were cut early to protect the evaluation and the
  report: Kafka, the reranker, UI extras, query decomposition, and a larger user study
  (ADR 0010).
- **Quality rules.** Every change went through a pull request with CI (lint and tests). Evaluation
  runs and contract changes needed a review by a second member.
- **AI coding tools.** Team members used AI coding assistants. The repository rules for them are in
  `AGENTS.md`. Authors stayed responsible for every change they merged.

## 1.6 Structure of the report

- Chapter 2 describes the data and the pipeline.
- Chapter 3 describes the system: architecture, retrieval, the agent and the design decisions.
- Chapter 4 reports the evaluation for RQ1–RQ3, with latency and an error analysis.
- Chapter 5 presents the user interface.
- Chapter 6 summarises the results, the limitations and future work.
