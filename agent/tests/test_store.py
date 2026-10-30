"""Unit tests of the Qdrant store (W3-D1-DAT-1) against `httpx.MockTransport`; no Qdrant needed.
The same calls against a real Qdrant are in `test_store_integration.py`."""

from __future__ import annotations

import json

import httpx
import pytest

from scitech_agent.retrieval import RetrievalError, ScoredChunk
from scitech_agent.store import (
    PAYLOAD_INDEXES,
    Point,
    QdrantStore,
    StoreConfig,
    StoreError,
    to_qdrant_filter,
    to_scored_chunk,
)

PAYLOAD = {
    "chunk_id": "2401.00001#0",
    "doc_id": "2401.00001",
    "source": "arxiv",
    "title": "Dense retrieval",
    "text": "Dense passage retrieval for open-domain QA.",
    "chunk_index": 0,
    "categories": ["cs.CL", "cs.IR"],
    "published_at": "2024-01-02",
    "url": "https://arxiv.org/abs/2401.00001",
    "license": "CC0-1.0",
    "embedding_model": "BAAI/bge-small-en-v1.5",
}


class FakeQdrant:
    """Records requests and answers them like Qdrant's REST API does."""

    def __init__(self, collection: dict | None = None, status: int = 200) -> None:
        self.collection = collection  # GET /collections/<name> result, None: missing
        self.status = status
        self.requests: list[tuple[str, str, dict | None]] = []
        self.query_points: list[dict] = []
        self.count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        self.requests.append((request.method, path, body))
        if self.status != 200:
            return httpx.Response(self.status, text="boom")
        if request.method == "GET":
            if self.collection is None:
                return httpx.Response(404, json={"status": {"error": "Not found"}})
            return httpx.Response(200, json={"result": self.collection})
        if path.endswith("/points/count"):
            return httpx.Response(200, json={"result": {"count": self.count}})
        if path.endswith("/points/query"):
            return httpx.Response(200, json={"result": {"points": self.query_points}})
        return httpx.Response(200, json={"result": True, "status": "ok"})


def make_store(fake: FakeQdrant) -> QdrantStore:
    config = StoreConfig(url="http://qdrant.test:6333", collection="test_chunks")
    return QdrantStore(config, transport=httpx.MockTransport(fake))


def existing(size: int, distance: str = "Cosine") -> dict:
    return {"config": {"params": {"vectors": {"size": size, "distance": distance}}}}


def test_config_from_env_and_defaults():
    config = StoreConfig.from_env({"QDRANT_URL": "http://q:6333/", "QDRANT_COLLECTION": "c"})
    assert (config.url, config.collection) == ("http://q:6333", "c")
    assert StoreConfig.from_env({"QDRANT_URL": "", "QDRANT_COLLECTION": ""}) == StoreConfig()


def test_ensure_collection_creates_it_with_cosine_and_payload_indexes():
    fake = FakeQdrant(collection=None)
    with make_store(fake) as store:
        assert store.ensure_collection(384) is True
    method, path, body = fake.requests[1]
    assert (method, path) == ("PUT", "/collections/test_chunks")
    assert body == {"vectors": {"size": 384, "distance": "Cosine"}}
    indexes = {b["field_name"]: b["field_schema"] for _, p, b in fake.requests[2:]}
    assert indexes == PAYLOAD_INDEXES
    assert indexes["published_at"] == "datetime"
    assert {"source", "categories", "published_at"} <= set(indexes)


def test_ensure_collection_keeps_a_matching_collection():
    fake = FakeQdrant(collection=existing(384))
    assert make_store(fake).ensure_collection(384) is False
    assert not any(m == "PUT" and p == "/collections/test_chunks" for m, p, _ in fake.requests)
    assert len(fake.requests) == 1 + len(PAYLOAD_INDEXES)  # indexes are still made sure of


@pytest.mark.parametrize("collection", [existing(768), existing(384, "Dot")])
def test_ensure_collection_refuses_another_dimension_or_distance(collection):
    with pytest.raises(StoreError, match="expected 384"):
        make_store(FakeQdrant(collection=collection)).ensure_collection(384)


def test_ensure_collection_rejects_a_bad_dimension():
    with pytest.raises(ValueError):
        make_store(FakeQdrant()).ensure_collection(0)


def test_upsert_sends_batches_and_plain_floats():
    fake = FakeQdrant()
    points = [Point(i, (0.5, 1), {"chunk_id": f"d#{i}"}) for i in range(5)]
    assert make_store(fake).upsert(iter(points), batch_size=2) == 5
    sent = [b for m, p, b in fake.requests if p == "/collections/test_chunks/points?wait=true"]
    assert [len(b["points"]) for b in sent] == [2, 2, 1]
    assert sent[0]["points"][0] == {"id": 0, "vector": [0.5, 1.0], "payload": {"chunk_id": "d#0"}}


def test_upsert_of_nothing_sends_nothing_and_rejects_a_bad_batch_size():
    fake = FakeQdrant()
    store = make_store(fake)
    assert store.upsert([]) == 0
    assert fake.requests == []
    with pytest.raises(ValueError):
        store.upsert([Point(1, [0.0])], batch_size=0)


