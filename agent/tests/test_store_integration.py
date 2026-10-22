"""Integration test of the Qdrant store (W3-D1-DAT-1) against a real Qdrant.

Runs only when Qdrant answers at `QDRANT_URL` (default http://localhost:6333), e.g. after
`make up`; otherwise it is skipped, as in CI. It works in a throw-away collection that it deletes
at the end, so it never touches `QDRANT_COLLECTION`. Run it alone with:
    python -m pytest -m integration agent/tests/test_store_integration.py
"""

from __future__ import annotations

import math
import os
import uuid

import httpx
import pytest

from scitech_agent.store import Point, QdrantStore, StoreConfig, StoreError

pytestmark = pytest.mark.integration

URL = (os.environ.get("QDRANT_URL") or "http://localhost:6333").rstrip("/")


def _reachable(url: str) -> bool:
    try:
        return httpx.get(f"{url}/healthz", timeout=2.0).is_success
    except httpx.HTTPError:
        return False


if not _reachable(URL):
    pytest.skip(f"Qdrant is not reachable at {URL}", allow_module_level=True)


def unit(*values: float) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def chunk(doc: str, index: int, categories: list[str], published_at: str, source="arxiv"):
    payload = {
        "chunk_id": f"{doc}#{index}",
        "doc_id": doc,
        "source": source,
        "title": f"Paper {doc}",
        "text": f"Text of {doc} part {index}.",
        "chunk_index": index,
        "categories": categories,
        "published_at": published_at,
    }
    return payload


@pytest.fixture
def store():
    config = StoreConfig(url=URL, collection=f"test_store_{uuid.uuid4().hex[:12]}")
    with QdrantStore(config) as s:
        yield s
        s.delete_collection()


def test_create_upsert_count_search_with_filters(store):
    assert store.ensure_collection(3) is True
    assert store.ensure_collection(3) is False  # second call: kept, indexes already there
    points = [
        Point(str(uuid.uuid4()), unit(1, 0, 0), chunk("a", 0, ["cs.CL"], "2022-05-01")),
        Point(str(uuid.uuid4()), unit(1, 0.2, 0), chunk("b", 0, ["cs.CL", "cs.IR"], "2023-03-15")),
        Point(str(uuid.uuid4()), unit(0, 1, 0), chunk("c", 0, ["cs.LG"], "2024-07-30")),
        Point(7, unit(0.9, 0, 0.4), chunk("w", 0, [], "2023-12-31", source="wikipedia")),
    ]
    assert store.upsert(points, batch_size=3) == 4
    assert store.count() == 4

    hits = store.search(unit(1, 0, 0), k=3)
    assert [h.chunk_id for h in hits] == ["a#0", "b#0", "w#0"]
    assert hits[0].score == pytest.approx(1.0, abs=1e-4)
    assert hits[0].categories == ("cs.CL",)
    assert hits[0].published_at == "2022-05-01"

    def ids(filters):
        return [h.chunk_id for h in store.search(unit(1, 0, 0), k=10, filters=filters)]

    assert ids({"categories": "cs.IR"}) == ["b#0"]  # a list field contains the value
    assert ids({"source": "wikipedia"}) == ["w#0"]
    assert ids({"published_at": {"gte": "2023-01-01", "lte": "2023-12-31"}}) == ["b#0", "w#0"]
    assert ids({"published_at": {"gt": "2023-12-31"}}) == ["c#0"]
    assert ids({"source": "arxiv", "categories": "cs.CL"}) == ["a#0", "b#0"]
    assert store.count({"categories": "cs.CL"}) == 2

    # Same id again: replaced, not added.
    store.upsert([Point(7, unit(0, 0, 1), chunk("w", 0, ["x"], "2020-01-01", "wikipedia"))])
    assert store.count() == 4
    assert store.search(unit(0, 0, 1), k=1)[0].categories == ("x",)


def test_exact_and_hnsw_search_both_answer(store):
    """Qdrant accepts `params.exact` (default) and the plain HNSW query; on a tiny collection
    both find the same nearest points."""
    store.ensure_collection(3)
    store.upsert(
        [
            Point(str(uuid.uuid4()), unit(1, 0, 0), chunk("a", 0, ["cs.CL"], "2022-05-01")),
            Point(str(uuid.uuid4()), unit(0, 1, 0), chunk("b", 0, ["cs.CL"], "2023-05-01")),
        ]
    )
    assert store.config.exact is True
    exact = [h.chunk_id for h in store.search(unit(1, 0.1, 0), k=2)]
    hnsw_store = QdrantStore(StoreConfig(url=URL, collection=store.collection, exact=False))
    with hnsw_store:
        approximate = [h.chunk_id for h in hnsw_store.search(unit(1, 0.1, 0), k=2)]
    assert exact == approximate == ["a#0", "b#0"]


def test_existing_collection_with_another_dimension_is_refused(store):
    store.ensure_collection(3)
    with pytest.raises(StoreError, match="expected 4"):
        store.ensure_collection(4)


def test_payload_indexes_exist(store):
    store.ensure_collection(3)
    info = httpx.get(f"{URL}/collections/{store.collection}", timeout=5.0).json()["result"]
    schema = {name: value["data_type"] for name, value in info["payload_schema"].items()}
    assert schema == {
        "source": "keyword",
        "categories": "keyword",
        "doc_id": "keyword",
        "published_at": "datetime",
    }
