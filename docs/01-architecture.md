# Architecture

## Approach
Retrieval-Augmented Generation (RAG) instead of training on the corpus: the corpus is indexed, the agent retrieves evidence per question, and the LLM reasons over that evidence. This allows citations and updating data without retraining. It reduces but does not eliminate hallucination, so the agent must check evidence sufficiency.

## Layers
| Layer | Responsibility | Module |
|---|---|---|
| Interface | Chat, citations, follow-up suggestions, streaming | `frontend/` |
| API | Sessions, validation, event streaming | `backend/` |
| Agent | Query rewrite/decomposition, tool use, evidence check, answer, follow-ups | `agent/` |
| Retrieval | Vector and keyword search, optional reranking | `agent/` (+ vector store) |
| Data | Ingestion, cleaning, chunking, embeddings, loading | `pipelines/` |
| Evaluation | Golden set, metrics, reports | `evaluation/` |

## Request flow
1. Frontend POSTs `/chat` (`session_id`, `message`).
2. Backend calls the agent and streams SSE events: `sources`, `token`, `followups`, `done` (or `error`).
3. Agent rewrites the query, retrieves top-k chunks, checks evidence against `RETRIEVAL_MIN_SCORE`, then generates a cited answer, then follow-up questions.

## Interfaces between modules
- Data to retrieval: `docs/contracts/chunk.schema.json`
- Frontend to backend: `docs/contracts/api.openapi.yaml`
- Agent to LLM: `docs/contracts/llm-client.md`

## Technology (proposed, to be confirmed by decisions in `docs/decisions/`)
Python + FastAPI; Qdrant (or pgvector) as vector store; BM25/keyword search for hybrid retrieval; Docker Compose for local infrastructure; GitHub Actions for CI. Big-data tooling (PySpark/DuckDB/Polars, Kafka, Airflow) only where data volume or update frequency justifies it.
