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

import { isUnreconciledIdle, resolveDrainDiskRecount } from "./drainGuard.js";

test("isUnreconciledIdle: true for the 0/0/1 counter wedge (crawl 6599)", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 1 }), true);
});
test("isUnreconciledIdle: false when counts reconcile at idle", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 174, totalRequestCount: 174 }), false);
});
test("isUnreconciledIdle: false while a task is running (concurrency > 0)", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 1, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 1 }), false);
});
test("isUnreconciledIdle: false at pre-dispatch start (total 0)", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 0 }), false);
});
test("resolveDrainDiskRecount: default-on; only 'false' disables", () => {
    assert.equal(resolveDrainDiskRecount(undefined), true);
    assert.equal(resolveDrainDiskRecount(""), true);
    assert.equal(resolveDrainDiskRecount("true"), true);
    assert.equal(resolveDrainDiskRecount("FALSE"), false);
    assert.equal(resolveDrainDiskRecount(" false "), false);
});
