# Crawler concurrency auto-adjust: detection-backpressure gate + quiet-guard

**Date:** 2026-06-21
**Service:** `crawler-service` (Node engine)
**Status:** design (approved)
**Supersedes:** the static-cap mechanism of
`docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md` (commit
`5537ac52`). The handler-timeout lever from that spec is retained unchanged.

## Problem

The shipped fix (`5537ac52`) capped crawl concurrency at a static
`CRAWLER_MAX_CONCURRENCY=10` to stop the AutoscaledPool over-subscribing the 5-wide
detection `p-limit` (root cause of the carflo.fr 7033 death-spiral). A static cap is
too coarse: it throttles **every** crawl to 10, including ones where
`api-detection-langue-fr` is fast and the pool could safely run much wider. We want
concurrency that **auto-adjusts per crawl** — wide when detection is fast, throttled
only when detection is the live bottleneck.

## Decision

**Reactive backpressure gate** on the AutoscaledPool, keyed off the detection
`p-limit` queue depth, plus a retained **hard ceiling** for memory/browser safety.

Rejected alternatives:
- **Custom Snapshotter** (feed detection saturation into the pool's native overload
  signal): smoother, but couples to undocumented Crawlee internals (version-fragile)
  and is hard to unit-test.
- **AIMD latency controller** (drive `maxConcurrency` toward a latency setpoint): most
  adaptive, but a feedback loop whose stability/convergence is only observable on a
  live crawl — unverifiable in this remote-only environment — and it fights the pool's
  own autoscaler on the same knob.

The gate buys ~90% of the adaptive benefit at ~10% of the risk and is fully
unit-testable (a pure predicate). It can evolve into the controller later if real
data shows the gate is too coarse.

## Design

### Signal (already wired)

`DetectionLangueClient.limiter.pendingCount` / `.activeCount` (p-limit v5), already
sampled by the timing recorder (`main.ts:1298`) and already the basis of the
"Detect API saturated" metric (`aggregator.ts:109`). `pendingCount` = detect calls
*waiting* for one of the `DETECTION_MAX_CONCURRENCY` (5) slots.

### Pure logic — `httpStatusPolicy.ts` (dependency-free, unit-testable)

- `shouldAcceptNewPage(pending: number, threshold: number): boolean` →
  `pending <= threshold`. The entire control decision. The `pending` arg is the
  observed backpressure depth — today just detection's `pendingCount`, but generic so
  a second source can later be folded in via `Math.max(detectPending, …)` at the call
  site without changing the signature.
- `resolveBackpressureMaxPending(raw): number` → finite & `>= 0` ? `Math.floor` :
  default **5**. (`>= 0` because 0 is a valid "tolerate no queue" setting.)
  Const `BACKPRESSURE_MAX_PENDING = resolveBackpressureMaxPending(process.env.DETECTION_BACKPRESSURE_MAX_PENDING)`.
- `isPageClosedError(errStr): boolean` → `errStr.includes("Target page, context or browser has been closed")`.
- `resolveMaxConcurrency` default **10 → 20** (role flip: primary throttle → ceiling).

### Gate wiring — `functions.ts`

`autoscaledPoolOptions` gains `isTaskReadyFunction` next to the existing
`isFinishedFunction` (and keeps `maxConcurrency: MAX_CONCURRENCY`, now default 20):

```ts
isTaskReadyFunction: async () =>
    shouldAcceptNewPage(context.detectionClient?.limiter.pendingCount ?? 0, BACKPRESSURE_MAX_PENDING),
```

The closure reads `context.detectionClient` at call time (set in `main.ts` before
`crawler.run()`), so it is always initialised when the pool evaluates it. `?? 0`
fails open (gate open) if the client is somehow absent — never blocks the crawl.

### Control behavior

A page starts only if **system-not-overloaded** (Crawlee native CPU/mem/event-loop)
**AND** `pendingCount <= 5` (gate). Three independent limiters: gate (detection),
memory snapshotter (Crawlee), hard ceiling (20).

- Fast detection → `pendingCount ≈ 0` → gate always open → pool ramps to the ceiling /
  memory limit. Fast crawls run wide.
- Slow detection → `pendingCount` climbs past 5 → gate vetoes new starts → concurrency
  holds at the level detection can sustain. Self-throttles.
- **No deadlock:** the gate only delays *starts*; running detects complete →
  `pendingCount` drops → gate reopens; `isFinishedFunction` still terminates the crawl.
