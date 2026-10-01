# Crawler HTTP Status & Navigation Retry Policy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HTTP status codes visible on heavy/slow pages and apply a single, correct retry policy — permanent codes (404/410/…) fail once, transient (504/408/…) retry, anti-bot (403/429) rotate session, navigation timeouts are capped.

**Architecture:** Extract the pure decision logic into a new dependency-free module `crawler/src/httpStatusPolicy.ts` (classification + env-driven navigation/retry knobs), because `routes.ts` cannot be imported by tests (it transitively imports `./main.js`, the crawler entry point with top-level side effects). `routes.ts` and `functions.ts` import the module and wire it in. The root-cause fix is switching `page.goto`'s wait condition from Playwright's default `'load'` (which hangs for the full 90 s navigation timeout on heavy pages whose sub-resources never settle) to `'domcontentloaded'`, so `response.status()` becomes available; content completeness is unaffected because the handler re-settles content post-navigation via `processPage`/`waitAndScroll` (bounded `networkidle` + scroll).

**Tech Stack:** Node.js 22, TypeScript, Crawlee 3, Playwright. Script-style tests run via `tsx` (local `assertEqual` + `process.exit`).

**Spec:** `docs/superpowers/specs/2026-06-09-crawler-http-status-retry-policy-design.md`

**Conventions / gotchas:**
- All commands run from the crawler directory: `apps-microservices/crawler-service/crawler/`.
- tdd-gate stem matching: editing `functions.ts` needs `test_functions.*`; `routes.ts` needs `test_routes.*`; creating `httpStatusPolicy.ts` needs `test_httpStatusPolicy.*`. Create the test file first.
- ESM import convention: import paths use the `.js` extension (tsx resolves the `.ts` source).
- Commits: bilingual EN+FR conventional commits. Use a private `.git/<NAME>_MSG.txt` written via the Write tool (UTF-8), then `git -c commit.encoding=utf-8 commit -F .git/<NAME>_MSG.txt`. Always `git add <explicit files>` (never `-A`). Work stays on `features/poc`, unpushed.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `crawler/src/httpStatusPolicy.ts` | Pure policy: `classifyHttpStatus`, `resolveNavigationWaitUntil`, `resolveTimeoutMaxRetries`, `shouldCapTimeoutRetry`, derived consts. Zero heavy imports. | **Create** |
| `crawler/src/tests/test_httpStatusPolicy.ts` | Unit tests for every pure function in the module. | **Create** |
| `crawler/src/routes.ts` | Import `classifyHttpStatus`; add `session` to handler; replace the dead status check (`:320-340`) with the policy. | Modify |
| `crawler/src/functions.ts` | Import policy helpers/consts; add the `waitUntil` preNavigationHook; set `blockedStatusCodes: []`; add the timeout retry cap in `failedRequestHandler`. | Modify |
| `apps-microservices/crawler-service/CLAUDE.md` | Document the policy + the 2 new env vars. | Modify |

---

## Task 1: `httpStatusPolicy.ts` module + unit tests

**Goal:** A dependency-free module holding all status/navigation/retry decision logic, fully unit-tested.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/httpStatusPolicy.ts`
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_httpStatusPolicy.ts`

**Acceptance Criteria:**
- [ ] `classifyHttpStatus` returns `permanent` / `block` / `transient` / `ok` per the spec table.
- [ ] `resolveNavigationWaitUntil` returns a valid Playwright wait state; invalid/empty/undefined → `'domcontentloaded'`; case-insensitive.
- [ ] `resolveTimeoutMaxRetries` parses a non-negative integer; invalid/negative/undefined → `2`.
- [ ] `shouldCapTimeoutRetry` is `true` only for a navigation-timeout error AND `retryCount >= cap`.
- [ ] Module has **no** import of `./main.js`, `crawlee`, `playwright`, or any I/O.

**Verify:** from `apps-microservices/crawler-service/crawler/`: `npx tsx src/tests/test_httpStatusPolicy.ts` → `... N passed, 0 failed`, exit 0.

