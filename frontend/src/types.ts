// Shapes of the data the chat screen shows. `Source` follows the frozen API contract
// (docs/contracts/api.openapi.yaml, 0.2.0); optional fields are simply absent when unknown.
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

export type UserMessage = { id: string; role: "user"; text: string };

export type AssistantMessage = {
  id: string;
  role: "assistant";
  text: string; // may contain citation markers like [1] (1-based position in `sources`)
  sources: Source[];
  followups: string[]; // the UI shows at most 4
  insufficientEvidence: boolean;
};

export type Message = UserMessage | AssistantMessage;

export const MAX_FOLLOWUPS = 4;
