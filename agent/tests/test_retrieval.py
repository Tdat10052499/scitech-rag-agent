"""Tests of the retrieval interface and the in-memory fake (W2-D3-DAT-1)."""

from __future__ import annotations

import pytest

from scitech_agent.demo import DEMO_CHUNKS, DemoRetriever
from scitech_agent.retrieval import InMemoryRetriever, RetrievalError, ScoredChunk, matches

CHUNKS = [
    ScoredChunk(
        "b#0",
        "b",
        0.0,
        "Dense retrieval",
        "Dense passage retrieval for QA.",
        source="arxiv",
        chunk_index=0,
        categories=("cs.CL", "cs.IR"),
    ),
    ScoredChunk(
        "a#0",
        "a",
        0.0,
        "Sparse retrieval",
        "BM25 keyword retrieval for QA.",
        source="arxiv",
        chunk_index=0,
        categories=("cs.IR",),
    ),
    ScoredChunk(
        "w#0",
        "w",
        0.0,
        "Question answering",
        "Question answering on Wikipedia.",
        source="wikipedia",
        chunk_index=0,
    ),
]


def test_scores_are_query_word_overlap_best_first() -> None:
    hits = InMemoryRetriever(CHUNKS).search("dense retrieval for QA", k=10)
    assert [(h.chunk_id, h.score) for h in hits] == [("b#0", 1.0), ("a#0", 0.75)]


def test_ties_break_by_chunk_id_and_k_limits() -> None:
    retriever = InMemoryRetriever(CHUNKS)
    assert [h.chunk_id for h in retriever.search("retrieval", k=10)] == ["a#0", "b#0"]
    assert [h.chunk_id for h in retriever.search("retrieval", k=1)] == ["a#0"]
    assert retriever.calls[-1] == ("retrieval", 1, None)


def test_no_shared_word_is_no_hit() -> None:
    assert InMemoryRetriever(CHUNKS).search("protein folding", k=5) == []
    assert InMemoryRetriever(CHUNKS).search("?!", k=5) == []


def test_filters_on_scalar_and_list_fields() -> None:
    retriever = InMemoryRetriever(CHUNKS)
    assert [h.doc_id for h in retriever.search("QA", 5, {"source": "wikipedia"})] == []
    assert [h.doc_id for h in retriever.search("question", 5, {"source": "wikipedia"})] == ["w"]
    assert [h.doc_id for h in retriever.search("retrieval", 5, {"categories": "cs.CL"})] == ["b"]
    assert matches(CHUNKS[0], None) and not matches(CHUNKS[0], {"no_such_field": 1})


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        InMemoryRetriever(CHUNKS).search("retrieval", k=0)


def test_demo_retriever_triggers() -> None:
    retriever = DemoRetriever()
    assert retriever.search("What is a Transformer?", k=5) == DEMO_CHUNKS
    assert retriever.search("anything", k=1) == DEMO_CHUNKS[:1]
    assert retriever.search("insufficient evidence please", k=5) == []
    with pytest.raises(RetrievalError):
        retriever.search("please fail:retrieval_failed", k=5)


def test_source_and_chunk_index_are_required() -> None:
    # A store that forgets to map them must fail, not label every hit `arxiv` / index 0.
    with pytest.raises(TypeError):
        ScoredChunk("x#0", "x", 0.5, "Title", "Text")


def test_demo_agent_ignores_retrieval_settings_from_env(monkeypatch) -> None:
    from scitech_agent.demo import demo_agent

    monkeypatch.setenv("RETRIEVAL_MIN_SCORE", "0.9")
    monkeypatch.setenv("RETRIEVAL_TOP_K", "1")
    events = list(demo_agent().run("s", "What is attention?"))
    assert len(events[0].chunks) == len(DEMO_CHUNKS)


def test_matches_supports_ranges_like_the_vector_store():
    chunk = ScoredChunk(
        "d#0", "d", 0.0, "T", "x", source="arxiv", chunk_index=0, published_at="2023-03-15"
    )
    assert matches(chunk, {"published_at": {"gte": "2023-01-01", "lte": "2023-12-31"}})
    assert not matches(chunk, {"published_at": {"gt": "2023-03-15"}})
    assert matches(chunk, {"published_at": {"lt": "2023-03-16"}})
    assert not matches(CHUNKS[0], {"published_at": {"gte": "2000-01-01"}})  # no date
    with pytest.raises(ValueError):
        matches(chunk, {"published_at": {"after": "2023"}})
