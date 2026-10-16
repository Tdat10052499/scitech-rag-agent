import os
import subprocess
import sys
from pathlib import Path

import pytest

import scitech_pipelines
from scitech_pipelines.cli import STEPS, main


def test_module_help_lists_every_step() -> None:
    src_dir = str(Path(scitech_pipelines.__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": src_dir}
    result = subprocess.run(
        [sys.executable, "-m", "scitech_pipelines", "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    for step in STEPS:
        assert step in result.stdout


@pytest.mark.parametrize("step", [s for s in STEPS if s not in ("download", "clean")])
def test_step_stub_runs(step: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([step]) == 0
    assert "not implemented" in capsys.readouterr().out


def test_missing_command_fails() -> None:
    with pytest.raises(SystemExit):
        main([])
