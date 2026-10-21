// Keeps a citation marker on the same line as the word before it and the punctuation after it, so a
// line never starts with "." or "[1]" ("…on them [1]." stays together). The renderer draws each group
// with `white-space: nowrap`. Pure, so it is tested without a browser (citeGroups.test.ts).
import type { Inline } from "./markdown.ts";

type Cite = Extract<Inline, { type: "cite" }>;

export type Piece =
  | { kind: "inline"; node: Exclude<Inline, Cite> }
  | { kind: "group"; before: string; cites: Cite[]; after: string };

const MAX_GLUED_WORD = 24; // a longer "word" (a URL) is left free to wrap, or it could overflow the column
const TRAILING_WORD = /(\S+\s?)$/;
const LEADING_PUNCTUATION = /^[.,;:!?)\]]+/;

export function groupCitations(nodes: Inline[]): Piece[] {
  const out: Piece[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i]!;
    if (node.type !== "cite") {
      out.push({ kind: "inline", node });
      continue;
    }
    const cites: Cite[] = [];
    let j = i;
    for (; j < nodes.length && nodes[j]!.type === "cite"; j++) cites.push(nodes[j] as Cite);

    let before = "";
    const prev = out[out.length - 1];
    if (prev?.kind === "inline" && prev.node.type === "text") {
      const m = TRAILING_WORD.exec(prev.node.text);
      if (m?.[1] && m[1].trim().length <= MAX_GLUED_WORD) {
        before = m[1];
        const rest = prev.node.text.slice(0, prev.node.text.length - before.length);
        if (rest) prev.node = { type: "text", text: rest };
        else out.pop();
      }
    }

    let after = "";
    const next = nodes[j];
    if (next?.type === "text") {
      after = LEADING_PUNCTUATION.exec(next.text)?.[0] ?? "";
      if (after) nodes = [...nodes.slice(0, j), { type: "text", text: next.text.slice(after.length) }, ...nodes.slice(j + 1)];
    }

    out.push({ kind: "group", before, cites, after });
    i = j - 1;
  }
  return out.filter((p) => !(p.kind === "inline" && p.node.type === "text" && p.node.text === ""));
}
