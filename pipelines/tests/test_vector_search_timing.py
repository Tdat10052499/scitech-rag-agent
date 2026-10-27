import importlib.util
import json
from itertools import count
from pathlib import Path

import pytest

from scitech_agent.store import InMemoryStore, Point

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vector_search_timing.py"
spec = importlib.util.spec_from_file_location("vector_search_timing", SCRIPT)
vst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vst)


def ticks(step: float = 0.002):
    """A clock that moves `step` seconds per reading: every timed call takes `step`."""
    counter = count()
    return lambda: next(counter) * step


def store(collection: str, n: int) -> InMemoryStore:
    s = InMemoryStore(collection)
    s.ensure_collection(2)
    s.upsert(
        Point(
            i,
            [1.0, i / n],
            {
                "chunk_id": f"2301.{i:05d}#0",
                "doc_id": f"2301.{i:05d}",
                "title": f"Paper {i}",
                "text": "text",
                "source": "arxiv",
                "chunk_index": 0,
            },
        )
        for i in range(n)
    )
    return s


def test_embed_all_warms_up_then_times_every_query():
    calls = []

    def embed(query: str) -> list[float]:
        calls.append(query)
        return [float(len(query)), 1.0]

    vectors, seconds = vst.embed_all(embed, ["a", "bb", "ccc"], warmup=2, clock=ticks())
    assert calls == ["a", "bb", "a", "bb", "ccc"]
    assert vectors == [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]]
    assert seconds == pytest.approx([0.002] * 3)


def test_time_search_runs_every_round_and_keeps_the_last_ids():
    s = store("c", 20)
    vectors = [[1.0, 0.0], [1.0, 1.0]]
    seconds, ids = vst.time_search(s.search, vectors, k=3, warmup=1, rounds=2, clock=ticks())
    assert len(seconds) == 4
    assert len(s.searches) == 1 + 4
    assert [len(i) for i in ids] == [3, 3]


def test_overlap():
    assert vst.overlap([["a", "b"], ["c", "x"]], [["a", "b"], ["c", "d"]]) == 0.75
    assert vst.overlap([[]], [[]]) == 1.0


def test_measure_uses_the_same_vectors_for_every_collection_and_mode():
    stores = {"small": store("small", 10), "big": store("big", 50)}
    made = []

    def store_for(collection: str, exact: bool, gzip: bool) -> InMemoryStore:
        made.append((collection, exact, gzip))
        return stores[collection]

    vectors = [[1.0, 0.1], [1.0, 0.9]]
    result = vst.measure(
        ["small", "big"], vectors, store_for, k=5, warmup=0, rounds=1, clock=ticks()
    )
    modes = [(True, True), (False, True), (True, False)]
    assert made == [(c, *m) for c in ("small", "big") for m in modes]
    assert result["small"]["points"] == 10
    assert result["big"]["points"] == 50
    for row in result.values():
        assert row["exact"]["n"] == row["hnsw"]["n"] == row["exact_no_gzip"]["n"] == 2
        assert row["exact"]["p50_ms"] == pytest.approx(2.0)
        assert row["hnsw"]["overlap_with_exact"] == 1.0  # same fake store: same hits
    assert [v for v, _, _ in stores["big"].searches] == vectors * 3
    text = vst.markdown(
        {"embedding": {"n": 2, "p50_ms": 80.0, "p95_ms": 90.0}, "collections": result}
    )
    assert "| big | 50 | 2.0 / 2.0 / 2.0 | 2.0 / 2.0 / 2.0 | 2.0 / 2.0 / 2.0 | 100.0% |" in text
    json.dumps(result)  # the result is written as JSON
