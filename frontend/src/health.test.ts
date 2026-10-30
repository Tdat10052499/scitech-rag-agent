import assert from "node:assert/strict";
import { test } from "node:test";
import { healthFromError, healthFromResponse, healthLabel } from "./health.ts";

test("HTTP 200 with status ok is healthy", () => {
  assert.deepEqual(healthFromResponse(200, { status: "ok" }), { kind: "ok" });
  assert.equal(healthLabel({ kind: "ok" }), "Backend: ok");
});

test("any other status, body or HTTP code is down, with a short reason", () => {
  assert.deepEqual(healthFromResponse(200, { status: "degraded" }), { kind: "down", detail: "unexpected answer" });
  assert.deepEqual(healthFromResponse(200, null), { kind: "down", detail: "unexpected answer" });
  assert.deepEqual(healthFromResponse(500, undefined), { kind: "down", detail: "HTTP 500" });
  assert.deepEqual(healthFromResponse(502, undefined), { kind: "down", detail: "not reachable" });
});

test("a failed request is down and the label says so", () => {
  assert.equal(healthLabel(healthFromError()), "Backend: not reachable");
  assert.equal(healthLabel({ kind: "checking" }), "Backend: checking...");
});
