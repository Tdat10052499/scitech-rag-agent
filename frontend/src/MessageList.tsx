import type { Message } from "./types";
import { MAX_FOLLOWUPS } from "./types";

type Props = {
  messages: Message[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCite: (messageId: string, sourceIndex: number) => void;
  onFollowup: (text: string) => void;
};

// Turns "[n]" markers into buttons when n points to an existing source; other text stays plain.
function withCitations(text: string, sourceCount: number, onCite: (index: number) => void) {
  return text.split(/(\[\d+\])/).map((part, i) => {
    const m = /^\[(\d+)\]$/.exec(part);
    const n = m ? Number(m[1]) : 0;
    if (m && n >= 1 && n <= sourceCount) {
      return (
        <button key={i} type="button" className="cite" onClick={() => onCite(n - 1)} aria-label={`Source ${n}`}>
          [{n}]
        </button>
      );
    }
    return part;
  });
}

export default function MessageList({ messages, selectedId, onSelect, onCite, onFollowup }: Props) {
  // Chips belong to the latest answer that actually offers follow-ups.
  const chipsOwner = [...messages].reverse().find((m) => m.role === "assistant" && m.followups.length > 0);
  return (
    <section className="messages" aria-label="Conversation" aria-live="polite">
      {messages.map((m) =>
        m.role === "user" ? (
          <article key={m.id} className="message user">
            <p className="who">You</p>
            <p className="text">{m.text}</p>
          </article>
        ) : (
          <article
            key={m.id}
            className={`message assistant${m.insufficientEvidence ? " insufficient" : ""}${selectedId === m.id ? " selected" : ""}`}
          >
            <p className="who">
              Assistant
              <button type="button" className="show-sources" onClick={() => onSelect(m.id)}>
                {m.sources.length > 0 ? `Show sources (${m.sources.length})` : "Show sources"}
              </button>
            </p>
            {m.insufficientEvidence && (
              <p className="notice" role="status">
                Not enough evidence in the corpus
              </p>
            )}
            <p className="text">{withCitations(m.text, m.sources.length, (i) => onCite(m.id, i))}</p>
            {m === chipsOwner && (
              <div className="chips" aria-label="Follow-up questions">
                {m.followups.slice(0, MAX_FOLLOWUPS).map((q) => (
                  <button key={q} type="button" className="chip" onClick={() => onFollowup(q)}>
                    {q}
                  </button>
                ))}
              </div>
            )}
          </article>
        ),
      )}
    </section>
  );
}
