# Design: Reconciliation Leader Election + Start-Crawl Heartbeat Guard

**Date:** 2026-04-18
**Service:** crawler-service
**Status:** Approved

## Problem

When 7 crawler-service replicas restart simultaneously (e.g., `docker compose up -d`), stale job detection races across replicas and produces duplicate failure webhooks — plus a dangerous secondary effect where a replica kills its own freshly-started crawl.

### Observed incident (crawl `5644`, 2026-04-17 14:55–14:56)

The failure webhook fired **7 times** after a `docker compose up -d`:

| Time | Replica | Event |
|------|---------|-------|
| 14:55:18 | 71 | Stale detection → webhook #1 |
| 14:55:18 | 72 | Stale detection → webhook #2 |
| 14:55:21 | 73 | Stale detection → webhook #3 |
| 14:55:22 | 75 | PHP scheduler resubmitted `/start` — 75 accepts, new crawl starts |
| 14:55:25 | 70 | Stale detection (old batch view) → webhook #4 |
| 14:55:33 | 75 | Reconciliation on its OWN fresh crawl → kills own PID 13 → webhook #5 |
| 14:55:41 | 74 | Stale detection → webhook #6 |
| 14:56:23 | 75 | Killed process dies (exit -9) → normal failure flow → webhook #7 |

### Root causes

**Issue #1 — Concurrent reconciliation races.** Every replica's `reconcile_jobs` loop runs independently and reads its own batch snapshot of Redis. On restart, all replicas see the same stale jobs simultaneously and each fires a webhook. No arbitration decides who owns the failure detection.

**Issue #2 — Replica kills its own fresh crawl.** When the PHP scheduler resubmitted crawl `5644` at 14:55:22, replica-75 accepted it. But `start_crawl` didn't write a fresh `last_heartbeat` — only `start_time`. In the meantime, replica-70's concurrent reconciliation overwrote the `job_data` with stale fields (old `replica_id=bf561798abcb`, old `last_heartbeat`). Replica-75's next reconciliation saw `status=running, remote (replica: bf561798abcb), last_heartbeat 616s ago` and killed its own freshly-spawned PID 13. The existing "local process override" (line 1809) gates on `is_local_job`, which was False because Redis now held the old replica_id — so the override didn't apply.

**Issue #3 (out of scope for this spec)** — The original crawl on `bf561798abcb` never sent a failure webhook before being SIGKILLed on shutdown. This is a separate `shutdown()` / Docker `stop_grace_period` problem, to be brainstormed next.

## Decision

Combine three small, targeted fixes:

1. **Reconciliation leader election** — only one replica runs `reconcile_jobs` at a time, chosen via Redis `SETNX reconcile_leader_lock` with TTL. Eliminates duplicate detection work and duplicate webhooks.
2. **Fresh `last_heartbeat` in `start_crawl`** — initial `job_data` includes `last_heartbeat = datetime.utcnow()`, closing the 60-second window where Redis shows a stale heartbeat from a previous replica.
3. **Ownership-agnostic local override** — the stale-detection "skip if local process is alive" branch no longer requires `is_local_job`. If the crawl_id is in `self.local_processes` with `returncode is None`, it's our process — skip stale detection regardless of what Redis says about `replica_id`.

## Design

### 1. Leader Lock in `reconcile_jobs`

**Location:** Top of `reconcile_jobs`, before the existing scanning logic (around line 1742).

