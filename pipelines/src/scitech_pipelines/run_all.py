"""One command from an empty data directory to a loaded index (W4-D2-FAO-1).

`run-all` runs download -> clean -> validate -> chunk -> embed -> load, each step as its own
`python -m scitech_pipelines` process, so a step behaves exactly as when it is run by hand and
the Spark JVM of `clean` ends with its step. Every step's output is shown and also written to
`<data-dir>/logs/run-all-<time>/<nn>-<step>.log`; `run-all.json` in the same folder records the
plan, the exit code and the time of every step. The run stops at the first step that fails.

`--limit N` is the small run for weak machines: after the download, a `sample` step keeps the
first N records of the category from the snapshot, and every later step works on that sample in
`<data-dir>/limit-<N>/`, loaded into its own collection (`<collection>_limit_<N>`), so a small run
never touches the full corpus or the full index. `--from` / `--to` run a part of the chain, for
example `--to chunk` on a machine without a GPU and `--from embed` in a GPU notebook.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scitech_pipelines.clean import ARXIV_FILE, DEFAULT_CATEGORY

STEP_NAMES = ("download", "sample", "clean", "validate", "chunk", "embed", "load")
SUMMARY = "run-all.json"
DEFAULT_GOLDEN = Path("evaluation/golden_set/golden.jsonl")
DEFAULT_COLLECTION = "scitech_chunks"

Log = Callable[[str], None]
# Runs one step (its argv after `python -m scitech_pipelines`) and returns its exit code.
RunStep = Callable[[Sequence[str], Path], int]


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]  # after `python -m scitech_pipelines`; empty for `sample`


@dataclass(frozen=True)
class Paths:
    snapshot: Path
    work: Path  # where the processed data of this run goes
    sample: Path | None
    documents: Path
    chunks: Path
    embeddings: Path
    index: Path


def plan_paths(data_dir: Path, *, limit: int | None, snapshot: Path | None) -> Paths:
    """Where every step reads and writes. With `limit`, everything after the download is under
    `<data-dir>/limit-<N>/`."""
    work = data_dir / f"limit-{limit}" if limit else data_dir
    processed = work / "processed"
    return Paths(
        snapshot=snapshot or data_dir / "raw" / "arxiv" / ARXIV_FILE,
        work=work,
        sample=work / "raw" / f"arxiv-first-{limit}.jsonl" if limit else None,
        documents=processed / "documents",
        chunks=processed / "chunks",
        embeddings=processed / "embeddings",
        index=processed / "index",
    )


def plan_steps(
    data_dir: Path,
    *,
    limit: int | None = None,
    snapshot: Path | None = None,
    model: str | None = None,
    device: str | None = None,
    collection: str | None = None,
    category: str = DEFAULT_CATEGORY,
    golden: Path | None = None,
) -> list[Step]:
    """The whole chain with the arguments of every step. `snapshot` (an existing arXiv snapshot)
    skips the download; `golden` is checked by `validate` on a full run only, since a sample
    does not contain the golden documents."""
    paths = plan_paths(data_dir, limit=limit, snapshot=snapshot)
    base = ("--data-dir", str(data_dir))
    steps: list[Step] = []
    if snapshot is None:
        steps.append(Step("download", (*base, "download", "--source", "arxiv")))
    if limit:
        steps.append(Step("sample", ()))
    clean = [*base, "clean", "--input", str(paths.sample or paths.snapshot)]
    clean += ["--out", str(paths.documents), "--category", category]
    if limit:
        clean += ["--sample-size", "0"]
    steps.append(Step("clean", tuple(clean)))
    validate = [*base, "validate", "--input", str(paths.documents), "--category", category]
    if golden and not limit:
        validate += ["--golden", str(golden)]
    steps.append(Step("validate", tuple(validate)))
    steps.append(
        Step(
            "chunk",
            (*base, "chunk", "--input", str(paths.documents), "--out", str(paths.chunks)),
        )
    )
    embed = [*base, "embed", "--input", str(paths.chunks), "--out", str(paths.embeddings)]
    if model:
        embed += ["--model", model]
    if device:
        embed += ["--device", device]
    steps.append(Step("embed", tuple(embed)))
    load = [*base, "load", "--chunks", str(paths.chunks), "--vectors", str(paths.embeddings)]
    load += ["--out", str(paths.index)]
    name = collection or os.environ.get("QDRANT_COLLECTION") or DEFAULT_COLLECTION
    if limit:
        name = f"{name}_limit_{limit}"
    if collection or limit:
        load += ["--collection", name]
    steps.append(Step("load", tuple(load)))
    return steps


def select_steps(steps: Sequence[Step], start: str | None, stop: str | None) -> list[Step]:
    """The steps from `start` to `stop`, both included (names from STEP_NAMES)."""
    names = [s.name for s in steps]
    for value in (start, stop):
        if value is not None and value not in names:
            raise ValueError(f"step {value!r} is not in this run ({', '.join(names)})")
    first = names.index(start) if start else 0
    last = names.index(stop) if stop else len(names) - 1
    if first > last:
        raise ValueError(f"--from {start} comes after --to {stop}")
    return list(steps[first : last + 1])


def sample_snapshot(snapshot: Path, out: Path, limit: int, category: str) -> int:
    """Write the first `limit` records of `snapshot` (arXiv JSON Lines) whose `categories`
    contain `category` to `out`. Returns the number written (less at the end of the file)."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if not snapshot.is_file():
        raise FileNotFoundError(f"{snapshot}: no arXiv snapshot (run `download` first)")
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    tmp = out.with_name(out.name + ".tmp")
    with snapshot.open(encoding="utf-8") as src, tmp.open("w", encoding="utf-8") as dst:
        for line in src:
            if category not in line:  # cheap test before parsing the line
                continue
            record = json.loads(line)
            if category not in str(record.get("categories") or "").split():
                continue
            dst.write(line if line.endswith("\n") else line + "\n")
            written += 1
            if written == limit:
                break
    tmp.replace(out)
    return written


