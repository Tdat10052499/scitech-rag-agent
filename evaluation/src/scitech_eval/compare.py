"""Compare run files written by `retrieval` (evaluation/PLAN.md section 4.1, Reporting).

The first run is the baseline. Every other run is also compared with it question by question:
difference of the per-question value, wins / losses / ties, and a bootstrap interval of the mean
difference. The pairing uses the golden item id, so it is only meaningful for runs on the same
questions; the report warns when the runs do not match.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from scitech_eval.metrics import bootstrap_ci, mean

LABELS = string.ascii_uppercase
TIE = 1e-9
UNSPECIFIED = "unspecified"


def load_run(path: Path) -> dict:
    """Read one run file; raise ValueError if it is not a run written by `retrieval`."""
    run = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(run, dict)
        or run.get("kind") != "retrieval"
        or "metrics" not in run
        or "per_question" not in run
    ):
        raise ValueError(f"{path}: not a run file written by 'retrieval'")
    return run


def _value(row: dict, metric: str) -> float:
    if metric == "mrr":
        return row["rr"]
    return row["recall"][metric.removeprefix("recall@")]


def _describe(label: str, run: dict) -> dict:
    golden = run.get("golden", {})
    timings = run.get("timings", {})
    return {
        "label": label,
        "name": run.get("name", "unknown"),
        "retriever_type": run.get("retriever_type", "unspecified"),
        "embedding_model": run.get("embedding_model"),
        "index_snapshot": run.get("index_snapshot", "unspecified"),
        "dataset_snapshot": run.get("dataset_snapshot", "unspecified"),
        "git_commit": run.get("git_commit", "unknown"),
        "split": golden.get("split", "unknown"),
        "language": golden.get("language", "unknown"),
        "n": golden.get("n_evaluated", len(run["per_question"])),
        "golden_sha256": golden.get("sha256"),
        "query": run.get("config", {}).get("query", "question"),
        "search_median_seconds": timings.get("search_seconds", {}).get("median"),
        "timestamp": run.get("timestamp", "unknown"),
        "notes": run.get("notes", ""),
    }


def compare_runs(runs: list[dict], resamples: int = 1000, seed: int = 0) -> dict:
    """Metrics side by side, plus paired differences of every run against the first one."""
    if len(runs) < 2:
        raise ValueError("compare needs at least two runs")
    if len(runs) > len(LABELS):
        raise ValueError(f"compare takes at most {len(LABELS)} runs")
    labels = LABELS[: len(runs)]
    described = [_describe(label, run) for label, run in zip(labels, runs, strict=True)]
    base = described[0]
    warnings: list[str] = []

    for d in described[1:]:
        if d["golden_sha256"] != base["golden_sha256"]:
            warnings.append(
                f"{d['label']} used a different golden file than {base['label']} "
                "(sha256 differs); only questions with the same id are paired."
            )
        if (d["split"], d["language"]) != (base["split"], base["language"]):
            warnings.append(
                f"{d['label']} scored split {d['split']} / language {d['language']}, "
                f"{base['label']} scored {base['split']} / {base['language']}."
            )
        if d["query"] != base["query"]:
            warnings.append(
                f"{d['label']} searched with query={d['query']}, {base['label']} with "
                f"query={base['query']}."
            )
        for field in ("index_snapshot", "dataset_snapshot"):
            if d[field] != base[field]:
                warnings.append(
                    f"{d['label']} has {field} {d[field]}, {base['label']} has {base[field]}; "
                    "the runs did not search the same data."
                )
    for d in described:
        missing = [f for f in ("index_snapshot", "dataset_snapshot") if d[f] == UNSPECIFIED]
        if missing:
            warnings.append(
                f"{d['label']} did not record {' and '.join(missing)} (still 'unspecified' in "
                "its config), so it cannot be checked against the other runs."
            )

    names = [n for n in runs[0]["metrics"] if all(n in r["metrics"] for r in runs[1:])]
    if not names:
        raise ValueError("the runs have no metric in common (different ks?)")
    left_out = sorted({n for r in runs for n in r["metrics"]} - set(names))
    if left_out:
        warnings.append(f"metrics that are not in every run are left out: {', '.join(left_out)}.")
    metrics = {n: [r["metrics"][n] for r in runs] for n in names}

    base_rows = {row["id"]: row for row in runs[0]["per_question"]}
    paired = []
    for label, run in zip(labels[1:], runs[1:], strict=True):
        rows = {row["id"]: row for row in run["per_question"]}
        common = [i for i in base_rows if i in rows]
        if not common:
            raise ValueError(f"{label} and {labels[0]} have no question in common")
        if len(common) < max(len(base_rows), len(rows)):
            warnings.append(
                f"{label} and {labels[0]} share {len(common)} questions "
                f"({labels[0]} has {len(base_rows)}, {label} has {len(rows)}); "
                "the paired numbers use the shared ones."
            )
        entry: dict = {"label": label, "baseline": labels[0], "n": len(common), "metrics": {}}
        for name in names:
            diffs = [_value(rows[i], name) - _value(base_rows[i], name) for i in common]
            low, high = bootstrap_ci(diffs, resamples=resamples, seed=seed)
            mean_diff = mean(diffs)
            entry["metrics"][name] = {
                "mean_diff": mean_diff,
                # Mean difference of a recall times the number of questions: how many questions'
                # worth of relevant documents were gained (+) or lost (-). Not defined for MRR.
                "questions_diff": None if name == "mrr" else mean_diff * len(common),
                "ci95": [low, high],
                "wins": sum(d > TIE for d in diffs),
                "losses": sum(d < -TIE for d in diffs),
                "ties": sum(abs(d) <= TIE for d in diffs),
            }
        paired.append(entry)

    return {"runs": described, "metrics": metrics, "paired": paired, "warnings": warnings}


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[c]) for r in [header, *rows]) for c in range(len(header))]
    return [
        "  ".join(cell.ljust(w) for cell, w in zip(r, widths, strict=True)).rstrip()
        for r in [header, *rows]
    ]


def format_comparison(result: dict) -> str:
    """Plain-text report of `compare_runs`."""
    lines = ["Runs"]
    for d in result["runs"]:
        lines.append(
            f"  {d['label']}  {d['name']}  type={d['retriever_type']}  "
            f"embedding={d['embedding_model'] or '-'}  index={d['index_snapshot']}  "
            f"dataset={d['dataset_snapshot']}"
        )
        median = d["search_median_seconds"]
        timing = f"  search median {median:.3f} s" if median is not None else ""
        lines.append(
            f"     commit {d['git_commit'][:12]}  golden {d['split']}/{d['language']} "
            f"n={d['n']}  query={d['query']}{timing}"
        )
        if d["notes"]:
            lines.append(f"     notes: {d['notes']}")

    if result["warnings"]:
        lines.append("")
        lines.extend(f"WARNING: {w}" for w in result["warnings"])

    labels = [d["label"] for d in result["runs"]]
    rows = []
    for name, values in result["metrics"].items():
        cells = [f"{v['mean']:.3f} [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}]" for v in values]
        rows.append([name, *cells])
    lines += ["", "Metrics (mean and 95% bootstrap interval over questions)"]
    lines += _table(["metric", *labels], rows)

    for entry in result["paired"]:
        rows = []
        for name, m in entry["metrics"].items():
            low, high = m["ci95"]
            questions = m["questions_diff"]
            rows.append(
                [
                    name,
                    f"{m['mean_diff']:+.3f}",
                    "-" if questions is None else f"{questions:+.1f}",
                    f"[{low:+.3f}, {high:+.3f}]",
                    str(m["wins"]),
                    str(m["losses"]),
                    str(m["ties"]),
                ]
            )
        lines += [
            "",
            f"{entry['label']} against {entry['baseline']}, {entry['n']} questions in common "
            f"(difference {entry['label']} - {entry['baseline']}; wins and losses are "
            f"{entry['label']}'s; 'questions' is the mean difference times {entry['n']}, "
            "recall rows only)",
        ]
        lines += _table(
            ["metric", "mean diff", "questions", "95% interval", "wins", "losses", "ties"], rows
        )
    return "\n".join(lines) + "\n"
