import json
from pathlib import Path

import pytest

from scitech_pipelines.chunk import chunk_documents
from scitech_pipelines.embed import embed_chunks
from scitech_pipelines.load import (
    LOAD_MANIFEST,
    LOAD_STATE,
    index_snapshot,
    load_index,
    point_id,
)

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
    assert manifest["index_snapshot"].startswith("test_chunks/model-a/chunked-")
    assert "/embedded-" in manifest["index_snapshot"]
    assert json.loads((tmp_path / "index" / LOAD_MANIFEST).read_text()) == manifest


def test_index_snapshot_tells_embed_runs_apart():
    chunked = "2026-10-17T05:19:12+00:00"
    first = index_snapshot("c", "BAAI/bge-small-en-v1.5", chunked, "2026-10-17T06:40:37+00:00")
    assert first == ("c/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37")
    # the same model on the same chunks, embedded again: another id
    assert first != index_snapshot("c", "BAAI/bge-small-en-v1.5", chunked, "2026-10-21T08:00:00")
    assert index_snapshot("c", "m", None, None) == "c/m/chunked-unknown/embedded-unknown"


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


class FakeQdrant:
    """The four Qdrant REST calls `QdrantStore` makes for a load, kept in memory. Bodies go
    through JSON, so a payload value Qdrant could not take (e.g. a numpy type) fails here."""

    def __init__(self):
        self.collections: dict[str, dict] = {}

    def __call__(self, request):
        import httpx

        parts = request.url.path.strip("/").split("/")  # collections/<name>[/...]
        name, rest = parts[1], parts[2:]
        body = json.loads(request.content) if request.content else None
        if request.method == "GET" and not rest:
            if name not in self.collections:
                return httpx.Response(404, json={"status": {"error": "not found"}})
            config = {"params": {"vectors": self.collections[name]["vectors"]}}
            return httpx.Response(200, json={"result": {"config": config}})
        if request.method == "PUT" and not rest:
            self.collections[name] = {"vectors": body["vectors"], "points": {}, "indexes": {}}
        elif request.method == "PUT" and rest == ["index"]:
            self.collections[name]["indexes"][body["field_name"]] = body["field_schema"]
        elif request.method == "PUT" and rest == ["points"]:
            for point in body["points"]:
                self.collections[name]["points"][point["id"]] = point
        elif request.method == "POST" and rest == ["points", "count"]:
            count = len(self.collections[name]["points"])
            return httpx.Response(200, json={"result": {"count": count}})
        else:
            return httpx.Response(400, json={"status": {"error": f"unexpected {request.url}"}})
        return httpx.Response(200, json={"result": True})


def test_load_into_the_qdrant_store(data, tmp_path: Path):
    httpx = pytest.importorskip("httpx")
    from scitech_agent.store import PAYLOAD_INDEXES, QdrantStore, StoreConfig

    chunks, vectors = data
    qdrant = FakeQdrant()
    config = StoreConfig(collection="test_chunks")
    with QdrantStore(config, transport=httpx.MockTransport(qdrant)) as store:
        manifest = load_index(chunks, vectors, store, tmp_path / "index", log=lambda _: None)
    collection = qdrant.collections["test_chunks"]
    assert collection["vectors"] == {"size": DIM, "distance": "Cosine"}
    assert collection["indexes"] == PAYLOAD_INDEXES
    expected = read_vectors(vectors)
    assert manifest["counts"]["points"] == len(collection["points"]) == len(expected)
    for chunk_id, (vector, _) in expected.items():
        point = collection["points"][point_id(chunk_id)]
        assert point["vector"] == pytest.approx(vector)
        assert point["payload"]["chunk_id"] == chunk_id


def test_load_command_uses_the_store_settings(data, tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    import scitech_agent.store
    from scitech_pipelines.cli import main

    chunks, vectors = data
    opened = []

    class Store(FakeStore):
        def __init__(self, config):
            super().__init__(config.collection)
            self.config = config
            opened.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True

    monkeypatch.setattr(scitech_agent.store, "QdrantStore", Store)
    monkeypatch.setenv("QDRANT_URL", "http://qdrant.test:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "from_env")
    args = ["load", "--chunks", str(chunks), "--vectors", str(vectors)]
    assert main(["--data-dir", str(tmp_path), *args, "--collection", "eval_chunks"]) == 0
    store = opened[0]
    assert (store.config.url, store.collection) == ("http://qdrant.test:6333", "eval_chunks")
    assert store.count() == n_chunks(chunks) and store.closed
    manifest = json.loads((tmp_path / "processed" / "index" / LOAD_MANIFEST).read_text())
    assert manifest["index_snapshot"].startswith("eval_chunks/")

    assert main(["--data-dir", str(tmp_path / "other"), *args]) == 0
    assert opened[1].collection == "from_env"
