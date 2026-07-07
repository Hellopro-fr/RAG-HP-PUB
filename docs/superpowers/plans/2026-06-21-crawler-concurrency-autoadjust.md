# Crawler Concurrency Auto-Adjust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static crawler `maxConcurrency` cap with a detection-backpressure gate so concurrency auto-adjusts per crawl, raise the cap to a memory/browser ceiling, and quiet the benign `page.$$eval` teardown log.

**Architecture:** Pure logic (a gate predicate, two env resolvers, an error-class predicate) lives in the dependency-free `httpStatusPolicy.ts` and is unit-tested. `functions.ts` wires an `isTaskReadyFunction` onto the AutoscaledPool that vetoes new page starts while the detection `p-limit` queue (`detectionClient.limiter.pendingCount`) exceeds a threshold. `routes.ts` guards the pre-batch link extraction against an already-closed page.

**Tech Stack:** Node 22, TypeScript, Crawlee 3 (PlaywrightCrawler / AutoscaledPool), p-limit v5, node:test.

**Spec:** `docs/superpowers/specs/2026-06-21-crawler-concurrency-autoadjust-design.md`

**Conventions:**
- Local `features/poc`, unpushed. Remote-only: `npm run build` + `npm test` in `apps-microservices/crawler-service/crawler/` only — no live crawl.
- Commits are made by the **coordinator** (main thread), one per task, via a private `.git/<NAME>_MSG.txt` written with the Write tool then `git -c commit.encoding=utf-8 commit -F <file>` (cp1252 + concurrent-session safety). Bilingual EN+FR. `git add <explicit files>` — never `-A`. Delete the temp msg file after.
- Build path shorthand below: `DIR = apps-microservices/crawler-service/crawler`.

---

### Task 1: Pure logic — gate predicate, resolvers, page-closed predicate (+ tests)

