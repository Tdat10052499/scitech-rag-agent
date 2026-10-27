"""Incremental fetch of new arXiv records through OAI-PMH (W3-D4-FAO-1, prototype for ADR 0008).

`ListRecords` with `metadataPrefix=arXiv` for a datestamp range (`from`/`until`, both inclusive,
days), optionally limited to one OAI set, following `resumptionToken` until the list ends.
arXiv allows one request every 3 s (docs/03-data-sources.md), so the client waits `pause` (at
least 3 s) before every request after the first, and retries 429/5xx answers, timeouts and
connection errors with backoff, honouring `Retry-After` (arXiv answers 503 for flow control).
The OAI error `noRecordsMatch` (nothing changed in the range) means zero records, not a failure.

Records whose `categories` contain `category` are written as JSON Lines in the shape of the
Kaggle snapshot (`clean.snapshot_schema()`), so `clean --input <file>` normalises them with the
same code as the bulk load. This module only maps XML to that shape; it does not normalise.
A manifest with the counts and settings is written next to the output.

The XML is matched on local element names, so a change of namespace URI does not break parsing.
"""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from scitech_pipelines.clean import DEFAULT_CATEGORY
from scitech_pipelines.download import DEFAULT_USER_AGENT, RETRY_STATUS, HttpSession, file_entry

DEFAULT_BASE_URL = "https://oaipmh.arxiv.org/oai"
DEFAULT_SET = "cs:cs:CL"  # holds cross-lists too: live check in ADR 0008
METADATA_PREFIX = "arXiv"
MIN_PAUSE = 3.0  # arXiv: one request every 3 s for the API, OAI-PMH and RSS together
OAI_ID_PREFIX = "oai:arXiv.org:"
# English names, independent of the locale, as in the snapshot's "Mon, 2 Apr 2007 19:18:42 GMT".
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

Log = Callable[[str], None]


class OaiError(RuntimeError):
    """An OAI-PMH `<error code="...">` answer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"OAI-PMH error {code}: {message}")
        self.code = code


# --- XML helpers (namespace-agnostic) -----------------------------------------------------------


def _local(tag: Any) -> str:
    """`{http://www.openarchives.org/OAI/2.0/}record` -> `record` (comments have no str tag)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if element is None else [c for c in element if _local(c.tag) == name]


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    found = _children(element, name)
    return found[0] if found else None


def _text(element: ET.Element | None, name: str) -> str | None:
    """Text of the child `name` as in the XML, None if the child is missing or blank."""
    child = _child(element, name)
    if child is None or child.text is None or not child.text.strip():
        return None
    return child.text


def _word(element: ET.Element | None, name: str) -> str:
    """Child text with whitespace collapsed, "" if missing (for author name parts)."""
    return " ".join((_text(element, name) or "").split())


# --- OAI-PMH client -----------------------------------------------------------------------------


class OaiClient:
    """Serial OAI-PMH client: one request at a time, at least `pause` seconds between requests,
    retries with backoff like `download.WikiClient`. `requests` counts HTTP answers received."""

    def __init__(
        self,
        session: HttpSession,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        pause: float = MIN_PAUSE,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
    ) -> None:
        if pause < MIN_PAUSE:
            raise ValueError(f"pause must be at least {MIN_PAUSE} s (arXiv rate limit)")
        self.session = session
        self.base_url = base_url
        self.headers = {"User-Agent": user_agent}
        self.pause = pause
        self.sleep = sleep
        self.max_retries = max_retries
        self.requests = 0
        self._started = False

    def backoff(self, attempt: int, retry_after: str | None = None) -> float:
        """Seconds to wait before retry `attempt`, never less than the pause."""
        if retry_after and retry_after.strip().isdigit():
            wait = min(float(retry_after), 300.0)
        else:
            wait = min(5.0 * 2**attempt, 120.0)
        return max(wait, self.pause)

    def get(self, params: dict[str, str]) -> ET.Element:
        """One OAI-PMH request; returns the parsed root. Raises OaiError for an OAI error."""
        wait = self.pause if self._started else 0.0
        self._started = True
        for attempt in range(self.max_retries + 1):
            last = attempt == self.max_retries
            if wait:
                self.sleep(wait)
            try:
                response = self.session.get(
                    self.base_url, params=params, headers=self.headers, timeout=120
                )
            except OSError:  # requests' ConnectionError and Timeout are OSErrors
                if last:
                    raise
                wait = self.backoff(attempt)
                continue
            self.requests += 1
            status = getattr(response, "status_code", 200)
            if status in RETRY_STATUS and not last:
                wait = self.backoff(attempt, response.headers.get("Retry-After"))
                continue
            response.raise_for_status()
            root = ET.fromstring(response.content)
            error = next((e for e in root.iter() if _local(e.tag) == "error"), None)
            if error is not None:
                raise OaiError(error.get("code", "unknown"), (error.text or "").strip())
            return root
        raise RuntimeError("OAI-PMH: retries exhausted")


