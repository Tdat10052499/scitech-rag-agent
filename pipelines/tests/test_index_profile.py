import argparse
import importlib.util
import json
from pathlib import Path

import pytest

from scitech_agent.retrieval import InMemoryRetriever, ScoredChunk

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "index_profile.py"
spec = importlib.util.spec_from_file_location("index_profile", SCRIPT)
index_profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(index_profile)


def chunk(n: int, categories: tuple[str, ...], published_at: str) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=f"2301.{n:05d}#0",
        doc_id=f"2301.{n:05d}",
        score=0.0,
        title=f"Paper {n} on language models",
        text=f"Abstract {n} about language models and retrieval.",
        source="arxiv",
        chunk_index=0,
        published_at=published_at,
        categories=categories,
    )


CHUNKS = [
    chunk(1, ("cs.CL",), "2022-05-01"),
    chunk(2, ("cs.CL", "cs.LG"), "2023-02-10"),
    chunk(3, ("cs.CL", "cs.LG"), "2023-11-30"),
    chunk(4, ("cs.CL",), "2024-01-15"),
]


def fake_retriever() -> InMemoryRetriever:
    """Factory for the command line tests: `test_index_profile:fake_retriever`."""
    return InMemoryRetriever(CHUNKS)


class IgnoresFilters(InMemoryRetriever):
    """A broken retriever: drops the filters it is given."""

    def search(self, query, k, filters=None):
        return super().search(query, k, None)


