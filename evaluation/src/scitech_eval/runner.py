"""Run a retrieval evaluation and write a run file (evaluation/PLAN.md sections 4.1 and 6)."""

from __future__ import annotations

import hashlib
import importlib
import json
import statistics
import subprocess
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scitech_eval.golden import GoldenItem, load_golden
from scitech_eval.metrics import MRR_DEPTH, bootstrap_ci, mean, recall_at_k, reciprocal_rank
from scitech_eval.retrievers import Retriever

SCHEMA_VERSION = 2
QUERY_MODES = ("question", "standalone_query")
NOTE = (
    "Relevance labels are incomplete (pooling, PLAN.md section 7); recall and MRR are "
    "conservative. Unanswerable items are excluded. One run per condition. Timings are the "
    "wall-clock time of retriever.search on the machine that ran it, not a latency benchmark "
    "(PLAN.md section 4.4)."
)


def load_config(path: Path) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{path}: config must be a YAML mapping")
    for key in ("name", "golden_path"):
        if not config.get(key):
            raise ValueError(f"{path}: missing '{key}'")
    if not config.get("retriever", {}).get("factory"):
        raise ValueError(f"{path}: missing 'retriever.factory' (module:callable)")
    config.setdefault("split", "dev")  # decisions use dev items; test items only for final numbers
    config.setdefault("language", "en")  # Vietnamese items are reported separately
    config.setdefault("query", "question")  # question | standalone_query (follow-up items)
    config.setdefault("ks", [1, 5, 10])
    config.setdefault("dataset_snapshot", "unspecified")
    config.setdefault(
        "retriever_type", "unspecified"
    )  # label for reports: dense, bm25, hybrid, ...
    config.setdefault("embedding_model", None)  # model id for dense and hybrid; none for BM25
    config.setdefault("index_snapshot", "unspecified")  # id of the loaded index (FAO's manifest)
    config.setdefault("notes", "")
    config.setdefault("bootstrap", {})
    ks = config["ks"]
    if not ks or not all(isinstance(k, int) and k > 0 for k in ks):
        raise ValueError(f"{path}: 'ks' must be positive integers")
    if config["query"] not in QUERY_MODES:
        raise ValueError(f"{path}: 'query' must be one of {', '.join(QUERY_MODES)}")
    if config["split"] not in ("dev", "test", "all"):
        raise ValueError(f"{path}: 'split' must be dev, test or all")
    for key in ("retriever_type", "index_snapshot", "notes"):
        if not isinstance(config[key], str):
            raise ValueError(f"{path}: '{key}' must be a string")
    if config["embedding_model"] is not None and not isinstance(config["embedding_model"], str):
        raise ValueError(f"{path}: 'embedding_model' must be a string or empty")
    return config


def build_retriever(spec: dict) -> Retriever:
    module_name, _, attr = spec["factory"].partition(":")
    factory = getattr(importlib.import_module(module_name), attr)
    return factory(**spec.get("params", {}))


def git_commit() -> str:
    """Commit hash of the code that produced the run, '+dirty' if the tree has changes."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return head + ("+dirty" if status else "")


def _summary(values: list[float], resamples: int, seed: int) -> dict:
    low, high = bootstrap_ci(values, resamples=resamples, seed=seed)
    return {"mean": mean(values), "ci95": [low, high]}


def query_for(item: GoldenItem, mode: str) -> str:
    """Text sent to the retriever: the question as asked, or the self-contained rewrite.

    `standalone_query` exists only on follow-up items; every other item keeps its question.
    """
    if mode == "standalone_query" and item.standalone_query:
        return item.standalone_query
    return item.question


def run_retrieval(
    config: dict,
    items: list[GoldenItem],
    retriever: Retriever,
    clock: Callable[[], float] = time.perf_counter,
) -> dict:
    """Score `retriever` on the answerable `items` selected by the config.

    `clock` returns seconds; tests pass a fake one. It is read once at the start, twice around each
    search and once at the end.
    """
    ks = sorted(set(config["ks"]))
    depth = max(max(ks), MRR_DEPTH)
    resamples = config["bootstrap"].get("resamples", 1000)
    seed = config["bootstrap"].get("seed", 0)

    selected = [
        i
        for i in items
        if (config["split"] in ("all", i.split)) and i.language == config["language"]
    ]
    answerable = [i for i in selected if i.type != "unanswerable"]
    if not answerable:
        raise ValueError("no answerable golden items match the split and language in the config")

    per_question = []
    run_started = clock()
    for item in answerable:
        query = query_for(item, config["query"])
        search_started = clock()
        hits = retriever.search(query, depth)
        search_seconds = clock() - search_started
        doc_ids = [h.doc_id for h in hits]
        relevant = set(item.relevant_doc_ids)
        per_question.append(
            {
                "id": item.id,
                "type": item.type,
                "query": query,
                "search_seconds": round(search_seconds, 6),
                "relevant_doc_ids": list(item.relevant_doc_ids),
                "retrieved": [{"chunk_id": h.chunk_id, "doc_id": h.doc_id} for h in hits],
                "recall": {str(k): recall_at_k(relevant, doc_ids, k) for k in ks},
                "rr": reciprocal_rank(relevant, doc_ids),
            }
        )

    def column(rows: list[dict], name: str) -> list[float]:
        if name == "mrr":
            return [r["rr"] for r in rows]
        return [r["recall"][name.removeprefix("recall@")] for r in rows]

    names = [f"recall@{k}" for k in ks] + ["mrr"]
    metrics = {n: _summary(column(per_question, n), resamples, seed) for n in names}

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in per_question:
        by_type[row["type"]].append(row)
    by_type_out = {
        t: {"n": len(rows), **{n: mean(column(rows, n)) for n in names}}
        for t, rows in sorted(by_type.items())
    }

    searches = [r["search_seconds"] for r in per_question]
    timings = {
        "run_seconds": round(clock() - run_started, 6),
        "search_seconds": {
            "total": round(sum(searches), 6),
            "median": round(statistics.median(searches), 6),
            "max": round(max(searches), 6),
        },
    }

    golden_path = Path(config["golden_path"])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "retrieval",
        "name": config["name"],
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "git_commit": git_commit(),
        "dataset_snapshot": config["dataset_snapshot"],
        "retriever_type": config["retriever_type"],
        "embedding_model": config["embedding_model"],
        "index_snapshot": config["index_snapshot"],
        "notes": config["notes"],
        "timings": timings,
        "golden": {
            "path": str(golden_path),
            "sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
            "split": config["split"],
            "language": config["language"],
            "n_evaluated": len(answerable),
            "n_unanswerable_excluded": len(selected) - len(answerable),
        },
        "config": config,
        "metrics": metrics,
        "by_type": by_type_out,
        "per_question": per_question,
        "note": NOTE,
    }


def write_run(result: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result['timestamp']}-{result['name']}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_from_config(config_path: Path, out_dir: Path) -> Path:
    config = load_config(config_path)
    items = load_golden(Path(config["golden_path"]))
    result = run_retrieval(config, items, build_retriever(config["retriever"]))
    return write_run(result, out_dir)
