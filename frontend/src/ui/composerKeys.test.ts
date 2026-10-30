import assert from "node:assert/strict";
import { test } from "node:test";
import { shouldSubmitOnKey } from "./composerKeys.ts";

const key = (over: Partial<Parameters<typeof shouldSubmitOnKey>[0]>) => ({ key: "Enter", shiftKey: false, isComposing: false, keyCode: 13, ...over });

test("Enter sends", () => {
  assert.equal(shouldSubmitOnKey(key({})), true);
});

test("Shift+Enter does not send (the browser inserts a line break)", () => {
  assert.equal(shouldSubmitOnKey(key({ shiftKey: true })), false);
});

test("Enter that confirms an IME composition does not send", () => {
  assert.equal(shouldSubmitOnKey(key({ isComposing: true })), false);
  assert.equal(shouldSubmitOnKey(key({ keyCode: 229 })), false); // Safari, right after compositionend
});

test("other keys do not send", () => {
  assert.equal(shouldSubmitOnKey(key({ key: "a", keyCode: 65 })), false);
});
