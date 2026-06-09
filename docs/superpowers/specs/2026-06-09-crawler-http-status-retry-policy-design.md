# Crawler HTTP Status & Navigation Retry Policy — Design

- **Date:** 2026-06-09
- **Service:** `apps-microservices/crawler-service` (Node.js / Crawlee 3 / Playwright crawler engine)
- **Status:** Approved design (brainstorming) → ready for plan
- **Scope owner:** crawler engine (`crawler/src/`). No Python orchestrator or BO change.

## 1. Problem

During crawls, dead/heavy pages waste up to ~9 minutes each and genuine 404s are
never recognized as 404. Observed log (crawl example, `planet-loisir-equipement.fr`):

```
WARN PlaywrightCrawler: Reclaiming failed request back to the list or queue.
Navigation timed out after 90 seconds.
{"id":"SusPEKwrnelwNRy","url":"https://www.planet-loisir-equipement.fr/basketball/426-but-de-basket-a-sceller-.html","retryCount":3}
```

Reported as "the crawler retries a 404." Investigation showed the deeper truth:
the URL **is** a genuine 404, but the crawler times out instead of detecting it,
then retries the timeout. The reported symptom (timeout) and the unrecognized-404
are the **same root cause**.

### 1.1 Evidence — the URL is a real 404, served fast

Live probe (Firefox UA), 2026-06-09:

```
HTTP/1.1 404 Not Found    Server: Apache/2.4.67 (Debian)    Transfer-Encoding: chunked
[GET status=404 time=7.2s size=247418 bytes]   [HEAD status=404 time=3.0s]   [ROOT status=200]
```

A genuine `404`, returned in 3–7 s, but as a **247 KB fully-styled HTML page**
(full site chrome: menus, carousels, scripts, third-party trackers). Root domain
is alive (`200`).

### 1.2 Root cause chain (all evidence from the installed Crawlee 3 source)

| # | Step | Evidence |
|---|------|----------|
| 1 | Crawler navigates via `page.goto(url, {timeout:90000})` with **no `waitUntil`** → Playwright default `'load'` | `node_modules/@crawlee/playwright/internals/utils/playwright-utils.js:165` (`gotoExtended` → `page.goto(url, gotoOptions)`); `@crawlee/browser/internals/browser-crawler.js:326` (`gotoOptions = { timeout }` only) |
| 2 | `'load'` waits for the window **load event** = main document **plus all sub-resources** (images, JS, fonts, trackers). One sub-resource on this heavy 404 page never completes → `load` never fires | Playwright navigation semantics |
| 3 | 90 s elapses → `page.goto` **rejects** `TimeoutError`; `crawlingContext.response` is never assigned | `browser-crawler.js:333-339` (`_handleNavigation` try/catch → `_handleNavigationTimeout`) |
| 4 | `_responseHandler` — the only reader of `response.status()` for the blocked throw — runs at `:262`, **after** a *successful* `_handleNavigation` (`:260`). On a timeout it is never reached → the `404` status is never inspected | `browser-crawler.js:258-264, 375-388` |
| 5 | `TimeoutError` is retryable → retried up to `maxRequestRetries: 5`. The `NON_RETRYABLE_ERRORS` list (DNS/SSL/redirect) does **not** include navigation timeouts → all 5 retries burn ≈ 6 × 90 s ≈ **9 min** on one dead 404 | `functions.ts:533, 547-555` |

**Why `curl` saw the 404 but the crawler does not:** `curl` fetches only the main
document (done in 7 s) — it never loads sub-resources or waits for `load`. The
browser does → it hangs on the hanging asset. Both status checks (Crawlee's
`blockedStatusCodes` AND the redundant `routes.ts:322`) are downstream of a
**resolved** navigation — neither fires on a timeout.

### 1.3 Secondary findings (confirmed)

