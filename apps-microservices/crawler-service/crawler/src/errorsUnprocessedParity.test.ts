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

    // Reading the counter is not enough — it must reach the breaker call itself.
    // Substituting errorsUnprocessed: 0 (or dropping the field) at the call site
    // reverts the denominator to `processed` and leaves the suite green, because
    // `npm test` runs tsx (transpile-only); only `npm run build` type-checks.
    assert.match(
        routes,
        /\{ errors, processed, errorsUnprocessed \}/,
        'routes.ts must pass errorsUnprocessed INTO the breaker — reading it and not passing it reverts the denominator to `processed`, and tsx does not type-check',
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
