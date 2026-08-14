import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

/**
 * `verdict_unavailable` is written in routes.ts and read back in main.ts by NAME, through a
 * Redis hash — nothing type-checks that the two literals agree. A typo on either side leaves
 * a counter that increments into one field and a payload that reads a permanently-absent
 * other, i.e. a fix that LOOKS complete and reports 0 forever. That is the exact failure mode
 * this chantier exists to close, so it gets pinned rather than trusted.
 *
 * Source-text assertions on purpose: neither routes.ts (a Crawlee handler needing a live
 * browser) nor main.ts (the entry point) is unit-testable here, and fabricating a fake handler
 * would only prove the fake agrees with itself. Three anchors, three independent directions of
 * failure: the increment, the readStat, and the payload key.
 */
const src = (f: string) =>
    fs.readFileSync(path.join(import.meta.dirname, f), "utf-8");

test("verdict_unavailable: routes.ts increments the name main.ts reads", () => {
    const routes = src("routes.ts");
    const main = src("main.ts");

    assert.ok(
        routes.includes('increment("verdict_unavailable")'),
        'routes.ts must increment "verdict_unavailable" — without it the counter is always 0',
    );
    assert.ok(
        main.includes('readStat("verdict_unavailable")'),
        'main.ts must readStat("verdict_unavailable") — a name mismatch reads a field nobody writes',
    );
    assert.match(
        main,
        /^\s*verdict_unavailable,\s*$/m,
        "main.ts must put verdict_unavailable in the webhook payload — a counter that never leaves Redis is inert",
    );
});

test("verdict_unavailable is counted on the convergence branch, not on `errors`", () => {
    const routes = src("routes.ts");

    // One increment, so all ten verdictUnavailable sites are covered exactly once.
    const increments = routes.match(/increment\("verdict_unavailable"\)/g) ?? [];
    assert.equal(
        increments.length,
        1,
        "expected exactly one increment site (the `else if (verdictUnavailable)` convergence branch)",
    );

    // It must sit inside that branch, ahead of recordUnjudgedUrls, and after the not-French
    // `else` nothing may increment it — `errors` stays untouched by this path (spec §7).
    const branch = routes.indexOf("} else if (verdictUnavailable) {");
    const increment = routes.indexOf('increment("verdict_unavailable")');
    const notFrenchElse = routes.indexOf('increment("filtered_nonfr")');
    assert.ok(branch !== -1, "the verdictUnavailable convergence branch must still exist");
    assert.ok(
        branch < increment && increment < notFrenchElse,
        "the increment must live in the verdictUnavailable branch, before the not-French else",
    );

    // Scoped to the branch, NOT the whole file: routes.ts:408 legitimately increments
    // `errors` on a permanent HTTP status for an existing URL. A file-wide assertion here was
    // written and observed failing on that pre-existing call — the wrong claim, caught by
    // running it.
    assert.ok(
        !routes.slice(branch, notFrenchElse).includes('increment("errors")'),
        "this branch must never touch `errors`: it feeds the BO health guard and both deletion caps",
    );
});
