import { test } from "node:test";
import assert from "node:assert/strict";
import { context } from "./context.js";
import { qmConsumptionStrip, shouldSkipDequeued, recordQmCollapsed, skipnavCollapseTarget } from "./qmConsumptionSkip.js";
import { baseKeyAbsent } from "./urlBase.js";

const reset = () => {
    context.config.toRemove = ["q"]; context.config.toKeep = [];
    context.config.skipQuestionMark = false; context.config.skipDiez = false;
    context.qmCollapsed = [];
    context.qmCollapsedRejected = 0;
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

test("recordQmCollapsed carries origin and gate", () => {
    reset();
    recordQmCollapsed("https://x.fr/c?q=a", "https://x.fr/c", "qm_strip", "prenav");
    assert.deepEqual(context.qmCollapsed, [{
        collapsed: "https://x.fr/c?q=a", base: "https://x.fr/c", param: "q",
        origin: "qm_strip", gate: "prenav",
    }]);
});

test("recordQmCollapsed refuses a degenerate entry (base === collapsed)", () => {
    reset();
    recordQmCollapsed("https://x.fr/c", "https://x.fr/c", "filter_on_seen", "dequeue");
    assert.deepEqual(context.qmCollapsed, []);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("recordQmCollapsed folds the trailing slash before judging degeneracy", () => {
    reset();
    recordQmCollapsed("https://x.fr/c/", "https://x.fr/c", "filter_on_seen", "dequeue");
    assert.deepEqual(context.qmCollapsed, []);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("recordQmCollapsed admits filter_on_seen past the shared 200 cap (its own budget is 4000)", () => {
    reset();
    for (let i = 0; i < 205; i++) {
        recordQmCollapsed(`https://x.fr/c${i}?q=a`, `https://x.fr/c${i}`, "filter_on_seen", "enqueue");
    }
    assert.equal(context.qmCollapsed.length, 205);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("recordQmCollapsed refuses facet_cap at the shared 200 cap without moving truncated_by_cap's counter", () => {
    reset();
    for (let i = 0; i < 205; i++) {
        recordQmCollapsed(`https://x.fr/f${i}?a=1`, `https://x.fr/f${i}`, "facet_cap", "prenav");
    }
    assert.equal(context.qmCollapsed.length, 200);
    // The point of this test: a facet_cap refusal must NOT feed truncated_by_cap — only
    // filter_on_seen (the admitted channel) is allowed to move this counter.
    assert.equal(context.qmCollapsedRejected, 0);
});

test("recordQmCollapsed counts filter_on_seen rejections once its OWN 4000 cap is hit", () => {
    reset();
    for (let i = 0; i < 4005; i++) {
        recordQmCollapsed(`https://x.fr/s${i}?q=a`, `https://x.fr/s${i}`, "filter_on_seen", "enqueue");
    }
    assert.equal(context.qmCollapsed.filter((r) => r.origin === "filter_on_seen").length, 4000);
    assert.equal(context.qmCollapsedRejected, 5);
});

test("recordQmCollapsed caps facet_cap and qm_strip together under the SAME shared 200", () => {
    reset();
    for (let i = 0; i < 100; i++) {
        recordQmCollapsed(`https://x.fr/f${i}?a=1`, `https://x.fr/f${i}`, "facet_cap", "prenav");
    }
    for (let i = 0; i < 150; i++) {
        recordQmCollapsed(`https://x.fr/q${i}?a=1`, `https://x.fr/q${i}`, "qm_strip", "prenav");
    }
    // 100 facet_cap admitted + only 100 of 150 qm_strip admitted = 200 total (shared cap).
    assert.equal(context.qmCollapsed.length, 200);
    assert.equal(context.qmCollapsed.filter((r) => r.origin === "facet_cap").length, 100);
    assert.equal(context.qmCollapsed.filter((r) => r.origin === "qm_strip").length, 100);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("skipnavCollapseTarget: strip decides -> via qm_strip", () => {
    reset();
    const r = skipnavCollapseTarget("https://x.fr/c?q=a", new Set<string>());
    assert.deepEqual(r, { target: "https://x.fr/c", via: "qm_strip" });
});

test("skipnavCollapseTarget: seenBases decides -> via filter_on_seen", () => {
    reset();
    context.config.toRemove = [];              // le strip ne peut plus trancher
    const seen = new Set<string>([baseKeyAbsent("https://x.fr/c")]);
    const r = skipnavCollapseTarget("https://x.fr/c?cat=3", seen);
    assert.equal(r.via, "filter_on_seen");
    assert.ok(r.target.startsWith("https://x.fr/c"));
});

test("skipnavCollapseTarget: nothing decides -> via none, target unchanged", () => {
    reset();
    context.config.toRemove = [];
    const r = skipnavCollapseTarget("https://x.fr/c?cat=3", new Set<string>());
    assert.deepEqual(r, { target: "https://x.fr/c?cat=3", via: "none" });
});

test("skipnavCollapseTarget: live strip changes the URL -> stripped form", () => {
    reset();
    const r = skipnavCollapseTarget("https://x.fr/c?q=batterie&z=2", new Set());
    assert.equal(r.target, "https://x.fr/c?z=2");
});

test("skipnavCollapseTarget: strip no-op but filter-on-seen matches -> seen base", () => {
    reset();
    const seen = new Set<string>([ baseKeyAbsent("https://x.fr/c") ]);
    const r = skipnavCollapseTarget("https://x.fr/c?f_place=47", seen);
    assert.equal(r.target, baseKeyAbsent("https://x.fr/c"));
});

test("skipnavCollapseTarget: neither strip nor filter-on-seen -> url itself", () => {
    reset();
    const r = skipnavCollapseTarget("https://x.fr/c?f_place=47", new Set());
    assert.equal(r.target, "https://x.fr/c?f_place=47");
});
