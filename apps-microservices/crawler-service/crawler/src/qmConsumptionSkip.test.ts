import { test } from "node:test";
import assert from "node:assert/strict";
import { context } from "./context.js";
import { qmConsumptionStrip, shouldSkipDequeued, recordQmCollapsed, skipnavCollapseTarget } from "./qmConsumptionSkip.js";
import { baseKeyAbsent } from "./urlBase.js";

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

test("skipnavCollapseTarget: live strip changes the URL -> stripped form", () => {
    reset();
    assert.equal(skipnavCollapseTarget("https://x.fr/c?q=batterie&z=2", new Set()), "https://x.fr/c?z=2");
});

test("skipnavCollapseTarget: strip no-op but filter-on-seen matches -> seen base", () => {
    reset();
    const seen = new Set<string>([ baseKeyAbsent("https://x.fr/c") ]);
    assert.equal(skipnavCollapseTarget("https://x.fr/c?f_place=47", seen), baseKeyAbsent("https://x.fr/c"));
});

test("skipnavCollapseTarget: neither strip nor filter-on-seen -> url itself", () => {
    reset();
    assert.equal(skipnavCollapseTarget("https://x.fr/c?f_place=47", new Set()), "https://x.fr/c?f_place=47");
});
