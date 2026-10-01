# W01-03 Working development environment for everyone

- Area: infra
- Milestone: Week 1
- Depends on: none

## Goal
Every member can clone, install, lint, test and run the backend health endpoint.

## Inputs and outputs
- Outputs: confirmed `make setup`, `make lint`, `make test`, `make run` on Windows (and macOS/Linux where used); fixes to docs/Makefile if something fails; confirmation that CI passes on a PR.

## Scope
- May change: `Makefile`, `README.md`, `CONTRIBUTING.md`, `requirements*.txt`, `.github/workflows/`.

## Acceptance criteria
- [ ] Each member ran the quick start and reported the result on the issue.
- [ ] `GET /health` returns `{"status": "ok"}` locally.
- [ ] Branch protection on `main` is enabled and a test PR was merged through it.

## Notes / risks
`make` is not available by default on Windows; document the chosen alternative (e.g. WSL, `winget install` of make, or running the commands from the Makefile directly).
