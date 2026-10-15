"""Raw downloader (W2-D1-FAO-1): the sources of ADR 0003 into `<out>/<source>/`.

- `arxiv`: the Kaggle arXiv metadata snapshot (`Cornell-University/arxiv`), one JSON Lines file.
  Kaggle resumes a partial zip; the zip is extracted and then deleted.
- `wikipedia`: English Wikipedia pages under `Category:Natural language processing` and its
  subcategories (MediaWiki API, plain-text extracts), one JSON object per page in `pages.jsonl`.
  Requests are serial with a pause between them; an interrupted crawl resumes where it stopped.

Each source directory gets a `manifest.json` (source, URL, date, file sizes, SHA-256 checksums).
A re-run skips a source whose manifest lists files that are all present with the same size.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

ARXIV_DATASET = "Cornell-University/arxiv"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_ROOT_CATEGORY = "Category:Natural language processing"
DEFAULT_USER_AGENT = (
    "scitech-rag-agent/0.1 (course project; https://github.com/Tdat10052499/scitech-rag-agent)"
)
MANIFEST = "manifest.json"
CHUNK = 16 * 1024 * 1024

Log = Callable[[str], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def file_entry(path: Path) -> dict[str, Any]:
    """Describe one output file for the manifest."""
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def read_manifest(source_dir: Path) -> dict[str, Any] | None:
    path = source_dir / MANIFEST
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(source_dir: Path, manifest: dict[str, Any]) -> None:
    """Write the manifest atomically, so an interrupted run never leaves a half-written file."""
    tmp = source_dir / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(source_dir / MANIFEST)


def is_complete(source_dir: Path, manifest: dict[str, Any] | None) -> bool:
    """True if every file listed in the manifest exists with the recorded size."""
    if not manifest or not manifest.get("files"):
        return False
    for entry in manifest["files"]:
        path = source_dir / entry["name"]
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            return False
    return True


# --- arXiv (Kaggle) -----------------------------------------------------------------------------


class KaggleClient(Protocol):
    def remote_files(self, dataset: str) -> list[dict[str, Any]]: ...

    def download_zip(self, dataset: str, out_dir: Path) -> Path: ...


class KaggleApiClient:
    """Thin wrapper around the `kaggle` package. Imported lazily: importing `kaggle` checks for
    credentials, which tests and CI do not have. Log in once with `kaggle auth login`."""

    def __init__(self) -> None:
        from kaggle.api.kaggle_api_extended import KaggleApi

        self.api = KaggleApi()
        self.api.authenticate()

    def remote_files(self, dataset: str) -> list[dict[str, Any]]:
        response = self.api.dataset_list_files(dataset)
        files = getattr(response, "files", None) or []
        return [
            {
                "name": getattr(f, "name", None),
                "bytes": getattr(f, "total_bytes", None),
                "created": str(getattr(f, "creation_date", "")) or None,
            }
            for f in files
        ]

    def download_zip(self, dataset: str, out_dir: Path) -> Path:
        # force=False lets the Kaggle client resume a partial zip and skip a complete one.
        self.api.dataset_download_files(dataset, path=str(out_dir), force=False, quiet=False)
        return out_dir / (dataset.split("/")[-1] + ".zip")


def extract_zip(zip_path: Path, out_dir: Path, log: Log = print) -> list[Path]:
    """Extract every file of the zip into out_dir (flat; member paths are reduced to their file
    name, so a crafted name cannot escape out_dir). Each file is written to a temporary name
    first and renamed when complete."""
    extracted = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if not name:
                continue
            target = out_dir / name
            tmp = out_dir / (name + ".part")
            log(f"extracting {name} ({member.file_size:,} bytes)")
            with archive.open(member) as src, tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            tmp.replace(target)
            extracted.append(target)
    return extracted


def download_arxiv(
    out: Path,
    *,
    client: KaggleClient | None = None,
    dataset: str = ARXIV_DATASET,
    force: bool = False,
    keep_zip: bool = False,
    log: Log = print,
) -> dict[str, Any]:
    """Download and extract the Kaggle arXiv snapshot into `<out>/arxiv/`."""
    source_dir = out / "arxiv"
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(source_dir)
    if not force and is_complete(source_dir, manifest):
        log(f"arxiv: complete in {source_dir} (manifest {manifest['downloaded_at']}), skipping")
        return manifest

    started = time.monotonic()
    client = client or KaggleApiClient()
    try:
        remote = client.remote_files(dataset)
    except Exception as exc:  # metadata only; the download itself must not depend on it
        log(f"arxiv: could not list remote files ({exc}); continuing")
        remote = []
    zip_path = client.download_zip(dataset, source_dir)
    zip_bytes = zip_path.stat().st_size
    extracted = extract_zip(zip_path, source_dir, log)
    log("computing checksums")
    manifest = {
        "source": "arxiv",
        "dataset": dataset,
        "url": f"https://www.kaggle.com/datasets/{dataset}",
        "licence": "CC0-1.0 (metadata); see ADR 0003",
        "downloaded_at": _now(),
        "seconds": round(time.monotonic() - started, 1),
        "zip_bytes": zip_bytes,
        "remote_files": remote,
        "files": [file_entry(path) for path in extracted],
    }
    write_manifest(source_dir, manifest)
    if not keep_zip:
        zip_path.unlink()
    for entry in manifest["files"]:
        log(f"arxiv: {entry['name']} {entry['bytes']:,} bytes, sha256 {entry['sha256'][:12]}...")
    return manifest


# --- Wikipedia (MediaWiki API) ------------------------------------------------------------------


class HttpSession(Protocol):
    def get(self, url: str, *, params: dict[str, Any], headers: dict[str, str], timeout: float):
        ...


class WikiClient:
    """Serial MediaWiki API client: one request at a time, a pause after each, and a retry when
    the API reports replication lag (`maxlag`), as the Wikimedia API etiquette asks."""

    def __init__(
        self,
        session: HttpSession,
        *,
        api: str = WIKI_API,
        user_agent: str = DEFAULT_USER_AGENT,
        pause: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
    ) -> None:
        self.session = session
        self.api = api
        self.headers = {"User-Agent": user_agent}
        self.pause = pause
        self.sleep = sleep
        self.max_retries = max_retries
        self.requests = 0

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        query = {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5", **params}
        for attempt in range(self.max_retries + 1):
            response = self.session.get(self.api, params=query, headers=self.headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            self.requests += 1
            self.sleep(self.pause)
            error = data.get("error")
            if not error:
                return data
            if error.get("code") == "maxlag" and attempt < self.max_retries:
                self.sleep(5.0)
                continue
            raise RuntimeError(f"MediaWiki API error: {error}")
        raise RuntimeError("MediaWiki API: retries exhausted")


def crawl_category(
    wiki: WikiClient, root: str, max_depth: int, log: Log = print
) -> list[dict[str, Any]]:
    """Breadth-first walk of a category tree. Returns the article pages (namespace 0), each with
    the depth and category where it was first found. Subcategories deeper than max_depth are not
    entered (root is depth 0)."""
    pages: dict[int, dict[str, Any]] = {}
    seen = {root}
    queue = [(root, 0)]
    while queue:
        category, depth = queue.pop(0)
        params: dict[str, Any] = {
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "page|subcat",
            "cmnamespace": "0|14",
            "cmlimit": "max",
        }
        while True:
            data = wiki.get(params)
            for member in data.get("query", {}).get("categorymembers", []):
                if member["ns"] == 14:
                    if depth < max_depth and member["title"] not in seen:
                        seen.add(member["title"])
                        queue.append((member["title"], depth + 1))
                elif member["ns"] == 0 and member["pageid"] not in pages:
                    pages[member["pageid"]] = {
                        "pageid": member["pageid"],
                        "title": member["title"],
                        "depth": depth,
                        "category": category,
                    }
            if "continue" not in data:
                break
            params = {**params, **data["continue"]}
    log(f"wikipedia: {len(pages):,} pages in {len(seen):,} categories (depth <= {max_depth})")
    return sorted(pages.values(), key=lambda p: p["pageid"])


def fetch_page(wiki: WikiClient, pageid: int) -> dict[str, Any] | None:
    """Fetch one page as plain text with its URL and current revision. None if it has no text."""
    data = wiki.get(
        {
            "pageids": str(pageid),
            "prop": "extracts|info|revisions",
            "explaintext": "1",
            "exsectionformat": "plain",
            "inprop": "url",
            "rvprop": "ids|timestamp",
        }
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or not pages[0].get("extract", "").strip():
        return None
    page = pages[0]
    revision = (page.get("revisions") or [{}])[0]
    return {
        "pageid": page["pageid"],
        "title": page["title"],
        "url": page.get("fullurl"),
        "revid": revision.get("revid"),
        "revision_timestamp": revision.get("timestamp"),
        "text": page["extract"],
    }


def _done_pageids(path: Path) -> set[int]:
    """Page ids already in pages.jsonl. A last line cut off by an interrupted run is dropped."""
    if not path.is_file():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    done, good = set(), []
    for line in lines:
        try:
            done.add(json.loads(line)["pageid"])
            good.append(line)
        except (json.JSONDecodeError, KeyError):
            break
    if len(good) != len(lines) or (good and not good[-1].endswith("\n")):
        path.write_text("".join(g if g.endswith("\n") else g + "\n" for g in good), "utf-8")
    return done


def download_wikipedia(
    out: Path,
    *,
    session: HttpSession | None = None,
    root: str = WIKI_ROOT_CATEGORY,
    max_depth: int = 2,
    max_pages: int | None = None,
    pause: float = 1.0,
    user_agent: str = DEFAULT_USER_AGENT,
    force: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    log: Log = print,
) -> dict[str, Any]:
    """Crawl the category tree and download page texts into `<out>/wikipedia/`."""
    source_dir = out / "wikipedia"
    source_dir.mkdir(parents=True, exist_ok=True)
    settings = {"root": root, "max_depth": max_depth, "max_pages": max_pages}
    manifest = read_manifest(source_dir)
    if (
        not force
        and is_complete(source_dir, manifest)
        and manifest.get("settings") == settings
    ):
        log(f"wikipedia: complete in {source_dir} (manifest {manifest['downloaded_at']}), skipping")
        return manifest

    if session is None:
        import requests

        session = requests.Session()
    wiki = WikiClient(session, user_agent=user_agent, pause=pause, sleep=sleep)
    started = time.monotonic()

    members_path = source_dir / "category_members.json"
    pages_path = source_dir / "pages.jsonl"
    if force:
        members_path.unlink(missing_ok=True)
        pages_path.unlink(missing_ok=True)
    cached = json.loads(members_path.read_text("utf-8")) if members_path.is_file() else None
    if cached and cached.get("settings") == settings:
        members = cached["pages"]
        log(f"wikipedia: using cached category crawl ({len(members):,} pages)")
    else:
        members = crawl_category(wiki, root, max_depth, log)
        if max_pages is not None:
            members = members[:max_pages]
        members_path.write_text(
            json.dumps({"settings": settings, "pages": members}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    done = _done_pageids(pages_path)
    todo = [m for m in members if m["pageid"] not in done]
    log(f"wikipedia: {len(done):,} pages already downloaded, {len(todo):,} to go")
    empty = 0
    with pages_path.open("a", encoding="utf-8") as f:
        for i, member in enumerate(todo, 1):
            page = fetch_page(wiki, member["pageid"])
            if page is None:
                empty += 1
                continue
            page.update(depth=member["depth"], category=member["category"])
            f.write(json.dumps(page, ensure_ascii=False) + "\n")
            f.flush()
            if i % 100 == 0:
                log(f"wikipedia: {i:,}/{len(todo):,}")

    manifest = {
        "source": "wikipedia",
        "url": f"https://en.wikipedia.org/wiki/{root.replace(' ', '_')}",
        "api": WIKI_API,
        "licence": "CC BY-SA 4.0",
        "settings": settings,
        "downloaded_at": _now(),
        "seconds": round(time.monotonic() - started, 1),
        "requests": wiki.requests,
        "pages_listed": len(members),
        "pages_without_text_this_run": empty,
        "files": [file_entry(members_path), file_entry(pages_path)],
    }
    write_manifest(source_dir, manifest)
    pages = len(_done_pageids(pages_path))
    log(f"wikipedia: {pages:,} pages in {pages_path} ({manifest['files'][1]['bytes']:,} bytes)")
    return manifest
