"""Retrieval misses for the error analysis (W7-D3-FAO-1): which golden questions each run missed.

Reads one or more retrieval run files of `scitech_eval` (R1 to R3 of `evaluation/RUNS.md`: dense,
bm25, hybrid) and lists every answerable question where at least one run did not find all of its
`relevant_doc_ids` in the top `--k`. For each such question it shows the question (and the
standalone query of a follow-up), the relevant documents with their titles, the rank of each one
in every run (or `-` when it is not in the run's list), and the titles of each run's top hits.
The categories (vocabulary mismatch, chunking split, missing document, ambiguous question, ...)
are a human judgement, so the script only writes an empty `category` column to fill in.

Usage (repository root; titles come from the chunks, so pyarrow is needed for `--chunks`):
    python pipelines/scripts/retrieval_misses.py \
        evaluation/runs/<R1>.json evaluation/runs/<R2>.json evaluation/runs/<R3>.json \
        --chunks data/processed/chunks --k 5 \
        --out data/reports/retrieval-misses.md --csv data/reports/retrieval-misses.csv
Without `--chunks` the titles are left out. Standard library otherwise.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TOP_TITLES = 3


def load_run(path: Path) -> dict[str, Any]:
    run = json.loads(Path(path).read_text(encoding="utf-8"))
    if "per_question" not in run:
        raise ValueError(f"{path}: no per_question results (not a retrieval run file?)")
    return run


def run_label(run: Mapping[str, Any], path: Path) -> str:
    return str(run.get("retriever_type") or run.get("name") or Path(path).stem)


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    items = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            items[item["id"]] = item
    return items


def doc_titles(chunks: Path, ids: set[str]) -> dict[str, str]:
    """Title of each doc id in `ids` that has a chunk in `chunks.parquet`."""
    import pyarrow.parquet as pq

    path = Path(chunks)
    if path.is_dir():
        path = path / "chunks.parquet"
    table = pq.read_table(path, columns=["doc_id", "title"]).to_pydict()
    return {d: t for d, t in zip(table["doc_id"], table["title"], strict=True) if d in ids}


def ranks(retrieved: Sequence[Mapping[str, Any]], relevant: Sequence[str]) -> dict[str, int | None]:
    """1-based rank of the first chunk of each relevant doc in a run's list, None when absent."""
    order: list[str] = []
    for hit in retrieved:
        if hit["doc_id"] not in order:
            order.append(hit["doc_id"])
    return {d: order.index(d) + 1 if d in order else None for d in relevant}


def misses(runs: Sequence[tuple[str, Mapping[str, Any]]], k: int) -> list[dict[str, Any]]:
    """Questions where some run found fewer than all relevant docs in its top k, in golden order.

    Each entry holds the question id, type, query, relevant ids, and per run the ranks of the
    relevant docs and its top doc ids. Questions without relevant docs (unanswerable) are skipped.
    """
    by_run = [(label, {q["id"]: q for q in run["per_question"]}) for label, run in runs]
    ids = list(by_run[0][1])
    out = []
    for qid in ids:
        first = by_run[0][1][qid]
        relevant = list(first.get("relevant_doc_ids") or [])
        if not relevant:
            continue
        per_run = {}
        for label, questions in by_run:
            q = questions.get(qid)
            if q is None:
                continue
            r = ranks(q.get("retrieved") or [], relevant)
            per_run[label] = {
                "ranks": r,
                "found": sum(1 for v in r.values() if v is not None and v <= k),
                "top": [h["doc_id"] for h in (q.get("retrieved") or [])][:TOP_TITLES],
            }
        missed_by = [label for label, v in per_run.items() if v["found"] < len(relevant)]
        if missed_by:
            out.append(
                {
                    "id": qid,
                    "type": first.get("type"),
                    "query": first.get("query"),
                    "relevant": relevant,
                    "runs": per_run,
                    "missed_by": missed_by,
                }
            )
    return out


def summary(
    found: Sequence[Mapping[str, Any]], labels: Sequence[str], answerable: int
) -> list[str]:
    lines = [f"Answerable questions: {answerable}; missed by at least one run: {len(found)}.", ""]
    lines += ["| Run | Questions missed |", "|---|---:|"]
    for label in labels:
        lines.append(f"| {label} | {sum(1 for m in found if label in m['missed_by'])} |")
    every = sum(1 for m in found if len(m["missed_by"]) == len(labels))
    lines += ["", f"Missed by every run: {every}.", ""]
    return lines


def render(
    found: Sequence[Mapping[str, Any]],
    labels: Sequence[str],
    golden: Mapping[str, Mapping[str, Any]],
    titles: Mapping[str, str],
    k: int,
    answerable: int,
) -> str:
    out = [f"# Retrieval misses at k = {k}", ""]
    out += summary(found, labels, answerable)
    for m in found:
        item = golden.get(m["id"], {})
        out.append(f"## {m['id']} ({m['type']}), missed by {', '.join(m['missed_by'])}")
        out.append("")
        out.append(f"- Question: {item.get('question', m['query'])}")
        if item.get("standalone_query"):
            out.append(f"- Standalone query: {item['standalone_query']}")
        if m["query"] and m["query"] != item.get("question"):
            out.append(f"- Query sent: {m['query']}")
        out.append("- Relevant:")
        for d in m["relevant"]:
            rank = ", ".join(f"{label} {v['ranks'][d] or '-'}" for label, v in m["runs"].items())
            name = f"{d} {titles[d]}" if d in titles else d
            out.append(f"  - {name} (rank: {rank})")
        out.append("- Top hits:")
        for label, v in m["runs"].items():
            hits = "; ".join(f"{d} {titles[d]}" if d in titles else d for d in v["top"])
            out.append(f"  - {label}: {hits}")
        out.append("- Category: ")
        out.append("")
    return "\n".join(out)


def write_csv(path: Path, found: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "type", "missed_by", "category", "note"])
        for m in found:
            writer.writerow([m["id"], m["type"], " ".join(m["missed_by"]), "", ""])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", type=Path, nargs="+", help="retrieval run files (R1 to R3)")
    parser.add_argument("--golden", type=Path, default=Path("evaluation/golden_set/golden.jsonl"))
    parser.add_argument("--chunks", type=Path, help="chunk folder or chunks.parquet, for titles")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--out", type=Path, help="write the Markdown here (default: stdout)")
    parser.add_argument("--csv", type=Path, help="also write a labelling sheet")
    args = parser.parse_args(argv)

    runs = []
    for path in args.runs:
        run = load_run(path)
        runs.append((run_label(run, path), run))
    labels = [label for label, _ in runs]
    if len(set(labels)) != len(labels):
        raise SystemExit(f"two runs have the same label: {labels}")
    golden = load_golden(args.golden)
    found = misses(runs, args.k)
    answerable = sum(1 for q in runs[0][1]["per_question"] if q.get("relevant_doc_ids"))
    ids = {d for m in found for d in m["relevant"]}
    ids |= {d for m in found for v in m["runs"].values() for d in v["top"]}
    titles = doc_titles(args.chunks, ids) if args.chunks else {}
    text = render(found, labels, golden, titles, args.k, answerable)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}: {len(found)} questions missed by at least one run")
    else:
        sys.stdout.write(text + "\n")
    if args.csv:
        write_csv(args.csv, found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
