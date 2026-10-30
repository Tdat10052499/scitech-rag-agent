// Pure state rules of a conversation, shared by the real chat (useChat) and the showcase simulator.
// No React and no network here, so the rules are tested with Node (chatState.test.ts).
import type { ChatEvent } from "../api";
import type { BackendHealth } from "../health";
import type { AssistantMessage, Message, UserMessage } from "../types";

/** idle: ready to send; waiting: question sent, no event yet; streaming: events are arriving. */
export type ChatPhase = "idle" | "waiting" | "streaming";

/** What a screen needs from a conversation, whatever the data source. */
export type ChatController = {
  messages: Message[];
  phase: ChatPhase;
  send: (text: string) => void;
  retry: () => void; // resend the last question after a failed answer (see retryPlan)
  newConversation: () => void;
  health?: BackendHealth; // the real chat reports GET /health; the showcase simulator leaves it out
};

export function newTurn(n: number, text: string): [UserMessage, AssistantMessage] {
  return [
    { id: `u${n}`, role: "user", text },
    { id: `a${n}`, role: "assistant", text: "", sources: [], followups: [], insufficientEvidence: false, status: "searching" },
  ];
}

/** Apply one event of the /chat stream to the answer it belongs to (moved from App.tsx unchanged). */
export function applyEvent(m: AssistantMessage, event: ChatEvent): AssistantMessage {
  switch (event.type) {
    case "sources":
      return { ...m, sources: event.sources, status: "answering" };
    case "token":
      return { ...m, text: m.text + event.text, status: "answering" };
    case "followups":
      return { ...m, followups: event.questions };
    case "done":
      return { ...m, insufficientEvidence: event.insufficientEvidence, status: "done", messageId: event.messageId };
    case "error":
      return { ...m, status: "error", error: event.error };
  }
}

export function lastAnswer(messages: Message[]): AssistantMessage | undefined {
  const last = messages[messages.length - 1];
  return last?.role === "assistant" ? last : undefined;
}

export function phaseOf(messages: Message[], busy: boolean): ChatPhase {
  if (!busy) return "idle";
  return lastAnswer(messages)?.status === "searching" ? "waiting" : "streaming";
}

/**
 * Retry = send the same question again. Only the latest answer, only when it failed. The failed pair
 * is removed first so the question is not shown twice; the agent stores a turn in its session history
 * only when it succeeds (agent/src/scitech_agent/agent.py), so resending in the same session is safe.
 */
export function retryPlan(messages: Message[]): { question: string; keep: Message[] } | null {
  const answer = lastAnswer(messages);
  const question = messages[messages.length - 2];
  if (answer?.status !== "error" || question?.role !== "user") return null;
  return { question: question.text, keep: messages.slice(0, -2) };
}

/** One line for the polite live region about the latest answer. */
export function liveStatus(messages: Message[]): string {
  const turn = lastAnswer(messages);
  if (!turn) return "";
  switch (turn.status) {
    case "searching":
      return "Searching the corpus...";
    case "answering":
      return "Writing the answer...";
    case "error":
      return `Error: ${turn.error?.message ?? "something went wrong."}`;
    case "done":
      if (turn.insufficientEvidence) return "Answer complete: not enough evidence in the corpus.";
      return turn.sources.length > 0 ? `Answer complete. ${turn.sources.length} sources.` : "Answer complete.";
  }
}
