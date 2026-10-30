"""Run a command every N hours, on the hour (W7-D6-FAO-1, ADR 0011).

The `ingest` container runs `incremental-run` with this loop instead of a cron daemon: it needs
no extra package, the container's environment reaches the command as it is, and its timing rule
is tested here. Runs start at the hours divisible by `--every-hours` (UTC: 00:00, 02:00, ... for
2), so the times in the log are predictable. Each run's output goes to stdout (`docker compose
logs ingest`) and is appended to `--log` with a header line; a failed run is logged with its exit
code and the loop goes on. A run that is still going when the next one is due delays that one;
two runs never overlap (and `incremental-run` holds a lock as well).

    python -m scitech_pipelines.schedule --every-hours 2 --log data/logs/incremental.log -- \
        python -m scitech_pipelines incremental-run --until today ...
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVERY_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)


def next_run(now: datetime, every_hours: int) -> datetime:
    """The first hour strictly after `now` that is divisible by `every_hours` (UTC).

    `every_hours` must divide 24, so that the gap over midnight is the same as the others."""
    if every_hours not in EVERY_HOURS:
        raise ValueError(f"every_hours must divide 24 ({EVERY_HOURS}), got {every_hours}")
    hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    while True:
        hour += timedelta(hours=1)
        if hour.hour % every_hours == 0:
            return hour


def run_once(command: Sequence[str], log_path: Path, *, now: datetime | None = None) -> int:
    """Run `command`, copy its output to stdout and `log_path`, return its exit code."""
    started = now or datetime.now(timezone.utc)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"=== run started {started.isoformat(timespec='seconds')}\n")
        log.flush()
        process = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
            log.flush()
        code = process.wait()
        ended = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log.write(f"=== run ended {ended}, exit code {code}\n")
    return code


def loop(
    command: Sequence[str],
    log_path: Path,
    every_hours: int,
    *,
    run_now: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
    runs: int | None = None,
) -> None:
    """Run `command` at every due hour, forever (or `runs` times, for tests)."""
    done = 0
    if run_now:
        run_once(command, log_path)
        done += 1
    while runs is None or done < runs:
        due = next_run(clock(), every_hours)
        print(f"schedule: next run at {due.isoformat(timespec='minutes')}", flush=True)
        while (wait := (due - clock()).total_seconds()) > 0:
            sleep(min(wait, 60.0))
        run_once(command, log_path)
        done += 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--every-hours",
        type=int,
        default=2,
        help="1, 2, 3, 4, 6, 8, 12 or 24; default 2 (ADR 0011).",
    )
    parser.add_argument("--log", type=Path, default=Path("data/logs/incremental.log"))
    parser.add_argument("--run-now", action="store_true", help="Also run once at start-up.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="After --: the command.")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give the command after --")
    next_run(datetime.now(timezone.utc), args.every_hours)  # check the interval before waiting
    loop(command, args.log, args.every_hours, run_now=args.run_now)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
