# frontend/

Chat UI for the SciTech RAG Agent: React + Vite + TypeScript (see
[ADR 0004](../docs/decisions/0004-frontend-framework.md)).

Current state: spike only. `src/App.tsx` calls `GET /health` and shows the result.
The real UI starts in W2-D1-LDN-1.

## Run (Windows, macOS, Linux)

Requires Node.js 22 LTS (https://nodejs.org). The backend must be running on
port 8000 (`make run`, or the raw command in the root README).

```bash
cd frontend
npm ci            # install exactly what package-lock.json says
npm run dev       # http://localhost:5173 (API calls are proxied to the backend)
```

Other commands: `npm run typecheck`, `npm run build` (output in `dist/`, git-ignored).

To use a backend on another address: `VITE_BACKEND_URL=http://host:8000 npm run dev`
(PowerShell: `$env:VITE_BACKEND_URL="http://host:8000"; npm run dev`).