```python
async def reconcile_jobs(self):
    """... existing docstring ..."""
    # --- LEADER ELECTION ---
    # Only one replica runs reconciliation at a time. Without this, multiple
    # replicas race on stale-job detection and each fires a failure webhook.
    leader_lock_key = "reconcile_leader_lock"
    my_replica_id = os.uname().nodename
    lock_ttl = settings.RECONCILE_INTERVAL_SECONDS * 2  # safety margin for slow scans
    acquired = await cache_service.redis_client.set(
        leader_lock_key, my_replica_id, nx=True, ex=lock_ttl
    )
    if not acquired:
        logger.debug("Reconciliation skipped: another replica holds the leader lock.")
        return

    try:
        # ... existing scanning logic unchanged ...
    finally:
        # Ownership-safe release: only delete the lock if we still own it.
        # Prevents a replica from releasing a lock that TTL-expired and was
        # re-acquired by a different replica during a long-running scan.
        try:
            current_owner = await cache_service.redis_client.get(leader_lock_key)
            if isinstance(current_owner, bytes):
                current_owner = current_owner.decode()
            if current_owner == my_replica_id:
                await cache_service.redis_client.delete(leader_lock_key)
        except Exception as e:
            logger.warning(f"Could not release reconciliation leader lock: {e}")
```

**TTL rationale:** `RECONCILE_INTERVAL_SECONDS * 2` gives a generous safety margin. If the leader dies mid-scan, the lock expires and the next replica takes over on the following cycle. If the scan legitimately exceeds the TTL (rare — scans are seconds, not minutes), the ownership-safe release prevents the leader from clobbering a new leader's lock.

### 2. Fresh `last_heartbeat` in `start_crawl`

**Location:** `start_crawl`, the initial `job_data` dict (line 147).

Add `last_heartbeat` to the dict:

```python
job_data = {
    "crawl_id": crawl_id, "status": "starting", "domain": domain,
    "start_url": start_url, "start_time": datetime.utcnow(),
    "last_heartbeat": datetime.utcnow(),
    "storage_path": job_storage_path,
    "callback_url": callback_url,
    "failure_callback_url": failure_callback_url, "pid": None,
    "crawl_mode": params.get("crawlMode", "standard"),
    "previous_crawl_id": params.get("previousCrawlId"),
    "params": params,
    "oom_restart_count": oom_restart_count,
    "replica_id": os.uname().nodename,
}
```

This closes the 60-second blind window between `start_crawl` writing initial state and the first monitor-loop heartbeat tick.

### 3. Ownership-Agnostic Local Override in Stale Detection

**Location:** `reconcile_jobs`, the existing local-override check (lines 1808-1814).

**Before:**

```python
if is_stale and is_local_job and status != "stopping":
    if crawl_id in self.local_processes:
        proc = self.local_processes[crawl_id]
        if proc.returncode is None:
            logger.info(f"Job '{crawl_id}' heartbeat is stale but local process is alive (PID {proc.pid}). Skipping stale detection.")
            is_stale = False
```

**After:**

```python
if is_stale and status != "stopping" and crawl_id in self.local_processes:
    proc = self.local_processes[crawl_id]
    if proc.returncode is None:
        logger.info(
            f"Job '{crawl_id}' heartbeat is stale in Redis but local process "
            f"is alive (PID {proc.pid}, replica_id in Redis: {job_replica_id}). "
            f"Skipping stale detection."
        )
        is_stale = False
```

Key change: `is_local_job` removed from the condition. We no longer trust Redis for ownership — we trust `self.local_processes`, which is a strictly local, authoritative source of truth about what this replica is running.

### Interaction Between the Fixes

