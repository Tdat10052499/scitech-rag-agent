# 0010. Compressed schedule: 2026-10-13 to 2026-11-06

- Status: accepted (kickoff, W1-D1-DAT-3, 2026-10-13)
- Date: 2026-10-13
- Deciders: DAT (maintainer), FAO, LDN (confirmations in issue #10)

## Context
The plan in `docs/plan/` was written for 2026-10-05 to 2026-11-27: 8 weeks of 5 working days (40 days, 126 tasks, about 1.05 tasks per member-day).
Work actually starts on Tuesday 2026-10-13 (afternoon), and the team set the submission date to Friday 2026-11-06.
With Monday to Saturday as working days and Sunday as buffer, that leaves 22 working days (55% of the original 40) and 3 buffer days.
The instructor does not answer design questions; the team decides, and the final product is presented on Tuesday 2026-11-10 (see the amendment below).

## Options considered
1. Shift the whole plan by 6 working days (end 2026-12-04). Rejected: misses the 2026-11-06 deadline.
2. Keep the full scope and compress it into 22 days. Rejected: 126 tasks over 66 member-days is about 1.9 tasks per member-day, about 1.8 times the original load, with no slack on the critical path.
3. Compress into 22 days, keep the critical path and evaluation/report intact, and apply the cut list early. Chosen.

## Decision
- The 8 weeks become 8 phases of 2-3 working days; the name "Week N" and all task IDs are kept (see `docs/plan/calendar.md`).
- Cut-list items applied now: 1 (Kafka), 2 (reranker), 3 (UI extras: data page, `GET /stats`, step/status display, debug view), 4 (query decomposition), 5 (user study at the minimum size, 5-6 participants).
- Cut-list item 6 (incremental ingestion) is a decision point at the Week 5 gate (D14): kept if the live test passes, otherwise cut and described in the report.
- Additional cuts outside the original cut list (to be approved by the team): follow-up suggestions v2 (W6-D1-DAT-1; v1 is the evaluated version) and response caching (part of W6-D2-DAT-1; the latency measurement is kept and moved to D18).
- Not cut: golden set target (60 items), retrieval comparison, agent ablations, faithfulness with manual check, efficiency/scaling measurements, user study, final report, clean-clone check.
- Result: 113 scheduled tasks, 10 cut, 3 merged into other tasks, 2 moved to another phase (counted as scheduled).

## Consequences
- Load: 113 tasks over 66 member-days is about 1.7 tasks per member-day (DAT 1.95, LDN 1.64, FAO 1.55), still about 1.6 times the original. DAT carries the most, on top of project management; reviews and gate checks must be short.
- Gates happen every 2-3 days; a one-day slip on a [blocking] task consumes most of a phase. Sunday buffers (2026-10-18, 2026-10-25, 2026-11-01) are the only slack.
- Highest schedule risk: the Week 3 chain chunk -> embedding -> load -> evaluation (D07-D09); the corpus subset in ADR 0003 must be sized so the full embedding fits in one night.
- Research questions: RQ2 (do agent steps improve faithfulness) is tested with rewriting and evidence check only, without decomposition. RQ3 (follow-up usefulness) rests on n = 5-6 participants, so only descriptive statistics can be reported, and no claim of a general effect.
- Without the reranker and decomposition, retrieval and agent results describe a simpler system than the original brief; the report must say so.
- If the presentation date or the scope changes, this ADR must be revisited and `docs/plan/` regenerated.

## Amendment (2026-10-13, W1-D1-DAT-2)
- The product presentation is on Tuesday 2026-11-10. 2026-11-06 (D22) stays the internal deadline for `v1.0` and the final report, so the 22-day plan above is unchanged.
- Three presentation days are added: D23 (Sat 2026-11-07, slides final and rehearsal), D24 (Mon 2026-11-09, dry run: W8-D4-DAT-1 moves here) and D25 (Tue 2026-11-10, presentation; final journals). Sunday 2026-11-08 is a buffer day.
- W8-D5-DAT-1 now releases `v1.0` on D22 and takes over the final report review; there is no separate submission step, because the instructor only asks for the product at the presentation.
- Kafka stays cut and the LLM does not have to run locally; both decisions are recorded in `docs/00-project-brief.md`.