**Steps:**

- [ ] **Step 1: Write the failing test** — create `src/tests/test_httpStatusPolicy.ts`:

```typescript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps-microservices/crawler-service/crawler/`): `npx tsx src/tests/test_httpStatusPolicy.ts`
Expected: FAIL — `Cannot find module '../httpStatusPolicy.js'`.

- [ ] **Step 3: Write the module** — create `src/httpStatusPolicy.ts`:

```typescript
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx tsx src/tests/test_httpStatusPolicy.ts`
Expected: PASS — `test_httpStatusPolicy: 41 passed, 0 failed`, exit 0.

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit`
Expected: clean (no errors).

- [ ] **Step 6: Commit**

Write `.git/HTTP_POLICY_T1_MSG.txt` (UTF-8) then:
```bash
git add apps-microservices/crawler-service/crawler/src/httpStatusPolicy.ts apps-microservices/crawler-service/crawler/src/tests/test_httpStatusPolicy.ts
git -c commit.encoding=utf-8 commit -F .git/HTTP_POLICY_T1_MSG.txt
```
Message (bilingual): `feat(crawler): add httpStatusPolicy module (status classification + nav/retry knobs)`.

---

## Task 2: Wire the status policy into the routes.ts handler

**Goal:** The default handler classifies the HTTP status and acts: permanent → `noRetry` + fail once; block → `session.retire()` + retry; transient → retry. Replaces the unreachable `:320-340` block.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts` (import; `:198` destructure; `:320-340` block)

**Blocked by:** Task 1.

**Acceptance Criteria:**
- [ ] `classifyHttpStatus` imported from `./httpStatusPolicy.js`.
- [ ] `session` added to the default-handler destructure.
- [ ] Permanent codes set `request.noRetry = true`; block codes call `session?.retire()`; all non-`ok` throw `HTTP ${status}`.
- [ ] Existing homepage `crawlErrorMessage` + `updateChecker.checkUrl` / `statsManager.increment("errors")` bookkeeping preserved.

**Verify:** from `crawler/`: `npx tsc --noEmit` clean; `npx tsx src/tests/test_routes.ts` → `... passed, 0 failed`; `npx tsx src/tests/test_httpStatusPolicy.ts` green.

**Steps:**

- [ ] **Step 1: Add the import** — in `routes.ts`, after line 26 (the existing `./qmHashTracker.js` import), add:

```typescript
import { classifyHttpStatus } from "./httpStatusPolicy.js";
```

- [ ] **Step 2: Add `session` to the handler destructure** — `routes.ts:198`:

```typescript
// ... existing code ...
router.addDefaultHandler(
    async ({ request, page, enqueueLinks, log, proxyInfo, crawler, response, session }) => {
// ... existing code ...
```

- [ ] **Step 3: Replace the dead blocked-status check** — replace the current `routes.ts:320-340` block:

```typescript
        // Blocked Status Check
        if (response) {
            const status = response.status();
            if ([401, 403, 429, 404, 410, 423, 502, 500, 503].includes(status)) {
                log.error(`🚫 BLOCKED: HTTP ${status} on ${url}`);
                // Set structured error message for "1 seul URL crawlé" case: HTTP error on homepage
                if (request.url === site) {
                    context.crawlErrorMessage = `Erreur HTTP ${status}`;
                }
                // Delegate error tracking to UpdateChecker in update mode
                const source = request.userData.source || '';
                if (context.updateChecker && source) {
                    await context.updateChecker.checkUrl(request.url, request.loadedUrl, source, status, false);
                } else if (context.statsManager && request.userData.is_existing) {
                    // Legacy fallback for non-update mode
                    await context.statsManager.increment("errors");
                }
                // Don't process, let failedRequestHandler handle it
                throw new Error(`BLOCKED: HTTP ${status}`);
            }
        }
```

with:

