import assert from "node:assert/strict";
import { test } from "node:test";
import { groupCitations } from "./citeGroups.ts";
import { parseInline } from "./markdown.ts";

const cite = (n: number) => ({ type: "cite" as const, n });
const text = (t: string) => ({ kind: "inline" as const, node: { type: "text" as const, text: t } });

test("a marker is grouped with the word before it and the punctuation after it", () => {
  assert.deepEqual(groupCitations(parseInline("conditions the answer on them [1]. The retriever")), [
    text("conditions the answer on "),
    { kind: "group", before: "them ", cites: [cite(1)], after: "." },
    text(" The retriever"),
  ]);
});

test("adjacent markers form one group", () => {
  assert.deepEqual(groupCitations(parseInline("the model [1][3].")), [text("the "), { kind: "group", before: "model ", cites: [cite(1), cite(3)], after: "." }]);
});

test("a marker at the start or with no punctuation after it still forms a group", () => {
  assert.deepEqual(groupCitations(parseInline("[2] says so")), [{ kind: "group", before: "", cites: [cite(2)], after: "" }, text(" says so")]);
});

test("a long word such as a URL is not glued (it must stay free to wrap)", () => {
  const url = "https://example.org/a-very-long-path-segment";
  assert.deepEqual(groupCitations(parseInline(`see ${url} [1]`)), [text(`see ${url} `), { kind: "group", before: "", cites: [cite(1)], after: "" }]);
});

test("the text is unchanged when the pieces are joined back", () => {
  const input = "RAG [1], DPR [2]; both (see [3]) and more [4]!";
  const joined = groupCitations(parseInline(input))
    .map((p) => (p.kind === "group" ? p.before + p.cites.map((c) => `[${c.n}]`).join("") + p.after : p.node.type === "text" ? p.node.text : ""))
    .join("");
  assert.equal(joined, input);
});
