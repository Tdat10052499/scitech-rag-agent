import type { ReactNode } from "react";
import { parseMarkdown } from "./markdown";
import type { Inline } from "./markdown";

type Props = {
  text: string;
  sourceCount: number; // "[n]" is a button only when 1 <= n <= sourceCount; other markers stay text
  onCite: (index: number) => void; // 0-based index of the source
};

function inline(nodes: Inline[], { sourceCount, onCite }: Pick<Props, "sourceCount" | "onCite">): ReactNode[] {
  return nodes.map((node, i) => {
    switch (node.type) {
      case "text":
        return node.text;
      case "code":
        return <code key={i}>{node.text}</code>;
      case "strong":
        return <strong key={i}>{inline(node.children, { sourceCount, onCite })}</strong>;
      case "em":
        return <em key={i}>{inline(node.children, { sourceCount, onCite })}</em>;
      case "cite":
        return node.n >= 1 && node.n <= sourceCount ? (
          <button key={i} type="button" className="cite" onClick={() => onCite(node.n - 1)} aria-label={`Source ${node.n}`}>
            [{node.n}]
          </button>
        ) : (
          `[${node.n}]`
        );
    }
  });
}

// The answer text as React elements (no innerHTML), with "[n]" markers as buttons.
export default function Markdown({ text, sourceCount, onCite }: Props) {
  const ctx = { sourceCount, onCite };
  return (
    <>
      {parseMarkdown(text).map((block, i) => {
        switch (block.type) {
          case "paragraph":
            return <p key={i}>{inline(block.children, ctx)}</p>;
          case "code":
            return (
              <pre key={i}>
                <code>{block.text}</code>
              </pre>
            );
          case "list": {
            const items = block.items.map((item, j) => <li key={j}>{inline(item, ctx)}</li>);
            return block.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
          }
        }
      })}
    </>
  );
}
