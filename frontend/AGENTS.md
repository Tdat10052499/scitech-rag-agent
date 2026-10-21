# frontend/ — user interface

Scope: chat UI that shows streamed answers, citations (sources) and clickable follow-up questions.

- Talks to the backend only through `docs/contracts/api.openapi.yaml` (including SSE event names).
- Stack (ADR 0004): React + Vite + TypeScript, Node.js 22 LTS. No Next.js: the backend is FastAPI and the UI is a static single-page app.
- Commands (run in `frontend/`): `npm ci` (install from `package-lock.json`), `npm run dev` (dev server, port 5173, proxies `/health` and `/chat` to the backend on port 8000), `npm run typecheck`, `npm test` (tests of `src/api.ts` and `src/markdown.ts` with Node's built-in test runner), `npm run build`.
- `/chat` is a POST request, so the browser `EventSource` cannot be used; read the stream with `fetch` and a stream reader.
- Answers are shown through `src/markdown.ts` and `src/AnswerMarkdown.tsx` (React elements, never `innerHTML`); keep it that way, because answers come from an LLM.
- Show source citations next to every answer and a clear message when the agent reports insufficient evidence.
- Do not hand-copy API shapes that the contract defines; derive TypeScript types from `api.openapi.yaml` or update them in the same PR as the contract.
- Adding `frontend/` steps to the `Makefile` and to CI (`.github/workflows/ci.yml`) touches shared files: ask DAT (see ADR 0004, Consequences).
