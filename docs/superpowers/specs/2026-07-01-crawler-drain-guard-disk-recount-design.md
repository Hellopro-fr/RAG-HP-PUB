# Crawler mid-run drain guard — disk recount backstop

**Date:** 2026-07-01
**Repo:** RAG-HP-PUB `apps-microservices/crawler-service` (`crawler/src`), branch `features/poc`
**Status:** design approved → plan next

## Problem

A standard-mode crawl whose only page (homepage) yields **0 new URLs** does not terminate on its own. It idles for 1200s until the `ProgressMonitor` watchdog aborts it with **exit code 6** (`PROGRESS_STALL`) — a stall/error terminal, not a clean completion — so the operator must relaunch manually.

Observed: domain `fr.zoomlion.com`, id `6599`, 2026-07-01 04:11→04:32.

## Root cause (evidence-confirmed)

Standard-mode completion gate (`functions.ts:859`):
```ts
isFinishedFunction: async () => (await requestQueue.isEmpty()) && context.phase2SeedingComplete;
```
`phase2SeedingComplete` is `true` in standard mode (default `context.ts:158`; the `false` path `main.ts:1404` is `crawlMode==='update'`-only), so the gate reduces to `requestQueue.isEmpty()`.

The queue backend is `@crawlee/memory-storage`. After the single homepage was handled (`requestsFinished:1`, `orderNo=null` on the disk request file = handled), the queue's completion signals were **wedged**:
- `isEmpty()`/`isFinished()` never returned true → `crawler.run()` never resolved.
- `getInfo()` reported `total_request_count:1, pending_request_count:0` (from `_queue_stats.json`, captured at 04:32:09) but **`handledRequestCount` stuck at 0** — the `0/0/1` deadlock signature. `__metadata__.json` was missing (Run 2: `[queue-repair] … no metadata`).

The existing in-run `drainGuard` (`main.ts:740-776`, deployed and running — it wrote `_queue_stats.json` every 30s) uses `isDrainedSample`, which requires `handledRequestCount === totalRequestCount`. With `handled` stuck at 0, that term is never true → the guard was **blind**. Its header comment ("getInfo() resolution counters accurate even when isEmpty()/queueHeadIds is wedged", `drainGuard.ts:19`) is **false for a counter-wedge**: here the counter itself is the wedged quantity.

The only authority that reflects truth is the request files' `orderNo` via `recountQueueFromDisk` (`queueRepair.ts:24`) — but it runs **pre-open, at startup only** (`main.ts:718`). No mid-run equivalent exists → manual relaunch required (Run 2: startup repair → `0/1` → `Crawl already completed` → exit 0).

## Goal

Make the crawl self-terminate cleanly (exit 0) when it is genuinely drained but the memory-storage counters are wedged — without a manual relaunch and without weakening true-hang detection.

## Scope

- **In scope:** a mid-run backstop that confirms drain from disk (`orderNo`) instead of trusting `getInfo()` counters, then aborts the pool for a clean exit 0.
- **Out of scope (deferred to a separate, time-boxed investigation):** *why* memory-storage left `handled=0/pending=0/total=1` with no `__metadata__.json` for a fresh 1-request crawl. It is a Crawlee memory-storage flush/counter desync; remote-only + non-reproducible → likely PLAUSIBLE-not-CONFIRMED. The backstop neutralizes the symptom regardless of root, so the root fix (if any) is optional follow-up. The desync corrupts only termination — results persist correctly.

## Design (Approach A — disk-confirmed abort on the "idle + unreconciled counts" signature)

Everything lives in the existing 30s queue-stats interval (`main.ts:740-776`), beside the current `drainGuard` block. Reuses `recountQueueFromDisk` and `autoscaledPool.abort()` (already shipped/tested).

### New pure predicate (`drainGuard.ts`)
```ts
// Idle but counts don't reconcile → wedge suspect. Only meaningful at concurrency 0,
// where the in-progress delta is 0, so handled+pending MUST equal total on a healthy queue.
export const isUnreconciledIdle = (s: DrainSample): boolean =>
    s.currentConcurrency === 0 &&
    s.totalRequestCount > 0 &&
    s.handledRequestCount + s.pendingRequestCount !== s.totalRequestCount;
```

