"""Golden-set coverage of the index (W4-D3-FAO-1): is every `relevant_doc_ids` searchable?

`validate --golden` checks the ids against the cleaned documents. This checks the next steps:
the chunks (`--chunks`, no Qdrant needed) and the loaded Qdrant collection (`--qdrant`), so a
document lost by chunking or loading is found before a retrieval run scores it as a miss.

For every golden item it lists the ids that are missing, in a form that can be pasted into an
issue for the golden-set author. Exit code 0 when nothing is missing, 1 otherwise.

Usage (repository root):
    python pipelines/scripts/golden_coverage.py --chunks data/processed/chunks --qdrant
    python pipelines/scripts/golden_coverage.py --golden evaluation/golden_set/golden.jsonl \
        --qdrant --qdrant-url http://localhost:6333 --collection scitech_chunks
`--qdrant` uses QDRANT_URL and QDRANT_COLLECTION (.env.example) unless given. Points must carry
`doc_id` in their payload, as `load` writes it (chunk.schema.json fields).
Dependencies: pyarrow for `--chunks` (pipelines/requirements.txt); nothing else.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from scitech_pipelines.validate import read_golden_doc_ids

ID_BATCH = 256
PAGE_SIZE = 1024
TIMEOUT = 30.0

Post = Callable[[str, dict[str, Any]], dict[str, Any]]


def missing_by_item(wanted: Mapping[str, list[str]], found: set[str]) -> dict[str, list[str]]:
    """Golden item -> its ids that are not in `found` (items with nothing missing left out)."""
    missing = {item: [d for d in docs if d not in found] for item, docs in wanted.items()}
    return {item: docs for item, docs in missing.items() if docs}


def chunk_doc_ids(chunks: Path, ids: Iterable[str]) -> set[str]:
    """The ids among `ids` that have at least one chunk in `chunks.parquet`."""
    import pyarrow.parquet as pq

    path = Path(chunks)
    if path.is_dir():
        path = path / "chunks.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path}: no chunks (run `chunk` first)")
    wanted = set(ids)
    column = pq.read_table(path, columns=["doc_id"]).column("doc_id").to_pylist()
    return wanted.intersection(column)


def http_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def qdrant_doc_ids(
    url: str,
    collection: str,
    ids: Iterable[str],
    *,
    post: Post | None = None,
    id_batch: int = ID_BATCH,
    page_size: int = PAGE_SIZE,
) -> set[str]:
    """The ids among `ids` with at least one point in the collection (scroll with a doc_id filter).

    Only the `doc_id` payload field is returned, without vectors; a batch of ids is paged until
    Qdrant returns no next offset.
    """
    post = post or http_post
    endpoint = f"{url.rstrip('/')}/collections/{collection}/points/scroll"
    wanted = sorted(set(ids))
    found: set[str] = set()
    for start in range(0, len(wanted), id_batch):
        batch = wanted[start : start + id_batch]
        offset = None
        while True:
            body: dict[str, Any] = {
                "filter": {"must": [{"key": "doc_id", "match": {"any": batch}}]},
                "limit": page_size,
                "with_payload": ["doc_id"],
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            result = post(endpoint, body)["result"]
            found.update(p["payload"]["doc_id"] for p in result["points"] if p.get("payload"))
            offset = result.get("next_page_offset")
            if offset is None:
                break
    return found & set(wanted)


def report(name: str, wanted: Mapping[str, list[str]], found: set[str]) -> tuple[bool, list[str]]:
    """PASS/FAIL line for one source, then one line per item with missing ids."""
    ids = {d for docs in wanted.values() for d in docs}
    missing = missing_by_item(wanted, found)
    lost = {d for docs in missing.values() for d in docs}
    if not missing:
        return True, [f"  PASS  {name}: {len(ids)} ids in {len(wanted)} items, all found"]
    lines = [f"  FAIL  {name}: {len(lost)} of {len(ids)} ids missing in {len(missing)} items"]
    lines += [f"        {item}: {', '.join(docs)}" for item, docs in missing.items()]
    return False, lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--golden",
        type=Path,
        action="append",
        help="golden-set file (repeatable; default evaluation/golden_set/golden.jsonl)",
    )
    parser.add_argument("--chunks", type=Path, help="chunk folder or chunks.parquet to check")
    parser.add_argument("--qdrant", action="store_true", help="check the loaded collection")
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION"))
    args = parser.parse_args(argv)
    if not args.chunks and not args.qdrant:
        parser.error("give --chunks, --qdrant or both")
    if args.qdrant and not args.collection:
        parser.error("--qdrant needs --collection or QDRANT_COLLECTION")

    golden = args.golden or [Path("evaluation/golden_set/golden.jsonl")]
    wanted = read_golden_doc_ids(golden)
    ids = {d for docs in wanted.values() for d in docs}
    print(f"golden-coverage: {', '.join(str(p) for p in golden)} ({len(ids)} ids)")

    results = []
    if args.chunks:
        results.append(report(f"chunks {args.chunks}", wanted, chunk_doc_ids(args.chunks, ids)))
    if args.qdrant:
        found = qdrant_doc_ids(args.qdrant_url, args.collection, ids)
        results.append(report(f"Qdrant {args.collection}", wanted, found))
    for _, lines in results:
        print("\n".join(lines))
    ok = all(passed for passed, _ in results)
    print("golden-coverage: all ids found" if ok else "golden-coverage: ids missing (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
