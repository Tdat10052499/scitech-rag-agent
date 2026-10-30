"""Command line: `retrieval`, `compare`, `check-golden`, and the faithfulness pilot tools
`make-sheet` and `check-labels`, and `answers` (answers + faithfulness judge)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scitech_eval.answer_run import run_from_answer_config
from scitech_eval.answers import check_labels, make_sheet
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

    a = sub.add_parser("answers", help="answer golden questions with the agent and run the judge")
    a.add_argument("--config", required=True, type=Path)
    a.add_argument("--out-dir", type=Path, default=Path("evaluation/runs"))

    m = sub.add_parser("make-sheet", help="write the labelling sheet for an answers.jsonl")
    m.add_argument("answers", type=Path, help="answers.jsonl of the faithfulness pilot")
    m.add_argument("--out-dir", type=Path, default=Path("evaluation/pilot/faithfulness"))

    k = sub.add_parser("check-labels", help="check a filled labelling sheet")
    k.add_argument("sheet", type=Path, help="labels-<annotator>.csv")

    args = parser.parse_args(argv)

    if args.command == "answers":
        try:
            run_path, answers_path = run_from_answer_config(args.config, args.out_dir)
        except (GoldenError, OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        run = json.loads(run_path.read_text(encoding="utf-8"))
        c, f = run["counts"], run["metrics"]["faithfulness_macro"]
        print(f"wrote {run_path} and {answers_path}")
        print(
            f"  answers {c['answers']}, errors {c['errors']}, refused {c['refused_answerable']}, "
            f"judged {c['judged_answers']}, sentences {c['sentences']}, "
            f"judge_error {c['judge_error']}"
        )
        if f:
            print(f"  faithfulness (macro, n={f['n']}) {f['mean']:.3f} CI {f['ci95']}")
        return 0

    if args.command == "make-sheet":
        try:
            sheet, chunks = make_sheet(args.answers, args.out_dir)
        except (OSError, KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {sheet} and {chunks}")
        return 0

    if args.command == "check-labels":
        try:
            problems = check_labels(args.sheet)
        except (OSError, KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for p in problems:
            print(p)
        print(f"{args.sheet}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        return 1 if problems else 0

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
