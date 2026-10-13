# Calendar

Replanned on 2026-10-13 ([ADR 0010](../decisions/0010-compressed-schedule.md)).
Working days are Monday to Saturday. Sundays are buffer days (catch up, unattended long runs, no new tasks).
Day 1 = Tuesday 2026-10-13 (afternoon only). D22 = Friday 2026-11-06: internal deadline (`v1.0`, final report). D23-D24 = presentation preparation. D25 = Tuesday 2026-11-10: product presentation. 22 working days of project work plus 3 presentation days.

"Week N" now means phase N of the plan (2-3 working days). The name is kept so task IDs (`Wn-Dd-CODE-k`), milestones, tracking issues and journal files (`docs/journal/<CODE>/Wn.md`) stay stable. The `Dd` part of a task ID is historical: it no longer equals the day of the week. Use the Day ID below to find a task's date.

To change dates again, regenerate this table, the "Gate" lines of the week files and the due dates in `.github/workflows/bootstrap-project.yml`; task IDs never change.

| Date | Weekday | Day ID | Week (phase) | Milestone event | Plan file |
|---|---|---|---|---|---|
| 2026-10-13 | Tue | D01 | W1 | Plan starts (afternoon) | [week-01.md](week-01.md#d01) |
| 2026-10-14 | Wed | D02 | W1 | | [week-01.md](week-01.md#d02) |
| 2026-10-15 | Thu | D03 | W1 | Gate W1, contracts frozen | [week-01.md](week-01.md#d03) |
| 2026-10-16 | Fri | D04 | W2 | | [week-02.md](week-02.md#d04) |
| 2026-10-17 | Sat | D05 | W2 | | [week-02.md](week-02.md#d05) |
| 2026-10-18 | Sun | buffer | - | | - |
| 2026-10-19 | Mon | D06 | W2 | Gate W2 | [week-02.md](week-02.md#d06) |
| 2026-10-20 | Tue | D07 | W3 | | [week-03.md](week-03.md#d07) |
| 2026-10-21 | Wed | D08 | W3 | Full embedding run overnight | [week-03.md](week-03.md#d08) |
| 2026-10-22 | Thu | D09 | W3 | Gate W3 | [week-03.md](week-03.md#d09) |
| 2026-10-23 | Fri | D10 | W4 | | [week-04.md](week-04.md#d10) |
| 2026-10-24 | Sat | D11 | W4 | | [week-04.md](week-04.md#d11) |
| 2026-10-25 | Sun | buffer | - | | - |
| 2026-10-26 | Mon | D12 | W4 | Gate W4, tag `v0.4-mvp` | [week-04.md](week-04.md#d12) |
| 2026-10-27 | Tue | D13 | W5 | | [week-05.md](week-05.md#d13) |
| 2026-10-28 | Wed | D14 | W5 | Gate W5 | [week-05.md](week-05.md#d14) |
| 2026-10-29 | Thu | D15 | W6 | | [week-06.md](week-06.md#d15) |
| 2026-10-30 | Fri | D16 | W6 | Gate W6, feature freeze, tag `v0.6-rc` | [week-06.md](week-06.md#d16) |
| 2026-10-31 | Sat | D17 | W7 | | [week-07.md](week-07.md#d17) |
| 2026-11-01 | Sun | buffer | - | | - |
| 2026-11-02 | Mon | D18 | W7 | User study part 1 | [week-07.md](week-07.md#d18) |
| 2026-11-03 | Tue | D19 | W7 | User study part 2, Gate W7 | [week-07.md](week-07.md#d19) |
| 2026-11-04 | Wed | D20 | W8 | | [week-08.md](week-08.md#d20) |
| 2026-11-05 | Thu | D21 | W8 | | [week-08.md](week-08.md#d21) |
| 2026-11-06 | Fri | D22 | W8 | Final gate, tag `v1.0`, report final (internal deadline) | [week-08.md](week-08.md#d22) |
| 2026-11-07 | Sat | D23 | W8 | Slides final, rehearsal 1 | [week-08.md](week-08.md#d23) |
| 2026-11-08 | Sun | buffer | - | | - |
| 2026-11-09 | Mon | D24 | W8 | Dry run, last fixes | [week-08.md](week-08.md#d24) |
| 2026-11-10 | Tue | D25 | W8 | **Product presentation** | [week-08.md](week-08.md#d25) |

Dates not in this table with a Day ID (Sundays, before 2026-10-13, after 2026-11-10) have no scheduled tasks.
