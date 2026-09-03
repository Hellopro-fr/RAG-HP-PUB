import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

/**
 * `errors_unprocessed` is written in UpdateChecker.ts and read back in
 * routes.ts by NAME, through a Redis hash — nothing type-checks that the two
 * literals agree. This file pins both sides.
 *
 * Source-text assertions on purpose: UpdateChecker's CASE 1 needs a live
 * StatsManager; a fake would only prove the fake agrees with itself.
 *
 * ⚠ Still source-text, not a data-flow proof. The patterns below close the
 * two defeats found in adversarial review (a renamed/nulled read, and an
 * unanchored decoy match) — they do not execute routes.ts or trace
 * `errorsUnprocessed` through a real request. A proof-grade version would
 * need the three counters (`errors`, `processed`, `errorsUnprocessed`)
 * threaded through a testable seam that routes.ts calls into instead of
 * computing inline — a design change, out of scope here.
 */
const src = (f: string) => fs.readFileSync(path.join(import.meta.dirname, f), "utf-8");

test("errors_unprocessed: UpdateChecker writes the name the breaker will read", () => {
    const checker = src("class/UpdateChecker.ts");

    assert.ok(
        checker.includes('increment("errors_unprocessed")'),
        'UpdateChecker.ts must increment "errors_unprocessed" — without it the denominator is `processed` again',
    );

    const routes = src("routes.ts");
    assert.ok(
        routes.includes('getValue("errors_unprocessed")'),
        'routes.ts must getValue("errors_unprocessed") — a name mismatch reads a field nobody writes, i.e. a denominator silently back to `processed`',
    );

    // Reading the counter is not enough — it must actually reach the breaker
    // call. Two defeats surfaced in review: (A) rename the read and hardcode
    // the value (`const errorsUnprocessedRead = await …; const errorsUnprocessed = 0;`)
    // — tsconfig.json sets noUnusedLocals: false, so even `npm run build`
    // misses the orphaned binding, not just `npm test`'s transpile-only tsx;
    // (B) an unanchored regex satisfied by any decoy occurrence of the object
    // shape (a comment, or an unrelated destructure) — worse, a future helper
    // that omits the field would turn `attempts` into NaN and silently stop
    // the breaker from ever tripping, a louder bug an unanchored match is
    // equally blind to. The two assertions below close both: the first is
    // anchored to the actual call site and rejects a value substitution
    // (`errorsUnprocessed:` fails to match); the second requires the bound
    // name to resolve to the Redis read, not a hardcoded literal.
    assert.match(
        routes,
        /shouldTripErrorRateBreaker\(\s*\{[^}]*\berrorsUnprocessed\b\s*[,}]/s,
        'routes.ts must pass errorsUnprocessed as a property INTO the shouldTripErrorRateBreaker(...) call — reading the counter and not forwarding it (or substituting a value) reverts the denominator to `processed`',
    );
    assert.match(
        routes,
        /const\s+errorsUnprocessed\s*=\s*await[^;]*getValue\("errors_unprocessed"\)/,
        'the errorsUnprocessed binding passed to the breaker must itself resolve to context.statsManager.getValue("errors_unprocessed") — a renamed read paired with a hardcoded errorsUnprocessed would pass the call-site assertion alone and defeat the parity fix',
    );
});

test("errors_unprocessed is written ONCE, on the HTTP-error branch only", () => {
    const checker = src("class/UpdateChecker.ts");

    const increments = checker.match(/increment\("errors_unprocessed"\)/g) ?? [];
    assert.equal(
        increments.length,
        1,
        "expected exactly one increment site — CASE 3 (2xx not_eligible) is already inside `processed`",
    );

    // It must sit in CASE 1 (isHttpError), i.e. before CASE 3's own errors++.
    const case3 = checker.indexOf("CASE 3: Success");
    const increment = checker.indexOf('increment("errors_unprocessed")');
    assert.ok(case3 !== -1, "the CASE 3 marker comment must still exist");
    assert.ok(
        increment < case3,
        "the increment must live in CASE 1 (HTTP error), which throws before increment(\"processed\")",
    );
});

test("`errors` keeps exactly its two live writers in UpdateChecker", () => {
    const checker = src("class/UpdateChecker.ts");
    const increments = checker.match(/increment\("errors"\)/g) ?? [];
    assert.equal(
        increments.length,
        2,
        "`errors` feeds the BO health guard and both deletion caps — this lot must not change its count",
    );
});