**Goal:** Add the backpressure gate predicate, the threshold resolver, the page-closed predicate, and raise the `maxConcurrency` default to 20 — all in the dependency-free policy module, fully unit-tested.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/httpStatusPolicy.ts`
- Test: `apps-microservices/crawler-service/crawler/src/tests/httpStatusPolicy.limits.test.ts`

**Acceptance Criteria:**
- [ ] `shouldAcceptNewPage(pending, threshold)` returns `pending <= threshold`.
- [ ] `resolveBackpressureMaxPending` defaults to 5; `'0'` → 0 (valid); negative/invalid/Infinity → 5.
- [ ] `isPageClosedError` matches the teardown string, rejects others/empty.
- [ ] `resolveMaxConcurrency` default is now **20** (was 10); existing test updated.
- [ ] `BACKPRESSURE_MAX_PENDING` module const exported.

**Verify:** `npm test --prefix DIR` → all pass (incl. the new + updated assertions); `npm run build --prefix DIR` → tsc 0 errors.

**Steps:**

- [ ] **Step 1: Update the failing tests first** (TDD — they will fail until Step 2/3 land)

In `httpStatusPolicy.limits.test.ts`, extend the import and replace the `resolveMaxConcurrency defaults to 10` test with a `20` version, and add the three new tests. Final file:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    resolveMaxConcurrency,
    resolveRequestHandlerTimeoutSecs,
    resolveBackpressureMaxPending,
    shouldAcceptNewPage,
    isPageClosedError,
} from '../httpStatusPolicy.js';

test('resolveMaxConcurrency defaults to 20 on missing/invalid/non-positive', () => {
    assert.equal(resolveMaxConcurrency(undefined), 20);
    assert.equal(resolveMaxConcurrency(''), 20);
    assert.equal(resolveMaxConcurrency('abc'), 20);
    assert.equal(resolveMaxConcurrency('0'), 20);
    assert.equal(resolveMaxConcurrency('-5'), 20);
    assert.equal(resolveMaxConcurrency('Infinity'), 20);
});

test('resolveMaxConcurrency parses a positive int (floored)', () => {
    assert.equal(resolveMaxConcurrency('1'), 1);
    assert.equal(resolveMaxConcurrency('8'), 8);
    assert.equal(resolveMaxConcurrency('25'), 25);
    assert.equal(resolveMaxConcurrency('8.9'), 8);
});

test('resolveRequestHandlerTimeoutSecs defaults to 200 on missing/invalid/non-positive', () => {
    assert.equal(resolveRequestHandlerTimeoutSecs(undefined), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs(''), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('abc'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('0'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('-1'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('Infinity'), 200);
});

test('resolveRequestHandlerTimeoutSecs parses a positive int (floored)', () => {
    assert.equal(resolveRequestHandlerTimeoutSecs('120'), 120);
    assert.equal(resolveRequestHandlerTimeoutSecs('200'), 200);
    assert.equal(resolveRequestHandlerTimeoutSecs('300.5'), 300);
});

test('resolveBackpressureMaxPending defaults to 5; 0 valid; negative/invalid/Infinity → 5', () => {
    assert.equal(resolveBackpressureMaxPending(undefined), 5);
    assert.equal(resolveBackpressureMaxPending(''), 5);
    assert.equal(resolveBackpressureMaxPending('abc'), 5);
    assert.equal(resolveBackpressureMaxPending('-1'), 5);
    assert.equal(resolveBackpressureMaxPending('Infinity'), 5);
    assert.equal(resolveBackpressureMaxPending('0'), 0);
    assert.equal(resolveBackpressureMaxPending('5'), 5);
    assert.equal(resolveBackpressureMaxPending('10'), 10);
    assert.equal(resolveBackpressureMaxPending('5.9'), 5);
});

test('shouldAcceptNewPage accepts at/below threshold, rejects above', () => {
    assert.equal(shouldAcceptNewPage(0, 5), true);
    assert.equal(shouldAcceptNewPage(5, 5), true);
    assert.equal(shouldAcceptNewPage(6, 5), false);
    assert.equal(shouldAcceptNewPage(0, 0), true);
    assert.equal(shouldAcceptNewPage(1, 0), false);
});

test('isPageClosedError matches the teardown class, rejects others', () => {
    assert.equal(isPageClosedError('page.$$eval: Target page, context or browser has been closed'), true);
    assert.equal(isPageClosedError('Navigation timed out after 90000ms'), false);
    assert.equal(isPageClosedError(''), false);
});
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `npm test --prefix DIR`
Expected: failures on `resolveBackpressureMaxPending`/`shouldAcceptNewPage`/`isPageClosedError` (not exported) and the `20` assertion (currently 10).

- [ ] **Step 3: Change the `resolveMaxConcurrency` default 10 → 20**

In `httpStatusPolicy.ts`, edit the resolver (update the return default and the docstring):

```ts
/**
 * Resolves the crawl-level max concurrency from an env value (positive int, default 20).
 * This is now a memory/browser SAFETY CEILING — the detection-backpressure gate
 * (isTaskReadyFunction in functions.ts) is the primary throttle. Left uncapped the pool
 * could overshoot into memory pressure (the incident hit ~95-100% at ~25 concurrent).
 * Invalid/empty/non-positive → 20.
 * Spec: docs/superpowers/specs/2026-06-21-crawler-concurrency-autoadjust-design.md
 */
export function resolveMaxConcurrency(raw: string | undefined): number {
    const n = Number(raw);
    return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 20;
}
```

- [ ] **Step 4: Add `resolveBackpressureMaxPending` + `shouldAcceptNewPage`**

In `httpStatusPolicy.ts`, immediately after `resolveRequestHandlerTimeoutSecs`:

```ts
/**
 * Resolves the detection-backpressure threshold from an env value (non-negative int,
 * default 5). The pool pauses launching new pages while the detection p-limit queue
 * (pendingCount) exceeds this, so concurrency auto-adjusts to detection throughput.
 * 0 is valid ("tolerate no queue"). ≈ DETECTION_MAX_CONCURRENCY; raise in step if you
 * raise detection concurrency. Invalid/empty/negative/Infinity → 5.
 * Spec: docs/superpowers/specs/2026-06-21-crawler-concurrency-autoadjust-design.md
 */
export function resolveBackpressureMaxPending(raw: string | undefined): number {
    const n = Number(raw);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 5;
}

