import assert from "node:assert/strict";
import { test } from "node:test";
import type { Source } from "../types.ts";
import { citedIndices, findSource, resolveCitation, sourceKey } from "./citations.ts";

const src = (id: string, title: string): Source => ({ chunk_id: `${id}#0`, doc_id: id, title, score: 0.5 });

// Two answers in one conversation; both cite [1], meaning different papers (contract: [n] refers to
// the `sources` of the same response).
const turns = [
  { id: "a1", sources: [src("2005.11401", "RAG"), src("2004.04906", "DPR")] },
  { id: "a2", sources: [src("2307.03172", "Lost in the Middle")] },
];

test("[n] resolves to the n-th source of its own answer, 1-based", () => {
  const r = resolveCitation(turns[0]!.sources, 2);
  assert.equal(r.kind, "source");
  assert.equal(r.kind === "source" && r.source.title, "DPR");
  assert.equal(r.kind === "source" && r.index, 1);
});

test("the same number in two answers points to different sources", () => {
  assert.equal(findSource(turns, { turnId: "a1", index: 0 })?.title, "RAG");
  assert.equal(findSource(turns, { turnId: "a2", index: 0 })?.title, "Lost in the Middle");
  assert.notEqual(sourceKey({ turnId: "a1", index: 0 }), sourceKey({ turnId: "a2", index: 0 }));
});

test("a number outside the list is reported missing, never remapped to another source", () => {
  for (const n of [0, 3, 99, -1, 1.5]) {
    assert.deepEqual(resolveCitation(turns[0]!.sources, n), { kind: "missing", n, available: 2 });
  }
  assert.equal(resolveCitation([], 1).kind, "missing"); // insufficient evidence: no sources at all
  assert.equal(findSource(turns, { turnId: "a2", index: 1 }), undefined);
  assert.equal(findSource(turns, { turnId: "nope", index: 0 }), undefined);
});

test("citedIndices finds markers in paragraphs, lists and emphasis, not in code", () => {
  const text = "RAG uses retrieval [1].\n\n- **Dense retrieval [2]**\n- see `[3]` in code\n\n```\n[4]\n```";
  assert.deepEqual([...citedIndices(text)].sort(), [0, 1]);
  assert.deepEqual([...citedIndices("No citation here.")], []);
});
