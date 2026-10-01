# Daily plan: how to use it

This folder is the single source of truth for **who does what, on which day**, from 2026-10-05 to 2026-11-27.
It is written so that an AI coding agent can answer "What do I need to do today?" without extra context.

| File | Content |
|---|---|
| [00-overview.md](00-overview.md) | Roles, phases, weekly gates, final deliverables, cut list |
| [calendar.md](calendar.md) | Date to Day ID (D01-D40) and week file |
| `week-01.md` ... `week-08.md` | Every working day, every member: tasks with acceptance criteria |

## Team

| Code | GitHub | Name | Owns |
|---|---|---|---|
| DAT | @Tdat10052499 | Dat (maintainer) | `agent/`, `backend/`, `docs/contracts/`, shared files (`Makefile`, `docker-compose.yml`, `.github/`), LLM serving, integration |
| FAO | @F4ol4n | Faolan | `pipelines/` (ingestion, cleaning, big-data processing, chunking, embeddings, indexing, incremental ingestion); retrieval quality inside `agent/retrieval/` together with DAT |
| LDN | @Yui-Mika | Duong Ngoc Linh Dan | `frontend/`, `evaluation/` (golden set, metrics, user study) |

## Procedure for an AI agent asked "What do I need to do today?"

1. **Identify the member.** Use `git config user.name`, `git config user.email` or `gh api user --jq .login`, and map it to the Team table. If it is ambiguous, ask the user which code (DAT, FAO, LDN) they are.
2. **Identify today.** Use the system date (do not guess). Look it up in [calendar.md](calendar.md) to get the Day ID and the heading `Wn-Dd` in the week file.
   - Weekend or date outside the table: say there are no scheduled tasks, then go to step 4 (catch-up).
3. **Read today's section** for that member in the week file. Each task has: ID, module, what to do, outputs, "Done when", "Depends on".
4. **Check for unfinished work.** Look at the member's previous tasks in the current and previous week: a task is done when its outputs exist on `main` (merged PR) or its issue is closed. Also read the member's last journal entry `docs/journal/<code>/Wn.md`. List unfinished tasks first; they take priority over today's tasks, except tasks marked **[blocking]** for others.
5. **Check dependencies.** For each "Depends on" ID, check it is done. If not, say which member owns it and propose either a stub/fake to proceed or a different task from the same week.
6. **Present the plan to the user** (tasks in order, files to touch, commands to run) and wait for confirmation before changing code.
7. **Execute** following [AGENTS.md](../../AGENTS.md): branch `feat/<task-id-lowercase>-<slug>` (e.g. `feat/w2-d1-fao-1-downloader`), only the files in scope, `make lint test` before committing, commit messages reference the task ID.
8. **Finish the day:** open or update the PR (title starts with the task ID), and append to `docs/journal/<code>/Wn.md`: done, results (numbers, commands, commit hash), problems, next.

## Rules that apply every day

- Every task ID appears in the branch name, PR title and journal, so progress can be traced.
- Tasks marked **[blocking]** unblock another member: finish and merge them first, even if a stub is all that is possible today.
- Never mark a task done without running its "Done when" checks.
- A change to `docs/contracts/` needs an issue and DAT's approval (see AGENTS.md).
- If you are more than one day behind, tell DAT in the week's tracking issue the same day; the cut list in [00-overview.md](00-overview.md#cut-list) decides what to drop.
- Friday is gate day: merge open PRs, run the gate checklist of the week, close the milestone.
