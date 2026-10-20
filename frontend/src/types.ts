// Shapes of the data the chat screen shows. `Source` follows the frozen API contract
// (docs/contracts/api.openapi.yaml, 0.2.1); optional fields are simply absent when unknown.
export type Source = {
  chunk_id: string;
  doc_id: string;
  title: string;
  score: number;
  url?: string;
  snippet?: string;
  source?: "arxiv" | "openalex" | "wikipedia";
  published_at?: string; // ISO date, e.g. "2024-10-08"
  categories?: string[];
};

// Error codes of the `error` event (contract 0.2.1, schema `Error`).
export type ErrorCode = "llm_unavailable" | "retrieval_failed" | "timeout" | "internal";

export type ChatError = {
  code?: ErrorCode; // absent for failures that never reached the agent (network, HTTP status)
  message: string;
};

export type UserMessage = { id: string; role: "user"; text: string };

export type AssistantMessage = {
  id: string;
  role: "assistant";
  text: string; // may contain citation markers like [1] (1-based position in `sources`)
  sources: Source[];
  followups: string[]; // the UI shows at most 4
  insufficientEvidence: boolean;
  // searching: request sent, no event yet; answering: sources arrived; done / error: stream ended.
  status: "searching" | "answering" | "done" | "error";
  error?: ChatError; // set when status is "error"; the text received so far is kept
};

export type Message = UserMessage | AssistantMessage;

export const MAX_FOLLOWUPS = 4;
