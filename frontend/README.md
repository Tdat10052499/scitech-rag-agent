# frontend/

Chat UI for the SciTech RAG Agent: React + Vite + TypeScript (see
[ADR 0004](../docs/decisions/0004-frontend-framework.md)).

Current state: the chat screen sends questions to `POST /chat` and renders the answer as its
events arrive (`src/api.ts` reads the stream with `fetch`): sources, streamed text, follow-up
chips, and the error and "not enough evidence" states. One `session_id` per conversation; the
"New conversation" button starts a new one. Sources are shown without the score until the range
of real retrieval scores is known (W3). Not done yet: the sources panel details, clickable
citations that jump to a passage (W3-W4). Tests: the SSE client (`src/api.ts`) has automated tests
(W2-D5-LDN-1); the screens are checked by hand.

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

Other commands: `npm run typecheck`, `npm test` (tests of the SSE client; Node's built-in test
runner, no extra package, needs Node 22.6 or newer), `npm run build` (output in `dist/`,
git-ignored).

To use a backend on another address: `VITE_BACKEND_URL=http://host:8000 npm run dev`
(PowerShell: `$env:VITE_BACKEND_URL="http://host:8000"; npm run dev`).
