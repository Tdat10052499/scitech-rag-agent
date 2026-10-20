import assert from "node:assert/strict";
import { test } from "node:test";
import { parseInline, parseMarkdown } from "./markdown.ts";
import type { Block, Inline } from "./markdown.ts";

const text = (t: string): Inline => ({ type: "text", text: t });
const cite = (n: number): Inline => ({ type: "cite", n });

test("an empty or blank answer has no blocks", () => {
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown("  \n\n \n"), []);
});

test("a blank line starts a new paragraph, a single line break does not", () => {
  const blocks = parseMarkdown("First line\nstill the first.\n\nSecond paragraph.");
  assert.deepEqual(blocks, [
    { type: "paragraph", children: [text("First line still the first.")] },
    { type: "paragraph", children: [text("Second paragraph.")] },
  ]);
});

test("CRLF line endings give the same blocks as LF", () => {
  assert.deepEqual(parseMarkdown("a\r\n\r\nb"), parseMarkdown("a\n\nb"));
});

test("a numbered list may follow a paragraph line directly (as in a real answer)", () => {
  const blocks = parseMarkdown("Two ways to reduce this issue are:\n1. Faithful Finetuning (F2) [1].\n2. Retrieval [2].");
  assert.deepEqual(blocks, [
    { type: "paragraph", children: [text("Two ways to reduce this issue are:")] },
    {
      type: "list",
      ordered: true,
      items: [[text("Faithful Finetuning (F2) "), cite(1), text(".")], [text("Retrieval "), cite(2), text(".")]],
    },
  ]);
});

test("bullets with -, * and a bullet character are one unordered list", () => {
  const blocks = parseMarkdown("- one\n* two\n• three");
  assert.deepEqual(blocks, [
    { type: "list", ordered: false, items: [[text("one")], [text("two")], [text("three")]] },
  ]);
});

test("a blank line between two numbered items keeps one list; a different list kind starts a new one", () => {
  const same = parseMarkdown("1. a\n\n2. b");
  assert.equal(same.length, 1);
  assert.equal((same[0] as Extract<Block, { type: "list" }>).items.length, 2);
  const mixed = parseMarkdown("1. a\n- b");
  assert.deepEqual(
    mixed.map((b) => (b.type === "list" ? b.ordered : null)),
    [true, false],
  );
});

test("an indented line continues the list item above", () => {
  const [list] = parseMarkdown("1. First part\n   second part\n2. Next");
  assert.deepEqual(list, {
    type: "list",
    ordered: true,
    items: [[text("First part second part")], [text("Next")]],
  });
});

test("bold, italic and code, and a citation inside bold", () => {
  assert.deepEqual(parseInline("a **bold [1]** and *it* and `x*y`"), [
    text("a "),
    { type: "strong", children: [text("bold "), cite(1)] },
    text(" and "),
    { type: "em", children: [text("it")] },
    text(" and "),
    { type: "code", text: "x*y" },
  ]);
});

test("markers that are not closed, or are not Markdown, stay text (an answer may still be streaming)", () => {
  assert.deepEqual(parseInline("an **open bold"), [text("an **open bold")]);
  assert.deepEqual(parseInline("2*3*4 = 24"), [text("2*3*4 = 24")]);
  assert.deepEqual(parseInline("a * b * c"), [text("a * b * c")]);
});

test("citation markers: adjacent ones are separate, a multi-digit one is one marker", () => {
  assert.deepEqual(parseInline("claim [1][3] and [12]."), [text("claim "), cite(1), cite(3), text(" and "), cite(12), text(".")]);
});

test("HTML in an answer stays characters, never markup", () => {
  const blocks = parseMarkdown('<script>alert(1)</script> <img src=x onerror=alert(1)> **ok**');
  assert.deepEqual(blocks, [
    {
      type: "paragraph",
      children: [text("<script>alert(1)</script> <img src=x onerror=alert(1)> "), { type: "strong", children: [text("ok")] }],
    },
  ]);
});

test("a line that starts with ** is a paragraph, not a list", () => {
  const [block] = parseMarkdown("**Note:** read this");
  assert.equal(block?.type, "paragraph");
});

test("a fenced code block keeps its lines; an unclosed fence runs to the end", () => {
  assert.deepEqual(parseMarkdown("Run:\n```\na = 1\n\nb = 2\n```\nDone."), [
    { type: "paragraph", children: [text("Run:")] },
    { type: "code", text: "a = 1\n\nb = 2" },
    { type: "paragraph", children: [text("Done.")] },
  ]);
  assert.deepEqual(parseMarkdown("```\nprint(1)"), [{ type: "code", text: "print(1)" }]);
});

test("headings, links and tables are left as plain text", () => {
  assert.deepEqual(parseMarkdown("# Title\n\n[a link](http://x.y)"), [
    { type: "paragraph", children: [text("# Title")] },
    { type: "paragraph", children: [text("[a link](http://x.y)")] },
  ]);
});

test("every prefix of a streamed answer parses without throwing", () => {
  const answer = "Intro [1].\n\n1. **First** item [2]\n   more\n2. `code` item\n```\nx\n```\n- tail *em*";
  for (let i = 0; i <= answer.length; i++) parseMarkdown(answer.slice(0, i));
});
