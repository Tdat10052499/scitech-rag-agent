import type { ChatError, ErrorCode, Source } from "./types";

// Client for POST /chat (docs/contracts/api.openapi.yaml, 0.2.1). The request is a POST, so the
// browser EventSource cannot be used: the body is read with fetch and parsed as server-sent events.

export type ChatEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "followups"; questions: string[] }
  | { type: "done"; insufficientEvidence: boolean; messageId?: string }
  | { type: "error"; error: ChatError };

const ERROR_CODES: readonly string[] = ["llm_unavailable", "retrieval_failed", "timeout", "internal"];

/** The request or the connection failed outside the agent: network down, HTTP error, cut stream. */
export class ChatTransportError extends Error {}

/**
 * Make every line ending "\n" ("\r\n", "\n" and a lone "\r" are all line ends in SSE). A "\r" at the
 * very end of the text may be the first half of a "\r\n" whose second half is in the next chunk,
 * so it is kept as it is until more text arrives or the stream has ended (`final`).
 */
function normalizeNewlines(text: string, final: boolean): string {
  const out = text.replace(/\r\n|\r(?!$)/g, "\n");
  return final ? out.replace(/\r$/, "\n") : out;
}

/** One SSE block ("event: x" and "data: ..." lines) as event name and data text. */
function parseBlock(block: string): { name: string; data: string } | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // blank line or comment (keep-alive)
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  return data.length === 0 ? null : { name, data: data.join("\n") };
}

/** Turn one parsed SSE block into a typed event; unknown event names are ignored. */
export function toChatEvent(name: string, data: string): ChatEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    throw new ChatTransportError(`The server sent a "${name}" event that is not valid JSON.`);
  }
  switch (name) {
    case "sources":
      return Array.isArray(payload) ? { type: "sources", sources: payload as Source[] } : null;
    case "token":
      return typeof payload === "string" ? { type: "token", text: payload } : null;
    case "followups":
      return Array.isArray(payload)
        ? { type: "followups", questions: payload.filter((q): q is string => typeof q === "string") }
        : null;
    case "done": {
      // A missing or empty payload means insufficient_evidence: false (contract).
      const o = (payload ?? {}) as { insufficient_evidence?: unknown; message_id?: unknown };
      return {
        type: "done",
        insufficientEvidence: o.insufficient_evidence === true,
        messageId: typeof o.message_id === "string" ? o.message_id : undefined,
      };
    }
    case "error": {
      const o = (payload ?? {}) as { code?: unknown; message?: unknown };
      const code = typeof o.code === "string" && ERROR_CODES.includes(o.code) ? (o.code as ErrorCode) : "internal";
      const message = typeof o.message === "string" && o.message ? o.message : "Something went wrong.";
      return { type: "error", error: { code, message } };
    }
    default:
      return null;
  }
}

/**
 * Send `message` and yield the events of the answer as they arrive. Ends after `done` or `error`.
 * Throws `ChatTransportError` when the request fails or the stream ends without either of them.
 * Pass an AbortSignal to stop reading (an aborted request throws a DOMException "AbortError").
 */
export async function* streamChat(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  let response: Response;
  try {
    response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ChatTransportError("The server is not reachable. Check that the backend is running.");
  }
  if ([502, 503, 504].includes(response.status)) {
    // The dev proxy answers like this when the backend on port 8000 is not running.
    throw new ChatTransportError("The server is not reachable. Check that the backend is running.");
  }
  if (!response.ok || !response.body) {
    throw new ChatTransportError(`The server rejected the request (HTTP ${response.status}).`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer = normalizeNewlines(buffer + decoder.decode(value, { stream: !done }), done);
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const parsed = parseBlock(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (!parsed) continue;
        const event = toChatEvent(parsed.name, parsed.data);
        if (!event) continue;
        yield event;
        if (event.type === "done" || event.type === "error") return;
      }
      if (done) break;
    }
  } catch (e) {
    if (e instanceof ChatTransportError || (e instanceof DOMException && e.name === "AbortError")) throw e;
    throw new ChatTransportError("The connection was lost while the answer was streaming.");
  } finally {
    void reader.cancel().catch(() => undefined);
  }
  throw new ChatTransportError("The connection was closed before the answer was complete.");
}
