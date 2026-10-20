import type { Source } from "./types";

type Props = {
  sources: Source[];
  insufficientEvidence: boolean;
  activeIndex: number | null; // 0-based index of the source whose [n] was clicked
  pending: boolean; // the request is sent but `sources` has not arrived yet
  failed: boolean; // the stream ended with an error
};

function meta(s: Source): string {
  const parts: string[] = [];
  if (s.source) parts.push(s.source);
  if (s.published_at) parts.push(s.published_at.slice(0, 4));
  if (s.categories?.length) parts.push(s.categories.join(", "));
  return parts.join(" · ");
}

function emptyText({ insufficientEvidence, pending, failed }: Pick<Props, "insufficientEvidence" | "pending" | "failed">) {
  if (pending) return "Looking for sources...";
  if (failed) return "No sources: the request failed before any source was found.";
  if (insufficientEvidence) return "No source passed the evidence check for this question.";
  return "No sources for this answer.";
}

export default function SourcesPanel({ sources, insufficientEvidence, activeIndex, pending, failed }: Props) {
  return (
    <aside className="sources" aria-label="Sources">
      <h2>Sources</h2>
      {sources.length === 0 ? (
        <p className="sources-empty">{emptyText({ insufficientEvidence, pending, failed })}</p>
      ) : (
        <ol className="source-list">
          {sources.map((s, i) => (
            <li key={s.chunk_id} className={`source${activeIndex === i ? " active" : ""}`}>
              <span className="source-number" aria-hidden="true">
                {i + 1}
              </span>
              <div className="source-body">
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title}
                  </a>
                ) : (
                  <span className="source-title">{s.title}</span>
                )}
                {meta(s) && <p className="source-meta">{meta(s)}</p>}
                {s.snippet && <p className="source-snippet">{s.snippet}</p>}
                {/* The score bar is hidden until the range of real retrieval scores is known (a bar
                    assumes 0 to 1). `s.score` is still part of the data; W3 decides how to show it. */}
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
