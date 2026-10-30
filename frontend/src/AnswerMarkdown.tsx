import { Fragment } from "react";
import type { ReactNode } from "react";
import { groupCitations } from "./citeGroups";
import { parseMarkdown } from "./markdown";
import type { Inline } from "./markdown";

type Props = {
  text: string;
  // Draws each "[n]" marker (the design system's AssistantMessage passes CitationMarker). The caller
  // decides how a number with no matching source looks; it must never point to another source.
  renderCite: (n: number) => ReactNode;
};

function inline(nodes: Inline[], renderCite: Props["renderCite"]): ReactNode[] {
  // A marker is kept on one line with the word before it and the punctuation after it.
  return groupCitations(nodes).map((piece, i) => {
    if (piece.kind === "group") {
      return (
        <span key={i} style={{ whiteSpace: "nowrap" }}>
          {piece.before}
          {piece.cites.map((c, j) => (
            <Fragment key={j}>{renderCite(c.n)}</Fragment>
          ))}
          {piece.after}
        </span>
      );
    }
    const node = piece.node;
    switch (node.type) {
      case "text":
        return node.text;
      case "code":
        return <code key={i}>{node.text}</code>;
      case "strong":
        return <strong key={i}>{inline(node.children, renderCite)}</strong>;
      case "em":
        return <em key={i}>{inline(node.children, renderCite)}</em>;
    }
  });
}

// The answer text as React elements (no innerHTML): an HTML tag in an LLM answer stays text.
export default function Markdown({ text, renderCite }: Props) {
  return (
    <>
      {parseMarkdown(text).map((block, i) => {
        switch (block.type) {
          case "paragraph":
            return <p key={i}>{inline(block.children, renderCite)}</p>;
          case "code":
            return (
              <pre key={i}>
                <code>{block.text}</code>
              </pre>
            );
          case "list": {
            const items = block.items.map((item, j) => <li key={j}>{inline(item, renderCite)}</li>);
            return block.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
          }
        }
      })}
    </>
  );
}
