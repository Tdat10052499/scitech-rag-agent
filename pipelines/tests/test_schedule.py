import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scitech_pipelines.schedule import loop, main, next_run, run_once


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 11, 4, hour, minute, second, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("now", "every", "due"),
    [
        (at(7, 59, 59), 2, at(8)),
        (at(8), 2, at(10)),  # strictly after: a run that just started does not repeat
        (at(9, 30), 2, at(10)),
        (at(23, 10), 2, at(0) + timedelta(days=1)),
        (at(8, 1), 1, at(9)),
        (at(5), 3, at(6)),
    ],
)
def test_next_run_is_the_next_hour_divisible_by_the_interval(now, every, due):
    assert next_run(now, every) == due


def test_interval_out_of_range_is_refused():
    with pytest.raises(ValueError):
        next_run(at(8), 0)
    with pytest.raises(ValueError):
        next_run(at(8), 25)


def test_run_once_copies_the_output_and_the_exit_code_to_the_log(tmp_path: Path, capsys):
    log = tmp_path / "logs" / "incremental.log"
    command = [sys.executable, "-c", "print('incremental: nothing changed'); raise SystemExit(3)"]
    assert run_once(command, log, now=at(8)) == 3
    text = log.read_text(encoding="utf-8")
    assert text.startswith("=== run started 2026-11-04T08:00:00+00:00\n")
    assert "incremental: nothing changed\n" in text and "exit code 3" in text
    assert "nothing changed" in capsys.readouterr().out


def test_loop_waits_for_each_due_hour_and_keeps_going_after_a_failure(tmp_path: Path):
    clock = [at(7, 59)]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    log = tmp_path / "incremental.log"
    fail = [sys.executable, "-c", "raise SystemExit(1)"]
    loop(fail, log, 2, clock=lambda: clock[0], sleep=sleep, runs=2)
    assert sum(slept) == 60 + 2 * 3600  # 08:00, then 10:00
    assert log.read_text(encoding="utf-8").count("exit code 1") == 2


def test_main_needs_a_command():
    with pytest.raises(SystemExit):
        main(["--every-hours", "2"])
