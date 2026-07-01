# Crawler Mid-Run Drain Guard — Disk Recount Backstop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a genuinely-drained crawl self-terminate with a clean exit 0 even when memory-storage's `getInfo()` counters are wedged, instead of idling to the 1200s progress-stall (exit 6) and forcing a manual relaunch.

**Architecture:** Extend the existing 30s queue-stats interval (`main.ts:740-776`) with a second, disk-authoritative drain check. When the pool is idle but `getInfo()` counts don't reconcile (`handled+pending !== total`) for ~90s, recount the request-queue from disk (`recountQueueFromDisk`, the same primitive the startup repair trusts) and abort the pool iff the disk proves the queue drained. The existing `isDrainedSample` fast-path (counter-honest / head-wedged flavor) is unchanged; the new path covers the counter-wedged flavor. Gated default-on with a kill-switch env.

**Tech Stack:** TypeScript (Node), `@crawlee/memory-storage`, `node:test` via `npx tsx`. Repo: RAG-HP-PUB `apps-microservices/crawler-service/crawler`, branch `features/poc`.

**Spec:** `docs/superpowers/specs/2026-07-01-crawler-drain-guard-disk-recount-design.md`

---

## File Structure

- **`crawler/src/drainGuard.ts`** (modify) — add the pure predicate `isUnreconciledIdle` and the kill-switch resolver `resolveDrainDiskRecount` + derived const `DRAIN_DISK_RECOUNT_ENABLED`. Co-located with `isDrainedSample`/`DrainSample` so the drain module owns its predicate and its flag.
- **`crawler/src/drainGuard.test.ts`** (modify) — unit tests for the new predicate and resolver (`node:test`).
- **`crawler/src/main.ts`** (modify) — extend the queue-stats interval with the disk-confirm path; add one state var and two imports.

No new files. `recountQueueFromDisk` (`queueRepair.ts:24`) and `autoscaledPool.abort()` already exist and are tested.

---

### Task DG-T1: `isUnreconciledIdle` predicate + `DRAIN_DISK_RECOUNT_ENABLED` flag (drainGuard.ts, TDD)

**Goal:** A pure predicate that detects the "idle but counts don't reconcile" wedge signature, plus a default-on kill-switch resolver — both unit-tested.

**Files:**
- Modify: `crawler/src/drainGuard.ts`
- Test: `crawler/src/drainGuard.test.ts`

**Acceptance Criteria:**
- [ ] `isUnreconciledIdle` returns true only when `currentConcurrency===0 && totalRequestCount>0 && handled+pending !== total`.
- [ ] The 6599 case `{0, pending 0, handled 0, total 1}` → true.
- [ ] A reconciled idle queue `{0, pending 0, handled 174, total 174}` → false; a running pool `{1, …}` → false; pre-dispatch `{0,0,0,0}` → false.
- [ ] `resolveDrainDiskRecount` is default-on: `undefined`/`""`/`"true"` → true; only `"false"` (any case, trimmed) → false.
- [ ] All `drainGuard.test.ts` tests pass. (tsx transpiles the TS — an import/type/syntax error in `drainGuard.ts` fails the run, so a green run confirms the module compiles.)

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsx@4 --test src/drainGuard.test.ts` → all tests pass.
**NOTE — local `tsc --noEmit` is NOT usable:** `node_modules` is empty on this machine (deps live only in the Docker image), so `tsc` reports module-not-found for the entire codebase regardless of the change. The authoritative typecheck is the VM Docker build. Use the tsx test as the local signal.

**Steps:**

- [ ] **Step 1: Write the failing tests** — append to `crawler/src/drainGuard.test.ts`:

```ts
import { isUnreconciledIdle, resolveDrainDiskRecount } from "./drainGuard.js";

