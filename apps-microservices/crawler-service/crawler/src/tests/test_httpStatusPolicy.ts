// Unit tests for the pure HTTP status / navigation retry policy.
// This module is dependency-free, so we import the REAL production helpers
// directly (no hand-mirrored logic that can drift — cf. the C-3 note in
// test_routes.ts).

import {
    classifyHttpStatus,
    resolveNavigationWaitUntil,
    resolveTimeoutMaxRetries,
    shouldCapTimeoutRetry,
} from "../httpStatusPolicy.js";

let passed = 0;
let failed = 0;

function assertEqual<T>(actual: T, expected: T, label: string) {
    const a = JSON.stringify(actual);
    const e = JSON.stringify(expected);
    if (a === e) {
        passed++;
    } else {
        console.error(`FAIL [${label}]: got ${a}, expected ${e}`);
        failed++;
    }
}

// --- classifyHttpStatus ---
for (const s of [400, 401, 404, 405, 406, 410, 414, 423, 451, 501]) {
    assertEqual(classifyHttpStatus(s), "permanent", `classify ${s} → permanent`);
}
for (const s of [403, 429]) {
    assertEqual(classifyHttpStatus(s), "block", `classify ${s} → block`);
}
for (const s of [408, 425, 500, 502, 503, 504, 509, 521, 522, 523, 524, 525, 526]) {
    assertEqual(classifyHttpStatus(s), "transient", `classify ${s} → transient`);
}
for (const s of [200, 201, 204, 301, 302, 304, 418]) {
    assertEqual(classifyHttpStatus(s), "ok", `classify ${s} → ok`);
}

// --- resolveNavigationWaitUntil ---
assertEqual(resolveNavigationWaitUntil("load"), "load", "waitUntil load");
assertEqual(resolveNavigationWaitUntil("domcontentloaded"), "domcontentloaded", "waitUntil domcontentloaded");
assertEqual(resolveNavigationWaitUntil("networkidle"), "networkidle", "waitUntil networkidle");
assertEqual(resolveNavigationWaitUntil("commit"), "commit", "waitUntil commit");
assertEqual(resolveNavigationWaitUntil("DOMContentLoaded"), "domcontentloaded", "waitUntil case-insensitive");
assertEqual(resolveNavigationWaitUntil("  load  "), "load", "waitUntil trims");
assertEqual(resolveNavigationWaitUntil("bogus"), "domcontentloaded", "waitUntil invalid → default");
assertEqual(resolveNavigationWaitUntil(""), "domcontentloaded", "waitUntil empty → default");
assertEqual(resolveNavigationWaitUntil(undefined), "domcontentloaded", "waitUntil undefined → default");

// --- resolveTimeoutMaxRetries ---
assertEqual(resolveTimeoutMaxRetries("0"), 0, "cap 0");
assertEqual(resolveTimeoutMaxRetries("3"), 3, "cap 3");
assertEqual(resolveTimeoutMaxRetries("2.9"), 2, "cap floors");
assertEqual(resolveTimeoutMaxRetries("-1"), 2, "cap negative → default");
assertEqual(resolveTimeoutMaxRetries("abc"), 2, "cap invalid → default");
assertEqual(resolveTimeoutMaxRetries(undefined), 2, "cap undefined → default");

// --- shouldCapTimeoutRetry ---
assertEqual(shouldCapTimeoutRetry("Navigation timed out after 90 seconds", 2, 2), true, "timeout at cap → true");
assertEqual(shouldCapTimeoutRetry("Navigation timed out after 90 seconds", 3, 2), true, "timeout over cap → true");
assertEqual(shouldCapTimeoutRetry("TimeoutError: ...", 2, 2), true, "TimeoutError at cap → true");
assertEqual(shouldCapTimeoutRetry("Navigation timed out after 90 seconds", 1, 2), false, "timeout under cap → false");
assertEqual(shouldCapTimeoutRetry("net::ERR_NAME_NOT_RESOLVED", 5, 2), false, "non-timeout → false");

console.log(`\ntest_httpStatusPolicy: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
