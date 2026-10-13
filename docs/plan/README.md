# Daily plan: how to use it

This folder is the single source of truth for **who does what, on which day**, from 2026-10-13 to the presentation on 2026-11-10 (replanned on 2026-10-13, see [ADR 0010](../decisions/0010-compressed-schedule.md)).
It is written so that an AI coding agent can answer "What do I need to do today?" without extra context.

| File | Content |
|---|---|
| [00-overview.md](00-overview.md) | Roles, phases, gates, final deliverables, cut list (as applied) |
| [calendar.md](calendar.md) | Date to Day ID (D01-D25), phase ("Week N") and week file anchor |
| `week-01.md` ... `week-08.md` | One file per phase: every working day (`## Dnn`), every member: tasks with acceptance criteria |

"Week N" is the name of phase N (2-3 working days). Task IDs (`Wn-Dd-CODE-k`) are the original ones; the `Dd` part no longer means the day of the week.

## Team

| Code | GitHub | Name | Owns |
|---|---|---|---|
| DAT | @Tdat10052499 | Dat (maintainer) | `agent/`, `backend/`, `docs/contracts/`, shared files (`Makefile`, `docker-compose.yml`, `.github/`), LLM serving, integration |
| FAO | @F4ol4n | Faolan | `pipelines/` (ingestion, cleaning, big-data processing, chunking, embeddings, indexing, incremental ingestion); retrieval quality inside `agent/retrieval/` together with DAT |
| LDN | @Yui-Mika | Duong Ngoc Linh Dan | `frontend/`, `evaluation/` (golden set, metrics, user study) |

## Procedure for an AI agent asked "What do I need to do today?"

1. **Identify the member.** Use `git config user.name`, `git config user.email` or `gh api user --jq .login`, and map it to the Team table. If it is ambiguous, ask the user which code (DAT, FAO, LDN) they are.
2. **Identify today.** Use the system date (do not guess). Look it up in [calendar.md](calendar.md) to get the Day ID (`Dnn`) and the week file; today's section is the heading `## Dnn` in that file.
   - Sunday or date outside the table: say there are no scheduled tasks, then go to step 4 (catch-up).
3. **Read today's section** for that member in the week file. Each task has: ID, module, what to do, outputs, "Done when", "Depends on". Lines starting with **Replan:** override the original task text.
4. **Check for unfinished work.** Look at the member's previous tasks in the current and previous phase: a task is done when its outputs exist on `main` (merged PR) or its issue is closed. Also read the member's last journal entry `docs/journal/<code>/Wn.md`. List unfinished tasks first; they take priority over today's tasks, except tasks marked **[blocking]** for others. Tasks listed under "Cut or merged in the replan" are not to be done.
5. **Check dependencies.** For each "Depends on" ID, check it is done. A dependency scheduled on the same day must be finished first (respect any time noted in the task, e.g. "merge by 12:00"). If it is not done, say which member owns it and propose either a stub/fake to proceed or a different task from the same phase.
6. **Present the plan to the user** (tasks in order, files to touch, commands to run) and wait for confirmation before changing code.
7. **Execute** following [AGENTS.md](../../AGENTS.md): branch `feat/<task-id-lowercase>-<slug>` (e.g. `feat/w2-d1-fao-1-downloader`), only the files in scope, `make lint test` before committing, commit messages reference the task ID.
8. **Finish the day:** open or update the PR (title starts with the task ID), and append to `docs/journal/<code>/Wn.md`: done, results (numbers, commands, commit hash), problems, next.

## Rules that apply every day

- Every task ID appears in the branch name, PR title and journal, so progress can be traced.
- Tasks marked **[blocking]** unblock another member: finish and merge them first, even if a stub is all that is possible today.
- Never mark a task done without running its "Done when" checks.
- A change to `docs/contracts/` needs an issue and DAT's approval (see AGENTS.md).
- Phases are only 2-3 days long: if a [blocking] task is more than half a day late, or any task more than one day late, tell DAT in the phase's tracking issue the same day; the cut list in [00-overview.md](00-overview.md#cut-list) decides what to drop.
- The last day of each phase is gate day (see [calendar.md](calendar.md)): merge open PRs, run the gate checklist of the phase, close the milestone.
- Sundays are buffer days: no new tasks; use them to catch up or let long jobs run.
