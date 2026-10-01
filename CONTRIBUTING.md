# Contributing

## Workflow (GitHub Flow)
1. Pick an issue assigned to you. Each issue links to a brief in `docs/tasks/`.
2. `git pull`, create a branch from `main`: `feat/<issue>-<slug>`, `fix/<issue>-<slug>` or `docs/<slug>`.
3. Implement within the scope declared in the brief. Run `make lint test`.
4. Open a Pull Request using the template; link the issue with `Closes #<n>`.
5. Another member reviews (CODEOWNERS requests the reviewer). CI must pass. Squash-merge into `main`.
6. Append to your journal: `docs/journal/<your-name>/Wxx.md`.

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
