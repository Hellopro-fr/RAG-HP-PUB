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

/**
 * `errors_unprocessed` is the breaker's other denominator term (errorRateBreaker.ts). It has to
 * reach the report because crawler_manager.py forwards `metrics` wholesale into the BO webhook,
 * which is the only path by which the number that decided a stop survives the dataset being
 * archived — /admin/dataset returns 404 on an archived crawl, which is exactly how the
 * composition of `errors` became unmeasurable during this chantier.
 *
 * Pinned by name for the same reason as the fields above: the Python forwards, and the PHP reads,
 * BY STRING KEY. A rename is tsc-clean, suite-green, and silently inert downstream.
 */
test("generateUpdateReport: errors_unprocessed reaches report.metrics", () => {
    const functions = src("functions.ts");
    const report = reportLiteral(functions);
    const metricsStart = report.indexOf("metrics: {");
    const metrics = report.slice(metricsStart, report.indexOf("}", metricsStart));

    assert.match(
        metrics,
        /\berrors_unprocessed:\s*errorsUnprocessed\b/,
        "report.metrics.errors_unprocessed — without it the breaker's denominator is unreproducible once the dataset is archived",
    );
    assert.match(
        functions,
        /const\s+errorsUnprocessed\s*=\s*await[^;]*getValue\("errors_unprocessed"\)/,
        "the reported value must come from the counter itself, not from a literal or a stale local",
    );
});

/**
 * Two different formulas must not answer to one grep.
 *
 * errorRateBreaker.ts divides by `processed + errors_unprocessed`; updateHealthVerdict.ts still
 * divides by `processed` alone (deliberate — correcting it would loosen CRITICAL and so apply MORE
 * destructive actions; see §8.1 of the design spec). Production logs are grepped by message text,
 * and the 69-run measurement that justified the whole chantier was taken that way. If the two
 * messages ever share a prefix again, that grep silently mixes the two formulas and the next
 * measurement is wrong in a way nobody can see.
 */
test("the breaker and the health verdict do not share a message prefix", () => {
    const breaker = src("errorRateBreaker.ts");
    const verdict = src("updateHealthVerdict.ts");

    assert.ok(
        breaker.includes("Error rate too high ("),
        "errorRateBreaker.ts must keep its grepped prefix — the historical measurement depends on it",
    );

    // Anchored to the EMITTED strings, not to the file text. A whole-file search is satisfied — or,
    // as happened when this test was written, broken — by any comment that merely quotes the
    // forbidden wording. The first draft searched the file and went red on its own explanatory
    // comment: same unanchored-match defect this suite exists to catch, one file over.
    const emitted = verdict.match(/statusMessage = `[^`]*`/g) ?? [];
    assert.ok(
        emitted.length >= 3,
        `expected the verdict's statusMessage assignments to be found, got ${emitted.length}`,
    );
    for (const message of emitted) {
        assert.ok(
            !/error rate too high \(/i.test(message),
            `updateHealthVerdict.ts must not emit the breaker's wording (case-insensitive) — it still divides by \`processed\` alone: ${message}`,
        );
    }
});
