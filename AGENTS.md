# AGENTS.md

Instructions for AI coding agents and humans working in this repository. Keep this file short; details live in `docs/`.

## Project
Interactive web app: an AI agent answers science and technology questions with retrieval over a large corpus, cites its sources, and suggests follow-up questions. Course project, 8 weeks, team work in parallel by module. Read first: `docs/00-project-brief.md`, `docs/01-architecture.md`, `docs/contracts/`.

## Daily plan ("What do I need to do today?")
The day-by-day plan for every member is in `docs/plan/`. When a member asks what to do today, follow the procedure in `docs/plan/README.md`: identify the member (DAT, FAO, LDN), map today's date with `docs/plan/calendar.md`, read that day's section in `docs/plan/week-NN.md`, check unfinished earlier tasks and dependencies, present the plan, then execute. Use the task ID (e.g. `W2-D1-FAO-1`) in branch names, PR titles and journal entries.

## Before you start any task
1. `git pull` and read your task: today's entry in `docs/plan/` or the brief named in your issue (`docs/tasks/<id>.md`). The brief defines goal, inputs/outputs, scope and acceptance criteria. If something is missing or contradictory, stop and ask in the issue; do not guess.
2. Read the `AGENTS.md` inside the module you are changing.
3. Work on a branch named `feat/<issue>-<slug>`, `fix/...` or `docs/...`. Never push to `main`.

## Module map and boundaries
- `pipelines/` data ingestion to chunks and embeddings. Output format: `docs/contracts/chunk.schema.json`.
- `agent/` agent loop, retrieval orchestration, prompts, follow-ups.
- `backend/` FastAPI service. Must match `docs/contracts/api.openapi.yaml`.
- `frontend/` UI. Talks to the backend only through the API contract.
- `evaluation/` golden set and metrics.
Only edit files inside the module(s) your brief names. Shared files (`docs/contracts/`, `docker-compose.yml`, `.github/`, `pyproject.toml`) change only through a dedicated issue.

## Commands
- `make setup` install tooling and dependencies
- `make lint` static checks (ruff)
- `make test` run tests (pytest)
- `make up` / `make down` local infrastructure (Qdrant)
- `make run` backend with auto-reload
Run `make lint test` before every commit; CI runs the same.

## Conventions
- Python 3.10+, type hints on public functions, line length 100.
- Commits follow Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Configuration comes from environment variables listed in `.env.example`. Add new variables there with a safe placeholder.
- The LLM is always called through the OpenAI-compatible interface described in `docs/contracts/llm-client.md`; never hard-code a vendor, model name or URL.
- The agent answers only from retrieved evidence, cites sources, and says so when evidence is insufficient.
- Update docs and contracts in the same PR as the code that changes them.

## Do not
- Read, print, or commit `.env`, API keys, tokens or personal data.
- Commit data files, model weights, or notebook outputs (`data/` is git-ignored; strip notebooks with `nbstripout`).
- Change a contract, schema or public interface without an approved issue.
- Add dependencies without listing them in the module's `requirements.txt` and mentioning them in the PR.
- Claim something works without running the relevant command and reading its output.

## Definition of done
Acceptance criteria in the brief are met, `make lint test` passes, docs/contracts are updated, the PR links its issue and describes how it was tested, and a human reviewer has read the diff.
