# 0013. Cancel the user study (RQ3 is not evaluated)

- Status: accepted (2026-11-03; recorded by FAO the day the team was notified that the user study is not needed; DAT and LDN review this record in its PR)
- Date: 2026-11-03
- Deciders: FAO (recorded), DAT, LDN

## Context
The user study (U1) was planned for the night of 2026-11-03, 22:30 to about 01:30, with 4 confirmed participants (`evaluation/RUNS.md` §5, `evaluation/user_study/PROTOCOL.md`). It was the only evidence for RQ3, the usefulness of the follow-up suggestions (`evaluation/PLAN.md` §2). ADR 0010 had already reduced it to 5-6 participants and descriptive statistics.

On 2026-11-03, before the first session, the team was notified that the user study is not needed for the project.

## Options considered
1. Run the four sessions anyway (n = 4, below the planned 5).
2. Cancel the study now and drop RQ3 from the evaluation.

## Decision
**Option 2: the user study is cancelled, completely and for good.** No session is held, on 2026-11-03 or later. Nobody needs to prepare, host, observe or analyse it.

## Consequences
- **Tasks cancelled:** W7-D3-DAT-1, W7-D3-LDN-1, W7-D4-LDN-1 and run U1. They are marked cancelled in `docs/plan/week-07.md` and `evaluation/RUNS.md`.
- **Participants:** LDN tells the four confirmed participants that the sessions are cancelled. Their contact details stay outside the repository and are deleted, as `PROTOCOL.md` §2 says.
- **Gate W7 (#156):** the item "user study completed (n >= 5)" is removed. The gate is: every run in `RUNS.md` has a stored run file (U1 is cancelled, not missing), and `final.md` is merged.
- **Dependencies:** W7-D5-DAT-1, W7-D5-FAO-1 and W7-D5-LDN-1 no longer wait for W7-D4-LDN-1.
- **RQ3:** not evaluated in v1.0. Follow-up suggestions stay in the product (frozen `v0.6-rc`) and are described in chapters 3 and 5, but there is no measurement of their usefulness. `final.md` and report chapters 1, 4 and 6 say that RQ3 was dropped and why, and list a user study as future work. Chapter owners update their own text: chapter 1 (DAT, W8-D1-DAT-1), chapter 4 and `final.md` (LDN, W8-D1-LDN-1 and W7-D5-LDN-1), chapter 6 (FAO, W8-D2-FAO-1).
- **No study data exists.** `evaluation/user_study/responses/` stays empty. The trace and feedback test lines from the two host rehearsals on 2026-11-03 were deleted the same day. W8-D5-LDN-1 has no raw study data to archive.
- **Product:** the rating buttons and `POST /feedback` stay as they are (no code change in the freeze). They are no longer used for evaluation.
- **Figures:** W8-D2-LDN-1 has no user-rating chart.
- **`PROTOCOL.md`** is kept as a record of what was planned, marked cancelled.
