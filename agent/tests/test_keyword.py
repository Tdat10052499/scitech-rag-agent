"""Tests of the BM25 keyword retriever (W3-D3-DAT-1) on a toy corpus."""

from __future__ import annotations

import json
import math
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scitech_agent.agent import Agent, AgentConfig
from scitech_agent.events import SourcesEvent
from scitech_agent.llm import FakeLLM
from scitech_agent.retrieval import Retriever
from scitech_agent.retrieval.keyword import (
    MANIFEST,
    BM25Index,
    BM25Params,
    KeywordRetriever,
    build_index,
    index_chunks,
    main,
    tokenize,
)


def chunk(doc, index, text, categories=(), published_at="2024-01-01", source="arxiv"):
    return {
        "chunk_id": f"{doc}#{index}",
        "doc_id": doc,
        "source": source,
        "title": text.split(".")[0],
        "text": text,
        "chunk_index": index,
        "authors": ["A. Author"],
        "categories": list(categories),
        "published_at": published_at,
        "url": f"https://arxiv.org/abs/{doc}",
        "license": "CC0-1.0",
    }


CHUNKS = [
    chunk(
        "a",
        0,
        "Dense retrieval. Dense passage retrieval with dual encoders.",
        ["cs.CL", "cs.IR"],
        "2020-04-10",
    ),
    chunk(
        "b",
        0,
        "BM25 baselines. Keyword search with BM25 is a strong retrieval baseline.",
        ["cs.IR"],
        "2021-06-01",
    ),
    chunk(
        "b",
        1,
        "BM25 baselines. The baseline beats several neural rankers on BEIR.",
        ["cs.IR"],
        "2021-06-01",
    ),
    chunk(
        "c",
        0,
        "Speech recognition. End-to-end speech recognition with transformers.",
        ["cs.CL", "eess.AS"],
        "2023-02-15",
    ),
    chunk(
        "w",
        0,
        "Question answering. Question answering is a task in language processing.",
        (),
        "2024-01-01",
        "wikipedia",
    ),
]


def reference_scores(chunks, query, k1=1.2, b=0.75):
    """Okapi BM25 written out term by term, to check the vectorised index."""
    docs = [tokenize(c["text"]) for c in chunks]
    n, avgdl = len(docs), sum(map(len, docs)) / len(docs)
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in tokenize(query):
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    return scores


@pytest.fixture(scope="module")
def index() -> BM25Index:
    return index_chunks(CHUNKS)


def test_tokenize_lowercases_and_drops_stop_words():
    assert tokenize("The BM25 baseline, and GPT-4!") == ["bm25", "baseline", "gpt", "4"]
    assert tokenize("The model", stop_words=None) == ["the", "model"]


@pytest.mark.parametrize("query", ["BM25 retrieval baseline", "speech transformers", "dense dense"])
def test_scores_match_the_bm25_formula(index, query):
    assert index.scores(query).tolist() == pytest.approx(reference_scores(CHUNKS, query), rel=1e-5)


def test_search_ranks_best_first_and_skips_chunks_without_query_words(index):
    hits = index.search("BM25 retrieval baseline", k=10)
    assert [h.chunk_id for h in hits][:2] == ["b#0", "b#1"]
    assert {h.chunk_id for h in hits} == {"a#0", "b#0", "b#1"}
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert index.search("BM25 retrieval baseline", k=1)[0].chunk_id == "b#0"
    assert index.search("photosynthesis", k=5) == []
    assert index.search("the and of", k=5) == []  # stop words only


def test_hits_carry_the_chunk_fields(index):
    hit = index.search("speech", k=1)[0]
    assert (hit.chunk_id, hit.doc_id, hit.chunk_index, hit.source) == ("c#0", "c", 0, "arxiv")
    assert hit.categories == ("cs.CL", "eess.AS")
    assert (hit.published_at, hit.license) == ("2023-02-15", "CC0-1.0")
    assert hit.url == "https://arxiv.org/abs/c"


def test_filters_follow_the_retriever_rules(index):
    def ids(filters, query="retrieval baseline speech question"):
        return {h.chunk_id for h in index.search(query, k=10, filters=filters)}

    assert ids({"categories": "cs.CL"}) == {"a#0", "c#0"}
    assert ids({"source": "wikipedia"}) == {"w#0"}
    assert ids({"published_at": {"gte": "2021-01-01", "lt": "2024-01-01"}}) == {"b#0", "b#1", "c#0"}
    hits = index.search("retrieval baseline", k=1, filters={"doc_id": "a"})
    assert [h.chunk_id for h in hits] == ["a#0"]  # k counts filtered hits only


def test_bad_k_and_empty_corpus_are_refused(index):
    with pytest.raises(ValueError):
        index.search("bm25", k=0)
    with pytest.raises(ValueError):
        index_chunks([])


def test_stop_words_can_be_kept():
    kept = index_chunks(CHUNKS, BM25Params(stop_words=False))
    assert "the" in kept.vocabulary
    assert kept.search("the", k=1)


def write_chunks(path, chunks):
    path.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(chunks), path / "chunks.parquet")
    (path / "_chunk_manifest.json").write_text(json.dumps({"chunked_at": "2026-10-16T19:20:01"}))


def test_build_saves_and_load_gives_the_same_results(tmp_path, index):
    write_chunks(tmp_path / "chunks", CHUNKS)
    manifest = build_index(tmp_path / "chunks", tmp_path / "bm25")
    assert manifest["counts"]["chunks"] == len(CHUNKS)
    assert manifest["chunked_at"] == "2026-10-16T19:20:01"
    assert manifest["build_seconds"] >= 0 and manifest["peak_traced_mb"] is None
    traced = build_index(tmp_path / "chunks", tmp_path / "bm25-traced", trace_memory=True)
    assert traced["traced"] and traced["peak_traced_mb"] is not None
    on_disk = json.loads((tmp_path / "bm25" / MANIFEST).read_text())
    assert on_disk["params"] == {"k1": 1.2, "b": 0.75, "stop_words": True}
    assert on_disk["index_mb"] >= 0

    retriever: Retriever = KeywordRetriever.load(tmp_path / "bm25")
    for query in ("BM25 retrieval baseline", "speech", "question answering"):
        assert retriever.search(query, k=5) == index.search(query, k=5)


def test_load_without_an_index_fails(tmp_path):
    with pytest.raises(FileNotFoundError, match="build the index"):
        KeywordRetriever.load(tmp_path)
    with pytest.raises(FileNotFoundError, match="run `chunk` first"):
        build_index(tmp_path, tmp_path / "bm25")


def test_cli_build_and_search(tmp_path, capsys):
    write_chunks(tmp_path / "chunks", CHUNKS)
    out = tmp_path / "bm25"
    assert main(["build", "--chunks", str(tmp_path / "chunks"), "--out", str(out)]) == 0
    assert "5 chunks" in capsys.readouterr().out
    args = ["search", "--index", str(out), "-k", "2", "--filters", '{"source": "arxiv"}']
    assert main([*args, "BM25 baseline"]) == 0
    printed = capsys.readouterr().out
    assert "b#0" in printed and "w#0" not in printed


def test_agent_runs_with_the_keyword_retriever(index):
    llm = FakeLLM(["BM25 is a strong baseline [1].", "What is BEIR?"])
    agent = Agent(KeywordRetriever(index), llm, AgentConfig(top_k=2, min_score=0.0))
    events = list(agent.run("s1", "Is BM25 a strong retrieval baseline?"))
    sources = next(e for e in events if isinstance(e, SourcesEvent))
    assert [c.chunk_id for c in sources.chunks] == ["b#0", "b#1"]
