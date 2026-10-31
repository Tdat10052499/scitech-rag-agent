"""Integration test of `load` (W3-D3-FAO-1) with DAT's store against a real Qdrant.

Runs only when Qdrant answers at `QDRANT_URL` (default http://localhost:6333), e.g. after
`make up-qdrant` (or `make up`); otherwise it is skipped, as in CI. It loads the fixture chunks
into a throw-away collection that it deletes at the end, so it never touches
`QDRANT_COLLECTION`. Run it with:
    python -m pytest -m integration pipelines/tests/test_load_integration.py
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from test_embed import read_vectors  # noqa: E402
from test_load import data, n_chunks  # noqa: E402, F401

from scitech_agent.store import QdrantStore, StoreConfig  # noqa: E402
from scitech_pipelines.cli import main  # noqa: E402

pytestmark = pytest.mark.integration

URL = (os.environ.get("QDRANT_URL") or "http://localhost:6333").rstrip("/")


def _reachable(url: str) -> bool:
    try:
        return httpx.get(f"{url}/healthz", timeout=2.0).is_success
    except httpx.HTTPError:
        return False


if not _reachable(URL):
    pytest.skip(f"Qdrant is not reachable at {URL}", allow_module_level=True)


def test_load_command_into_qdrant(data, tmp_path: Path, monkeypatch):  # noqa: F811
    chunks, vectors = data
    collection = f"test_load_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("QDRANT_URL", URL)
    store = QdrantStore(StoreConfig(url=URL, collection=collection))
    args = ["--data-dir", str(tmp_path), "load", "--chunks", str(chunks)]
    args += ["--vectors", str(vectors), "--collection", collection, "--batch-size", "3"]
    try:
        assert main(args) == 0
        expected = read_vectors(vectors)
        assert store.count() == n_chunks(chunks) == len(expected)

        # A re-run resumes with nothing left to load; with --force it upserts the same ids.
        assert main(args) == 0
        assert main([*args, "--force"]) == 0
        assert store.count() == len(expected)

        # Each stored vector finds its own chunk first.
        for chunk_id, (vector, _) in list(expected.items())[:5]:
            assert store.search(vector, 1)[0].chunk_id == chunk_id

        # The payload filters work on the loaded fields.
        hit = store.search(next(iter(expected.values()))[0], 1)[0]
        assert store.count({"doc_id": hit.doc_id}) >= 1
        assert store.count({"categories": hit.categories[0]}) >= 1
        day = hit.published_at
        assert store.count({"published_at": {"gte": day, "lte": day}}) >= 1

        manifest = json.loads(
            (tmp_path / "processed" / "index" / "_load_manifest.json").read_text()
        )
        assert manifest["counts"]["points"] == len(expected)
    finally:
        store.delete_collection()
        store.close()
