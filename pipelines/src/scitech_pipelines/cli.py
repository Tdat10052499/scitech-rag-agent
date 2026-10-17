"""Command-line interface of the data pipeline.

Each sub-command is implemented by its own task (download: W2-D1-FAO-1, clean: W2-D2-FAO-1,
validate: W2-D4-FAO-1, profile: W2-D3-FAO-1, chunk: W3-D1-FAO-1, embed: W3-D2-FAO-1,
load: W3-D3-FAO-1); the others are stubs for now.
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
    "validate": "Run the data quality checks on the cleaned documents.",
    "profile": "Write the data profile of the raw and cleaned data (Markdown and JSON).",
    "chunk": "Split cleaned documents into chunks (docs/contracts/chunk.schema.json).",
    "embed": "Compute an embedding for every chunk (resumable).",
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


def add_validate_arguments(parser: argparse.ArgumentParser) -> None:
    from scitech_pipelines.clean import DEFAULT_CATEGORY

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Cleaned documents (default: <data-dir>/processed/documents).",
    )
    parser.add_argument(
        "--category", default=DEFAULT_CATEGORY, help="Sub-domain every record must be in."
    )
    parser.add_argument(
        "--golden",
        type=Path,
        action="append",
        default=[],
        help="Golden-set file whose relevant_doc_ids must exist (repeatable).",
    )


def add_profile_arguments(parser: argparse.ArgumentParser) -> None:
    from scitech_pipelines.clean import ARXIV_FILE, DEFAULT_CATEGORY

    parser.add_argument(
        "--raw",
        type=Path,
        default=None,
        help=f"arXiv snapshot (default: <data-dir>/raw/arxiv/{ARXIV_FILE}).",
    )
    parser.add_argument(
        "--documents",
        type=Path,
        default=None,
        help="Cleaned documents (default: <data-dir>/processed/documents).",
    )
    parser.add_argument(
        "--wiki",
        type=Path,
        default=None,
        help="Raw Wikipedia directory (default: <data-dir>/raw/wikipedia, skipped if absent).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("pipelines/reports/data_profile.md"),
        help="Markdown report; the numbers go to the same name with .json "
        "(default: pipelines/reports/data_profile.md).",
    )
    parser.add_argument(
        "--category", default=DEFAULT_CATEGORY, help="Sub-domain category (ADR 0003)."
    )
    parser.add_argument(
        "--clean-peak-mb",
        type=float,
        default=None,
        help="Peak memory of the clean run in MB, measured outside it (shown in the report).",
    )


def add_chunk_arguments(parser: argparse.ArgumentParser) -> None:
    from scitech_pipelines.chunk import DEFAULT_MAX_WORDS, DEFAULT_OVERLAP_WORDS, env_int

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Cleaned documents (default: <data-dir>/processed/documents).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <data-dir>/processed/chunks).",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=env_int("CHUNK_MAX_WORDS", DEFAULT_MAX_WORDS),
        help=f"Words per chunk, title included (env CHUNK_MAX_WORDS, default {DEFAULT_MAX_WORDS}).",
    )
    parser.add_argument(
        "--overlap-words",
        type=int,
        default=env_int("CHUNK_OVERLAP_WORDS", DEFAULT_OVERLAP_WORDS),
        help="Words shared by consecutive chunks of one abstract "
        f"(env CHUNK_OVERLAP_WORDS, default {DEFAULT_OVERLAP_WORDS}).",
    )


def add_embed_arguments(parser: argparse.ArgumentParser) -> None:
    from scitech_pipelines.embed import DEFAULT_BATCH_SIZE, DEFAULT_PART_SIZE

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Chunks directory (default: <data-dir>/processed/chunks).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <data-dir>/processed/embeddings).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("EMBEDDING_MODEL"),
        help="Embedding model, a sentence-transformers name (env EMBEDDING_MODEL, ADR 0007).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Texts per model call (default {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--part-size",
        type=int,
        default=DEFAULT_PART_SIZE,
        help=f"Chunks per output file; a resumed run restarts at the first missing file "
        f"(default {DEFAULT_PART_SIZE}).",
    )
    parser.add_argument(
        "--device", default=None, help="cuda, cpu, ... (default: GPU if there is one)."
    )
    parser.add_argument(
        "--passage-prefix",
        default="",
        help="Text put before every chunk, for models that expect one (e.g. 'passage: ').",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Embed only the first N chunks (model comparison)."
    )
    parser.add_argument("--force", action="store_true", help="Delete the output and start again.")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one sub-command per pipeline step."""
    parser = argparse.ArgumentParser(
        prog="scitech_pipelines",
        description="Data pipeline: download, clean, validate, profile, chunk, embed, load.",
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
        elif name == "validate":
            add_validate_arguments(sub)
        elif name == "profile":
            add_profile_arguments(sub)
        elif name == "chunk":
            add_chunk_arguments(sub)
        elif name == "embed":
            add_embed_arguments(sub)
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


def run_validate(args: argparse.Namespace) -> int:
    from scitech_pipelines.validate import run_validate as validate

    path = args.input or Path(args.data_dir) / "processed" / "documents"
    return 0 if validate(path, category=args.category, golden=args.golden) else 1


def run_profile(args: argparse.Namespace) -> int:
    from scitech_pipelines.clean import ARXIV_FILE
    from scitech_pipelines.profile import run_profile as profile

    data_dir = Path(args.data_dir)
    wiki = args.wiki or data_dir / "raw" / "wikipedia"
    profile(
        args.raw or data_dir / "raw" / "arxiv" / ARXIV_FILE,
        args.documents or data_dir / "processed" / "documents",
        args.out,
        wiki=wiki if wiki.is_dir() else None,
        category=args.category,
        clean_peak_mb=args.clean_peak_mb,
    )
    return 0


def run_chunk(args: argparse.Namespace) -> int:
    from scitech_pipelines.chunk import chunk_documents

    data_dir = Path(args.data_dir)
    chunk_documents(
        args.input or data_dir / "processed" / "documents",
        args.out or data_dir / "processed" / "chunks",
        max_words=args.max_words,
        overlap_words=args.overlap_words,
    )
    return 0


def run_embed(args: argparse.Namespace) -> int:
    from scitech_pipelines.embed import SentenceTransformerEncoder, check_model_name, embed_chunks

    data_dir = Path(args.data_dir)
    model = check_model_name(args.model)
    encoder = SentenceTransformerEncoder(model, batch_size=args.batch_size, device=args.device)
    embed_chunks(
        args.input or data_dir / "processed" / "chunks",
        args.out or data_dir / "processed" / "embeddings",
        encoder,
        part_size=args.part_size,
        passage_prefix=args.passage_prefix,
        limit=args.limit,
        force=args.force,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "download":
        return run_download(args)
    if args.command == "clean":
        return run_clean(args)
    if args.command == "validate":
        return run_validate(args)
    if args.command == "profile":
        return run_profile(args)
    if args.command == "chunk":
        return run_chunk(args)
    if args.command == "embed":
        return run_embed(args)
    print(f"{args.command}: not implemented")
    return 0
