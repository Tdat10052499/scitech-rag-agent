"""What the harness needs from a retriever, plus a replay retriever for stored rankings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk. `doc_id` is the arXiv id without a version suffix.

    The fields are the same as `ScoredChunk` in scitech_agent (chunk_id, doc_id, score). The runner
    reads only `chunk_id` and `doc_id`, so a retriever may return its own `ScoredChunk` objects.
    """

    chunk_id: str
    doc_id: str
    score: float | None = None


class Retriever(Protocol):
    """Same call as the agent's `search(query, k, filters)`; the harness passes no filters."""

    def search(self, query: str, k: int, filters: dict | None = None) -> list[Hit]:
        """Return at most k chunks, best first."""
        ...


class CannedRetriever:
    """Replays stored rankings: {question: [{"chunk_id": ..., "doc_id": ...}, ...]}.

    Used to test the harness and to score a ranking that was produced elsewhere.
    """

    def __init__(self, rankings: dict[str, list[dict]]):
        self._rankings = rankings

    def search(self, query: str, k: int, filters: dict | None = None) -> list[Hit]:
        if query not in self._rankings:
            raise KeyError(f"no stored ranking for query: {query!r}")
        return [Hit(h["chunk_id"], h["doc_id"], h.get("score")) for h in self._rankings[query][:k]]


def canned(rankings_path: str) -> CannedRetriever:
    """Factory for config files: `factory: scitech_eval.retrievers:canned`."""
    return CannedRetriever(json.loads(Path(rankings_path).read_text(encoding="utf-8")))


AGENT_RETRIEVERS = ("dense", "bm25", "hybrid")


def agent_retriever(retriever: str, **env: object) -> Retriever:
    """Build one of the agent's retrievers (factory `scitech_eval.retrievers:agent_retriever`).

    `retriever` is `dense`, `bm25` or `hybrid`. It is passed to the agent as `RETRIEVER`; the other
    params are environment variables for it (`RRF_K`, `EMBEDDING_QUERY_PREFIX`, ...), written as in
    `.env.example` and turned into strings. Everything else comes from the process environment
    (`QDRANT_URL`, `QDRANT_COLLECTION`, `DATA_DIR`, ...), which the params override. The agent
    package is imported only here, so the rest of the harness does not need it (`PYTHONPATH` must
    contain `agent/src` for this factory).
    """
    if retriever not in AGENT_RETRIEVERS:
        names = ", ".join(AGENT_RETRIEVERS)
        raise ValueError(f"retriever must be one of {names}, not {retriever!r}")
    from scitech_agent.retrieval.hybrid import retriever_from_env

    merged = {**os.environ, "RETRIEVER": retriever}
    merged.update({key: str(value) for key, value in env.items()})
    return retriever_from_env(merged)
