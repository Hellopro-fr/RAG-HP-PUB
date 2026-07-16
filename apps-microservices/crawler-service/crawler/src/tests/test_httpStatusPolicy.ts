// Unit tests for the pure HTTP status / navigation retry policy.
// This module is dependency-free, so we import the REAL production helpers
// directly (no hand-mirrored logic that can drift — cf. the C-3 note in
// test_routes.ts).

import {
    classifyHttpStatus,
    resolveNavigationWaitUntil,
    resolveTimeoutMaxRetries,
    shouldCapTimeoutRetry,
    classifyFailure,
    isRecoverableFailureClass,
    selectReclaimableIds,
    resolveRecoverFailedOnRestart,
    shouldRunRecovery,
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

// --- classifyFailure: permanent error markers (win over everything) ---
for (const e of [
    "page.goto: net::ERR_NAME_NOT_RESOLVED",
    "ERR_CERT_DATE_INVALID at ...",
    "ERR_SSL_PROTOCOL_ERROR",
    "ERR_TOO_MANY_REDIRECTS",
    "Download is starting",
    "page.goto: net::ERR_ABORTED",
    "Execution context was destroyed",
]) {
    assertEqual(classifyFailure(e), "permanent", `classifyFailure permanent: ${e.slice(0, 24)}`);
}
assertEqual(classifyFailure("net::ERR_NAME_NOT_RESOLVED", 503), "permanent", "permanent marker > status");

// --- classifyFailure: infra (transport/proxy) markers ---
for (const e of [
    "page.goto: NS_ERROR_PROXY_CONNECTION_REFUSED",
    "NS_ERROR_CONNECTION_REFUSED",
    "NS_ERROR_NET_RESET",
    "connect ECONNREFUSED 1.2.3.4:8080",
    "read ECONNRESET",
    "connect ETIMEDOUT",
    "socket hang up",
]) {
    assertEqual(classifyFailure(e), "infra", `classifyFailure infra: ${e.slice(0, 24)}`);
}
assertEqual(classifyFailure("NS_ERROR_PROXY_CONNECTION_REFUSED", 404), "infra", "infra marker > status");

// --- classifyFailure: status-driven ---
assertEqual(classifyFailure("HTTP 404", 404), "permanent", "status 404 → permanent");
assertEqual(classifyFailure("HTTP 410", 410), "permanent", "status 410 → permanent");
assertEqual(classifyFailure("HTTP 503", 503), "transient", "status 503 → transient");
assertEqual(classifyFailure("HTTP 429", 429), "transient", "status 429 (block) → transient-recoverable");

// --- classifyFailure: nav-timeout (no status) ---
assertEqual(classifyFailure("Navigation timed out after 90 seconds"), "transient", "nav timeout → transient");
assertEqual(classifyFailure("TimeoutError: ..."), "transient", "TimeoutError → transient");

// --- classifyFailure: unknown ---
assertEqual(classifyFailure("page.goto: NS_ERROR_ABORT"), "unknown", "NS_ERROR_ABORT → unknown (ambiguous)");
assertEqual(classifyFailure("browserController.newPage() failed: abc"), "unknown", "newPage fail → unknown");
assertEqual(classifyFailure("some weird error", 0), "unknown", "gibberish → unknown");

// --- isRecoverableFailureClass ---
assertEqual(isRecoverableFailureClass("infra"), true, "infra recoverable");
assertEqual(isRecoverableFailureClass("transient"), true, "transient recoverable");
assertEqual(isRecoverableFailureClass("permanent"), false, "permanent not recoverable");
assertEqual(isRecoverableFailureClass("unknown"), false, "unknown not recoverable");

// --- selectReclaimableIds ---
const sel = selectReclaimableIds([
    { id: "a", failure_class: "infra" },
    { id: "b", failure_class: "transient" },
    { id: "c", failure_class: "permanent" },
    { id: "d", failure_class: "unknown" },
    { id: "e" },                       // legacy: missing class → recoverable
    { failure_class: "infra" },        // no id → ignored
]);
assertEqual(sel.reclaim, ["a", "b", "e"], "selectReclaimableIds picks recoverable + legacy");
assertEqual(sel.skippedPermanent, 2, "selectReclaimableIds counts permanent+unknown skips");

// --- resolveRecoverFailedOnRestart ---
assertEqual(resolveRecoverFailedOnRestart(undefined), true, "recover default true");
assertEqual(resolveRecoverFailedOnRestart(""), true, "recover empty → true");
assertEqual(resolveRecoverFailedOnRestart("true"), true, "recover true");
assertEqual(resolveRecoverFailedOnRestart("false"), false, "recover false");
assertEqual(resolveRecoverFailedOnRestart("FALSE"), false, "recover FALSE → false");
assertEqual(resolveRecoverFailedOnRestart("  false  "), false, "recover trims");

// --- shouldRunRecovery ---
assertEqual(shouldRunRecovery(true, "update"), true, "recovery on update");
assertEqual(shouldRunRecovery(true, ""), true, "recovery on standard");
assertEqual(shouldRunRecovery(true, "sitemap"), false, "no recovery on sitemap");
assertEqual(shouldRunRecovery(true, "generate_data"), false, "no recovery on generate_data");
assertEqual(shouldRunRecovery(false, "update"), false, "flag off → no recovery");

console.log(`\ntest_httpStatusPolicy: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
