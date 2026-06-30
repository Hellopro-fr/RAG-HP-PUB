import { test } from "node:test";
import assert from "node:assert/strict";
import { isDrainedSample, DRAIN_CONFIRM_SAMPLES } from "./drainGuard.js";

const base = { currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 174, totalRequestCount: 174 };

test("isDrainedSample: fires on idle + pending 0 + handled===total>0", () => {
    assert.equal(isDrainedSample(base), true);
});
test("isDrainedSample: not drained when a task is running", () => {
    assert.equal(isDrainedSample({ ...base, currentConcurrency: 1 }), false);
});
test("isDrainedSample: not drained when pending > 0 (slow/paused crawl)", () => {
    assert.equal(isDrainedSample({ ...base, pendingRequestCount: 2, handledRequestCount: 172 }), false);
});
test("isDrainedSample: not drained at pre-dispatch start (total 0)", () => {
    assert.equal(isDrainedSample({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 0 }), false);
});
test("isDrainedSample: not drained on count drift (handled !== total)", () => {
    assert.equal(isDrainedSample({ ...base, handledRequestCount: 173 }), false);
});
test("DRAIN_CONFIRM_SAMPLES is a positive integer", () => {
    assert.ok(Number.isInteger(DRAIN_CONFIRM_SAMPLES) && DRAIN_CONFIRM_SAMPLES > 0);
});
