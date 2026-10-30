import { useCallback, useEffect, useRef, useState } from "react";
import { ChatTransportError, streamChat } from "../api";
import type { AssistantMessage, Message } from "../types";
import { applyEvent, newTurn, phaseOf, retryPlan } from "./chatState";
import type { ChatController } from "./chatState";
import { useBackendHealth } from "./useBackendHealth";

// The real conversation: POST /chat through src/api.ts, one session_id per conversation. This is the
// logic that was in App.tsx (W2-D2-LDN-1), unchanged in behaviour; retry is new.

function newSessionId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useChat(): ChatController {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState(newSessionId);
  const [busy, setBusy] = useState(false);
  const health = useBackendHealth();
  const nextId = useRef(1);
  const abort = useRef<AbortController | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => () => abort.current?.abort(), []); // stop reading if the page unmounts

  const update = useCallback((id: string, change: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((prev) => prev.map((m) => (m.role === "assistant" && m.id === id ? change(m) : m)));
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (abort.current) return; // one question at a time (the composer also blocks this)
      const [question, reply] = newTurn(nextId.current++, text);
      setMessages((prev) => [...prev, question, reply]);
      setBusy(true);

      const controller = new AbortController();
      abort.current = controller;
      try {
        for await (const event of streamChat(text, sessionId, controller.signal)) {
          update(reply.id, (m) => applyEvent(m, event));
        }
      } catch (e) {
        if (controller.signal.aborted) return; // a new conversation was started
        const message = e instanceof ChatTransportError ? e.message : "Unexpected error while reading the answer.";
        update(reply.id, (m) => ({ ...m, status: "error", error: { message } }));
      } finally {
        if (abort.current === controller) {
          abort.current = null;
          setBusy(false);
        }
      }
    },
    [sessionId, update],
  );

  const retry = useCallback(() => {
    const plan = abort.current ? null : retryPlan(messagesRef.current);
    if (!plan) return;
    setMessages(plan.keep);
    void send(plan.question);
  }, [send]);

  const newConversation = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    setBusy(false);
    setMessages([]);
    setSessionId(newSessionId());
  }, []);

  return { messages, phase: phaseOf(messages, busy), send: (t) => void send(t), retry, newConversation, health };
}
