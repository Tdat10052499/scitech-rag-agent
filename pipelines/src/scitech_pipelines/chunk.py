"""Split cleaned documents into chunks (W3-D1-FAO-1). Output: `docs/contracts/chunk.schema.json`.

Each chunk's `text` is the title, then a window of the abstract (`<title>. <words>`), so every
chunk can be read and embedded on its own (issue #7, C7). An abstract that fits in `max_words`
together with its title gives one chunk; a longer one gives overlapping windows of
`overlap_words` words. Lengths are counted in words, not tokens, because the embedding model is
chosen after this step (ADR 0007); the step takes seconds, so it can be re-run with the model's
limit. I/O uses DuckDB, so it runs on Windows without Java (ADR 0005).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scitech_pipelines.clean import CLEAN_MANIFEST
from scitech_pipelines.validate import _quote, documents_glob

CHUNK_FILE = "chunks.parquet"
CHUNK_MANIFEST = "_chunk_manifest.json"
OUTPUT_FILES = (CHUNK_FILE, CHUNK_MANIFEST)  # the only files a re-run replaces in --out
DEFAULT_MAX_WORDS = 320
DEFAULT_OVERLAP_WORDS = 48
# Fields of chunk.schema.json and their Parquet types. `embedding_model` is set by `embed`.
COLUMNS = {
    "chunk_id": "VARCHAR",
    "doc_id": "VARCHAR",
    "source": "VARCHAR",
    "title": "VARCHAR",
    "text": "VARCHAR",
    "chunk_index": "INTEGER",
    "authors": "VARCHAR[]",
    "categories": "VARCHAR[]",
    "published_at": "VARCHAR",
    "url": "VARCHAR",
    "license": "VARCHAR",
}
BATCH = 10_000

Log = Callable[[str], None]


def check_sizes(max_words: int, overlap_words: int) -> None:
    if max_words < 2 or not 0 <= overlap_words < max_words // 2:
        raise ValueError(
            f"need max_words >= 2 and 0 <= overlap_words < max_words / 2, "
            f"got {max_words} and {overlap_words}"
        )


def windows(words: list[str], size: int, overlap: int) -> list[list[str]]:
    """Consecutive windows of `size` words, each sharing `overlap` words with the previous one.
    The last window ends at the last word."""
    if len(words) <= size:
        return [words]
    step = size - overlap
    out = []
    start = 0
    while True:
        out.append(words[start : start + size])
        if start + size >= len(words):
            return out
        start += step


def chunk_document(
    doc: dict[str, Any],
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[dict[str, Any]]:
    """Chunks of one cleaned document. `text` is `<title>. <abstract window>`; a window gets at
    least half of `max_words`, so a very long title can push a chunk over `max_words`."""
    check_sizes(max_words, overlap_words)
    title = doc["title"]
    title_words = len(title.split())
    size = max(max_words - title_words, max_words // 2)
    separator = " " if title.endswith((".", "?", "!")) else ". "
    published = doc.get("published_at")
    chunks = []
    for index, window in enumerate(windows(doc["abstract"].split(), size, overlap_words)):
        chunks.append(
            {
                "chunk_id": f"{doc['doc_id']}#{index}",
                "doc_id": doc["doc_id"],
                "source": doc["source"],
                "title": title,
                "text": title + separator + " ".join(window),
                "chunk_index": index,
                "authors": list(doc.get("authors") or []),
                "categories": list(doc.get("categories") or []),
                "published_at": published.isoformat() if published else None,
                "url": doc.get("url"),
                "license": doc.get("license"),
            }
        )
    return chunks


def _documents(con, documents: Path) -> Iterator[dict[str, Any]]:
    fields = ["doc_id", "source", "title", "abstract", "authors", "categories"]
    fields += ["published_at", "url", "license"]
    result = con.execute(
        f"SELECT {', '.join(fields)} FROM read_parquet("
        f"{_quote(documents_glob(documents))}, hive_partitioning = true) ORDER BY doc_id"
    )
    while rows := result.fetchmany(BATCH):
        for row in rows:
            yield dict(zip(fields, row, strict=True))


def _write_jsonl(chunks: Iterable[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps({k: v for k, v in chunk.items() if v is not None}) + "\n")


def chunk_documents(
    documents: Path,
    out: Path,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
    log: Log = print,
) -> dict[str, Any]:
    """Chunk every cleaned document into `<out>/chunks.parquet` and write `_chunk_manifest.json`.
    Re-running replaces those two files; an `out` holding anything else is refused, so a wrong
    `--out` cannot delete other data."""
    import duckdb

    check_sizes(max_words, overlap_words)
    if not (documents / CLEAN_MANIFEST).is_file():
        raise FileNotFoundError(f"{documents / CLEAN_MANIFEST} not found (run `clean` first)")
    started = time.monotonic()
    others = (
        sorted(p.name for p in out.iterdir() if p.name not in OUTPUT_FILES) if out.is_dir() else []
    )
    if others:
        raise ValueError(
            f"{out} holds other files ({', '.join(others[:5])}); --out must be a directory "
            "for chunks only"
        )
    out.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_FILES:
        (out / name).unlink(missing_ok=True)
    con = duckdb.connect()
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        staged = Path(tmp) / "chunks.jsonl"
        _write_jsonl(
            (
                chunk
                for doc in _documents(con, documents)
                for chunk in chunk_document(doc, max_words, overlap_words)
            ),
            staged,
        )
        columns = ", ".join(f"{name}: '{kind}'" for name, kind in COLUMNS.items())
        con.execute(
            f"COPY (SELECT * FROM read_json({_quote(staged.as_posix())}, "
            f"format = 'newline_delimited', columns = {{{columns}}}) ORDER BY doc_id, chunk_index) "
            f"TO {_quote((out / CHUNK_FILE).as_posix())} (FORMAT parquet)"
        )
    con.execute(
        f"CREATE VIEW chunks AS SELECT *, len(string_split(text, ' ')) AS words "
        f"FROM read_parquet({_quote((out / CHUNK_FILE).as_posix())})"
    )
    n_chunks, n_docs, unique = con.execute(
        "SELECT count(*), count(DISTINCT doc_id), count(DISTINCT chunk_id) = count(*) FROM chunks"
    ).fetchone()
    lo, median, p95, hi, mean = con.execute(
        "SELECT min(words), quantile_cont(words, 0.5), quantile_cont(words, 0.95), max(words), "
        "avg(words) FROM chunks"
    ).fetchone()
    per_doc = dict(
        con.execute(
            "SELECT n, count(*) FROM (SELECT doc_id, count(*) AS n FROM chunks GROUP BY doc_id) "
            "GROUP BY n ORDER BY n"
        ).fetchall()
    )
    over = con.execute(f"SELECT count(*) FROM chunks WHERE words > {max_words}").fetchone()[0]
    con.close()
    if not unique:
        raise RuntimeError("chunk_id is not unique: the cleaned documents have duplicate doc_id")
    manifest = {
        "step": "chunk",
        "documents": str(documents),
        "chunked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.monotonic() - started, 1),
        "max_words": max_words,
        "overlap_words": overlap_words,
        "counts": {
            "documents": n_docs,
            "chunks": n_chunks,
            "chunks_per_document": {str(k): v for k, v in per_doc.items()},
            "chunks_over_max_words": over,
        },
        "words_per_chunk": {
            "min": lo,
            "median": median,
            "p95": p95,
            "max": hi,
            "mean": round(mean, 1) if mean is not None else None,
        },
        "bytes": (out / CHUNK_FILE).stat().st_size,
    }
    (out / CHUNK_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(
        f"chunk: {n_docs:,} documents -> {n_chunks:,} chunks "
        f"({n_chunks / n_docs if n_docs else 0:.3f} per document), words per chunk "
        f"median {median}, p95 {p95}, max {hi}; {manifest['seconds']} s -> {out}"
    )
    return manifest


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {value!r}") from None
