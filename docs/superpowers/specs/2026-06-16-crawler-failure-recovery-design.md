# Crawler Failure Classification & Auto-Recovery on Restart — Design

**Date:** 2026-06-16
**Service:** `apps-microservices/crawler-service` (Node.js/TypeScript Crawlee engine)
**Branch:** `features/poc` (local, unpushed — operator decides push/deploy)
**Status:** Approved (design gate)

## 1. Context & Trigger

During a crawl of `headpowerac.net`, a **temporary proxy-gateway outage** produced
`page.goto: NS_ERROR_PROXY_CONNECTION_REFUSED` on 27 valid URLs. Each was retried up to
`maxRequestRetries=5`, then **permanently failed** and written to the Crawlee
`error-{domain}` dataset. The crawl ended (exit code 6, progress stall — graceful, all
local data intact).

Investigation (systematic-debugging Phase 1) surfaced **two distinct bugs**:

### Bug 1 — Auto-recovery is unreachable for completed crawls (ordering)

`reclaimFailedRequest(domain)` (`crawler/src/functions.ts:1618`) is the purpose-built
mechanism that re-queues failed URLs from `error-{domain}` (resets `retryCount=0`,
`handledAt=undefined`, then `reclaimRequest`). It is called at `main.ts:1131`.

But the **queue-health early-exit** runs first, at `main.ts:800-803`:

```typescript
if (queueInfo && queueInfo.totalRequestCount > 0
    && queueInfo.handledRequestCount === queueInfo.totalRequestCount
    && queueInfo.pendingRequestCount === 0) {
    console.log(`✅ Crawl already completed: ...`);
    process.exit(0); // Success exit  ← fires BEFORE reclaim at 1131
}
```

Crawlee marks permanently-failed requests as **handled**. On this run all requests
reached terminal (`5198 finished + 92 failed = 5290 total`, `0` pending), so line 800's
condition is `true` → `process.exit(0)` → `reclaimFailedRequest` at 1131 **never runs**.
A plain same-id restart therefore exits "already completed" and recovers nothing;
`reclaimFailedRequest` is effectively dead code for any completed crawl.

### Bug 2 — A transient proxy fault permanently kills valid pages (classification)

`NS_ERROR_PROXY_CONNECTION_REFUSED` is a **transport/infrastructure fault** (our proxy
gateway was unreachable), not a page fault. It is **not** in `NON_RETRYABLE_ERRORS`
(`functions.ts:556-564`) and is not a navigation timeout, so it consumed the full
`maxRequestRetries` budget and then permanently failed valid URLs. There is no
infra-vs-page distinction and no proxy retire/rotate. The proxy is a **single Apify
gateway** (`ProxyConfiguration({ proxyUrls: [proxyUrl] })`), so `session.retire()` /
IP-rotation cannot revive a dead gateway.

## 2. Goals & Non-Goals

**Goals**
- A same-id standard restart **auto-recovers** previously-failed URLs that are
  *recoverable* (infra/transient), re-crawling them instead of exiting "already completed".
- A temporary proxy/transport outage must **not** permanently lose valid URLs.
- Recovery must **skip permanent failures** (genuine 404/410/DNS/SSL/etc.) so restarts
  don't wastefully re-crawl them.

**Non-Goals (deliberate, per brainstorming decisions)**
- No new proxy-outage circuit-breaker / monitor. The existing `ProgressMonitor` already
  exits 6 on a sustained outage; bug-1 auto-recovery is the safety net.
- No `session.retire()` / proxy rotation on infra errors (single gateway — no benefit).
- No "infra retries don't count against budget" scheme (avoids long stalls).
- No per-URL persistent recovery-attempt counter.
- No exit-code / Python / BO contract change.

## 3. Decisions (from brainstorming)

| # | Decision |
|---|----------|
| Q1 | Recovery re-queues **recoverable only** (infra + transient); permanent skipped → requires failure classification. |
| Q2 | Proxy handling is **lean**: classify + tag, lean on bug-1 auto-recovery. No new monitor, no retire. |
| Q3 | Auto-recovery is **default-on with an env kill-switch** (`RECOVER_FAILED_ON_RESTART`, default `true`). |
| Approach | **A** — extend `httpStatusPolicy.ts` (it already classifies error strings via `shouldCapTimeoutRetry` and reads env). All decisions pure/unit-tested; thin `main.ts` wiring. |

