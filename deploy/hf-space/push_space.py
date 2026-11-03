"""Publish the app to a Hugging Face Docker Space (deploy/hf-space, docs/runbooks/hosting.md).
Runs on the machine that holds the index (DAT's laptop), after `huggingface-cli login`.

    python deploy/hf-space/push_space.py index --repo <user>/scitech-index
        Snapshot of the running Qdrant collection + the BM25 directory, uploaded to a private
        dataset repo (created if missing). Run once per index version.
    python deploy/hf-space/push_space.py code --space <user>/scitech-rag-agent
        Copies agent/, backend/, frontend/ and this folder's files into a temporary folder with
        the Space README, then uploads it; the Space rebuilds its image.

Nothing here reads .env or prints a token; huggingface_hub uses the login's stored token.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

# Paths copied into the Space, relative to the repository root.
CODE = [
    "agent/src",
    "agent/prompts",
    "agent/requirements.txt",
    "agent/requirements-embed.txt",
    "backend/src",
    "backend/requirements.txt",
    "frontend",
]
SPACE_FILES = ["Dockerfile", "nginx.conf", "start.sh", "fetch_index.py", "requirements-space.txt"]
SKIP = shutil.ignore_patterns("node_modules", "dist", "__pycache__", "*.tsbuildinfo", ".vite")

SPACE_README = """---
title: SciTech RAG Agent
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

Course project demo: questions about computational linguistics research answered from arXiv
cs.CL abstracts with citations. Source: https://github.com/Tdat10052499/scitech-rag-agent
"""


def push_index(args: argparse.Namespace) -> int:
    import httpx
    from huggingface_hub import HfApi

    qdrant = args.qdrant_url.rstrip("/")
    bm25 = Path(args.bm25_dir)
    if not (bm25 / "_bm25_manifest.json").is_file():
        print(f"{bm25} is not a BM25 index directory", file=sys.stderr)
        return 1
    api = HfApi()
    api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / f"{args.collection}.snapshot"
        print(f"creating a snapshot of {args.collection} ...")
        created = httpx.post(f"{qdrant}/collections/{args.collection}/snapshots", timeout=1800.0)
        created.raise_for_status()
        name = created.json()["result"]["name"]
        url = f"{qdrant}/collections/{args.collection}/snapshots/{name}"
        with httpx.stream("GET", url, timeout=1800.0) as response, snap.open("wb") as fh:
            response.raise_for_status()
            for block in response.iter_bytes(1 << 20):
                fh.write(block)
        httpx.delete(url, timeout=60.0)  # keep the laptop's snapshot folder empty
        print(f"snapshot {snap.stat().st_size / 2**20:.0f} MiB; uploading ...")
        api.upload_file(
            path_or_fileobj=str(snap),
            path_in_repo=f"qdrant/{args.collection}.snapshot",
            repo_id=args.repo,
            repo_type="dataset",
            commit_message=f"Qdrant snapshot of {args.collection}",
        )
    api.upload_folder(
        folder_path=str(bm25),
        path_in_repo="bm25",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="BM25 index",
    )
    print(f"done: https://huggingface.co/datasets/{args.repo}")
    return 0


def assemble(out: Path) -> None:
    for rel in CODE:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, out / rel, ignore=SKIP)
        else:
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out / rel)
    for name in SPACE_FILES:
        shutil.copy2(HERE / name, out / name)
    (out / "README.md").write_text(SPACE_README, encoding="utf-8")


def push_code(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "space"
        assemble(out)
        if args.dry_run:
            dest = Path(args.dry_run)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(out, dest)
            print(f"assembled into {dest} (not uploaded)")
            return 0
        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)
        api.upload_folder(
            folder_path=str(out),
            repo_id=args.space,
            repo_type="space",
            commit_message=args.message,
            delete_patterns=["agent/**", "backend/**", "frontend/**"],
        )
    print(f"done: https://huggingface.co/spaces/{args.space} (the image builds now)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    index = sub.add_parser("index", help="upload the Qdrant snapshot and BM25 index")
    index.add_argument("--repo", required=True, help="dataset repo id, e.g. user/scitech-index")
    index.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    )
    index.add_argument(
        "--collection", default=os.environ.get("QDRANT_COLLECTION", "scitech_chunks")
    )
    index.add_argument("--bm25-dir", default=str(ROOT / "data" / "index" / "bm25"))
    code = sub.add_parser("code", help="upload the code to the Space")
    code.add_argument("--space", default="", help="Space repo id, e.g. user/scitech-rag-agent")
    code.add_argument("--message", default="Update from scitech-rag-agent")
    code.add_argument("--dry-run", metavar="DIR", help="assemble into DIR, do not upload")
    args = parser.parse_args(argv)
    if args.cmd == "code" and not (args.space or args.dry_run):
        parser.error("code needs --space (or --dry-run DIR)")
    return push_index(args) if args.cmd == "index" else push_code(args)


if __name__ == "__main__":
    sys.exit(main())
