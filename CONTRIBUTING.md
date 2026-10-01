# Contributing

## Workflow (GitHub Flow)
1. Pick today's task from `docs/plan/` (see `docs/plan/README.md`) or an issue assigned to you.
2. `git pull`, create a branch from `main`: `feat/<task-id>-<slug>` (e.g. `feat/w2-d1-fao-1-downloader`), `fix/...` or `docs/...`.
3. Implement within the scope declared in the brief. Run `make lint test`.
4. Open a Pull Request using the template; link the issue with `Closes #<n>`.
5. Another member reviews (CODEOWNERS requests the reviewer). CI must pass. Squash-merge into `main`.
6. Append to your journal: `docs/journal/<CODE>/Wn.md` (CODE = DAT, FAO or LDN).

## Rules
- `main` is protected: no direct pushes, at least one approving review, CI green.
- Keep PRs small (one task, ideally under ~400 changed lines) and merge often to avoid conflicts.
- Commit messages use Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Changes to `docs/contracts/` need an issue and approval from the maintainer, because several modules depend on them.
- Never commit secrets, `.env`, data files, or notebook outputs.
- If AI tools produced the code, you are still the author: read the whole diff, run the tests, and be able to explain every change in review.

## Reviewing
Read the diff, not just the description. Check: scope matches the brief, acceptance criteria are met, tests exist for new behaviour, contracts/docs updated, no secrets or data files.

## Local setup
See the Quick start in `README.md`. Install the git hooks once with `make setup`.
