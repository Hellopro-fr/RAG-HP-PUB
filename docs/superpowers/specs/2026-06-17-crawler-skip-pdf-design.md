# Crawler — Skip download/PDF pages (fast-fail, no stall)

**Date:** 2026-06-17
**Service:** `apps-microservices/crawler-service` (Node.js/Crawlee engine)
**Status:** Design approved — ready for implementation plan
**Author:** Rindra ANDRIANJANAKA (with Claude)

## Problem

The crawler wastes time and stalls on URLs that serve a downloadable file
(PDF, etc.) at an **extension-less path**, e.g.
`https://www.caravi.com/produit/pdf/pro_id/85`.

Observed log:

```
WARN  PlaywrightCrawler: Reclaiming failed request back to the list or queue. page.goto: Download is starting
{"id":"0VNJzzQX58ke0BG","url":"https://www.caravi.com/produit/pdf/pro_id/85","retryCount":1}
...
ERROR PlaywrightCrawler: Request https://www.caravi.com/produit/pdf/pro_id/85 failed: page.goto: Download is starting
```

### Root cause

1. `page.goto` throws `"Download is starting"` **during navigation**, before the
   request handler runs — so the in-handler Content-Type guard
   (`routes.ts:311-318`) never executes.
2. The URL has no `.pdf` extension, so the `enqueueLinks` extension glob
   (`**/*.@(${ignoredExtensions})...`) does not exclude it.
3. There is **no Crawlee `errorHandler`**. `"Download is starting"` is already in
   `PERMANENT_ERROR_MARKERS` (`httpStatusPolicy.ts:87`) and
   `failedRequestHandler` sets `request.noRetry` for permanent markers
   (`functions.ts:562-566`) — but `failedRequestHandler` is **terminal** (runs
   only after retries are exhausted), so it cannot prevent the retry storm.
   With `maxRequestRetries:5` + `navigationTimeoutSecs:90`, each download URL
   burns multiple navigations; a site with many product PDFs clogs the worker
   pool → stall.

Inline PDFs (rendered in-browser, no download trigger) are **already** handled by
the Content-Type guard at `routes.ts:311`; the gap is strictly the
**download-triggering** case.

## Goals

- Skip download/PDF pages without retries and without stalling the crawl.
- Do not pollute error metrics or trip the circuit breaker.
- Persist the skipped URLs so a future "download them" feature has the list.
- Default-on, with an env kill-switch.

## Non-goals (out of scope)

- Actually downloading/storing PDFs (future feature; this spec only leaves the hook).
- The `Redis Stats — SocketClosedUnexpectedlyError` issue (StatsManager owns a
  separate Redis client; a known deferred follow-up) — **separate spec**.

## Decisions (from brainstorm)

- **Skip cost:** fast-fail — one quick navigation allowed, detected, cancelled,
  marked skipped, never retried. (Zero-navigation HEAD pre-check and URL-pattern
  blocklists were rejected: extra round-trip on every URL / fragile + site-specific.)
- **Accounting:** dedicated counter **plus** a persisted URL list.
- **Approach A:** `errorHandler` + `page.on('download')` cancel safety-net +
  unified PDF accounting, default-on with env flag. (Response-interception
  hardening deferred.)

## Design

### §1 Detection & skip

- **`isDownloadError(errorStr: string): boolean`** — new pure predicate in
  `httpStatusPolicy.ts`. Returns true when `errorStr` contains
  `"Download is starting"`. Single source of truth, unit-testable. (Keeps the
  existing `PERMANENT_ERROR_MARKERS` entry; the predicate is the named, reusable
  form consumed by the handlers below.)

- **New Crawlee `errorHandler`** in the crawler config (`functions.ts`, alongside
  `failedRequestHandler`):
  ```
  errorHandler: async ({ request }, error) => {
      if (SKIP_DOWNLOADS && isDownloadError(String(error))) {
          request.noRetry = true;   // stop retries BEFORE Crawlee reclaims
      }
  }
  ```
  `errorHandler` runs after each failed attempt and before the retry decision —
  this is the mechanism that actually prevents the retry storm.

- **Download-cancel safety-net** — add to `preNavigationHooks` (`functions.ts`):
  ```
  async ({ page }) => {
      page.on('download', d => { d.cancel().catch(() => {}); });
  }
  ```
  Ensures a started download is never held open (prevents the stall regardless of
  `page.goto` throw timing). One listener per page; pages are per-request
  (`retireBrowserAfterPageCount:25`).