- **`blockedStatusCodes` is misused for permanent codes.** `functions.ts:538`
  overrides Crawlee's default (`[401, 403, 429]`) to
  `[401, 403, 429, 404, 410, 423, 502, 500, 503]`. Crawlee treats this list as
  "we got blocked → retire session + retry." So even when a 404 *does* resolve
  normally, it is retried 5× — wrong for permanent codes (404/410).
  - Mechanism: `_responseHandler` → `_throwOnBlockedRequest`
    (`browser-crawler.js:383`) → `session.retireOnBlockedStatusCodes(status)`
    (`@crawlee/core/session_pool/session.js:238-246`) → if blocked,
    `throw new Error("Request blocked - received {status} status code.")`
    (`@crawlee/basic/internals/basic-crawler.js:910-913`), a **retryable** error.
- **`routes.ts:320-340` is dead code for those 9 codes.** `_responseHandler`
  (`:262`) throws before `_runRequestHandler` (`:226`, the router) runs. The
  manual re-check of the same 9 codes is unreachable for them.
- **Codes NOT in the list are processed as valid content.** A `504`/`408`/`52x`
  error page is handed to the request handler and run through detection/extraction
  as if it were a real page. Single consumer confirmed: `blockedStatusCodes`
  appears only at `functions.ts:538`; no other `.retire()`/`markBad()` in
  `crawler/src`.

## 2. Goals / Non-goals

**Goals**
1. Make HTTP status codes visible to the crawler on heavy/slow pages (kill the
   "navigation never completes" failure).
2. Stop retrying permanently-failed pages (404/410/…). Fail once.
3. Handle currently-uncaught codes (504/408/52x/…) deliberately.
4. One status-policy source of truth in `routes.ts`.
5. Cap wasted retries on genuinely-unresponsive URLs (navigation timeouts).

**Non-goals (explicitly out of scope)**
- Soft-404 detection (HTTP 200 + "not found" body) — needs content heuristics.
- Challenge/anti-bot resolution (`waitForChallengeResolution`,
  `detectChallengePage`) — unchanged.
- The `NON_RETRYABLE_ERRORS` DNS/SSL/redirect list — unchanged.
- Python orchestrator / BO / webhook contracts — unchanged.

## 3. Design

Five coordinated changes, all in the crawler engine.

### 3.1 Navigation lever — `waitUntil: 'domcontentloaded'`

Inject the navigation wait condition via a `preNavigationHook` (the second hook
arg `gotoOptions` is passed straight to `page.goto`):

```ts
// functions.ts — new preNavigationHook (added to the existing array, functions.ts:667)
async (_crawlingContext: PlaywrightCrawlingContext, gotoOptions) => {
    // Resolve navigation as soon as the DOM is parsed, NOT when every
    // sub-resource finishes. The default 'load' hangs for the full
    // navigationTimeoutSecs on heavy pages whose trackers/lazy assets never
    // settle (hides the HTTP status behind a never-completing navigation).
    // Content completeness is handled post-navigation by processPage/waitAndScroll
    // (functions.ts:80, bounded networkidle wait + scroll), so this does not
    // reduce extracted content.
    if (gotoOptions) gotoOptions.waitUntil = NAVIGATION_WAIT_UNTIL;
},
```

- `goto` resolves on DOM-parsed (~7 s for the example 404) → `response` and
  `response.status()` become available to `_responseHandler` and the request
  handler.
- **Gate cleared:** content acquisition is decoupled from `goto`. `processPage`
  (`functions.ts:135`) → `waitAndScroll` (`functions.ts:70`) does its own
  **bounded** settle: `page.waitForLoadState("networkidle", {timeout:5000})`
  (`functions.ts:80`, ignore-on-timeout) + scroll loop, then `page.content()`.
- `NAVIGATION_WAIT_UNTIL` is env-driven (§3.5), default `'domcontentloaded'`.

### 3.2 Disable Crawlee status-based retirement

`functions.ts:538`:

```ts
sessionPoolOptions: {
    blockedStatusCodes: [],   // was [401, 403, 429, 404, 410, 423, 502, 500, 503]
},
```

