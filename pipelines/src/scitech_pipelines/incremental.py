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
from collections.abc import Callable, Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from scitech_pipelines.clean import DEFAULT_CATEGORY
from scitech_pipelines.download import DEFAULT_USER_AGENT, RETRY_STATUS, HttpSession, file_entry

DEFAULT_BASE_URL = "https://oaipmh.arxiv.org/oai"
DEFAULT_SET = "cs"
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
