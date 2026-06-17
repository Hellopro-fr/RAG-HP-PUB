# Crawler — Skip download/PDF pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fast-fail skip of download-triggering URLs (extension-less PDFs that throw `"Download is starting"`) so they stop burning retries and stalling the crawl.

**Architecture:** A Crawlee `errorHandler` sets `request.noRetry` the instant a download trigger is seen (stops the retry storm that the terminal `failedRequestHandler` cannot). A `preNavigationHook` cancels any started download (kills the stall). The `failedRequestHandler` records the skip under a new `filtered_pdf` stat + a `pdf-{domain}` dataset and returns before the error path (no circuit-breaker trip, no restart re-crawl). The inline-PDF Content-Type guard in `routes.ts` gets the same accounting. All gated by env `SKIP_DOWNLOADS` (default on). Pure predicates live in `httpStatusPolicy.ts` (DRY, unit-testable).

**Tech Stack:** Node.js 22, TypeScript, Crawlee 3 / Playwright, `node:test` runner (`src/**/*.test.ts`).

**Spec:** `docs/superpowers/specs/2026-06-17-crawler-skip-pdf-design.md`

**Branch:** `features/poc` (no worktree). All paths relative to `apps-microservices/crawler-service/crawler/`.

**Commit messages:** Conventional Commits, bilingual EN+FR per project rule — confirm language before each commit.

---

## File Structure

| File | Responsibility | Change |
|------|---------------|--------|
| `src/httpStatusPolicy.ts` | Pure policy predicates (SoT) | Add `isDownloadError`, `resolveSkipDownloads`, `SKIP_DOWNLOADS`, `shouldSkipAsDownload`, `pdfDatasetName` |
| `src/functions.ts` | Crawler config (handlers, hooks) | Add `errorHandler`, download-cancel preNav hook, `failedRequestHandler` download branch |
| `src/routes.ts` | Page request handler | Content-Type guard: unified `filtered_pdf` accounting |
| `src/main.ts` | Webhook payload assembly | Surface `filtered_pdf` in payload |
| `src/tests/httpStatusPolicy.download.test.ts` | Unit tests for the new predicates | Create |
| `src/tests/skipDownload.handler.test.ts` | Model test for the handler branch ordering | Create |

---

### Task 1: Download-skip predicates in httpStatusPolicy.ts

**Goal:** Add the pure, testable building blocks (`isDownloadError`, `resolveSkipDownloads`, `SKIP_DOWNLOADS`, `shouldSkipAsDownload`, `pdfDatasetName`) consumed by Tasks 2–3.

**Files:**
- Modify: `src/httpStatusPolicy.ts` (append a new section at end of file)
- Test: `src/tests/httpStatusPolicy.download.test.ts` (create)

**Acceptance Criteria:**
- [ ] `isDownloadError` true only when the error contains `"Download is starting"`.
- [ ] `resolveSkipDownloads` defaults true; only `"false"` (case/space-insensitive) disables.
- [ ] `shouldSkipAsDownload(flag, errorStr)` = `flag && isDownloadError(errorStr)`.
- [ ] `pdfDatasetName` prefers `crawleeStorageName`, falls back to `domain`.

**Verify:** `node --import tsx --test src/tests/httpStatusPolicy.download.test.ts` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test** — create `src/tests/httpStatusPolicy.download.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    isDownloadError,
    resolveSkipDownloads,
    shouldSkipAsDownload,
    pdfDatasetName,
} from '../httpStatusPolicy.js';

test('isDownloadError matches the Playwright download trigger', () => {
    assert.equal(isDownloadError('page.goto: Download is starting'), true);
    assert.equal(isDownloadError('Error: Download is starting\nCall log: ...'), true);
});

test('isDownloadError rejects unrelated errors', () => {
    assert.equal(isDownloadError('Navigation timed out after 90000ms'), false);
    assert.equal(isDownloadError('net::ERR_NAME_NOT_RESOLVED'), false);
    assert.equal(isDownloadError(''), false);
});

test('resolveSkipDownloads defaults true; only "false" disables', () => {
    assert.equal(resolveSkipDownloads(undefined), true);
    assert.equal(resolveSkipDownloads(''), true);
    assert.equal(resolveSkipDownloads('true'), true);
    assert.equal(resolveSkipDownloads('false'), false);
    assert.equal(resolveSkipDownloads('FALSE'), false);
    assert.equal(resolveSkipDownloads(' false '), false);
});

test('shouldSkipAsDownload requires both the flag and a download error', () => {
    assert.equal(shouldSkipAsDownload(true, 'Download is starting'), true);
    assert.equal(shouldSkipAsDownload(false, 'Download is starting'), false);
    assert.equal(shouldSkipAsDownload(true, 'Navigation timed out'), false);
});

test('pdfDatasetName prefers crawleeStorageName, falls back to domain', () => {
    assert.equal(pdfDatasetName('store-1', 'caravi.com'), 'pdf-store-1');
    assert.equal(pdfDatasetName(undefined, 'caravi.com'), 'pdf-caravi.com');
    assert.equal(pdfDatasetName('', 'caravi.com'), 'pdf-caravi.com');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --import tsx --test src/tests/httpStatusPolicy.download.test.ts`
