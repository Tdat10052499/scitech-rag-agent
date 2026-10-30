# frontend/

Chat UI for the SciTech RAG Agent: React + Vite + TypeScript (see
[ADR 0004](../docs/decisions/0004-frontend-framework.md)).

Current state: the chat screen (`src/App.tsx` → `src/chat/ChatWorkspace.tsx`) is built from the
design system approved on 2026-10-21 ([docs/design-system/](docs/design-system/README.md)): a
workspace with sidebar, conversation and sources panel (drawers on narrow screens), light and dark
themes. It sends questions to `POST /chat` and renders the answer as its events arrive
(`src/chat/useChat.ts` with the SSE client `src/api.ts`): sources, streamed text, follow-up
suggestions, and the error and "not enough evidence" states, with "Try again" after an error. One
`session_id` per conversation; "New conversation" starts a new one. The answer text is read as
Markdown by a small parser of our own (`src/markdown.ts`), rendered as React elements, so no HTML in
an answer is ever interpreted; `[n]` markers open source `n` of the same answer in the sources panel.
Sources are listed in rank order with title, kind, year, categories and link, without the score: it
has no common scale across retrievers and `RETRIEVAL_MIN_SCORE` is not calibrated yet (W3-D2-LDN-1).
Not done yet: a way to show how well a source matches (after ADR 0009), citations that jump to a
passage inside a paper, rating buttons. Tests: the SSE client, the Markdown parser, the chat state
rules and the design-system logic (citations, source metadata, composer keys, WCAG contrast) have
automated tests; the screens are checked by hand.

## Run (Windows, macOS, Linux)

Requires Node.js 22 LTS (https://nodejs.org). The backend must be running on
port 8000 (`make run`, or the raw command in the root README). The backend imports the agent
package, so set `PYTHONPATH=agent/src` first (PowerShell: `$env:PYTHONPATH = "agent/src"`);
`make run` does it for you. Until the index and the LLM server are wired in, the backend uses the
offline demo agent. In the chat box, `insufficient`, `fail:retrieval_failed`, `fail:timeout`,
`fail:llm_unavailable` and `fail:internal` trigger the demo's special cases.

```bash
cd frontend
npm ci            # install exactly what package-lock.json says
npm run dev       # http://localhost:5173 (API calls are proxied to the backend)
```

Other commands: `npm run typecheck`, `npm test` (tests of the SSE client, the Markdown parser, the chat state
rules and the design-system logic and contrast; Node's built-in test runner, no extra package, needs Node 22.6 or
newer), `npm run build` (output in `dist/`, git-ignored), `npm run showcase` (design-system showcase,
no backend needed; its layout specimen renders the same `ChatWorkspace` as the app with fixture data;
see [docs/design-system/](docs/design-system/README.md)).

To use a backend on another address: `VITE_BACKEND_URL=http://host:8000 npm run dev`
(PowerShell: `$env:VITE_BACKEND_URL="http://host:8000"; npm run dev`).
