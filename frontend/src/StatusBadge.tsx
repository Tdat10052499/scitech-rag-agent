import { useEffect, useState } from "react";

// Backend health indicator kept from the ADR 0004 spike (GET /health, contract: api.openapi.yaml).
type State = { kind: "loading" } | { kind: "ok"; status: string } | { kind: "error"; message: string };

export default function StatusBadge() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/health")
      .then((r) => (r.ok ? (r.json() as Promise<{ status: string }>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((h) => setState({ kind: "ok", status: h.status }))
      .catch((e: Error) => setState({ kind: "error", message: e.message }));
  }, []);

  const label =
    state.kind === "loading" ? "checking..." : state.kind === "ok" ? state.status : `unreachable (${state.message})`;
  return (
    <p className={`status status-${state.kind}`} data-testid="backend-status">
      Backend: {label}
    </p>
  );
}
