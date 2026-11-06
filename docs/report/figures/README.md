# Report figures

`make_figures.py` draws every figure of the report. Run `python docs/report/figures/make_figures.py`
(needs matplotlib). The SVG files are written next to the script and are not committed in this
version: run the script before the PDF export (W8-D4-LDN-1) or before reading the chapters in a
viewer.

The numbers are typed into the script from `evaluation/reports/final.md`, with the section named
next to each figure; change them there and run the script again. No figure uses user ratings: the
user study was cancelled (ADR 0013).

| File | Chapter | Shows | Source |
|---|---|---|---|
| `fig-3-1-architecture.svg` | 3 (3.1) | Layers and the online and offline paths | `docs/report/03-system.md` 3.1 and 3.2 |
| `fig-4-1-retrieval.svg` | 4 (4.3) | Recall@1/5/10 and MRR of hybrid, dense, BM25 with 95% intervals | `final.md` §3 (R1 to R3) |
| `fig-4-2-retrieval-by-type.svg` | 4 (4.3) | Recall@5 by question type | `final.md` §3 |
| `fig-4-3-dev-test.svg` | 4 (4.3) | Recall@5 on development and test items | `final.md` §3 |
| `fig-4-4-ablation.svg` | 4 (4.4) | Faithfulness and refusals of A1 to A4 | `final.md` §4.1 |
| `fig-4-5-judge-agreement.svg` | 4 (4.5) | Agreement of the judge with human labels | `final.md` §5 |
| `fig-4-6-latency-scaling.svg` | 4 (4.7) | Time per question (L1) and index scaling (S1) | `final.md` §6 |

Colours are slots 1 to 3 of the validated categorical palette on a light surface; every bar carries
its value, so identity does not depend on colour alone. The files are SVG with the text kept as
text, for the PDF export (W8-D4-LDN-1).
