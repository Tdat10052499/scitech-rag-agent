import { useEffect, useState } from "react";

// Spike for ADR 0004 (W1-D2-LDN-1): proves React + Vite + TypeScript can call
// the backend (GET /health, contract: docs/contracts/api.openapi.yaml).
type Health = { status: string };
type State = { kind: "loading" } | { kind: "ok"; health: Health } | { kind: "error"; message: string };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/health")
      .then((r) => (r.ok ? (r.json() as Promise<Health>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((health) => setState({ kind: "ok", health }))
      .catch((e: Error) => setState({ kind: "error", message: e.message }));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", margin: "4rem auto", maxWidth: 480 }}>
      <h1>SciTech RAG Agent</h1>
      <p data-testid="backend-status">
        Backend:{" "}
        {state.kind === "loading" && "checking..."}
        {state.kind === "ok" && `${state.health.status}`}
        {state.kind === "error" && `unreachable (${state.message})`}
      </p>
    </main>
  );
}
