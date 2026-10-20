"""Load the chunks and their vectors into the vector store (W3-D3-FAO-1).

Every vector part of `embed` (`part-NNNNN.parquet`, in `chunk_id` order) is joined with its
chunks and upserted in batches. Each point carries a stable id derived from `chunk_id`
(`point_id`) and the chunk's fields as payload (`docs/contracts/chunk.schema.json`, with
`embedding_model`; fields without a value are left out). A re-run upserts the same ids again,
so loading is idempotent. Finished parts are kept in `<out>/_load_state.json`, so an
interrupted run resumes at the first part not done; a run with other settings (vectors, chunks,
collection) fails instead of mixing them. At the end the store must hold exactly one point per
chunk. `<out>/_load_manifest.json` records counts, times and `index_snapshot`, the id that
evaluation runs cite (`index_snapshot` in their config).

`fraction` loads a fixed subset of the documents instead (scaling measurements, W6-D2-FAO-1):
a document is kept when the hash of its `doc_id` falls below `fraction`, with all its chunks.
The subset does not depend on the order of the data, spreads over all years, and is nested
(the 10% subset is inside the 50% one), so each size can go to its own collection from the
same vectors without embedding again.

The store itself (create the collection, upsert, count) is DAT's module (W3-D1-DAT-1); this
module only needs the three methods of `VectorStore`.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from scitech_pipelines.chunk import CHUNK_FILE, CHUNK_MANIFEST
from scitech_pipelines.embed import EMBED_MANIFEST, EMBED_STATE
from scitech_pipelines.validate import _quote

LOAD_STATE = "_load_state.json"
LOAD_MANIFEST = "_load_manifest.json"
DEFAULT_BATCH_SIZE = 256
# Fixed namespace of the point ids: the same chunk_id always gives the same id.
POINT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://github.com/Tdat10052499/scitech-rag-agent"
)

Log = Callable[[str], None]


@dataclass(frozen=True)
class Point:
    id: str
    vector: list[float]
    payload: dict[str, Any]


class VectorStore(Protocol):
    """What `load_index` needs from the store module."""

    collection: str

    def ensure_collection(self, dimension: int) -> None:
        """Create the collection if it is missing; fail if it exists with another dimension."""
        ...

    def upsert(self, points: Sequence[Point]) -> None:
        """Insert or replace the points (same id: replaced). Raise on failure."""
        ...

    def count(self) -> int:
        """Exact number of points in the collection."""
        ...


def point_id(chunk_id: str) -> str:
    """Stable point id of a chunk (the store needs an unsigned integer or a UUID)."""
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_part(part: Path, chunks: Path, dimension: int) -> tuple[list[dict[str, Any]], Any]:
    """Chunk fields and vectors of one vector part, in `chunk_id` order."""
    import duckdb

    con = duckdb.connect()
    result = con.execute(
        "SELECT v.chunk_id, c.* EXCLUDE (chunk_id), v.embedding_model, v.embedding "
        f"FROM read_parquet({_quote(part.as_posix())}) v "
        f"LEFT JOIN read_parquet({_quote((chunks / CHUNK_FILE).as_posix())}) c USING (chunk_id) "
        "ORDER BY chunk_id"
    )
    # to_arrow_table is the newer name (duckdb >= 1.4); fetch_arrow_table works from 1.1.
    table = getattr(result, "to_arrow_table", result.fetch_arrow_table)()
    con.close()
    vectors = (
        table.column("embedding")
        .combine_chunks()
        .flatten()
        .to_numpy(zero_copy_only=False)
        .reshape(-1, dimension)
    )
    rows = table.drop(["embedding"]).to_pylist()
    missing = [r["chunk_id"] for r in rows if r["doc_id"] is None]
    if missing:
        raise ValueError(f"{part.name}: {len(missing)} vectors have no chunk, e.g. {missing[0]}")
    return rows, vectors


def in_subset(doc_id: str, fraction: float | None) -> bool:
    """Whether `doc_id` belongs to the subset of size `fraction` (None: everything)."""
    if fraction is None:
        return True
    digest = hashlib.sha256(doc_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < fraction


def _check_fraction(fraction: float | None) -> float | None:
    if fraction is None or fraction == 1:
        return None
    if not 0 < fraction < 1:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    return fraction


def _subset_count(chunks: Path, fraction: float) -> int:
    """Number of chunks whose document is in the subset."""
    import pyarrow.parquet as pq

    doc_ids = pq.read_table(chunks / CHUNK_FILE, columns=["doc_id"]).column("doc_id")
    return sum(in_subset(d, fraction) for d in doc_ids.to_pylist())


def to_point(row: dict[str, Any], vector: Any) -> Point:
    payload = {k: v for k, v in row.items() if v is not None and v != []}
    return Point(point_id(row["chunk_id"]), vector.tolist(), payload)


def index_snapshot(
    collection: str,
    model: str,
    chunked_at: str | None,
    embedded_at: str | None,
    fraction: float | None = None,
) -> str:
    """Readable id of a loaded index, e.g.
    `scitech_chunks/bge-small-en-v1.5/chunked-2026-10-17T05:19:12/embedded-2026-10-17T06:40:37`.
    `embedded_at` tells two embed runs of the same model on the same chunks apart."""

    def stamp(value: str | None) -> str:
        return (value or "unknown").split("+")[0]

    snapshot = (
        f"{collection}/{model.split('/')[-1]}/"
        f"chunked-{stamp(chunked_at)}/embedded-{stamp(embedded_at)}"
    )
    return f"{snapshot}/subset-{fraction:g}" if fraction is not None else snapshot


def load_index(
    chunks: Path,
    vectors: Path,
    store: VectorStore,
    out: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force: bool = False,
    fraction: float | None = None,
    log: Log = print,
) -> dict[str, Any]:
    """Upsert every vector of `vectors` with its chunk from `chunks` into `store`, then check
    the count and write `<out>/_load_manifest.json`. `force` ignores the resume state;
    `fraction` loads only the documents of that subset (`in_subset`)."""
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    fraction = _check_fraction(fraction)
    started = time.monotonic()
    chunk_manifest = _read_json(chunks / CHUNK_MANIFEST)
    embed_state = _read_json(vectors / EMBED_STATE)
    embed_manifest = _read_json(vectors / EMBED_MANIFEST)  # only a finished embed run is loaded
    if embed_state["chunks"]["chunked_at"] != chunk_manifest.get("chunked_at"):
        raise ValueError(
            f"{vectors} was made from other chunks (chunked_at "
            f"{embed_state['chunks']['chunked_at']}, {chunks} has "
            f"{chunk_manifest.get('chunked_at')}); re-run embed or pick the matching chunks"
        )
    expected = embed_manifest["counts"]["chunks"]
    if expected != chunk_manifest["counts"]["chunks"]:
        raise ValueError(
            f"{vectors} holds {expected} vectors for {chunk_manifest['counts']['chunks']} chunks "
            "(embed ran with --limit?); load needs one vector per chunk"
        )
    parts = sorted(vectors.glob("part-*.parquet"))
    if len(parts) != embed_manifest["counts"]["parts"]:
        raise ValueError(
            f"{vectors}: {len(parts)} parts, the embed manifest lists "
            f"{embed_manifest['counts']['parts']}"
        )
    model, dimension = embed_state["model"], embed_state["dimension"]
    settings = {
        "collection": store.collection,
        "model": model,
        "dimension": dimension,
        "chunked_at": chunk_manifest.get("chunked_at"),
        "embedded_at": embed_manifest.get("embedded_at"),
        "parts": [p.name for p in parts],
    }
    if fraction is not None:  # only then, so resume states of full loads stay valid
        settings["fraction"] = fraction
        expected = _subset_count(chunks, fraction)

    out.mkdir(parents=True, exist_ok=True)
    state_path = out / LOAD_STATE
    state = {"settings": settings, "parts_done": []}
    if state_path.is_file() and not force:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        if previous.get("settings") != settings:
            raise ValueError(
                f"{state_path} is from a load with other settings (vectors, chunks or "
                "collection); use --force to load again, or another --out"
            )
        state = previous

    store.ensure_collection(dimension)
    done = set(state["parts_done"])
    loaded = 0
    for i, part in enumerate(parts, 1):
        if part.name in done:
            continue
        t = time.monotonic()
        rows, part_vectors = _read_part(part, chunks, dimension)
        if fraction is not None:
            keep = [i for i, r in enumerate(rows) if in_subset(r["doc_id"], fraction)]
            rows, part_vectors = [rows[i] for i in keep], part_vectors[keep]
        for start in range(0, len(rows), batch_size):
            batch = zip(
                rows[start : start + batch_size],
                part_vectors[start : start + batch_size],
                strict=True,
            )
            store.upsert([to_point(r, v) for r, v in batch])
        loaded += len(rows)
        state["parts_done"].append(part.name)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        log(f"load: part {i}/{len(parts)}, {len(rows):,} points in {time.monotonic() - t:.1f} s")

    points = store.count()
    if points != expected:
        raise RuntimeError(
            f"load check failed: {store.collection} holds {points} points, expected {expected} "
            "(one per chunk of the subset loaded). Points from an older load? Recreate the "
            "collection and use --force"
        )
    manifest = {
        "step": "load",
        "index_snapshot": index_snapshot(
            store.collection, model, settings["chunked_at"], settings["embedded_at"], fraction
        ),
        "collection": store.collection,
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunks": str(chunks),
        "vectors": str(vectors),
        "model": model,
        "dimension": dimension,
        "chunked_at": settings["chunked_at"],
        "embedded_at": settings["embedded_at"],
        "batch_size": batch_size,
        "fraction": fraction,
        "counts": {
            "points": points,
            "parts": len(parts),
            "parts_resumed": len(done),
            "points_loaded_this_run": loaded,
        },
        "seconds": round(time.monotonic() - started, 1),
    }
    (out / LOAD_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(
        f"load: {points:,} points in {store.collection} ({model}, {dimension} dimensions), "
        f"{loaded:,} loaded in this run ({len(done)} parts resumed); {manifest['seconds']} s; "
        f"index_snapshot {manifest['index_snapshot']}"
    )
    return manifest
