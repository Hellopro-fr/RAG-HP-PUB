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
 * Resolves the crawl-level max concurrency from an env value (positive int, default 10).
 * Caps the AutoscaledPool — which scales on local CPU/event-loop/memory, all idle while
 * handlers await the detection HTTP call — so it cannot over-subscribe the
 * DETECTION_MAX_CONCURRENCY-wide (5) detect p-limit. Without a cap the pool ramps to 25+
 * handlers against 5 detect slots, inflating per-page detect latency past
 * requestHandlerTimeoutSecs → mass handler timeouts + progress-stall death spiral.
 * Default 10 ≈ 2× DETECTION_MAX_CONCURRENCY: overlaps nav/extract with the in-flight
 * detects without growing the detect queue. Invalid/empty/non-positive → 10.
 * Spec: docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md
 */
export function resolveMaxConcurrency(raw: string | undefined): number {
    const n = Number(raw);
    return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 10;
}

/**
 * Resolves the request-handler timeout in seconds from an env value (positive int, default 200).
 * Must exceed one navigation (≤ navigationTimeoutSecs 90) plus one detection call
 * (DETECTION_REQUEST_TIMEOUT_S 180) so a slow-but-progressing page is not killed mid-detect.
 * The prior 120s budget sat BELOW the 180s detect timeout → orphaned handlers hit
 * page.$$eval on a torn-down page. Invalid/empty/non-positive → 200.
 * Spec: docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md
 */
