# backend/ — API service

Scope: FastAPI app that exposes the contract in `docs/contracts/api.openapi.yaml`, manages sessions, calls the agent, streams events (SSE).

- Code in `src/app/`, tests in `tests/` (`make test`). Run locally with `make run`.
- Implement endpoints exactly as the contract defines; if the contract is wrong, open an issue instead of diverging.
- No business logic here that belongs to the agent; the backend orchestrates and validates.
- Configuration only via environment variables (`.env.example`).