## 4. Architecture

One shared primitive — **failure classification** — drives both fixes. The
load-bearing insight: **`request.noRetry` is the authoritative "permanent" signal.**
It is already set by every permanent path (routes.ts permanent-status, `NON_RETRYABLE`
markers, the timeout cap, `detectChallengePage` WAF-permanent). Recovery eligibility is
therefore: "was this deemed permanent, or did it merely exhaust retries on a recoverable
fault?"

```
failure → failedRequestHandler
            failure_class = request.noRetry ? "permanent" : classifyFailure(errorStr, status)
            push {..., failure_class} → error-{domain} dataset
                                              │
restart  → main.ts: if RECOVER_FAILED_ON_RESTART && default crawl type
            reclaimFailedRequest(domain)  ← runs BEFORE queue-health check
              for each error item: if failure_class recoverable → reset + reclaimRequest
              drop error dataset (if any reclaimed)
            queue-health check: pending>0 → proceed and re-crawl; else exit(0)
```

## 5. Components

### 5.1 `crawler/src/httpStatusPolicy.ts` (extend) — pure, unit-tested

```typescript
export type FailureClass = "permanent" | "transient" | "infra" | "unknown";

// Moved here from failedRequestHandler (DRY — used by both the handler and classifyFailure)
export const PERMANENT_ERROR_MARKERS: readonly string[] = [
    "ERR_NAME_NOT_RESOLVED", "ERR_CERT_DATE_INVALID", "ERR_SSL_PROTOCOL_ERROR",
    "ERR_TOO_MANY_REDIRECTS", "Download is starting", "net::ERR_ABORTED",
    "Execution context was destroyed",
];

// Transport/connection faults on OUR side (proxy gateway, network) — recoverable.
const INFRA_ERROR_MARKERS: readonly string[] = [
    "NS_ERROR_PROXY_CONNECTION_REFUSED", "NS_ERROR_PROXY_",
    "NS_ERROR_CONNECTION_REFUSED", "NS_ERROR_NET_",
    "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "socket hang up",
];

export function classifyFailure(errorStr: string, status?: number): FailureClass {
    if (PERMANENT_ERROR_MARKERS.some(m => errorStr.includes(m))) return "permanent";
    if (INFRA_ERROR_MARKERS.some(m => errorStr.includes(m))) return "infra";
    if (typeof status === "number" && status > 0) {
        const c = classifyHttpStatus(status);
        if (c === "permanent") return "permanent";
        if (c === "transient" || c === "block") return "transient";
    }
    if (errorStr.includes("Navigation timed out") || errorStr.includes("TimeoutError")) return "transient";
    return "unknown";
}

export function isRecoverableFailureClass(cls: FailureClass): boolean {
    return cls === "infra" || cls === "transient";
}

export const RECOVER_FAILED_ON_RESTART: boolean =
    (process.env.RECOVER_FAILED_ON_RESTART ?? "true").trim().toLowerCase() !== "false";

// Pure gate for the main.ts recovery call (keeps main.ts wiring thin + testable)
export function shouldRunRecovery(flag: boolean, typeCrawling: string): boolean {
    return flag && typeCrawling !== "sitemap" && typeCrawling !== "generate_data";
}
```

**Classification precedence:** permanent marker > infra marker > numeric HTTP status >
navigation-timeout > unknown.

**Deliberate exclusions** (ambiguous → `unknown` → not auto-recovered):
`NS_ERROR_ABORT` (Firefox/camoufox — could be transport OR binary-download abort) and
`browserController.newPage() failed` (could be a poison URL crashing the browser). Both
are deferred infra-marker candidates, called out for future revisit.

### 5.2 `crawler/src/functions.ts` `failedRequestHandler` (≈551-684)

1. Replace the inline `NON_RETRYABLE_ERRORS` literal (556-564) with the imported
   `PERMANENT_ERROR_MARKERS`; the `isPermanentError` check (566) consumes it unchanged.