def list_records(
    client: OaiClient,
    *,
    from_date: date,
    until: date | None = None,
    set_spec: str | None = None,
    metadata_prefix: str = METADATA_PREFIX,
    on_page: Callable[[ET.Element], None] | None = None,
) -> Iterator[ET.Element]:
    """Yield every `<record>` of a `ListRecords` harvest, following `resumptionToken`.
    `on_page` is called with the root of each page. `noRecordsMatch` yields nothing."""
    params = {"verb": "ListRecords", "metadataPrefix": metadata_prefix, "from": str(from_date)}
    if until is not None:
        params["until"] = str(until)
    if set_spec:
        params["set"] = set_spec
    while True:
        try:
            root = client.get(params)
        except OaiError as exc:
            if exc.code == "noRecordsMatch":
                return
            raise
        if on_page is not None:
            on_page(root)
        listing = next((e for e in root.iter() if _local(e.tag) == "ListRecords"), None)
        yield from _children(listing, "record")
        token = _text(listing, "resumptionToken")
        if token is None:  # absent or empty: the list is complete
            return
        # A resumption request carries only the verb and the token (OAI-PMH 2.0, exclusive arg).
        params = {"verb": "ListRecords", "resumptionToken": token.strip()}


# --- arXiv metadata format -> Kaggle snapshot record --------------------------------------------


def rfc2822_day(day: str) -> str | None:
    """`2024-09-30` -> `Mon, 30 Sep 2024 00:00:00 GMT`, as the snapshot's `versions[].created`
    (day without leading zero). None if the date cannot be parsed."""
    try:
        d = date.fromisoformat(day.strip())
    except ValueError:
        return None
    return f"{DAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]} {d.year} 00:00:00 GMT"


def is_deleted(record: ET.Element) -> bool:
    """A withdrawn record: `<header status="deleted">` without metadata."""
    header = _child(record, "header")
    return header is not None and header.get("status") == "deleted"


def to_snapshot_record(record: ET.Element) -> dict[str, Any]:
    """Map one OAI `<record>` in the arXiv metadata format to the Kaggle snapshot fields of
    `clean.snapshot_schema()`; missing fields are null, as in the snapshot.

    The arXiv format gives the first-version date (`created`) and the latest version date
    (`updated`) but no version list, so `versions` holds v1 only and `update_date` is `updated`
    (else `created`). Text fields are copied as they are: `clean` collapses whitespace.
    """
    header = _child(record, "header")
    identifier = _text(header, "identifier") or ""
    metadata = _child(record, "metadata")
    arxiv = next(iter(metadata), None) if metadata is not None else None
    if arxiv is None:
        raise ValueError(f"OAI record without metadata: {identifier!r}")
    doc_id = (_text(arxiv, "id") or identifier.removeprefix(OAI_ID_PREFIX)).strip()

    parsed = [
        [_word(a, "keyname"), _word(a, "forenames"), _word(a, "suffix")]
        for a in _children(_child(arxiv, "authors"), "author")
    ]
    names = [" ".join(p for p in (fore, key, suffix) if p) for key, fore, suffix in parsed]
    created = _text(arxiv, "created")
    first = rfc2822_day(created) if created else None
    updated = _text(arxiv, "updated") or created
    categories = _text(arxiv, "categories")
    return {
        "id": doc_id,
        "authors": ", ".join(n for n in names if n) or None,
        "title": _text(arxiv, "title"),
        "comments": _text(arxiv, "comments"),
        "journal-ref": _text(arxiv, "journal-ref"),
        "doi": _text(arxiv, "doi"),
        "report-no": _text(arxiv, "report-no"),
        "categories": " ".join(categories.split()) if categories else None,
        "license": _text(arxiv, "license"),
        "abstract": _text(arxiv, "abstract"),
        # No date: an empty list, so `clean` drops the record and counts it (dropped_no_date).
        "versions": [{"version": "v1", "created": first}] if first else [],
        "update_date": updated.strip() if updated else None,
        "authors_parsed": parsed or None,
    }


def in_category(record: dict[str, Any], category: str | None) -> bool:
    if not category:
        return True
    return category in (record.get("categories") or "").split()


