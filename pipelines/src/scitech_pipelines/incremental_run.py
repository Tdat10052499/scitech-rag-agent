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

Known gap of delete-then-upsert (DAT's review): between the delete and the upsert, the papers being
replaced have no points, so a search at that moment does not find them (0.3 to 2.4 s in the live
test, #124). If the upsert fails, they stay missing until the next run, which repeats the range
because the watermark did not move. Accepted for v1.0: runs are manual and short, and the
evaluation index is never a target (ADR 0008).

The run refuses a model other than the one the bulk load wrote into the same collection
(`check_index_model`): only the vector size is checked against Qdrant, so a different model with
the same size would mix vectors silently.

The steps are passed in (`Steps`), so the order and the watermark rules are tested without
Spark, a model or Qdrant; `default_steps` wires the real ones. The store needs one method more
than `load` (`delete_doc_ids`). DAT's store module (W3-D1-DAT-1) has no delete, so
`QdrantReplaceStore` adds Qdrant's delete-by-filter on top of it, through the REST API at the
store's own URL and collection; the store module itself is unchanged.

Scheduled runs (ADR 0011) add four rules, all off by default so a manual run behaves as before:
- `until_today`: fetch up to today (UTC) instead of yesterday. The watermark day is still fetched
  again by the next run, so records that arrive later the same day are not missed.
- `skip_unchanged`: compare each fetched record with the one fetched for the same paper by the
  last successful run (a hash of its line, in `<data>/state/incremental-seen.json`) and send only
  new or changed papers to `clean`. With none left, the run logs `incremental: nothing changed`
  and changes nothing, not even the watermark.
- `after_load`: called once the load has passed and before the watermark moves (the BM25
  rebuild of the live index, `scitech_pipelines.bm25_live`); if it fails, the next run repeats.
- `run_lock`: one run at a time (`<data>/state/incremental.lock`).
`check_not_frozen` refuses the frozen evaluation collection (`FROZEN_COLLECTION`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
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
SEEN_FILE = Path("state") / "incremental-seen.json"  # line hash per paper of the last run
LOCK_FILE = Path("state") / "incremental.lock"
LOCK_STALE_SECONDS = 3 * 3600  # a lock of another host older than this is taken over
DEFAULT_FROZEN_COLLECTION = "scitech_chunks"  # evaluation index, frozen (evaluation/SNAPSHOT.md)
DELETE_BATCH = 256  # doc ids per delete request

Log = Callable[[str], None]


class ReplaceStore(VectorStore, Protocol):
    """`VectorStore` plus deleting every point of some papers."""

    def delete_doc_ids(self, doc_ids: Sequence[str]) -> None:
        """Delete every point whose payload `doc_id` is in `doc_ids`. Raise on failure."""
        ...


class QdrantReplaceStore:
    """A `QdrantStore` (scitech_agent.store) plus `delete_doc_ids`, for `replace_documents`.

    Collection, upsert and count go to the wrapped store. The delete is Qdrant's
    `POST /collections/<collection>/points/delete` with a `doc_id` filter (`doc_id` has a payload
    index, created by `ensure_collection`), sent with `wait=true` so the count that follows
    already sees it."""

    def __init__(self, store: Any, *, transport: Any = None) -> None:
        import httpx

        self.store = store
        config = store.config
        self._http = httpx.Client(base_url=config.url, timeout=config.timeout, transport=transport)

    @property
    def collection(self) -> str:
        return self.store.collection

    def ensure_collection(self, dimension: int) -> None:
        self.store.ensure_collection(dimension)

    def upsert(self, points: Sequence[Any]) -> None:
        self.store.upsert(points)

    def count(self) -> int:
        return self.store.count()

    def delete_doc_ids(self, doc_ids: Sequence[str]) -> None:
        if not doc_ids:
            return
        import httpx

        path = f"/collections/{self.collection}/points/delete?wait=true"
        body = {"filter": {"must": [{"key": "doc_id", "match": {"any": list(doc_ids)}}]}}
        try:
            response = self._http.post(path, json=body)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Qdrant delete in {self.collection} failed: {exc}") from exc
        if response.is_error:
            raise RuntimeError(
                f"Qdrant delete in {self.collection} failed with HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

    def scroll_payloads(
        self, fields: Sequence[str], *, page_size: int = 1000
    ) -> Iterator[dict[str, Any]]:
        """Every point's payload (only `fields`), page by page through Qdrant's scroll API."""
        import httpx

        path = f"/collections/{self.collection}/points/scroll"
        offset: Any = None
        while True:
            body: dict[str, Any] = {
                "limit": page_size,
                "with_payload": list(fields),
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            try:
                response = self._http.post(path, json=body)
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Qdrant scroll in {self.collection} failed: {exc}") from exc
            if response.is_error:
                raise RuntimeError(
                    f"Qdrant scroll in {self.collection} failed with HTTP "
                    f"{response.status_code}: {response.text[:300]}"
                )
            result = response.json()["result"]
            for point in result["points"]:
                yield point.get("payload") or {}
            offset = result.get("next_page_offset")
            if offset is None:
                return

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> QdrantReplaceStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


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


def check_index_model(data_dir: Path, collection: str, model: str) -> None:
    """Refuse `model` if the bulk load's manifest (`<data>/processed/index/_load_manifest.json`)
    says the same collection was loaded with another model. Nothing to check without it."""
    path = data_dir / "processed" / "index" / LOAD_MANIFEST
    if not path.is_file():
        return
    bulk = json.loads(path.read_text(encoding="utf-8"))
    if bulk.get("collection") == collection and bulk.get("model") not in (None, model):
        raise ValueError(
            f"{collection} was loaded with {bulk['model']} ({path}), not {model}: vectors of two "
            "models would be mixed. Use the model of the bulk load, or another --collection."
        )


def check_not_frozen(collection: str, frozen: str | None = DEFAULT_FROZEN_COLLECTION) -> None:
    """Refuse the frozen evaluation collection (ADR 0011). `frozen` empty: no check."""
    if frozen and collection == frozen:
        raise ValueError(
            f"{collection} is the frozen evaluation collection (FROZEN_COLLECTION): incremental "
            "runs go to the live collection (ADR 0011), for example scitech_chunks_live"
        )


class RunLocked(RuntimeError):
    """Another run holds the lock."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # alive, owned by another user
        return True
    except OSError:  # Windows: no signal 0 for a process that is gone
        return False
    return True


@contextmanager
def run_lock(
    data_dir: Path, *, stale_seconds: float = LOCK_STALE_SECONDS, log: Log = print
) -> Iterator[Path]:
    """Hold `<data>/state/incremental.lock` for the duration of a run.

    The lock file holds the host name, the process id and the start time. A lock left by a
    process that is gone (same host) is taken over; a lock of another host (a container that
    was recreated) is taken over only after `stale_seconds`, because its process cannot be
    checked from here. Anything else raises `RunLocked`."""
    path = data_dir / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    mine = {"host": socket.gethostname(), "pid": os.getpid(), "started": time.time()}
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                held = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                held = {}
            same_host = held.get("host") == mine["host"]
            age = time.time() - float(held.get("started") or 0)
            if (same_host and _pid_alive(int(held.get("pid") or 0))) or (
                not same_host and age < stale_seconds
            ):
                raise RunLocked(
                    f"another incremental run holds {path} (host {held.get('host')}, pid "
                    f"{held.get('pid')}, started {age / 60:.0f} min ago); this run stops"
                ) from None
            log(f"incremental: taking over a stale lock {path} ({held})")
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(mine, f)
        break
    else:
        raise RunLocked(f"could not take {path}")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _line_hashes(raw: Path) -> dict[str, str]:
    """Paper id -> sha1 of its fetched line (the record as `incremental-fetch` wrote it)."""
    hashes: dict[str, str] = {}
    if not raw.is_file():
        return hashes
    with raw.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                hashes[json.loads(line)["id"]] = hashlib.sha1(line.encode("utf-8")).hexdigest()
    return hashes


def read_seen(data_dir: Path) -> dict[str, str]:
    path = data_dir / SEEN_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def keep_changed(raw: Path, out: Path, seen: dict[str, str]) -> int:
    """Copy the lines of `raw` whose paper is not in `seen` or has another hash to `out`;
    return how many were copied."""
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with raw.open(encoding="utf-8") as src, out.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            doc_id = json.loads(line)["id"]
            if seen.get(doc_id) != hashlib.sha1(line.encode("utf-8")).hexdigest():
                dst.write(line)
                kept += 1
    return kept


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
    until_today: bool = False,
    skip_unchanged: bool = False,
    after_load: Callable[[], Any] | None = None,
    now: datetime | None = None,
    log: Log = print,
) -> dict[str, Any]:
    """Run the days from the watermark (or `start` on the first run) to yesterday, UTC (today
    with `until_today`), and move the watermark only when the load and `after_load` have
    passed. Return the watermark state (unchanged when nothing changed)."""
    state = read_watermark(data_dir)
    if state is None and start is None:
        raise ValueError(
            f"no watermark in {data_dir / STATE_FILE}: give the first day with --start, the "
            "date of the Kaggle snapshot the bulk index was built from (2026-10-10 for 307)"
        )
    now = now or datetime.now(timezone.utc)
    from_day = date.fromisoformat(state["until"]) if state else start
    until = (today or now.date()) - timedelta(days=0 if until_today else 1)
    if until < from_day:
        log(f"incremental: nothing to do, the watermark is {from_day} and yesterday was {until}")
        return state or {}

    name = f"{from_day.isoformat()}_{until.isoformat()}"
    raw = data_dir / "raw" / "arxiv-oai" / f"{name}.jsonl"
    # Several runs a day fetch the same range: each gets its own folder, so the folder of the
    # last successful run, named in the watermark, is never removed by the next one.
    work = data_dir / "processed" / "incremental" / (
        f"{name}_{now:%H%M%S}" if until_today else name
    )
    if work.exists():  # an earlier failed run of the same range: start its steps again
        shutil.rmtree(work)
    log(f"incremental: {from_day} to {until} ({set_spec}, {category})")

    fetched = steps.fetch(from_day, until, raw)
    records = fetched["counts"]["kept"]
    to_clean = raw
    if skip_unchanged and records:
        to_clean = work / "changed.jsonl"
        records = keep_changed(raw, to_clean, read_seen(data_dir))
        log(f"incremental: {records:,} of {fetched['counts']['kept']:,} papers new or changed")
        if not records:
            shutil.rmtree(work)
            log("incremental: nothing changed")
            return state or {}
    load_manifest: dict[str, Any] | None = None
    if records:
        documents, chunks, embeddings = work / "documents", work / "chunks", work / "embeddings"
        steps.clean(to_clean, documents)
        steps.chunk(documents, chunks)
        steps.embed(chunks, embeddings)
        load_manifest = steps.load(chunks, embeddings, work / "index")
        if after_load is not None:
            after_load()
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
        "updated_at": now.isoformat(timespec="seconds"),
    }
    if skip_unchanged:
        _write_json(data_dir / SEEN_FILE, _line_hashes(raw))
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
