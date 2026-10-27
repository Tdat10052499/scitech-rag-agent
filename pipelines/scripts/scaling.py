"""Scaling measurements for W6-D2-FAO-1: the index at several corpus sizes from the same vectors.

For each fraction below 1 (default 0.1 and 0.5), and for the full index already loaded:
1. **Qdrant:** `load --fraction F` puts the nested subset (`scitech_pipelines.load.in_subset`)
   into its own collection, `<collection>_<pct>pct`, from the Week 3 vectors, so nothing is
   embedded again. Its `_load_manifest.json` gives points and seconds. A subset load still
   reads every vector part and skips the other documents, so its seconds are an upper bound.
2. **BM25:** the subset's chunks are written to `<data>/processed/chunks-<pct>pct/` and
   `python -m scitech_agent.retrieval.keyword build` indexes them into
   `<data>/index/bm25-<pct>pct`; its manifest gives seconds and size.
3. **Latency, disk and memory:** Qdrant is restarted (`docker compose restart qdrant`) so its
   memory starts from what the collections on disk need, then `index_profile.py` (W3-D5-FAO-1)
   runs the same queries against that size's collection and BM25 index. All sizes use the same
   query set, taken from the full chunks.

The subsets are cut from the chunks and vectors named in the full load's manifest,
`<data>/processed/index/_load_manifest.json` (`--chunks` and `--vectors` override them). The
full size reuses that manifest and `<data>/index/bm25`, which
the full load and BM25 build wrote. Qdrant's memory is that of the whole container, which holds
every collection, so the table also gives the growth of the container's memory after each load.

Usage (repository root, Qdrant up, PYTHONPATH=agent/src:pipelines/src, and the variables of
`.env.example`: QDRANT_URL, QDRANT_COLLECTION, EMBEDDING_MODEL, EMBEDDING_QUERY_PREFIX):
    python pipelines/scripts/scaling.py --out-dir data/reports/scaling
It writes `scaling.json` and `scaling.csv` there, plus one `profile-<pct>pct.json` per size.
Re-running reuses finished loads and BM25 indexes (`--force` builds them again).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_FRACTIONS = (0.1, 0.5)
RETRIEVERS = ("dense", "bm25", "hybrid")
CSV_FIELDS = (
    "fraction",
    "documents",
    "chunks",
    "load_seconds",
    "bm25_build_seconds",
    "qdrant_collection_mib",
    "bm25_index_mib",
    "qdrant_memory_mib",
    *(f"{r}_{p}_ms" for r in RETRIEVERS for p in ("p50", "p95")),
)
UNITS = {"b": 1, "kib": 2**10, "mib": 2**20, "gib": 2**30, "kb": 1e3, "mb": 1e6, "gb": 1e9}

Run = Callable[..., subprocess.CompletedProcess]


def pct(fraction: float) -> str:
    """0.1 -> '10pct', 0.05 -> '5pct', 1 -> '100pct'."""
    return f"{fraction * 100:g}pct"


def subset_chunks(chunks: Path, out: Path, fraction: float) -> dict[str, int]:
    """Write the chunks of the documents in the subset to `<out>/chunks.parquet`, with a chunk
    manifest that keeps the full chunks' `chunked_at`; return the document and chunk counts."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from scitech_pipelines.chunk import CHUNK_FILE, CHUNK_MANIFEST
    from scitech_pipelines.load import in_subset

    table = pq.read_table(chunks / CHUNK_FILE)
    doc_ids = table.column("doc_id").to_pylist()
    keep = {d for d in set(doc_ids) if in_subset(d, fraction)}
    subset = table.filter(pc.is_in(table.column("doc_id"), value_set=pc.cast(list(keep), "string")))
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(subset, out / CHUNK_FILE)
    source = json.loads((chunks / CHUNK_MANIFEST).read_text(encoding="utf-8"))
    counts = {"documents": len(keep), "chunks": subset.num_rows}
    manifest = {
        "step": "chunk",
        "chunked_at": source.get("chunked_at"),
        "subset_of": str(chunks),
        "fraction": fraction,
        "counts": counts,
    }
    (out / CHUNK_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return counts


def memory_mib(usage: str | None) -> float | None:
    """'280.7MiB / 7.662GiB' (docker stats) -> 280.7."""
    match = re.match(r"\s*([\d.]+)\s*([KMG]i?B|B)", usage or "", re.IGNORECASE)
    if not match:
        return None
    return round(float(match.group(1)) * UNITS[match.group(2).lower()] / 2**20, 1)


def row(
    fraction: float,
    load: dict[str, Any],
    bm25: dict[str, Any],
    profile: dict[str, Any],
    documents: int | None,
) -> dict[str, Any]:
    """One line of the table, from the load manifest, the BM25 manifest and the profile."""
    docker = profile.get("docker") or {}
    latency = profile.get("latency") or {}
    out: dict[str, Any] = {
        "fraction": fraction,
        "documents": documents,
        "chunks": load["counts"]["points"],
        "load_seconds": load.get("seconds"),
        "bm25_build_seconds": bm25.get("build_seconds"),
        "qdrant_collection_mib": (
            round(docker["collection_bytes"] / 2**20, 1) if "collection_bytes" in docker else None
        ),
        "bm25_index_mib": bm25.get("index_mb"),
        "qdrant_memory_mib": memory_mib(docker.get("memory_usage")),
    }
    for name in RETRIEVERS:
        for p in ("p50", "p95"):
            out[f"{name}_{p}_ms"] = latency.get(name, {}).get(f"{p}_ms")
    return out


def markdown(rows: Sequence[dict[str, Any]]) -> str:
    """The table of scaling.md."""

    def cell(value: Any) -> str:
        if value is None:
            return "-"
        return f"{value:,}" if isinstance(value, int) else f"{value:g}"

    lines = [
        "| Size | Documents | Chunks | Load (s) | BM25 build (s) | Qdrant on disk (MiB) | "
        "BM25 on disk (MiB) | Qdrant memory (MiB) | dense p50 / p95 (ms) | "
        "bm25 p50 / p95 (ms) | hybrid p50 / p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        latency = [f"{cell(r[f'{n}_p50_ms'])} / {cell(r[f'{n}_p95_ms'])}" for n in RETRIEVERS]
        lines.append(
            f"| {r['fraction'] * 100:g}% | {cell(r['documents'])} | {cell(r['chunks'])} | "
            f"{cell(r['load_seconds'])} | {cell(r['bm25_build_seconds'])} | "
            f"{cell(r['qdrant_collection_mib'])} | {cell(r['bm25_index_mib'])} | "
            f"{cell(r['qdrant_memory_mib'])} | " + " | ".join(latency) + " |"
        )
    return "\n".join(lines) + "\n"


def wait_for_qdrant(url: str, timeout: float = 120.0, pause: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/collections", timeout=5):
                return
        except OSError:
            if time.monotonic() > deadline:
                raise RuntimeError(f"Qdrant at {url} did not come back in {timeout:g} s") from None
            time.sleep(pause)


def main(argv: list[str] | None = None, run: Run = subprocess.run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", "data")))
    parser.add_argument(
        "--fraction", type=float, action="append", help="repeat; default 0.1 and 0.5"
    )
    parser.add_argument(
        "--collection", default=os.environ.get("QDRANT_COLLECTION", "scitech_chunks")
    )
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument(
        "--chunks", type=Path, help="default: the chunks of the full load (its manifest)"
    )
    parser.add_argument(
        "--vectors", type=Path, help="default: the vectors of the full load (its manifest)"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data/reports/scaling"))
    parser.add_argument("--no-restart", action="store_true", help="do not restart Qdrant")
    parser.add_argument("--force", action="store_true", help="load and build the subsets again")
    args = parser.parse_args(argv)
    fractions = sorted(set(args.fraction or DEFAULT_FRACTIONS))
    if any(not 0 < f < 1 for f in fractions):
        parser.error("each --fraction must be in (0, 1); the full index is always included")

    from scitech_agent.retrieval.keyword import MANIFEST as BM25_MANIFEST
    from scitech_pipelines.chunk import CHUNK_MANIFEST
    from scitech_pipelines.load import LOAD_MANIFEST

    data = args.data_dir
    python = sys.executable
    args.out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def step(cmd: list[str], env: dict[str, str] | None = None) -> None:
        print("scaling: " + " ".join(cmd), file=sys.stderr, flush=True)
        run(cmd, check=True, env={**os.environ, **(env or {})})

    def read(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    full_index, full_bm25 = data / "processed" / "index", data / "index" / "bm25"
    for needed in (full_index / LOAD_MANIFEST, full_bm25 / BM25_MANIFEST):
        if not needed.is_file():  # fail before the subsets are built, not after
            parser.error(f"{needed} is missing: the full load and BM25 build come first")
    # The subsets come from the same chunks and vectors as the full index.
    full_load = read(full_index / LOAD_MANIFEST)
    chunks = args.chunks or Path(full_load["chunks"])
    vectors = args.vectors or Path(full_load["vectors"])
    for needed, option in ((chunks / CHUNK_MANIFEST, "--chunks"), (vectors, "--vectors")):
        if not needed.exists():
            parser.error(f"{needed} is missing (from {full_index / LOAD_MANIFEST}); use {option}")

    sizes = []  # (fraction, collection, load dir, bm25 dir, documents)
    for f in fractions:
        name = pct(f)
        collection = f"{args.collection}_{name}"
        index_dir = data / "processed" / f"index-{name}"
        sub_chunks = data / "processed" / f"chunks-{name}"
        bm25_dir = data / "index" / f"bm25-{name}"
        if args.force or not (index_dir / LOAD_MANIFEST).is_file():
            load = ["-m", "scitech_pipelines", "--data-dir", str(data), "load"]
            step(
                [python, *load, "--fraction", str(f), "--collection", collection]
                + ["--chunks", str(chunks), "--vectors", str(vectors), "--out", str(index_dir)]
                + (["--force"] if args.force else [])
            )
        if args.force or not (bm25_dir / BM25_MANIFEST).is_file():
            counts = subset_chunks(chunks, sub_chunks, f)
            print(f"scaling: {name}: {counts}", file=sys.stderr, flush=True)
            build = ["-m", "scitech_agent.retrieval.keyword", "build"]
            step([python, *build, "--chunks", str(sub_chunks), "--out", str(bm25_dir)])
        documents = read(sub_chunks / CHUNK_MANIFEST)["counts"]["documents"]
        sizes.append((f, collection, index_dir, bm25_dir, documents))
    full_docs = read(chunks / CHUNK_MANIFEST)["counts"].get("documents")
    sizes.append((1.0, args.collection, full_index, full_bm25, full_docs))

    rows = []
    for f, collection, index_dir, bm25_dir, documents in sizes:
        if not args.no_restart:
            step(["docker", "compose", "restart", "qdrant"])
            wait_for_qdrant(args.qdrant_url)
        profile_path = args.out_dir / f"profile-{pct(f)}.json"
        retrievers = [a for r in RETRIEVERS for a in ("--retriever", r)]
        step(
            [python, str(SCRIPTS / "index_profile.py"), *retrievers]
            + ["--collection", collection, "--size", f"bm25={bm25_dir}"]
            + ["--chunks", str(chunks), "--out", str(profile_path)],
            env={"QDRANT_COLLECTION": collection, "BM25_INDEX_DIR": str(bm25_dir)},
        )
        rows.append(
            row(
                f,
                read(index_dir / LOAD_MANIFEST),
                read(bm25_dir / BM25_MANIFEST),
                read(profile_path),
                documents,
            )
        )

    result = {
        "measured_at": started,
        "collection": args.collection,
        "restarted_qdrant": not args.no_restart,
        "rows": rows,
    }
    (args.out_dir / "scaling.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    with open(args.out_dir / "scaling.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(markdown(rows), end="")
    print(f"scaling: written to {args.out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