Empty list → `_throwOnBlockedRequest` never throws → **every** status reaches the
request handler. `routes.ts` becomes the single source of truth. Session rotation
for true anti-bot codes (403/429) is re-implemented in §3.3 so behavior is
preserved, not lost.

### 3.3 Single status policy in `routes.ts`

Add a pure helper and rewrite the unreachable `routes.ts:320-340` block. `session`
is added to the handler destructure (`routes.ts:198`) for the block path.

```ts
// routes.ts (module scope) — single source of truth for HTTP status handling
type StatusClass = "ok" | "permanent" | "transient" | "block";

const PERMANENT_STATUS = new Set([400, 401, 404, 405, 406, 410, 414, 423, 451, 501]);
const BLOCK_STATUS = new Set([403, 429]);
const TRANSIENT_STATUS = new Set([408, 425, 500, 502, 503, 504, 509, 521, 522, 523, 524, 525, 526]);

export function classifyHttpStatus(status: number): StatusClass {
    if (PERMANENT_STATUS.has(status)) return "permanent";
    if (BLOCK_STATUS.has(status)) return "block";
    if (TRANSIENT_STATUS.has(status)) return "transient";
    return "ok"; // 2xx/3xx and any unlisted code → proceed to extraction
}
```

Handler action (replaces `routes.ts:320-340`, runs once `response` exists):

```ts
if (response) {
    const status = response.status();
    const cls = classifyHttpStatus(status);
    if (cls !== "ok") {
        // Homepage error message + UpdateChecker/StatsManager bookkeeping
        // (preserve the existing :324-336 behavior exactly).
        if (cls === "permanent") {
            request.noRetry = true;                       // fail once
            log.error(`⛔ PERMANENT HTTP ${status} on ${url} — no retry`);
        } else if (cls === "block") {
            session?.retire();                            // fresh session/IP may pass
            log.warning(`🚫 BLOCKED HTTP ${status} on ${url} — retire session, retry`);
        } else { // transient
            log.warning(`↻ TRANSIENT HTTP ${status} on ${url} — retry`);
        }
        throw new Error(`HTTP ${status}`); // → failedRequestHandler (records to error dataset)
    }
}
```

| Class | Codes | Retry? | Session |
|---|---|---|---|
| permanent | 400, 401, 404, 405, 406, 410, 414, 423, 451, 501 | **no** (`noRetry`) | keep |
| block | 403, 429 | yes (≤ `maxRequestRetries`) | `retire()` |
| transient | 408, 425, 500, 502, 503, 504, 509, 521-526 | yes (≤ `maxRequestRetries`) | keep |
| ok | all others (2xx/3xx + unlisted) | n/a | proceed |

Notes:
- The existing homepage `crawlErrorMessage` write and the
  `updateChecker.checkUrl(...)` / `statsManager.increment("errors")` calls
  (`routes.ts:324-336`) are preserved inside the non-`ok` branch — same
  bookkeeping, new classification.
- `failedRequestHandler` (`functions.ts:542`) still records the rich error row
  (`status_code`, captcha probe, etc.). For `permanent`, `noRetry` is already set
  by the handler; the failed-handler captcha/challenge probe still runs harmlessly.

### 3.4 Navigation-timeout retry cap

In `failedRequestHandler` (`functions.ts:542`), after the existing
`NON_RETRYABLE_ERRORS` check:

```ts
const isNavTimeout = errorStr.includes("Navigation timed out")
    || errorStr.includes("TimeoutError");
if (isNavTimeout && request.retryCount >= TIMEOUT_MAX_RETRIES) {
    request.noRetry = true;
    log.warning(`Navigation timeout cap reached for ${request.url} (retryCount=${request.retryCount}) — no retry`);
}
```

Bounds a genuinely-unresponsive URL to ≈ (`TIMEOUT_MAX_RETRIES` + 1) × 90 s
instead of 6 × 90 s. Default `TIMEOUT_MAX_RETRIES = 2`.

