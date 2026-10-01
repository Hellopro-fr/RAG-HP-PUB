import { test } from "node:test";
import assert from "node:assert/strict";
import { shouldStopForDiez } from "./diezLimitStop.js";

test("no stop when bypassDiez committed, even at/over the limit", () => {
	assert.equal(shouldStopForDiez(150, true, false, 100), false);
});
test("no stop when skipDiez committed", () => {
	assert.equal(shouldStopForDiez(150, false, true, 100), false);
});
test("stop when neither flag and over the limit", () => {
	assert.equal(shouldStopForDiez(100, false, false, 100), true);
});
test("no stop below the limit", () => {
	assert.equal(shouldStopForDiez(99, false, false, 100), false);
});
