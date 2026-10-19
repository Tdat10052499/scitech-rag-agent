import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ChatTransportError, streamChat } from "./api";
import type { ChatEvent } from "./api";
import MessageList from "./MessageList";
import SourcesPanel from "./SourcesPanel";
import StatusBadge from "./StatusBadge";
import type { AssistantMessage, Message } from "./types";
import "./App.css";
import "./chat.css";

// W2-D2-LDN-1: the input calls POST /chat and the answer is rendered as its events arrive
// (sources, token, followups, done or error). One session_id per conversation.

function newSessionId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Apply one event of the stream to the assistant message it belongs to. */
function applyEvent(m: AssistantMessage, event: ChatEvent): AssistantMessage {
  switch (event.type) {
    case "sources":
      return { ...m, sources: event.sources, status: "answering" };
    case "token":
      return { ...m, text: m.text + event.text, status: "answering" };
    case "followups":
      return { ...m, followups: event.questions };
    case "done":
      return { ...m, insufficientEvidence: event.insufficientEvidence, status: "done" };
    case "error":
      return { ...m, status: "error", error: event.error };
  }
}

/** One line for screen readers (aria-live) and sighted users about the latest answer. */
function statusText(messages: Message[]): string {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") return "";
  switch (last.status) {
    case "searching":
      return "Searching the corpus...";
    case "answering":
      return "Writing the answer...";
    case "error":
      return `Error: ${last.error?.message ?? "something went wrong."}`;
    case "done":
      if (last.insufficientEvidence) return "Answer complete: not enough evidence in the corpus.";
      return last.sources.length > 0 ? `Answer complete. ${last.sources.length} sources.` : "Answer complete.";
  }
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState(newSessionId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []); // stop reading if the page unmounts

  const selected = messages.find((m): m is AssistantMessage => m.role === "assistant" && m.id === selectedId);

  function select(id: string) {
    setSelectedId(id);
    setActiveSource(null);
  }

  function cite(messageId: string, sourceIndex: number) {
    setSelectedId(messageId);
    setActiveSource(sourceIndex);
  }

  function update(id: string, change: (m: AssistantMessage) => AssistantMessage) {
    setMessages((prev) => prev.map((m) => (m.role === "assistant" && m.id === id ? change(m) : m)));
  }

  async function send(text: string) {
    const n = nextId.current++;
    const assistantId = `a${n}`;
    const reply: AssistantMessage = {
      id: assistantId,
      role: "assistant",
      text: "",
      sources: [],
      followups: [],
      insufficientEvidence: false,
      status: "searching",
    };
    setMessages((prev) => [...prev, { id: `u${n}`, role: "user", text }, reply]);
    setSelectedId(assistantId);
    setActiveSource(null);
    setBusy(true);

    const controller = new AbortController();
    abort.current = controller;
    try {
      for await (const event of streamChat(text, sessionId, controller.signal)) {
        update(assistantId, (m) => applyEvent(m, event));
      }
    } catch (e) {
      if (controller.signal.aborted) return; // a new conversation was started
      const message = e instanceof ChatTransportError ? e.message : "Unexpected error while reading the answer.";
      update(assistantId, (m) => ({ ...m, status: "error", error: { message } }));
    } finally {
      if (abort.current === controller) {
        abort.current = null;
        setBusy(false);
      }
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    void send(text);
  }

  function newConversation() {
    abort.current?.abort();
    abort.current = null;
    setBusy(false);
    setMessages([]);
    setSelectedId(null);
    setActiveSource(null);
    setDraft("");
    setSessionId(newSessionId());
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>SciTech RAG Agent</h1>
        <div className="header-actions">
          <button type="button" className="new-chat" onClick={newConversation} disabled={messages.length === 0}>
            New conversation
          </button>
          <StatusBadge />
        </div>
      </header>
      <main className="layout">
        <MessageList
          messages={messages}
          selectedId={selectedId}
          onSelect={select}
          onCite={cite}
          onFollowup={setDraft}
          status={statusText(messages)}
        />
        <SourcesPanel
          sources={selected?.sources ?? []}
          insufficientEvidence={selected?.insufficientEvidence ?? false}
          activeIndex={activeSource}
          pending={selected?.status === "searching"}
          failed={selected?.status === "error"}
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
          <button type="submit" disabled={busy || draft.trim() === ""}>
            {busy ? "Answering..." : "Send"}
          </button>
        </form>
      </main>
    </div>
  );
}
