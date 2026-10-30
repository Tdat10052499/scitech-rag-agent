// Backend health for the status indicator (GET /health, contract: docs/contracts/api.openapi.yaml).
// Pure rules here; the hook that polls is src/chat/useBackendHealth.ts.

export type BackendHealth = { kind: "checking" } | { kind: "ok" } | { kind: "down"; detail: string };

/** The answer of GET /health as a health state: HTTP 200 with {"status": "ok"} is healthy. */
export function healthFromResponse(httpStatus: number, body: unknown): BackendHealth {
  // 502, 503 and 504 are what the dev proxy and nginx answer when the backend is not running.
  if ([502, 503, 504].includes(httpStatus)) return healthFromError();
  if (httpStatus < 200 || httpStatus >= 300) return { kind: "down", detail: `HTTP ${httpStatus}` };
  const status = (body as { status?: unknown } | null)?.status;
  return status === "ok" ? { kind: "ok" } : { kind: "down", detail: "unexpected answer" };
}

export function healthFromError(): BackendHealth {
  return { kind: "down", detail: "not reachable" };
}

/** Short text for the indicator. */
export function healthLabel(health: BackendHealth): string {
  switch (health.kind) {
    case "checking":
      return "Backend: checking...";
    case "ok":
      return "Backend: ok";
    case "down":
      return `Backend: ${health.detail}`;
  }
}
