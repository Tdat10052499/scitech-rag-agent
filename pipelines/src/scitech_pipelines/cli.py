"""Command-line interface of the data pipeline.

Each sub-command is implemented by its own task (download: W2-D1-FAO-1, clean: W2-D2-FAO-1,
chunk: W3-D1-FAO-1, embed: W3-D2-FAO-1, load: W3-D3-FAO-1); the others are stubs for now.
Paths and settings come from arguments, with environment variables as defaults.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

STEPS: dict[str, str] = {
    "download": "Download raw source data into the raw data directory.",
    "clean": "Normalise, de-duplicate and filter raw data into Parquet.",
    "chunk": "Split cleaned documents into chunks (docs/contracts/chunk.schema.json).",
    "embed": "Compute embeddings for chunks.",
    "load": "Load chunks and embeddings into the vector store.",
}
SOURCES = ("arxiv", "wikipedia")


def add_download_arguments(parser: argparse.ArgumentParser) -> None:
    from scitech_pipelines.download import DEFAULT_USER_AGENT, WIKI_ROOT_CATEGORY

    parser.add_argument(
        "--source",
        choices=[*SOURCES, "all"],
        default="all",
        help="Source to download (ADR 0003). Default: all.",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="Raw data directory (default: <data-dir>/raw)."
    )
    parser.add_argument(
        "--force", action="store_true", help="Download again even if the manifest is complete."
    )
    parser.add_argument(
        "--keep-zip", action="store_true", help="arxiv: keep the Kaggle zip after extraction."
    )
    parser.add_argument("--wiki-root", default=WIKI_ROOT_CATEGORY, help="Root category.")
    parser.add_argument(
        "--wiki-depth", type=int, default=2, help="Subcategory depth below the root (default 2)."
    )
    parser.add_argument(
        "--wiki-max-pages", type=int, default=None, help="Stop after this many pages (for tests)."
    )
    parser.add_argument(
        "--wiki-pause", type=float, default=1.0, help="Seconds between API requests (default 1)."
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("WIKI_USER_AGENT") or DEFAULT_USER_AGENT,
        help="User-Agent for the MediaWiki API (env WIKI_USER_AGENT; empty: built-in default).",
    )


def add_clean_arguments(parser: argparse.ArgumentParser) -> None:
    from scitech_pipelines.clean import ARXIV_FILE, DEFAULT_CATEGORY, DEFAULT_SAMPLE_SIZE

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=f"arXiv snapshot (default: <data-dir>/raw/arxiv/{ARXIV_FILE}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <data-dir>/processed/documents).",
    )
    parser.add_argument(
        "--category", default=DEFAULT_CATEGORY, help="Sub-domain category (ADR 0003)."
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help="Records in the golden-set sample, written next to --out (0: none).",
    )
    parser.add_argument(
        "--master",
        default=os.environ.get("SPARK_MASTER") or "local[*]",
        help="Spark master (env SPARK_MASTER, default local[*]).",
    )
    parser.add_argument(
        "--driver-memory",
        default=os.environ.get("SPARK_DRIVER_MEMORY") or "4g",
        help="Spark driver memory (env SPARK_DRIVER_MEMORY, default 4g).",
    )
    parser.add_argument(
        "--snapshot-version",
        default=None,
        help="Kaggle dataset version to record (default: from the download manifest).",
    )
    parser.add_argument(
        "--skip-duckdb-check",
        action="store_true",
        help="Do not compare the category count with DuckDB (ADR 0005).",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one sub-command per pipeline step."""
    parser = argparse.ArgumentParser(
        prog="scitech_pipelines",
        description="Data pipeline: download, clean, chunk, embed, load.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("DATA_DIR", "data"),
        help="Root data directory (env DATA_DIR, default: data).",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    for name, help_text in STEPS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "download":
            add_download_arguments(sub)
        elif name == "clean":
            add_clean_arguments(sub)
    return parser


def run_download(args: argparse.Namespace) -> int:
    from scitech_pipelines.download import download_arxiv, download_wikipedia

    out = args.out or Path(args.data_dir) / "raw"
    sources = SOURCES if args.source == "all" else (args.source,)
    if "arxiv" in sources:
        download_arxiv(out, force=args.force, keep_zip=args.keep_zip)
    if "wikipedia" in sources:
        download_wikipedia(
            out,
            root=args.wiki_root,
            max_depth=args.wiki_depth,
            max_pages=args.wiki_max_pages,
            pause=args.wiki_pause,
            user_agent=args.user_agent,
            force=args.force,
        )
    return 0


def run_clean(args: argparse.Namespace) -> int:
    from scitech_pipelines.clean import ARXIV_FILE, clean_arxiv, create_spark

    data_dir = Path(args.data_dir)
    src = args.input or data_dir / "raw" / "arxiv" / ARXIV_FILE
    out = args.out or data_dir / "processed" / "documents"
    sample_out = out.parent / f"{out.name}-sample"
    spark = create_spark(args.master, args.driver_memory)
    try:
        clean_arxiv(
            spark,
            src,
            out,
            category=args.category,
            sample_out=sample_out,
            sample_size=args.sample_size,
            duckdb_check=not args.skip_duckdb_check,
            snapshot_version=args.snapshot_version,
        )
    finally:
        spark.stop()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "download":
        return run_download(args)
    if args.command == "clean":
        return run_clean(args)
    print(f"{args.command}: not implemented")
    return 0
