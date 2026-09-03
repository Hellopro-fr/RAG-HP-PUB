import { test } from "node:test";
import assert from "node:assert/strict";
import { context } from "./context.js";
import { qmConsumptionStrip, shouldSkipDequeued, recordQmCollapsed, skipnavCollapseTarget, resetQmCollapsedState } from "./qmConsumptionSkip.js";
import { baseKeyAbsent } from "./urlBase.js";

const reset = () => {
    context.config.toRemove = ["q"]; context.config.toKeep = [];
    context.config.skipQuestionMark = false; context.config.skipDiez = false;
    // One call, not three assignments: the row array and the two dedup maps must move
    // together. Emptying the array alone would leave the maps holding keys, and every later
    // record of those pairs would be silently dropped — several tests below reuse the same
    // URLs, so that leak would show up as unrelated failures.
    resetQmCollapsedState();
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

// ─────────────────────────────────────────────────────────────────────────────
// The cap bounds a POPULATION, not a call count (measured 2026-09-02)
// ─────────────────────────────────────────────────────────────────────────────
// `filter_on_seen` is recorded from three sites, one of them inside the enqueue loop, so a
// parameterised link in a nav menu is recorded once per crawled page. Before this change the
// 4000 budget filled with repeats and every further call declared a truncation to the BO,
// which then shut the whole destructive phase of the run.
//
// FIVE of the nine below fail on the pre-change cap logic — measured by restoring it and
// re-running, not asserted. The other four pass both ways by construction and are guards, not
// discriminators: the cap still refusing a genuinely new pair (a fix that merely stopped
// counting would satisfy every other assertion here), the two classes not sharing a map,
// facet_cap repeats not starving the admitted budget, and the reset clearing the maps. The 19
// pre-existing tests in this file pass unchanged, which is the non-regression measurement.

test("a repeat of the same pair takes no slot and declares no truncation", () => {
    reset();
    for (let i = 0; i < 500; i++) {
        recordQmCollapsed("https://x.fr/p?q=a", "https://x.fr/p", "filter_on_seen", "enqueue");
    }
    assert.equal(context.qmCollapsed.length, 1);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("the trailing slash is folded in the dedup key too, not only in the degeneracy test", () => {
    reset();
    recordQmCollapsed("https://x.fr/p?q=a", "https://x.fr/p", "filter_on_seen", "enqueue");
    recordQmCollapsed("https://x.fr/p?q=a/", "https://x.fr/p/", "filter_on_seen", "prenav");
    assert.equal(context.qmCollapsed.length, 1);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("a repeat arriving AFTER the cap is full still declares no truncation", () => {
    // THE defect. Order matters: dedup is tested before the cap, so a pair already recorded
    // cannot report a truncation the population never suffered. Reversed, this asserts 0
    // against a counter that would read 500.
    reset();
    for (let i = 0; i < 4000; i++) {
        recordQmCollapsed(`https://x.fr/s${i}?q=a`, `https://x.fr/s${i}`, "filter_on_seen", "enqueue");
    }
    assert.equal(context.qmCollapsedRejected, 0);
    for (let i = 0; i < 500; i++) {
        recordQmCollapsed("https://x.fr/s0?q=a", "https://x.fr/s0", "filter_on_seen", "enqueue");
    }
    assert.equal(context.qmCollapsed.length, 4000);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("tools-trails.com shape: 4 distinct pairs recorded thousands of times", () => {
    // Measured run of 2026-09-01: 45,662 records, 4 distinct pairs, and the BO was told
    // 41,662 lines had been truncated. Scaled down; the ratio is what this pins.
    reset();
    for (let page = 0; page < 1000; page++) {
        for (let link = 0; link < 4; link++) {
            recordQmCollapsed(`https://tt.com/c${link}?utm=x`, `https://tt.com/c${link}`, "filter_on_seen", "enqueue");
        }
    }
    assert.equal(context.qmCollapsed.length, 4);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("a genuinely new pair beyond the cap IS still refused and counted", () => {
    // Non-regression on the cap itself: deduping must not disarm it. Without this, a fix that
    // simply stopped counting would pass every assertion above.
    reset();
    for (let i = 0; i < 4005; i++) {
        recordQmCollapsed(`https://x.fr/n${i}?q=a`, `https://x.fr/n${i}`, "filter_on_seen", "enqueue");
    }
    assert.equal(context.qmCollapsed.length, 4000);
    assert.equal(context.qmCollapsedRejected, 5);
});

test("the two cap classes keep independent dedup budgets", () => {
    reset();
    // Same path in both classes: if one shared map backed both, the second call would be
    // deduped away and the array would hold 1 row instead of 2.
    recordQmCollapsed("https://x.fr/d?q=a", "https://x.fr/d", "filter_on_seen", "enqueue");
    recordQmCollapsed("https://x.fr/d?q=a", "https://x.fr/d", "facet_cap", "prenav");
    assert.equal(context.qmCollapsed.length, 2);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("facet_cap repeats do not starve the seen-base budget", () => {
    reset();
    for (let i = 0; i < 5000; i++) {
        recordQmCollapsed("https://x.fr/f?a=1", "https://x.fr/f", "facet_cap", "prenav");
    }
    recordQmCollapsed("https://x.fr/keep?q=a", "https://x.fr/keep", "filter_on_seen", "enqueue");
    assert.equal(context.qmCollapsed.filter((r) => r.origin === "filter_on_seen").length, 1);
    assert.equal(context.qmCollapsedRejected, 0);
});

test("the dedup maps stay in step with the rows they admitted", () => {
    // The invariant the O(1) cap read rests on. A drift here makes the cap judge the wrong
    // population, in either direction.
    reset();
    for (let i = 0; i < 50; i++) {
        recordQmCollapsed(`https://x.fr/i${i % 10}?q=a`, `https://x.fr/i${i % 10}`, "filter_on_seen", "enqueue");
        recordQmCollapsed(`https://x.fr/j${i % 7}?a=1`, `https://x.fr/j${i % 7}`, "facet_cap", "prenav");
    }
    assert.equal(context.qmCollapsedSeenKeys.size,
        context.qmCollapsed.filter((r) => r.origin === "filter_on_seen").length);
    assert.equal(context.qmCollapsedOtherKeys.size,
        context.qmCollapsed.filter((r) => r.origin !== "filter_on_seen").length);
    assert.equal(context.qmCollapsedSeenKeys.size, 10);
    assert.equal(context.qmCollapsedOtherKeys.size, 7);
});

test("resetQmCollapsedState clears the maps, not only the rows", () => {
    // Without this, the partial-reset trap comes back the moment someone inlines the reset.
    reset();
    recordQmCollapsed("https://x.fr/r?q=a", "https://x.fr/r", "filter_on_seen", "enqueue");
    resetQmCollapsedState();
    recordQmCollapsed("https://x.fr/r?q=a", "https://x.fr/r", "filter_on_seen", "enqueue");
    assert.equal(context.qmCollapsed.length, 1);
    assert.equal(context.qmCollapsedSeenKeys.size, 1);
});
