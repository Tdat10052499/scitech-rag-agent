import type { Source } from "./types";

type Props = {
  sources: Source[];
  insufficientEvidence: boolean;
  activeIndex: number | null; // 0-based index of the source whose [n] was clicked
};

function meta(s: Source): string {
  const parts: string[] = [];
  if (s.source) parts.push(s.source);
  if (s.published_at) parts.push(s.published_at.slice(0, 4));
  if (s.categories?.length) parts.push(s.categories.join(", "));
  return parts.join(" · ");
}

export default function SourcesPanel({ sources, insufficientEvidence, activeIndex }: Props) {
  return (
    <aside className="sources" aria-label="Sources">
      <h2>Sources</h2>
      {sources.length === 0 ? (
        <p className="sources-empty">
          {insufficientEvidence ? "No source passed the evidence check for this question." : "No sources for this answer."}
        </p>
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
                <p className="source-score">
                  <span className="score-bar" aria-hidden="true">
                    <span style={{ width: `${Math.round(Math.min(Math.max(s.score, 0), 1) * 100)}%` }} />
                  </span>
                  score {s.score.toFixed(2)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
