"""Embed the chunks (W3-D2-FAO-1). Output: one vector per `chunk_id`, for `load`.

Vectors go to `<out>/part-NNNNN.parquet` with the columns `chunk_id`, `embedding` (float32,
L2-normalised, so the dot product is the cosine similarity) and `embedding_model` (the
`embedding_model` field of `docs/contracts/chunk.schema.json`). Chunks are taken in `chunk_id`
order and split into parts of `part_size`; each finished part is written at once, so an
interrupted run resumes at the first missing part. The settings of a run are kept in
`_embed_state.json`, and a resume with other settings (model, prefix, part size, other chunks)
fails instead of mixing vectors. `_embed_manifest.json` records counts and throughput for
ADR 0007. The model comes from `--model`/`EMBEDDING_MODEL`, never from the code.
"""

from __future__ import annotations

import json
import math
import os
import platform
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from scitech_pipelines.chunk import CHUNK_FILE, CHUNK_MANIFEST
from scitech_pipelines.validate import _quote

EMBED_MANIFEST = "_embed_manifest.json"
EMBED_STATE = "_embed_state.json"
DEFAULT_BATCH_SIZE = 64
DEFAULT_PART_SIZE = 8192

Log = Callable[[str], None]


class Encoder(Protocol):
    """What `embed_chunks` needs from a model. `encode` returns one L2-normalised row per text,
    as a 2-D float array of shape (len(texts), dimension)."""

    name: str
    dimension: int

    def encode(self, texts: Sequence[str]) -> Any: ...

    def info(self) -> dict[str, Any]: ...


class SentenceTransformerEncoder:
    """An open embedding model run locally with sentence-transformers (GPU if available)."""

    def __init__(
        self, name: str, *, batch_size: int = DEFAULT_BATCH_SIZE, device: str | None = None
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "embed needs sentence-transformers: pip install -r pipelines/requirements-embed.txt"
            ) from e
        self.name = name
        self.batch_size = batch_size
        self.model = SentenceTransformer(name, device=device)
        # Renamed in sentence-transformers 6; older versions only have the long name.
        dimension = getattr(self.model, "get_embedding_dimension", None)
        self.dimension = (dimension or self.model.get_sentence_embedding_dimension)()

    def encode(self, texts: Sequence[str]) -> Any:
        return self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    def info(self) -> dict[str, Any]:
        import sentence_transformers
        import torch

        device = str(self.model.device)
        return {
            "device": device,
            "gpu": torch.cuda.get_device_name(0) if device.startswith("cuda") else None,
            "batch_size": self.batch_size,
            "max_seq_length": self.model.max_seq_length,
            "sentence_transformers": sentence_transformers.__version__,
            "torch": torch.__version__,
        }


def check_model_name(name: str | None) -> str:
    name = (name or "").strip()
    if not name or name == "replace-me":
        raise ValueError("no embedding model: pass --model or set EMBEDDING_MODEL (ADR 0007)")
    return name


def _read_chunks(chunks: Path, limit: int | None) -> list[tuple[str, str]]:
    import duckdb

    con = duckdb.connect()
    sql = f"SELECT chunk_id, text FROM read_parquet({_quote((chunks / CHUNK_FILE).as_posix())}) "
    sql += "ORDER BY chunk_id" + (f" LIMIT {int(limit)}" if limit else "")
    rows = con.execute(sql).fetchall()
    con.close()
    return rows


