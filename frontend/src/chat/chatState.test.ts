import assert from "node:assert/strict";
import { test } from "node:test";
import type { ChatEvent } from "../api.ts";
import type { AssistantMessage, Message, Source } from "../types.ts";
import { applyEvent, liveStatus, newTurn, phaseOf, retryPlan } from "./chatState.ts";

const src: Source = { chunk_id: "1706.03762#0", doc_id: "1706.03762", title: "Attention Is All You Need", score: 0.8 };
const play = (events: ChatEvent[]): AssistantMessage => events.reduce(applyEvent, newTurn(1, "q")[1]);

test("a normal stream: sources, tokens, follow-ups, done", () => {
  const m = play([
    { type: "sources", sources: [src] },
    { type: "token", text: "Attention only " },
    { type: "token", text: "[1]." },
    { type: "followups", questions: ["What is multi-head attention?"] },
    { type: "done", insufficientEvidence: false },
  ]);
  assert.equal(m.status, "done");
  assert.equal(m.text, "Attention only [1].");
  assert.deepEqual(m.sources, [src]);
  assert.deepEqual(m.followups, ["What is multi-head attention?"]);
  assert.equal(m.insufficientEvidence, false);
});

test("done keeps the message id; an answer that ends in an error has none", () => {
  const done = play([{ type: "sources", sources: [] }, { type: "done", insufficientEvidence: false, messageId: "3f2a" }]);
  assert.equal(done.messageId, "3f2a");
  const failed = play([{ type: "token", text: "x" }, { type: "error", error: { message: "boom" } }]);
  assert.equal(failed.messageId, undefined);
});

test("insufficient evidence is a finished answer, not an error", () => {
  const m = play([{ type: "sources", sources: [] }, { type: "token", text: "Not enough evidence." }, { type: "done", insufficientEvidence: true }]);
  assert.equal(m.status, "done");
  assert.equal(m.insufficientEvidence, true);
  assert.equal(liveStatus([m]), "Answer complete: not enough evidence in the corpus.");
});

test("an error keeps the text received before it", () => {
  const m = play([{ type: "sources", sources: [src] }, { type: "token", text: "Partial" }, { type: "error", error: { code: "timeout", message: "Too slow." } }]);
  assert.equal(m.status, "error");
  assert.equal(m.text, "Partial");
  assert.deepEqual(m.error, { code: "timeout", message: "Too slow." });
});

test("the composer phase follows the latest answer", () => {
  const [q, a] = newTurn(1, "q");
  assert.equal(phaseOf([q, a], true), "waiting"); // sent, no event yet
  assert.equal(phaseOf([q, applyEvent(a, { type: "sources", sources: [] })], true), "streaming");
  assert.equal(phaseOf([q, a], false), "idle");
});

test("retry resends the question of the latest failed answer and drops the failed pair", () => {
  const [q1, a1] = newTurn(1, "first");
  const [q2, a2] = newTurn(2, "second");
  const failed = applyEvent(a2, { type: "error", error: { message: "The server is not reachable." } });
  const done = applyEvent(a1, { type: "done", insufficientEvidence: false });
  const messages: Message[] = [q1, done, q2, failed];
  assert.deepEqual(retryPlan(messages), { question: "second", keep: [q1, done] });
});

test("no retry when the latest answer did not fail", () => {
  const [q, a] = newTurn(1, "q");
  assert.equal(retryPlan([q, applyEvent(a, { type: "done", insufficientEvidence: false })]), null);
  assert.equal(retryPlan([q, a]), null); // still streaming
  assert.equal(retryPlan([]), null);
});
