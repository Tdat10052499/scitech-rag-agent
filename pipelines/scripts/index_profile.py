"""Index profile for W3-D5-FAO-1: query latency per retriever, filter check, index size and RAM.

Measures what `pipelines/reports/index_profile.md` reports:
- query latency of each retriever's `search(query, k, filters)`, end to end (for dense and hybrid
  this includes embedding the query), p50 / p95 / mean / max over the same query set;
- a filter check: for each filter, every hit must satisfy it, on a few queries;
- the Qdrant collection (points, segments, status) from its REST API;
- Qdrant's disk use and memory, from the `qdrant` service of docker-compose.yml (optional);
- the size on disk of any other index folder (for example `data/index/bm25`).

Retrievers are built like the evaluation harness does it: `name=module:factory` plus an optional
JSON object of keyword arguments, so this script works with whatever DAT's store and retrievers
expose on D09 without changing.

Queries: every golden question (and the standalone query of follow-up items), then chunk titles
sampled with a fixed seed until there are `--n-queries`. The titles make the set larger than the
golden set; latency does not need relevance labels.

Usage (repository root, Qdrant up, PYTHONPATH=agent/src:pipelines/src):
    python pipelines/scripts/index_profile.py \
        --retriever "dense=scitech_agent.retrieval.dense:from_env" \
        --retriever "bm25=scitech_agent.retrieval.keyword:from_env" \
        --retriever "hybrid=scitech_agent.retrieval.hybrid:from_env" \
        --filter '{"categories": "cs.LG"}' \
        --filter '{"published_at": {"gte": "2023-01-01", "lte": "2023-12-31"}}' \
        --collection scitech --size bm25=data/index/bm25 \
        --out data/reports/index_profile.json
The factory names above are placeholders until W3-D1/D2/D3/D4-DAT-1 are merged.
Dependencies: pyarrow (pipelines/requirements.txt); `docker` on PATH for disk and RAM.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_N_QUERIES = 100
DEFAULT_WARMUP = 5
FILTER_QUERIES = 5
SEED = 0


def golden_queries(path: Path) -> list[str]:
    """The question of every golden item, plus the standalone query of follow-up items."""
    queries = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        queries.append(item["question"])
        if item.get("standalone_query"):
            queries.append(item["standalone_query"])
    return list(dict.fromkeys(queries))


def chunk_titles(chunks: Path) -> list[str]:
    """Distinct chunk titles from `chunks.parquet` in a chunk folder (or the file itself)."""
    import pyarrow.parquet as pq

    path = Path(chunks)
    if path.is_dir():
        path = path / "chunks.parquet"
    titles = pq.read_table(path, columns=["title"]).column("title").to_pylist()
    return sorted({t for t in titles if t})


def build_queries(golden: list[str], titles: list[str], n: int, seed: int = SEED) -> list[str]:
    """Golden queries first, then sampled titles not already in the set, up to `n`."""
    queries = list(dict.fromkeys(golden))[:n]
    seen = set(queries)
    pool = [t for t in titles if t not in seen]
    queries += random.Random(seed).sample(pool, min(n - len(queries), len(pool)))
    return queries


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (p in 0-100): the smallest value with p% of values at or below."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p / 100 * len(ordered))) - 1]


def summarise(seconds: Sequence[float]) -> dict[str, float]:
    ms = [s * 1000 for s in seconds]
    return {
        "n": len(ms),
        "p50_ms": round(percentile(ms, 50), 2),
        "p95_ms": round(percentile(ms, 95), 2),
        "mean_ms": round(statistics.fmean(ms), 2),
        "max_ms": round(max(ms), 2),
    }


def time_queries(
    search: Callable[..., list],
    queries: Sequence[str],
    k: int,
    warmup: int = DEFAULT_WARMUP,
    filters: Mapping[str, Any] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[list[float], list[int]]:
    """Seconds per search and number of hits, after `warmup` untimed searches (first queries)."""
    for query in queries[:warmup]:
        search(query, k, filters)
    seconds, hits = [], []
    for query in queries:
        started = clock()
        result = search(query, k, filters)
        seconds.append(clock() - started)
        hits.append(len(result))
    return seconds, hits


def satisfies(hit: Any, filters: Mapping[str, Any]) -> bool:
    """True if `hit` meets every filter.

    A list field (categories) must contain the value; a {"gte", "lte"} object is an inclusive
    range compared as strings (ISO dates compare correctly); anything else must be equal.
    """
    for name, wanted in filters.items():
        value = getattr(hit, name, None)
        if isinstance(wanted, Mapping):
            if value is None:
                return False
            if "gte" in wanted and str(value) < str(wanted["gte"]):
                return False
            if "lte" in wanted and str(value) > str(wanted["lte"]):
                return False
        elif isinstance(value, (list, tuple)):
            if wanted not in value:
                return False
        elif value != wanted:
            return False
    return True


def check_filter(
    search: Callable[..., list], queries: Sequence[str], k: int, filters: Mapping[str, Any]
) -> dict[str, Any]:
    """Run `queries` with `filters`; count hits and hits that break the filter."""
    hits = violations = empty = 0
    examples = []
    for query in queries:
        result = search(query, k, filters)
        empty += not result
        hits += len(result)
        for hit in result:
            if not satisfies(hit, filters):
                violations += 1
                if len(examples) < 3:
                    examples.append(getattr(hit, "chunk_id", repr(hit)))
    return {
        "filters": dict(filters),
        "queries": len(queries),
        "hits": hits,
        "queries_without_hits": empty,
        "violations": violations,
        "violation_examples": examples,
        "ok": violations == 0 and hits > 0,
    }


def build_retriever(spec: str, params: dict[str, Any] | None = None) -> Any:
    """`module:factory` -> factory(**params), as `retriever.factory` in the evaluation configs."""
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError(f"retriever factory must be 'module:attribute', got {spec!r}")
    return getattr(importlib.import_module(module_name), attr)(**(params or {}))


def parse_retriever(value: str) -> tuple[str, str, dict[str, Any]]:
    """'name=module:factory' or 'name=module:factory {json params}'."""
    name, sep, rest = value.partition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f"expected name=module:factory, got {value!r}")
    spec, _, params = rest.strip().partition(" ")
    try:
        parsed = json.loads(params) if params.strip() else {}
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{name}: params are not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(f"{name}: params must be a JSON object")
    return name.strip(), spec, parsed


def parse_filter(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"filter is not JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise argparse.ArgumentTypeError("a filter must be a non-empty JSON object")
    return parsed


def folder_bytes(path: Path) -> int:
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def qdrant_collection(url: str, collection: str, timeout: float = 10.0) -> dict[str, Any]:
    """Points, segments, status and vector config of the collection (GET /collections/{name})."""
    endpoint = f"{url.rstrip('/')}/collections/{collection}"
    with urllib.request.urlopen(endpoint, timeout=timeout) as response:
        result = json.load(response)["result"]
    return {
        "status": result.get("status"),
        "points_count": result.get("points_count"),
        "indexed_vectors_count": result.get("indexed_vectors_count"),
        "segments_count": result.get("segments_count"),
        "vectors": result.get("config", {}).get("params", {}).get("vectors"),
        "payload_indexes": sorted(result.get("payload_schema", {})),
    }


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60).stdout


def docker_qdrant(collection: str, service: str = "qdrant") -> dict[str, Any]:
    """Disk use of the collection and of all storage, and container memory, through docker.

    Memory is what `docker stats` reports for the container (cgroup usage, which includes page
    cache of the memory-mapped segments), so it is an upper bound of what Qdrant needs.
    """
    container = _run(["docker", "compose", "ps", "-q", service]).strip()
    if not container:
        raise RuntimeError(f"docker compose service {service!r} is not running")

    def du(path: str) -> int:
        return int(_run(["docker", "exec", container, "du", "-sb", path]).split()[0])

    memory = _run(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container]
    ).strip()
    return {
        "collection_bytes": du(f"/qdrant/storage/collections/{collection}"),
        "storage_bytes": du("/qdrant/storage"),
        "memory_usage": memory,
        "image": _run(["docker", "inspect", "--format", "{{.Config.Image}}", container]).strip(),
    }


def machine() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }
    try:
        import psutil

        info["ram_bytes"] = psutil.virtual_memory().total
    except ImportError:
        info["ram_bytes"] = None  # type it into the report by hand
    return info


def mib(n: int | None) -> str:
    return "-" if n is None else f"{n / 2**20:,.1f} MiB"


def markdown(profile: dict[str, Any]) -> str:
    """The tables of index_profile.md, from the JSON profile."""
    lines = [
        f"Queries: {profile['queries']['n']} ({profile['queries']['golden']} golden, the rest "
        f"chunk titles, seed {profile['queries']['seed']}); k = {profile['k']}; "
        f"{profile['warmup']} warm-up searches per retriever, not timed.",
        "",
        "| Retriever | p50 (ms) | p95 (ms) | mean (ms) | max (ms) | queries without hits |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, r in profile["latency"].items():
        lines.append(
            f"| {name} | {r['p50_ms']} | {r['p95_ms']} | {r['mean_ms']} | {r['max_ms']} | "
            f"{r['queries_without_hits']} |"
        )
    if profile["filters"]:
        lines += [
            "",
            "| Retriever | Filter | Hits | Violations | Result |",
            "|---|---|---:|---:|---|",
        ]
        for name, checks in profile["filters"].items():
            for c in checks:
                result = "ok" if c["ok"] else ("no hits" if not c["hits"] else "FAILED")
                lines.append(
                    f"| {name} | `{json.dumps(c['filters'])}` | {c['hits']} | "
                    f"{c['violations']} | {result} |"
                )
    sizes = dict(profile["sizes"])
    q = profile.get("qdrant") or {}
    d = profile.get("docker") or {}
    if q or d or sizes:
        lines += ["", "| Item | Value |", "|---|---|"]
        if q:
            lines.append(f"| Qdrant points | {q.get('points_count')} |")
            lines.append(f"| Qdrant segments | {q.get('segments_count')} |")
        if d:
            lines.append(f"| Qdrant collection on disk | {mib(d.get('collection_bytes'))} |")
            lines.append(f"| Qdrant storage on disk | {mib(d.get('storage_bytes'))} |")
            lines.append(f"| Qdrant container memory | {d.get('memory_usage')} |")
        for label, size in sizes.items():
            lines.append(f"| {label} on disk | {mib(size)} |")
    for problem in profile["problems"]:
        lines.append(f"\nNot measured: {problem}")
    return "\n".join(lines) + "\n"


def profile_index(
    retrievers: Mapping[str, Any],
    queries: Sequence[str],
    *,
    n_golden: int,
    k: int = 10,
    warmup: int = DEFAULT_WARMUP,
    filters: Sequence[Mapping[str, Any]] = (),
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Latency and filter results for every retriever on the same queries."""
    latency, checks = {}, {}
    for name, retriever in retrievers.items():
        seconds, hits = time_queries(retriever.search, queries, k, warmup, clock=clock)
        latency[name] = {**summarise(seconds), "queries_without_hits": hits.count(0)}
        checks[name] = [
            check_filter(retriever.search, queries[:FILTER_QUERIES], k, f) for f in filters
        ]
    return {
        "queries": {"n": len(queries), "golden": n_golden, "seed": SEED},
        "k": k,
        "warmup": warmup,
        "latency": latency,
        "filters": checks if filters else {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--retriever",
        action="append",
        required=True,
        type=parse_retriever,
        help="name=module:factory [JSON params]; repeat for each retriever",
    )
    parser.add_argument("--golden", type=Path, default=Path("evaluation/golden_set/golden.jsonl"))
    parser.add_argument("--chunks", type=Path, default=Path("data/processed/chunks"))
    parser.add_argument("--n-queries", type=int, default=DEFAULT_N_QUERIES)
    parser.add_argument("--k", type=int, default=int(os.environ.get("RETRIEVAL_TOP_K", "10")))
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--filter", action="append", default=[], type=parse_filter)
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument("--collection", help="Qdrant collection to describe (and measure on disk)")
    parser.add_argument("--no-docker", action="store_true", help="skip disk and RAM via docker")
    parser.add_argument(
        "--size", action="append", default=[], help="label=path of another index to measure"
    )
    parser.add_argument("--out", type=Path, help="write the JSON profile here")
    args = parser.parse_args(argv)

    golden = golden_queries(args.golden)
    queries = build_queries(golden, chunk_titles(args.chunks), args.n_queries)
    retrievers = {name: build_retriever(spec, params) for name, spec, params in args.retriever}

    started = datetime.now(timezone.utc)
    result = profile_index(
        retrievers,
        queries,
        n_golden=min(len(golden), len(queries)),
        k=args.k,
        warmup=args.warmup,
        filters=args.filter,
    )

    problems: list[str] = []
    qdrant = docker = None
    if args.collection:
        try:
            qdrant = qdrant_collection(args.qdrant_url, args.collection)
        except (OSError, urllib.error.URLError, KeyError, ValueError) as exc:
            problems.append(f"Qdrant collection info ({exc})")
        if not args.no_docker:
            try:
                docker = docker_qdrant(args.collection)
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
                problems.append(f"Qdrant disk and memory through docker ({exc})")
    sizes = {}
    for item in args.size:
        label, _, path = item.partition("=")
        if not Path(path).exists():
            problems.append(f"size of {label}: {path} does not exist")
            continue
        sizes[label] = folder_bytes(Path(path))

    profile = {
        "measured_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": machine(),
        "retrievers": {name: spec for name, spec, _ in args.retriever},
        **result,
        "qdrant": qdrant,
        "docker": docker,
        "sizes": sizes,
        "problems": problems,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(markdown(profile), end="")
    failed = [c for checks in result["filters"].values() for c in checks if not c["ok"]]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
