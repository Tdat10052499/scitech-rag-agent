"""Tests for the OAI-PMH incremental fetch (W3-D4-FAO-1). No network: arXiv's OAI-PMH endpoint is
replaced by a fake session that serves small hand-written XML pages."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scitech_pipelines import clean
from scitech_pipelines.cli import main
from scitech_pipelines.incremental import (
    OaiClient,
    OaiError,
    fetch_incremental,
    is_deleted,
    list_records,
    manifest_path,
    rfc2822_day,
    to_snapshot_record,
)

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
ARXIV_NS = "http://arxiv.org/OAI/arXiv/"
URL = "https://oai.example.org/oai"


def quiet(_: str) -> None:
    pass


def arxiv_record(
    doc_id: str,
    categories: str,
    *,
    created: str = "2026-10-12",
    updated: str | None = None,
    extra: str = "",
    ns: str = ARXIV_NS,
) -> str:
    """One `<record>` in the arXiv metadata format, as arXiv's OAI-PMH returns it."""
    updated_xml = f"<updated>{updated}</updated>" if updated else ""
    return f"""
  <record>
    <header>
      <identifier>oai:arXiv.org:{doc_id}</identifier>
      <datestamp>2026-10-14</datestamp>
      <setSpec>cs</setSpec>
    </header>
    <metadata>
      <arXiv xmlns="{ns}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <id>{doc_id}</id>
        <created>{created}</created>{updated_xml}
        <authors>
          <author><keyname>Lovelace</keyname><forenames>Ada</forenames></author>
          <author><keyname>Turing</keyname><forenames>Alan  M.</forenames><suffix>Jr</suffix>
          </author>
        </authors>
        <title>Paper {doc_id}: a
  wrapped title</title>
        <categories>{categories}</categories>{extra}
        <license>http://creativecommons.org/licenses/by/4.0/</license>
        <abstract>  We study {doc_id}.
The abstract wraps lines.
</abstract>
      </arXiv>
    </metadata>
  </record>"""


DELETED = """
  <record>
    <header status="deleted">
      <identifier>oai:arXiv.org:2610.00009</identifier>
      <datestamp>2026-10-14</datestamp>
      <setSpec>cs</setSpec>
    </header>
  </record>"""


