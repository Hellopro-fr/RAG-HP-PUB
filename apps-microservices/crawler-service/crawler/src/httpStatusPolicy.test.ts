import { test } from "node:test";
import assert from "node:assert/strict";
import {
    classifyHttpStatus,
    resolveNavigationWaitUntil,
    resolveTimeoutMaxRetries,
    resolveMaxConcurrency,
    resolveRequestHandlerTimeoutSecs,
    resolveBackpressureMaxPending,
    shouldAcceptNewPage,
    shouldCapTimeoutRetry,
    classifyFailure,
    isRecoverableFailureClass,
    selectReclaimableIds,
    resolveRecoverFailedOnRestart,
    shouldRunRecovery,
    isDownloadError,
    isPageClosedError,
    resolveSkipDownloads,
    shouldSkipAsDownload,
    resolveStallCountResolved,
} from "./httpStatusPolicy.js";

// ---------------------------------------------------------------------------
// classifyHttpStatus
// ---------------------------------------------------------------------------
test("classifyHttpStatus: permanent statuses", () => {
    assert.equal(classifyHttpStatus(400), "permanent");
    assert.equal(classifyHttpStatus(404), "permanent");
    assert.equal(classifyHttpStatus(410), "permanent");
});

test("classifyHttpStatus: block statuses", () => {
    assert.equal(classifyHttpStatus(403), "block");
    assert.equal(classifyHttpStatus(429), "block");
});

test("classifyHttpStatus: transient statuses", () => {
    assert.equal(classifyHttpStatus(500), "transient");
    assert.equal(classifyHttpStatus(503), "transient");
});

test("classifyHttpStatus: ok for 2xx and unlisted", () => {
    assert.equal(classifyHttpStatus(200), "ok");
    assert.equal(classifyHttpStatus(301), "ok");
    assert.equal(classifyHttpStatus(999), "ok");
});

// ---------------------------------------------------------------------------
// resolveNavigationWaitUntil
// ---------------------------------------------------------------------------
test("resolveNavigationWaitUntil: valid values pass through", () => {
    assert.equal(resolveNavigationWaitUntil("load"), "load");
    assert.equal(resolveNavigationWaitUntil("networkidle"), "networkidle");
    assert.equal(resolveNavigationWaitUntil("commit"), "commit");
    assert.equal(resolveNavigationWaitUntil("domcontentloaded"), "domcontentloaded");
});

test("resolveNavigationWaitUntil: invalid/empty → domcontentloaded", () => {
    assert.equal(resolveNavigationWaitUntil(undefined), "domcontentloaded");
    assert.equal(resolveNavigationWaitUntil(""), "domcontentloaded");
    assert.equal(resolveNavigationWaitUntil("bogus"), "domcontentloaded");
});

// ---------------------------------------------------------------------------
// resolveTimeoutMaxRetries
// ---------------------------------------------------------------------------
test("resolveTimeoutMaxRetries: valid non-negative int", () => {
    assert.equal(resolveTimeoutMaxRetries("0"), 0);
    assert.equal(resolveTimeoutMaxRetries("5"), 5);
});

test("resolveTimeoutMaxRetries: invalid → 2", () => {
    assert.equal(resolveTimeoutMaxRetries(undefined), 2);
    assert.equal(resolveTimeoutMaxRetries("abc"), 2);
    assert.equal(resolveTimeoutMaxRetries("-1"), 2);
    // Note: "" coerces to 0 via Number(""), which is a valid non-negative int → returns 0
    assert.equal(resolveTimeoutMaxRetries(""), 0);
});

// ---------------------------------------------------------------------------
// resolveMaxConcurrency
// ---------------------------------------------------------------------------
test("resolveMaxConcurrency: valid positive int", () => {
    assert.equal(resolveMaxConcurrency("10"), 10);
    assert.equal(resolveMaxConcurrency("1"), 1);
});

test("resolveMaxConcurrency: invalid/zero → 20", () => {
    assert.equal(resolveMaxConcurrency(undefined), 20);
    assert.equal(resolveMaxConcurrency("0"), 20);
    assert.equal(resolveMaxConcurrency("abc"), 20);
});

// ---------------------------------------------------------------------------
// resolveRequestHandlerTimeoutSecs
// ---------------------------------------------------------------------------
test("resolveRequestHandlerTimeoutSecs: valid", () => {
    assert.equal(resolveRequestHandlerTimeoutSecs("300"), 300);
});

test("resolveRequestHandlerTimeoutSecs: invalid → 200", () => {
    assert.equal(resolveRequestHandlerTimeoutSecs(undefined), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs("0"), 200);
});

// ---------------------------------------------------------------------------
// resolveBackpressureMaxPending
// ---------------------------------------------------------------------------
test("resolveBackpressureMaxPending: valid including 0", () => {
    assert.equal(resolveBackpressureMaxPending("0"), 0);
    assert.equal(resolveBackpressureMaxPending("10"), 10);
});

test("resolveBackpressureMaxPending: invalid → 5", () => {
    assert.equal(resolveBackpressureMaxPending(undefined), 5);
    assert.equal(resolveBackpressureMaxPending(""), 5);
    assert.equal(resolveBackpressureMaxPending("abc"), 5);
});

