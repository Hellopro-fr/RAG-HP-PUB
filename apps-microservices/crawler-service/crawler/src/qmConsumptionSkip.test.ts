import { test } from "node:test";
import assert from "node:assert/strict";
import { context } from "./context.js";
import { qmConsumptionStrip, shouldSkipDequeued, recordQmCollapsed } from "./qmConsumptionSkip.js";

const reset = () => {
    context.config.toRemove = ["q"]; context.config.toKeep = [];
    context.config.skipQuestionMark = false; context.config.skipDiez = false;
    context.qmCollapsed = [];
};

test("qmConsumptionStrip removes committed toRemove param", () => {
    reset();
    assert.equal(qmConsumptionStrip("https://x.fr/c?q=batterie&z=2"), "https://x.fr/c?z=2");
});

test("shouldSkipDequeued: stripped + already-seen base -> skip", () => {
    reset();
    assert.equal(shouldSkipDequeued("https://x.fr/c?q=a", "https://x.fr/c", true), true);
    assert.equal(shouldSkipDequeued("https://x.fr/c?q=a", "https://x.fr/c", false), false);
    assert.equal(shouldSkipDequeued("https://x.fr/c", "https://x.fr/c", true), false);
});

test("recordQmCollapsed pushes capped candidate with param", () => {
    reset();
    recordQmCollapsed("https://x.fr/c?q=a", "https://x.fr/c");
    assert.deepEqual(context.qmCollapsed, [{ collapsed: "https://x.fr/c?q=a", base: "https://x.fr/c", param: "q" }]);
});