```typescript
        // HTTP Status Policy — single source of truth.
        // Reachable for every non-ok status because blockedStatusCodes is now empty
        // (Crawlee no longer pre-throws) and navigation resolves on 'domcontentloaded'
        // so response.status() is available even on heavy/slow pages.
        // Spec: docs/superpowers/specs/2026-06-09-crawler-http-status-retry-policy-design.md
        if (response) {
            const status = response.status();
            const statusClass = classifyHttpStatus(status);
            if (statusClass !== "ok") {
                // Preserve existing bookkeeping: homepage error message + error tracking.
                if (request.url === site) {
                    context.crawlErrorMessage = `Erreur HTTP ${status}`;
                }
                const source = request.userData.source || '';
                if (context.updateChecker && source) {
                    await context.updateChecker.checkUrl(request.url, request.loadedUrl, source, status, false);
                } else if (context.statsManager && request.userData.is_existing) {
                    await context.statsManager.increment("errors");
                }

                if (statusClass === "permanent") {
                    request.noRetry = true;
                    log.error(`⛔ PERMANENT HTTP ${status} on ${url} — no retry`);
                } else if (statusClass === "block") {
                    session?.retire();
                    log.warning(`🚫 BLOCKED HTTP ${status} on ${url} — retire session, retry`);
                } else {
                    log.warning(`↻ TRANSIENT HTTP ${status} on ${url} — retry`);
                }
                // Hand off to failedRequestHandler (records the rich error row).
                throw new Error(`HTTP ${status}`);
            }
        }
```

- [ ] **Step 4: Typecheck**

Run: `npx tsc --noEmit`
Expected: clean. (If `session` is reported unused on other handlers, ignore — it is used here.)

- [ ] **Step 5: Run the affected suites**

Run: `npx tsx src/tests/test_routes.ts` → expected PASS (unchanged).
Run: `npx tsx src/tests/test_httpStatusPolicy.ts` → expected PASS.

- [ ] **Step 6: Commit**

Write `.git/HTTP_POLICY_T2_MSG.txt` (UTF-8) then:
```bash
git add apps-microservices/crawler-service/crawler/src/routes.ts
git -c commit.encoding=utf-8 commit -F .git/HTTP_POLICY_T2_MSG.txt
```
Message (bilingual): `fix(crawler): single HTTP status policy in default handler`.

---

## Task 3: Wire the navigation lever, empty blockedStatusCodes, and timeout cap into functions.ts

**Goal:** `page.goto` resolves on `domcontentloaded`; Crawlee no longer pre-throws on status codes (`blockedStatusCodes: []`); navigation timeouts are capped via `failedRequestHandler`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts` (import; `:538`; `:556-561` region; `:667` preNavigationHooks)

**Blocked by:** Task 1.

**Acceptance Criteria:**
- [ ] Helpers/consts imported from `./httpStatusPolicy.js`.
- [ ] A preNavigationHook sets `gotoOptions.waitUntil = NAVIGATION_WAIT_UNTIL` (added first in the array).
- [ ] `blockedStatusCodes: []` (was the 9-code list).
- [ ] `failedRequestHandler` sets `request.noRetry = true` when `shouldCapTimeoutRetry(...)` is true.

**Verify:** from `crawler/`: `npx tsc --noEmit` clean; `npx tsx src/tests/test_functions.ts` green; `npx tsx src/tests/test_httpStatusPolicy.ts` green.

**Steps:**

- [ ] **Step 1: Add the import** — in `functions.ts`, after the `./camoufoxLaunchInput.js` import (line 27), add:

```typescript
import {
    NAVIGATION_WAIT_UNTIL,
    TIMEOUT_MAX_RETRIES,
    shouldCapTimeoutRetry,
} from "./httpStatusPolicy.js";
```

- [ ] **Step 2: Empty `blockedStatusCodes`** — `functions.ts:537-539`:

```typescript
        sessionPoolOptions: {
            // Empty: status-based retire/retry is now handled by the single policy
            // in routes.ts (classifyHttpStatus). Crawlee no longer pre-throws on
            // status codes, so every status reaches the handler. 403/429 session
            // rotation is re-implemented there via session.retire().
            blockedStatusCodes: [],
        },
