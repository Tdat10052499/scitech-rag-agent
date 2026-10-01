# 0002. Retrieval-augmented generation instead of training on the corpus

- Status: accepted
- Date: 2026-10-01
- Deciders: project maintainer

## Context
The system must answer from a large corpus within 8 weeks, with traceable sources.

## Decision
Index the corpus and retrieve evidence per question (RAG) rather than training or fine-tuning a model on it.

## Consequences
- Citations and data updates are possible without retraining.
- Answer quality depends on retrieval quality and corpus quality; both must be evaluated (`evaluation/`).
- Hallucination is reduced, not removed: the agent must check evidence sufficiency and may answer "insufficient evidence".