- **Leader election (fix 1)** prevents duplicate detection work — only one replica scans at a time, so only one webhook fires per stale job.
- **Fresh heartbeat (fix 2)** prevents the race window where a new `start_crawl` hasn't yet had its monitor loop run, so Redis still shows the previous replica's stale heartbeat.
- **Ownership-agnostic override (fix 3)** is the final safety net: if Redis state has been corrupted (e.g., another replica's reconciliation wrote stale fields), the owning replica still recognizes its own live process and skips the kill path.

All three together:
- Eliminate the 5+ duplicate webhooks observed in the incident.
- Prevent a replica from killing its own freshly-started crawl.
- Preserve self-healing (if a leader crashes, TTL ensures another replica takes over).

### Edge Cases

| Case | Behavior |
|------|----------|
| All 7 replicas start simultaneously | First to `SETNX` wins leader; others skip until TTL |
| Leader crashes mid-scan | Lock TTL expires (~2× interval); next replica takes over on following cycle |
| Leader scan exceeds TTL | Another replica may acquire the lock; ownership-safe release prevents the original leader from deleting the new leader's lock |
| PHP scheduler resubmits a stale crawl mid-reconciliation | Fresh heartbeat in `start_crawl` (fix 2) closes the blind window; ownership-agnostic override (fix 3) protects the owning replica |
| Redis briefly unavailable during leader election | `SETNX` call raises; caller catches, logs, and treats as "not leader" — we skip this cycle, reconciliation resumes when Redis recovers |
| `self.local_processes` grows stale (e.g., dict entry not cleared after process death) | The existing `proc.returncode is None` check handles this — a dead process has non-None returncode, override doesn't apply |

### What Stays Unchanged

- The scanning logic: status checks, heartbeat comparison, counter decrement, process kill, completion marker writing, webhook firing
- Stale-detection branches for `stopping` jobs — unchanged
- `start_crawl`'s lock claim, capacity checks, rollback paths — unchanged
- Webhook delivery in normal (non-stale) failure paths — unchanged
- Redis key naming (`crawl_job:{id}`, `crawl_lock:{id}`, `crawl_jobs:running_count`) — unchanged
- Python ↔ Node.js contract — unchanged
- Reconciliation interval (`RECONCILE_INTERVAL_SECONDS`) — unchanged

### Files to Modify

| File | Change |
|------|--------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Leader lock wrapper in `reconcile_jobs`; `last_heartbeat=now()` in `start_crawl`; ownership-agnostic local override |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | Tests: leader-lock early return; `start_crawl` writes heartbeat; local override skips stale detection regardless of `replica_id` |
| `apps-microservices/crawler-service/CLAUDE.md` | Brief note on reconciliation leader election and the Redis lock key |

## Alternatives Considered

### B: Per-job atomic claim
Keep all replicas running reconciliation, but before each job's "mark failed + webhook" branch, acquire `SETNX failure_claim:{crawl_id}` with TTL.

**Rejected:** adds one extra Redis round-trip per job per replica per reconciliation cycle. Doesn't reduce redundant scanning work. Leader election eliminates both duplicate webhooks AND duplicate scanning for the same code complexity.

### C: Read-verify-write (CAS) before mark-failed
Re-read the job from Redis before writing `failed`. If status or heartbeat changed, skip.

**Rejected:** still allows N replicas to each do a full scan + decision + re-read per cycle. Race windows narrow but not eliminated without WATCH/MULTI or Lua — at which point the implementation is more complex than leader election with no additional correctness benefit.

### D: Stop running reconciliation on multiple replicas (ops-only)
Configure only one replica to run reconciliation via env var.

**Rejected:** breaks self-healing. If the chosen replica is down, no reconciliation runs — stale jobs accumulate indefinitely. Leader election gives the same guarantee (single active scanner) with automatic failover.

## Future Extensions

Not in scope for this spec, but informed by this change:

1. **Explicit ownership handoff on start_crawl write** — use `SET EX ... XX` (set only if exists) variants or a Lua script to prevent concurrent writers from overwriting fresher state. Only worth adding if the ownership-agnostic override + leader election prove insufficient in production.
2. **Webhook idempotency keys** — add a `request_id` to failure webhook payloads so consumers (PHP scheduler) can dedupe defensively. Complementary to this fix but orthogonal.
3. **Reconciliation metrics** — export `reconciliation_runs_total`, `stale_jobs_detected_total`, `leader_acquisition_failures_total` to Prometheus once structured logs reveal any remaining patterns.
4. **Issue #3 (graceful shutdown webhook)** — next brainstorming session.
