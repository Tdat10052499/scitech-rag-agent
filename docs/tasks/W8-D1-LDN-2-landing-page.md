# W8-D1-LDN-2 Landing page on GitHub Pages

- Area: frontend | infra
- Milestone: Week 8, exception to the feature freeze (needs DAT's approval in the issue)
- Depends on: none (uses the Week 7 results already in `README.md`)

## Goal
A public one-page site that introduces the project before and after the presentation on
2026-11-10: project name and slogan, how a question is answered, the main features, a link to the
live demo, the evaluation results with their intervals, and the team. It is separate from the chat
app, so the frozen product and the Hugging Face Space do not change.

## Context to read
- `docs/00-project-brief.md`, root `README.md` (results, live demo, limits of the public demo)
- `frontend/docs/design-system/` and `frontend/src/ui/tokens.css` (colors, fonts)
- `docs/plan/week-06.md` (feature freeze: only bug fixes after D16)

## Inputs and outputs
- Inputs: design tokens, Week 7 numbers, team table in `docs/plan/README.md`.
- Outputs: `landing/index.html`, `landing/README.md`, `.github/workflows/deploy-landing.yml`,
  one line `/landing/ @Yui-Mika @Tdat10052499` in `.github/CODEOWNERS`.

## Scope
- May change: `landing/` (new), `.github/workflows/deploy-landing.yml` (new), `.github/CODEOWNERS`
  (one added line).
- Must not change: `frontend/`, `backend/`, `agent/`, `pipelines/`, `evaluation/`, `deploy/`,
  `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/deploy-hf-space.yml`,
  root `README.md` (a link to the landing page can be added after the `v1.0` tag).

## Acceptance criteria
- [ ] The PR adds files only in the paths listed under "May change"; `git diff --stat main` shows nothing else.
- [ ] Existing CI passes unchanged (the landing page has no build step and no dependency).
- [ ] After merge, the Pages workflow publishes the page and it opens at the repository's Pages URL.
- [ ] Every number on the page matches `README.md` / `evaluation/RUNS.md` §7; illustrative examples are labelled.
- [ ] Works at 390 px and 1440 px without horizontal scrolling; Auto / Light / Dark theme works; with
      `prefers-reduced-motion` the page has no animation.
- [ ] Links: live demo, GitHub, report, each member's GitHub profile.

## How to test
```bash
cd landing && python -m http.server 8090   # open http://localhost:8090, check desktop and phone width
git diff --stat origin/main                 # only landing/, the new workflow and CODEOWNERS
```

## Notes / risks
- Feature freeze: this adds no feature to the evaluated system; it is a separate static page.
  Merge only after DAT approves the exception in the issue.
- GitHub Pages must be enabled once by the owner (Settings > Pages > Source: GitHub Actions).
- The page loads GSAP, Lenis and SplitType from CDNs and fonts from Google Fonts; without them the
  page still shows all content, only the animations are missing.