def page(records: str = "", token: str | None = None, error: str | None = None) -> bytes:
    """A whole ListRecords answer. `token=""` is the empty token that ends a list."""
    if error is not None:
        body = f'<error code="{error}">no records</error>'
    else:
        token_xml = ""
        if token is not None:
            token_xml = (
                f'<resumptionToken cursor="0" completeListSize="5">{token}</resumptionToken>'
            )
        body = f"<ListRecords>{records}{token_xml}</ListRecords>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="{OAI_NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <responseDate>2026-10-15T08:00:00Z</responseDate>
  <request verb="ListRecords">{URL}</request>
  {body}
</OAI-PMH>""".encode()


PAGE_1 = page(
    arxiv_record("2610.00001", "cs.CL")
    + arxiv_record("2610.00002", "cs.LG cs.CL", extra="<doi>10.1/x</doi>"),
    token="token-1",
)
PAGE_2 = page(
    arxiv_record("2610.00003", "cs.CL", updated="2026-10-14")
    + arxiv_record("2610.00004", "cs.CV")
    + DELETED,
    token="",
)


class FakeResponse:
    def __init__(
        self, content: bytes = b"", status_code: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeOai:
    """Serves the first page for a fresh request and `pages[token]` for a resumption request.
    `transient` answers (exceptions or FakeResponses) are returned first, in order."""

    def __init__(
        self,
        first: bytes = PAGE_1,
        pages: dict[str, bytes] | None = None,
        transient: list[Any] | None = None,
    ) -> None:
        self.first = first
        self.pages = {"token-1": PAGE_2} if pages is None else pages
        self.transient = transient or []
        self.calls: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []

    def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str], timeout: float):
        assert url == URL
        self.calls.append(dict(params))
        self.headers.append(headers)
        if self.transient:
            failure = self.transient.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        if "resumptionToken" in params:
            return FakeResponse(self.pages[params["resumptionToken"]])
        return FakeResponse(self.first)


def fetch(tmp_path: Path, session: FakeOai, sleeps: list[float] | None = None, **kwargs: Any):
    out = tmp_path / "new.jsonl"
    sleep = sleeps.append if sleeps is not None else (lambda _: None)
    kwargs.setdefault("from_date", date(2026, 10, 14))
    manifest = fetch_incremental(
        out, base_url=URL, session=session, sleep=sleep, log=quiet, **kwargs
    )
    return out, manifest


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- harvest ------------------------------------------------------------------------------------


def test_two_pages_follow_the_resumption_token_and_filter_the_category(tmp_path: Path) -> None:
    session = FakeOai()
    sleeps: list[float] = []
    out, manifest = fetch(
        tmp_path, session, sleeps, until=date(2026, 10, 14), set_spec="cs", category="cs.CL"
    )

    assert session.calls == [
        {
            "verb": "ListRecords",
            "metadataPrefix": "arXiv",
            "from": "2026-10-14",
            "until": "2026-10-14",
            "set": "cs",
        },
        # A resumption request carries only the verb and the token.
        {"verb": "ListRecords", "resumptionToken": "token-1"},
    ]
    assert all("User-Agent" in h for h in session.headers)
    assert sleeps == [3.0]  # one pause, before the second request
    # The cross-list (cs.LG cs.CL) is kept; cs.CV and the deleted record are not.
    assert [r["id"] for r in read_lines(out)] == ["2610.00001", "2610.00002", "2610.00003"]
    assert manifest["counts"] == {"harvested": 5, "deleted": 1, "not_in_category": 1, "kept": 3}
    assert manifest["pages"] == 2 and manifest["requests"] == 2
    assert manifest["from"] == "2026-10-14" and manifest["until"] == "2026-10-14"
    assert manifest["set"] == "cs" and manifest["category"] == "cs.CL"
    assert manifest["base_url"] == URL and manifest["response_date"] == "2026-10-15T08:00:00Z"
    assert manifest["output"]["name"] == "new.jsonl"
    assert manifest["output"]["bytes"] == out.stat().st_size
    on_disk = json.loads(manifest_path(out).read_text(encoding="utf-8"))
    assert on_disk == manifest and manifest_path(out).name == "new.manifest.json"
    assert not (tmp_path / "new.jsonl.part").exists()


def test_empty_category_keeps_every_record_and_no_set_or_until_is_sent(tmp_path: Path) -> None:
    session = FakeOai()
    out, manifest = fetch(tmp_path, session, set_spec=None, category="")
    assert session.calls[0] == {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
        "from": "2026-10-14",
    }
    assert len(read_lines(out)) == 4
    assert manifest["counts"]["kept"] == 4 and manifest["category"] is None
    assert manifest["set"] is None and manifest["until"] is None


def test_no_records_match_is_zero_records(tmp_path: Path) -> None:
    session = FakeOai(first=page(error="noRecordsMatch"))
    out, manifest = fetch(tmp_path, session)
    assert out.read_text(encoding="utf-8") == ""
    assert manifest["counts"] == {"harvested": 0, "deleted": 0, "not_in_category": 0, "kept": 0}
    assert manifest["pages"] == 0 and manifest["requests"] == 1
    assert len(session.calls) == 1


def test_other_oai_errors_fail_and_leave_no_output(tmp_path: Path) -> None:
    session = FakeOai(pages={"token-1": page(error="badResumptionToken")})
    with pytest.raises(OaiError, match="badResumptionToken") as exc:
        fetch(tmp_path, session)
    assert exc.value.code == "badResumptionToken"
    assert list(tmp_path.iterdir()) == []


def test_until_before_from_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="before"):
        fetch(tmp_path, FakeOai(), until=date(2026, 10, 13))


def test_namespace_change_does_not_break_parsing() -> None:
    moved = page(arxiv_record("2610.00001", "cs.CL", ns="http://arxiv.org/OAI/arXiv/v2/"))
    moved = moved.replace(OAI_NS.encode(), b"http://www.openarchives.org/OAI/3.0/")
    client = OaiClient(FakeOai(first=moved), base_url=URL, sleep=lambda _: None)
    records = list(list_records(client, from_date=date(2026, 10, 14)))
    assert [to_snapshot_record(r)["id"] for r in records] == ["2610.00001"]


# --- rate limit and retries ---------------------------------------------------------------------


def test_pause_between_requests_and_minimum_pause() -> None:
    sleeps: list[float] = []
    client = OaiClient(FakeOai(), base_url=URL, pause=4.5, sleep=sleeps.append)
    for _ in range(3):
        client.get({"verb": "Identify"})
    assert sleeps == [4.5, 4.5]  # none before the first request
    with pytest.raises(ValueError, match="at least 3"):
        OaiClient(FakeOai(), base_url=URL, pause=1.0)


def test_503_retry_after_is_honoured(tmp_path: Path) -> None:
    session = FakeOai(
        transient=[
            FakeResponse(status_code=503, headers={"Retry-After": "10"}),
            FakeResponse(status_code=503, headers={"Retry-After": "1"}),  # below the pause
            FakeResponse(status_code=503),  # no Retry-After: backoff 5 * 2**2 s
            TimeoutError("read timed out"),
        ]
    )
    sleeps: list[float] = []
    out, manifest = fetch(tmp_path, session, sleeps)
    assert sleeps == [10.0, 3.0, 20.0, 40.0, 3.0]  # 4 retries, then the pause before page 2
    assert len(session.calls) == 6
    assert manifest["requests"] == 5  # HTTP answers received; the timeout got none
    assert manifest["counts"]["kept"] == 3


def test_gives_up_after_max_retries(tmp_path: Path) -> None:
    session = FakeOai(transient=[FakeResponse(status_code=503)] * 3)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        fetch(tmp_path, session, max_retries=2)
    assert len(session.calls) == 3
    assert list(tmp_path.iterdir()) == []


# --- record shape -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        ("2024-09-30", "Mon, 30 Sep 2024 00:00:00 GMT"),
        ("2007-04-02", "Mon, 2 Apr 2007 00:00:00 GMT"),  # no leading zero, as in the snapshot
        ("2026-10-18", "Sun, 18 Oct 2026 00:00:00 GMT"),
        ("30 Sep 2024", None),
    ],
)
def test_rfc2822_day(day: str, expected: str | None) -> None:
    assert rfc2822_day(day) == expected


def test_record_has_the_snapshot_shape() -> None:
    client = OaiClient(FakeOai(), base_url=URL, sleep=lambda _: None)
    harvest = list_records(client, from_date=date(2026, 10, 14))
    records = [to_snapshot_record(r) for r in harvest if not is_deleted(r)]
    first, cross, updated = records[0], records[1], records[2]
    assert first == {
        "id": "2610.00001",
        "authors": "Ada Lovelace, Alan M. Turing Jr",
        "title": "Paper 2610.00001: a\n  wrapped title",
        "comments": None,
        "journal-ref": None,
        "doi": None,
        "report-no": None,
        "categories": "cs.CL",
        "license": "http://creativecommons.org/licenses/by/4.0/",
        "abstract": "  We study 2610.00001.\nThe abstract wraps lines.\n",
        "versions": [{"version": "v1", "created": "Mon, 12 Oct 2026 00:00:00 GMT"}],
        "update_date": "2026-10-12",
        "authors_parsed": [["Lovelace", "Ada", ""], ["Turing", "Alan M.", "Jr"]],
    }
    assert cross["doi"] == "10.1/x" and cross["categories"] == "cs.LG cs.CL"
    assert updated["update_date"] == "2026-10-14"
    assert updated["versions"][0]["created"] == "Mon, 12 Oct 2026 00:00:00 GMT"


def test_record_fields_are_the_snapshot_schema_fields() -> None:
    pytest.importorskip("pyspark")
    client = OaiClient(FakeOai(), base_url=URL, sleep=lambda _: None)
    record = to_snapshot_record(next(list_records(client, from_date=date(2026, 10, 14))))
    assert list(record) == clean.snapshot_schema().fieldNames()


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_incremental_fetch_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_fetch(out: Path, **kwargs: Any) -> dict[str, Any]:
        seen.update(out=out, **kwargs)
        return {}

    monkeypatch.setattr("scitech_pipelines.incremental.fetch_incremental", fake_fetch)
    args = ["--data-dir", str(tmp_path), "incremental-fetch", "--from", "2026-10-14"]
    assert main([*args, "--set", "cs:cs:CL"]) == 0
    # ":" is not allowed in Windows file names.
    assert seen["out"] == tmp_path / "raw" / "arxiv-oai" / "cs-cs-CL_2026-10-14_open.jsonl"
    assert seen["from_date"] == date(2026, 10, 14) and seen["until"] is None
    assert seen["set_spec"] == "cs:cs:CL" and seen["category"] == "cs.CL"
    assert seen["base_url"] == "https://oaipmh.arxiv.org/oai" and seen["pause"] == 3.0

    out = tmp_path / "x.jsonl"
    assert main([*args, "--until", "2026-10-15", "--out", str(out), "--category", ""]) == 0
    assert seen["out"] == out and seen["until"] == date(2026, 10, 15)
    assert seen["set_spec"] == "cs" and seen["category"] == ""
    with pytest.raises(SystemExit):
        main([*args[:-1], "14/10/2026"])
    with pytest.raises(SystemExit):
        main([*args, "--pause", "1"])


# --- the same `clean` code path (skipped without PySpark or Java, ADR 0005) ---------------------


@pytest.fixture(scope="module")
def spark():
    pytest.importorskip("pyspark")
    if not clean.java_available():
        pytest.skip("Java not found: Spark tests run in CI (ADR 0005)")
    session = clean.create_spark("local[1]", "1g")
    yield session
    session.stop()


def test_fetched_records_go_through_clean(spark, tmp_path: Path) -> None:
    out, _ = fetch(tmp_path, FakeOai())
    documents = tmp_path / "documents"

    manifest = clean.clean_arxiv(spark, out, documents, sample_size=0, log=quiet)

    counts = manifest["counts"]
    assert counts["records_in"] == counts["in_category"] == counts["records_out"] == 3
    assert counts["in_category_duckdb"] == 3  # DuckDB reads the same file
    rows = {r["doc_id"]: r.asDict() for r in spark.read.parquet(str(documents)).collect()}
    assert sorted(rows) == ["2610.00001", "2610.00002", "2610.00003"]
    doc = rows["2610.00003"]
    assert doc["title"] == "Paper 2610.00003: a wrapped title"
    assert doc["abstract"] == "We study 2610.00003. The abstract wraps lines."
    assert doc["authors"] == ["Ada Lovelace", "Alan M. Turing Jr"]
    assert doc["categories"] == ["cs.CL"]
    assert doc["published_at"] == date(2026, 10, 12) and doc["year"] == 2026
    assert doc["updated_at"] == date(2026, 10, 14)
    assert doc["url"] == "https://arxiv.org/abs/2610.00003" and doc["license"] == "CC0-1.0"
    assert rows["2610.00002"]["categories"] == ["cs.LG", "cs.CL"]