2. At the error-dataset push (675-683), compute and record the class:

```typescript
const status = response?.status() || 0;
const failureClass: FailureClass = request.noRetry ? "permanent" : classifyFailure(errorStr, status);
await dataset.pushData({
    id: request.id, url: request.url, errors: request.errorMessages,
    proxy_used: maskProxyUrl(proxyInfo?.url), status_code: status,
    captcha: captchaDetected, failure_class: failureClass,   // ← new field
    timestamp: new Date().toISOString(),
});
```

`errorStr` already exists (565). No `session.retire()` (Q2 lean). The 63 genuine 404s
carry `noRetry` (set in routes.ts) → tagged `permanent`. The 27 proxy-refused exhausted
retries with `noRetry` unset → `classifyFailure` → `infra`.

### 5.3 `crawler/src/functions.ts` `reclaimFailedRequest` (1618-1656) — filter on class

```typescript
const cls = item["failure_class"];
if (cls !== undefined && !isRecoverableFailureClass(cls)) { skippedPermanent++; return; }
// ...existing: getRequest → retryCount=0, errorMessages=[], handledAt=undefined → reclaimRequest...
```

- **Legacy entries** (pre-deploy, `failure_class === undefined`) → treated **recoverable**
  (re-crawled). Transitional and bounded (permanent ones fail-fast via the status policy).
- **Dataset drop unchanged**: drop the whole `error-{domain}` only if `reclaimedCount > 0`
  (existing behavior). Permanent records discarded — acceptable, since those URLs stay
  `handled` in the queue and are not re-crawled. If nothing recoverable →
  `reclaimedCount === 0` → keep dataset → fall through to `exit(0)`.
- Summary log → `Reclaimed N recoverable requests, skipped M permanent.`

### 5.4 `crawler/src/main.ts` — move recovery before the early-exit

Insert before the QUEUE HEALTH CHECK (≈795), **remove** the old call at 1129-1134:

```typescript
if (shouldRunRecovery(RECOVER_FAILED_ON_RESTART, typeCrawling)) {
    try { await reclaimFailedRequest(domain); }
    catch (e) { console.warn(`⚠️ auto-recovery skipped for ${domain}: ${e}`); }
}
// existing QUEUE HEALTH CHECK (800): pending>0 if anything reclaimed → proceeds; else exit(0)
```

Recovery resets recoverable requests to **pending** → `pendingRequestCount === 0` at line
800 becomes false → crawler proceeds and re-crawls only the reclaimed (the rest stay
deduped/handled). With `RECOVER_FAILED_ON_RESTART=false`, `shouldRunRecovery` returns
false → skipped → exact current behavior (kill-switch).

The module-level `requestQueue` is opened at 664 (before 795); `reclaimFailedRequest`
opens the same named queue (Crawlee singleton) — consistent. Confirmed by investigation:
exit-6 leaves the on-disk queue intact, so `getRequest(id)` resolves the failed ids.

## 6. Error Handling / Edge Cases

- **No infinite loop:** recovery fires only on a deliberate same-id restart. A recovered
  URL that fails *permanently* on re-crawl is tagged `permanent` → not recovered next time.
  A still-`infra` one (gateway still down) is recovered only if the operator restarts
  again. Bounded by operator action.
- **`reclaimFailedRequest` throw** → caught in `main.ts` → warn + proceed (recovery is
  best-effort; never blocks the crawl).
- **Mixed dataset, none recoverable** → `reclaimedCount === 0` → dataset kept → `exit(0)`
  "already completed" (correct: nothing to recover).
- **Headpowerac trace:** 27 proxy → `infra` → recovered; 63×404 + 1 timeout-capped +
  1 `newPage` fail → `permanent`/`unknown` → skipped. Exactly the proxy victims.

## 7. Blast Radius

Crawler-service Node engine only. No shared libs (`libs/`), no protos, no Python
exit-code contract change, no Marketplace BO change. Behavior delta: a same-id restart of
a *completed* crawl may now re-crawl recoverable failures instead of an instant
`exit(0)`. Kill-switch (`RECOVER_FAILED_ON_RESTART=false`) reverts to current behavior.

