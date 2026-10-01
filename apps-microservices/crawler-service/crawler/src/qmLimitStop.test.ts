import { test } from "node:test";
import assert from "node:assert/strict";
import { shouldStopForQuestionMark } from "./qmLimitStop.js";

test("no stop when bypass committed at/over limit", () => {
    assert.equal(shouldStopForQuestionMark(150, true, false, 100), false);
});
test("no stop when skip committed", () => {
    assert.equal(shouldStopForQuestionMark(150, false, true, 100), false);
});
test("stop when neither and over the limit", () => {
    assert.equal(shouldStopForQuestionMark(100, false, false, 100), true);
});
test("no stop below the limit", () => {
    assert.equal(shouldStopForQuestionMark(99, false, false, 100), false);
});
