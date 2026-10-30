# Report outline

Task: W7-D5-DAT-1, outline part. The gate part of the task (check every run in
`evaluation/RUNS.md`, review `final.md`) waits for those files.

Status: **draft for review by FAO and LDN.** The chapter files, owners and tasks come from
`docs/plan/week-07.md` and `docs/plan/week-08.md`. The page budget and the dates in section 3 are
proposals.

## 1. Format

- One Markdown file per chapter in `docs/report/`, exported to one PDF (W8-D4-LDN-1).
- Figures and the scripts that made them go in `docs/report/figures/` (W8-D2-LDN-1).
- Writing style:
  - English;
  - terms as in `docs/02-glossary.md`;
  - every number names the run file, report or ADR it comes from;
  - "TODO(<task id>)" marks a gap and the task that fills it.
- Page budget: about 22 pages, A4, without the appendix. It is a target, not a limit set by the
  course; the course states none (`docs/00-project-brief.md`).

## 2. Chapters

| File | Chapter | Owner | Task | Pages | Main sources | State on 2026-10-30 |
|---|---|---|---|---|---|---|
| `01-introduction.md` | 1. Introduction: problem, goals, scope, research questions, how the project was run | DAT | W8-D1-DAT-1 | 2 | `docs/00-project-brief.md`, `evaluation/PLAN.md` §1, ADR 0010 | Draft in this PR |
| `02-data.md` | 2. Data: sources, volume, pipeline, processing engine, incremental ingestion, scaling, frozen snapshot | FAO | W7-D4-FAO-1, W8-D1-FAO-1 | 5 | ADR 0003, 0005, 0007, 0008, 0011; `pipelines/reports/`; `evaluation/reports/scaling.md` | Draft PR #122 |
| `03-system.md` | 3. System: architecture, request flow, retrieval, agent, LLM serving, API, deployment, design decisions | DAT | W8-D1-DAT-1 | 5 | `docs/01-architecture.md`, `docs/contracts/`, ADR 0001, 0006, 0009, 0010; `agent/` | Draft in this PR |
| `04-evaluation.md` | 4. Evaluation: golden set, RQ1 retrieval, RQ2 agent ablations and faithfulness, RQ3 user study, latency, error analysis, threats to validity | LDN (error analysis: DAT, W7-D4-DAT-1) | W8-D1-LDN-1 | 6 | `evaluation/reports/final.md` (W7-D5-LDN-1), `retrieval-v1.md`, `ablations-v1.md`, `docs/runbooks/performance.md` | Not started; `final.md` does not exist yet |
| `05-interface.md` | 5. Interface: chat, citations, sources panel, follow-ups, refusal state, feedback | LDN | W8-D1-LDN-1 | 2 | `frontend/`, `docs/demo/`, ADR 0004 | Not started |
| `06-conclusion.md` | 6. Conclusion: results by research question, limitations, future work | FAO | W8-D2-FAO-1 | 2 | chapters 2–5 | Draft PR #131 |
| `demo-script.md` | Demo script (not a chapter) | DAT | W8-D3-DAT-1 | — | — | Not started |
| Appendix | A. How to run (link to README); B. ADR index; C. Golden-set format; D. Team and AI-tool use | DAT | W8-D5-DAT-1 | — | `README.md`, `docs/decisions/` | Not started |

### What each chapter must contain

The other chapters rely on these points, so they are fixed here.

- **Chapter 1** states the three research questions exactly as in `evaluation/PLAN.md`. Chapters 4
  and 6 answer them in the same order.
- **Chapter 3** describes the frozen configuration of `evaluation/SNAPSHOT.md`. Anything changed
  after the freeze (scheduled ingestion, ADR 0011) is described as an addition, not as the
  evaluated system.
- **Chapter 4** reports, for every result:
  - n;
  - the split;
  - the run file;
  - the interval where one exists.

  It also keeps "supported by the cited passages" apart from "true". The error analysis section
  (DAT) uses the 20 answers of W7-D4-DAT-1, plus the qualitative examples from the 2026-10-30 UI
  test, which are marked as a single session, not as a measurement.
- **Chapter 6** lists every feature cut in ADR 0010 and the reason for the cut.

## 3. Schedule

The dates come from `docs/plan/` and ADR 0010. The presentation is on Tuesday 2026-11-10.

| Day | Report work | Owner |
|---|---|---|
| Fri 10-30 (D16) | Outline, chapters 1 and 3 drafts (this PR, written early) | DAT |
| Sat 10-31 to Tue 11-03 (D17–D19) | Final runs. `final.md` draft with the error analysis. Chapter 2 with final numbers (#122) | LDN, DAT, FAO |
| Tue 11-03 (D19) | Gate W7: every run in `RUNS.md` has results; `final.md` reviewed (gate part of W7-D5-DAT-1) | DAT |
| Wed 11-04 (D20) | Chapters 1, 3 and 4–6 completed; chapter 2 final edit | all |
| Thu 11-05 (D21) | Figures and tables, merged report, PDF export, demo script | LDN, DAT |
| Fri 11-06 (D22) | Final review pass; `v1.0` release with the PDF | DAT |
| Sat 11-07 to Mon 11-09 (D23–D24) | Slides, rehearsal, dry run | all |
| Tue 11-10 (D25) | Presentation | all |

One decision is still open for chapter 4: the ablations ran on `split: dev` (32 items;
`ablations-v1.md`), while the draft `RUNS.md` (#160) plans `split: all`. The team decides in #160
whether to rerun them on all items (about 15 minutes on DAT's laptop) or report them on dev.
