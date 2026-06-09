/**
 * Pure HTTP status / navigation retry policy for the crawler engine.
 *
 * Single source of truth, intentionally dependency-free so it can be unit-tested
 * in isolation (routes.ts cannot be imported by tests — it transitively imports
 * ./main.js, the crawler entry point with top-level side effects).
 *
 * Spec: docs/superpowers/specs/2026-06-09-crawler-http-status-retry-policy-design.md
 */

export type StatusClass = "ok" | "permanent" | "transient" | "block";

// Permanent: retrying yields the same result — fail once.
const PERMANENT_STATUS: ReadonlySet<number> = new Set([
    400, 401, 404, 405, 406, 410, 414, 423, 451, 501,
]);
// Block: anti-bot — a fresh session/IP may pass.
const BLOCK_STATUS: ReadonlySet<number> = new Set([403, 429]);
// Transient: server-side hiccup — retry may succeed.
const TRANSIENT_STATUS: ReadonlySet<number> = new Set([
    408, 425, 500, 502, 503, 504, 509, 521, 522, 523, 524, 525, 526,
]);

/** Classifies an HTTP response status for retry/drop/session decisions. */
export function classifyHttpStatus(status: number): StatusClass {
    if (PERMANENT_STATUS.has(status)) return "permanent";
    if (BLOCK_STATUS.has(status)) return "block";
    if (TRANSIENT_STATUS.has(status)) return "transient";
    return "ok"; // 2xx/3xx and any unlisted code → proceed to extraction
}

export type NavigationWaitUntil = "load" | "domcontentloaded" | "networkidle" | "commit";

const VALID_WAIT_UNTIL: ReadonlySet<string> = new Set([
    "load", "domcontentloaded", "networkidle", "commit",
]);

/**
 * Resolves the page.goto waitUntil condition from an env value.
 * Invalid/empty/undefined → 'domcontentloaded' (resolve on DOM parsed, not on
 * the never-firing load event of heavy pages).
 */
export function resolveNavigationWaitUntil(raw: string | undefined): NavigationWaitUntil {
    const v = (raw ?? "").trim().toLowerCase();
    return VALID_WAIT_UNTIL.has(v) ? (v as NavigationWaitUntil) : "domcontentloaded";
}

/** Resolves the max navigation-timeout retries from an env value (non-negative int, default 2). */
export function resolveTimeoutMaxRetries(raw: string | undefined): number {
    const n = Number(raw);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 2;
}

/**
 * True when a failed request is a navigation timeout that has reached the retry
 * cap — bounds wasted retries on genuinely-unresponsive URLs.
 */
export function shouldCapTimeoutRetry(errorStr: string, retryCount: number, cap: number): boolean {
    const isNavTimeout =
        errorStr.includes("Navigation timed out") || errorStr.includes("TimeoutError");
    return isNavTimeout && retryCount >= cap;
}

// Derived once at module load from the process environment.
export const NAVIGATION_WAIT_UNTIL: NavigationWaitUntil =
    resolveNavigationWaitUntil(process.env.NAVIGATION_WAIT_UNTIL);
export const TIMEOUT_MAX_RETRIES: number =
    resolveTimeoutMaxRetries(process.env.TIMEOUT_MAX_RETRIES);