Expected: FAIL — `isDownloadError`/`resolveSkipDownloads`/`shouldSkipAsDownload`/`pdfDatasetName` are not exported.

- [ ] **Step 3: Write minimal implementation** — append to the END of `src/httpStatusPolicy.ts`:

```ts

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --import tsx --test src/tests/httpStatusPolicy.download.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/httpStatusPolicy.ts src/tests/httpStatusPolicy.download.test.ts
git commit -m "feat(crawler): download-skip predicates in httpStatusPolicy"
```

---

### Task 2: Wire fast-fail skip into the crawler (functions.ts)

**Goal:** Stop retries on download errors, cancel started downloads, and record the skip under `filtered_pdf` + `pdf-{domain}` without counting it as an error.

**Files:**
- Modify: `src/functions.ts` — import block (lines 28-36); add `errorHandler` (before line 554); add download-cancel preNav hook (after line 701); add download branch in `failedRequestHandler` (after line 561)
- Test: `src/tests/skipDownload.handler.test.ts` (create — models the branch ordering)

**Acceptance Criteria:**
- [ ] An `errorHandler` sets `request.noRetry = true` when `shouldSkipAsDownload(SKIP_DOWNLOADS, String(error))`.
- [ ] A preNav hook registers `page.on('download', d => d.cancel())` when `SKIP_DOWNLOADS`.
- [ ] `failedRequestHandler` increments `filtered_pdf` (not `errors`), writes to `pdf-{domain}`, and returns before the permanent-error / error-dataset logic.
- [ ] When `SKIP_DOWNLOADS=false`, a download error falls through to the existing error path.

**Verify:** `npm run build && node --import tsx --test src/tests/skipDownload.handler.test.ts` → build clean, tests pass.

**Steps:**

- [ ] **Step 1: Write the model test** — create `src/tests/skipDownload.handler.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldSkipAsDownload } from '../httpStatusPolicy.js';

/**
 * Models the failedRequestHandler branch ordering (functions.ts): a download
 * error increments filtered_pdf + writes the pdf dataset and returns BEFORE the
 * errors counter / error-{domain} dataset path. Mirrors the routes.pushedSet.test
 * pattern (functions.ts is not importable by the test runner).
 */
function simulateFailedRequest(errorStr: string, skipDownloads: boolean, isExisting: boolean) {
    const counters = { filtered_pdf: 0, errors: 0 };
    const datasets = { pdf: [] as string[], error: [] as string[] };
    if (shouldSkipAsDownload(skipDownloads, errorStr)) {
        counters.filtered_pdf++;
        datasets.pdf.push('row');
        return { counters, datasets }; // early return — no error accounting
    }
    if (isExisting) counters.errors++;
    datasets.error.push('row');
    return { counters, datasets };
}

test('download error → filtered_pdf + pdf dataset, no errors, no error dataset', () => {
    const r = simulateFailedRequest('page.goto: Download is starting', true, true);
    assert.equal(r.counters.filtered_pdf, 1);
    assert.equal(r.counters.errors, 0);
    assert.deepEqual(r.datasets.pdf, ['row']);
    assert.deepEqual(r.datasets.error, []);
});

test('SKIP_DOWNLOADS=false → download error falls through to error path', () => {
    const r = simulateFailedRequest('Download is starting', false, true);
    assert.equal(r.counters.filtered_pdf, 0);
    assert.equal(r.counters.errors, 1);
    assert.deepEqual(r.datasets.error, ['row']);
});

test('non-download error → normal error path', () => {
    const r = simulateFailedRequest('Navigation timed out', true, true);
    assert.equal(r.counters.filtered_pdf, 0);
    assert.equal(r.counters.errors, 1);
});
```

