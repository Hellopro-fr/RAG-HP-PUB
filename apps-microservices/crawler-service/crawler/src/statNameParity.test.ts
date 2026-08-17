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

/**
 * `_update_report.json` is consumed by script_process_update_crawling.php BY STRING KEY.
 * Nothing on either side type-checks the field names, and nothing else in this suite
 * exercises generateUpdateReport. A rename here is the same failure mode as
 * verdict_unavailable above, one boundary over: it LOOKS complete (tsc clean, suite
 * green) and goes silently inert on the PHP side. Renaming `previous_total` alone
 * takes out both percentage deletion caps (each gated on `previous_total_update > 0`)
 * AND makes the reconciliation gate pass unconditionally (`processed >= 0 * 0.8`).
 */
const reportLiteral = (functions: string) => {
    const start = functions.indexOf("const report = {");
    assert.ok(start !== -1, "generateUpdateReport must build a `report` object literal");
    return functions.slice(start, functions.indexOf("};", start));
};

test("generateUpdateReport: the seven field names the BO script reads are pinned", () => {
    const functions = src("functions.ts");
    const report = reportLiteral(functions);
    const metricsStart = report.indexOf("metrics: {");
    const metrics = report.slice(metricsStart, report.indexOf("}", metricsStart));

    assert.match(report, /\bhealth:\s*status,/, "report.health");
    assert.match(report, /\bmessage:\s*statusMessage,/, "report.message");
    assert.match(report, /\bredirect_rate:\s*parseFloat\(redirectRate\.toFixed\(4\)\),/, "report.rates.redirect_rate");
    assert.match(metrics, /^\s*redirects,\s*$/m, "report.metrics.redirects (shorthand key)");
    assert.match(metrics, /\bnew_urls:\s*newUrls,/, "report.metrics.new_urls");
    assert.match(metrics, /\bprevious_total:\s*cb\.previousTotal\b/, "report.metrics.previous_total");
    assert.match(metrics, /^\s*processed,\s*$/m, "report.metrics.processed (shorthand key)");
});

test("generateUpdateReport: the two fields a future BO consumer will depend on are pinned", () => {
    const report = reportLiteral(src("functions.ts"));

    assert.match(report, /\bmin_coverage:\s*cb\.minCoverage,/, "report.thresholds.min_coverage");
    assert.match(report, /\bdisabled_signals:\s*verdict\.disabledSignals\b/, "report.thresholds.disabled_signals");
});