def test_count_is_exact_and_takes_filters():
    fake = FakeQdrant()
    fake.count = 7
    assert make_store(fake).count({"source": "arxiv"}) == 7
    _, path, body = fake.requests[0]
    assert path == "/collections/test_chunks/points/count"
    must = [{"key": "source", "match": {"value": "arxiv"}}]
    assert body == {"exact": True, "filter": {"must": must}}


def test_search_maps_payload_to_scored_chunks_in_order():
    fake = FakeQdrant()
    other = dict(PAYLOAD, chunk_id="2401.00002#1", doc_id="2401.00002", chunk_index=1)
    del other["url"], other["categories"]
    fake.query_points = [
        {"id": "a", "score": 0.91, "payload": PAYLOAD},
        {"id": "b", "score": 0.5, "payload": other},
    ]
    hits = make_store(fake).search([0.1, 0.2], k=2, filters={"categories": "cs.IR"})
    assert [h.chunk_id for h in hits] == ["2401.00001#0", "2401.00002#1"]
    assert hits[0] == ScoredChunk(
        chunk_id="2401.00001#0",
        doc_id="2401.00001",
        score=0.91,
        title="Dense retrieval",
        text="Dense passage retrieval for open-domain QA.",
        source="arxiv",
        chunk_index=0,
        url="https://arxiv.org/abs/2401.00001",
        published_at="2024-01-02",
        categories=("cs.CL", "cs.IR"),
        license="CC0-1.0",
    )
    assert hits[1].url is None and hits[1].categories == ()
    _, path, body = fake.requests[0]
    assert path == "/collections/test_chunks/points/query"
    assert body == {
        "query": [0.1, 0.2],
        "limit": 2,
        "with_payload": True,
        "filter": {"must": [{"key": "categories", "match": {"value": "cs.IR"}}]},
        "params": {"exact": True},
    }


def test_search_without_filters_sends_no_filter_and_rejects_bad_k():
    fake = FakeQdrant()
    store = make_store(fake)
    assert store.search([1.0], k=3) == []
    assert "filter" not in fake.requests[0][2]
    with pytest.raises(ValueError):
        store.search([1.0], k=0)


def test_search_is_exact_by_default_and_uses_hnsw_when_exact_is_off():
    fake = FakeQdrant()
    make_store(fake).search([1.0], k=1)
    assert fake.requests[0][2]["params"] == {"exact": True}

    fake = FakeQdrant()
    config = StoreConfig(url="http://qdrant.test:6333", collection="test_chunks", exact=False)
    QdrantStore(config, transport=httpx.MockTransport(fake)).search([1.0], k=1)
    assert "params" not in fake.requests[0][2]


def test_requests_ask_qdrant_not_to_compress():
    seen: list[str | None] = []

    def fake(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Accept-Encoding"))
        return httpx.Response(200, json={"result": {"points": []}})

    config = StoreConfig(url="http://qdrant.test:6333", collection="test_chunks")
    QdrantStore(config, transport=httpx.MockTransport(fake)).search([1.0], k=1)
    assert seen == ["identity"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, True),
        ("", True),
        ("  ", True),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        (" off ", False),
    ],
)
def test_search_exact_setting_from_env(raw, expected):
    env = {} if raw is None else {"QDRANT_SEARCH_EXACT": raw}
    assert StoreConfig.from_env(env).exact is expected


@pytest.mark.parametrize("raw", ["maybe", "ture", "2", "exact"])
def test_search_exact_setting_rejects_other_values(raw):
    with pytest.raises(ValueError, match="QDRANT_SEARCH_EXACT"):
        StoreConfig.from_env({"QDRANT_SEARCH_EXACT": raw})


def test_payload_without_a_required_field_is_an_error():
    payload = dict(PAYLOAD)
    del payload["source"]
    with pytest.raises(StoreError, match="source"):
        to_scored_chunk(payload, 0.3)


def test_filters_translate_to_match_and_range():
    assert to_qdrant_filter(None) is None
    assert to_qdrant_filter({}) is None
    assert to_qdrant_filter(
        {"source": "arxiv", "published_at": {"gte": "2023-01-01", "lt": "2024-01-01"}}
    ) == {
        "must": [
            {"key": "source", "match": {"value": "arxiv"}},
            {"key": "published_at", "range": {"gte": "2023-01-01", "lt": "2024-01-01"}},
        ]
    }
    for bad in ({"published_at": {"after": "2023"}}, {"published_at": {}}, {"x": None}):
        with pytest.raises(ValueError):
            to_qdrant_filter(bad)


def test_http_errors_and_connection_errors_are_retrieval_errors():
    with pytest.raises(StoreError, match="HTTP 500"):
        make_store(FakeQdrant(status=500)).count()

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    store = QdrantStore(StoreConfig(), transport=httpx.MockTransport(refuse))
    with pytest.raises(RetrievalError) as info:
        store.search([1.0], k=1)
    assert info.value.code == "retrieval_failed"
