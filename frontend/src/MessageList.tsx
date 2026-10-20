import { useEffect, useRef } from "react";
import Markdown from "./Markdown";
import type { Message } from "./types";
import { MAX_FOLLOWUPS } from "./types";

type Props = {
  messages: Message[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCite: (messageId: string, sourceIndex: number) => void;
  onFollowup: (text: string) => void;
  status: string; // one-line progress or result of the latest answer, announced to screen readers
};

const EXAMPLES = [
  "What is retrieval-augmented generation?",
  "How are LLM hallucinations detected?",
  "Does giving a model more retrieved passages always help?",
];

export default function MessageList({ messages, selectedId, onSelect, onCite, onFollowup, status }: Props) {
  // Keep the newest text in view while the answer streams (the composer is sticky at the bottom).
  const end = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages]);

  // Chips belong to the latest answer that actually offers follow-ups.
  const chipsOwner = [...messages].reverse().find((m) => m.role === "assistant" && m.followups.length > 0);
  return (
    <section className="messages" aria-label="Conversation">
      {messages.length === 0 && (
        <div className="empty">
          <p>Ask a question about LLM and NLP research. Answers cite the papers they come from.</p>
          <div className="chips" aria-label="Example questions">
            {EXAMPLES.map((q) => (
              <button key={q} type="button" className="chip" onClick={() => onFollowup(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      {messages.map((m) =>
        m.role === "user" ? (
          <article key={m.id} className="message user">
            <p className="who">You</p>
            <p className="text">{m.text}</p>
          </article>
        ) : (
          <article
            key={m.id}
            className={`message assistant${m.insufficientEvidence ? " insufficient" : ""}${m.status === "error" ? " failed" : ""}${selectedId === m.id ? " selected" : ""}`}
          >
            <p className="who">
              Assistant
              <button type="button" className="show-sources" onClick={() => onSelect(m.id)}>
                {m.sources.length > 0 ? `Show sources (${m.sources.length})` : "Show sources"}
              </button>
            </p>
            {m.insufficientEvidence && <p className="notice">Not enough evidence in the corpus</p>}
            {m.text !== "" && (
              <div className="text md">
                <Markdown text={m.text} sourceCount={m.sources.length} onCite={(i) => onCite(m.id, i)} />
              </div>
            )}
            {m.status === "searching" && <p className="pending">Searching the corpus...</p>}
            {m.status === "error" && m.error && (
              <p className="notice error">
                {m.text !== "" ? "The answer stopped early: " : ""}
                {m.error.message}
              </p>
            )}
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
      <p ref={end} className="chat-status" role="status" aria-live="polite">
        {status}
      </p>
    </section>
  );
}
