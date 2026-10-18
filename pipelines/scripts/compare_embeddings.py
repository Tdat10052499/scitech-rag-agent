"""Compare the candidate embedding models on the golden set for ADR 0007 (W3-D2-FAO-1).

Input: the chunks and one `embed` output folder per model (the D08 vectors). For each model the
script embeds the golden questions with the same model, ranks every chunk by dot product (the
vectors are L2-normalised, so this is exact cosine search over the whole index, not a small
one), and scores the rankings with LDN's harness (`scitech_eval`, canned retriever). Each
model runs with the `--query-prefix` and without it. It also counts the chunks that are longer
than the model's `max_seq_length` in tokens, because those were cut when they were embedded.

Writes to `--out`: `rankings/`, `configs/` and `runs/` (harness run files) per condition, and
`summary.json` plus `summary.md` with the comparison table.

Usage (Kaggle notebook with the chunks and the embed output added as inputs; GPU optional):
    PYTHONPATH=pipelines/src:evaluation/src python pipelines/scripts/compare_embeddings.py \
        --chunks <chunks dir> --vectors <embed out of model A> --vectors <embed out of model B> \
        --golden evaluation/golden_set/golden.jsonl --query-prefix "<query instruction>" \
        --out <dir>
Run it from the repository root so the harness records the commit. The models come from each
folder's `_embed_state.json`, never from the code. Dependencies: pipelines/requirements-embed.txt
and evaluation/requirements.txt.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

CHUNK_FILE = "chunks.parquet"
CHUNK_MANIFEST = "_chunk_manifest.json"
EMBED_STATE = "_embed_state.json"
DEPTH = 100  # chunks kept per query; the harness reads at most max(ks, MRR depth) of them
KS = [1, 5, 10]


def read_golden_queries(path: Path) -> list[str]:
    """Every text the harness may send: each question, and each follow-up's standalone query."""
    queries: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        for text in (item.get("question"), item.get("standalone_query")):
            if text and text not in queries:
                queries.append(text)
    return queries


def read_chunks(chunks: Path) -> tuple[dict[str, str], dict[str, str]]:
    """`chunk_id` -> `doc_id` and `chunk_id` -> `text`."""
    import pyarrow.parquet as pq

    table = pq.read_table(chunks / CHUNK_FILE, columns=["chunk_id", "doc_id", "text"])
    ids = table.column("chunk_id").to_pylist()
    doc_of = dict(zip(ids, table.column("doc_id").to_pylist(), strict=True))
    text_of = dict(zip(ids, table.column("text").to_pylist(), strict=True))
    return doc_of, text_of


