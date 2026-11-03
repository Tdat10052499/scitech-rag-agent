import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scitech_pipelines.cli import main
from scitech_pipelines.run_all import (
    INTERRUPTED,
    SUMMARY,
    Step,
    plan_steps,
    run_all,
    sample_snapshot,
    select_steps,
    show,
    tee_step,
)

SRC = Path(__file__).resolve().parents[1] / "src"


def write_snapshot(path: Path, categories: list[str]) -> Path:
    lines = [
        json.dumps({"id": f"2401.{i:05d}", "categories": c, "abstract": "a"})
        for i, c in enumerate(categories)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def names(steps: list[Step]) -> list[str]:
    return [s.name for s in steps]


def argv_of(steps: list[Step], name: str) -> list[str]:
    return list(next(s for s in steps if s.name == name).argv)


def test_full_run_plan(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    golden = tmp_path / "golden.jsonl"
    steps = plan_steps(tmp_path, model="m", golden=golden)
    assert names(steps) == ["download", "clean", "validate", "chunk", "embed", "load"]
    processed = tmp_path / "processed"
    clean = argv_of(steps, "clean")
    assert clean[:3] == ["--data-dir", str(tmp_path), "clean"]
    assert clean[clean.index("--input") + 1].endswith("arxiv-metadata-oai-snapshot.json")
    assert clean[clean.index("--out") + 1] == str(processed / "documents")
    assert "--sample-size" not in clean
    assert argv_of(steps, "validate")[-2:] == ["--golden", str(golden)]
    assert argv_of(steps, "embed")[-2:] == ["--model", "m"]
    load = argv_of(steps, "load")
    assert load[load.index("--vectors") + 1] == str(processed / "embeddings")
    assert load[load.index("--out") + 1] == str(processed / "index")
    assert "--collection" not in load  # the store's own setting (QDRANT_COLLECTION)


def test_limit_run_keeps_away_from_the_full_corpus_and_index(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("QDRANT_COLLECTION", "scitech_chunks")
    steps = plan_steps(tmp_path, limit=50, golden=tmp_path / "golden.jsonl")
    assert names(steps) == ["download", "sample", "clean", "validate", "chunk", "embed", "load"]
    work = tmp_path / "limit-50"
    clean = argv_of(steps, "clean")
    assert clean[clean.index("--input") + 1] == str(work / "raw" / "arxiv-first-50.jsonl")
    assert clean[clean.index("--out") + 1] == str(work / "processed" / "documents")
    assert clean[-2:] == ["--sample-size", "0"]
    assert "--golden" not in argv_of(steps, "validate")  # a sample has no golden documents
    assert argv_of(steps, "load")[-2:] == ["--collection", "scitech_chunks_limit_50"]
    for step in steps:
        paths = [a for a in step.argv if a.startswith(str(tmp_path)) and a != str(tmp_path)]
        assert all(p.startswith(str(work)) for p in paths), step


def test_snapshot_on_disk_skips_the_download(tmp_path: Path):
    snapshot = tmp_path / "snap.json"
    steps = plan_steps(tmp_path, snapshot=snapshot, collection="mine")
    assert names(steps)[0] == "clean"
    clean = argv_of(steps, "clean")
    assert clean[clean.index("--input") + 1] == str(snapshot)
    assert argv_of(steps, "load")[-2:] == ["--collection", "mine"]


def test_select_steps(tmp_path: Path):
    steps = plan_steps(tmp_path, limit=5)
    assert names(select_steps(steps, None, "chunk")) == [
        "download",
        "sample",
        "clean",
        "validate",
        "chunk",
    ]
    assert names(select_steps(steps, "embed", None)) == ["embed", "load"]
    assert names(select_steps(steps, "load", "load")) == ["load"]
    with pytest.raises(ValueError, match="comes after"):
        select_steps(steps, "load", "clean")
    with pytest.raises(ValueError, match="not in this run"):
        select_steps(plan_steps(tmp_path, snapshot=tmp_path / "s"), "download", None)


def test_sample_keeps_the_first_records_of_the_category(tmp_path: Path):
    snapshot = write_snapshot(
        tmp_path / "snap.json", ["cs.AI", "cs.CL", "cs.CLX", "cs.LG cs.CL", "cs.CL", "cs.CL"]
    )
    out = tmp_path / "out" / "sample.jsonl"
    assert sample_snapshot(snapshot, out, 2, "cs.CL") == 2
    ids = [json.loads(line)["id"] for line in out.read_text().splitlines()]
    assert ids == ["2401.00001", "2401.00003"]  # cs.CLX is another category
    assert sample_snapshot(snapshot, out, 10, "cs.CL") == 4  # end of the file
    assert not list(out.parent.glob("*.tmp"))
    with pytest.raises(FileNotFoundError):
        sample_snapshot(tmp_path / "missing.json", out, 2, "cs.CL")


def test_run_all_runs_in_order_logs_and_stops_at_a_failure(tmp_path: Path):
    snapshot = write_snapshot(tmp_path / "snap.json", ["cs.CL", "cs.CL", "cs.AI"])
    steps = plan_steps(tmp_path, limit=2, snapshot=snapshot, model="m")
    calls: list[str] = []

    def fake(argv, log_file: Path) -> int:
        step = argv[2]
        calls.append(step)
        log_file.write_text(f"{step} output\n", encoding="utf-8")
        return 3 if step == "embed" else 0

    code = run_all(tmp_path, steps, limit=2, snapshot=snapshot, run_step=fake, log=lambda _: None)
    assert code == 3
    assert calls == ["clean", "validate", "chunk", "embed"]  # load never ran
    (logs,) = (tmp_path / "logs").iterdir()
    summary = json.loads((logs / SUMMARY).read_text())
    assert summary["exit_code"] == 3 and summary["limit"] == 2
    assert [(s["name"], s["exit_code"]) for s in summary["steps"]] == [
        ("sample", 0),
        ("clean", 0),
        ("validate", 0),
        ("chunk", 0),
        ("embed", 3),
    ]
    assert (logs / "01-sample.log").read_text().startswith("sample: 2 cs.CL records")
    assert (logs / "05-embed.log").read_text() == "embed output\n"
    sample = tmp_path / "limit-2" / "raw" / "arxiv-first-2.jsonl"
    assert len(sample.read_text().splitlines()) == 2


def test_tee_step_shows_and_logs_the_output(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setenv("PYTHONPATH", str(SRC))
    log_file = tmp_path / "help.log"
    assert tee_step(["run-all", "--help"], log_file) == 0
    text = log_file.read_text(encoding="utf-8")
    assert "--limit" in text and "--limit" in capsys.readouterr().out
    assert text.startswith("$ ")
    assert tee_step(["no-such-step"], tmp_path / "bad.log") == 2  # argparse error


def stop_at(name: str, error: BaseException):
    def fake(argv, log_file: Path) -> int:
        if argv[2] == name:
            raise error
        return 0

    return fake


def summary_of(data_dir: Path) -> dict:
    (logs,) = (data_dir / "logs").iterdir()
    return json.loads((logs / SUMMARY).read_text())


def test_interrupted_run_keeps_the_record_of_its_steps(tmp_path: Path):
    snapshot = write_snapshot(tmp_path / "snap.json", ["cs.CL"])
    steps = plan_steps(tmp_path, snapshot=snapshot, model="m")
    fake = stop_at("chunk", KeyboardInterrupt())
    code = run_all(tmp_path, steps, snapshot=snapshot, run_step=fake, log=lambda _: None)
    assert code == INTERRUPTED == 130
    summary = summary_of(tmp_path)
    assert summary["exit_code"] == INTERRUPTED
    assert [(s["name"], s["exit_code"]) for s in summary["steps"]] == [
        ("clean", 0),
        ("validate", 0),
        ("chunk", INTERRUPTED),
    ]


def test_run_stopped_by_an_error_keeps_the_record_and_raises(tmp_path: Path):
    snapshot = write_snapshot(tmp_path / "snap.json", ["cs.CL"])
    steps = plan_steps(tmp_path, snapshot=snapshot, model="m")
    fake = stop_at("validate", OSError("disk full"))
    with pytest.raises(OSError, match="disk full"):
        run_all(tmp_path, steps, snapshot=snapshot, run_step=fake, log=lambda _: None)
    summary = summary_of(tmp_path)
    assert summary["exit_code"] == 1
    assert [(s["name"], s["exit_code"]) for s in summary["steps"]] == [
        ("clean", 0),
        ("validate", 1),
    ]


def test_tee_step_child_writes_utf8(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setenv("PYTHONPATH", str(SRC))
    # A child whose pipe is not UTF-8, as on Windows (code page): ASCII locale, no UTF-8 mode
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONCOERCECLOCALE", "0")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    envs: list[dict] = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        envs.append(kwargs["env"])
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    assert tee_step(["no-such-step-\u00e9\u2713"], tmp_path / "bad.log") == 2
    assert envs[0]["PYTHONUTF8"] == "1"
    error = "invalid choice: 'no-such-step-\u00e9\u2713'"  # the child's own line, not the "$ " one
    assert error in (tmp_path / "bad.log").read_text(encoding="utf-8")
    assert error in capsys.readouterr().out


def test_tee_step_stops_the_child_when_interrupted(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PYTHONPATH", str(SRC))
    processes: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        processes.append(real_popen(*args, **kwargs))
        return processes[-1]

    def interrupt(line: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr("scitech_pipelines.run_all.show", interrupt)
    with pytest.raises(KeyboardInterrupt):
        tee_step(["run-all", "--help"], tmp_path / "help.log")
    assert processes[0].poll() is not None  # not left running


def test_show_replaces_what_stdout_cannot_encode(monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")  # no \r\n on Windows
    monkeypatch.setattr(sys, "stdout", out)
    show("caf\u00e9 \u2713\n")  # cp1252 has the accent but not the check mark
    out.flush()
    assert out.buffer.getvalue() == "caf\u00e9 ?\n".encode("cp1252")


def test_command_runs_a_part_of_the_chain(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    snapshot = write_snapshot(tmp_path / "snap.json", ["cs.CL"] * 3)
    argv = ["--data-dir", str(tmp_path), "run-all", "--snapshot", str(snapshot), "--limit", "2"]
    assert main([*argv, "--to", "sample"]) == 0  # no embed step: no model needed
    assert (tmp_path / "limit-2" / "raw" / "arxiv-first-2.jsonl").is_file()
    with pytest.raises(ValueError, match="no embedding model"):
        main(argv)  # checked before any step runs
    assert len(list((tmp_path / "logs").iterdir())) == 1  # only the first run