def tee_step(argv: Sequence[str], log_file: Path) -> int:
    """Run `python -m scitech_pipelines <argv>`, show its output and copy it to `log_file`."""
    command = [sys.executable, "-m", "scitech_pipelines", *argv]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with log_file.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        return process.wait()


def run_all(
    data_dir: Path,
    steps: Sequence[Step],
    *,
    limit: int | None = None,
    snapshot: Path | None = None,
    category: str = DEFAULT_CATEGORY,
    run_step: RunStep = tee_step,
    log: Log = print,
) -> int:
    """Run `steps` in order and return the exit code of the run (that of the failed step)."""
    paths = plan_paths(data_dir, limit=limit, snapshot=snapshot)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs = data_dir / "logs" / f"run-all-{stamp}"
    logs.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "step": "run-all",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_dir": str(data_dir),
        "work_dir": str(paths.work),
        "limit": limit,
        "category": category,
        "steps": [],
    }
    started, code = time.monotonic(), 0
    for i, step in enumerate(steps, 1):
        log_file = logs / f"{i:02d}-{step.name}.log"
        log(f"run-all: step {i}/{len(steps)} {step.name} (log {log_file})")
        t = time.monotonic()
        if step.name == "sample":
            assert limit and paths.sample is not None
            written = sample_snapshot(paths.snapshot, paths.sample, limit, category)
            message = f"sample: {written:,} {category} records -> {paths.sample}"
            log_file.write_text(message + "\n", encoding="utf-8")
            log(message)
            code = 0 if written else 1
        else:
            code = run_step(step.argv, log_file)
        seconds = round(time.monotonic() - t, 1)
        summary["steps"].append(
            {"name": step.name, "argv": list(step.argv), "exit_code": code, "seconds": seconds}
        )
        log(f"run-all: {step.name} {'done' if code == 0 else 'FAILED'} in {seconds} s")
        if code != 0:
            break
    summary["seconds"] = round(time.monotonic() - started, 1)
    summary["exit_code"] = code
    (logs / SUMMARY).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if code == 0:
        log(f"run-all: {len(steps)} step(s) done in {summary['seconds']} s; logs in {logs}")
    else:
        log(f"run-all: stopped at {summary['steps'][-1]['name']} (exit {code}); see {logs}")
    return code