- **Equilibrium:** concurrency settles where `pendingCount` hovers at the threshold;
  it hunts by ~one launch batch — cosmetic, smoothed by the pool's ~0.5s ramp cadence.
- Threshold 5 (= `DETECTION_MAX_CONCURRENCY`) tolerates one queued wave, keeping
  per-page detect latency ≈ raw call time, well under the 200s handler budget. If an
  operator raises `DETECTION_MAX_CONCURRENCY`, consider raising this in step.

### Safety ceiling

`CRAWLER_MAX_CONCURRENCY` default **20** (was 10). Now a memory/browser backstop, not
the primary throttle. The incident hit memory pressure at ~25 concurrent, so 20 sits
below that; the gate makes the ceiling rarely the binding limit (only when detection
is fast *and* the crawl ramps hard).

### Quiet-guard (`routes.ts`)

At the pre-batch link-extraction block: `if (page.isClosed()) { ... skip pre-batch
dedup ... }` before `page.$$eval`; in the existing catch, `isPageClosedError(e)` →
`log.debug` (benign teardown), else keep `console.warn`. A normal `/stop`/shutdown
that tears down in-flight pages stops surfacing as `Erreur crawling`. Pure log
hygiene — no behavior change. (After the gate removes the timeout-driven occurrences,
the only ones left are benign teardown, which this silences.)

### Scope (YAGNI)

Gate on **detection only**. The content-extractor (`tier2 /clean`) p-limit is excluded
— `DIEZ_TIER2_ENABLED` / `QM_TIER2_ENABLED` default false, and the incident was pure
detection. The predicate is generic, so adding a second source later is a one-line
`Math.max(detectPending, extractorPending)` change.

## Env vars

| Variable | Default | Effect |
|---|---|---|
| `CRAWLER_MAX_CONCURRENCY` | `20` (was 10) | Hard ceiling on `autoscaledPoolOptions.maxConcurrency` (memory/browser backstop). |
| `DETECTION_BACKPRESSURE_MAX_PENDING` | `5` | Gate threshold: pause new page starts while detection `pendingCount` exceeds this. ≈ `DETECTION_MAX_CONCURRENCY`. |
| `REQUEST_HANDLER_TIMEOUT_S` | `200` | Unchanged (from `5537ac52`). |

## Files

- `crawler/src/httpStatusPolicy.ts` — `shouldAcceptNewPage`, `resolveBackpressureMaxPending` + `BACKPRESSURE_MAX_PENDING`, `isPageClosedError`; `resolveMaxConcurrency` default 10→20.
- `crawler/src/functions.ts` — add `isTaskReadyFunction` to `autoscaledPoolOptions`.
- `crawler/src/routes.ts` — quiet-guard at the `page.$$eval` pre-batch block.
- `crawler/src/tests/httpStatusPolicy.limits.test.ts` — extend (predicate, new resolver, isPageClosedError, updated maxConcurrency default).
- `apps-microservices/crawler-service/CLAUDE.md` — rewrite the "Detection Backpressure" section (gate supersedes static cap).
- `.../2026-06-21-crawler-detection-backpressure-design.md` — add a "Superseded by" note on its static-cap section.

## Testing

All new logic is pure → node:test, remote-safe:
- `shouldAcceptNewPage`: below / at / above threshold; threshold 0 (gate closes on any queue).
- `resolveBackpressureMaxPending`: missing/invalid/negative/Infinity → default 5; `'0'` → 0 (valid, kept — "tolerate no queue"); `'5'`/`'10'` → parsed.
- `isPageClosedError`: match / non-match / empty.
- `resolveMaxConcurrency`: default now 20.

Build (tsc) + full node suite green. Live ramp behavior (gate opens/closes, crawl
completes instead of looping) is post-deploy verification — cannot run a live crawl here.

## Blast radius

Crawler-engine only. No proto / shared-lib / Python / BO change.
- All crawls: concurrency now auto-adjusts. Fast-detection crawls ramp wider than the
  old static 10 (up to 20); slow-detection crawls self-throttle (no death-spiral).
- `isTaskReadyFunction` adds one cheap sync read per task-start decision — negligible.
- Reversible: unset the gate (revert `functions.ts`) → falls back to ceiling-only.

## Post-deploy verification

Re-run a detection-gated domain: handler timeouts → ~0, `Pre-batch link extraction
failed` → ~0 (outside genuine shutdown), `Detect API saturated` drops, the crawl
completes instead of looping on `progress_stalled`; on a fast-detection domain confirm
concurrency exceeds 10 (ramps toward 20).