def read_vectors(folder: Path) -> tuple[dict[str, Any], list[str], np.ndarray]:
    """Settings of the embed run, the chunk ids and their vectors (one row per chunk)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    state = json.loads((folder / EMBED_STATE).read_text(encoding="utf-8"))
    parts = sorted(folder.glob("part-*.parquet"))
    if not parts:
        raise ValueError(f"{folder}: no part-*.parquet files")
    tables = [pq.read_table(p, columns=["chunk_id", "embedding"]) for p in parts]
    table = pa.concat_tables(tables)
    embedding = table.column("embedding").combine_chunks()
    dimension = embedding.type.list_size
    matrix = embedding.flatten().to_numpy(zero_copy_only=False).reshape(-1, dimension)
    return state, table.column("chunk_id").to_pylist(), np.ascontiguousarray(matrix, np.float32)


def rank(
    query_vectors: np.ndarray,
    matrix: np.ndarray,
    chunk_ids: list[str],
    doc_of: dict[str, str],
    depth: int = DEPTH,
) -> list[list[dict]]:
    """Top `depth` chunks per query by dot product, best first."""
    scores = np.asarray(query_vectors, np.float32) @ matrix.T
    depth = min(depth, scores.shape[1])
    out = []
    for row in scores:
        top = np.argpartition(-row, depth - 1)[:depth]
        top = top[np.argsort(-row[top], kind="stable")]
        out.append(
            [
                {"chunk_id": chunk_ids[i], "doc_id": doc_of[chunk_ids[i]], "score": float(row[i])}
                for i in top
            ]
        )
    return out


def count_over_limit(
    tokenize: Callable[[list[str]], list[list[int]]],
    texts: Sequence[str],
    doc_ids: Sequence[str],
    limit: int,
    batch_size: int = 2048,
) -> dict[str, Any]:
    """How many chunks have more tokens (special tokens included) than the model reads."""
    lengths: list[int] = []
    for start in range(0, len(texts), batch_size):
        lengths.extend(len(ids) for ids in tokenize(list(texts[start : start + batch_size])))
    over = [i for i, n in enumerate(lengths) if n > limit]
    array = np.asarray(lengths)
    return {
        "max_seq_length": limit,
        "chunks": len(lengths),
        "chunks_over": len(over),
        "documents_over": len({doc_ids[i] for i in over}),
        "tokens_max": int(array.max()) if len(array) else 0,
        "tokens_p99": float(np.percentile(array, 99)) if len(array) else 0.0,
        "tokens_median": float(np.median(array)) if len(array) else 0.0,
    }


def score(
    name: str,
    rankings: dict[str, list[dict]],
    golden: Path,
    snapshot: str,
    out: Path,
    model: str = "",
    prefix: str = "",
) -> dict[str, Any]:
    """Score one ranking with the harness, as asked (`question`) and rewritten for follow-ups.
    The run setup fields (`retriever_type` ... `notes`) will be recorded once #66 (harness
    schema 2) is merged; the harness on main ignores them."""
    import yaml

    from scitech_eval.runner import run_from_config

    rankings_path = out / "rankings" / f"{name}.json"
    rankings_path.parent.mkdir(parents=True, exist_ok=True)
    rankings_path.write_text(json.dumps(rankings, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {}
    for mode in ("question", "standalone_query"):
        config = {
            "name": f"{name}-{mode}",
            "golden_path": str(golden),
            "split": "dev",
            "language": "en",
            "query": mode,
            "ks": KS,
            "dataset_snapshot": snapshot,
            "retriever_type": "dense",
            "embedding_model": model,
            "index_snapshot": "none: exact search over the chunk vectors",
            "notes": f"ADR 0007 comparison; query prefix {prefix!r}",
            "bootstrap": {"resamples": 1000, "seed": 0},
            "retriever": {
                "factory": "scitech_eval.retrievers:canned",
                "params": {"rankings_path": str(rankings_path)},
            },
        }
        config_path = out / "configs" / f"{name}-{mode}.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        run = json.loads(run_from_config(config_path, out / "runs").read_text(encoding="utf-8"))
        result[mode] = {
            "n": run["golden"]["n_evaluated"],
            "metrics": run["metrics"],
            "by_type": run["by_type"],
            "misses_at_5": [q["id"] for q in run["per_question"] if q["recall"]["5"] == 0],
        }
    return result


def compare(
    vectors: list[Path],
    chunks: Path,
    golden: Path,
    query_prefix: str,
    out: Path,
    load_model: Callable[[str], Any],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """`load_model(name)` returns an object with `encode(texts)` (L2-normalised rows),
    `tokenize(texts)` (token ids per text) and `max_seq_length`."""
    out.mkdir(parents=True, exist_ok=True)
    queries = read_golden_queries(golden)
    doc_of, text_of = read_chunks(chunks)
    manifest = json.loads((chunks / CHUNK_MANIFEST).read_text(encoding="utf-8"))
    snapshot = f"chunks {manifest.get('chunked_at', 'unknown')}"
    log(f"{len(queries)} query texts from {golden}; {len(doc_of)} chunks")
    summary: dict[str, Any] = {
        "golden": str(golden),
        "query_texts": len(queries),
        "query_prefix": query_prefix,
        "dataset_snapshot": snapshot,
        "models": [],
    }
    for folder in vectors:
        state, chunk_ids, matrix = read_vectors(folder)
        model_name = state["model"]
        missing = set(doc_of) - set(chunk_ids)
        if missing:
            raise ValueError(f"{folder}: {len(missing)} chunks have no vector")
        log(f"{model_name}: {matrix.shape[0]} vectors of dimension {matrix.shape[1]}")
        model = load_model(model_name)
        entry: dict[str, Any] = {
            "model": model_name,
            "vectors": str(folder),
            "dimension": int(matrix.shape[1]),
            "passage_prefix": state.get("passage_prefix", ""),
            "conditions": {},
        }
        for label, prefix in (("query-prefix", query_prefix), ("no-prefix", "")):
            if label == "query-prefix" and not query_prefix:
                continue
            started = time.perf_counter()
            query_vectors = model.encode([prefix + q for q in queries])
            ranked = rank(query_vectors, matrix, chunk_ids, doc_of)
            seconds = time.perf_counter() - started
            name = f"adr0007-{model_name.split('/')[-1]}-{label}"
            entry["conditions"][label] = {
                "prefix": prefix,
                "encode_and_search_seconds": round(seconds, 3),
                **score(
                    name,
                    dict(zip(queries, ranked, strict=True)),
                    golden,
                    snapshot,
                    out,
                    model=model_name,
                    prefix=prefix,
                ),
            }
            m = entry["conditions"][label]["question"]["metrics"]
            log(f"  {label}: recall@5 {m['recall@5']['mean']:.3f}  MRR {m['mrr']['mean']:.3f}")
        started = time.perf_counter()
        ids = sorted(doc_of)
        entry["tokens"] = count_over_limit(
            model.tokenize,
            [entry["passage_prefix"] + text_of[i] for i in ids],
            [doc_of[i] for i in ids],
            model.max_seq_length,
        )
        entry["tokens"]["seconds"] = round(time.perf_counter() - started, 1)
        log(f"  tokens: {entry['tokens']}")
        summary["models"].append(entry)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: dict[str, Any]) -> str:
    n = next((c["question"]["n"] for m in summary["models"] for c in m["conditions"].values()), 0)
    lines = [
        f"Golden set: `{summary['golden']}` ({n} answerable English dev items scored), "
        f"{summary['dataset_snapshot']}. Exact search over every chunk.",
        "",
        "| Model | Query prefix | recall@1 | recall@5 (95% CI) | recall@10 | MRR "
        "| recall@5, standalone queries | Missed at 5 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for m in summary["models"]:
        for label, c in m["conditions"].items():
            q = c["question"]["metrics"]
            low, high = q["recall@5"]["ci95"]
            s = c["standalone_query"]["metrics"]["recall@5"]["mean"]
            lines.append(
                f"| `{m['model']}` | {'yes' if label == 'query-prefix' else 'no'} "
                f"| {q['recall@1']['mean']:.3f} | {q['recall@5']['mean']:.3f} "
                f"({low:.3f}-{high:.3f}) | {q['recall@10']['mean']:.3f} | {q['mrr']['mean']:.3f} "
                f"| {s:.3f} | {', '.join(c['question']['misses_at_5']) or '-'} |"
            )
    lines += [
        "",
        "| Model | max_seq_length | Chunks over | Documents over | Max tokens | p99 | Median |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in summary["models"]:
        t = m["tokens"]
        lines.append(
            f"| `{m['model']}` | {t['max_seq_length']} | {t['chunks_over']} of {t['chunks']} "
            f"| {t['documents_over']} | {t['tokens_max']} | {t['tokens_p99']:.0f} "
            f"| {t['tokens_median']:.0f} |"
        )
    return "\n".join(lines) + "\n"


class SentenceTransformerModel:
    """Query encoder and tokenizer of a sentence-transformers model, as `embed` uses it."""

    def __init__(self, name: str):
        from scitech_pipelines.embed import SentenceTransformerEncoder

        self._encoder = SentenceTransformerEncoder(name)
        self.max_seq_length = self._encoder.model.max_seq_length

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return self._encoder.encode(texts)

    def tokenize(self, texts: list[str]) -> list[list[int]]:
        tokenizer = self._encoder.model.tokenizer
        return tokenizer(texts, add_special_tokens=True, truncation=False)["input_ids"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunks", type=Path, default=Path("data/processed/chunks"))
    parser.add_argument(
        "--vectors",
        type=Path,
        action="append",
        required=True,
        help="an embed output folder; repeat once per model",
    )
    parser.add_argument("--golden", type=Path, default=Path("evaluation/golden_set/golden.jsonl"))
    parser.add_argument(
        "--query-prefix",
        default="",
        help="instruction put before each query (empty: no-prefix runs only)",
    )
    parser.add_argument("--out", type=Path, default=Path("data/adr0007"))
    args = parser.parse_args()
    try:
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()  # silence "sequence longer than max length" warnings
    except ImportError:
        pass
    compare(
        args.vectors,
        args.chunks,
        args.golden,
        args.query_prefix,
        args.out,
        SentenceTransformerModel,
    )
    print((args.out / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