### 3.5 Config knobs

New env, read where the crawler options object is built (`functions.ts`), with
NaN/empty/invalid fallback to the default (mirrors the existing
`PROGRESS_STALL_THRESHOLD_MS` validation pattern):

| Env var | Default | Effect |
|---|---|---|
| `NAVIGATION_WAIT_UNTIL` | `domcontentloaded` | `page.goto` wait condition. Allowed: `load`, `domcontentloaded`, `commit`, `networkidle`. Invalid → default. |
| `TIMEOUT_MAX_RETRIES` | `2` | Max navigation-timeout retries before `noRetry`. |

`navigationTimeoutSecs` (90) and `maxRequestRetries` (5) are left as-is (tuning,
not part of this bug). Document them as related knobs.

## 4. Testing

Script-style `test_*.ts` (run via `tsx`, `assertEqual` + `process.exit(1)`),
matching the existing crawler test convention. tdd-gate stems:
`test_functions.*` for `functions.ts`, `test_routes.*` for `routes.ts`.

1. `classifyHttpStatus` — full table: each permanent/block/transient code → its
   class; representative `ok` cases (200, 301, 418-unlisted → ok).
2. waitUntil hook — given a `gotoOptions` object, the hook sets
   `gotoOptions.waitUntil === 'domcontentloaded'` (and honors a valid env override;
   invalid env → default).
3. Status-policy handler behavior (unit-level around `classifyHttpStatus` + a thin
   seam): permanent → `noRetry=true` + throws; block → `session.retire()` called +
   throws; transient → throws **without** `noRetry`; ok → no throw.
4. Timeout cap — `failedRequestHandler` logic: `isNavTimeout` & `retryCount ≥ cap`
   → `noRetry=true`; under cap → not set; non-timeout error → unaffected.

`tsc --noEmit` must stay clean. Existing `test_routes.*` / `test_functions.*`
suites must stay green.

## 5. Blast radius / risk

- **Global to every crawl** — both levers live in the shared crawler options
  (`functions.ts`). Mitigations: decoupled post-nav settle (gate cleared); full
  test coverage; env knobs to revert (`NAVIGATION_WAIT_UNTIL=load` restores old
  navigation behavior without a redeploy).
- **Emptying `blockedStatusCodes`** — confirmed single consumer (`functions.ts:538`).
  403/429 session rotation is re-implemented in `routes.ts` via `session.retire()`;
  net behavior preserved, just relocated.
- **`'domcontentloaded'` vs `'load'`** — for the rare site that only completes
  meaningful DOM after `load`, `processPage`'s networkidle+scroll still settles it;
  if a regression appears, set `NAVIGATION_WAIT_UNTIL=load` for that deployment.

## 6. Rollout

1. Deploy with defaults (`NAVIGATION_WAIT_UNTIL=domcontentloaded`,
   `TIMEOUT_MAX_RETRIES=2`).
2. Re-run the example URL's domain (or any known-404 link) → expect the request to
   fail **once** with `PERMANENT HTTP 404`, no 90 s timeout, no 5× retry.
3. Watch crawl wall-clock and the `error-{domain}` dataset `status_code`
   distribution — expect 404/410 rows with no retry storms, and 504/408 now
   captured instead of silently extracted.
4. Revert lever: `NAVIGATION_WAIT_UNTIL=load` if any content-completeness
   regression is observed.

## 7. Deferred follow-ups

- Soft-404 (HTTP 200 + not-found body) heuristic — separate effort.
- Per-class retry caps (e.g. a lower cap for `transient` than `maxRequestRetries`)
  if data shows transient codes rarely recover.
- Lowering `navigationTimeoutSecs` below 90 s now that most pages resolve fast with
  `domcontentloaded` — data-driven tuning.
- `'commit'` instead of `'domcontentloaded'` for even earlier status visibility
  (status available on first response byte) — only if `domcontentloaded` still
  shows hangs.
