"""Command line: `retrieval --config <yaml>`, `compare <run> <run> ...` and `check-golden`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scitech_eval.compare import compare_runs, format_comparison, load_run
from scitech_eval.golden import GoldenError, check_golden, read_corpus_doc_ids
from scitech_eval.runner import run_from_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scitech_eval")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("retrieval", help="run recall@k and MRR for the retriever in a config")
    r.add_argument("--config", required=True, type=Path)
    r.add_argument("--out-dir", type=Path, default=Path("evaluation/runs"))

    c = sub.add_parser("compare", help="compare two or more run files; the first is the baseline")
    c.add_argument("runs", nargs="+", type=Path, help="run files written by 'retrieval'")

    g = sub.add_parser("check-golden", help="check golden.jsonl against FORMAT.md")
    g.add_argument("path", nargs="?", type=Path, default=Path("evaluation/golden_set/golden.jsonl"))
    g.add_argument("--corpus", type=Path, help="JSONL corpus file to check doc ids against")
    g.add_argument("--id-field", default="doc_id", help="field holding the doc id in --corpus")

    args = parser.parse_args(argv)

    if args.command == "compare":
        if len(args.runs) < 2:
            parser.error("compare needs at least two run files")
        try:
            runs = [load_run(path) for path in args.runs]
            base_config = runs[0].get("config", {}).get("bootstrap", {})
            result = compare_runs(
                runs,
                resamples=base_config.get("resamples", 1000),
                seed=base_config.get("seed", 0),
            )
        except (OSError, KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(format_comparison(result), end="")
        return 0

    if args.command == "check-golden":
        try:
            corpus = read_corpus_doc_ids(args.corpus, args.id_field) if args.corpus else None
            problems = check_golden(args.path, corpus)
        except (OSError, KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for p in problems:
            print(p)
        print(f"{args.path}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        return 1 if problems else 0

    try:
        path = run_from_config(args.config, args.out_dir)
    except (GoldenError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    result = json.loads(path.read_text(encoding="utf-8"))
    print(f"wrote {path} (n={result['golden']['n_evaluated']})")
    for name, m in result["metrics"].items():
        low, high = m["ci95"]
        print(f"  {name:<10} {m['mean']:.3f}  95% CI [{low:.3f}, {high:.3f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
