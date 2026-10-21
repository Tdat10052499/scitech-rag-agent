"""Tests of reciprocal rank fusion and the hybrid retriever (W3-D4-DAT-1), on hand-made rankings;
no model, no Qdrant."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scitech_agent.agent import Agent, AgentConfig
from scitech_agent.events import SourcesEvent
from scitech_agent.llm import FakeLLM
from scitech_agent.retrieval import RetrievalError, Retriever, ScoredChunk
from scitech_agent.retrieval.dense import DenseRetriever
from scitech_agent.retrieval.hybrid import (
    HybridConfig,
    HybridRetriever,
    bm25_index_dir,
    retriever_from_env,
    rrf_fuse,
)
from scitech_agent.retrieval.keyword import KeywordRetriever, build_index


def hit(cid: str, score: float = 1.0, title: str = "") -> ScoredChunk:
    doc = cid.split("#")[0]
    return ScoredChunk(cid, doc, score, title or doc, f"text of {cid}", "arxiv", 0)


class Scripted:
    """Retriever returning a fixed ranking (cut to k); records the calls."""

    def __init__(self, ranking: list[ScoredChunk], error: Exception | None = None) -> None:
        self.ranking = ranking
        self.error = error
        self.calls: list[tuple[str, int, object]] = []

    def search(self, query, k, filters=None):
        self.calls.append((query, k, filters))
        if self.error:
            raise self.error
        return self.ranking[:k]


def ids(chunks):
    return [c.chunk_id for c in chunks]


def test_fusion_order_on_a_hand_made_example():
    # dense: a, b, c; keyword: c, d, a. With rrf_k = 60:
    # a = 1/61 + 1/63, c = 1/63 + 1/61 (tie, both reach rank 1: chunk_id decides),
    # b = 1/62, d = 1/62 (tie, both reach rank 2).
    dense = [hit("a#0", 0.9), hit("b#0", 0.8), hit("c#0", 0.7)]
    keyword = [hit("c#0", 12.0), hit("d#0", 9.0), hit("a#0", 3.0)]
    fused = rrf_fuse([dense, keyword])
    assert ids(fused) == ["a#0", "c#0", "b#0", "d#0"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63)
    assert fused[2].score == pytest.approx(1 / 62)


def test_agreement_beats_a_single_first_place():
    # x is first in one list only; y is second in one and first in the other.
    fused = rrf_fuse([[hit("x#0"), hit("y#0")], [hit("y#0")]])
    assert ids(fused) == ["y#0", "x#0"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)


def test_raw_scores_are_ignored_and_the_constant_changes_the_order():
    # z is 1st and 30th; w is 3rd in both lists. Small rrf_k rewards the single top rank,
    # large rrf_k rewards appearing high in both lists.
    filler = [hit(f"f{i}#0") for i in range(26)]
    first = [hit("z#0", 1e6), hit("p#0"), hit("w#0", 1e-6)]
    second = [hit("q#0"), hit("r#0"), hit("w#0"), *filler, hit("z#0")]
    assert ids(rrf_fuse([first, second], rrf_k=0))[:2] == ["z#0", "q#0"]
    assert ids(rrf_fuse([first, second], rrf_k=60))[0] == "w#0"
    with pytest.raises(ValueError):
        rrf_fuse([first], rrf_k=-1)


def test_duplicates_are_merged_by_chunk_id_keeping_the_first_list_fields():
    fused = rrf_fuse([[hit("a#0", title="from dense")], [hit("a#0", title="from bm25")]])
    assert len(fused) == 1 and fused[0].title == "from dense"
    # A list that repeats a chunk counts it once, at its best rank.
    assert rrf_fuse([[hit("a#0"), hit("a#0")]])[0].score == pytest.approx(1 / 61)
    assert rrf_fuse([[], []]) == []


def test_hybrid_asks_each_retriever_for_its_own_top_k_with_the_same_filters():
    dense = Scripted([hit("a#0"), hit("b#0"), hit("c#0")])
    keyword = Scripted([hit("c#0"), hit("d#0"), hit("a#0")])
    hybrid: Retriever = HybridRetriever(
        dense, keyword, HybridConfig(dense_top_k=3, keyword_top_k=2)
    )
    filters = {"categories": "cs.CL"}
    hits = hybrid.search("q", k=2, filters=filters)
    assert dense.calls == [("q", 3, filters)] and keyword.calls == [("q", 2, filters)]
    # keyword top 2 is c, d: a = 1/61, c = 1/63 + 1/61, so c leads.
    assert ids(hits) == ["c#0", "a#0"]
    hybrid.search("q", k=10)  # k above a top-k: each retriever is asked for k
    assert dense.calls[-1][1] == 10 and keyword.calls[-1][1] == 10
    with pytest.raises(ValueError):
        hybrid.search("q", k=0)


def test_a_failing_retriever_fails_the_search():
    ok = Scripted([hit("a#0")])
    down = Scripted([], error=RetrievalError("qdrant down"))
    for hybrid in (HybridRetriever(down, ok), HybridRetriever(ok, down)):
        with pytest.raises(RetrievalError):
            hybrid.search("q", k=3)


def test_hybrid_config_from_env():
    assert HybridConfig.from_env({}) == HybridConfig(60, 50, 50)
    env = {"RRF_K": "20", "HYBRID_DENSE_TOP_K": "30", "HYBRID_KEYWORD_TOP_K": " "}
    assert HybridConfig.from_env(env) == HybridConfig(20, 30, 50)
    for bad in ({"RRF_K": "-1"}, {"HYBRID_DENSE_TOP_K": "0"}, {"HYBRID_KEYWORD_TOP_K": "x"}):
        with pytest.raises(ValueError):
            HybridConfig.from_env(bad)


@pytest.fixture
def bm25_dir(tmp_path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    rows = [
        {
            "chunk_id": "a#0",
            "doc_id": "a",
            "source": "arxiv",
            "title": "BM25",
            "chunk_index": 0,
            "text": "BM25 is a strong keyword retrieval baseline.",
            "categories": ["cs.IR"],
            "published_at": "2021-06-01",
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), chunks / "chunks.parquet")
    (chunks / "_chunk_manifest.json").write_text(json.dumps({"chunked_at": "2026-10-17"}))
    build_index(chunks, tmp_path / "index" / "bm25")
    return tmp_path


def test_retriever_switch(bm25_dir):
    base = {"EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5", "DATA_DIR": str(bm25_dir)}
    assert isinstance(retriever_from_env({**base, "RETRIEVER": "dense"}), DenseRetriever)
    bm25 = retriever_from_env({**base, "RETRIEVER": "BM25"})
    assert isinstance(bm25, KeywordRetriever) and ids(bm25.search("bm25", k=1)) == ["a#0"]
    hybrid = retriever_from_env({**base, "RRF_K": "10"})  # empty RETRIEVER: hybrid
    assert isinstance(hybrid, HybridRetriever) and hybrid.config.rrf_k == 10
    assert isinstance(hybrid.dense, DenseRetriever)
    assert isinstance(hybrid.keyword, KeywordRetriever)
    with pytest.raises(ValueError, match="RETRIEVER"):
        retriever_from_env({**base, "RETRIEVER": "rerank"})
    with pytest.raises(ValueError, match="EMBEDDING_MODEL"):
        retriever_from_env({"DATA_DIR": str(bm25_dir), "RETRIEVER": "hybrid"})


def test_bm25_index_dir():
    assert bm25_index_dir({}).as_posix() == "data/index/bm25"
    assert bm25_index_dir({"DATA_DIR": "/d"}).as_posix() == "/d/index/bm25"
    assert bm25_index_dir({"BM25_INDEX_DIR": "/x", "DATA_DIR": "/d"}).as_posix() == "/x"


def test_agent_runs_with_the_hybrid_retriever():
    dense = Scripted([hit("a#0"), hit("b#0")])
    keyword = Scripted([hit("b#0"), hit("c#0")])
    llm = FakeLLM(["Answer [1].", "Next?"])
    agent = Agent(HybridRetriever(dense, keyword), llm, AgentConfig(top_k=2, min_score=0.0))
    sources = next(e for e in agent.run("s1", "q?") if isinstance(e, SourcesEvent))
    assert [c.chunk_id for c in sources.chunks] == ["b#0", "a#0"]
