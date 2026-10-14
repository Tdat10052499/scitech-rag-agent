# 0004. Frontend framework: React + Vite + TypeScript

- Status: accepted (2026-10-14, DAT post-merge review of #22)
- Date: 2026-10-14
- Deciders: LDN (proposal), DAT (review)

## Context
The product is a chat UI that streams an answer token by token, shows numbered citations `[n]` linked to a sources panel, offers clickable follow-up questions and a distinct "insufficient evidence" state (`frontend/AGENTS.md`, contract `docs/contracts/api.openapi.yaml`). It will be judged in a live demo on 2026-11-10 and in a small user study (W7), so polish and smooth streaming matter, not only correctness. The backend, agent and pipelines are Python (FastAPI).

Constraints:
- 22 working days in total (ADR 0010); the frontend skeleton is due on D03 and the first end-to-end UI on D12. ADR 0010 makes "time to build" weigh more than in the original plan.
- Team skills, as stated by LDN on 2026-10-14 (not independently checked): all three members know Python, JavaScript, React and Vite.
- `/chat` is a POST request that returns `text/event-stream`.

## Options considered
Criteria and weights (time to build is weighted highest because of ADR 0010):

| Criterion | Weight | Streamlit (Python) | React + Vite + TypeScript |
|---|---|---|---|
| Time to build | high | Fastest start: a working chat page in hours. Custom behaviour (clickable `[n]`, highlighting a source, special evidence state) needs workarounds or custom components, which removes much of the head start. | Slower start (Node setup, project files, CI step), an estimated half day to a working skeleton. Custom behaviour is ordinary component code. |
| SSE streaming | high | Works, but every interaction re-runs the script, so streaming into a rich layout is harder to control and tends to flicker. | Natural: update only the answer component as tokens arrive. Needs `fetch` plus a stream reader because `EventSource` is GET-only. |
| Look and polish (demo, user study) | high | Looks like a data tool; limited control over layout and typography. | Full control; common UI libraries (Tailwind CSS, shadcn/ui) give a professional look quickly. |
| Team skills | medium | Everyone knows Python. | Everyone knows JavaScript and React; TypeScript is the only new piece. |
| Deployment with Docker | medium | One Python container. | Build to static files (multi-stage Docker build), served by a small web server or by FastAPI. One more build step. |
| Fit with the repo | medium | Same language as everything else. | Separate `package.json` inside `frontend/`; touches shared files (CI, Makefile). Types can be generated from the OpenAPI contract. |

A third family was considered and rejected up front: Next.js. It is a full-stack framework with its own Node server (server-side rendering, API routes). The app has one page, no SEO need and an existing FastAPI backend, so Next.js would add a second server layer and a heavier deployment, and its server/client component model is extra to learn. A static single-page app built by Vite is enough.

TypeScript or plain JavaScript: TypeScript. The project is driven by contracts and the contract is about to change (for example new `Source` fields, see issue #7). Types derived from `api.openapi.yaml` make such changes show up as compile errors instead of demo-day bugs. The cost is some friction at the start; the Vite `react-ts` setup with simple types keeps it small.

## Decision
Use React + Vite + TypeScript (Node.js 22 LTS), as a static single-page app in `frontend/`, without Next.js.

Implementation choices that follow (confirmed or changed in W2-D1-LDN-1, not yet installed in the spike):
- Dev server on port 5173 with a Vite proxy for `/health` and `/chat` to the backend on port 8000, so no CORS configuration is needed in development.
- Read the `/chat` stream with `fetch` and a stream reader (or a small library such as `@microsoft/fetch-event-source`).
- Styling and components: Tailwind CSS and shadcn/ui; answers rendered with `react-markdown`.
- Types for contract schemas generated with `openapi-typescript`; the SSE event payloads, which OpenAPI does not describe, are declared by hand next to them.

Exit condition: if by the end of D06 (Mon 2026-10-19, Gate W2) the frontend does not have a working page that sends a question and renders streamed events (stub backend is enough), the team switches to Streamlit, which is the default in `docs/plan/00-overview.md`. Work done up to then (API types, event parsing) is small and would be kept as notes for the Streamlit client.

## Consequences
- Spike in `frontend/` proves the toolchain: `npm run typecheck` and `npm run build` pass, and the page shows the result of `GET /health` through the Vite proxy (checked against a FastAPI app with the same `/health` response, both when the backend is up and when it is down).
- Node.js 22 LTS becomes a prerequisite for frontend work. Members install it from nodejs.org; the root README quick start should mention it (small follow-up PR).
- Shared files need a change that DAT owns: add `npm ci`, `npm run typecheck` and `npm run build` for `frontend/` to `.github/workflows/ci.yml` (W1-D5-DAT-2 currently speaks of "frontend requirements if Python") and optional `make` targets. Until then CI does not check the frontend.
- If the backend is ever served from a different origin than the page (for example a deployed static site calling a separate API host), the backend must enable CORS for that origin. In development the proxy avoids this. Static files can also be served by the backend itself, which avoids CORS entirely.
- The sources panel and the "insufficient evidence" state depend on contract changes proposed in issue #7 (`Source` fields, `done` payload).
- Risk: setup time on Windows machines and TypeScript friction. Mitigation: the exit condition above and the small spike already in place.
