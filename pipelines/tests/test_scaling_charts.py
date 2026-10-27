"""Tests for `pipelines/scripts/scaling_charts.py` (W7-D2-FAO-1)."""

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scaling_charts.py"
spec = importlib.util.spec_from_file_location("scaling_charts", SCRIPT)
scaling_charts = importlib.util.module_from_spec(spec)
sys.modules["scaling_charts"] = scaling_charts  # dataclasses look their module up
spec.loader.exec_module(scaling_charts)

REPORT_CSV = Path(__file__).resolve().parents[1] / "reports" / "scaling.csv"
SVG = "{http://www.w3.org/2000/svg}"


def test_nice_max_rounds_up_to_a_round_axis_end():
    assert [scaling_charts.nice_max(v) for v in (0, 0.7, 1, 3, 17.2, 136, 121926)] == [
        1.0,
        1.0,
        1,
        5,
        20,
        200,
        200000,
    ]


def test_the_report_charts_are_valid_svg_with_one_line_per_series(tmp_path: Path):
    assert scaling_charts.main(["--csv", str(REPORT_CSV), "--out-dir", str(tmp_path)]) == 0
    lines = {"scaling-latency.svg": 6, "scaling-build.svg": 2}
    for name, count in lines.items():
        root = ET.parse(tmp_path / name).getroot()
        polylines = root.findall(f"{SVG}polyline")
        assert len(polylines) == count
        assert all(len(p.get("points").split()) == 3 for p in polylines)  # three sizes


def test_points_sit_where_their_values_are():
    rows = [
        {"chunks": 100.0, "load_seconds": 2.5, "bm25_build_seconds": 2.0},
        {"chunks": 200.0, "load_seconds": 5.0, "bm25_build_seconds": 2.0},
    ]
    s = scaling_charts.Series
    svg = scaling_charts.line_chart(
        "t",
        [r["chunks"] for r in rows],
        [s("a", [r["load_seconds"] for r in rows], "#000")],
        "y",
        "x",
    )
    # coordinates are written with one decimal
    points = ET.fromstring(svg).find(f"{SVG}polyline").get("points").split()
    (x1, y1), (x2, y2) = (tuple(map(float, p.split(","))) for p in points)
    plot_w = scaling_charts.WIDTH - scaling_charts.LEFT - scaling_charts.RIGHT
    plot_h = scaling_charts.HEIGHT - scaling_charts.TOP - scaling_charts.BOTTOM
    assert x2 == pytest.approx(scaling_charts.LEFT + plot_w / 1.04, abs=0.05)  # axis ends at 208
    assert x1 == pytest.approx(scaling_charts.LEFT + plot_w / 2 / 1.04, abs=0.05)
    assert y2 == pytest.approx(scaling_charts.TOP, abs=0.05)  # 5 is the axis end
    assert y1 == pytest.approx(scaling_charts.TOP + plot_h / 2, abs=0.05)


def test_a_series_of_the_wrong_length_is_refused():
    with pytest.raises(ValueError, match="one value per x"):
        scaling_charts.line_chart("t", [1, 2], [scaling_charts.Series("a", [1], "#000")], "y", "x")
