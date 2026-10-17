"""Retrieval interface of the agent (W2-D3-DAT-1).

`Retriever` is what the agent needs from any search backend: the vector store (W3), hybrid search
(W4) or a fake. `ScoredChunk` is one hit; its field names follow `docs/contracts/chunk.schema.json`,
and `chunk_id`, `doc_id`, `score` match `Hit` in `evaluation/` (W2-D4-LDN-1), so the evaluation
harness can wrap the same retriever. `InMemoryRetriever` is a deterministic fake for tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

Filters = Mapping[str, Any]


class RetrievalError(Exception):
    """The search backend failed (index down, bad response). Contract code `retrieval_failed`."""

    code = "retrieval_failed"


@dataclass(frozen=True)
class ScoredChunk:
    """One retrieved chunk with its similarity score (higher is better)."""

    chunk_id: str
    doc_id: str
    score: float
    title: str
    text: str
    source: str = "arxiv"
    chunk_index: int = 0
    url: str | None = None
    published_at: str | None = None  # ISO date, as in chunk.schema.json
    categories: tuple[str, ...] = field(default_factory=tuple)
    license: str | None = None


class Retriever(Protocol):
    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        """Return at most `k` chunks, best first. Raise on backend failure."""
        ...


def matches(chunk: ScoredChunk, filters: Filters | None) -> bool:
    """True if `chunk` has every filtered value; a list field (categories) must contain it."""
    for name, wanted in (filters or {}).items():
        value = getattr(chunk, name, None)
        if isinstance(value, (tuple, list)):
            if wanted not in value:
                return False
        elif value != wanted:
            return False
    return True


_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class InMemoryRetriever:
    """Fake retriever over a fixed list of chunks. The score is the share of query words found
    in the chunk's title and text (0 to 1); chunks sharing no word with the query are not hits.
    Ties are broken by `chunk_id`, so results are deterministic."""

    def __init__(self, chunks: Iterable[ScoredChunk]) -> None:
        self.chunks: Sequence[ScoredChunk] = list(chunks)
        self.calls: list[tuple[str, int, Filters | None]] = []

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        self.calls.append((query, k, filters))
        terms = _words(query)
        hits = []
        for chunk in self.chunks:
            if not matches(chunk, filters) or not terms:
                continue
            overlap = len(terms & _words(f"{chunk.title} {chunk.text}"))
            if overlap:
                hits.append(replace(chunk, score=round(overlap / len(terms), 4)))
        hits.sort(key=lambda c: (-c.score, c.chunk_id))
        return hits[:k]
