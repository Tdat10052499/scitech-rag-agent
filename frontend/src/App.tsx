import { useRef, useState } from "react";
import type { FormEvent } from "react";
import MessageList from "./MessageList";
import SourcesPanel from "./SourcesPanel";
import StatusBadge from "./StatusBadge";
import { mockConversation } from "./mock";
import type { AssistantMessage, Message } from "./types";
import "./App.css";

// W2-D1-LDN-1: layout of the chat screen with a hard-coded conversation. Nothing here calls the
// backend yet except the health badge; W2-D2-LDN-1 connects the input to POST /chat.
export default function App() {
  const [messages, setMessages] = useState<Message[]>(mockConversation);
  const firstAssistant = mockConversation.find((m) => m.role === "assistant");
  const [selectedId, setSelectedId] = useState<string | null>(firstAssistant?.id ?? null);
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const nextId = useRef(1);

  const selected = messages.find((m): m is AssistantMessage => m.role === "assistant" && m.id === selectedId);

  function select(id: string) {
    setSelectedId(id);
    setActiveSource(null);
  }

  function cite(messageId: string, sourceIndex: number) {
    setSelectedId(messageId);
    setActiveSource(sourceIndex);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const n = nextId.current++;
    const reply: AssistantMessage = {
      id: `mock-a${n}`,
      role: "assistant",
      text: "(mock) The real answer will stream from the backend once the input is connected.",
      sources: [],
      followups: [],
      insufficientEvidence: false,
    };
    setMessages((prev) => [...prev, { id: `mock-u${n}`, role: "user", text }, reply]);
    setSelectedId(reply.id);
    setActiveSource(null);
    setDraft("");
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>SciTech RAG Agent</h1>
        <StatusBadge />
      </header>
      <main className="layout">
        <MessageList
          messages={messages}
          selectedId={selectedId}
          onSelect={select}
          onCite={cite}
          onFollowup={setDraft}
        />
        <SourcesPanel
          sources={selected?.sources ?? []}
          insufficientEvidence={selected?.insufficientEvidence ?? false}
          activeIndex={activeSource}
        />
        <form className="composer" onSubmit={submit}>
          <label htmlFor="question" className="visually-hidden">
            Your question
          </label>
          <input
            id="question"
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about LLM and NLP research..."
            autoComplete="off"
          />
          <button type="submit" disabled={draft.trim() === ""}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
