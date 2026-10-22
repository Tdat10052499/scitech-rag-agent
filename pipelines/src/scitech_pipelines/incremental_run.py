"""Incremental ingestion with a date watermark (W5-D2-FAO-1, ADR 0008 points 3 to 5).

One run takes the days from the watermark to yesterday (UTC) through the bulk steps:
`incremental-fetch` -> `clean` -> `chunk` -> `embed` -> load. The watermark,
`<data>/state/incremental.json`, holds the last `until` day that was loaded. It is written
only after the load and its count check pass, so a failure at any step leaves it unchanged and
the next run repeats the same range. `--from` of the next run is that day itself, not the day
after: a day's records may still be arriving when it is first harvested (ADR 0008 point 1).

Re-running a range is harmless. The load deletes the points of every `doc_id` it is about to
load and then upserts the new chunks (`replace_documents`), so a paper harvested again (a new
version or a metadata change, about a third of a day on 2026-10-16) replaces its old chunks,
including higher-numbered ones its new abstract no longer has. Points of other papers are left
alone, and the store must end with exactly (points before - points deleted + chunks loaded).

The steps are passed in (`Steps`), so the order and the watermark rules are tested without
Spark, a model or Qdrant; `default_steps` wires the real ones. The store needs one method more
than `load` (`delete_doc_ids`); it comes with DAT's store module (W3-D1-DAT-1).
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from scitech_pipelines.chunk import CHUNK_FILE
from scitech_pipelines.clean import DEFAULT_CATEGORY
from scitech_pipelines.incremental import DEFAULT_SET, manifest_path
from scitech_pipelines.load import (
    DEFAULT_BATCH_SIZE,
    LOAD_MANIFEST,
    VectorStore,
    check_inputs,
    index_snapshot,
    upsert_part,
)
from scitech_pipelines.validate import _quote

STATE_FILE = Path("state") / "incremental.json"
DELETE_BATCH = 256  # doc ids per delete request

Log = Callable[[str], None]


class ReplaceStore(VectorStore, Protocol):
    """`VectorStore` plus deleting every point of some papers."""

    def delete_doc_ids(self, doc_ids: Sequence[str]) -> None:
        """Delete every point whose payload `doc_id` is in `doc_ids`. Raise on failure."""
        ...


@dataclass(frozen=True)
class Steps:
    """The five steps of a run. Paths are decided by `run_incremental`."""

    fetch: Callable[[date, date, Path], dict[str, Any]]  # (from, until, out.jsonl) -> manifest
    clean: Callable[[Path, Path], Any]  # (raw.jsonl, documents)
    chunk: Callable[[Path, Path], Any]  # (documents, chunks)
    embed: Callable[[Path, Path], Any]  # (chunks, embeddings)
    load: Callable[[Path, Path, Path], dict[str, Any]]  # (chunks, embeddings, out) -> manifest


def read_watermark(data_dir: Path) -> dict[str, Any] | None:
    path = data_dir / STATE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_watermark(data_dir: Path, state: dict[str, Any]) -> Path:
    """Write the state file through a temporary file, so a crash never leaves half of it."""
    path = data_dir / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _doc_ids(chunks: Path) -> list[str]:
    import duckdb

    con = duckdb.connect()
    rows = con.execute(
        f"SELECT DISTINCT doc_id FROM read_parquet({_quote((chunks / CHUNK_FILE).as_posix())}) "
        "ORDER BY doc_id"
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def replace_documents(
    chunks: Path,
    vectors: Path,
    store: ReplaceStore,
    out: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    log: Log = print,
) -> dict[str, Any]:
    """Delete the points of every paper in `chunks`, upsert its new chunks with their vectors,
    check the count and write `<out>/_load_manifest.json`."""
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    started = time.monotonic()
    inputs = check_inputs(chunks, vectors)
    doc_ids = _doc_ids(chunks)
    store.ensure_collection(inputs["dimension"])
    before = store.count()
    for start in range(0, len(doc_ids), DELETE_BATCH):
        store.delete_doc_ids(doc_ids[start : start + DELETE_BATCH])
    kept = store.count()
    loaded = sum(
        upsert_part(part, chunks, inputs["dimension"], store, batch_size)
        for part in inputs["parts"]
    )
    points = store.count()
    if loaded != inputs["expected"] or points != kept + loaded:
        raise RuntimeError(
            f"load check failed: {store.collection} holds {points} points, expected "
            f"{kept} kept + {inputs['expected']} loaded"
        )
    manifest = {
        "step": "load",
        "mode": "replace",
        "index_snapshot": index_snapshot(
            store.collection, inputs["model"], inputs["chunked_at"], inputs["embedded_at"]
        ),
        "collection": store.collection,
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunks": str(chunks),
        "vectors": str(vectors),
        "model": inputs["model"],
        "dimension": inputs["dimension"],
        "chunked_at": inputs["chunked_at"],
        "embedded_at": inputs["embedded_at"],
        "batch_size": batch_size,
        "counts": {
            "documents": len(doc_ids),
            "points_before": before,
            "points_deleted": before - kept,
            "points_loaded": loaded,
            "points": points,
        },
        "seconds": round(time.monotonic() - started, 1),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / LOAD_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(
        f"load: {len(doc_ids):,} papers replaced in {store.collection}: "
        f"{before - kept:,} old points deleted, {loaded:,} loaded, {points:,} points now"
    )
    return manifest


def run_incremental(
    data_dir: Path,
    steps: Steps,
    *,
    start: date | None = None,
    today: date | None = None,
    set_spec: str | None = DEFAULT_SET,
    category: str | None = DEFAULT_CATEGORY,
    log: Log = print,
) -> dict[str, Any]:
    """Run the days from the watermark (or `start` on the first run) to yesterday, UTC, and
    move the watermark only when the load has passed. Return the watermark state."""
    state = read_watermark(data_dir)
    if state is None and start is None:
        raise ValueError(
            f"no watermark in {data_dir / STATE_FILE}: give the first day with --start, the "
            "date of the Kaggle snapshot the bulk index was built from (2026-10-10 for 307)"
        )
    from_day = date.fromisoformat(state["until"]) if state else start
    until = (today or datetime.now(timezone.utc).date()) - timedelta(days=1)
    if until < from_day:
        log(f"incremental: nothing to do, the watermark is {from_day} and yesterday was {until}")
        return state or {}

    name = f"{from_day.isoformat()}_{until.isoformat()}"
    raw = data_dir / "raw" / "arxiv-oai" / f"{name}.jsonl"
    work = data_dir / "processed" / "incremental" / name
    if work.exists():  # an earlier failed run of the same range: start its steps again
        shutil.rmtree(work)
    log(f"incremental: {from_day} to {until} ({set_spec}, {category})")

    fetched = steps.fetch(from_day, until, raw)
    records = fetched["counts"]["kept"]
    load_manifest: dict[str, Any] | None = None
    if records:
        documents, chunks, embeddings = work / "documents", work / "chunks", work / "embeddings"
        steps.clean(raw, documents)
        steps.chunk(documents, chunks)
        steps.embed(chunks, embeddings)
        load_manifest = steps.load(chunks, embeddings, work / "index")
    else:
        log("incremental: no new records, nothing to load")

    previous = state or {}  # a day without records keeps the counts of the last load
    new_state = {
        "until": until.isoformat(),
        "from": from_day.isoformat(),
        "set": set_spec,
        "category": category,
        "records": records,
        "fetch_manifest": str(manifest_path(raw)),
        "load_manifest": str(work / "index" / LOAD_MANIFEST) if load_manifest else None,
        "points": load_manifest["counts"]["points"] if load_manifest else previous.get("points"),
        "index_snapshot": (
            load_manifest["index_snapshot"] if load_manifest else previous.get("index_snapshot")
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = write_watermark(data_dir, new_state)
    log(f"incremental: watermark {until} -> {path}")
    return new_state


def default_steps(
    store: ReplaceStore,
    encoder: Any,
    *,
    set_spec: str | None = DEFAULT_SET,
    category: str | None = DEFAULT_CATEGORY,
    passage_prefix: str = "",
    log: Log = print,
) -> Steps:
    """The real steps, with the same defaults as the bulk commands."""
    from scitech_pipelines.chunk import chunk_documents
    from scitech_pipelines.embed import embed_chunks
    from scitech_pipelines.incremental import fetch_incremental

    def clean(raw: Path, documents: Path) -> Any:
        from scitech_pipelines.clean import clean_arxiv, create_spark

        spark = create_spark()
        try:
            return clean_arxiv(spark, raw, documents, category=category, sample_size=0, log=log)
        finally:
            spark.stop()

    return Steps(
        fetch=lambda f, u, out: fetch_incremental(
            out, from_date=f, until=u, set_spec=set_spec, category=category, log=log
        ),
        clean=clean,
        chunk=lambda documents, chunks: chunk_documents(documents, chunks, log=log),
        embed=lambda chunks, out: embed_chunks(
            chunks, out, encoder, passage_prefix=passage_prefix, log=log
        ),
        load=lambda chunks, vectors, out: replace_documents(chunks, vectors, store, out, log=log),
    )