- [ ] **Step 2: Run test to verify it passes** (predicate already exists from Task 1)

Run: `node --import tsx --test src/tests/skipDownload.handler.test.ts`
Expected: PASS (3 tests). This locks the contract Task 2's wiring must satisfy.

- [ ] **Step 3: Extend the httpStatusPolicy import** — replace the import block at `src/functions.ts:28-36`:

```ts
import {
    NAVIGATION_WAIT_UNTIL,
    TIMEOUT_MAX_RETRIES,
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

- [ ] **Step 4: Add the `errorHandler`** — insert immediately BEFORE the `// V3 Logic: Rich error reporting` comment at `src/functions.ts:554` (i.e. as a sibling field of `failedRequestHandler`):

```ts
        // Fast-fail download/PDF skip: stop retries the moment a download trigger
        // is seen. errorHandler runs after each failed attempt and BEFORE the retry
        // decision — failedRequestHandler is terminal and cannot prevent retries.
        // Spec: docs/superpowers/specs/2026-06-17-crawler-skip-pdf-design.md
        errorHandler: async ({ request }, error) => {
            if (shouldSkipAsDownload(SKIP_DOWNLOADS, String(error))) {
                request.noRetry = true;
            }
        },

```

- [ ] **Step 5: Add the download branch in `failedRequestHandler`** — insert immediately AFTER `const errorStr = String(request.errorMessages);` (`src/functions.ts:561`), before `const isPermanentError = ...`:

```ts

            // Download/PDF skip: a download-triggering URL (e.g. extension-less PDF)
            // is recorded under filtered_pdf + the pdf-{domain} dataset and returns
            // early — NOT counted as an error (no circuit-breaker trip) and NOT
            // written to error-{domain} (so reclaimFailedRequest never re-crawls it).
            // Spec: docs/superpowers/specs/2026-06-17-crawler-skip-pdf-design.md
            if (shouldSkipAsDownload(SKIP_DOWNLOADS, errorStr)) {
                if (context.statsManager) {
                    await context.statsManager.increment("filtered_pdf");
                }
                const pdfDataset = await Dataset.open(
                    pdfDatasetName(context.config.crawleeStorageName, domain),
                );
                await pdfDataset.pushData({
                    url: request.url,
                    source: request.userData.source ?? "",
                    status: response?.status() ?? 0,
                    timestamp: new Date().toISOString(),
                });
                log.info(`Skipped download/PDF (no retry): ${request.url}`);
                return;
            }
```

- [ ] **Step 6: Add the download-cancel preNav hook** — insert as a new array entry immediately AFTER the `waitUntil` hook that ends at `src/functions.ts:701` (the `},` closing the first preNavigation hook), before the `async ({ page }) => { const isStopped ... }` hook:

```ts
            // Cancel any download the navigation triggers so the browser context
            // never holds a partial download (prevents the crawl stalling on
            // download/PDF URLs). The download error itself is fast-failed via
            // errorHandler above. Gated by SKIP_DOWNLOADS.
            async ({ page }) => {
                if (SKIP_DOWNLOADS) {
                    page.on('download', (d) => { d.cancel().catch(() => {}); });
                }
            },
```

- [ ] **Step 7: Build + run tests**