# --- the fetch step -----------------------------------------------------------------------------


def manifest_path(out: Path) -> Path:
    """`new.jsonl` -> `new.manifest.json`, next to the output."""
    return out.with_name(out.stem + ".manifest.json")


def fetch_incremental(
    out: Path,
    *,
    from_date: date,
    until: date | None = None,
    set_spec: str | None = DEFAULT_SET,
    category: str | None = DEFAULT_CATEGORY,
    base_url: str = DEFAULT_BASE_URL,
    pause: float = MIN_PAUSE,
    session: HttpSession | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_retries: int = 5,
    user_agent: str = DEFAULT_USER_AGENT,
    log: Log = print,
) -> dict[str, Any]:
    """Harvest records with a datestamp in [from_date, until] and write those in `category` to
    `out` (JSON Lines, snapshot shape) plus `<out stem>.manifest.json`. Returns the manifest.

    The output is written to a temporary file and renamed when the harvest is complete, so a
    failed run leaves no partial file; a re-run with the same arguments replaces it.
    """
    if until is not None and until < from_date:
        raise ValueError(f"--until {until} is before --from {from_date}")
    if session is None:
        import requests

        session = requests.Session()
    client = OaiClient(
        session,
        base_url=base_url,
        user_agent=user_agent,
        pause=pause,
        sleep=sleep,
        max_retries=max_retries,
    )
    started = time.monotonic()
    harvested = deleted = kept = 0
    pages: list[str | None] = []  # responseDate of each page

    def on_page(root: ET.Element) -> None:
        pages.append(_text(root, "responseDate"))
        log(f"incremental-fetch: page {len(pages)} ({harvested:,} records before it)")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            records = list_records(
                client, from_date=from_date, until=until, set_spec=set_spec, on_page=on_page
            )
            for element in records:
                harvested += 1
                if is_deleted(element):
                    deleted += 1
                    continue
                record = to_snapshot_record(element)
                if in_category(record, category):
                    kept += 1
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)

    manifest = {
        "step": "incremental-fetch",
        "source": "arxiv-oai-pmh",
        "base_url": base_url,
        "metadata_prefix": METADATA_PREFIX,
        "from": str(from_date),
        "until": str(until) if until else None,
        "set": set_spec or None,
        "category": category or None,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "response_date": pages[0] if pages else None,
        "seconds": round(time.monotonic() - started, 1),
        "requests": client.requests,
        "pages": len(pages),
        "counts": {
            "harvested": harvested,
            "deleted": deleted,
            "not_in_category": harvested - deleted - kept,
            "kept": kept,
        },
        "output": file_entry(out),
    }
    manifest_path(out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(
        f"incremental-fetch: {harvested:,} records harvested ({deleted:,} deleted) in "
        f"{len(pages)} page(s), {kept:,} kept with {category or 'any category'} -> {out}"
    )
    return manifest


# --- the incremental run (W5-D2-FAO-1, ADR 0008) ------------------------------------------------

STATE_FILE = "incremental.json"  # the watermark, in <data-dir>/state/
SUMMARY = "incremental.json"  # what the run did, in its log folder
STEP_NAMES = ("incremental-fetch", "clean", "validate", "chunk", "embed", "load")


class IncrementalStore(Protocol):
    """What the run needs from the store (`scitech_agent.store.QdrantStore` has it)."""

    collection: str

    def ensure_collection(self, dimension: int) -> Any: ...

    def upsert(self, points: Sequence[Any]) -> Any: ...

    def count(self) -> int: ...

    def delete_doc_ids(self, doc_ids: Iterable[str]) -> int: ...


@dataclass(frozen=True)
class RunPaths:
    raw: Path  # the fetched records
    work: Path  # everything made from them
    documents: Path
    chunks: Path
    embeddings: Path
    index: Path


def run_paths(data_dir: Path, set_spec: str | None, from_date: date, until: date) -> RunPaths:
    """Where one range goes: the raw file next to those of `incremental-fetch`, the processed
    data in `<data-dir>/processed/incremental/<from>_<until>/`, never in the bulk folders."""
    name = f"{set_spec or 'all'}_{from_date}_{until}".replace(":", "-")  # ":" breaks Windows
    work = data_dir / "processed" / "incremental" / f"{from_date}_{until}"
    return RunPaths(
        raw=data_dir / "raw" / "arxiv-oai" / f"{name}.jsonl",
        work=work,
        documents=work / "documents",
        chunks=work / "chunks",
        embeddings=work / "embeddings",
        index=work / "index",
    )


def read_state(path: Path) -> dict[str, Any] | None:
    """The watermark file, or None before the first run."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: dict[str, Any]) -> None:
    """Write the watermark through a temporary file, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def plan_range(
    state: dict[str, Any] | None,
    *,
    start: date | None,
    until: date | None,
    today: date,
    state_path: Path,
) -> tuple[date, date]:
    """The datestamp range of this run. It starts at the watermark day itself (ADR 0008, point
    1: that day may have been harvested before all its records arrived), or at `start` on the
    first run, and ends at `until`, by default yesterday (UTC)."""
    if state is not None:
        if start is not None:
            raise ValueError(
                f"--start is only for the first run; {state_path} already holds the watermark "
                f"{state['until']} (delete that file to start again)"
            )
        from_date = date.fromisoformat(state["until"])
    elif start is None:
        raise ValueError(
            f"no watermark in {state_path}: pass --start with the date of the snapshot of the "
            "bulk index (2026-10-10 for Kaggle snapshot 307, ADR 0008 point 4)"
        )
    else:
        from_date = start
    return from_date, until or today - timedelta(days=1)


def check_settings(
    state: dict[str, Any] | None, settings: dict[str, Any], state_path: Path
) -> None:
    """A run with another set, category, collection or model than the watermark's would mix
    two indexes, so it fails."""
    if state is None:
        return
    changed = [k for k, v in settings.items() if state.get(k) != v]
    if changed:
        was = ", ".join(f"{k} {state.get(k)!r}" for k in changed)
        now = ", ".join(f"{k} {settings[k]!r}" for k in changed)
        raise ValueError(f"{state_path} was written with {was}; this run has {now}")


def plan_incremental_steps(
    data_dir: Path,
    paths: RunPaths,
    *,
    from_date: date,
    until: date,
    set_spec: str | None,
    category: str | None,
    base_url: str,
    pause: float,
    model: str,
    device: str | None = None,
) -> dict[str, tuple[str, ...]]:
    """The arguments of every step run as its own `python -m scitech_pipelines` process (the
    same commands as by hand); `load` runs in this process because it deletes first."""
    base = ("--data-dir", str(data_dir))
    fetch = [*base, "incremental-fetch", "--from", str(from_date), "--until", str(until)]
    fetch += ["--set", set_spec or "", "--category", category or "", "--out", str(paths.raw)]
    fetch += ["--base-url", base_url, "--pause", f"{pause:g}"]
    clean = [*base, "clean", "--input", str(paths.raw), "--out", str(paths.documents)]
    clean += ["--sample-size", "0"]
    validate = [*base, "validate", "--input", str(paths.documents)]
    if category:
        clean += ["--category", category]
        validate += ["--category", category]
    embed = [*base, "embed", "--input", str(paths.chunks), "--out", str(paths.embeddings)]
    embed += ["--model", model, "--force"]  # re-chunked input after a failed run: embed again
    if device:
        embed += ["--device", device]
    return {
        "incremental-fetch": tuple(fetch),
        "clean": tuple(clean),
        "validate": tuple(validate),
        "chunk": (*base, "chunk", "--input", str(paths.documents), "--out", str(paths.chunks)),
        "embed": tuple(embed),
    }


def _doc_ids(chunks: Path) -> list[str]:
    import duckdb

    from scitech_pipelines.chunk import CHUNK_FILE
    from scitech_pipelines.validate import _quote

    con = duckdb.connect()
    rows = con.execute(
        f"SELECT DISTINCT doc_id FROM read_parquet({_quote((chunks / CHUNK_FILE).as_posix())}) "
        "ORDER BY doc_id"
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def replace_documents(
    store: IncrementalStore,
    paths: RunPaths,
    *,
    batch_size: int,
    log: Log = print,
) -> dict[str, Any]:
    """Delete every point of the documents in this run's chunks, then load their new chunks
    (ADR 0008, point 5), and check that the store holds exactly the points it should."""
    from scitech_pipelines.embed import EMBED_STATE
    from scitech_pipelines.load import load_index

    dimension = json.loads((paths.embeddings / EMBED_STATE).read_text(encoding="utf-8"))[
        "dimension"
    ]
    store.ensure_collection(dimension)
    doc_ids = _doc_ids(paths.chunks)
    before = store.count()
    store.delete_doc_ids(doc_ids)
    left = store.count()
    log(
        f"load: {len(doc_ids):,} documents to (re)load; {before - left:,} of their old points "
        f"deleted, {left:,} points left in {store.collection}"
    )
    chunks = json.loads((paths.chunks / "_chunk_manifest.json").read_text(encoding="utf-8"))
    manifest = load_index(
        paths.chunks,
        paths.embeddings,
        store,
        paths.index,
        batch_size=batch_size,
        force=True,
        expected_points=left + chunks["counts"]["chunks"],
        log=log,
    )
    manifest["counts"].update(
        {"documents": len(doc_ids), "points_before": before, "old_points_deleted": before - left}
    )
    (paths.index / "_load_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def run_incremental(
    data_dir: Path,
    store: IncrementalStore,
    *,
    model: str,
    state_path: Path | None = None,
    start: date | None = None,
    until: date | None = None,
    today: date | None = None,
    set_spec: str | None = DEFAULT_SET,
    category: str | None = DEFAULT_CATEGORY,
    base_url: str = DEFAULT_BASE_URL,
    pause: float = MIN_PAUSE,
    device: str | None = None,
    batch_size: int = 256,
    run_step: Callable[[Sequence[str], Path], int] | None = None,
    log: Log = print,
) -> int:
    """One incremental run: fetch the range from the watermark, clean, validate, chunk, embed,
    replace the documents in the store, and only then move the watermark. Any failure leaves the
    watermark where it was, so the next run repeats the same range. Returns the exit code."""
    from scitech_pipelines.run_all import tee_step

    run_step = run_step or tee_step
    state_path = state_path or data_dir / "state" / STATE_FILE
    today = today or datetime.now(timezone.utc).date()
    state = read_state(state_path)
    from_date, until = plan_range(
        state, start=start, until=until, today=today, state_path=state_path
    )
    settings = {
        "set": set_spec or None,
        "category": category or None,
        "collection": store.collection,
        "model": model,
    }
    check_settings(state, settings, state_path)
    if until < from_date:
        log(f"incremental: nothing to do, the watermark {from_date} is after {until}")
        return 0
    paths = run_paths(data_dir, set_spec, from_date, until)
    steps = plan_incremental_steps(
        data_dir,
        paths,
        from_date=from_date,
        until=until,
        set_spec=set_spec,
        category=category,
        base_url=base_url,
        pause=pause,
        model=model,
        device=device,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs = data_dir / "logs" / f"incremental-{stamp}"
    logs.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "step": "incremental",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "from": str(from_date),
        "until": str(until),
        "watermark_before": state["until"] if state else None,
        **settings,
        "work_dir": str(paths.work),
        "steps": [],
    }
    started = time.monotonic()

    def finish(code: int, message: str) -> int:
        summary["exit_code"] = code
        summary["watermark_after"] = str(until) if code == 0 else summary["watermark_before"]
        summary["seconds"] = round(time.monotonic() - started, 1)
        (logs / SUMMARY).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        log(f"incremental: {message}; logs in {logs}")
        return code

    log(f"incremental: {from_date} to {until} into {store.collection} (logs {logs})")
    load_manifest: dict[str, Any] | None = None
    for i, name in enumerate(STEP_NAMES, 1):
        log_file = logs / f"{i:02d}-{name}.log"
        t = time.monotonic()
        if name == "load":
            try:
                load_manifest = replace_documents(store, paths, batch_size=batch_size, log=log)
                code = 0
            except Exception as exc:  # noqa: BLE001 - reported, and the watermark stays
                log_file.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
                log(f"load failed: {exc}")
                code = 1
        else:
            code = run_step(steps[name], log_file)
        summary["steps"].append(
            {"name": name, "exit_code": code, "seconds": round(time.monotonic() - t, 1)}
        )
        if code != 0:
            message = f"{name} FAILED (exit {code}), watermark stays at {from_date}"
            if name == "load":
                message += " (documents deleted before the failure come back when it is re-run)"
            return finish(code, message)
        if name == "incremental-fetch":
            fetched = json.loads(manifest_path(paths.raw).read_text(encoding="utf-8"))
            summary["fetch"] = fetched["counts"]
            if fetched["counts"]["kept"] == 0:
                summary["steps"][-1]["note"] = "no records: nothing to clean or load"
                break

    points = load_manifest["counts"]["points"] if load_manifest else (state or {}).get("points")
    write_state(
        state_path,
        {
            "until": str(until),
            **settings,
            "points": points,
            "fetch_manifest": str(manifest_path(paths.raw)),
            "load_manifest": str(paths.index / "_load_manifest.json") if load_manifest else None,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    if load_manifest:
        summary["load"] = load_manifest["counts"]
    loaded = load_manifest["counts"]["chunks"] if load_manifest else 0
    return finish(0, f"{loaded:,} chunks loaded, watermark moved to {until}")
