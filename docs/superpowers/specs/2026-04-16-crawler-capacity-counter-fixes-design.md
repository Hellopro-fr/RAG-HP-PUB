# Design: Crawler Capacity Counter & OOM Relaunch Fixes

**Date:** 2026-04-16
**Service:** `crawler-service`
**Status:** Approved

## Problem

The global capacity counter (`crawl_jobs:running_count` in Redis) drifts out of sync with actual running processes. Observed symptoms:

- Capacity shows `6/7` while 7 crawls are listed as running (one is actually failed but still counted)
- Capacity reaches `8/7` — one more job running than the configured limit

Example log excerpt (crawl `5482`, 2026-04-14):

```
17:25:26 | Job '5482' (status: running, local) is stale! Last activity: 205s ago. Marking as failed.
17:25:27 | status changed to 'failed'
17:25:27 | Webhook 'failure' for '5482' sent (attempt 1). Status: 200
17:26:03 | Crawl '5482' exited with OOM_RELAUNCH (code 3). Slot preserved. Auto-relaunching...
17:26:03 | Relaunching OOM Job '5482' (Attempt 1/3)
```

A job marked `failed` at 17:25:27 gets auto-relaunched 36 seconds later because its subprocess finally exited with code 3 (OOM) after the stale-failed transition.

## Root Causes (four compounding bugs)

### Bug 1 — Stale handler doesn't decrement the counter

In `reconcile_jobs()` around lines 1676-1723, when a stale job transitions from `running`/`restarting_oom`/`stopping` to `failed`/`stopped`, the code publishes the status change and sends a webhook but never calls `safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)`. The counter stays inflated until the next reconciliation's bulk reset.

### Bug 2 — Stale handler doesn't kill the subprocess

A stale job is marked `failed` but its subprocess keeps running. When the process eventually exits (OOM at 17:26:03 in the example), the `_monitor_process` OOM handler fires on an already-failed job.

### Bug 3 — `_relaunch_oom_crawl` uses a stale `job_info` snapshot

The coroutine is scheduled with a point-in-time snapshot. If stale detection (or force-finish) updates Redis between scheduling and execution, the relaunch proceeds anyway because the local snapshot still shows `restarting_oom`.

### Bug 4 — `_monitor_process` schedules relaunch without re-checking current status

Between the status write (`restarting_oom`) and `asyncio.create_task(self._relaunch_oom_crawl(...))`, another actor can transition the job to a terminal state. The scheduling fires regardless.

### Bug 5 — `force_finish_crawl` can double-decrement

`force_finish_crawl` decrements the counter based on the status it reads at the start of the function. If stale detection (after Fix 1) already decremented, force-finish's own decrement causes over-decrement. Race exists today even without the other fixes — two concurrent `/force-finish` calls would have the same problem.

## Solution

Five surgical state-transition fixes in `app/core/crawler_manager.py`. The Redis counter remains authoritative for capacity; every path that changes a job's effective state keeps the counter in sync.

## Changes

### Fix 1 — Decrement counter in stale handler

**Where:** `reconcile_jobs()` inside the `if is_stale:` block, after `job_data["status"] = final_status`.

**What:** If the previous status was `running`, `restarting_oom`, or `stopping`, call `await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)` before publishing the update.

