"""Filters by year range and category give the same hits in every retriever (W4-D1-FAO-1).

One corpus with dates on both sides of a year boundary goes into the in-memory fake, the dense
retriever (fake store), BM25, hybrid and, when Qdrant answers at `QDRANT_URL`, the dense
retriever over a real Qdrant in a throw-away collection (marked `integration`, skipped in CI).
Every filter in `CASES` must keep the same documents in all of them.
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scitech_agent import retrieval
from scitech_agent.embedding import FakeEmbedder
from scitech_agent.retrieval import (
    InMemoryRetriever,
    ScoredChunk,
    check_range,
    compile_filters,
    matches,
    year_range,
)
from scitech_agent.retrieval.dense import DenseRetriever
from scitech_agent.retrieval.hybrid import HybridRetriever
from scitech_agent.retrieval.keyword import KeywordRetriever, build_index
from scitech_agent.store import InMemoryStore, Point, QdrantStore, StoreConfig

QUERY = "retrieval"

# doc_id, published_at, categories: two papers on each side of 1 January 2024 and 2025.
DOCS = [
    ("d2023", "2023-12-31", ["cs.CL"]),
    ("d2024a", "2024-01-01", ["cs.IR"]),
    ("d2024b", "2024-06-15", ["cs.CL", "cs.IR"]),
    ("d2024c", "2024-12-31", ["cs.LG"]),
    ("d2025", "2025-01-01", ["cs.CL"]),
]

CASES = [
    pytest.param(year_range(2024, 2024), {"d2024a", "d2024b", "d2024c"}, id="year-2024"),
    pytest.param(year_range(start=2024), {"d2024a", "d2024b", "d2024c", "d2025"}, id="from-2024"),
    pytest.param(year_range(end=2023), {"d2023"}, id="to-2023"),
    pytest.param({"categories": "cs.CL"}, {"d2023", "d2024b", "d2025"}, id="category"),
    pytest.param({**year_range(2024, 2025), "categories": "cs.CL"}, {"d2024b", "d2025"}, id="both"),
    pytest.param(  # a datetime bound: a date is midnight UTC, as in Qdrant
        {"published_at": {"gte": "2024-01-01T00:00:00Z", "lte": "2024-06-15T00:00:00Z"}},
        {"d2024a", "d2024b"},
        id="datetime-bounds",
    ),
    pytest.param(
        {"published_at": {"gt": "2024-06-15", "lte": "2024-12-31"}}, {"d2024c"}, id="date-bounds"
    ),
]


def payload(doc: str, published_at: str, categories: list[str]) -> dict:
    return {
        "chunk_id": f"{doc}#0",
        "doc_id": doc,
        "source": "arxiv",
        "title": f"Paper {doc}",
        "text": f"Dense and sparse retrieval, paper {doc}.",
        "chunk_index": 0,
        "categories": categories,
        "published_at": published_at,
    }


PAYLOADS = [payload(*doc) for doc in DOCS]


def dense(store) -> DenseRetriever:
    embedder = FakeEmbedder()
    store.ensure_collection(embedder.dimension)
    store.upsert(Point(i, embedder.embed(p["text"]), p) for i, p in enumerate(PAYLOADS))
    return DenseRetriever(store, embedder)


@pytest.fixture(scope="module")
def keyword(tmp_path_factory) -> KeywordRetriever:
    root = tmp_path_factory.mktemp("bm25")
    (root / "chunks").mkdir()
    pq.write_table(pa.Table.from_pylist(PAYLOADS), root / "chunks" / "chunks.parquet")
    (root / "chunks" / "_chunk_manifest.json").write_text(json.dumps({"chunked_at": "x"}))
    build_index(root / "chunks", root / "bm25")
    return KeywordRetriever.load(root / "bm25")


@pytest.fixture(scope="module")
def qdrant():
    url = (os.environ.get("QDRANT_URL") or "http://localhost:6333").rstrip("/")
    try:
        up = httpx.get(f"{url}/healthz", timeout=2.0).is_success
    except httpx.HTTPError:
        up = False
    if not up:
        pytest.skip(f"Qdrant is not reachable at {url}")
    with QdrantStore(StoreConfig(url=url, collection=f"test_filters_{uuid.uuid4().hex[:12]}")) as s:
        yield dense(s)
        s.delete_collection()


@pytest.fixture(
    params=[
        "memory",
        "dense",
        "bm25",
        "hybrid",
        pytest.param("qdrant", marks=pytest.mark.integration),
    ]
)
def retriever(request, keyword):
    if request.param == "memory":
        return InMemoryRetriever(
            ScoredChunk(score=0.0, **{**p, "categories": tuple(p["categories"])}) for p in PAYLOADS
        )
    if request.param == "dense":
        return dense(InMemoryStore())
    if request.param == "bm25":
        return keyword
    if request.param == "hybrid":
        return HybridRetriever(dense(InMemoryStore()), keyword)
    return request.getfixturevalue("qdrant")


def test_every_document_is_a_hit_without_filters(retriever):
    assert {h.doc_id for h in retriever.search(QUERY, k=10)} == {d[0] for d in DOCS}


@pytest.mark.parametrize(("filters", "expected"), CASES)
def test_filters_keep_the_same_documents_in_every_retriever(retriever, filters, expected):
    assert {h.doc_id for h in retriever.search(QUERY, k=10, filters=filters)} == expected


@pytest.mark.parametrize("bound", ["2024", "20240101", "last year", None])
def test_a_bound_that_is_not_an_iso_date_is_refused_everywhere(retriever, bound):
    with pytest.raises(ValueError, match="year_range|ISO date"):
        retriever.search(QUERY, k=10, filters={"published_at": {"gte": bound}})


def test_a_range_mixing_numbers_and_dates_is_refused_everywhere(retriever):
    with pytest.raises(ValueError, match="mixes numbers and dates"):
        retriever.search(QUERY, k=10, filters={"published_at": {"gte": 2020, "lt": "2024-01-01"}})


def test_a_bad_bound_is_refused_even_when_nothing_would_be_compared(retriever):
    # No chunk has the field, so a per-row check would never run; the check is per search.
    with pytest.raises(ValueError, match="year_range"):
        retriever.search(QUERY, k=10, filters={"no_such_field": {"gte": "2024"}})


@pytest.mark.parametrize(("filters", "expected"), CASES)
def test_compile_filters_agrees_with_matches(filters, expected):
    chunks = [
        ScoredChunk(score=0.0, **{**p, "categories": tuple(p["categories"])}) for p in PAYLOADS
    ]
    keep = compile_filters(filters)
    assert {c.doc_id for c in chunks if keep(c)} == expected
    assert [keep(c) for c in chunks] == [matches(c, filters) for c in chunks]


def test_compile_filters_checks_the_bounds_once(monkeypatch):
    calls = []
    real = retrieval.check_range
    monkeypatch.setattr(retrieval, "check_range", lambda *a: calls.append(a) or real(*a))
    keep = compile_filters({**year_range(2024, 2024), "categories": "cs.CL"})
    chunk = ScoredChunk(
        score=0.0, **{**PAYLOADS[0], "categories": tuple(PAYLOADS[0]["categories"])}
    )
    for _ in range(1000):
        keep(chunk)
    assert len(calls) == 1
    assert compile_filters(None)(chunk) and compile_filters({})(chunk)


def test_year_range():
    assert year_range(2020, 2024) == {"published_at": {"gte": "2020-01-01", "lt": "2025-01-01"}}
    assert year_range(end=1999) == {"published_at": {"lt": "2000-01-01"}}
    with pytest.raises(ValueError, match="start 2025 is after end 2024"):
        year_range(2025, 2024)
    with pytest.raises(ValueError, match="needs"):
        year_range()


def test_check_range():
    check_range("published_at", {"gte": "2024-01-01", "lt": "2024-06-15T12:30:00+07:00"})
    check_range("chunk_index", {"gte": 1, "lt": 2.5})
    with pytest.raises(ValueError, match="a range takes"):
        check_range("published_at", {"after": "2024-01-01"})
    with pytest.raises(ValueError, match="a range takes"):
        check_range("published_at", {})
    with pytest.raises(ValueError, match="'published_at': gte bound True"):
        check_range("published_at", {"gte": True})
    with pytest.raises(ValueError, match="mixes numbers and dates"):
        check_range("published_at", {"gte": 2020, "lt": "2024-01-01"})