test("isUnreconciledIdle: true for the 0/0/1 counter wedge (crawl 6599)", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 1 }), true);
});
test("isUnreconciledIdle: false when counts reconcile at idle", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 174, totalRequestCount: 174 }), false);
});
test("isUnreconciledIdle: false while a task is running (concurrency > 0)", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 1, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 1 }), false);
});
test("isUnreconciledIdle: false at pre-dispatch start (total 0)", () => {
    assert.equal(isUnreconciledIdle({ currentConcurrency: 0, pendingRequestCount: 0, handledRequestCount: 0, totalRequestCount: 0 }), false);
});
test("resolveDrainDiskRecount: default-on; only 'false' disables", () => {
    assert.equal(resolveDrainDiskRecount(undefined), true);
    assert.equal(resolveDrainDiskRecount(""), true);
    assert.equal(resolveDrainDiskRecount("true"), true);
    assert.equal(resolveDrainDiskRecount("FALSE"), false);
    assert.equal(resolveDrainDiskRecount(" false "), false);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx@4 --test src/drainGuard.test.ts`
Expected: FAIL — `isUnreconciledIdle`/`resolveDrainDiskRecount` are not exported.

- [ ] **Step 3: Implement in `crawler/src/drainGuard.ts`** — append after `isDrainedSample`:

```ts
/**
 * Idle but the resolution counters don't reconcile → wedge suspect. Only meaningful
 * at concurrency 0: while the pool runs, in-progress requests make handled+pending < total
 * legitimately; at idle (nothing dispatched) handled+pending MUST equal total on a healthy
 * queue. When it doesn't, getInfo()'s counters are themselves wedged (the 0/0/N deadlock) —
 * which isDrainedSample cannot see. Callers confirm via a disk recount before acting.
 */
export const isUnreconciledIdle = (s: DrainSample): boolean =>
    s.currentConcurrency === 0 &&
    s.totalRequestCount > 0 &&
    s.handledRequestCount + s.pendingRequestCount !== s.totalRequestCount;

/** Resolves the disk-recount drain backstop kill-switch. Default true; only "false" disables. */
export const resolveDrainDiskRecount = (raw: string | undefined): boolean =>
    (raw ?? "true").trim().toLowerCase() !== "false";

/** Derived once at module load. Node-only, inherited by the crawler subprocess. */
export const DRAIN_DISK_RECOUNT_ENABLED: boolean =
    resolveDrainDiskRecount(process.env.DRAIN_DISK_RECOUNT_ENABLED);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx@4 --test src/drainGuard.test.ts`
Expected: PASS (6 existing + 5 new = 11).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/drainGuard.ts apps-microservices/crawler-service/crawler/src/drainGuard.test.ts
git commit -m "feat(crawler): isUnreconciledIdle predicate + DRAIN_DISK_RECOUNT flag"
```

---

### Task DG-T2: Wire disk-confirm drain path into the queue-stats interval (main.ts)

**Goal:** In the existing 30s interval, after the unchanged `isDrainedSample` fast-path, add the gated disk-confirm path: on `isUnreconciledIdle` sustained ~90s, recount from disk and abort the pool iff disk-drained.

**Files:**
- Modify: `crawler/src/main.ts` (imports ~line 52-53; interval block 736-776)

**Acceptance Criteria:**
- [ ] `main.ts` imports `isUnreconciledIdle` and `DRAIN_DISK_RECOUNT_ENABLED` from `./drainGuard.js`, and `recountQueueFromDisk` from `./queueRepair.js`.
- [ ] New `wedgeSuspectCount` state initialized to 0 beside `drainConfirmCount`.
- [ ] Disk-confirm path is gated by `DRAIN_DISK_RECOUNT_ENABLED` and the shared `drainAbortInitiated` latch, uses the same relative queue dir as the startup repair (`storage/request_queues/${domain}`), and aborts only when the disk recount satisfies `isDrainedSample`.
- [ ] Every referenced symbol is imported or in scope; `drainGuard.test.ts` still green.

**Verify:** local `tsc --noEmit` is unavailable (empty `node_modules` — see DG-T1 note). Verify by: (1) `cd apps-microservices/crawler-service/crawler && npx tsx@4 --test src/drainGuard.test.ts` → still green (confirms the drainGuard exports main.ts consumes are valid); (2) diff review confirming each referenced symbol is imported/in-scope. Authoritative typecheck = VM Docker build. (The pure predicate/resolver are covered in DG-T1; `recountQueueFromDisk` in `queueRepair.test.ts`.)

**Steps:**

- [ ] **Step 1: Extend the imports** — `crawler/src/main.ts`.

Change line 52 from:
```ts
import { repairQueueMetadata } from "./queueRepair.js";
```
to:
```ts
import { repairQueueMetadata, recountQueueFromDisk } from "./queueRepair.js";
```

Change line 53 from:
```ts
import { isDrainedSample, DRAIN_CONFIRM_SAMPLES } from "./drainGuard.js";
```
to:
```ts
import { isDrainedSample, isUnreconciledIdle, DRAIN_CONFIRM_SAMPLES, DRAIN_DISK_RECOUNT_ENABLED } from "./drainGuard.js";
```

- [ ] **Step 2: Add `wedgeSuspectCount` state** — change lines 738-739 from:

```ts
let drainConfirmCount = 0;
let drainAbortInitiated = false;
```
to:
```ts
let drainConfirmCount = 0;
let wedgeSuspectCount = 0;
let drainAbortInitiated = false;
```

- [ ] **Step 3: Replace the drain block** — inside the interval, replace lines 754-772 (from `const drainPool = …` through the closing `}` of the `if (drainPool && !drainAbortInitiated)` block) with the following complete block:

```ts
        const drainPool = (context.crawlerInstance as any)?.autoscaledPool;
        if (drainPool && !drainAbortInitiated) {
            const sample = {
                currentConcurrency: drainPool.currentConcurrency ?? 0,
                pendingRequestCount: info.pendingRequestCount ?? 0,
                handledRequestCount: info.handledRequestCount ?? 0,
                totalRequestCount: info.totalRequestCount ?? 0,
            };
            // Fast-path: getInfo counters honest but isEmpty()/queueHeadIds wedged.
            drainConfirmCount = isDrainedSample(sample) ? drainConfirmCount + 1 : 0;
            if (drainConfirmCount >= DRAIN_CONFIRM_SAMPLES) {
                drainAbortInitiated = true;
                console.warn(`[drain-guard] queue drained but crawler not finished (idle ${drainConfirmCount}x, handled ${info.handledRequestCount}/${info.totalRequestCount}, pending ${info.pendingRequestCount}) — aborting pool to complete cleanly.`);
                try {
                    await drainPool.abort();
                } catch (e) {
                    console.warn(`[drain-guard] abort failed: ${(e as Error).message}`);
                }
            }
            // Disk-confirm path: getInfo counters THEMSELVES wedged (handled+pending !== total
            // while idle — the 0/0/N deadlock isDrainedSample can't see). Recount from the
            // request files' orderNo (ground truth, same source as the startup repair) and abort
            // only if genuinely drained; a real backlog shows pending>0 → leave to progress-stall.
            if (!drainAbortInitiated && DRAIN_DISK_RECOUNT_ENABLED) {
                wedgeSuspectCount = isUnreconciledIdle(sample) ? wedgeSuspectCount + 1 : 0;
                if (wedgeSuspectCount >= DRAIN_CONFIRM_SAMPLES) {
                    const rc = recountQueueFromDisk(`storage/request_queues/${domain}`);
                    const diskDrained = isDrainedSample({
                        currentConcurrency: 0,
                        pendingRequestCount: rc.pending,
                        handledRequestCount: rc.handled,
                        totalRequestCount: rc.total,
                    });
                    if (diskDrained) {
                        drainAbortInitiated = true;
                        console.warn(`[drain-guard] disk-confirmed drain despite wedged counters (getInfo handled=${info.handledRequestCount}/${info.totalRequestCount}, disk handled=${rc.handled}/${rc.total}) — aborting pool to exit 0.`);
                        try {
                            await drainPool.abort();
                        } catch (e) {
                            console.warn(`[drain-guard] abort failed: ${(e as Error).message}`);
                        }
                    } else {
                        console.warn(`[drain-guard] idle+unreconciled ${wedgeSuspectCount}x but disk shows pending=${rc.pending}/${rc.total} — genuine work, not aborting.`);
                        wedgeSuspectCount = 0;
                    }
                }
            }
        }
```

- [ ] **Step 4: Typecheck**

Run: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`
Expected: no errors. Confirm `domain` and `storagePath` are in scope in the interval (they are — `storagePath` is used at the `writeFile` call above, `domain` at the startup repair `main.ts:718`).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler): mid-run disk-recount drain backstop (exit 0 on counter-wedge)"
```

---

## Self-Review

**Spec coverage:**
- §1 location / new predicate → DG-T1 (predicate + flag), DG-T2 (interval wiring). ✓
- §2 fast-path unchanged + disk-confirm path with reuse of `isDrainedSample` on recounted values → DG-T2 Step 3. ✓
- §3 gating default-on kill-switch → DG-T1 (`resolveDrainDiskRecount`/`DRAIN_DISK_RECOUNT_ENABLED`), DG-T2 (gate). ✓
- §4 no-false-abort / recount-failure-safe / pre-empts exit6 → DG-T2 (abort only on `diskDrained`; `recountQueueFromDisk` returns zeros on unreadable dir → `total 0` → not drained; interval `try/catch`). ✓
- §5 testing → DG-T1 tests + verify commands. ✓

**Placeholder scan:** none — all code blocks complete.

**Type consistency:** `DrainSample` fields (`currentConcurrency`, `pendingRequestCount`, `handledRequestCount`, `totalRequestCount`) match `drainGuard.ts`. `recountQueueFromDisk` returns `{pending, handled, total}` (`QueueCounts`) — used as `rc.pending/rc.handled/rc.total`. ✓

**Deploy:** `features/poc` push + VM docker rebuild; env `DRAIN_DISK_RECOUNT_ENABLED` default-on. Smoke: 0-link homepage crawl → `[drain-guard] disk-confirmed drain …` + clean exit 0 at ~90s.
