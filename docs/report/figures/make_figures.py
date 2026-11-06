"""Figures of chapters 3 and 4 (W8-D2-LDN-1).

Run from anywhere:  python docs/report/figures/make_figures.py
Writes SVG files next to this script (text, so they diff and commit cleanly). Needs matplotlib only.

Every number is copied from `evaluation/reports/final.md` (sections named in the comments), which
takes them from the run files in `evaluation/runs/`, `docs/runbooks/performance.md` and
`pipelines/reports/scaling.md`. Nothing here is computed from user ratings: the user study was
cancelled (ADR 0013). If a number changes in `final.md`, change it here and run the script again.

Colours: slots 1 to 3 of the validated categorical palette (blue, orange, aqua), light surface.
Values are written on the bars, so identity never depends on colour alone.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2de"
GREY = "#8a8985"

plt.rcParams.update({
    "svg.hashsalt": "report",
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "text.color": INK, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "svg.fonttype": "none", "figure.facecolor": "white",
    "axes.facecolor": "white",
    "legend.frameon": False,
})


def save(fig, name):
    fig.savefig(
        OUT / name, format="svg", facecolor="white", bbox_inches="tight", metadata={"Date": None}
    )
    plt.close(fig)
    print("wrote", name)


def grouped(ax, groups, series, colors, width=0.26, label_fmt="{:.2f}", ci=None, fontsize=7.5):
    """Grouped vertical bars. series: {name: [values per group]}; ci: {name: [(lo, hi), ...]}."""
    n = len(series)
    for i, (name, vals) in enumerate(series.items()):
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        ax.bar(xs, vals, width * 0.92, color=colors[i], label=name, zorder=3)
        for j, (x, v) in enumerate(zip(xs, vals, strict=False)):
            top = v
            if ci and name in ci:
                lo, hi = ci[name][j]
                ax.errorbar(x, v, yerr=[[v - lo], [hi - v]], color=INK, lw=0.8, capsize=2, zorder=4)
                top = hi
            ax.text(
                x,
                top + 0.012,
                label_fmt.format(v),
                ha="center",
                va="bottom",
                fontsize=fontsize,
                color=INK,
            )
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups)


# ---- Figure 1: retrieval comparison (final.md section 3, R1 to R3, n = 60, 95% bootstrap CI) ----
def fig_retrieval():
    groups = ["recall@1", "recall@5", "recall@10", "MRR"]
    s = {
        "Hybrid (product default)": [0.358, 0.508, 0.583, 0.474],
        "Dense only": [0.300, 0.458, 0.492, 0.420],
        "BM25 only": [0.358, 0.508, 0.567, 0.486],
    }
    ci = {
        "Hybrid (product default)": [
            (0.250, 0.475), (0.383, 0.625), (0.458, 0.700), (0.363, 0.590)
        ],
        "Dense only": [(0.183, 0.417), (0.350, 0.575), (0.383, 0.600), (0.309, 0.529)],
        "BM25 only": [(0.250, 0.467), (0.392, 0.633), (0.450, 0.692), (0.375, 0.601)],
    }
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    grouped(ax, groups, s, [BLUE, ORANGE, AQUA], ci=ci)
    ax.set_ylim(0, 0.85)
    ax.set_ylabel("Score (0 to 1)")
    ax.set_title("Retrieval on 60 answerable questions (R1 to R3)", loc="left", fontsize=10)
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    fig.text(
        0.01,
        -0.03,
        "Bars: mean. Whiskers: 95% bootstrap interval over questions (1,000 resamples). "
        "Source: final.md section 3.",
        fontsize=7,
        color=MUTED,
    )
    save(fig, "fig-4-1-retrieval.svg")


# ---- Figure 2: recall@5 by question type (final.md section 3) ----
def fig_by_type():
    types = [("factual", 13), ("explanatory", 17), ("comparison", 8), ("multi-hop", 11),
             ("follow-up", 11)]
    groups = [f"{t}\n(n = {n})" for t, n in types]
    s = {
        "Hybrid": [0.85, 0.65, 0.50, 0.32, 0.09],
        "Dense only": [0.69, 0.71, 0.31, 0.27, 0.09],
        "BM25 only": [0.92, 0.53, 0.50, 0.32, 0.18],
    }
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    grouped(ax, groups, s, [BLUE, ORANGE, AQUA], width=0.27)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("recall@5")
    ax.set_title("Retrieval by question type", loc="left", fontsize=10)
    ax.legend(loc="upper right", ncol=3, fontsize=8)
    fig.text(
        0.01,
        -0.11,
        "Follow-up questions were searched without their history; the product rewrites "
        "them first (A2). Cells hold 8 to 17 questions. Source: final.md section 3.",
        fontsize=7,
        color=MUTED,
    )
    save(fig, "fig-4-2-retrieval-by-type.svg")


# ---- Figure 3: development against test items (final.md section 3) ----
def fig_dev_test():
    groups = ["Development items\n(1 to 30)", "Test items\n(31 to 60)"]
    s = {
        "Hybrid": [0.333, 0.683],
        "Dense only": [0.283, 0.633],
        "BM25 only": [0.350, 0.667],
    }
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    grouped(ax, groups, s, [BLUE, ORANGE, AQUA], width=0.26, label_fmt="{:.2f}")
    ax.set_ylim(0, 0.85)
    ax.set_ylabel("recall@5")
    ax.set_title("The two halves of the golden set differ", loc="left", fontsize=10)
    ax.legend(loc="upper left", fontsize=8)
    fig.text(
        0.01, -0.12, "30 questions per half. Source: final.md section 3.", fontsize=7, color=MUTED
    )
    save(fig, "fig-4-3-dev-test.svg")


# ---- Figure 4: ablations (final.md section 4.1; A1 to A4 run on 65 items) ----
def fig_ablation():
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 3.2), gridspec_kw={"width_ratios": [1.0, 1.0]})
    names = ["A1\nMVP", "A2\n+ rewrite", "A3\n+ check", "A4\nfull"]
    # left: macro faithfulness with CI; A3 and A4 have no judged answers
    vals, lo, hi = [0.491, 0.527], [0.39, 0.43], [0.59, 0.62]
    for i, c in enumerate([BLUE, ORANGE]):
        a.bar(i, vals[i], 0.55, color=c, zorder=3)
        a.errorbar(
            i,
            vals[i],
            yerr=[[vals[i] - lo[i]], [hi[i] - vals[i]]],
            color=INK,
            lw=0.8,
            capsize=2,
            zorder=4,
        )
        a.text(i, hi[i] + 0.015, f"{vals[i]:.3f}", ha="center", fontsize=8)
    for i in (2, 3):
        a.text(i, 0.04, "not\nscorable", ha="center", va="bottom", fontsize=7.5, color=MUTED)
    a.set_xticks(range(4))
    a.set_xticklabels(names)
    a.set_ylim(0, 0.8)
    a.set_ylabel("Faithfulness (macro)")
    a.set_title("Faithfulness, judge qwen2.5:7b", loc="left", fontsize=9)
    # right: answerable questions refused out of 60
    ref = [6, 5, 60, 60]
    b.bar(range(4), ref, 0.55, color=[BLUE, ORANGE, GREY, GREY], zorder=3)
    for i, v in enumerate(ref):
        b.text(i, v + 1.5, f"{v}/60", ha="center", fontsize=8)
    b.set_xticks(range(4))
    b.set_xticklabels(names)
    b.set_ylim(0, 72)
    b.set_ylabel("Answerable questions refused")
    b.set_title("Refusals (of 60 answerable)", loc="left", fontsize=9)
    fig.text(
        0.01,
        -0.04,
        "One run per condition. Whiskers: 95% bootstrap interval, 53 to 55 judged answers. "
        "The evidence check refused every question. Source: final.md section 4.1.",
        fontsize=7,
        color=MUTED,
    )
    fig.tight_layout()
    save(fig, "fig-4-4-ablation.svg")


# ---- Figure 5: judge against human labels (final.md section 5) ----
def fig_judge():
    groups = [
        "Faithfulness\nA1 (29 sent.)", "Faithfulness\nA2 (26 sent.)", "Faithfulness\nboth (55)",
        "Relevance\nA1 (11 ans.)", "Relevance\nA2 (11 ans.)", "Relevance\nboth (22)"
    ]
    s = {
        "Raw agreement": [0.862, 0.846, 0.855, 0.455, 0.909, 0.682],
        "Cohen's kappa": [0.733, 0.720, 0.734, 0.057, 0.810, 0.389],
    }
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    grouped(ax, groups, s, [BLUE, ORANGE], width=0.3, fontsize=7.5)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Judge against human labels")
    ax.set_title("Agreement of the judge with LDN's and FAO's labels", loc="left", fontsize=10)
    ax.legend(loc="upper right", ncol=2, fontsize=8)
    ax.tick_params(axis="x", labelsize=7.5)
    fig.text(
        0.01,
        -0.05,
        "20% sample, seed 20261031; each answer labelled by one person. Too few ratings "
        "to trust the relevance bars. Source: final.md section 5.",
        fontsize=7,
        color=MUTED,
    )
    save(fig, "fig-4-5-judge-agreement.svg")


# ---- Figure 6: latency and scaling (final.md section 6) ----
def fig_latency():
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 3.2), gridspec_kw={"width_ratios": [1.1, 1.0]})
    # left: L1, 30 questions, p50 and p95 per stage (ms -> s)
    stages = ["First token", "Answer\ncomplete", "Total"]
    p50, p95 = [0.422, 1.328, 4.304], [2.632, 3.196, 6.025]
    xs = range(3)
    a.bar([x - 0.19 for x in xs], p50, 0.34, color=BLUE, label="p50", zorder=3)
    a.bar([x + 0.19 for x in xs], p95, 0.34, color=ORANGE, label="p95", zorder=3)
    for x, v in zip(xs, p50, strict=False):
        a.text(x - 0.19, v + 0.12, f"{v:.1f}", ha="center", fontsize=7.5)
    for x, v in zip(xs, p95, strict=False):
        a.text(x + 0.19, v + 0.12, f"{v:.1f}", ha="center", fontsize=7.5)
    a.set_xticks(list(xs))
    a.set_xticklabels(stages)
    a.set_ylim(0, 7.2)
    a.set_ylabel("Seconds")
    a.set_title("Time per question (L1, n = 30)", loc="left", fontsize=9)
    a.legend(loc="upper left", fontsize=8)
    # right: S1, hybrid retrieval latency against index size
    chunks = [12162, 61067, 121926]
    q50, q95 = [89.6, 97.7, 120.4], [131.0, 135.2, 134.6]
    b.plot(chunks, q50, "o-", color=BLUE, lw=2, ms=6, label="p50", zorder=3)
    b.plot(chunks, q95, "o-", color=ORANGE, lw=2, ms=6, label="p95", zorder=3)
    for x, v in zip(chunks, q50, strict=False):
        b.annotate(
            f"{v:.0f}",
            (x, v),
            textcoords="offset points",
            xytext=(0, -13),
            ha="center",
            fontsize=7.5,
        )
    for x, v in zip(chunks, q95, strict=False):
        b.annotate(
            f"{v:.0f}", (x, v), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7.5
        )
    b.set_xticks(chunks)
    b.set_xticklabels(["12k\n(10%)", "61k\n(50%)", "122k\n(100%)"])
    b.set_ylim(0, 170)
    b.set_xlim(0, 135000)
    b.set_ylabel("Milliseconds")
    b.set_xlabel("Chunks in the index")
    b.set_title("Hybrid retrieval vs index size (S1)", loc="left", fontsize=9)
    b.legend(loc="lower right", fontsize=8)
    fig.text(
        0.01,
        -0.04,
        "L1: DAT's laptop, one run. S1: FAO's laptop, 100 queries, k = 10, one repetition; the "
        "two hosts are not comparable. Sources: final.md section 6.",
        fontsize=7,
        color=MUTED,
    )
    fig.tight_layout()
    save(fig, "fig-4-6-latency-scaling.svg")


# ---- Figure 7: architecture (chapter 3, section 3.1 and 3.2; docs/01-architecture.md) ----
def box(ax, x, y, w, h, title, sub, fc="#f3f6fb", ec=BLUE):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1.2
        )
    )
    ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=9, weight="bold")
    ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=7, color=MUTED)


def arrow(ax, x0, y0, x1, y1, text=None, dy=0.1, dx=0.0, ha="center"):
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.0)
    )
    if text:
        ax.text(
            (x0 + x1) / 2 + dx,
            (y0 + y1) / 2 + dy,
            text,
            ha=ha,
            va="bottom",
            fontsize=7,
            color=MUTED,
        )


def fig_architecture():
    fig, ax = plt.subplots(figsize=(7.6, 4.3))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.grid(False)
    # online path
    box(ax, 0.1, 4.0, 2.0, 1.2, "Interface", "frontend/ (React)")
    box(ax, 3.5, 4.0, 2.0, 1.2, "API", "backend/ (FastAPI)")
    box(ax, 6.9, 4.0, 1.9, 1.2, "Agent", "agent/ (fixed steps)")
    box(ax, 9.4, 4.0, 1.5, 1.2, "LLM", "OpenAI API", fc="#eef8f4", ec=AQUA)
    box(ax, 6.9, 1.9, 1.9, 1.2, "Retrieval", "hybrid (RRF)", fc="#fdf3ee", ec=ORANGE)
    box(ax, 9.4, 1.9, 1.5, 1.2, "Index", "Qdrant, BM25", fc="#fdf3ee", ec=ORANGE)
    arrow(ax, 2.1, 4.85, 3.5, 4.85, "POST /chat", dy=0.06)
    arrow(ax, 3.5, 4.35, 2.1, 4.35, "SSE events", dy=-0.36)
    arrow(ax, 5.5, 4.6, 6.9, 4.6)
    arrow(ax, 8.8, 4.6, 9.4, 4.6)
    arrow(ax, 7.85, 4.0, 7.85, 3.1, "search", dy=0.0, dx=0.1, ha="left")
    arrow(ax, 8.8, 2.5, 9.4, 2.5)
    # offline path
    box(ax, 0.1, 0.3, 2.4, 1.2, "Data pipeline", "pipelines/ (chapter 2)", fc="#f4f3f1", ec=GREY)
    box(ax, 3.5, 0.3, 2.4, 1.2, "Chunks + vectors", "chunk.schema.json", fc="#f4f3f1", ec=GREY)
    box(ax, 0.1, 2.3, 2.4, 1.0, "Evaluation", "golden set, runners", fc="#f4f3f1", ec=GREY)
    arrow(ax, 2.5, 0.9, 3.5, 0.9)
    ax.plot([5.9, 10.15], [0.9, 0.9], color=INK, lw=1.0)
    arrow(ax, 10.15, 0.9, 10.15, 1.9)
    ax.text(0.1, 5.65, "Online path (one question)", fontsize=8.5, weight="bold")
    ax.text(0.1, 1.78, "Offline path", fontsize=8.5, weight="bold", color=MUTED)
    ax.text(3.5, 3.4, "Events: sources, token, followups, done", fontsize=7, color=MUTED)
    ax.text(
        0.1,
        -0.2,
        "Layers and contracts: chapter 3, section 3.1. The LLM is outside the system and is "
        "reached through an OpenAI-compatible interface (ADR 0001).",
        fontsize=7,
        color=MUTED,
    )
    save(fig, "fig-3-1-architecture.svg")


if __name__ == "__main__":
    fig_retrieval()
    fig_by_type()
    fig_dev_test()
    fig_ablation()
    fig_judge()
    fig_latency()
    fig_architecture()
