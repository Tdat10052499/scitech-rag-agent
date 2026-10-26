# backend/ — API service

Scope: FastAPI app that exposes the contract in `docs/contracts/api.openapi.yaml`, manages sessions, calls the agent, streams events (SSE).

- Code in `src/app/`, tests in `tests/` (`make test`). Run locally with `make run`.
- Implement endpoints exactly as the contract defines; if the contract is wrong, open an issue instead of diverging.
- No business logic here that belongs to the agent; the backend orchestrates and validates.
- Configuration only via environment variables (`.env.example`).
- `/chat` runs `scitech_agent.Agent` through `app.agent_adapter.AgentAdapter`. `AGENT_MODE=real` (default) builds it with `scitech_agent.factory.agent_from_env()` (`RETRIEVER`, `RETRIEVAL_*`, `LLM_*`); `AGENT_MODE=demo` uses the offline `demo_agent()` (UI work without an index or LLM). Backend tests run in demo mode (`tests/conftest.py`). Startup builds the agent once and, in real mode, warms up its retriever (loads the embedding model, ADR 0009); if that fails, `/chat` streams one `error` event and the next request tries again. So `agent/src` must be importable: `make run` sets `PYTHONPATH=agent/src` (PowerShell: `$env:PYTHONPATH = "agent/src"`); pytest gets it from `pyproject.toml`.
