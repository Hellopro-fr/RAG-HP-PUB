# Crawler detection-backpressure: concurrency cap + handler-timeout alignment

**Date:** 2026-06-21
**Service:** `crawler-service` (Node engine)
**Status:** design + fix
**Trigger incident:** crawl `7033` (carflo.fr), 2026-06-19 — death-spiral, exit 6 ×3, never completed.

## Symptom reported

```
Erreur crawling : [stderr] Pre-batch link extraction failed:
  Error: page.$$eval: Target page, context or browser has been closed
```
Hundreds of these, interleaved with active crawling, plus `requestHandler timed out
after 120 seconds` (145 occurrences in the final stats) and a repeating
`progress_stalled: No URL progress for 630s` → exit 6 → relaunch loop.

## Root cause (evidence-based)

The `page.$$eval` warning at `routes.ts:854` is a **symptom**, not the disease. The
default handler runs heavy external-IO awaits — chiefly `detectionClient.detect`
(`DETECTION_REQUEST_TIMEOUT_S` = 180s, 5-wide `p-limit`) — between the last page op
(`processPage`, ≤ ~line 711) and the pre-batch link extraction (`page.$$eval`, line
843). No `page.*` call runs in that window, so `$$eval` is the **first page touch
after the detect gap** — the canary for "the page died mid-detect".

The crawl's `AutoscaledPool` scales on **local** CPU / event-loop / memory. While
handlers `await` the detection HTTP call those are all idle, so the pool reads
`isSystemIdle: true` and **keeps ramping** — to 25–29 concurrent handlers against
only **5** detection slots. ~20 handlers park in the `p-limit` queue, inflating
per-page detect latency. The incident timing summary:

```
detect_ms  94.4%  (median 145480ms, p95 238113ms)
Detect API saturated 84.1% of time (pending queue non-empty at concurrency cap)
```

Median detect (145s) > `requestHandlerTimeoutSecs` (120s). Crawlee kills the handler
at 120s and closes the page; the orphaned handler keeps running and, when detect
finally returns, hits `page.$$eval` on the dead page → the warning + a reclaimed
(retried) request. With almost nothing finishing, `ProgressMonitor` fires at 630s →
exit 6 → relaunch → same state → **death spiral** (34 → 111 → 51 finished across 3
runs; the domain never completes).

Two coupled defects:
1. **Over-subscription** — pool concurrency (≤unbounded) ≫ detection throughput (5).
2. **Budget inversion** — handler timeout (120s) < a single detect call's own timeout
   (180s), so even a normal-but-slow detect is killed mid-flight.

The upstream root — `api-detection-langue-fr` latency under load — is out of this
service's scope (tracked separately; the async `detect-batch-async` work is the
strategic fix). This change makes the crawler stop *amplifying* it and tolerate the
common slow case.

## Fix

Two env-tunable levers in `httpStatusPolicy.ts` (the dependency-free resolver home),
wired in `functions.ts`. Mirrors the existing `NAVIGATION_WAIT_UNTIL` /
`TIMEOUT_MAX_RETRIES` pattern (resolve once at module load, validate, fall back).

| Env var | Default | Effect |
|---|---|---|
| `CRAWLER_MAX_CONCURRENCY` | `10` | Caps `autoscaledPoolOptions.maxConcurrency`. ≈2× `DETECTION_MAX_CONCURRENCY` (5): enough to overlap nav/extract with the in-flight detects without growing the detect queue. Bounds the queue → detect latency ≈ raw call time, not queue wait. |
| `REQUEST_HANDLER_TIMEOUT_S` | `200` | `requestHandlerTimeoutSecs`. Raised from 120 to exceed one nav (≤90) + one detect (≤180) so a slow-but-progressing page is not killed mid-detect. Resolves the inversion (180 < 200). |

- `maxConcurrency` is set inside `autoscaledPoolOptions` (canonical Crawlee
  placement; avoids the top-level/pool dual-specification error).
- Validation: non-finite / non-positive → default (matches `resolveTimeoutMaxRetries`).
- Operators tune both together: raising `DETECTION_MAX_CONCURRENCY` should be paired
  with a higher `CRAWLER_MAX_CONCURRENCY`; detection-light deployments can raise the
  cap for more throughput.

### Why not just silence `page.$$eval`

Guarding line 843 with `page.isClosed()` would hide the line and fix nothing — the
crawl would still over-subscribe detection, still time out, still death-spiral. The
warning is a downstream effect; the fix targets the cause (concurrency vs. detection
throughput + the timeout budget).

## Blast radius

Both defaults change behaviour for **all** crawls, not just carflo.
- Gain: kills the death spiral on detection-gated/slow sites; eliminates the 145
  timeouts + retry waste; crawls actually finish.
- Cost: on detection-light sites where the pool could safely run wide, peak
  concurrency drops to 10. Mitigated by `CRAWLER_MAX_CONCURRENCY` being env-tunable.
- A genuinely-hung handler now holds a slot up to 200s (was 120s); bounded by the
  concurrency cap, and `ProgressMonitor` (600s) still catches a dead crawl.

No proto / shared-lib / Python / BO change. Crawler-engine only.

## Verification

- Unit: `resolveMaxConcurrency` / `resolveRequestHandlerTimeoutSecs` (node:test,
  default + valid + invalid + non-positive paths).
- `npm run build` (tsc) + `npm test` green.
- Cannot reproduce the live crawl (remote-only). Post-deploy, re-run a
  detection-gated domain and confirm: handler timeouts → ~0, `Pre-batch link
  extraction failed` → ~0 (outside genuine shutdown), `Detect API saturated` drops,
  the crawl completes instead of looping on `progress_stalled`.
