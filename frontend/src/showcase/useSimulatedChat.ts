import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatEvent } from "../api";
import { applyEvent, newTurn, phaseOf, retryPlan } from "../chat/chatState";
import type { ChatController } from "../chat/chatState";
import type { Message } from "../types";
import { INSUFFICIENT_TEXT, SOURCES, TURN_1, TURN_2 } from "./fixtures";

// SHOWCASE ONLY. A ChatController that plays fixture answers with timers, as the same events the API
// streams (sources, token, followups, done | error), through the same applyEvent as the real chat.
// "insufficient" in a question gives the insufficient-evidence branch, "fail" an error, like the demo agent.

export function useSimulatedChat(initial: Message[]): ChatController {
  const [messages, setMessages] = useState<Message[]>(initial);
  const [busy, setBusy] = useState(false);
  const timers = useRef<number[]>([]);
  const nextId = useRef(10);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const stop = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => stop, []);

  const send = useCallback((text: string) => {
    const n = nextId.current++;
    const [question, reply] = newTurn(n, text);
    setMessages((prev) => [...prev, question, reply]);
    setBusy(true);

    const lowered = text.toLowerCase();
    const script = n % 2 === 0 ? TURN_1 : TURN_2;
    const events: ChatEvent[] = [];
    if (lowered.includes("insufficient")) {
      events.push({ type: "sources", sources: [] });
      events.push(...INSUFFICIENT_TEXT.split(/(?<=\s)/).map((t): ChatEvent => ({ type: "token", text: t })));
      events.push({ type: "done", insufficientEvidence: true });
    } else if (lowered.includes("fail")) {
      events.push({ type: "sources", sources: [SOURCES.attention] });
      events.push({ type: "error", error: { code: "retrieval_failed", message: "Simulated failure (retrieval_failed), no backend involved." } });
    } else {
      events.push({ type: "sources", sources: script.sources });
      events.push(...script.text.split(/(?<=\s)/).map((t): ChatEvent => ({ type: "token", text: t })));
      events.push({ type: "followups", questions: script.followups });
      events.push({ type: "done", insufficientEvidence: false });
    }
    events.forEach((event, i) => {
      const at = i === 0 ? 700 : 800 + i * 35;
      timers.current.push(
        window.setTimeout(() => {
          setMessages((prev) => prev.map((m) => (m.role === "assistant" && m.id === reply.id ? applyEvent(m, event) : m)));
          if (event.type === "done" || event.type === "error") setBusy(false);
        }, at),
      );
    });
  }, []);

  const retry = useCallback(() => {
    const plan = retryPlan(messagesRef.current);
    if (!plan) return;
    setMessages(plan.keep);
    send(plan.question.replace(/fail/gi, "retry")); // the simulated retry succeeds
  }, [send]);

  const newConversation = useCallback(() => {
    stop();
    setBusy(false);
    setMessages([]);
  }, []);

  return { messages, phase: phaseOf(messages, busy), send, retry, newConversation };
}
