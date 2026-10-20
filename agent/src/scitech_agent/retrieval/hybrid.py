"""Hybrid retriever (W3-D4-DAT-1): reciprocal rank fusion of dense and BM25 results.

`rrf_fuse` merges ranked lists by rank only: a chunk at rank r (1-based) in a list gets
`1 / (rrf_k + r)` from it, and its fused score is the sum over the lists it appears in (Cormack
et al., 2009; `rrf_k` 60 by default). Cosine and BM25 scores live on different scales, so they are
never mixed. Chunks are deduplicated by `chunk_id`, keeping the fields of the first list that has
the chunk. The fused score is at most `len(lists) / (rrf_k + 1)` (about 0.033 for two lists), so
`RETRIEVAL_MIN_SCORE` thresholds tuned on cosine scores do not carry over.

`HybridRetriever` asks each retriever for its own top-k (at least the caller's `k`) with the same
filters, fuses, and returns the best `k`. A failure of either retriever is raised: a silent fall
back to one retriever would change results without anyone noticing.

`retriever_from_env` is the config switch `RETRIEVER=dense|bm25|hybrid` (default `hybrid`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from scitech_agent.retrieval import Filters, Retriever, ScoredChunk

RETRIEVERS = ("dense", "bm25", "hybrid")


def rrf_fuse(rankings: Sequence[Sequence[ScoredChunk]], rrf_k: int = 60) -> list[ScoredChunk]:
    """Fuse ranked lists (best first) into one list, best first, with the RRF score as `score`.
    Ties are broken by the best rank the chunk reached in any list, then by `chunk_id`."""
    if rrf_k < 0:
        raise ValueError(f"rrf_k must be >= 0, got {rrf_k}")
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    chunks: dict[str, ScoredChunk] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, chunk in enumerate(ranking, start=1):
            cid = chunk.chunk_id
            if cid in seen:  # a list should not repeat a chunk; count its best rank only
                continue
            seen.add(cid)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            best_rank[cid] = min(best_rank.get(cid, rank), rank)
            chunks.setdefault(cid, chunk)
    order = sorted(scores, key=lambda cid: (-scores[cid], best_rank[cid], cid))
    return [replace(chunks[cid], score=scores[cid]) for cid in order]


@dataclass(frozen=True)
class HybridConfig:
    rrf_k: int = 60
    dense_top_k: int = 50
    keyword_top_k: int = 50

    def __post_init__(self) -> None:
        if self.rrf_k < 0:
            raise ValueError(f"RRF_K must be >= 0, got {self.rrf_k}")
        if self.dense_top_k <= 0 or self.keyword_top_k <= 0:
            raise ValueError("HYBRID_DENSE_TOP_K and HYBRID_KEYWORD_TOP_K must be positive")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HybridConfig:
        """Read `RRF_K`, `HYBRID_DENSE_TOP_K`, `HYBRID_KEYWORD_TOP_K` (empty: the defaults)."""
        env = os.environ if env is None else env

        def number(name: str, default: int) -> int:
            raw = (env.get(name) or "").strip()
            return int(raw) if raw else default

        return cls(
            rrf_k=number("RRF_K", cls.rrf_k),
            dense_top_k=number("HYBRID_DENSE_TOP_K", cls.dense_top_k),
            keyword_top_k=number("HYBRID_KEYWORD_TOP_K", cls.keyword_top_k),
        )


class HybridRetriever:
    def __init__(
        self, dense: Retriever, keyword: Retriever, config: HybridConfig | None = None
    ) -> None:
        self.dense = dense
        self.keyword = keyword
        self.config = config or HybridConfig()

    def search(self, query: str, k: int, filters: Filters | None = None) -> list[ScoredChunk]:
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        dense = self.dense.search(query, max(k, self.config.dense_top_k), filters)
        keyword = self.keyword.search(query, max(k, self.config.keyword_top_k), filters)
        return rrf_fuse([dense, keyword], self.config.rrf_k)[:k]


def bm25_index_dir(env: Mapping[str, str]) -> Path:
    """`BM25_INDEX_DIR`, or `<DATA_DIR>/index/bm25` when it is empty."""
    explicit = (env.get("BM25_INDEX_DIR") or "").strip()
    return Path(explicit) if explicit else Path(env.get("DATA_DIR") or "data") / "index" / "bm25"


def retriever_from_env(env: Mapping[str, str] | None = None) -> Retriever:
    """The retriever named by `RETRIEVER` (`dense`, `bm25` or `hybrid`; empty: `hybrid`).
    Dense needs Qdrant and the embedding model (`DenseRetriever.from_env`); BM25 loads the index
    from `BM25_INDEX_DIR`; hybrid needs both, plus `RRF_K` and the per-retriever top-k."""
    from scitech_agent.retrieval.dense import DenseRetriever
    from scitech_agent.retrieval.keyword import KeywordRetriever

    env = os.environ if env is None else env
    name = (env.get("RETRIEVER") or "hybrid").strip().lower()
    if name not in RETRIEVERS:
        raise ValueError(f"RETRIEVER must be one of {', '.join(RETRIEVERS)}, got {name!r}")
    if name == "dense":
        return DenseRetriever.from_env(env)
    if name == "bm25":
        return KeywordRetriever.load(bm25_index_dir(env))
    config = HybridConfig.from_env(env)  # checked before loading the index or the model
    return HybridRetriever(
        DenseRetriever.from_env(env), KeywordRetriever.load(bm25_index_dir(env)), config
    )
