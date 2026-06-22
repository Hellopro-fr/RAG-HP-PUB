import { test } from "node:test";
import assert from "node:assert/strict";
import { routeDiezOutcome } from "./diezHookGate.js";

test("tier-2 ON: tier-1 outcomes activate engine, not commit", () => {
    for (const o of ["skipDiez", "bypassDiez", "promoteTier2"] as const) {
        assert.deepEqual(routeDiezOutcome(o, true), { action: "activate" });
    }
});
test("tier-2 ON: escalate defaults to bypass", () => {
    assert.deepEqual(routeDiezOutcome("escalate", true), { action: "commit", decision: "bypassDiez", source: "default" });
});
test("tier-2 OFF: tier-1 commits directly", () => {
    assert.deepEqual(routeDiezOutcome("skipDiez", false), { action: "commit", decision: "skipDiez", source: "tier1" });
    assert.deepEqual(routeDiezOutcome("bypassDiez", false), { action: "commit", decision: "bypassDiez", source: "tier1" });
});
test("tier-2 OFF: promoteTier2 is a no-op, escalate defaults", () => {
    assert.deepEqual(routeDiezOutcome("promoteTier2", false), { action: "noop" });
    assert.deepEqual(routeDiezOutcome("escalate", false), { action: "commit", decision: "bypassDiez", source: "default" });
});
test("null outcome is a no-op", () => {
    assert.deepEqual(routeDiezOutcome(null, true), { action: "noop" });
});
