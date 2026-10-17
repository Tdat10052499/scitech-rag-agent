import json
from pathlib import Path

import pytest

from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.embed import embed_chunks
from scitech_pipelines.load import LOAD_MANIFEST, LOAD_STATE, load_index, point_id

duckdb = pytest.importorskip("duckdb")
np = pytest.importorskip("numpy")
pytest.importorskip("pyarrow")
jsonschema = pytest.importorskip("jsonschema")

from test_chunk import SCHEMA, fixture_documents, write_documents  # noqa: E402
from test_embed import DIM, FakeEncoder, read_vectors  # noqa: E402

PART_SIZE = 4


class FakeStore:
    """In-memory store: points by id, like an upsert into Qdrant."""

    def __init__(self, collection: str = "test_chunks", fail_on_upsert: int = -1):
        self.collection = collection
        self.points: dict[str, tuple[list[float], dict]] = {}
        self.dimension: int | None = None
        self.upserts = 0
        self.fail_on_upsert = fail_on_upsert

    def ensure_collection(self, dimension: int) -> None:
        if self.dimension not in (None, dimension):
            raise ValueError("collection exists with another dimension")
        self.dimension = dimension

    def upsert(self, points) -> None:
        if self.upserts == self.fail_on_upsert:
            raise ConnectionError("Qdrant went away")
        self.upserts += 1
        for p in points:
            assert len(p.vector) == self.dimension
            self.points[p.id] = (p.vector, p.payload)

    def count(self) -> int:
        return len(self.points)


@pytest.fixture
def data(tmp_path: Path) -> tuple[Path, Path]:
    docs = write_documents(tmp_path / "documents", fixture_documents())
    chunks = tmp_path / "chunks"
    chunk_documents(docs, chunks, log=lambda _: None)
    vectors = tmp_path / "embeddings"
    embed_chunks(chunks, vectors, FakeEncoder(), part_size=PART_SIZE, log=lambda _: None)
    return chunks, vectors


def n_chunks(chunks: Path) -> int:
    return json.loads((chunks / "_chunk_manifest.json").read_text())["counts"]["chunks"]


def test_every_chunk_is_one_point_with_its_vector_and_payload(data, tmp_path: Path):
    chunks, vectors = data
    store = FakeStore()
    manifest = load_index(chunks, vectors, store, tmp_path / "index", batch_size=3, log=print)
    expected = read_vectors(vectors)
    assert store.count() == len(expected) == n_chunks(chunks) == manifest["counts"]["points"]
    assert store.dimension == DIM
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for chunk_id, (vector, model) in expected.items():
        stored_vector, payload = store.points[point_id(chunk_id)]
        assert stored_vector == pytest.approx(vector)
        assert payload["chunk_id"] == chunk_id
        assert payload["embedding_model"] == model == "fake/model-a"
        jsonschema.validate(payload, schema)  # no nulls, no extra fields
    assert manifest["index_snapshot"].startswith("test_chunks/model-a/")
    assert json.loads((tmp_path / "index" / LOAD_MANIFEST).read_text()) == manifest


def test_point_id_is_stable_and_unique():
    assert point_id("2404.00001#0") == point_id("2404.00001#0")
    assert point_id("2404.00001#0") != point_id("2404.00001#1")


def test_re_run_skips_finished_parts(data, tmp_path: Path):
    chunks, vectors = data
    store = FakeStore()
    load_index(chunks, vectors, store, tmp_path / "index", log=lambda _: None)
    upserts = store.upserts
    again = load_index(chunks, vectors, store, tmp_path / "index", log=lambda _: None)
    assert store.upserts == upserts
    assert again["counts"]["points_loaded_this_run"] == 0
    assert again["counts"]["parts_resumed"] == again["counts"]["parts"]


def test_interrupted_load_resumes_at_the_failed_part(data, tmp_path: Path):
    chunks, vectors = data
    store = FakeStore(fail_on_upsert=2)  # batch size = part size: fails in the third part
    with pytest.raises(ConnectionError):
        load_index(chunks, vectors, store, tmp_path / "index", batch_size=PART_SIZE)
    state = json.loads((tmp_path / "index" / LOAD_STATE).read_text())
    assert state["parts_done"] == ["part-00000.parquet", "part-00001.parquet"]
    store.fail_on_upsert = -1
    manifest = load_index(chunks, vectors, store, tmp_path / "index", batch_size=PART_SIZE)
    assert manifest["counts"]["parts_resumed"] == 2
    assert manifest["counts"]["points_loaded_this_run"] == n_chunks(chunks) - 2 * PART_SIZE
    assert store.count() == n_chunks(chunks)


def test_other_collection_needs_force(data, tmp_path: Path):
    chunks, vectors = data
    load_index(chunks, vectors, FakeStore(), tmp_path / "index", log=lambda _: None)
    other = FakeStore("other_chunks")
    with pytest.raises(ValueError, match="other settings"):
        load_index(chunks, vectors, other, tmp_path / "index", log=lambda _: None)
    load_index(chunks, vectors, other, tmp_path / "index", force=True, log=lambda _: None)
    assert other.count() == n_chunks(chunks)


def test_leftover_points_fail_the_count_check(data, tmp_path: Path):
    chunks, vectors = data
    store = FakeStore()
    store.ensure_collection(DIM)
    store.points["old"] = ([0.0] * DIM, {})
    with pytest.raises(RuntimeError, match="expected"):
        load_index(chunks, vectors, store, tmp_path / "index", log=lambda _: None)


def test_vectors_of_other_chunks_are_refused(data, tmp_path: Path):
    chunks, vectors = data
    manifest = json.loads((chunks / "_chunk_manifest.json").read_text())
    manifest["chunked_at"] = "2030-01-01T00:00:00+00:00"  # as after a new `chunk` run
    (chunks / "_chunk_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="other chunks"):
        load_index(chunks, vectors, FakeStore(), tmp_path / "index")


def test_partial_embedding_is_refused(data, tmp_path: Path):
    chunks, _ = data
    partial = tmp_path / "partial"
    embed_chunks(chunks, partial, FakeEncoder(), limit=3, log=lambda _: None)
    with pytest.raises(ValueError, match="one vector per chunk"):
        load_index(chunks, partial, FakeStore(), tmp_path / "index")


def test_unfinished_embedding_is_refused(data, tmp_path: Path):
    chunks, vectors = data
    (vectors / "_embed_manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        load_index(chunks, vectors, FakeStore(), tmp_path / "index")
