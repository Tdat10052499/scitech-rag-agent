"""Command-line interface of the data pipeline.

Every sub-command is a stub for now; each one is implemented by its own task
(download: W2-D1-FAO-1, clean: W2-D2-FAO-1, chunk: W3-D1-FAO-1, embed: W3-D2-FAO-1,
load: W3-D3-FAO-1).
Paths and settings come from arguments, with environment variables as defaults.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

STEPS: dict[str, str] = {
    "download": "Download raw source data into the raw data directory.",
    "clean": "Normalise, de-duplicate and filter raw data into Parquet.",
    "chunk": "Split cleaned documents into chunks (docs/contracts/chunk.schema.json).",
    "embed": "Compute embeddings for chunks.",
    "load": "Load chunks and embeddings into the vector store.",
}


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
        subparsers.add_parser(name, help=help_text, description=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    print(f"{args.command}: not implemented")
    return 0
