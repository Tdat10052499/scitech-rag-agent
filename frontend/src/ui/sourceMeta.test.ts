import assert from "node:assert/strict";
import { test } from "node:test";
import type { Source } from "../types.ts";
import { describeSource, safeHref } from "./sourceMeta.ts";

const base: Source = { chunk_id: "x#0", doc_id: "x", title: "A title", score: 0.4 };

test("an arXiv source shows kind, year and the arXiv id", () => {
  const d = describeSource({ ...base, doc_id: "1706.03762", source: "arxiv", published_at: "2017-06-12", url: "https://arxiv.org/abs/1706.03762" });
  assert.equal(d.kind, "arXiv");
  assert.equal(d.date, "2017");
  assert.equal(d.identifier, "arXiv:1706.03762");
  assert.equal(d.href, "https://arxiv.org/abs/1706.03762");
});

test("a Wikipedia date is the revision, not publication", () => {
  const d = describeSource({ ...base, doc_id: "wiki-Transformer", source: "wikipedia", published_at: "2024-03-02" });
  assert.equal(d.date, "Revised 2024");
  assert.equal(d.identifier, undefined); // internal doc ids are not shown
});

test("missing or invalid metadata is left out, not invented", () => {
  const d = describeSource({ ...base, published_at: "unknown", categories: [" ", ""] });
  assert.equal(d.kind, undefined);
  assert.equal(d.date, undefined);
  assert.equal(d.href, undefined);
  assert.deepEqual(d.categories, []);
  assert.equal(d.snippet, undefined);
  assert.equal(describeSource({ ...base, published_at: "2020-13-01" }).date, undefined);
  assert.equal(describeSource({ ...base, published_at: "2021-02-30" }).date, undefined);
  assert.equal(describeSource({ ...base, published_at: "2024" }).date, "2024");
});

test("an empty title gets a neutral placeholder and is marked", () => {
  const d = describeSource({ ...base, title: "   " });
  assert.equal(d.title, "Untitled source");
  assert.equal(d.untitled, true);
});

test("only http(s) URLs become links", () => {
  assert.equal(safeHref("javascript:alert(1)"), undefined);
  assert.equal(safeHref("data:text/html,hi"), undefined);
  assert.equal(safeHref("/relative/path"), undefined);
  assert.equal(safeHref(""), undefined);
  assert.equal(safeHref(" https://en.wikipedia.org/wiki/Transformer "), "https://en.wikipedia.org/wiki/Transformer");
});

test("categories are trimmed and de-duplicated, order kept", () => {
  assert.deepEqual(describeSource({ ...base, categories: ["cs.CL", "cs.LG", "cs.CL "] }).categories, ["cs.CL", "cs.LG"]);
});