class FakeClock:
    """Each search takes 1 ms longer than the one before (1, 2, 3, ... ms)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        if self.calls % 2 == 0:  # end of a search
            self.now += self.calls / 2 / 1000
        return self.now


def test_percentile_is_nearest_rank():
    values = list(range(1, 101))
    assert index_profile.percentile(values, 50) == 50
    assert index_profile.percentile(values, 95) == 95
    assert index_profile.percentile([7.0], 95) == 7.0
    assert index_profile.percentile([3, 1, 2], 50) == 2
    with pytest.raises(ValueError):
        index_profile.percentile([], 50)


def test_build_queries_golden_first_then_titles_without_repeats():
    golden = ["q1", "q2", "q1"]
    titles = ["t1", "t2", "t3", "q2", "t4"]
    queries = index_profile.build_queries(golden, titles, 4)
    assert queries[:2] == ["q1", "q2"]
    assert len(queries) == 4 and len(set(queries)) == 4
    assert index_profile.build_queries(golden, titles, 4) == queries  # fixed seed
    everything = index_profile.build_queries(golden, titles, 100)
    assert everything[:2] == ["q1", "q2"]
    assert sorted(everything[2:]) == ["t1", "t2", "t3", "t4"]


def test_build_queries_stops_at_the_pool_size():
    queries = index_profile.build_queries(["q1"], ["t1", "t2"], 100)
    assert sorted(queries) == ["q1", "t1", "t2"]


def test_golden_queries_include_standalone_queries(tmp_path):
    path = tmp_path / "golden.jsonl"
    items = [
        {"id": "gs-001", "question": "What is RAG?"},
        {"id": "gs-002", "question": "And that one?", "standalone_query": "What is BM25?"},
    ]
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    assert index_profile.golden_queries(path) == ["What is RAG?", "And that one?", "What is BM25?"]


def test_time_queries_warms_up_then_times_every_query():
    retriever = fake_retriever()
    seconds, hits = index_profile.time_queries(
        retriever.search, ["language", "models", "nothing"], 2, warmup=2, clock=FakeClock()
    )
    assert len(retriever.calls) == 2 + 3
    assert seconds == pytest.approx([0.001, 0.002, 0.003])
    assert hits == [2, 2, 0]
    summary = index_profile.summarise(seconds)
    assert summary == {"n": 3, "p50_ms": 2.0, "p95_ms": 3.0, "mean_ms": 2.0, "max_ms": 3.0}


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"categories": "cs.LG"}, True),
        ({"categories": "cs.CV"}, False),
        ({"published_at": {"gte": "2023-01-01", "lte": "2023-12-31"}}, True),
        ({"published_at": {"gte": "2024-01-01"}}, False),
        ({"source": "arxiv", "categories": "cs.CL"}, True),
        ({"source": "wikipedia"}, False),
    ],
)
def test_satisfies(filters, expected):
    assert index_profile.satisfies(CHUNKS[1], filters) is expected


def test_check_filter_passes_a_filtering_retriever_and_catches_one_that_ignores_filters():
    queries = ["language models", "retrieval"]
    good = index_profile.check_filter(fake_retriever().search, queries, 10, {"categories": "cs.LG"})
    assert good["ok"] and good["hits"] == 4 and good["violations"] == 0

    bad = index_profile.check_filter(
        IgnoresFilters(CHUNKS).search, queries, 10, {"categories": "cs.LG"}
    )
    assert not bad["ok"] and bad["violations"] == 4
    assert bad["violation_examples"] == ["2301.00001#0", "2301.00004#0", "2301.00001#0"]

    none = index_profile.check_filter(fake_retriever().search, queries, 10, {"source": "openalex"})
    assert not none["ok"] and none["hits"] == 0 and none["queries_without_hits"] == 2


def test_parse_retriever():
    assert index_profile.parse_retriever("dense=pkg.mod:make") == ("dense", "pkg.mod:make", {})
    assert index_profile.parse_retriever('bm25=pkg.mod:make {"path": "x"}') == (
        "bm25",
        "pkg.mod:make",
        {"path": "x"},
    )
    for bad in ("pkg.mod:make", "dense=pkg.mod:make {not json}", "dense=pkg.mod:make [1]"):
        with pytest.raises(argparse.ArgumentTypeError):
            index_profile.parse_retriever(bad)


def test_command_line_end_to_end(tmp_path, capsys):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "gs-001", "question": "language models"}) + "\n")
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    pq.write_table(pa.table({"title": [c.title for c in CHUNKS]}), chunks / "chunks.parquet")
    bm25 = tmp_path / "bm25"
    bm25.mkdir()
    (bm25 / "index.bin").write_bytes(b"x" * 2048)
    out = tmp_path / "profile.json"

    code = index_profile.main(
        [
            "--retriever", "fake=test_index_profile:fake_retriever",
            "--golden", str(golden), "--chunks", str(chunks), "--n-queries", "5",
            "--k", "3", "--warmup", "1",
            "--filter", '{"categories": "cs.LG"}',
            "--size", f"bm25={bm25}", "--size", f"missing={tmp_path / 'nope'}",
            "--out", str(out),
        ]
    )  # fmt: skip

    assert code == 0
    profile = json.loads(out.read_text())
    assert profile["queries"] == {"n": 5, "golden": 1, "seed": 0}
    assert profile["latency"]["fake"]["n"] == 5
    assert profile["latency"]["fake"]["queries_without_hits"] == 0
    assert profile["filters"]["fake"][0]["ok"] is True
    assert profile["sizes"] == {"bm25": 2048}
    assert profile["qdrant"] is None and profile["docker"] is None
    assert any("missing" in p for p in profile["problems"])
    printed = capsys.readouterr().out
    assert "| fake |" in printed and "| bm25 on disk | 0.0 MiB |" in printed


def test_command_line_fails_when_a_filter_is_broken(tmp_path):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({"id": "gs-001", "question": "language models"}) + "\n")
    pq.write_table(pa.table({"title": ["Paper 1"]}), tmp_path / "chunks.parquet")
    code = index_profile.main(
        [
            "--retriever", "fake=test_index_profile:broken_retriever",
            "--golden", str(golden), "--chunks", str(tmp_path / "chunks.parquet"),
            "--filter", '{"categories": "cs.LG"}', "--warmup", "0",
        ]
    )  # fmt: skip
    assert code == 1


def broken_retriever() -> IgnoresFilters:
    return IgnoresFilters(CHUNKS)


def test_qdrant_collection_reads_the_rest_api(monkeypatch):
    body = {
        "result": {
            "status": "green",
            "points_count": 121926,
            "indexed_vectors_count": 121926,
            "segments_count": 8,
            "config": {"params": {"vectors": {"size": 384, "distance": "Cosine"}}},
            "payload_schema": {"source": {}, "published_at": {}, "categories": {}},
        }
    }
    opened = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *args):
            return json.dumps(body).encode()

    def urlopen(url, timeout):
        opened.append(url)
        return Response()

    monkeypatch.setattr(index_profile.urllib.request, "urlopen", urlopen)
    info = index_profile.qdrant_collection("http://localhost:6333/", "scitech")
    assert opened == ["http://localhost:6333/collections/scitech"]
    assert info == {
        "status": "green",
        "points_count": 121926,
        "indexed_vectors_count": 121926,
        "segments_count": 8,
        "vectors": {"size": 384, "distance": "Cosine"},
        "payload_indexes": ["categories", "published_at", "source"],
    }


def test_docker_qdrant_measures_disk_and_memory(monkeypatch):
    outputs = {
        ("docker", "compose", "ps", "-q", "qdrant"): "abc123\n",
        ("docker", "exec", "abc123", "du", "-sb", "/qdrant/storage/collections/scitech"): (
            "209715200\t/qdrant/storage/collections/scitech\n"
        ),
        (
            "docker",
            "exec",
            "abc123",
            "du",
            "-sb",
            "/qdrant/storage",
        ): "220000000\t/qdrant/storage\n",
        ("docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", "abc123"): (
            "412.3MiB / 7.6GiB\n"
        ),
        ("docker", "inspect", "--format", "{{.Config.Image}}", "abc123"): "qdrant/qdrant:v1.12.4\n",
    }
    monkeypatch.setattr(index_profile, "_run", lambda cmd: outputs[tuple(cmd)])
    assert index_profile.docker_qdrant("scitech") == {
        "collection_bytes": 209715200,
        "storage_bytes": 220000000,
        "memory_usage": "412.3MiB / 7.6GiB",
        "image": "qdrant/qdrant:v1.12.4",
    }

    monkeypatch.setattr(index_profile, "_run", lambda cmd: "")
    with pytest.raises(RuntimeError, match="not running"):
        index_profile.docker_qdrant("scitech")