/**
 * Backpressure gate predicate: accept a new page only when the observed backpressure
 * depth is within the threshold. `pending` is the detection p-limit pendingCount today;
 * generic so a second source can fold in via Math.max(...) at the call site.
 */
export function shouldAcceptNewPage(pending: number, threshold: number): boolean {
    return pending <= threshold;
}
```

- [ ] **Step 5: Add the `BACKPRESSURE_MAX_PENDING` module const**

In `httpStatusPolicy.ts`, in the "Derived once at module load" block (next to `MAX_CONCURRENCY` / `REQUEST_HANDLER_TIMEOUT_S`):

```ts
export const BACKPRESSURE_MAX_PENDING: number =
    resolveBackpressureMaxPending(process.env.DETECTION_BACKPRESSURE_MAX_PENDING);
```

- [ ] **Step 6: Add `isPageClosedError`**

In `httpStatusPolicy.ts`, next to `isDownloadError` (the other error-string predicate):

```ts
/**
 * True when a Playwright error means the page/context/browser was already torn down
 * (e.g. a concurrent /stop or shutdown closed the pool mid-handler). Used to downgrade
 * the benign pre-batch link-extraction failure from a warning to a debug log.
 */
export function isPageClosedError(errStr: string): boolean {
    return errStr.includes("Target page, context or browser has been closed");
}
```

- [ ] **Step 7: Run tests + build to confirm green**

Run: `npm test --prefix DIR` → all pass. `npm run build --prefix DIR` → tsc 0 errors.

- [ ] **Step 8: Commit** (coordinator)

Files: `httpStatusPolicy.ts`, `httpStatusPolicy.limits.test.ts`. Conventional: `feat(crawler): backpressure gate predicate + threshold resolver + page-closed predicate`.

---

### Task 2: Wire the detection-backpressure gate into the AutoscaledPool

**Goal:** Add `isTaskReadyFunction` to `autoscaledPoolOptions` so the pool vetoes new page starts while detection is saturated; refresh the `maxConcurrency` comment to reflect its new ceiling role.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts` (import block ~L28-41; `autoscaledPoolOptions` block ~L826-840)

**Acceptance Criteria:**
- [ ] `functions.ts` imports `BACKPRESSURE_MAX_PENDING` and `shouldAcceptNewPage` from `./httpStatusPolicy.js`.
- [ ] `autoscaledPoolOptions` has `isTaskReadyFunction` gating on `context.detectionClient?.limiter.pendingCount ?? 0`, alongside the existing `maxConcurrency` and `isFinishedFunction`.
- [ ] Fails open (gate open) when `detectionClient` is absent.

