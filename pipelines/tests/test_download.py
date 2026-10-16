"""Tests for the raw downloader (W2-D1-FAO-1). No network: Kaggle and the MediaWiki API are
replaced by fakes that return canned responses."""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scitech_pipelines.cli import main
from scitech_pipelines.download import (
    KaggleApiClient,
    WikiClient,
    crawl_category,
    download_arxiv,
    download_wikipedia,
    extract_zip,
    sha256_file,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"
SNAPSHOT = "arxiv-metadata-oai-snapshot.json"


def quiet(_: str) -> None:
    pass


class FakeKaggle:
    """Writes a zip with the fixture as the snapshot, like `dataset_download_files`."""

    def __init__(self, version_error: bool = False) -> None:
        self.downloads = 0
        self.version_error = version_error

    def remote_version(self, dataset: str) -> int | None:
        if self.version_error:
            raise ConnectionError("no metadata")
        return 307

    def remote_files(self, dataset: str) -> list[dict[str, Any]]:
        return [{"name": SNAPSHOT, "bytes": FIXTURE.stat().st_size, "created": "2026-10-10"}]

    def download_zip(self, dataset: str, out_dir: Path) -> Path:
        self.downloads += 1
        zip_path = out_dir / "arxiv.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.write(FIXTURE, SNAPSHOT)
        return zip_path


def test_arxiv_download_extracts_and_writes_manifest(tmp_path: Path) -> None:
    kaggle = FakeKaggle()
    manifest = download_arxiv(tmp_path, client=kaggle, log=quiet)

    snapshot = tmp_path / "arxiv" / SNAPSHOT
    assert snapshot.read_bytes() == FIXTURE.read_bytes()
    assert not (tmp_path / "arxiv" / "arxiv.zip").exists()
    on_disk = json.loads((tmp_path / "arxiv" / "manifest.json").read_text("utf-8"))
    assert on_disk == manifest
    assert manifest["source"] == "arxiv"
    assert manifest["url"] == "https://www.kaggle.com/datasets/Cornell-University/arxiv"
    assert manifest["version"] == 307
    assert manifest["files"] == [
        {"name": SNAPSHOT, "bytes": FIXTURE.stat().st_size, "sha256": sha256_file(FIXTURE)}
    ]
    assert manifest["remote_files"][0]["created"] == "2026-10-10"


def test_arxiv_rerun_skips_complete_download(tmp_path: Path) -> None:
    kaggle = FakeKaggle()
    first = download_arxiv(tmp_path, client=kaggle, log=quiet)
    second = download_arxiv(tmp_path, client=kaggle, log=quiet)
    assert kaggle.downloads == 1
    assert second == first


def test_arxiv_downloads_again_when_file_changed_or_forced(tmp_path: Path) -> None:
    kaggle = FakeKaggle()
    download_arxiv(tmp_path, client=kaggle, log=quiet)
    (tmp_path / "arxiv" / SNAPSHOT).write_text("truncated", encoding="utf-8")
    download_arxiv(tmp_path, client=kaggle, log=quiet)
    assert kaggle.downloads == 2
    download_arxiv(tmp_path, client=kaggle, force=True, log=quiet)
    assert kaggle.downloads == 3
    assert (tmp_path / "arxiv" / SNAPSHOT).read_bytes() == FIXTURE.read_bytes()


def test_arxiv_metadata_failure_does_not_block_download(tmp_path: Path) -> None:
    logged: list[str] = []
    manifest = download_arxiv(tmp_path, client=FakeKaggle(version_error=True), log=logged.append)
    assert manifest["version"] is None
    assert manifest["files"][0]["name"] == SNAPSHOT
    assert any("WARNING could not read the dataset version" in line for line in logged)


def test_kaggle_api_client_reads_version_and_files_from_kaggle_types() -> None:
    """The real wrapper against the response types of the `kaggle` package (no network)."""
    types = pytest.importorskip("kagglesdk.datasets.types.dataset_api_service")
    from datetime import datetime

    file = types.ApiDatasetFile()
    file.name = SNAPSHOT
    file.total_bytes = 5_610_000_000
    file.creation_date = datetime(2026, 10, 10, 3, 0)
    response = types.ApiListDatasetFilesResponse()
    response.dataset_files = [file]

    class FakeApi:
        def dataset_status(self, dataset: str, format: str | None = None) -> str:
            assert format == "json(current_version_number)"
            return json.dumps({"current_version_number": 307})

        def dataset_list_files(self, dataset: str):
            return response

    client = KaggleApiClient(api=FakeApi())
    assert client.remote_version("Cornell-University/arxiv") == 307
    assert client.remote_files("Cornell-University/arxiv") == [
        {"name": SNAPSHOT, "bytes": 5_610_000_000, "created": "2026-10-10 03:00:00"}
    ]


def test_extract_zip_keeps_files_inside_out_dir(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../../escaped.txt", "x")
    out = tmp_path / "out"
    out.mkdir()
    assert extract_zip(zip_path, out, quiet) == [out / "escaped.txt"]
    assert not (tmp_path / "escaped.txt").exists()


# --- Wikipedia ----------------------------------------------------------------------------------

ROOT = "Category:Natural language processing"
CATEGORIES = {
    ROOT: [
        [
            {"ns": 0, "pageid": 1, "title": "Natural language processing"},
            {"ns": 14, "title": "Category:Machine translation"},
        ],
        [
            {"ns": 0, "pageid": 2, "title": "Tokenization"},
            {"ns": 14, "title": "Category:Language models"},
        ],
    ],
    "Category:Machine translation": [
        [
            {"ns": 0, "pageid": 3, "title": "Machine translation"},
            {"ns": 0, "pageid": 1, "title": "Natural language processing"},
            {"ns": 14, "title": "Category:Too deep"},
        ]
    ],
    "Category:Language models": [
        [{"ns": 0, "pageid": 4, "title": "Large language model"}, {"ns": 14, "title": ROOT}]
    ],
    "Category:Too deep": [[{"ns": 0, "pageid": 99, "title": "Deep page"}]],
}
EMPTY_PAGES = {2}


class FakeResponse:
    def __init__(
        self, data: dict[str, Any], status_code: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.data = data
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self.data


class FakeWiki:
    """Answers `list=categorymembers` (with continuation) and page-text queries."""

    def __init__(
        self,
        maxlag_first: bool = False,
        fail_on_page: int | None = None,
        transient: list[Any] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.maxlag_first = maxlag_first
        self.fail_on_page = fail_on_page
        self.transient = transient or []  # exceptions or FakeResponses returned first, in order

    def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str], timeout: float):
        self.calls.append(params)
        self.headers.append(headers)
        if self.transient:
            failure = self.transient.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        if self.maxlag_first:
            self.maxlag_first = False
            return FakeResponse({"error": {"code": "maxlag", "info": "lagged"}})
        if params.get("list") == "categorymembers":
            batches = CATEGORIES.get(params["cmtitle"], [[]])
            index = int(params.get("cmcontinue", 0))
            data: dict[str, Any] = {"query": {"categorymembers": batches[index]}}
            if index + 1 < len(batches):
                data["continue"] = {"cmcontinue": str(index + 1), "continue": "-||"}
            return FakeResponse(data)
        pageid = int(params["pageids"])
        if pageid == self.fail_on_page:
            raise ConnectionError("network down")
        text = "" if pageid in EMPTY_PAGES else f"Text of page {pageid}."
        return FakeResponse(
            {
                "query": {
                    "pages": [
                        {
                            "pageid": pageid,
                            "title": f"Page {pageid}",
                            "extract": text,
                            "fullurl": f"https://en.wikipedia.org/wiki/Page_{pageid}",
                            "revisions": [
                                {"revid": 1000 + pageid, "timestamp": "2026-10-01T00:00:00Z"}
                            ],
                        }
                    ]
                }
            }
        )


def no_sleep(_: float) -> None:
    pass


def test_crawl_follows_continuation_and_depth_limit() -> None:
    wiki = WikiClient(FakeWiki(), sleep=no_sleep)
    pages = crawl_category(wiki, ROOT, max_depth=1, log=quiet)
    assert [p["pageid"] for p in pages] == [1, 2, 3, 4]
    assert pages[2] == {
        "pageid": 3,
        "title": "Machine translation",
        "depth": 1,
        "category": "Category:Machine translation",
    }
    assert [p["pageid"] for p in crawl_category(wiki, ROOT, max_depth=0, log=quiet)] == [1, 2]


def test_wiki_client_pauses_retries_maxlag_and_sends_user_agent() -> None:
    session = FakeWiki(maxlag_first=True)
    sleeps: list[float] = []
    wiki = WikiClient(session, user_agent="test-agent", pause=1.5, sleep=sleeps.append)
    data = wiki.get({"list": "categorymembers", "cmtitle": ROOT})
    assert data["query"]["categorymembers"]
    assert sleeps == [1.5, 5.0, 1.5]
    assert all(h == {"User-Agent": "test-agent"} for h in session.headers)
    assert session.calls[0]["maxlag"] == "5" and session.calls[0]["format"] == "json"


def test_wiki_client_retries_transient_errors_with_backoff() -> None:
    session = FakeWiki(
        transient=[
            TimeoutError("read timed out"),
            FakeResponse({}, status_code=429, headers={"Retry-After": "30"}),
            FakeResponse({}, status_code=503),
        ]
    )
    sleeps: list[float] = []
    wiki = WikiClient(session, pause=1.0, sleep=sleeps.append)
    assert wiki.get({"list": "categorymembers", "cmtitle": ROOT})["query"]["categorymembers"]
    assert sleeps == [5.0, 30.0, 20.0, 1.0]  # backoff 5 s, Retry-After, backoff 20 s, pause


def test_wiki_client_gives_up_after_max_retries() -> None:
    session = FakeWiki(transient=[FakeResponse({}, status_code=503)] * 3)
    wiki = WikiClient(session, sleep=no_sleep, max_retries=2)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        wiki.get({"list": "categorymembers", "cmtitle": ROOT})
    assert len(session.calls) == 3


def read_pages(out: Path) -> list[dict[str, Any]]:
    text = (out / "wikipedia" / "pages.jsonl").read_text("utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_wikipedia_download_writes_pages_and_manifest(tmp_path: Path) -> None:
    manifest = download_wikipedia(
        tmp_path, session=FakeWiki(), max_depth=1, sleep=no_sleep, log=quiet
    )
    pages = read_pages(tmp_path)
    assert [p["pageid"] for p in pages] == [1, 3, 4]  # page 2 has no text
    assert pages[0] == {
        "pageid": 1,
        "title": "Page 1",
        "url": "https://en.wikipedia.org/wiki/Page_1",
        "revid": 1001,
        "revision_timestamp": "2026-10-01T00:00:00Z",
        "text": "Text of page 1.",
        "depth": 0,
        "category": ROOT,
    }
    assert manifest["licence"] == "CC BY-SA 4.0"
    assert manifest["pages_listed"] == 4
    assert manifest["pages_downloaded"] == 3
    assert manifest["pages_without_text"] == 1
    assert manifest["pages_listed_by_depth"] == {"0": 2, "1": 2}
    assert manifest["pages_downloaded_by_depth"] == {"0": 1, "1": 2}
    assert [f["name"] for f in manifest["files"]] == [
        "category_members.json",
        "pages.jsonl",
        "pages_without_text.txt",
    ]


def test_wikipedia_resumes_after_interruption_and_skips_when_complete(tmp_path: Path) -> None:
    with pytest.raises(ConnectionError):
        download_wikipedia(
            tmp_path, session=FakeWiki(fail_on_page=3), max_depth=1, sleep=no_sleep, log=quiet
        )
    assert [p["pageid"] for p in read_pages(tmp_path)] == [1]
    assert not (tmp_path / "wikipedia" / "manifest.json").exists()

    session = FakeWiki()
    download_wikipedia(tmp_path, session=session, max_depth=1, sleep=no_sleep, log=quiet)
    fetched = [c["pageids"] for c in session.calls if "pageids" in c]
    # cached crawl reused; page 1 (downloaded) and page 2 (no text) are not requested again
    assert fetched == ["3", "4"]
    assert [p["pageid"] for p in read_pages(tmp_path)] == [1, 3, 4]

    session = FakeWiki()
    download_wikipedia(tmp_path, session=session, max_depth=1, sleep=no_sleep, log=quiet)
    assert session.calls == []


def test_wikipedia_drops_a_cut_off_last_line(tmp_path: Path) -> None:
    source = tmp_path / "wikipedia"
    source.mkdir()
    (source / "pages.jsonl").write_text('{"pageid": 1, "text": "ok"}\n{"pageid": 3, "te', "utf-8")
    session = FakeWiki()
    download_wikipedia(tmp_path, session=session, max_depth=1, sleep=no_sleep, log=quiet)
    assert [c["pageids"] for c in session.calls if "pageids" in c] == ["2", "3", "4"]
    assert [p["pageid"] for p in read_pages(tmp_path)] == [1, 3, 4]


def test_cli_download_uses_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_wikipedia(out: Path, **kwargs: Any) -> dict[str, Any]:
        seen.update(out=out, **kwargs)
        return {}

    monkeypatch.setattr("scitech_pipelines.download.download_wikipedia", fake_wikipedia)
    args = ["--data-dir", str(tmp_path), "download", "--source", "wikipedia", "--wiki-depth", "1"]
    assert main(args) == 0
    assert seen["out"] == tmp_path / "raw"
    assert seen["max_depth"] == 1 and seen["pause"] == 1.0 and seen["force"] is False