- **Env flag `SKIP_DOWNLOADS`** — default `true`; only `"false"` disables (revert
  to current behavior). Resolved once at module load, Node-only, inherited by the
  subprocess. Mirrors `RECOVER_FAILED_ON_RESTART` / `NAVIGATION_WAIT_UNTIL`.

### §2 Accounting & persistence (circuit-breaker-safe)

In `failedRequestHandler`, branch **at the top**, before the existing
captcha/challenge/`errors` logic:

```
if (SKIP_DOWNLOADS && isDownloadError(errorStr)) {
    if (context.statsManager) await context.statsManager.increment("filtered_pdf");
    const ds = await Dataset.open(`pdf-${crawleeStorageName ?? domain}`);
    await ds.pushData({
        url: request.url,
        source: request.userData.source ?? "",
        status: response?.status() ?? 0,
        timestamp: new Date().toISOString(),
    });
    return; // skip captcha/processPage AND the error-{domain} write below
}
```

- The branch is gated by `SKIP_DOWNLOADS`: when disabled, a download error falls
  through to the existing error path (retried, counted as `errors`) — exact
  current behavior.
- **`filtered_pdf`** is a new metric. `StatsManager.increment` accepts any key, so
  no schema change is needed. It is **not** `errors` → the circuit breaker
  (which keys on `errors`/`redirects`/`new_urls`) is never tripped by PDFs.
- **`pdf-{domain}` dataset** mirrors the existing `error-{domain}` / `nfr-{domain}`
  pattern: works in both standard and update modes, and is archived with the crawl.
- **No restart re-crawl:** because the branch returns *before* the
  `error-{domain}` `pushData`, the skipped PDF is never written to the error
  dataset, so `reclaimFailedRequest` (which reads only `error-{domain}`) inherently
  never re-queues it on a same-id restart — no `failure_class` bookkeeping needed.

`main.ts` webhook payload: add `const filtered_pdf = await readStat("filtered_pdf")`
and include `filtered_pdf` in the payload object (alongside `filtered_ext` etc.).
Additive field → BO PHP ignores unknown keys → backward-compatible.

**Update-mode semantics:** a download/PDF never reaches `UpdateChecker`, so it is
neither `deleted` nor `confirmed` — it is simply *ignored* and recorded under
`filtered_pdf` + `pdf-{domain}`.

### §3 Unify the inline-PDF path + future hook

- The Content-Type guard at `routes.ts:311-318` (inline PDFs that render rather
  than download) gets the **same** accounting before its `return`:
  `filtered_pdf`++ and a `pdf-{domain}` row. So all PDFs are counted uniformly
  regardless of download-vs-inline. This guard already skips inline non-HTML today,
  so its accounting is independent of `SKIP_DOWNLOADS` (it reflects existing
  behavior; the flag only governs the new download-error path in §1/§2).
- **Future "download them" extension point:** the `pdf-{domain}` dataset is the
  list a future download mode consumes; `SKIP_DOWNLOADS` is the switch that flips
  skip → download. No download infrastructure is built now.

### §4 Tests & blast radius

**Tests** (pure-function style — `routes.ts`/`main.ts`/`functions.ts` are not
importable by the test runner; follows `routes.pushedSet.test.ts` precedent):
- `isDownloadError` truth table (matches `"Download is starting"`, rejects
  unrelated errors).
- errorHandler decision model: `isDownloadError && SKIP_DOWNLOADS` → noRetry.
- accounting branch model: download error → `filtered_pdf` (not `errors`),
  `pdf-{domain}` row written, early return.
- Verify: `npm run build && npm test` in `crawler/`.

**Blast radius:** entirely within `crawler-service`:
- `crawler/src/httpStatusPolicy.ts` — add `isDownloadError` + `SKIP_DOWNLOADS`.
- `crawler/src/functions.ts` — add `errorHandler`, download-cancel preNav hook,
  `failedRequestHandler` download branch.
- `crawler/src/routes.ts` — Content-Type guard accounting.
- `crawler/src/main.ts` — `filtered_pdf` readStat + payload field.

No shared libs, no proto, no gateway change. One additive webhook field.
**Deploy:** rebuild + redeploy the crawler Docker image.

## Rollout

1. Implement + `npm run build && npm test`.
2. Deploy crawler image (default `SKIP_DOWNLOADS=true`).
3. Validate on caravi.com: expect no `Reclaiming ... Download is starting` storm,
   PDF URLs recorded under `filtered_pdf` + the `pdf-{domain}` dataset, crawl no
   longer stalling on the product PDFs.
4. Kill-switch: set `SKIP_DOWNLOADS=false` to revert.

## Open questions

None — design approved.