## 8. Testing (script-style `tsx` + local `assertEqual`, run from `crawler/`)

- **`tests/test_httpStatusPolicy.ts` (extend):** `classifyFailure` — proxy/`ECONNRESET`
  → `infra`; DNS/SSL → `permanent`; status 404 → `permanent`, 503 → `transient`;
  "Navigation timed out" → `transient`; gibberish → `unknown`; precedence (permanent
  marker > infra > status). `isRecoverableFailureClass` truth table.
  `RECOVER_FAILED_ON_RESTART` resolver (default `true`, `"false"`→false, `"FALSE"`→false,
  `""`→true). `shouldRunRecovery` (flag × crawl type).
- **`tests/test_functions.ts` (extend):** integration with a temp `CRAWLEE_STORAGE_DIR` —
  seed an `error-{domain}` dataset (mixed `failure_class`) + a queue holding those ids →
  run `reclaimFailedRequest` → assert recoverable ids pending, permanent ids still
  handled, dataset dropped. Fills a current coverage gap (`reclaimFailedRequest` had no
  test). If the Crawlee temp-storage harness proves too fiddly in this test style, fall
  back to the pure predicate test + code-review of the wiring.
- **`main.ts` ordering:** covered via the pure `shouldRunRecovery` helper in
  `test_httpStatusPolicy.ts`; keep `main.ts` wiring thin. If `tdd-gate` requires
  `test_main.*` for the `main.ts` edit, add a focused `tests/test_main.ts`.

## 9. Config & Docs

- **Env:** `RECOVER_FAILED_ON_RESTART` (default `true`, Node-only, inherited by the
  subprocess like `NAVIGATION_WAIT_UNTIL`/`TIMEOUT_MAX_RETRIES`). No `docker-compose`
  change required; optional passthrough for discoverability is deferred.
- **Docs:** crawler-service `CLAUDE.md` — new "Failure Classification & Auto-Recovery on
  Restart" subsection (class table, the `noRetry`→permanent rule, the env var,
  legacy-entry behavior); cross-link from the existing "HTTP Status & Navigation Retry
  Policy" section.

## 10. Rollout

Default-on → deploy makes the fix live. Kill-switch `RECOVER_FAILED_ON_RESTART=false`.

For the **immediate headpowerac recovery** (separate from this code change):
- Manual path (no deploy): run `reclaimFailedRequest('headpowerac.net')` against the
  crawl's on-disk storage (resets the 27 to pending), then same-id standard restart
  (`dropData=false`).
- Or deploy this fix, then same-id standard restart → the 27 auto-recover (404s skipped).
- **Do not** `dropData=true` / archive / stash-drop before recovering — that destroys the
  `error-{domain}` dataset (`main.ts:555 dropDataset(error-${domain})`).

## 11. Implementation Tasks (preview for writing-plans)

1. **T1** — `httpStatusPolicy.ts`: `FailureClass`, `PERMANENT_ERROR_MARKERS`,
   `INFRA_ERROR_MARKERS`, `classifyFailure`, `isRecoverableFailureClass`,
   `RECOVER_FAILED_ON_RESTART`, `shouldRunRecovery` + `test_httpStatusPolicy.ts` cases.
2. **T2** — `functions.ts` `failedRequestHandler`: consume `PERMANENT_ERROR_MARKERS`
   (DRY), compute + push `failure_class`.
3. **T3** — `functions.ts` `reclaimFailedRequest` class filter + `main.ts` reorder/flag;
   `test_functions.ts` reclaim integration test (+ `test_main.ts` only if tdd-gate
   requires it).
4. **T4** — crawler-service `CLAUDE.md` documentation.

## 12. Deferred Follow-ups

- `NS_ERROR_ABORT` / `browserController.newPage() failed` as infra markers (need
  disambiguation from binary-download / poison-URL cases).
- Optional `RECOVER_FAILED_ON_RESTART` passthrough in `docker-compose.yml`.
- Proxy-outage circuit breaker (only if `ProgressMonitor` + auto-recovery prove
  insufficient in practice).