### Per-tick logic (getInfo already fetched in the interval)
1. **Existing fast-path — unchanged.** `isDrainedSample(getInfo + concurrency)` → `drainConfirmCount` → abort. Catches the head-wedge flavor (counters honest, `isEmpty`/`queueHeadIds` wedged).
2. **New disk-confirm path.** If `isUnreconciledIdle(sample)` → `wedgeSuspectCount++`; else reset to 0. When `wedgeSuspectCount >= DRAIN_CONFIRM_SAMPLES` (3, ~90s):
   - `const rc = recountQueueFromDisk('storage/request_queues/${domain}')` — same dir as the startup repair (`main.ts:718`).
   - Disk-drained check reuses the predicate: `isDrainedSample({ currentConcurrency: 0, pendingRequestCount: rc.pending, handledRequestCount: rc.handled, totalRequestCount: rc.total })`.
   - **True** → set the shared `drainAbortInitiated` latch, `await drainPool.abort()`, log `[drain-guard] disk-confirmed drain despite wedged counters (getInfo handled=<h>/total=<t>, disk handled=<rc.handled>) — aborting to exit 0`.
   - **False** (disk shows real pending) → log once, do **not** abort; the 1200s `ProgressMonitor` watchdog remains the last resort for a genuine hang.
3. Both paths share the single `drainAbortInitiated` latch → abort at most once.

### Gating
Default-**on**. Kill-switch env `DRAIN_DISK_RECOUNT_ENABLED` (`=false` disables the new disk-confirm path only; the existing `isDrainedSample` fast-path stays always-on, it is already live). Parsed via the same resolver style as `RECOVER_FAILED_ON_RESTART` (`httpStatusPolicy.ts`). Rationale: a stall→exit6→manual-relaunch is the worse outcome; the new path aborts only when disk *proves* drained.

## Error handling / edge cases

- **No false-abort:** aborts only when the disk recount proves `pending===0 && handled===total>0`. A truly-stuck-with-work crawl → disk `pending>0` → no abort → progress-stall watchdog unchanged. True-hang detection is not weakened.
- **In-progress race:** at `concurrency===0` nothing is dispatched, so `orderNo` on disk is the final state. Safe to recount.
- **Recount failure** (dir unreadable) → `recountQueueFromDisk` returns zeros → `total 0` → not drained → no abort; wrapped in the interval's existing `try/catch`. Fails safe.
- **Backpressure/rate pause:** `concurrency===0` with real backlog → `handled+pending===total` (reconciled) → `isUnreconciledIdle` false → no disk read, no abort.
- **Pre-empts exit 6:** fires at ~90s ≪ 1200s → clean exit 0.

## Testing (TDD, `node:test` via `npx tsx --test`)

- New unit tests for `isUnreconciledIdle` (`drainGuard.test.ts`):
  - idle + unreconciled → true; reconciled (`handled+pending===total`) → false; `concurrency>0` → false; `total===0` → false.
  - the 6599 case `{ currentConcurrency:0, pendingRequestCount:0, handledRequestCount:0, totalRequestCount:1 }` → true.
- Disk-confirm reuses `isDrainedSample` (already tested) + `recountQueueFromDisk` (tested in `queueRepair.test.ts`).
- Local verify: `npx tsc --noEmit` (crawler/ has tsconfig + node_modules) + run the tests.

## Deploy

- crawler-service `features/poc`: `git push origin features/poc` + **VM docker rebuild** (Node).
- Env `DRAIN_DISK_RECOUNT_ENABLED` default-on (unset = enabled); set `false` to disable.
- Smoke: crawl a site whose homepage yields 0 crawlable links → expect a `[drain-guard] disk-confirmed drain …` log and clean completion at ~90s (exit code 2, the normal-success code — NOT exit 6/stall), no manual relaunch.

## Follow-up (separate)

Time-boxed static investigation of the memory-storage counter/flush desync (why `handled` did not increment for the 1-request crawl). Decide afterward whether a root fix is worth it; the backstop stands regardless.

## Post-review corrections (2026-07-01)

Two wording fixes from the final adversarial review (the code is correct; only this doc was imprecise):
- **Exit code:** mid-run clean completion goes through `gracefulShutdown('COMPLETED', … ?? 2)` → **exit code 2**, the normal-success code every naturally-draining crawl uses (the orchestrator treats it as success). Wherever this doc says "exit 0", read "clean success terminal (exit 2), not the exit-6 stall". Literal `exit 0` is only the *startup* early-exit path (`main.ts:945`), not the mid-run abort.
- **Stall threshold:** `ProgressMonitor` default is **600s** (10 min); the incident VM overrode `PROGRESS_STALL_THRESHOLD_MS` to `1200000` (hence the log's 1200s). The drain guard fires at ~90s — well under either — so pre-emption holds regardless.
