"""Download the index from a Hugging Face dataset repo and load it into the local Qdrant
(deploy/hf-space, run by start.sh). The repo holds what `push_space.py index` uploaded:
`qdrant/<collection>.snapshot` and `bm25/` (the BM25 index directory).

Settings (Space variables and secrets): INDEX_REPO (dataset repo id), HF_TOKEN (read access, only
for a private repo), QDRANT_URL, QDRANT_COLLECTION, DATA_DIR. If `<DATA_DIR>/index-src` already
holds the index (a local test mounts it there), nothing is downloaded. Exit code 1 on any failure.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from huggingface_hub import snapshot_download


def wait_for_qdrant(url: str, seconds: float = 60.0) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            httpx.get(f"{url}/readyz", timeout=2.0).raise_for_status()
            return
        except httpx.HTTPError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1.0)


def points_count(url: str, collection: str) -> int | None:
    response = httpx.get(f"{url}/collections/{collection}", timeout=10.0)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return int(response.json()["result"]["points_count"])


def main() -> int:
    repo = os.environ.get("INDEX_REPO", "").strip()
    qdrant = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
    collection = os.environ.get("QDRANT_COLLECTION", "scitech_chunks")
    target = Path(os.environ.get("DATA_DIR", "/app/data")) / "index-src"

    if (target / "bm25" / "_bm25_manifest.json").is_file():
        local = target  # already there (a local test mounts it); no download
    elif not repo:
        print("fetch_index: INDEX_REPO is empty and no index is in " + str(target), file=sys.stderr)
        return 1
    else:
        t0 = time.monotonic()
        local = Path(
            snapshot_download(
                repo_id=repo,
                repo_type="dataset",
                local_dir=target,
                token=os.environ.get("HF_TOKEN") or None,
            )
        )
        print(f"fetch_index: downloaded {repo} in {time.monotonic() - t0:.0f} s")

    bm25 = local / "bm25"
    if not (bm25 / "_bm25_manifest.json").is_file():
        print(f"fetch_index: {bm25} has no _bm25_manifest.json", file=sys.stderr)
        return 1

    wait_for_qdrant(qdrant)
    if points_count(qdrant, collection) is None:
        snapshot = local / "qdrant" / f"{collection}.snapshot"
        t0 = time.monotonic()
        with snapshot.open("rb") as fh:
            response = httpx.post(
                f"{qdrant}/collections/{collection}/snapshots/upload",
                params={"priority": "snapshot", "wait": "true"},
                files={"snapshot": (snapshot.name, fh, "application/octet-stream")},
                timeout=1800.0,
            )
        response.raise_for_status()
        print(f"fetch_index: restored {collection} in {time.monotonic() - t0:.0f} s")
    print(f"fetch_index: {collection} has {points_count(qdrant, collection)} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