export function resolveRequestHandlerTimeoutSecs(raw: string | undefined): number {
    const n = Number(raw);
    return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 200;
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
export const MAX_CONCURRENCY: number =
    resolveMaxConcurrency(process.env.CRAWLER_MAX_CONCURRENCY);
export const REQUEST_HANDLER_TIMEOUT_S: number =
    resolveRequestHandlerTimeoutSecs(process.env.REQUEST_HANDLER_TIMEOUT_S);

// ---------------------------------------------------------------------------
// Failure classification & auto-recovery on restart
// Spec: docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md
// ---------------------------------------------------------------------------

export type FailureClass = "permanent" | "transient" | "infra" | "unknown";

/**
 * Transport-layer error markers that mean "retrying yields the same result".
 * Single source of truth — also consumed by functions.ts failedRequestHandler
 * (DRY; replaces the inline NON_RETRYABLE_ERRORS list).
 */
export const PERMANENT_ERROR_MARKERS: readonly string[] = [
    "ERR_NAME_NOT_RESOLVED",      // domain does not exist
    "ERR_CERT_DATE_INVALID",      // expired TLS cert
    "ERR_SSL_PROTOCOL_ERROR",     // incompatible TLS
    "ERR_TOO_MANY_REDIRECTS",     // redirect loop
    "Download is starting",       // Playwright binary-download trigger
    "net::ERR_ABORTED",           // navigation aborted (often binary content)
    "Execution context was destroyed", // page destroyed during download
];

/**
 * Transport/connection faults on OUR side (proxy gateway, network) — recoverable.
 * NOTE: NS_ERROR_ABORT and "browserController.newPage() failed" are intentionally
 * excluded (ambiguous: binary-download abort / poison URL) → classified "unknown"
 * → not auto-recovered. Deferred infra-marker candidates.
 */
const INFRA_ERROR_MARKERS: readonly string[] = [
    "NS_ERROR_PROXY_CONNECTION_REFUSED",
    "NS_ERROR_PROXY_",
    "NS_ERROR_CONNECTION_REFUSED",
    "NS_ERROR_NET_",
    "ECONNREFUSED",
    "ECONNRESET",
    "ETIMEDOUT",
    "socket hang up",
];

/**
 * Classifies a failed request from its error string (and optional HTTP status).
 * Precedence: permanent marker > infra marker > HTTP status > navigation-timeout > unknown.
 */
export function classifyFailure(errorStr: string, status?: number): FailureClass {
    if (PERMANENT_ERROR_MARKERS.some((m) => errorStr.includes(m))) return "permanent";
    if (INFRA_ERROR_MARKERS.some((m) => errorStr.includes(m))) return "infra";
    if (typeof status === "number" && status > 0) {
        const c = classifyHttpStatus(status);
        if (c === "permanent") return "permanent";
        if (c === "transient" || c === "block") return "transient";
    }
    if (errorStr.includes("Navigation timed out") || errorStr.includes("TimeoutError")) {
        return "transient";
    }
    return "unknown";
}

/** Recoverable on restart = infra (our transport) or transient (server-side hiccup). */
export function isRecoverableFailureClass(cls: FailureClass): boolean {
    return cls === "infra" || cls === "transient";
}

/**
 * Pure filter for reclaimFailedRequest: given error-dataset items, returns the
 * request ids to re-queue plus the count of skipped permanent/unknown items.
 * A missing failure_class (legacy, pre-feature crawls) is treated as recoverable
 * so old proxy victims are not lost (bounded — permanent ones fail-fast on re-crawl).
 */
export function selectReclaimableIds(
    items: ReadonlyArray<{ id?: string; failure_class?: string }>,
): { reclaim: string[]; skippedPermanent: number } {
    const reclaim: string[] = [];
    let skippedPermanent = 0;
    for (const item of items) {
        if (!item.id) continue;
        const cls = item.failure_class as FailureClass | undefined;
        if (cls !== undefined && !isRecoverableFailureClass(cls)) {
            skippedPermanent++;
            continue;
        }
        reclaim.push(item.id);
    }
    return { reclaim, skippedPermanent };
}

/** Resolves the auto-recovery kill-switch. Default true; only "false" disables. */
export function resolveRecoverFailedOnRestart(raw: string | undefined): boolean {
    return (raw ?? "true").trim().toLowerCase() !== "false";
}

/** Auto-recovery runs only for the default crawl flow (not sitemap/generate_data). */
export function shouldRunRecovery(flag: boolean, typeCrawling: string): boolean {
    return flag && typeCrawling !== "sitemap" && typeCrawling !== "generate_data";
}

export const RECOVER_FAILED_ON_RESTART: boolean =
    resolveRecoverFailedOnRestart(process.env.RECOVER_FAILED_ON_RESTART);

// ---------------------------------------------------------------------------
// Download / PDF skip (fast-fail)
// Spec: docs/superpowers/specs/2026-06-17-crawler-skip-pdf-design.md
// ---------------------------------------------------------------------------

/**
 * True when a navigation error is Playwright's download trigger — the response
 * is a downloadable file (e.g. an extension-less PDF path) rather than a page.
 * "Download is starting" is also a PERMANENT_ERROR_MARKER; this named predicate
 * is the reusable form consumed by the errorHandler + failedRequestHandler.
 */
export function isDownloadError(errorStr: string): boolean {
    return errorStr.includes("Download is starting");
}

/** Resolves the download-skip kill-switch. Default true; only "false" disables. */
export function resolveSkipDownloads(raw: string | undefined): boolean {
    return (raw ?? "true").trim().toLowerCase() !== "false";
}

/** Pure skip decision: skipping is enabled AND the error is a download trigger. */
export function shouldSkipAsDownload(skipDownloads: boolean, errorStr: string): boolean {
    return skipDownloads && isDownloadError(errorStr);
}

/** Crawlee dataset name for skipped downloads/PDFs (mirrors error-/nfr- naming). */
export function pdfDatasetName(crawleeStorageName: string | undefined, domain: string): string {
    return crawleeStorageName ? `pdf-${crawleeStorageName}` : `pdf-${domain}`;
}

/** Resolved once at module load. Node-only, inherited by the crawler subprocess. */
export const SKIP_DOWNLOADS: boolean = resolveSkipDownloads(process.env.SKIP_DOWNLOADS);
