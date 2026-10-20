"""Dense retriever (W3-D2-DAT-1): embed the query, search the vector store.

`DenseRetriever` implements `Retriever`: the query is embedded by a `QueryEmbedder` (the corpus
model and its query prefix, `scitech_agent.embedding`) and searched in a `VectorSearch` (the Qdrant
store, `scitech_agent.store`), with the caller's `k` (the agent passes `RETRIEVAL_TOP_K`) and
filters. The score is the store's cosine similarity, so `RETRIEVAL_MIN_SCORE` is compared with it.
Embedding and store failures surface as `RetrievalError` (`retrieval_failed`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from scitech_agent.embedding import EmbeddingError, QueryEmbedder, SentenceTransformerEmbedder
from scitech_agent.retrieval import Filters, ScoredChunk


class VectorSearch(Protocol):
    def search(
        self, vector: Sequence[float], k: int, filters: Filters | None = None
    ) -> list[ScoredChunk]: ...


class DenseRetriever:
    def __init__(self, store: VectorSearch, embedder: QueryEmbedder) -> None:
        self.store = store
        self.embedder = embedder

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DenseRetriever:
        """Qdrant from `QDRANT_URL`/`QDRANT_COLLECTION`, the model from `EMBEDDING_MODEL` and
        `EMBEDDING_QUERY_PREFIX`. The model loads on the first search."""
        from scitech_agent.store import QdrantStore

        return cls(QdrantStore.from_env(env), SentenceTransformerEmbedder.from_env(env))

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        if not query.strip():
            return []
        try:
            vector = self.embedder.embed_query(query)
        except EmbeddingError:
            raise
        except Exception as exc:  # a model error mid-encode: report it as a retrieval failure
            raise EmbeddingError(f"query embedding failed: {exc}") from exc
        return self.store.search(vector, k, filters)
