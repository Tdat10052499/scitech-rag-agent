"""Retrieval metrics as defined in evaluation/PLAN.md section 4.1.

A retriever returns a ranked list of chunks; a chunk is a hit if its doc_id is relevant.
`doc_ids` below is that list reduced to the doc_id of each chunk, best first.
"""

from __future__ import annotations

import random
from collections.abc import Collection, Sequence

MRR_DEPTH = 10


def recall_at_k(relevant: Collection[str], doc_ids: Sequence[str], k: int) -> float:
    """|R_q ∩ D_k| / |R_q|, where D_k is the set of distinct doc_ids among the top-k chunks."""
    relevant = set(relevant)
    if not relevant:
        raise ValueError("recall needs at least one relevant document")
    return len(relevant & set(doc_ids[:k])) / len(relevant)


def reciprocal_rank(
    relevant: Collection[str], doc_ids: Sequence[str], depth: int = MRR_DEPTH
) -> float:
    """1 / position of the first hit chunk in the top `depth`, or 0 if there is none.

    Positions count chunks, so several chunks of one document before the first hit all take a rank.
    """
    relevant = set(relevant)
    for position, doc_id in enumerate(doc_ids[:depth], start=1):
        if doc_id in relevant:
            return 1 / position
    return 0.0


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def bootstrap_ci(
    values: Sequence[float], resamples: int = 1000, seed: int = 0, level: float = 0.95
) -> tuple[float, float]:
    """Percentile bootstrap interval of the mean, resampling questions with replacement."""
    if not values:
        raise ValueError("bootstrap needs at least one value")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    tail = (1 - level) / 2
    return means[int(tail * resamples)], means[int((1 - tail) * resamples) - 1]
