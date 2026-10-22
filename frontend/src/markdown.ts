// A small Markdown reader for the answers of the agent. It understands what the answers use:
// paragraphs, bullet and numbered lists, **bold**, *italic*, `code`, fenced code, and the citation
// markers "[n]". It builds a tree, never HTML, so nothing in an answer can inject markup: a "<b>" in
// the text stays the characters "<b>". Anything else (headings, links, tables, images) stays plain text.
// W3-D2-LDN-1; the choice against a Markdown library is in the PR.

export type Inline =
  | { type: "text"; text: string }
  | { type: "cite"; n: number } // "[n]"; the screen decides whether n points to an existing source
  | { type: "code"; text: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] };

export type Block =
  | { type: "paragraph"; children: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "code"; text: string };

// One of: [n] | `code` | **strong** | *em*. A marker only opens before a non-space and only closes
// after a non-space, and "*" does not open right after a letter or digit ("2*3*4" stays text).
const INLINE = /\[(\d+)\]|`([^`\n]+)`|(?<!\*)\*\*(?=\S)([\s\S]+?)(?<=\S)\*\*(?!\*)|(?<![A-Za-z0-9*])\*(?=[^\s*])([^*\n]+?)(?<=\S)\*(?!\*)/g;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ type: "text", text: text.slice(last, start) });
    if (m[1] !== undefined) out.push({ type: "cite", n: Number(m[1]) });
    else if (m[2] !== undefined) out.push({ type: "code", text: m[2] });
    else if (m[3] !== undefined) out.push({ type: "strong", children: parseInline(m[3]) });
    else out.push({ type: "em", children: parseInline(m[4] ?? "") });
    last = start + m[0].length;
  }
  if (last < text.length) out.push({ type: "text", text: text.slice(last) });
  return out;
}

const FENCE = /^\s*```/;
const LIST_ITEM = /^\s*(?:([-*+•])|(\d{1,3})[.)])\s+(.*)$/;

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) blocks.push({ type: "paragraph", children: parseInline(paragraph.join(" ")) });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push({ type: "list", ordered: list.ordered, items: list.items.map(parseInline) });
    list = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";
    if (FENCE.test(line)) {
      flushParagraph();
      flushList();
      const code: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i] ?? "")) code.push(lines[i++] ?? ""); // an unclosed fence runs to the end (the answer may still be streaming)
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }
    if (line.trim() === "") {
      flushParagraph();
      // A blank line between two items of the same list does not end the list.
      const next = lines.slice(i + 1).find((l) => l.trim() !== "");
      const nextItem = next === undefined ? null : LIST_ITEM.exec(next);
      if (list && !(nextItem && Boolean(nextItem[2]) === list.ordered)) flushList();
      continue;
    }
    const item = LIST_ITEM.exec(line);
    if (item) {
      flushParagraph();
      const ordered = Boolean(item[2]);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((item[3] ?? "").trim());
      continue;
    }
    if (list && /^\s{2,}\S/.test(line)) {
      list.items[list.items.length - 1] += " " + line.trim(); // an indented line continues the item
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  return blocks;
}
