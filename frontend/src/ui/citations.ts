// Citation rules shared by the answer and the sources panel.
//
// Contract (api.openapi.yaml): "[n]" in an answer is the n-th (1-based) element of the `sources` array
// of the SAME response. Two answers can both cite [1] and mean different papers, so a citation is
// identified by (turn id, index), never by the number alone.
import { parseMarkdown } from "../markdown.ts";
import type { Inline } from "../markdown.ts";
import type { Source } from "../types";

/** A source of one answer: `index` is 0-based (citation [n] has index n - 1). */
export type CitationTarget = { turnId: string; index: number };

/** The source currently shown from a citation. `nonce` changes on every click (restarts the highlight). */
export type ActiveCitation = CitationTarget & { nonce: number };

export type CitationResolution =
  | { kind: "source"; index: number; source: Source }
  | { kind: "missing"; n: number; available: number };

/** What "[n]" in an answer with `sources` points to. A number outside the list is never remapped. */
export function resolveCitation(sources: readonly Source[], n: number): CitationResolution {
  const source = Number.isInteger(n) && n >= 1 ? sources[n - 1] : undefined;
  return source ? { kind: "source", index: n - 1, source } : { kind: "missing", n, available: sources.length };
}

/** Stable key of a source within the whole conversation. */
export function sourceKey({ turnId, index }: CitationTarget): string {
  return `${turnId}:${index}`;
}

/** Look up the source a target points to, in the turn it belongs to. */
export function findSource(
  turns: ReadonlyArray<{ id: string; sources: readonly Source[] }>,
  target: CitationTarget,
): Source | undefined {
  return turns.find((t) => t.id === target.turnId)?.sources[target.index];
}

/** 0-based indices of the sources an answer text cites (markers inside code are not citations). */
export function citedIndices(text: string): Set<number> {
  const found = new Set<number>();
  const visit = (nodes: Inline[]) => {
    for (const node of nodes) {
      if (node.type === "cite" && node.n >= 1) found.add(node.n - 1);
      else if (node.type === "strong" || node.type === "em") visit(node.children);
    }
  };
  for (const block of parseMarkdown(text)) {
    if (block.type === "paragraph") visit(block.children);
    else if (block.type === "list") block.items.forEach(visit);
  }
  return found;
}
