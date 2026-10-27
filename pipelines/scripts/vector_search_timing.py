"""Vector search timings for W7-D2-FAO-1: `QdrantStore.search` alone, at each corpus size.

DAT's note 1 on #96: the dense latency in `scaling.md` is mostly the CPU embedding of the query
(about 80 ms), which does not depend on the corpus size, so it says little about how the vector
search scales. Here every query is embedded once, up front, and that time is reported on its own;
then the same pre-computed vectors are searched in each collection with `QdrantStore.search`:
- **exact** (`"params": {"exact": true}`, a full scan, the default since #101);
- **HNSW** (`exact=False`), with the share of its top-k that exact search also returns (#87);
- **exact, no gzip**: exact again, with `Accept-Encoding: identity`. `QdrantStore`'s client (httpx)
  asks for gzip, and Qdrant then sends a chunked gzip response; on Linux each such search took
  about 44 ms against about 1 ms without gzip (a 3,000-point test collection, 2026-10-27),
  a pattern that fits Nagle's algorithm meeting delayed ACKs (inferred). This mode shows
  whether FAO's laptop has the same delay;
- **exact, no gzip, TCP_NODELAY**: the same, on a socket with Nagle's algorithm off.

For every mode the table also gives Qdrant's own time per search (the `time` field of its
answer), so the search itself can be told apart from the HTTP round trip: on FAO's laptop
(Windows, Qdrant in Docker Desktop) every search took about 48 ms end to end on 2026-10-27,
HNSW included, at all three sizes.

Queries are those of `index_profile.py` (the golden query texts, then chunk titles with seed 0),
so the numbers line up with `scaling.md`. Each mode gets `--warmup` untimed searches, then
`--rounds` passes over all the vectors.

Usage (repository root, Qdrant up with the collections of `scaling.py`,
PYTHONPATH=agent/src:pipelines/src, and the variables of `.env.example`: QDRANT_URL,
QDRANT_COLLECTION, EMBEDDING_MODEL, EMBEDDING_QUERY_PREFIX):
    python pipelines/scripts/vector_search_timing.py --out data/reports/scaling/vector_search.json
The collections default to `<QDRANT_COLLECTION>_10pct`, `<QDRANT_COLLECTION>_50pct` and
`<QDRANT_COLLECTION>`; `--collection` (repeat) names others.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from index_profile import (  # noqa: E402
    DEFAULT_N_QUERIES,
    DEFAULT_WARMUP,
    SEED,
    build_queries,
    chunk_titles,
    golden_queries,
    machine,
    summarise,
)


class Mode(NamedTuple):
    exact: bool
    gzip: bool = True  # httpx's default Accept-Encoding, as in QdrantStore
    nodelay: bool = False


MODES = {
    "exact": Mode(exact=True),
    "hnsw": Mode(exact=False),
    "exact_no_gzip": Mode(exact=True, gzip=False),
    "exact_no_gzip_nodelay": Mode(exact=True, gzip=False, nodelay=True),
}
DEFAULT_ROUNDS = 3
SUBSET_SUFFIXES = ("_10pct", "_50pct", "")

Vector = Sequence[float]
Search = Callable[[Vector, int], list]


def embed_all(
    embed: Callable[[str], Vector],
    queries: Sequence[str],
    warmup: int = DEFAULT_WARMUP,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[list[Vector], list[float]]:
    """Every query's vector and the seconds each took, after `warmup` untimed embeddings (the
    first one loads the model)."""
    for query in queries[:warmup]:
        embed(query)
    vectors, seconds = [], []
    for query in queries:
        started = clock()
        vectors.append(embed(query))
        seconds.append(clock() - started)
    return vectors, seconds


def time_search(
    search: Search,
    vectors: Sequence[Vector],
    k: int,
    warmup: int = DEFAULT_WARMUP,
    rounds: int = DEFAULT_ROUNDS,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[list[float], list[list[str]]]:
    """Seconds per search over `rounds` passes, and the chunk ids of the last pass per vector."""
    for vector in vectors[:warmup]:
        search(vector, k)
    seconds: list[float] = []
    ids: list[list[str]] = []
    for _ in range(rounds):
        ids = []
        for vector in vectors:
            started = clock()
            hits = search(vector, k)
            seconds.append(clock() - started)
            ids.append([hit.chunk_id for hit in hits])
    return seconds, ids


def overlap(found: Sequence[Sequence[str]], truth: Sequence[Sequence[str]]) -> float:
    """Mean share of each exact top-k that the other search also returned."""
    shares = [len(set(f) & set(t)) / len(t) for f, t in zip(found, truth, strict=True) if t]
    return round(sum(shares) / len(shares), 4) if shares else 1.0


def measure(
    collections: Sequence[str],
    vectors: Sequence[Vector],
    store_for: Callable[[str, Mode], Any],
    *,
    k: int = 10,
    warmup: int = DEFAULT_WARMUP,
    rounds: int = DEFAULT_ROUNDS,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, dict[str, Any]]:
    """Per collection: its points, and the latency of each mode on the same vectors. A store
    with a `server_seconds` list (Qdrant's own time per answer) adds a `qdrant` summary."""
    result: dict[str, dict[str, Any]] = {}
    for collection in collections:
        print(f"vector_search_timing: {collection}", file=sys.stderr, flush=True)
        row: dict[str, Any] = {}
        ids: dict[str, list[list[str]]] = {}
        for name, mode in MODES.items():
            store = store_for(collection, mode)
            try:
                row.setdefault("points", store.count())
                seconds, ids[name] = time_search(store.search, vectors, k, warmup, rounds, clock)
            finally:
                close = getattr(store, "close", None)
                if close:
                    close()
            row[name] = summarise(seconds)
            server = getattr(store, "server_seconds", None)
            if server:  # the timed searches are the last ones
                row[name]["qdrant"] = summarise(server[-len(seconds) :])
        row["hnsw"]["overlap_with_exact"] = overlap(ids["hnsw"], ids["exact"])
        result[collection] = row
    return result


def markdown(profile: dict[str, Any]) -> str:
    embed = profile["embedding"]
    lines = [
        f"Query embedding alone ({embed['n']} queries): p50 {embed['p50_ms']} ms, "
        f"p95 {embed['p95_ms']} ms.",
        "",
        "End to end, p50 / p95 / max (ms):",
        "",
        "| Collection | Points | exact | HNSW | exact, no gzip | exact, no gzip, nodelay | "
        "HNSW top-k shared with exact |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    rows = profile["collections"]
    for name, row in rows.items():
        cells = [f"{row[m]['p50_ms']} / {row[m]['p95_ms']} / {row[m]['max_ms']}" for m in MODES]
        lines.append(
            f"| {name} | {row['points']:,} | " + " | ".join(cells) + " | "
            f"{row['hnsw']['overlap_with_exact']:.1%} |"
        )
    lines += [
        "",
        "Qdrant's own time (the `time` field of its answers), p50 / p95 / max (ms):",
        "",
        "| Collection | exact | HNSW | exact, no gzip | exact, no gzip, nodelay |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in rows.items():
        cells = []
        for m in MODES:
            q = row[m].get("qdrant")
            cells.append(f"{q['p50_ms']} / {q['p95_ms']} / {q['max_ms']}" if q else "-")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--collection",
        action="append",
        help="repeat; default <QDRANT_COLLECTION>_10pct, _50pct and <QDRANT_COLLECTION>",
    )
    parser.add_argument("--golden", type=Path, default=Path("evaluation/golden_set/golden.jsonl"))
    parser.add_argument("--chunks", type=Path, default=Path("data/processed/chunks"))
    parser.add_argument("--n-queries", type=int, default=DEFAULT_N_QUERIES)
    parser.add_argument("--k", type=int, default=int(os.environ.get("RETRIEVAL_TOP_K", "10")))
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--out", type=Path, help="write the JSON result here")
    args = parser.parse_args(argv)
    if args.rounds < 1:
        parser.error("--rounds must be at least 1")

    import httpx

    from scitech_agent.embedding import SentenceTransformerEmbedder
    from scitech_agent.store import QdrantStore, StoreConfig

    base = StoreConfig.from_env()
    collections = args.collection or [base.collection + s for s in SUBSET_SUFFIXES]

    def store_for(collection: str, mode: Mode) -> QdrantStore:
        options = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)] if mode.nodelay else []
        store = QdrantStore(
            StoreConfig(url=base.url, collection=collection, exact=mode.exact),
            transport=httpx.HTTPTransport(socket_options=options),
        )
        # The store has no setting for these; its client is only used here.
        if not mode.gzip:
            store._http.headers["Accept-Encoding"] = "identity"
        server: list[float] = []

        def qdrant_time(response: httpx.Response) -> None:
            if response.url.path.endswith("/points/query"):
                response.read()
                server.append(float(response.json().get("time", 0.0)))

        store._http.event_hooks["response"] = [qdrant_time]
        store.server_seconds = server  # type: ignore[attr-defined]
        return store

    golden = golden_queries(args.golden)
    queries = build_queries(golden, chunk_titles(args.chunks), args.n_queries)
    started = datetime.now(timezone.utc)
    print(f"vector_search_timing: embedding {len(queries)} queries", file=sys.stderr, flush=True)
    vectors, embed_seconds = embed_all(
        SentenceTransformerEmbedder.from_env().embed_query, queries, args.warmup
    )
    profile = {
        "measured_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": machine(),
        "queries": {"n": len(queries), "golden": min(len(golden), len(queries)), "seed": SEED},
        "k": args.k,
        "warmup": args.warmup,
        "rounds": args.rounds,
        "embedding": summarise(embed_seconds),
        "collections": measure(
            collections, vectors, store_for, k=args.k, warmup=args.warmup, rounds=args.rounds
        ),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(markdown(profile), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