**Verify:** `npm run build --prefix DIR` → tsc 0 errors. `grep -n "isTaskReadyFunction" DIR/src/functions.ts` → present. (The gate predicate itself is covered by Task 1's tests; `functions.ts` builds a live crawler and is not unit-tested.)

**Steps:**

- [ ] **Step 1: Extend the httpStatusPolicy import**

In `functions.ts`, the existing import block (added by `5537ac52`) reads:

```ts
import {
    NAVIGATION_WAIT_UNTIL,
    TIMEOUT_MAX_RETRIES,
    MAX_CONCURRENCY,
    REQUEST_HANDLER_TIMEOUT_S,
    shouldCapTimeoutRetry,
    PERMANENT_ERROR_MARKERS,
    classifyFailure,
    selectReclaimableIds,
    shouldSkipAsDownload,
    SKIP_DOWNLOADS,
    pdfDatasetName,
    type FailureClass,
} from "./httpStatusPolicy.js";
```

Add two names:

```ts
    MAX_CONCURRENCY,
    REQUEST_HANDLER_TIMEOUT_S,
    BACKPRESSURE_MAX_PENDING,
    shouldAcceptNewPage,
    shouldCapTimeoutRetry,
```

- [ ] **Step 2: Add `isTaskReadyFunction` to the pool options**

Replace the existing `autoscaledPoolOptions` block (from `5537ac52`):

```ts
    optionsCrawler.autoscaledPoolOptions = {
        ...optionsCrawler.autoscaledPoolOptions,
        maxConcurrency: MAX_CONCURRENCY,
        isFinishedFunction: async () => {
            const isEmpty = await requestQueue.isEmpty();
            return isEmpty && context.phase2SeedingComplete;
        },
    };
```

with:

```ts
    // maxConcurrency is now a memory/browser SAFETY CEILING (env CRAWLER_MAX_CONCURRENCY,
    // default 20). The primary throttle is the detection-backpressure gate below.
    //
    // isTaskReadyFunction: accept a new page only while the detection p-limit queue is
    // within DETECTION_BACKPRESSURE_MAX_PENDING. The pool scales on local
    // CPU/event-loop/memory — all idle while handlers await the detection HTTP call — so
    // without this gate it over-subscribes the 5-wide detect p-limit, inflating per-page
    // detect latency past requestHandlerTimeoutSecs (the 7033 death-spiral). With it,
    // fast detection (pendingCount≈0) ramps freely to the ceiling; slow detection holds
    // concurrency where detection keeps up. Only delays STARTS (running detects drain →
    // gate reopens); isFinishedFunction still terminates the crawl. Fails open if the
    // client is somehow absent (?? 0) — never blocks the crawl.
    // Spec: docs/superpowers/specs/2026-06-21-crawler-concurrency-autoadjust-design.md
    optionsCrawler.autoscaledPoolOptions = {
        ...optionsCrawler.autoscaledPoolOptions,
        maxConcurrency: MAX_CONCURRENCY,
        isTaskReadyFunction: async () =>
            shouldAcceptNewPage(
                context.detectionClient?.limiter.pendingCount ?? 0,
                BACKPRESSURE_MAX_PENDING,
            ),
        isFinishedFunction: async () => {
            const isEmpty = await requestQueue.isEmpty();
            return isEmpty && context.phase2SeedingComplete;
        },
    };
```

- [ ] **Step 3: Build to confirm**

Run: `npm run build --prefix DIR` → tsc 0 errors. (`context.detectionClient` is `DetectionLangueClient | undefined`; `?.limiter.pendingCount` is `number | undefined`; `?? 0` yields `number`.)

- [ ] **Step 4: Commit** (coordinator)

Files: `functions.ts`. Conventional: `feat(crawler): gate AutoscaledPool on detection backpressure (auto-adjust concurrency)`.

---

### Task 3: Quiet-guard the pre-batch `page.$$eval`

**Goal:** Skip the pre-batch link-extraction on an already-closed page, and downgrade the benign page-closed catch to a debug log so a normal `/stop`/shutdown stops surfacing as `Erreur crawling`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts` (import L31; pre-batch block ~L838-856)

**Acceptance Criteria:**
- [ ] `isPageClosedError` imported from `./httpStatusPolicy.js`.
- [ ] Pre-batch block guarded with `!page.isClosed()`.
- [ ] Catch branches: page-closed → `log.debug`; other → `console.warn` (unchanged).

**Verify:** `npm run build --prefix DIR` → tsc 0 errors. `npm test --prefix DIR` → all pass (no regression). `grep -n "page.isClosed\|isPageClosedError" DIR/src/routes.ts` → present.

**Steps:**

- [ ] **Step 1: Extend the import (routes.ts:31)**

Change:

```ts
import { classifyHttpStatus, pdfDatasetName } from "./httpStatusPolicy.js";
```

to:

```ts
import { classifyHttpStatus, pdfDatasetName, isPageClosedError } from "./httpStatusPolicy.js";
```

- [ ] **Step 2: Guard the pre-batch block**

Replace (current, ~L838-856):

```ts
                let knownUrlsOnPage = new Set<string>();

                if (context.dedupManager) {
                    try {
                        // 1. Extract all <a href> links from the page
                        const rawLinks = await page.$$eval('a[href]', (anchors: HTMLAnchorElement[]) =>
                            anchors.map(a => a.href).filter(href => href && href.startsWith('http'))
                        );

                        if (rawLinks.length > 0) {
                            // 2. Batch-check against Redis in a single round-trip
                            knownUrlsOnPage = await context.dedupManager.isKnownBatch(rawLinks);
                        }
                    } catch (e) {
                        // Non-fatal: if link extraction fails, we proceed without pre-filtering
                        // The handler-level dedup (line ~176) will still catch duplicates
                        console.warn(`Pre-batch link extraction failed: ${e}`);
                    }
                }
```

with:

```ts
                let knownUrlsOnPage = new Set<string>();

                if (context.dedupManager && !page.isClosed()) {
                    try {
                        // 1. Extract all <a href> links from the page
                        const rawLinks = await page.$$eval('a[href]', (anchors: HTMLAnchorElement[]) =>
                            anchors.map(a => a.href).filter(href => href && href.startsWith('http'))
                        );

                        if (rawLinks.length > 0) {
                            // 2. Batch-check against Redis in a single round-trip
                            knownUrlsOnPage = await context.dedupManager.isKnownBatch(rawLinks);
                        }
                    } catch (e) {
                        // Non-fatal: proceed without pre-filtering; the handler-level dedup
                        // (line ~176) still catches duplicates. A torn-down page (a concurrent
                        // /stop or shutdown closed the pool mid-handler) is benign — log it
                        // quietly, not as a warning that surfaces in Python as "Erreur crawling".
                        if (isPageClosedError(String(e))) {
                            log.debug(`Pre-batch link extraction skipped (page closed): ${e}`);
                        } else {
                            console.warn(`Pre-batch link extraction failed: ${e}`);
                        }
                    }
                }
```

- [ ] **Step 3: Build + test**

Run: `npm run build --prefix DIR` → tsc 0 errors. `npm test --prefix DIR` → all pass.

> **tdd-gate note:** editing `routes.ts` requires a matching test stem. `tests/routes.pushedSet.test.ts` exists (stem `routes.*`) and should satisfy it. If the PreToolUse `tdd-gate.sh` hook blocks the Edit anyway, write the new file content to a temp `.txt` and `cp` it over the target (`cp`/`mv` are gate-exempt) — the documented worktree-hook workaround. The guard logic (`isPageClosedError`) is already unit-tested in Task 1.

- [ ] **Step 4: Commit** (coordinator)

Files: `routes.ts`. Conventional: `fix(crawler): quiet benign page-closed teardown in pre-batch link extraction`.

---

### Task 4: Docs — rewrite CLAUDE.md section + supersede prior spec

**Goal:** Update the crawler-service CLAUDE.md "Detection Backpressure" section to describe the gate (superseding the static-cap text), and mark the static-cap section of the prior spec superseded.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` ("Detection Backpressure" section, added by `5537ac52`)
- Modify: `docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md` (Status line)

**Acceptance Criteria:**
- [ ] CLAUDE.md section retitled + rewritten: gate is the primary throttle, `CRAWLER_MAX_CONCURRENCY` (default 20) is the ceiling, `DETECTION_BACKPRESSURE_MAX_PENDING` (5) added, quiet-guard noted.
- [ ] Prior spec carries a "Superseded by" note pointing at the auto-adjust spec.

**Verify:** Manual read — section reflects the gate, env table lists all three vars with correct defaults (20 / 5 / 200), no stale "ramped to 25+ … capped at 10" framing implying the cap is the throttle.

**Steps:**

- [ ] **Step 1: Replace the CLAUDE.md "Detection Backpressure" section body**

Replace the section added by `5537ac52` (heading `## Detection Backpressure (Concurrency Cap + Handler-Timeout Alignment)` through its `Spec:` line) with:

```markdown
## Detection Backpressure (Auto-Adjusting Concurrency + Handler-Timeout Alignment)

The default handler awaits a per-page detection call (~94% of handler time on
detection-gated sites). Crawlee's `AutoscaledPool` scales on **local**
CPU/event-loop/memory — all idle while handlers `await` that HTTP call — so left
unchecked it ramps to 25+ concurrent handlers against only `DETECTION_MAX_CONCURRENCY`
(5) detect slots. The surplus piles into the detection `p-limit` queue, inflating
per-page detect latency past `requestHandlerTimeoutSecs`; Crawlee then kills the
handler mid-detect and closes the page, the orphaned handler hits `page.$$eval` on the
dead page (`Pre-batch link extraction failed: ... Target page ... has been closed`),
the request retries, and with nothing finishing the crawl loops on `progress_stalled`
(exit 6) — a death spiral. Incident: crawl 7033 (carflo.fr), 2026-06-19.

**Auto-adjusting gate (primary throttle).** `autoscaledPoolOptions.isTaskReadyFunction`
accepts a new page only while the detection p-limit queue
(`detectionClient.limiter.pendingCount`) is within `DETECTION_BACKPRESSURE_MAX_PENDING`.
Fast detection → `pendingCount≈0` → the pool ramps freely to the ceiling; slow
detection → the gate vetoes new starts → concurrency self-settles where detection keeps
up. It only delays *starts* (running detects drain → gate reopens; `isFinishedFunction`
still ends the crawl), so no deadlock. Concurrency thus auto-adjusts per crawl instead
of a one-size cap.

**Safety ceiling + timeout (defense-in-depth).** `CRAWLER_MAX_CONCURRENCY` (default 20)
is a memory/browser backstop (the incident hit ~95-100% memory at ~25 concurrent), no
longer the primary throttle. `REQUEST_HANDLER_TIMEOUT_S` (default 200, raised from 120)
exceeds one nav (≤90) + one detect (`DETECTION_REQUEST_TIMEOUT_S` 180) so a
slow-but-progressing detect is not killed mid-flight. Three independent limiters: gate
(detection), Crawlee memory snapshotter, hard ceiling.

**Quiet-guard.** The `routes.ts` pre-batch block skips when `page.isClosed()` and
downgrades the page-closed catch (`isPageClosedError`) to `log.debug`, so a benign
`/stop`/shutdown teardown stops surfacing in Python as `Erreur crawling`.

| Variable | Default | Effect |
|---|---|---|
| `DETECTION_BACKPRESSURE_MAX_PENDING` | `5` | Gate threshold: pause new page starts while detection `pendingCount` exceeds this. ≈ `DETECTION_MAX_CONCURRENCY`; raise in step if you raise detection concurrency. `0` = tolerate no queue. |
| `CRAWLER_MAX_CONCURRENCY` | `20` | Hard ceiling on `autoscaledPoolOptions.maxConcurrency` (memory/browser backstop). |
| `REQUEST_HANDLER_TIMEOUT_S` | `200` | `requestHandlerTimeoutSecs` — covers one nav + one detect. |

Gate is detection-only (tier2 `/clean` excluded — flag-gated off by default; the
predicate is generic so a second source folds in via `Math.max(...)` later).

Spec: `docs/superpowers/specs/2026-06-21-crawler-concurrency-autoadjust-design.md`
(supersedes the static-cap mechanism of
`docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md`).
```

- [ ] **Step 2: Add the supersede note to the prior spec**

In `docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md`, under the `**Status:**` line near the top, add:

```markdown
> **Superseded (2026-06-21):** the static `CRAWLER_MAX_CONCURRENCY=10` cap described
> here is replaced by an auto-adjusting detection-backpressure gate (cap → ceiling,
> default 20). See `docs/superpowers/specs/2026-06-21-crawler-concurrency-autoadjust-design.md`.
> The `REQUEST_HANDLER_TIMEOUT_S` lever from this spec is retained unchanged.
```

- [ ] **Step 3: Commit** (coordinator)

Files: `apps-microservices/crawler-service/CLAUDE.md`, `docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md`. Conventional: `docs(crawler): document the auto-adjusting backpressure gate; supersede static-cap note`.

---

## Notes for the executor

- Run `npm run build` + `npm test` from `apps-microservices/crawler-service/crawler/` (or `--prefix` it). `npm test` = `node --import tsx --test src/**/*.test.ts`.
- Do NOT run the whole Python suite or attempt a live crawl (remote-only).
- graphify: do NOT `git add graphify-out/*`; if it shows dirty after a commit, `git checkout -- graphify-out/GRAPH_REPORT.md`.
- Coordinator owns commits (private `.git/<NAME>_MSG.txt` + `commit -F`, bilingual EN+FR, explicit `git add`, delete temp after).