def _write_part(path: Path, ids: list[str], vectors: Any, model: str) -> None:
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    flat = np.ascontiguousarray(vectors, dtype=np.float32).reshape(-1)
    table = pa.table(
        {
            "chunk_id": pa.array(ids, pa.string()),
            "embedding": pa.FixedSizeListArray.from_arrays(pa.array(flat), len(flat) // len(ids)),
            "embedding_model": pa.array([model] * len(ids), pa.string()).dictionary_encode(),
        }
    )
    staged = path.with_name(path.name + ".tmp")
    pq.write_table(table, staged)
    os.replace(staged, path)


def _check_output(out: Path, expected: int, dimension: int) -> None:
    import duckdb

    con = duckdb.connect()
    n, distinct, bad = con.execute(
        "SELECT count(*), count(DISTINCT chunk_id), "
        f"count(*) FILTER (WHERE len(embedding) <> {dimension}) "
        f"FROM read_parquet({_quote((out / 'part-*.parquet').as_posix())})"
    ).fetchone()
    con.close()
    if (n, distinct, bad) != (expected, expected, 0):
        raise RuntimeError(
            f"embed output check failed: {n} vectors, {distinct} distinct chunk_id, "
            f"{bad} with a dimension other than {dimension}; expected {expected} (use --force)"
        )


def _own_files(out: Path) -> list[Path]:
    """The files of this step in `out`. Anything else there is refused, so a wrong `--out`
    (e.g. `data/processed`) is never written into or deleted by `--force`."""
    if not out.is_dir():
        return []
    own, others = [], []
    for path in out.iterdir():
        is_own = path.name in (EMBED_STATE, EMBED_MANIFEST) or (
            path.name.startswith("part-") and path.name.endswith((".parquet", ".parquet.tmp"))
        )
        (own if is_own and path.is_file() else others).append(path)
    if others:
        names = ", ".join(sorted(p.name for p in others)[:5])
        raise ValueError(f"{out} holds other files ({names}); --out must be for embeddings only")
    return own


def _complete_manifest(out: Path, dimension: int) -> dict[str, Any] | None:
    """The manifest of a finished run whose parts are all still there, else None."""
    if not (out / EMBED_MANIFEST).is_file():
        return None
    manifest = json.loads((out / EMBED_MANIFEST).read_text(encoding="utf-8"))
    try:
        _check_output(out, manifest["counts"]["chunks"], dimension)
    except Exception:  # a missing or unreadable part: resume instead
        return None
    return manifest


def embed_chunks(
    chunks: Path,
    out: Path,
    encoder: Encoder,
    *,
    part_size: int = DEFAULT_PART_SIZE,
    passage_prefix: str = "",
    limit: int | None = None,
    force: bool = False,
    log: Log = print,
) -> dict[str, Any]:
    """Embed `<chunks>/chunks.parquet` into `<out>/part-*.parquet` and write the manifest.
    Re-running resumes at the first missing part and skips a complete output (its manifest is
    kept); `force` starts again from nothing."""
    if part_size < 1 or (limit is not None and limit < 1):
        raise ValueError(f"need part_size >= 1 and limit >= 1, got {part_size} and {limit}")
    if not (chunks / CHUNK_MANIFEST).is_file():
        raise FileNotFoundError(f"{chunks / CHUNK_MANIFEST} not found (run `chunk` first)")
    started = time.monotonic()
    chunk_manifest = json.loads((chunks / CHUNK_MANIFEST).read_text(encoding="utf-8"))
    state = {
        "model": encoder.name,
        "dimension": encoder.dimension,
        "passage_prefix": passage_prefix,
        "part_size": part_size,
        "limit": limit,
        "chunks": {
            "chunked_at": chunk_manifest.get("chunked_at"),
            "count": chunk_manifest.get("counts", {}).get("chunks"),
            "bytes": (chunks / CHUNK_FILE).stat().st_size,
        },
    }
    own = _own_files(out)
    if force:
        for path in own:
            path.unlink()
    if own and not force:
        previous = (
            json.loads((out / EMBED_STATE).read_text(encoding="utf-8"))
            if (out / EMBED_STATE).is_file()
            else None
        )
        if previous != state:
            raise ValueError(
                f"{out} holds vectors made with other settings or other chunks; "
                "use --force to start again or another --out"
            )
        done = _complete_manifest(out, encoder.dimension)
        if done:
            log(f"embed: {out} is complete for these settings, skipping (--force to redo)")
            return done
    out.mkdir(parents=True, exist_ok=True)
    (out / EMBED_STATE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    rows = _read_chunks(chunks, limit)
    if not rows:
        raise ValueError(f"{chunks / CHUNK_FILE} has no chunks")
    n_parts = math.ceil(len(rows) / part_size)
    resumed = embedded = 0
    encode_seconds = 0.0
    for i in range(n_parts):
        path = out / f"part-{i:05d}.parquet"
        if path.is_file():
            resumed += 1
            continue
        part = rows[i * part_size : (i + 1) * part_size]
        t = time.monotonic()
        vectors = encoder.encode([passage_prefix + text for _, text in part])
        encode_seconds += time.monotonic() - t
        shape = getattr(vectors, "shape", None) or (len(vectors), len(vectors[0]))
        if tuple(shape) != (len(part), encoder.dimension):
            raise RuntimeError(
                f"encoder returned shape {tuple(shape)}, expected ({len(part)}, "
                f"{encoder.dimension})"
            )
        _write_part(path, [chunk_id for chunk_id, _ in part], vectors, encoder.name)
        embedded += len(part)
        rate = embedded / encode_seconds if encode_seconds else 0.0
        left = max(len(rows) - (i + 1) * part_size, 0)
        eta = f", about {left / rate / 60:.1f} min left" if rate and left else ""
        log(f"embed: part {i + 1}/{n_parts}, {len(part):,} chunks, {rate:,.1f} chunks/s{eta}")
    _check_output(out, len(rows), encoder.dimension)

    manifest = {
        "step": "embed",
        "chunks": str(chunks),
        "embedded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": encoder.name,
        "dimension": encoder.dimension,
        "normalized": True,
        "passage_prefix": passage_prefix,
        "part_size": part_size,
        "limit": limit,
        "counts": {
            "chunks": len(rows),
            "parts": n_parts,
            "parts_resumed": resumed,
            "chunks_embedded_this_run": embedded,
        },
        "seconds": round(time.monotonic() - started, 1),
        "encode_seconds": round(encode_seconds, 1),
        "chunks_per_second": round(embedded / encode_seconds, 1) if encode_seconds else None,
        "bytes": sum(p.stat().st_size for p in out.glob("part-*.parquet")),
        "machine": {
            "platform": platform.platform(),
            "cpus": os.cpu_count(),
            **encoder.info(),
        },
    }
    (out / EMBED_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(
        f"embed: {len(rows):,} chunks with {encoder.name} ({encoder.dimension} dimensions), "
        f"{embedded:,} embedded in this run ({resumed} parts resumed), "
        f"{manifest['chunks_per_second'] or 0:,} chunks/s; {manifest['seconds']} s -> {out}"
    )
    return manifest
