import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

/**
 * R23 (2) — wiring parity of the non-HTML prefix gate.
 *
 * routes.ts (a Crawlee handler needing a live browser), functions.ts and main.ts are not
 * unit-testable here, and nothing type-checks that a counter written in one file is read by
 * name in another or that a hook sits on the right side of an anchor. Source-text assertions
 * on purpose (same stance as statNameParity.test.ts): exact literals, exact occurrence
 * counts, and ORDER at each anchor point. The gate's own logic is covered by
 * nonHtmlPrefixGate.test.ts.
 *
 * Counts run on the source with `//` comment lines blanked to equal length, so a comment that
 * quotes a literal cannot satisfy or break a count; offsets stay comparable with the raw
 * source, where the comment markers are read.
 */
const raw = (f: string) =>
    fs.readFileSync(path.join(import.meta.dirname, f), "utf-8");
const blankComments = (s: string) =>
    s.replace(/^[ \t]*\/\/.*$/gm, (m) => " ".repeat(m.length));
const count = (s: string, needle: string) => s.split(needle).length - 1;
const at = (s: string, needle: string): number => {
    const i = s.indexOf(needle);
    assert.notEqual(i, -1, `anchor not found: ${needle}`);
    return i;
};
const COUNTER_INC = 'increment("filtered_nonhtml")';
const NEG_CHECK = /!\s*context\.nonHtmlPrefix\.check\(/g;

function assertCounts(code: string, file: string, literals: Array<[string, number]>) {
    for (const [literal, expected] of literals) {
        assert.equal(
            count(code, literal),
            expected,
            `${file}: expected exactly ${expected} of ${literal}`,
        );
    }
}

test("routes.ts: C5 literals present the exact number of times (b1 + learning points)", () => {
    const code = blankComments(raw("routes.ts"));
    assertCounts(code, "routes.ts", [
        ['check(request.url, "enqueue")', 1],
        ["onNonHtml(request.url)", 1],
        [".onHtml(request.url)", 1],
        [COUNTER_INC, 1],
        ["context.nonHtmlPrefix?.onNonHtml(request.url);", 1],
        ["context.nonHtmlPrefix?.onHtml(request.url);", 1],
    ]);
    assert.match(
        code,
        /context\.nonHtmlPrefix\s*&&\s*!context\.nonHtmlPrefix\.check\(request\.url, "enqueue"\)/,
        "routes.ts: b1 must be guarded by context.nonHtmlPrefix (mode off = no-op)",
    );
});

test("functions.ts: C5 literals present the exact number of times (b3 + probe failure)", () => {
    const code = blankComments(raw("functions.ts"));
    assertCounts(code, "functions.ts", [
        ['check(request.url, "prenav")', 1],
        ["onProbeFailure(request.url)", 1],
        [COUNTER_INC, 1],
        ["context.nonHtmlPrefix?.onProbeFailure(request.url);", 1],
    ]);
    assert.match(
        code,
        /context\.nonHtmlPrefix\s*&&\s*!context\.nonHtmlPrefix\.check\(request\.url, "prenav"\)/,
        "functions.ts: b3 must be guarded by context.nonHtmlPrefix (mode off = no-op)",
    );
});

test("main.ts: C5 literals present the exact number of times (init, exemption, b2, counter)", () => {
    const code = blankComments(raw("main.ts"));
    assertCounts(code, "main.ts", [
        ['check(seedUrl, "seed")', 1],
        [COUNTER_INC, 1],
        ['readStat("filtered_nonhtml")', 1],
        ["context.nonHtmlPrefix?.addExempt(consolidatedUrl);", 1],
        ["context.nonHtmlPrefix.addExempt(seedUrl);", 1],
        ["context.nonHtmlPrefix.addExempt(site);", 1],
        ["new NonHtmlPrefixGate(", 1],
        ["resolveNonHtmlPrefixMode(process.env.NONHTML_PREFIX_MODE)", 1],
    ]);
    const i = at(code, 'check(seedUrl, "seed")');
    assert.match(
        code.slice(Math.max(0, i - 600), i),
        /if \(context\.nonHtmlPrefix\) \{/,
        "main.ts: b2 must sit under `if (context.nonHtmlPrefix) {` (mode off = no-op)",
    );
});

test("filtered_nonhtml: exactly one increment per file (b1, b2, b3) and one readStat", () => {
    const files = ["routes.ts", "functions.ts", "main.ts"];
    let total = 0;
    for (const f of files) {
        const n = count(blankComments(raw(f)), COUNTER_INC);
        assert.equal(n, 1, `${f}: expected exactly 1 ${COUNTER_INC}, got ${n}`);
        total += n;
    }
    assert.equal(total, 3, "three blocking points, three increments");
    assert.equal(
        count(blankComments(raw("main.ts")), 'readStat("filtered_nonhtml")'),
        1,
        "main.ts must read back the name the three points write",
    );
});

test("filtered_nonhtml: payload carries it only through the conditional spread (mode off = no key)", () => {
    const code = blankComments(raw("main.ts"));
    const spread = "...(context.nonHtmlPrefix ? { filtered_nonhtml } : {})";
    assert.equal(count(code, spread), 1, `main.ts: expected exactly 1 ${spread}`);
    assert.doesNotMatch(
        code,
        /^\s*filtered_nonhtml,\s*$/m,
        "main.ts: filtered_nonhtml must not appear as a bare payload key (mode off would carry it)",
    );
    assert.ok(
        at(code, 'readStat("filtered_nonhtml")') < at(code, spread),
        "main.ts: readStat must precede the payload that uses it",
    );
});

test("routes.ts: order at the anchors (learn before skip log, html before breaker, b1 between the two queue-purge blocks)", () => {
    const src = raw("routes.ts");
    const code = blankComments(src);
    assert.ok(
        at(code, "onNonHtml(request.url)") < at(src, "Skipping non-HTML response:"),
        "onNonHtml must precede the `Skipping non-HTML response:` log",
    );
    assert.ok(
        at(code, ".onHtml(request.url)") < at(src, "// --- Circuit Breaker Check (Dual-Mode) ---"),
        "onHtml must precede the circuit breaker block",
    );
    const b1 = at(code, 'check(request.url, "enqueue")');
    assert.ok(
        at(src, "// Queue-purge #1: facet cap") < b1 &&
            b1 < at(src, "// Queue-purge #2: filter-on-seen-base"),
        "b1 must sit between the facet cap block and the filter-on-seen-base block",
    );
});

test("functions.ts: order at the anchors (probe failure after the stale-variant branch, before the error log)", () => {
    const src = raw("functions.ts");
    const code = blankComments(src);
    const handler = at(src, "String(request.errorMessages).includes(STALE_VARIANT_SKIP_MARKER)");
    const probe = at(code, "onProbeFailure(request.url)");
    const errLog = at(src, "Request ${request.url} failed:");
    assert.ok(
        handler < probe && probe < errLog,
        "onProbeFailure must come after the STALE_VARIANT_SKIP_MARKER branch and before log.error(`Request … failed:`)",
    );
});

test("main.ts: order at the anchors (init after the sidecar guard, b2 check before the enqueue)", () => {
    const src = raw("main.ts");
    const code = blankComments(src);
    const sidecar = at(src, "ensureUnjudgedSidecar(domain);");
    assert.ok(
        sidecar < at(code, "resolveNonHtmlPrefixMode(process.env.NONHTML_PREFIX_MODE)") &&
            sidecar < at(code, "new NonHtmlPrefixGate("),
        "the gate must be initialised after ensureUnjudgedSidecar(domain);",
    );
    assert.ok(
        at(code, 'check(seedUrl, "seed")') < at(src, "uniqueKey: seedUrl"),
        "b2 must test the seed before it is enqueued with uniqueKey: seedUrl",
    );
});

test("filtered_nonhtml parity: every increment follows a negative check( within 500 chars, and counts match", () => {
    for (const f of ["routes.ts", "functions.ts", "main.ts"]) {
        const code = blankComments(raw(f));
        const negChecks = code.match(NEG_CHECK) ?? [];
        const incs = count(code, COUNTER_INC);
        assert.equal(
            negChecks.length,
            incs,
            `${f}: ${negChecks.length} negative check( vs ${incs} increments — a blocking point without its counter (or the reverse)`,
        );
        let from = 0;
        for (let k = 0; k < incs; k++) {
            const i = code.indexOf(COUNTER_INC, from);
            from = i + COUNTER_INC.length;
            const before = code.slice(Math.max(0, i - 500), i);
            assert.match(
                before,
                /!\s*context\.nonHtmlPrefix\.check\(/,
                `${f}: increment("filtered_nonhtml") outside a block that follows a negative check(`,
            );
        }
    }
});
