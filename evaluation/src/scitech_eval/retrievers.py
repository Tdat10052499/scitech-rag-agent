"""What the harness needs from a retriever, plus a replay retriever for stored rankings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk. `doc_id` is the arXiv id without a version suffix."""

    chunk_id: str
    doc_id: str
    score: float | None = None


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[Hit]:
        """Return at most k chunks, best first."""
        ...


class CannedRetriever:
    """Replays stored rankings: {question: [{"chunk_id": ..., "doc_id": ...}, ...]}.

    Used to test the harness and to score a ranking that was produced elsewhere.
    """

    def __init__(self, rankings: dict[str, list[dict]]):
        self._rankings = rankings

    def search(self, query: str, k: int) -> list[Hit]:
        if query not in self._rankings:
            raise KeyError(f"no stored ranking for query: {query!r}")
        return [
            Hit(h["chunk_id"], h["doc_id"], h.get("score")) for h in self._rankings[query][:k]
        ]


def canned(rankings_path: str) -> CannedRetriever:
    """Factory for config files: `factory: scitech_eval.retrievers:canned`."""
    return CannedRetriever(json.loads(Path(rankings_path).read_text(encoding="utf-8")))
