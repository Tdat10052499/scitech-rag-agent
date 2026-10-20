"""Tests of the query embedding helper and the dense retriever (W3-D2-DAT-1), with
`FakeEmbedder` and `InMemoryStore`; no model and no Qdrant."""

from __future__ import annotations

import pytest

from scitech_agent.agent import Agent, AgentConfig
from scitech_agent.embedding import (
    EmbeddingConfig,
    EmbeddingError,
    FakeEmbedder,
    SentenceTransformerEmbedder,
    query_text,
)
from scitech_agent.events import SourcesEvent
from scitech_agent.llm import FakeLLM
from scitech_agent.retrieval import RetrievalError, Retriever
from scitech_agent.retrieval.dense import DenseRetriever
from scitech_agent.store import InMemoryStore, Point, StoreError

BGE_PREFIX = "Represent this sentence for searching relevant passages: "

DOCS = [
    (
        "a",
        "Dense passage retrieval",
        "Dense retrieval with dual encoders for open-domain QA.",
        ["cs.CL", "cs.IR"],
        "2020-04-10",
        "arxiv",
    ),
    (
        "b",
        "BM25 baselines",
        "Keyword search with BM25 remains a strong retrieval baseline.",
        ["cs.IR"],
        "2021-06-01",
        "arxiv",
    ),
    (
        "c",
        "Speech recognition",
        "End-to-end speech recognition with transformers.",
        ["cs.CL", "eess.AS"],
        "2023-02-15",
        "arxiv",
    ),
    (
        "w",
        "Question answering",
        "Question answering is a task in natural language processing.",
        [],
        "2024-01-01",
        "wikipedia",
    ),
]


def make_store(embedder: FakeEmbedder) -> InMemoryStore:
    store = InMemoryStore()
    store.ensure_collection(embedder.dimension)
    points = []
    for i, (doc, title, text, categories, published_at, source) in enumerate(DOCS):
        payload = {
            "chunk_id": f"{doc}#0",
            "doc_id": doc,
            "source": source,
            "title": title,
            "text": f"{title}. {text}",
            "chunk_index": 0,
            "categories": categories,
            "published_at": published_at,
        }
        points.append(Point(i, embedder.embed(payload["text"]), payload))  # passages: no prefix
    store.upsert(points)
    return store


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimension=64, query_prefix=BGE_PREFIX)


@pytest.fixture
def retriever(embedder) -> DenseRetriever:
    return DenseRetriever(make_store(embedder), embedder)


def test_query_text_applies_the_prefix_with_one_space():
    assert query_text("what is BM25?", BGE_PREFIX) == BGE_PREFIX + "what is BM25?"
    assert query_text("q", BGE_PREFIX.rstrip()) == BGE_PREFIX + "q"  # trimmed by a .env parser
    assert query_text("q", "") == "q"
    assert query_text("q", "   ") == "q"


def test_embedding_config_from_env():
    config = EmbeddingConfig.from_env(
        {"EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5", "EMBEDDING_QUERY_PREFIX": BGE_PREFIX}
    )
    assert config == EmbeddingConfig("BAAI/bge-small-en-v1.5", BGE_PREFIX)
    assert EmbeddingConfig.from_env({"EMBEDDING_MODEL": "m"}).query_prefix == ""
    for env in ({}, {"EMBEDDING_MODEL": ""}, {"EMBEDDING_MODEL": "replace-me"}):
        with pytest.raises(ValueError, match="EMBEDDING_MODEL"):
            EmbeddingConfig.from_env(env)


def test_dense_retriever_is_a_retriever_and_ranks_by_cosine(retriever, embedder):
    r: Retriever = retriever
    hits = r.search("dense retrieval for open-domain QA", k=3)
    assert hits[0].chunk_id == "a#0"
    assert len(hits) == 3
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert 0 < hits[0].score <= 1
    assert embedder.calls == [BGE_PREFIX + "dense retrieval for open-domain QA"]


def test_dense_retriever_passes_k_and_filters_to_the_store(retriever):
    store = retriever.store
    hits = retriever.search("retrieval", k=2, filters={"categories": "cs.IR"})
    assert {h.chunk_id for h in hits} <= {"a#0", "b#0"}
    assert store.searches[-1][1:] == (2, {"categories": "cs.IR"})
    hits = retriever.search(
        "retrieval", k=10, filters={"published_at": {"gte": "2021-01-01", "lte": "2023-12-31"}}
    )
    assert {h.chunk_id for h in hits} == {"b#0", "c#0"}
    hits = retriever.search("question", k=5, filters={"source": "wikipedia"})
    assert [h.chunk_id for h in hits] == ["w#0"]


def test_blank_query_returns_nothing_and_bad_k_is_refused(retriever, embedder):
    assert retriever.search("   ", k=3) == []
    assert embedder.calls == []
    with pytest.raises(ValueError):
        retriever.search("retrieval", k=0)


class BrokenEmbedder:
    def embed_query(self, query: str) -> list[float]:
        raise RuntimeError("CUDA out of memory")


def test_embedding_and_store_failures_are_retrieval_failed(embedder):
    with pytest.raises(RetrievalError) as info:
        DenseRetriever(make_store(embedder), BrokenEmbedder()).search("q", k=1)
    assert info.value.code == "retrieval_failed"
    assert isinstance(info.value, EmbeddingError)

    wrong_dimension = DenseRetriever(make_store(embedder), FakeEmbedder(dimension=8))
    with pytest.raises(StoreError):
        wrong_dimension.search("retrieval", k=1)


def test_missing_sentence_transformers_is_an_embedding_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_st(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_st)
    embedder = SentenceTransformerEmbedder(EmbeddingConfig("BAAI/bge-small-en-v1.5"))
    with pytest.raises(EmbeddingError, match="requirements-embed"):
        embedder.embed_query("q")


def test_agent_runs_with_the_dense_retriever(retriever):
    llm = FakeLLM(["Dense retrieval uses dual encoders [1].", "What is DPR?"])
    agent = Agent(retriever, llm, AgentConfig(top_k=2, min_score=0.1))
    events = list(agent.run("s1", "How does dense retrieval work?"))
    sources = next(e for e in events if isinstance(e, SourcesEvent))
    assert sources.chunks[0].chunk_id == "a#0"
    assert len(sources.chunks) <= 2


def test_in_memory_store_behaves_like_the_store():
    store = InMemoryStore()
    assert store.ensure_collection(2) is True
    assert store.ensure_collection(2) is False
    with pytest.raises(StoreError):
        store.ensure_collection(3)
    payload = {
        "chunk_id": "d#0",
        "doc_id": "d",
        "source": "arxiv",
        "title": "T",
        "text": "x",
        "chunk_index": 0,
        "categories": ["cs.CL"],
    }
    store.upsert(
        [
            Point(1, [1.0, 0.0], payload),
            Point(2, [0.0, 1.0], dict(payload, chunk_id="d#1", chunk_index=1)),
        ]
    )
    store.upsert([Point(1, [1.0, 0.0], payload)])  # same id: replaced
    assert store.count() == 2
    assert store.count({"categories": "cs.LG"}) == 0
    assert [h.chunk_id for h in store.search([1.0, 0.1], k=1)] == ["d#0"]
    with pytest.raises(StoreError):
        store.upsert([Point(3, [1.0], payload)])
