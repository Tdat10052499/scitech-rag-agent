import { useEffect, useState } from "react";
import { healthFromError, healthFromResponse } from "../health";
import type { BackendHealth } from "../health";

const CHECK_EVERY_MS = 30_000;

/** GET /health once at start and every 30 s, so a user sees that the backend is down before sending. */
export function useBackendHealth(): BackendHealth {
  const [health, setHealth] = useState<BackendHealth>({ kind: "checking" });

  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    async function check() {
      try {
        const response = await fetch("/health", { signal: controller.signal });
        const body: unknown = await response.json().catch(() => null);
        if (!stopped) setHealth(healthFromResponse(response.status, body));
      } catch {
        if (!stopped) setHealth(healthFromError());
      }
    }
    void check();
    const timer = setInterval(() => void check(), CHECK_EVERY_MS);
    return () => {
      stopped = true;
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  return health;
}