// ---------------------------------------------------------------------------
// shouldAcceptNewPage
// ---------------------------------------------------------------------------
test("shouldAcceptNewPage: accept when pending <= threshold", () => {
    assert.equal(shouldAcceptNewPage(3, 5), true);
    assert.equal(shouldAcceptNewPage(5, 5), true);
    assert.equal(shouldAcceptNewPage(6, 5), false);
});

// ---------------------------------------------------------------------------
// shouldCapTimeoutRetry
// ---------------------------------------------------------------------------
test("shouldCapTimeoutRetry: caps on nav timeout at/above cap", () => {
    assert.equal(shouldCapTimeoutRetry("Navigation timed out", 2, 2), true);
    assert.equal(shouldCapTimeoutRetry("Navigation timed out", 3, 2), true);
    assert.equal(shouldCapTimeoutRetry("Navigation timed out", 1, 2), false);
    assert.equal(shouldCapTimeoutRetry("other error", 5, 2), false);
});

// ---------------------------------------------------------------------------
// classifyFailure
// ---------------------------------------------------------------------------
test("classifyFailure: permanent marker", () => {
    assert.equal(classifyFailure("ERR_NAME_NOT_RESOLVED"), "permanent");
});

test("classifyFailure: infra marker", () => {
    assert.equal(classifyFailure("ECONNREFUSED"), "infra");
});

test("classifyFailure: timeout → transient", () => {
    assert.equal(classifyFailure("Navigation timed out"), "transient");
});

test("classifyFailure: unknown by default", () => {
    assert.equal(classifyFailure("some random error"), "unknown");
});

// ---------------------------------------------------------------------------
// isRecoverableFailureClass
// ---------------------------------------------------------------------------
test("isRecoverableFailureClass: infra/transient recoverable", () => {
    assert.equal(isRecoverableFailureClass("infra"), true);
    assert.equal(isRecoverableFailureClass("transient"), true);
    assert.equal(isRecoverableFailureClass("permanent"), false);
    assert.equal(isRecoverableFailureClass("unknown"), false);
});

// ---------------------------------------------------------------------------
// selectReclaimableIds
// ---------------------------------------------------------------------------
test("selectReclaimableIds: reclaims infra/transient/missing class, skips permanent/unknown", () => {
    const result = selectReclaimableIds([
        { id: "a", failure_class: "infra" },
        { id: "b", failure_class: "transient" },
        { id: "c", failure_class: "permanent" },
        { id: "d", failure_class: "unknown" },
        { id: "e" }, // missing → treated as recoverable
    ]);
    assert.deepEqual(result.reclaim.sort(), ["a", "b", "e"]);
    assert.equal(result.skippedPermanent, 2);
});

// ---------------------------------------------------------------------------
// resolveRecoverFailedOnRestart / shouldRunRecovery
// ---------------------------------------------------------------------------
test("resolveRecoverFailedOnRestart: false only for 'false'", () => {
    assert.equal(resolveRecoverFailedOnRestart(undefined), true);
    assert.equal(resolveRecoverFailedOnRestart("true"), true);
    assert.equal(resolveRecoverFailedOnRestart("false"), false);
    assert.equal(resolveRecoverFailedOnRestart("FALSE"), false);
});

test("shouldRunRecovery: false for sitemap/generate_data", () => {
    assert.equal(shouldRunRecovery(true, "sitemap"), false);
    assert.equal(shouldRunRecovery(true, "generate_data"), false);
    assert.equal(shouldRunRecovery(true, "default"), true);
    assert.equal(shouldRunRecovery(false, "default"), false);
});

// ---------------------------------------------------------------------------
// isDownloadError / isPageClosedError / resolveSkipDownloads / shouldSkipAsDownload
// ---------------------------------------------------------------------------
test("isDownloadError: matches download trigger string", () => {
    assert.equal(isDownloadError("Download is starting"), true);
    assert.equal(isDownloadError("other error"), false);
});

test("isPageClosedError: matches closed-page string", () => {
    assert.equal(isPageClosedError("Target page, context or browser has been closed"), true);
    assert.equal(isPageClosedError("other"), false);
});

test("resolveSkipDownloads: false only for 'false'", () => {
    assert.equal(resolveSkipDownloads(undefined), true);
    assert.equal(resolveSkipDownloads("true"), true);
    assert.equal(resolveSkipDownloads("false"), false);
});

test("shouldSkipAsDownload: gate + predicate", () => {
    assert.equal(shouldSkipAsDownload(true, "Download is starting"), true);
    assert.equal(shouldSkipAsDownload(false, "Download is starting"), false);
    assert.equal(shouldSkipAsDownload(true, "other"), false);
});

// ---------------------------------------------------------------------------
// resolveStallCountResolved
// ---------------------------------------------------------------------------
test("resolveStallCountResolved: default false when unset/empty", () => {
    assert.equal(resolveStallCountResolved(undefined), false);
    assert.equal(resolveStallCountResolved(""), false);
});
test("resolveStallCountResolved: true only for 'true' (case-insensitive)", () => {
    assert.equal(resolveStallCountResolved("true"), true);
    assert.equal(resolveStallCountResolved("TRUE"), true);
    assert.equal(resolveStallCountResolved("1"), false);
    assert.equal(resolveStallCountResolved("yes"), false);
});
