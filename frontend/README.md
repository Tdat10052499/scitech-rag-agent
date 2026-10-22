# frontend/

Chat UI for the SciTech RAG Agent: React + Vite + TypeScript (see
[ADR 0004](../docs/decisions/0004-frontend-framework.md)).

Current state: the chat screen sends questions to `POST /chat` and renders the answer as its
events arrive (`src/api.ts` reads the stream with `fetch`): sources, streamed text, follow-up
chips, and the error and "not enough evidence" states. One `session_id` per conversation; the
"New conversation" button starts a new one. The answer text is read as Markdown by a small parser of
our own (`src/markdown.ts`: paragraphs, bullet and numbered lists, bold, italic, code), rendered as React
elements, so no HTML in an answer is ever interpreted; `[n]` markers are buttons that bring source `n`
into view. Sources are listed in rank order with title, year, categories and link, without the score:
it has no common scale across retrievers and `RETRIEVAL_MIN_SCORE` is not calibrated yet (W3-D2-LDN-1).
Not done yet: a way to show how well a source matches (after ADR 0009), and citations that jump to a
passage inside a paper. Tests: the SSE client (`src/api.ts`, W2-D5-LDN-1) and the Markdown parser
(`src/markdown.ts`, W3-D2-LDN-1) have automated tests; the screens are checked by hand.

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

Other commands: `npm run typecheck`, `npm test` (tests of the SSE client and the Markdown parser; Node's built-in test
runner, no extra package, needs Node 22.6 or newer), `npm run build` (output in `dist/`,
git-ignored).

To use a backend on another address: `VITE_BACKEND_URL=http://host:8000 npm run dev`
(PowerShell: `$env:VITE_BACKEND_URL="http://host:8000"; npm run dev`).
