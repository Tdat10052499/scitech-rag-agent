import importlib.util
import json
from pathlib import Path

import pytest

from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.embed import embed_chunks

np = pytest.importorskip("numpy")
pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")
pytest.importorskip("yaml")

from test_chunk import fixture_documents, write_documents  # noqa: E402
from test_embed import FakeEncoder, chunk_texts  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_embeddings.py"
spec = importlib.util.spec_from_file_location("compare_embeddings", SCRIPT)
compare_embeddings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_embeddings)


class FakeModel:
    """Query side of FakeEncoder: a query equal to a chunk's text gets that chunk's vector."""

    max_seq_length = 40

    def __init__(self, name: str):
        self._encoder = FakeEncoder(name)

    def encode(self, texts):
        return self._encoder.encode(texts)

    def tokenize(self, texts):
        return [[0] + [1] * len(t.split()) + [0] for t in texts]


@pytest.fixture
def setup(tmp_path: Path):
    docs = write_documents(tmp_path / "documents", fixture_documents())
    chunks = tmp_path / "chunks"
    chunk_documents(docs, chunks, log=lambda _: None)
    vectors = tmp_path / "emb"
    embed_chunks(chunks, vectors, FakeEncoder("fake/model-a"), part_size=7, log=lambda _: None)
    texts = sorted(chunk_texts(chunks).items())
    items = []
    for n, (chunk_id, text) in enumerate(texts[:3], start=1):
        items.append(
            {
                "id": f"gs-{n:03d}",
                "question": text,
                "type": "factual",
                "relevant_doc_ids": [chunk_id.split("#")[0]],
                "reference_answer": "x",
                "notes": "plain. test",
                "author": "FAO",
                "split": "dev",
            }
        )
    items.append(
        {
            "id": "gs-u01",
            "question": "Nothing in the corpus?",
            "type": "unanswerable",
            "relevant_doc_ids": [],
            "reference_answer": "x",
            "notes": "plain. test",
            "author": "FAO",
            "split": "dev",
        }
    )
    golden = tmp_path / "golden.jsonl"
    golden.write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    return chunks, vectors, golden, texts


def test_rank_orders_by_dot_product():
    matrix = np.array([[1, 0], [0.6, 0.8], [0, 1]], np.float32)
    doc_of = {"a#0": "a", "b#0": "b", "c#0": "c"}
    ranked = compare_embeddings.rank(
        np.array([[0, 1]], np.float32), matrix, ["a#0", "b#0", "c#0"], doc_of, depth=2
    )
    assert [h["chunk_id"] for h in ranked[0]] == ["c#0", "b#0"]
    assert ranked[0][0]["doc_id"] == "c"


def test_count_over_limit():
    tokens = compare_embeddings.count_over_limit(
        lambda texts: [[0] * len(t) for t in texts],
        ["aa", "aaaa", "aaaaa"],
        ["d1", "d1", "d2"],
        limit=3,
        batch_size=2,
    )
    assert tokens["chunks_over"] == 2
    assert tokens["documents_over"] == 2
    assert tokens["tokens_max"] == 5


def test_compare_scores_every_condition(setup, tmp_path: Path, monkeypatch):
    chunks, vectors, golden, texts = setup
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    summary = compare_embeddings.compare(
        [vectors], chunks, golden, "query: ", out, FakeModel, log=lambda _: None
    )
    [model] = summary["models"]
    assert model["model"] == "fake/model-a"
    assert set(model["conditions"]) == {"query-prefix", "no-prefix"}
    no_prefix = model["conditions"]["no-prefix"]["question"]
    # Without a prefix each question is a chunk's text, so the fake vectors match exactly.
    assert no_prefix["n"] == 3
    assert no_prefix["metrics"]["recall@1"]["mean"] == 1.0
    assert no_prefix["metrics"]["mrr"]["mean"] == 1.0
    assert model["tokens"]["chunks"] == len(texts)
    assert model["tokens"]["max_seq_length"] == 40
    assert (out / "summary.md").read_text(encoding="utf-8").count("`fake/model-a`") == 3
    assert len(list((out / "runs").glob("*.json"))) == 4
    config = (out / "configs" / "adr0007-model-a-query-prefix-question.yaml").read_text("utf-8")
    assert "retriever_type: dense" in config
    assert "embedding_model: fake/model-a" in config


def test_compare_refuses_vectors_of_other_chunks(setup, tmp_path: Path):
    chunks, vectors, golden, _ = setup
    other = tmp_path / "partial"
    embed_chunks(chunks, other, FakeEncoder(), limit=3, log=lambda _: None)
    with pytest.raises(ValueError, match="no vector"):
        compare_embeddings.compare(
            [other], chunks, golden, "", tmp_path / "out", FakeModel, log=lambda _: None
        )