Run: `npm run build && node --import tsx --test src/tests/skipDownload.handler.test.ts`
Expected: `tsc` clean; 3 tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/functions.ts src/tests/skipDownload.handler.test.ts
git commit -m "feat(crawler): fast-fail skip of download/PDF pages (errorHandler + cancel + accounting)"
```

---

### Task 3: Unify inline-PDF accounting in routes.ts

**Goal:** Inline (rendered) PDFs caught by the Content-Type guard get the same `filtered_pdf` + `pdf-{domain}` accounting as download-triggering ones.

**Files:**
- Modify: `src/routes.ts:27` (import) and `src/routes.ts:311-318` (Content-Type guard)

**Acceptance Criteria:**
- [ ] The Content-Type guard increments `filtered_pdf` and writes a `pdf-{domain}` row before returning.
- [ ] Accounting is independent of `SKIP_DOWNLOADS` (the guard already skips inline non-HTML today).
- [ ] `npm run build` clean; full suite (`npm test`) still green.

**Verify:** `npm run build && npm test` → build clean, all tests pass (no regressions).

**Steps:**

- [ ] **Step 1: Extend the import** — replace `src/routes.ts:27`:

```ts
import { classifyHttpStatus, pdfDatasetName } from "./httpStatusPolicy.js";
```

- [ ] **Step 2: Add accounting to the Content-Type guard** — replace the block at `src/routes.ts:313-319`:

```ts
        if (response) {
            const contentType = (response.headers()['content-type'] || '').toLowerCase();
            if (contentType && !contentType.includes('text/html') && !contentType.includes('text/plain') && !contentType.includes('application/xhtml')) {
                // Unified PDF/download accounting (mirrors functions.ts failedRequestHandler):
                // count under filtered_pdf + record in the pdf-{domain} dataset so inline
                // (rendered) PDFs are tracked the same as download-triggering ones. This guard
                // already skips inline non-HTML today, so accounting is independent of SKIP_DOWNLOADS.
                if (context.statsManager) {
                    await context.statsManager.increment("filtered_pdf");
                }
                const pdfDataset = await Dataset.open(
                    pdfDatasetName(context.config.crawleeStorageName, targetDomain),
                );
                await pdfDataset.pushData({
                    url,
                    source: request.userData.source ?? "",
                    status: response.status(),
                    content_type: contentType,
                    timestamp: new Date().toISOString(),
                });
                log.warning(`Skipping non-HTML response: ${url} (Content-Type: ${contentType})`);
                return;
            }
        }
```

Note: `Dataset` and `context` are already imported; `url` (= `request.loadedUrl`), `targetDomain`, `request`, `log` are all in handler scope. This is the only change in the file. (routes.ts is not importable by the test runner — verification is build + no-regression of the existing suite.)

- [ ] **Step 3: Build + full suite**

Run: `npm run build && npm test`
Expected: `tsc` clean; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/routes.ts
git commit -m "feat(crawler): unify inline-PDF accounting with filtered_pdf + pdf dataset"
```

---

### Task 4: Surface filtered_pdf in the webhook payload (main.ts)

**Goal:** Expose `filtered_pdf` in the crawl-complete webhook payload alongside the other `filtered_*` counters.

**Files:**
- Modify: `src/main.ts` (after line 991 `readStat`; after line 1016 payload field)

**Acceptance Criteria:**
- [ ] `filtered_pdf` is read via `readStat` and included in the `payload` object.
- [ ] `npm run build` clean; `npm test` green.

**Verify:** `npm run build && npm test` → clean; then `grep -n "filtered_pdf" src/main.ts` shows the readStat + payload lines.

**Steps:**

- [ ] **Step 1: Add the readStat** — insert immediately AFTER `src/main.ts:991` (`const filtered_duplicate = await readStat("filtered_duplicate");`):

```ts
    const filtered_pdf = await readStat("filtered_pdf");
```

- [ ] **Step 2: Add to the payload object** — insert immediately AFTER the `filtered_duplicate,` line (`src/main.ts:1016`) inside the `payload` object:

```ts
        filtered_pdf,
```

- [ ] **Step 3: Build + full suite**

Run: `npm run build && npm test`
Expected: `tsc` clean; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/main.ts
git commit -m "feat(crawler): expose filtered_pdf in crawl webhook payload"
```

---

## Final Verification

- [ ] `npm run build` → clean (run from `apps-microservices/crawler-service/crawler/`).
- [ ] `npm test` → all tests pass (existing + `httpStatusPolicy.download.test.ts` + `skipDownload.handler.test.ts`).
- [ ] `grep -rn "filtered_pdf\|pdfDatasetName\|SKIP_DOWNLOADS\|isDownloadError" src/` → references in httpStatusPolicy.ts, functions.ts, routes.ts, main.ts only.

## Deploy & Live Validation (post-merge, operator)

1. Rebuild + redeploy the crawler Docker image (default `SKIP_DOWNLOADS=true`).
2. Run a crawl on `caravi.com`. Expect: no `Reclaiming failed request ... Download is starting` storm; PDF URLs counted under `filtered_pdf`; a `pdf-{domain}` dataset populated; the crawl no longer stalling on product PDFs.
3. Kill-switch: set `SKIP_DOWNLOADS=false` to revert.

## Out of Scope

- Actually downloading/storing PDFs (future feature — `pdf-{domain}` dataset is the input it will read).
- The `Redis Stats — SocketClosedUnexpectedlyError` (StatsManager's own Redis client) — separate spec.
