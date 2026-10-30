import assert from "node:assert/strict";
import { test } from "node:test";
import { buildFeedback, feedbackKey } from "./feedback.ts";

test("a thumb on an answer has no follow-up field", () => {
  assert.deepEqual(buildFeedback("s1", { messageId: "m1", target: "answer", rating: "up" }), {
    session_id: "s1",
    message_id: "m1",
    target: "answer",
    rating: "up",
  });
});

test("a click on a follow-up carries the suggestion text as shown", () => {
  assert.deepEqual(buildFeedback("s1", { messageId: "m1", target: "followup", rating: "click", followup: "What is multi-head attention?" }), {
    session_id: "s1",
    message_id: "m1",
    target: "followup",
    rating: "click",
    followup: "What is multi-head attention?",
  });
});

test("items the endpoint would reject with 422 are not built", () => {
  assert.equal(buildFeedback("s1", { messageId: "m1", target: "answer", rating: "click" }), null); // click only for a follow-up
  assert.equal(buildFeedback("s1", { messageId: "m1", target: "followup", rating: "up" }), null); // follow-up text missing
  assert.equal(buildFeedback("s1", { messageId: "", target: "answer", rating: "up" }), null); // no message id
  assert.equal(buildFeedback("", { messageId: "m1", target: "answer", rating: "up" }), null); // no session
});

test("the screen keeps one choice per answer and per suggestion", () => {
  const a = feedbackKey({ messageId: "m1", target: "answer" });
  const f = feedbackKey({ messageId: "m1", target: "followup", followup: "Q?" });
  assert.notEqual(a, f);
  assert.equal(a, feedbackKey({ messageId: "m1", target: "answer" }));
});
