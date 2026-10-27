"""Charts of the scaling measurements (W7-D2-FAO-1) from `pipelines/reports/scaling.csv`.

Writes two SVG line charts next to the CSV, with the corpus size in chunks on the x axis:
- `scaling-latency.svg`: p50 (solid) and p95 (dashed) query latency of dense, bm25 and hybrid;
- `scaling-build.svg`: load time into Qdrant and BM25 build time.
Sizes on disk stay a table in the report: the BM25 index and the raw vectors are almost equal
(177.2 and 178.6 MiB at 100%), so their lines would lie on top of each other.

Standard library only, so the charts can be regenerated anywhere after the numbers change:
    python pipelines/scripts/scaling_charts.py [--csv pipelines/reports/scaling.csv] [--out-dir ...]
"""

from __future__ import annotations

import argparse
import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"

# Okabe-Ito colours: distinguishable with colour-blindness, on a white background in both themes
BLUE, ORANGE, GREEN, GREY = "#0072B2", "#D55E00", "#009E73", "#555555"
WIDTH, HEIGHT = 640, 380
LEFT, RIGHT, TOP, BOTTOM = 70, 170, 50, 60  # plot margins; the legend sits in the right one


@dataclass(frozen=True)
class Series:
    name: str
    values: Sequence[float]
    color: str
    dashed: bool = False


def read_rows(path: Path) -> list[dict[str, float]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]
    if not rows:
        raise ValueError(f"{path} has no rows")
    return sorted(rows, key=lambda r: r["chunks"])


def nice_max(value: float) -> float:
    """The smallest 1, 2, 2.5 or 5 times a power of ten that is >= value."""
    if value <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * power:
            return step * power
    return 10 * power  # not reached


def fmt(value: float) -> str:
    return f"{value:,.0f}" if value >= 10 or value == int(value) else f"{value:g}"


def line_chart(
    title: str, x: Sequence[float], series: Sequence[Series], y_label: str, x_label: str
) -> str:
    """One SVG line chart; x and every series have one value per measured size."""
    if any(len(s.values) != len(x) for s in series):
        raise ValueError("every series needs one value per x")
    plot_w, plot_h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    x_max = max(x) * 1.04  # the axis ends just after the full corpus
    y_max = nice_max(max(v for s in series for v in s.values))

    def px(v: float) -> float:
        return LEFT + v / x_max * plot_w

    def py(v: float) -> float:
        return TOP + plot_h - v / y_max * plot_h

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="sans-serif" font-size="12" '
        f'role="img" aria-label="{escape(title)}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>',
        f'<text x="{LEFT}" y="24" font-size="15" font-weight="bold" fill="#000">'
        f"{escape(title)}</text>",
    ]
    for i in range(6):  # y grid and labels
        v = y_max * i / 5
        y = py(v)
        out.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + plot_w}" y2="{y:.1f}" stroke="#e0e0e0"/>'
        )
        out.append(
            f'<text x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end" fill="{GREY}">{fmt(v)}</text>'
        )
    for v in x:  # x ticks at the measured sizes
        out.append(
            f'<text x="{px(v):.1f}" y="{TOP + plot_h + 18}" text-anchor="middle" '
            f'fill="{GREY}">{fmt(v)}</text>'
        )
    out.append(
        f'<line x1="{LEFT}" y1="{TOP + plot_h}" x2="{LEFT + plot_w}" y2="{TOP + plot_h}" '
        f'stroke="{GREY}"/>'
    )
    out.append(
        f'<text x="{LEFT + plot_w / 2:.1f}" y="{HEIGHT - 16}" text-anchor="middle" '
        f'fill="#000">{escape(x_label)}</text>'
    )
    out.append(
        f'<text transform="translate(18 {TOP + plot_h / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" fill="#000">{escape(y_label)}</text>'
    )
    for n, s in enumerate(series):
        points = " ".join(f"{px(a):.1f},{py(b):.1f}" for a, b in zip(x, s.values, strict=True))
        dash = ' stroke-dasharray="6 4"' if s.dashed else ""
        out.append(
            f'<polyline points="{points}" fill="none" stroke="{s.color}" stroke-width="2"{dash}/>'
        )
        for a, b in zip(x, s.values, strict=True):
            out.append(f'<circle cx="{px(a):.1f}" cy="{py(b):.1f}" r="3.5" fill="{s.color}"/>')
        ly = TOP + 10 + n * 22  # legend
        lx = LEFT + plot_w + 16
        out.append(
            f'<line x1="{lx}" y1="{ly}" x2="{lx + 24}" y2="{ly}" stroke="{s.color}" '
            f'stroke-width="2"{dash}/>'
        )
        out.append(f'<text x="{lx + 30}" y="{ly + 4}" fill="#000">{escape(s.name)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def charts(rows: list[dict[str, float]]) -> dict[str, str]:
    """File name -> SVG text."""
    x = [r["chunks"] for r in rows]
    x_label = "Corpus size (chunks)"

    def col(name: str) -> list[float]:
        return [r[name] for r in rows]

    latency = []
    for name, color in (("dense", BLUE), ("bm25", ORANGE), ("hybrid", GREEN)):
        latency.append(Series(f"{name} p50", col(f"{name}_p50_ms"), color))
        latency.append(Series(f"{name} p95", col(f"{name}_p95_ms"), color, dashed=True))
    return {
        "scaling-latency.svg": line_chart(
            "Query latency by corpus size (k = 10)", x, latency, "Latency (ms)", x_label
        ),
        "scaling-build.svg": line_chart(
            "Build time by corpus size",
            x,
            [
                Series("Qdrant load", col("load_seconds"), BLUE),
                Series("BM25 build", col("bm25_build_seconds"), ORANGE),
            ],
            "Time (s)",
            x_label,
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=REPORTS / "scaling.csv")
    parser.add_argument("--out-dir", type=Path, default=None, help="default: next to the CSV")
    args = parser.parse_args(argv)
    out_dir = args.out_dir or args.csv.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, svg in charts(read_rows(args.csv)).items():
        (out_dir / name).write_text(svg, encoding="utf-8")
        print(f"wrote {out_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
