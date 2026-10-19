// Tests for the SSE client in api.ts. Run with `npm test` (Node's built-in test runner, no extra
// dependency). `fetch` is replaced by a fake that returns a stream of the chunks given by each test,
// so the cut points between chunks are exactly the ones the test writes down.
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { ChatTransportError, streamChat, toChatEvent } from "./api.ts";
import type { ChatEvent } from "./api.ts";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

const encoder = new TextEncoder();

/** Answer the next fetch with `chunks` as the response body, one read per chunk. */
function fakeStream(chunks: (string | Uint8Array)[], status = 200): void {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  });
  globalThis.fetch = (async () => new Response(body, { status })) as typeof fetch;
}

async function collect(): Promise<ChatEvent[]> {
  const events: ChatEvent[] = [];
  for await (const event of streamChat("Why?", "session-1")) events.push(event);
  return events;
}

const SOURCE = { chunk_id: "2401.00001#0", doc_id: "2401.00001", title: "A paper", score: 0.5 };
const DONE = 'event: done\ndata: {"insufficient_evidence": false, "message_id": "m1"}\n\n';

describe("streamChat: normal streams", () => {
  it("yields sources, tokens, follow-ups and done in order", async () => {
    fakeStream([
      `event: sources\ndata: ${JSON.stringify([SOURCE])}\n\n`,
      'event: token\ndata: "Hel"\n\n',
      'event: token\ndata: "lo [1]"\n\n',
      'event: followups\ndata: ["What next?", 7]\n\n',
      DONE,
    ]);
    assert.deepEqual(await collect(), [
      { type: "sources", sources: [SOURCE] },
      { type: "token", text: "Hel" },
      { type: "token", text: "lo [1]" },
      { type: "followups", questions: ["What next?"] },
      { type: "done", insufficientEvidence: false, messageId: "m1" },
    ]);
  });

  it("sends the question and the session id as a POST", async () => {
    let request: { url: string; init?: RequestInit } | undefined;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      request = { url, init };
      return new Response(DONE);
    }) as typeof fetch;
    await collect();
    assert.equal(request?.url, "/chat");
    assert.equal(request?.init?.method, "POST");
    assert.deepEqual(JSON.parse(String(request?.init?.body)), { session_id: "session-1", message: "Why?" });
  });

  it("reads an event that is split across chunks at any point", async () => {
    const whole = `event: token\ndata: "Hi"\n\n${DONE}`;
    for (let cut = 1; cut < whole.length; cut++) {
      fakeStream([whole.slice(0, cut), whole.slice(cut)]);
      assert.deepEqual(
        await collect(),
        [
          { type: "token", text: "Hi" },
          { type: "done", insufficientEvidence: false, messageId: "m1" },
        ],
        `cut at ${cut}`,
      );
    }
  });

  it("reads a multi-byte character that is split across chunks", async () => {
    const bytes = encoder.encode('event: token\ndata: "Đan"\n\n');
    const cut = bytes.indexOf(0xc4) + 1; // between the two bytes of "Đ"
    fakeStream([bytes.slice(0, cut), bytes.slice(cut), DONE]);
    assert.deepEqual((await collect())[0], { type: "token", text: "Đan" });
  });

  it("ignores comments, unknown events and a payload of the wrong shape", async () => {
    fakeStream([': keep-alive\n\n', 'event: surprise\ndata: {}\n\n', 'event: token\ndata: 5\n\n', DONE]);
    assert.deepEqual(await collect(), [{ type: "done", insufficientEvidence: false, messageId: "m1" }]);
  });
});

describe("streamChat: line endings", () => {
  it("reads CRLF line endings", async () => {
    fakeStream(['event: token\r\ndata: "Hi"\r\n\r\n', DONE.replaceAll("\n", "\r\n")]);
    assert.deepEqual((await collect())[0], { type: "token", text: "Hi" });
  });

  it("keeps a CRLF whose two characters arrive in different chunks", async () => {
    // The case found in the review of #63: the first chunk ends with "\r", the next starts with "\n".
    fakeStream(['event: token\r', '\ndata: "Hi"\r\n\r\n', DONE]);
    assert.deepEqual(await collect(), [
      { type: "token", text: "Hi" },
      { type: "done", insufficientEvidence: false, messageId: "m1" },
    ]);
  });

  it("keeps a blank line made of CRLF CRLF split between chunks", async () => {
    fakeStream(['event: token\r\ndata: "Hi"\r\n\r', '\n', DONE]);
    assert.deepEqual((await collect())[0], { type: "token", text: "Hi" });
  });

  it("reads lone CR line endings, also at the very end of the stream", async () => {
    fakeStream(['event: token\rdata: "Hi"\r\r', 'event: done\rdata: {}\r\r']);
    assert.deepEqual(await collect(), [
      { type: "token", text: "Hi" },
      { type: "done", insufficientEvidence: false, messageId: undefined },
    ]);
  });
});

describe("streamChat: errors", () => {
  it("passes on a stream that is only an error event (contract 0.2.1)", async () => {
    fakeStream(['event: error\ndata: {"code": "retrieval_failed", "message": "Index offline"}\n\n']);
    assert.deepEqual(await collect(), [
      { type: "error", error: { code: "retrieval_failed", message: "Index offline" } },
    ]);
  });

  it("keeps the tokens received before an error event", async () => {
    fakeStream(['event: token\ndata: "Par"\n\n', 'event: error\ndata: {"code": "timeout", "message": "Slow"}\n\n']);
    const events = await collect();
    assert.deepEqual(events.map((e) => e.type), ["token", "error"]);
  });

  it("throws when the stream ends without done or error", async () => {
    fakeStream(['event: token\ndata: "Par"\n\n']);
    await assert.rejects(collect(), (e) => e instanceof ChatTransportError && /closed before/.test(e.message));
  });

  it("says the server is not reachable when fetch fails or the proxy answers 502, 503 or 504", async () => {
    globalThis.fetch = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    await assert.rejects(collect(), (e) => e instanceof ChatTransportError && /not reachable/.test(e.message));

    for (const status of [502, 503, 504]) {
      fakeStream([], status);
      await assert.rejects(collect(), (e) => e instanceof ChatTransportError && /not reachable/.test(e.message), String(status));
    }
  });

  it("reports another HTTP error with its status", async () => {
    fakeStream([], 500);
    await assert.rejects(collect(), (e) => e instanceof ChatTransportError && /HTTP 500/.test(e.message));
  });

  it("throws on an event whose data is not JSON", async () => {
    fakeStream(["event: token\ndata: not json\n\n"]);
    await assert.rejects(collect(), (e) => e instanceof ChatTransportError && /not valid JSON/.test(e.message));
  });

  it("lets an abort through as an AbortError, not as a transport error", async () => {
    globalThis.fetch = (async () => {
      throw new DOMException("aborted", "AbortError");
    }) as typeof fetch;
    await assert.rejects(collect(), (e) => e instanceof DOMException && e.name === "AbortError");
  });
});

describe("toChatEvent", () => {
  it("reads a done event without a payload as sufficient evidence", () => {
    assert.deepEqual(toChatEvent("done", "null"), {
      type: "done",
      insufficientEvidence: false,
      messageId: undefined,
    });
    assert.deepEqual(toChatEvent("done", '{"insufficient_evidence": true}'), {
      type: "done",
      insufficientEvidence: true,
      messageId: undefined,
    });
  });

  it("maps an unknown error code to internal and fills in a missing message", () => {
    assert.deepEqual(toChatEvent("error", '{"code": "gremlins"}'), {
      type: "error",
      error: { code: "internal", message: "Something went wrong." },
    });
  });
});