**Guard:** Skip decrement for jobs already in a terminal state (defensive — shouldn't reach here, but safe).

### Fix 2 — Kill subprocess in stale handler

**Where:** Same block, immediately after Fix 1.

**What:**
```python
if crawl_id in self.local_processes:
    proc = self.local_processes[crawl_id]
    if proc.returncode is None:
        self._kill_process_group(proc.pid)
        logger.info(f"Stale detection: killed process for '{crawl_id}' (PID {proc.pid}).")
```

Mirrors `force_finish_crawl`'s existing pattern exactly. The `returncode is None` check prevents killing a recycled PID.

### Fix 3 — Re-read status at top of `_relaunch_oom_crawl`

**Where:** Very top of `_relaunch_oom_crawl(self, job_info: dict)`.

**What:**
```python
current = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")
if not current or current.get("status") != "restarting_oom":
    logger.info(f"OOM relaunch for '{crawl_id}' aborted: status is {current.get('status') if current else 'gone'}, not restarting_oom.")
    return
```

No counter adjustment — Fix 1 already handled the decrement when stale detection changed the status.

### Fix 4 — Re-read status before scheduling OOM relaunch

**Where:** `_monitor_process()` right before `asyncio.create_task(self._relaunch_oom_crawl(job_info))`.

**What:**
```python
current = await cache_service.get_json(job_key)
if current and current.get("status") == "restarting_oom":
    asyncio.create_task(self._relaunch_oom_crawl(job_info))
else:
    logger.info(f"Skipping OOM relaunch for '{crawl_id}': status is now {current.get('status') if current else 'gone'}.")
```

Belt-and-suspenders with Fix 3.

### Fix 5 — Make `force_finish_crawl` idempotent

**Where:** `force_finish_crawl()` just before `safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)`.

**What:** Re-read the current status from Redis. Only decrement if status is still in the slot-holding set.

```python
current = await cache_service.get_json(job_key)
holding_slot_statuses = {"running", "restarting_oom", "stopping"}
if current and current.get("status") in holding_slot_statuses:
    await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
# else: slot already released
```

## Kill Signal Policy

Uses the existing `_kill_process_group` helper (SIGKILL on the process group via `os.killpg`). No SIGTERM/grace-period escalation added:

- Stale jobs have already failed the heartbeat responsiveness bar — they're unlikely to respond to SIGTERM
- The Node.js crawler has no SIGTERM handler, so SIGTERM would behave as SIGKILL after a timeout anyway
- Matches `force_finish_crawl`'s pattern exactly — consistent with existing "unrecoverable, kill it" semantics

## Edge Cases

| Scenario | Behavior with fixes |
|---|---|
| Stale job in `running` (heartbeat died, process stuck) | Fix 1 decrements → Fix 2 SIGKILLs → slot freed immediately |
| Stale job in `restarting_oom` (relaunch scheduled but not yet executing) | Fix 1 decrements → Fix 2 kills old process → Fix 3 aborts relaunch when it runs |
| Stale job in `stopping` (user called `/stop`, subprocess stuck) | Fix 1 decrements → Fix 2 SIGKILLs → transitions to `stopped`, not `failed` (existing logic preserved) |
| Process already exited (`returncode != None`) | Fix 2 skips the kill — no wasted syscall, no PID-recycle risk |
| Job on a different replica | Fix 2 skips (not in local `local_processes`); can't kill cross-replica anyway |
| `_monitor_process` sees exit code 3 after stale detection already ran | Fix 4 sees status is `failed`, skips scheduling. No ghost relaunch, no duplicate webhook |
| Force-finish called on a stale-marked job | Fix 5 re-reads status, sees terminal, skips decrement. No over-decrement |
| Concurrent `/force-finish` calls | Fix 5 protects: whichever reads first wins, other sees terminal status and skips |
| Counter goes negative through some other path | Existing reconciliation bulk reset (line 1753) still corrects it — unchanged |

## Files to Modify

| File | Action | Description |
|---|---|---|
| `crawler-service/app/core/crawler_manager.py` | UPDATE | All 5 fixes |
| `crawler-service/tests/test_crawler_manager.py` | CREATE or UPDATE | 7 new unit tests |
| `crawler-service/CLAUDE.md` | UPDATE | Brief note on counter-drift invariants |

## Commit Strategy

Five independent commits, one per fix. Each compiles, tests pass independently, each can be reverted surgically.

1. `fix(crawler): decrement running counter when stale detection marks job failed`
2. `fix(crawler): kill subprocess when stale detection marks job failed`
3. `fix(crawler): abort OOM relaunch if job status no longer restarting_oom`
4. `fix(crawler): skip OOM relaunch scheduling if status changed before task dispatch`
5. `fix(crawler): make force-finish idempotent against concurrent stale detection`

Each commit message is bilingual EN+FR per project convention.

## Testing Strategy

### Unit tests (mocked Redis + subprocess)

| Test | Scenario |
|---|---|
| `test_stale_handler_decrements_counter` | Seed a `running` job with stale heartbeat → run `reconcile_jobs` → assert counter decremented by 1 |
| `test_stale_handler_kills_process` | Mock `local_processes` entry with `returncode=None` → run reconcile → assert `_kill_process_group` called with correct PID |
| `test_stale_handler_skips_dead_process` | Mock entry with `returncode=1` (already exited) → run reconcile → assert kill NOT called |
| `test_relaunch_aborts_if_status_not_restarting_oom` | Seed job with `status="failed"` → call `_relaunch_oom_crawl` → assert no `start_crawl` invocation, counter unchanged |
| `test_monitor_skips_relaunch_if_status_changed` | Mock process exit code 3 → simulate status change to `failed` between write and schedule → assert relaunch NOT scheduled |
| `test_force_finish_idempotent_after_stale` | Seed job in terminal `failed` state (slot released) → call `force_finish_crawl` → assert counter NOT decremented again |
| `test_force_finish_still_works_on_active_job` | Seed job in `running` state → call `force_finish_crawl` → assert counter decremented once, process killed |

### Post-deploy log verification

```bash
grep "Stale detection: killed process" crawler.log  # Fix 2 fired
grep "OOM relaunch for '.*' aborted: status is" crawler.log  # Fix 3 fired
grep "Skipping OOM relaunch for '.*': status is now" crawler.log  # Fix 4 fired
```

### Counter-drift monitoring

Add a log line in the existing reconciliation bulk-reset path showing any `counter vs actual` delta. Before fixes: deltas of +1, +2 expected. After fixes: trend to 0.

## Rollback

Any single fix reverts independently. Full revert restores pre-fix behavior (drift returns, no new bugs). No schema, no Redis key, no contract changes.

## Non-goals

- Not redesigning counter to derive from process state (Option C — out of scope).
- Not adding SIGTERM graceful shutdown to the Node.js crawler (separate effort).
- Not changing `RECONCILIATION_INTERVAL_SECONDS` or `STALE_JOB_THRESHOLD_LOCAL`.
- Not touching the `/capacity` endpoint — it reads the counter; fixes keep the counter accurate.