```

- [ ] **Step 3: Add the navigation-lever preNavigationHook** — insert as the **first** element of the `preNavigationHooks` array (`functions.ts:667`), before the existing `async ({ page }) => {` hook:

```typescript
        preNavigationHooks: [
            // Resolve navigation as soon as the DOM is parsed (NAVIGATION_WAIT_UNTIL,
            // default 'domcontentloaded'), NOT when every sub-resource finishes.
            // Playwright's default 'load' hangs for the full navigationTimeoutSecs on
            // heavy pages whose trackers/lazy assets never settle — which hides the
            // HTTP status behind a never-completing navigation. Content completeness
            // is handled post-navigation by processPage/waitAndScroll (bounded
            // networkidle + scroll), so this does not reduce extracted content.
            async (_crawlingContext, gotoOptions) => {
                gotoOptions.waitUntil = NAVIGATION_WAIT_UNTIL;
            },
            async ({ page }) => {
// ... existing first hook body unchanged ...
```

(Leave the remaining hooks unchanged.)

- [ ] **Step 4: Add the timeout retry cap** — in `failedRequestHandler`, immediately after the existing `isPermanentError` block (`functions.ts:557-561`), add:

```typescript
            const errorStr = String(request.errorMessages);
            const isPermanentError = NON_RETRYABLE_ERRORS.some(err => errorStr.includes(err));
            if (isPermanentError) {
                request.noRetry = true;
                log.warning(`Permanent error detected for ${request.url} — no retry`);
            }

            // Navigation-timeout retry cap: a genuinely-unresponsive URL (no HTTP
            // response at all) would otherwise burn all maxRequestRetries × navigation
            // timeout. With waitUntil 'domcontentloaded', a real 404 resolves fast and
            // is handled by the status policy; a true timeout means the server never
            // responded — cap the retries.
            if (shouldCapTimeoutRetry(errorStr, request.retryCount, TIMEOUT_MAX_RETRIES)) {
                request.noRetry = true;
                log.warning(`Navigation timeout cap reached for ${request.url} (retryCount=${request.retryCount}) — no retry`);
            }
```

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit`
Expected: clean. If `gotoOptions.waitUntil` errors on type, confirm `NavigationWaitUntil` exactly matches Playwright's literals (`load|domcontentloaded|networkidle|commit`) — it does.

- [ ] **Step 6: Run the affected suites**

Run: `npx tsx src/tests/test_functions.ts` → expected PASS (unchanged).
Run: `npx tsx src/tests/test_httpStatusPolicy.ts` → expected PASS.

- [ ] **Step 7: Commit**

Write `.git/HTTP_POLICY_T3_MSG.txt` (UTF-8) then:
```bash
git add apps-microservices/crawler-service/crawler/src/functions.ts
git -c commit.encoding=utf-8 commit -F .git/HTTP_POLICY_T3_MSG.txt
```
Message (bilingual): `fix(crawler): waitUntil domcontentloaded, empty blockedStatusCodes, timeout retry cap`.

---

## Task 4: Document the policy in crawler-service CLAUDE.md

**Goal:** Operators/maintainers can find the policy + tune it.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Blocked by:** Task 2, Task 3.

**Acceptance Criteria:**
- [ ] New section describing the navigation lever + the status classes + the timeout cap.
- [ ] The two env vars (`NAVIGATION_WAIT_UNTIL`, `TIMEOUT_MAX_RETRIES`) documented with defaults.
- [ ] Spec path referenced.

**Verify:** section present; `git diff --stat` shows only `CLAUDE.md`.

**Steps:**

- [ ] **Step 1: Add the section** — append after the "api-detection-langue-fr Caller Contract" section in `apps-microservices/crawler-service/CLAUDE.md`:

```markdown
## HTTP Status & Navigation Retry Policy

`page.goto` resolves on `domcontentloaded` (not Playwright's default `load`), so the
HTTP status is visible even on heavy pages whose sub-resources never settle. Default
`load` previously hung for the full `navigationTimeoutSecs` (90s) and the status was
never read — a real 404 timed out and was retried 5×. Content completeness is
unaffected: the handler re-settles content post-navigation via
`processPage`/`waitAndScroll` (bounded `networkidle` + scroll).

Status handling is a single source of truth in `crawler/src/httpStatusPolicy.ts`
(`classifyHttpStatus`), applied in the `routes.ts` default handler. `blockedStatusCodes`
is empty — Crawlee no longer pre-throws on status; every status reaches the handler.

| Class | Codes | Behavior |
|-------|-------|----------|
| permanent | 400, 401, 404, 405, 406, 410, 414, 423, 451, 501 | `request.noRetry = true` → fail once |
| block | 403, 429 | `session.retire()` → retry with fresh session |
| transient | 408, 425, 500, 502, 503, 504, 509, 521-526 | retry (≤ `maxRequestRetries`) |
| ok | all others (2xx/3xx + unlisted) | proceed to extraction |

Navigation timeouts (no HTTP response at all) are capped in `failedRequestHandler`:
after `TIMEOUT_MAX_RETRIES`, `request.noRetry` is set.

**Env vars (optional; defaults baked in, inherited by the Node subprocess):**

| Variable | Default | Effect |
|---|---|---|
| `NAVIGATION_WAIT_UNTIL` | `domcontentloaded` | `page.goto` wait condition. Allowed: `load`, `domcontentloaded`, `commit`, `networkidle`. Invalid → default. Set `load` to revert. |
| `TIMEOUT_MAX_RETRIES` | `2` | Max navigation-timeout retries before `noRetry`. |

Spec: `docs/superpowers/specs/2026-06-09-crawler-http-status-retry-policy-design.md`.
```

- [ ] **Step 2: Commit**

Write `.git/HTTP_POLICY_T4_MSG.txt` (UTF-8) then:
```bash
git add apps-microservices/crawler-service/CLAUDE.md
git -c commit.encoding=utf-8 commit -F .git/HTTP_POLICY_T4_MSG.txt
```
Message (bilingual): `docs(crawler): document HTTP status & navigation retry policy`.

---

## Self-Review

**Spec coverage:**
- §3.1 navigation lever → Task 3 (preNavigationHook) + Task 1 (`resolveNavigationWaitUntil`/`NAVIGATION_WAIT_UNTIL`). ✓
- §3.2 empty blockedStatusCodes → Task 3 Step 2. ✓
- §3.3 single status policy + `session.retire()` + bookkeeping → Task 1 (`classifyHttpStatus`) + Task 2. ✓
- §3.4 timeout retry cap → Task 1 (`shouldCapTimeoutRetry`/`resolveTimeoutMaxRetries`) + Task 3 Step 4. ✓
- §3.5 config knobs → Task 1 (resolvers) + Task 4 (docs). ✓
- §4 tests → Task 1 test file (pure logic); wiring verified by tsc + existing suites. ✓
- §5 blast radius (single `blockedStatusCodes` consumer) → confirmed during spec write. ✓

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `StatusClass` ("ok"|"permanent"|"transient"|"block") consistent across module + handler. `NavigationWaitUntil` matches Playwright literals. `classifyHttpStatus`, `resolveNavigationWaitUntil`, `resolveTimeoutMaxRetries`, `shouldCapTimeoutRetry` signatures identical between module (Task 1), tests (Task 1), and consumers (Tasks 2-3). `NAVIGATION_WAIT_UNTIL`/`TIMEOUT_MAX_RETRIES` exported from Task 1, imported in Task 3.

**Note on test count:** Step 4 of Task 1 states "41 passed" — recount if cases are added/removed; the exact number is illustrative, `0 failed` is the gate.
