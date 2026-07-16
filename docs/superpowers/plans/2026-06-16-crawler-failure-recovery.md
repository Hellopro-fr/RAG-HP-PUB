# Crawler Failure Classification & Auto-Recovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A same-id crawler restart auto-recovers proxy/transport-failed URLs (skipping genuine permanent failures), so a temporary proxy outage never permanently loses valid pages.

**Architecture:** One shared, pure failure-classification primitive in `httpStatusPolicy.ts` keyed off the authoritative `request.noRetry` flag. The `failedRequestHandler` tags each `error-{domain}` record with a `failure_class`; `reclaimFailedRequest` re-queues only recoverable (infra/transient) records via a pure `selectReclaimableIds`; `main.ts` runs recovery *before* the queue-health early-exit, behind `RECOVER_FAILED_ON_RESTART` (default on, env kill-switch).

**Tech Stack:** Node.js 22, TypeScript, Crawlee 3, Playwright/Camoufox. Tests: script-style `tsx` runners with a local `assertEqual` (run individually: `npx tsx src/tests/test_X.ts`).

**Spec:** `docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md`

**Branch:** `features/poc` (local, unpushed — operator decides push/deploy).

**Conventions (standing):** `git add <explicit files>` (never `-A`); commit via a private `.git/<NAME>_MSG.txt` + `git -c commit.encoding=utf-8 commit -F` (cp1252 + concurrent-session safety); never stage `graphify-out/*`; run targeted test files only. Implementers do NOT commit — the coordinator (main thread) runs the final test suite and all commits.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `crawler/src/httpStatusPolicy.ts` | Pure status/nav/**failure** policy (single source of truth) | Modify — add failure-classification + recovery primitives |
| `crawler/src/tests/test_httpStatusPolicy.ts` | Unit tests for the pure policy | Modify — add cases |
| `crawler/src/functions.ts` | Crawler utilities incl. `failedRequestHandler` + `reclaimFailedRequest` | Modify — DRY markers, tag `failure_class`, filter reclaim |
| `crawler/src/tests/test_functions.ts` | Tests for crawler utilities | Modify — add reclaim integration test |
| `crawler/src/main.ts` | Crawlee entry point / orchestration | Modify — run recovery before early-exit, behind flag |
| `apps-microservices/crawler-service/CLAUDE.md` | Service docs | Modify — document policy + env var |

All paths below are relative to `apps-microservices/crawler-service/crawler/` unless stated otherwise. Run test commands from that directory.

---

### Task 1: Failure-classification + recovery primitives (`httpStatusPolicy.ts`)

**Goal:** Add the pure, dependency-free primitives both fixes consume: `FailureClass`, the marker lists, `classifyFailure`, `isRecoverableFailureClass`, `selectReclaimableIds`, the `RECOVER_FAILED_ON_RESTART` env flag, and the `shouldRunRecovery` gate.

**Files:**
- Modify: `crawler/src/httpStatusPolicy.ts` (append after line 68)
- Test: `crawler/src/tests/test_httpStatusPolicy.ts`

**Acceptance Criteria:**
- [ ] `classifyFailure` returns `permanent` for DNS/SSL/redirect markers and for permanent HTTP status; `infra` for proxy/connection markers; `transient` for transient/block status + nav-timeout; `unknown` otherwise; precedence permanent-marker > infra-marker > status > nav-timeout.
- [ ] `isRecoverableFailureClass` is true only for `infra`/`transient`.
- [ ] `selectReclaimableIds` returns recoverable ids + `skippedPermanent` count; treats missing `failure_class` as recoverable; ignores items without `id`.
- [ ] `RECOVER_FAILED_ON_RESTART` is `true` unless the env value (case-insensitive, trimmed) is `"false"`.
- [ ] `shouldRunRecovery(flag, typeCrawling)` is false for `sitemap`/`generate_data` or when flag is false.
- [ ] All existing tests still pass.

**Verify:** `npx tsx src/tests/test_httpStatusPolicy.ts` → `test_httpStatusPolicy: <N> passed, 0 failed`

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `crawler/src/tests/test_httpStatusPolicy.ts` (before the final `console.log`/`process.exit` lines at 67-68; add the new imports to the existing import block at lines 6-11):

Add to the import block (lines 6-11):
```typescript
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
```

Insert before line 67 (`console.log(...)`):
```typescript
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
// permanent marker beats an otherwise-transient status
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
// infra marker beats status
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx tsx src/tests/test_httpStatusPolicy.ts`
Expected: FAIL — `classifyFailure`/`selectReclaimableIds`/etc. not exported (TypeScript/runtime error or assertion failures).

- [ ] **Step 3: Implement the primitives** — append to `crawler/src/httpStatusPolicy.ts` after line 68:

```typescript

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx tsx src/tests/test_httpStatusPolicy.ts`
Expected: PASS — `test_httpStatusPolicy: <N> passed, 0 failed`

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: (coordinator commits)** — implementer stops here. Coordinator stages `crawler/src/httpStatusPolicy.ts` + `crawler/src/tests/test_httpStatusPolicy.ts`.

---

### Task 2: Tag `failure_class` at failure (`functions.ts` `failedRequestHandler`)

**Goal:** Make the handler the single producer of `failure_class`, and DRY the permanent-error list against `httpStatusPolicy.ts`.

**Files:**
- Modify: `crawler/src/functions.ts` (import block lines 28-32; `failedRequestHandler` 551-684)
- Test: `crawler/src/tests/test_httpStatusPolicy.ts` (classification already covered by Task 1; no new test needed for the pure logic — the handler wiring is verified by Task 3's integration test which reads handler-shaped records)

**Acceptance Criteria:**
- [ ] The inline `NON_RETRYABLE_ERRORS` array is removed; `isPermanentError` consumes the imported `PERMANENT_ERROR_MARKERS`.
- [ ] The `error-{domain}` record includes `failure_class`, computed as `request.noRetry ? "permanent" : classifyFailure(errorStr, status)`.
- [ ] No behavior change to existing noRetry decisions (permanent markers, timeout cap, WAF block all still set noRetry exactly as before).

**Verify:** `npx tsc --noEmit` → no errors; `npx tsx src/tests/test_functions.ts` → existing test still passes.

**Steps:**

- [ ] **Step 1: Extend the httpStatusPolicy import** — `crawler/src/functions.ts` lines 28-32 currently:

```typescript
import {
    NAVIGATION_WAIT_UNTIL,
    TIMEOUT_MAX_RETRIES,
    shouldCapTimeoutRetry,
} from "./httpStatusPolicy.js";
```

Replace with:
```typescript
import {
    NAVIGATION_WAIT_UNTIL,
    TIMEOUT_MAX_RETRIES,
    shouldCapTimeoutRetry,
    PERMANENT_ERROR_MARKERS,
    classifyFailure,
    type FailureClass,
} from "./httpStatusPolicy.js";
```

- [ ] **Step 2: DRY the permanent-error list** — replace lines 556-566 (the inline `NON_RETRYABLE_ERRORS` literal + the `errorStr`/`isPermanentError` lines) with:

```typescript
            // Détection des erreurs permanentes — inutile de réessayer.
            // Markers live in httpStatusPolicy.ts (PERMANENT_ERROR_MARKERS) so the
            // handler and classifyFailure share one source of truth (DRY).
            const errorStr = String(request.errorMessages);
            const isPermanentError = PERMANENT_ERROR_MARKERS.some((err) => errorStr.includes(err));
```

(Leave lines 567-570 — the `if (isPermanentError) { request.noRetry = true; ... }` block — unchanged.)

- [ ] **Step 3: Compute + record `failure_class`** — replace the error-dataset push block (currently lines 672-683, the comment `// Save rich error info` through the `pushData({...})` call) with:

```typescript
            // Save rich error info. failure_class drives auto-recovery on restart:
            // request.noRetry is the authoritative "permanent" signal (set by routes.ts
            // permanent status, PERMANENT_ERROR_MARKERS, the timeout cap, or a permanent
            // WAF block); only the retried-but-exhausted bucket is refined by classifyFailure.
            // Spec: docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md
            const status = response?.status() || 0;
            const failureClass: FailureClass = request.noRetry
                ? "permanent"
                : classifyFailure(errorStr, status);
            let datasetName = context.config.crawleeStorageName ? `error-${context.config.crawleeStorageName}` : `error-${domain}`;
            let dataset = await Dataset.open(datasetName);
            await dataset.pushData({
                id: request.id,
                url: request.url,
                errors: request.errorMessages,
                proxy_used: maskProxyUrl(proxyInfo?.url),
                status_code: status,
                captcha: captchaDetected,
                failure_class: failureClass,
                timestamp: new Date().toISOString()
            });
```

- [ ] **Step 4: Typecheck + existing test**

Run: `npx tsc --noEmit` → no errors.
Run: `npx tsx src/tests/test_functions.ts` → `excludedPaths persistence: <N> passed, 0 failed`.

- [ ] **Step 5: (coordinator commits)** — implementer stops. Coordinator stages `crawler/src/functions.ts`.

---

### Task 3: Filtered reclaim + reachable recovery (`functions.ts` + `main.ts`)

**Goal:** `reclaimFailedRequest` re-queues only recoverable records (via `selectReclaimableIds`); `main.ts` runs it before the queue-health early-exit, behind the kill-switch.

**Files:**
- Modify: `crawler/src/functions.ts` (`reclaimFailedRequest` 1618-1656; extend the httpStatusPolicy import from Task 2)
- Modify: `crawler/src/main.ts` (import block; insert recovery before line 795; remove old call at 1129-1134)
- Test: `crawler/src/tests/test_functions.ts` (reclaim integration test)

**Acceptance Criteria:**
- [ ] `reclaimFailedRequest` re-queues only ids selected by `selectReclaimableIds`; logs `Reclaimed N recoverable requests, skipped M permanent.`; drops the error dataset only when `reclaimedCount > 0`.
- [ ] `main.ts` calls `reclaimFailedRequest(domain)` before the QUEUE HEALTH CHECK, guarded by `shouldRunRecovery(RECOVER_FAILED_ON_RESTART, typeCrawling)`, inside try/catch.
- [ ] The old reclaim call (was at 1129-1134, inside the `else` typeCrawling branch) is removed.
- [ ] Integration test: a recoverable record is reclaimed (pending), a permanent record is not, the error dataset is dropped.

**Verify:** `npx tsx src/tests/test_functions.ts` → `0 failed`; `npx tsc --noEmit` → no errors.

**Steps:**

- [ ] **Step 1: Write the failing integration test** — append to `crawler/src/tests/test_functions.ts` (before any final top-level call; add a self-contained async function and invoke it at the end). This sets a temp Crawlee storage dir BEFORE importing crawlee, seeds a queue + error dataset, runs the real `reclaimFailedRequest`, and asserts the filter + drop:

```typescript
// --- reclaimFailedRequest: only recoverable records are re-queued ---
// Uses an isolated CRAWLEE_STORAGE_DIR so it never touches real crawl storage.
async function testReclaimFiltersByFailureClass() {
    let passed = 0;
    let failed = 0;

    const os = await import("os");
    const fsp = await import("fs/promises");
    const tmpRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "reclaim-test-"));
    process.env.CRAWLEE_STORAGE_DIR = tmpRoot;

    // Import AFTER setting the storage dir so Crawlee uses the temp location.
    const { RequestQueue, Dataset } = await import("crawlee");
    const { reclaimFailedRequest } = await import("../functions.js");

    const name = "reclaimtest.example";
    const queue = await RequestQueue.open(name);

    // Seed 3 requests, capture their Crawlee-assigned ids, and mark all handled
    // (simulates a completed crawl whose requests all reached terminal state).
    const urls = [
        "https://reclaimtest.example/infra",
        "https://reclaimtest.example/permanent",
        "https://reclaimtest.example/legacy",
    ];
    const { processedRequests } = await queue.addRequests(urls.map((url) => ({ url })));
    const idByUrl: Record<string, string> = {};
    for (const pr of processedRequests) idByUrl[pr.uniqueKey] = pr.requestId;
    for (const url of urls) {
        const req = await queue.getRequest(idByUrl[url]);
        if (req) await queue.markRequestHandled(req);
    }

    // Error dataset with mixed failure_class (legacy entry has none).
    const errorDataset = await Dataset.open(`error-${name}`);
    await errorDataset.pushData([
        { id: idByUrl[urls[0]], url: urls[0], failure_class: "infra" },
        { id: idByUrl[urls[1]], url: urls[1], failure_class: "permanent" },
        { id: idByUrl[urls[2]], url: urls[2] }, // legacy: missing → recoverable
    ]);

    await reclaimFailedRequest(name);

    // infra + legacy reclaimed (pending), permanent skipped (still handled).
    const info = await queue.getInfo();
    if (info && info.pendingRequestCount === 2) passed++;
    else { console.error(`FAIL: expected 2 pending after reclaim, got ${info?.pendingRequestCount}`); failed++; }

    if (info && info.handledRequestCount === 1) passed++;
    else { console.error(`FAIL: expected 1 still-handled (permanent), got ${info?.handledRequestCount}`); failed++; }

    // Error dataset dropped (reclaimedCount > 0).
    const reopened = await Dataset.open(`error-${name}`);
    const after = await reopened.getInfo();
    if (!after || after.itemCount === 0) passed++;
    else { console.error(`FAIL: expected error dataset dropped/empty, got itemCount=${after.itemCount}`); failed++; }

    // Cleanup
    await fsp.rm(tmpRoot, { recursive: true, force: true });
    delete process.env.CRAWLEE_STORAGE_DIR;

    console.log(`reclaimFailedRequest filter: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testReclaimFiltersByFailureClass();
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx tsx src/tests/test_functions.ts`
Expected: FAIL — `reclaimFailedRequest` currently re-queues ALL records (no filter), so `pendingRequestCount` is 3 not 2 (and the permanent one is wrongly reclaimed).

- [ ] **Step 3: Extend the httpStatusPolicy import in `functions.ts`** — update the import block (from Task 2) to also pull `selectReclaimableIds`:

```typescript
import {
    NAVIGATION_WAIT_UNTIL,
    TIMEOUT_MAX_RETRIES,
    shouldCapTimeoutRetry,
    PERMANENT_ERROR_MARKERS,
    classifyFailure,
    selectReclaimableIds,
    type FailureClass,
} from "./httpStatusPolicy.js";
```

- [ ] **Step 4: Filter `reclaimFailedRequest`** — replace the body from the `dataset.forEach(...)` loop through the summary/drop logic (currently lines 1631-1655) with:

```typescript
    const { items } = await dataset.getData();
    const { reclaim, skippedPermanent } = selectReclaimableIds(
        items as Array<{ id?: string; failure_class?: string }>,
    );

    for (const requestID of reclaim) {
        try {
            const request = await requestQueue.getRequest(requestID);
            if (request) {
                request.retryCount = 0;
                request.errorMessages = [];
                request.handledAt = undefined;
                await requestQueue.reclaimRequest(request);
                reclaimedCount++;
            }
        } catch (e) {
            console.error(`Failed to reclaim request ${requestID}: ${e}`);
        }
    }

    console.log(`Reclaimed ${reclaimedCount} recoverable requests, skipped ${skippedPermanent} permanent.`);
    if (reclaimedCount > 0) {
        await dropDataset(errorDatasetName);
        console.log(`Reclaimed ${reclaimedCount} items, dropped error dataset.`);
    } else {
        console.warn(`No recoverable items — keeping error dataset '${errorDatasetName}' for debugging.`);
    }
```

(The lines above this — opening the dataset, the `if (!info || info.itemCount === 0) return;` guard at 1623, `const requestQueue = await RequestQueue.open(name);` at 1628, `let reclaimedCount = 0;` at 1629 — stay unchanged.)

- [ ] **Step 5: Run the integration test to verify it passes**

Run: `npx tsx src/tests/test_functions.ts`
Expected: PASS — `reclaimFailedRequest filter: 3 passed, 0 failed` (and the existing excludedPaths test still passes).

- [ ] **Step 6: Make recovery reachable in `main.ts`** — add the import (after line 6, `import { router } from "./routes.js";`):

```typescript
import { RECOVER_FAILED_ON_RESTART, shouldRunRecovery } from "./httpStatusPolicy.js";
```

Insert the recovery block immediately before the `// --- QUEUE HEALTH CHECK ---` comment (currently line 795), i.e. after the homepage-seed `else { console.log("RequestQueueNotEmpty"); }` block at 791-793:

```typescript

// Auto-recover recoverable (infra/transient) failures from a prior run BEFORE the
// queue-health early-exit, so a same-id restart re-crawls proxy/network victims
// instead of exiting "already completed". Default-on; RECOVER_FAILED_ON_RESTART=false
// reverts to the prior behavior. Spec: 2026-06-16-crawler-failure-recovery-design.md
if (shouldRunRecovery(RECOVER_FAILED_ON_RESTART, typeCrawling)) {
    try {
        await reclaimFailedRequest(domain);
    } catch (e) {
        console.warn(`⚠️ auto-recovery skipped for ${domain}: ${e}`);
    }
}
```

- [ ] **Step 7: Remove the now-redundant old reclaim call** — in the `else` branch of the `typeCrawling` conditional (currently lines 1128-1134), delete the reclaim try/catch so the branch starts directly at the memory pre-flight. The block currently reads:

```typescript
} else {
    // Reclaim failed request
    try {
        await reclaimFailedRequest(domain);
    } catch (error) {
        console.warn(`⚠️ Warning: Failed to reclaim failed requests for ${domain}. The crawler will continue without them. Error: ${error}`);
    }

    // Pre-flight: Configure Global Crawlee Memory Limit
```

Change to:
```typescript
} else {
    // Failed-request recovery now runs earlier (before the queue-health check) so it
    // is reachable for completed crawls — see the RECOVER_FAILED_ON_RESTART block above.

    // Pre-flight: Configure Global Crawlee Memory Limit
```

- [ ] **Step 8: Typecheck**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 9: (coordinator commits)** — implementer stops. Coordinator stages `crawler/src/functions.ts`, `crawler/src/main.ts`, `crawler/src/tests/test_functions.ts`.

---

### Task 4: Documentation (`crawler-service/CLAUDE.md`)

**Goal:** Document the failure-classification + auto-recovery behavior and the new env var.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] New subsection "Failure Classification & Auto-Recovery on Restart" with the class table, the `noRetry`→permanent rule, the legacy-entry behavior, and the `RECOVER_FAILED_ON_RESTART` env var (default `true`).
- [ ] Cross-linked from the existing "HTTP Status & Navigation Retry Policy" section.
- [ ] Spec path referenced.

**Verify:** `grep -n "RECOVER_FAILED_ON_RESTART" apps-microservices/crawler-service/CLAUDE.md` → matches; visual read confirms the table.

**Steps:**

- [ ] **Step 1: Add the subsection** — in `apps-microservices/crawler-service/CLAUDE.md`, immediately after the existing "## HTTP Status & Navigation Retry Policy" section (right before "## Conventions"), insert:

```markdown
## Failure Classification & Auto-Recovery on Restart

A failed request is classified so a same-id restart can recover the *recoverable*
ones without re-crawling genuine permanent failures. The authoritative "permanent"
signal is `request.noRetry` (set by the status policy, `PERMANENT_ERROR_MARKERS`, the
navigation-timeout cap, or a permanent WAF block); only the retried-but-exhausted
bucket is refined by `classifyFailure` (`crawler/src/httpStatusPolicy.ts`).

| Class | Source | Auto-recovered on restart? |
|-------|--------|----------------------------|
| permanent | `noRetry` set, or DNS/SSL/redirect markers, or permanent HTTP status | No |
| infra | transport faults — `NS_ERROR_PROXY_*`, `NS_ERROR_CONNECTION_REFUSED`, `NS_ERROR_NET_*`, `ECONNREFUSED/RESET`, `ETIMEDOUT`, `socket hang up` | Yes |
| transient | transient/block HTTP status (5xx/429/408/…) or navigation timeout | Yes |
| unknown | anything else (incl. `NS_ERROR_ABORT`, `browserController.newPage() failed` — ambiguous) | No |

Each permanently-failed request is written to the `error-{domain}` Crawlee dataset
with a `failure_class` field. On the next launch, `reclaimFailedRequest` runs **before**
the queue-health early-exit in `main.ts` and re-queues only the recoverable records
(resets `retryCount`/`handledAt`), then drops the error dataset. Legacy records with no
`failure_class` (pre-feature crawls) are treated as recoverable so old proxy victims are
not lost (bounded — permanent ones fail-fast on re-crawl).

**Why this exists:** a temporary proxy-gateway outage produced
`NS_ERROR_PROXY_CONNECTION_REFUSED` on valid URLs; without classification they burned the
full retry budget and were permanently lost, and `reclaimFailedRequest` was unreachable
for completed crawls (the queue-health `exit(0)` ran before it).

**Env var:**

| Variable | Default | Effect |
|---|---|---|
| `RECOVER_FAILED_ON_RESTART` | `true` | Auto-recover recoverable failures on a same-id restart. Set `false` to disable (revert to instant "already completed" exit). Node-only, inherited by the subprocess. |

Spec: `docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md`.
```

- [ ] **Step 2: Cross-link from the HTTP Status Policy section** — at the end of the "## HTTP Status & Navigation Retry Policy" section (after its Spec line), append:

```markdown
See also "Failure Classification & Auto-Recovery on Restart" below — `classifyFailure`
extends this module to transport errors and drives restart recovery.
```

- [ ] **Step 3: Verify**

Run: `grep -n "RECOVER_FAILED_ON_RESTART" apps-microservices/crawler-service/CLAUDE.md`
Expected: at least 2 matches (table + env row).

- [ ] **Step 4: (coordinator commits)** — implementer stops. Coordinator stages `apps-microservices/crawler-service/CLAUDE.md`.

---

## Final Verification (coordinator, after all tasks)

Run from `apps-microservices/crawler-service/crawler/`:
```bash
npx tsc --noEmit
npx tsx src/tests/test_httpStatusPolicy.ts
npx tsx src/tests/test_functions.ts
npx tsx src/tests/test_main.ts
npx tsx src/tests/test_routes.ts
```
Expected: tsc clean; every test prints `0 failed`.

Then a final holistic review (cavecrew-reviewer) over the full diff, fix any criticals, and commit each task's files with bilingual (EN+FR) messages via private `.git/<NAME>_MSG.txt`.

## Self-Review Notes

- **Spec coverage:** §5.1→T1, §5.2→T2, §5.3+§5.4→T3, §9 docs→T4, §8 testing→T1+T3, §6 edge cases→covered by `selectReclaimableIds` legacy handling (T1) + `reclaimedCount>0` drop guard (T3). All spec sections mapped.
- **Type consistency:** `FailureClass`, `classifyFailure`, `isRecoverableFailureClass`, `selectReclaimableIds`, `RECOVER_FAILED_ON_RESTART`, `shouldRunRecovery`, `resolveRecoverFailedOnRestart` defined in T1 and consumed with matching names in T2/T3. `failure_class` field name consistent across handler (T2), `selectReclaimableIds` (T1), and the integration test (T3).
- **tdd-gate:** all edited production files (`httpStatusPolicy.ts`, `functions.ts`, `main.ts`) have existing stem-matching `test_*.ts`; `.md` is gate-exempt.
