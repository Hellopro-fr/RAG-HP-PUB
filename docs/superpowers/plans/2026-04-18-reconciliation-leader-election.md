# Reconciliation Leader Election + Start-Crawl Heartbeat Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate duplicate failure webhooks and prevent replicas from killing their own freshly-started crawls by (1) adding leader election to `reconcile_jobs`, (2) writing a fresh `last_heartbeat` in `start_crawl`, and (3) making the stale-detection local override ownership-agnostic.

**Architecture:** Three independent, small modifications to `crawler_manager.py`. Leader election gates `reconcile_jobs` via `SET NX reconcile_leader_lock` with TTL. `start_crawl` writes `last_heartbeat=datetime.utcnow()` in the initial `job_data`. Stale detection's local override no longer requires `is_local_job` — it trusts `self.local_processes` as the authoritative source of ownership.

**Tech Stack:** Python 3.12, Redis `SET NX EX`, pytest + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-04-18-reconciliation-leader-election-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | MODIFY | Three small changes: fresh heartbeat in `start_crawl`; ownership-agnostic local override in stale detection; leader-lock wrapper around `reconcile_jobs` |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | MODIFY | Add `TestReconciliationLeaderElection` class with tests for each of the three changes |
| `apps-microservices/crawler-service/CLAUDE.md` | MODIFY | Brief note on reconciliation leader election and Redis lock key |

---

### Task 1: Write fresh `last_heartbeat` in `start_crawl`

**Goal:** Close the 60-second window where Redis holds a stale heartbeat from a previous replica between `start_crawl` and the first monitor-loop tick.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (around line 147-158, initial `job_data` dict)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add new test class)

**Acceptance Criteria:**
- [ ] `job_data` dict in `start_crawl` contains `last_heartbeat=datetime.utcnow()`
- [ ] New test verifies the field is set to a value close to "now" (< 5s delta)
- [ ] No regression in existing tests

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v` → all tests PASS

**Steps:**

- [ ] **Step 1: Update the `job_data` dict in `start_crawl`**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, find the existing `job_data` dict inside `start_crawl` (around lines 147-158):

**Find:**

```python
        # Build job data early (pid will be patched after spawn)
        job_data = {
            "crawl_id": crawl_id, "status": "starting", "domain": domain,
            "start_url": start_url, "start_time": datetime.utcnow(),
            "storage_path": job_storage_path,
            "callback_url": callback_url,
            "failure_callback_url": failure_callback_url, "pid": None,
            "crawl_mode": params.get("crawlMode", "standard"),
            "previous_crawl_id": params.get("previousCrawlId"),
            "params": params,
            "oom_restart_count": oom_restart_count,
            "replica_id": os.uname().nodename
        }
```

**Replace with:**

```python
        # Build job data early (pid will be patched after spawn).
        # last_heartbeat is set to now() immediately so concurrent reconciliation
        # on other replicas sees a fresh heartbeat — preventing the 60s blind
        # window between start_crawl and the first monitor-loop tick.
        now = datetime.utcnow()
        job_data = {
            "crawl_id": crawl_id, "status": "starting", "domain": domain,
            "start_url": start_url, "start_time": now,
            "last_heartbeat": now,
            "storage_path": job_storage_path,
            "callback_url": callback_url,
            "failure_callback_url": failure_callback_url, "pid": None,
            "crawl_mode": params.get("crawlMode", "standard"),
            "previous_crawl_id": params.get("previousCrawlId"),
            "params": params,
            "oom_restart_count": oom_restart_count,
            "replica_id": os.uname().nodename
        }
```

- [ ] **Step 2: Add a new test class to `test_crawler_manager.py`**

Append the following to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python


class TestReconciliationLeaderElection:
    """Tests for Issue #1 (leader election) and Issue #2 (fresh heartbeat,
    ownership-agnostic local override) in crawler_manager."""

    def test_start_crawl_writes_fresh_last_heartbeat(self):
        """start_crawl's initial job_data must include last_heartbeat=now().
        Asserted via source inspection because start_crawl is async and
        requires heavy Redis/process mocking to exercise end-to-end."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.start_crawl)
        assert '"last_heartbeat"' in source or "'last_heartbeat'" in source, (
            "start_crawl must include last_heartbeat in the initial job_data dict"
        )
```

- [ ] **Step 3: Run the tests**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestReconciliationLeaderElection::test_start_crawl_writes_fresh_last_heartbeat -v
```

Expected: PASSED.

Then run the full test file to confirm no regressions:

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler-service): write fresh last_heartbeat in start_crawl to close reconcile race window"
```

---

### Task 2: Remove `is_local_job` gate from the stale-detection local override

**Goal:** Trust `self.local_processes` as the authoritative source of process ownership, not `replica_id` in Redis. This prevents a replica from killing its own freshly-started crawl when another replica has overwritten the job_data with stale `replica_id`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (around lines 1808-1814, stale-detection local override)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add test to `TestReconciliationLeaderElection`)

**Acceptance Criteria:**
- [ ] The stale-detection local override no longer checks `is_local_job`
- [ ] A crawl_id present in `self.local_processes` with `proc.returncode is None` bypasses stale detection regardless of what Redis reports for `replica_id`
- [ ] Source inspection test passes

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestReconciliationLeaderElection -v`

**Steps:**

- [ ] **Step 1: Update the stale-detection local override**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, find the existing override (around lines 1808-1814):

**Find:**

```python
                    # Local job override: if process is alive locally, skip stale detection
                    if is_stale and is_local_job and status != "stopping":
                        if crawl_id in self.local_processes:
                            proc = self.local_processes[crawl_id]
                            if proc.returncode is None:
                                logger.info(f"Job '{crawl_id}' heartbeat is stale but local process is alive (PID {proc.pid}). Skipping stale detection.")
                                is_stale = False
```

**Replace with:**

```python
                    # Local process override: if our replica owns the live subprocess,
                    # skip stale detection — regardless of what Redis says about
                    # replica_id. Another replica may have overwritten our state with
                    # stale fields during a write race, but self.local_processes is
                    # the authoritative source for "is this process alive on this replica".
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

- [ ] **Step 2: Add a source-inspection test**

Append to the existing `TestReconciliationLeaderElection` class in `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python

    def test_stale_override_does_not_require_is_local_job(self):
        """The stale-detection local override must NOT gate on is_local_job.
        It must trust self.local_processes as the authoritative source of
        ownership — otherwise a replica can kill its own freshly-started
        crawl after another replica overwrote replica_id in Redis.

        Note: after Task 3, the scanning logic lives in reconcile_jobs
        (before Task 3) OR in _reconcile_locked (after Task 3). This test
        checks both to remain correct at any point in the task sequence."""
        import inspect
        from app.core import crawler_manager as cm

        # Check whichever method holds the scanning logic
        method = getattr(cm.CrawlerManager, "_reconcile_locked", None) or cm.CrawlerManager.reconcile_jobs
        source = inspect.getsource(method)
        # Find the local-override block: it must check local_processes
        # but NOT gate on is_local_job in the SAME condition.
        assert "crawl_id in self.local_processes" in source, (
            "stale detection must check self.local_processes in the local override"
        )
        # Ensure the phrase 'is_stale and is_local_job and' (the old gate) is absent.
        assert "is_stale and is_local_job and" not in source, (
            "stale detection must not gate the local override on is_local_job; "
            "self.local_processes alone is authoritative for process ownership"
        )
```

- [ ] **Step 3: Run the tests**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestReconciliationLeaderElection -v
```

Expected: both tests PASS.

Then run the full test file:

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler-service): trust local_processes over Redis replica_id in stale detection override"
```

---

### Task 3: Add leader election to `reconcile_jobs` (via helper-method pattern)

**Goal:** Only one replica runs reconciliation at a time, chosen via Redis `SET NX reconcile_leader_lock` with TTL. Eliminates duplicate failure webhooks when multiple replicas scan for stale jobs concurrently.

**Approach:** Use a helper-method pattern to avoid re-indenting the existing ~170-line reconciliation body. Rename the current `reconcile_jobs` to `_reconcile_locked` (the actual scanning logic), and make `reconcile_jobs` a new thin public wrapper that acquires the lock and calls `_reconcile_locked`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (rename method, add new wrapper)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add tests to `TestReconciliationLeaderElection`)

**Acceptance Criteria:**
- [ ] Public `reconcile_jobs(self)` is a thin wrapper that acquires `SET NX reconcile_leader_lock` with TTL `= RECONCILIATION_INTERVAL_SECONDS * 2`
- [ ] If lock is NOT acquired, return early (log at debug level)
- [ ] If lock IS acquired, call `_reconcile_locked()` inside a `try` and release the lock in `finally` — but only if this replica still owns it (ownership-safe release)
- [ ] `_reconcile_locked(self)` contains the original reconciliation logic, unchanged except the method name and docstring
- [ ] File still parses as valid Python
- [ ] Source-inspection tests verify the lock acquire + finally release are present

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestReconciliationLeaderElection -v`

**Steps:**

- [ ] **Step 1: Rename the existing `reconcile_jobs` method to `_reconcile_locked`**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, find the start of the existing `reconcile_jobs` method (around line 1742):

**Find:**

```python
    async def reconcile_jobs(self):
        """
        Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
        marks them as failed, and corrects the global running jobs counter.
        """
        logger.info("Starting job reconciliation...")
```

**Replace with:**

```python
    async def _reconcile_locked(self):
        """
        Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
        marks them as failed, and corrects the global running jobs counter.

        This is the actual reconciliation logic. It is called by the public
        `reconcile_jobs` wrapper only after the leader lock has been acquired —
        so the scan runs on exactly one replica at a time.
        """
        logger.info("Starting job reconciliation...")
```

This is a single, targeted rename — no other lines of the reconciliation body change. Indentation of the body is preserved exactly.

- [ ] **Step 2: Insert a new public `reconcile_jobs` method above `_reconcile_locked`**

In the same file, find the newly renamed method definition:

**Find:**

```python
    async def _reconcile_locked(self):
        """
        Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
        marks them as failed, and corrects the global running jobs counter.

        This is the actual reconciliation logic. It is called by the public
        `reconcile_jobs` wrapper only after the leader lock has been acquired —
        so the scan runs on exactly one replica at a time.
        """
```

**Replace with:**

```python
    async def reconcile_jobs(self):
        """
        Public wrapper: leader election + delegate to _reconcile_locked.

        Only one replica runs reconciliation at a time, chosen via a Redis
        SET NX lock. Without this, multiple replicas race on stale jobs and
        each fires duplicate failure webhooks.
        """
        leader_lock_key = "reconcile_leader_lock"
        my_replica_id = os.uname().nodename
        # TTL is 2x the reconciliation interval — enough safety margin to survive
        # a slow scan, and short enough to recover if the leader dies mid-scan.
        lock_ttl = settings.RECONCILIATION_INTERVAL_SECONDS * 2
        acquired = await cache_service.redis_client.set(
            leader_lock_key, my_replica_id, nx=True, ex=lock_ttl
        )
        if not acquired:
            logger.debug("Reconciliation skipped: another replica holds the leader lock.")
            return

        try:
            await self._reconcile_locked()
        finally:
            # Ownership-safe release: only delete the lock if we still own it.
            # This prevents a replica from releasing a lock that TTL-expired and
            # was re-acquired by a different replica during a long-running scan.
            try:
                current_owner = await cache_service.redis_client.get(leader_lock_key)
                if isinstance(current_owner, bytes):
                    current_owner = current_owner.decode()
                if current_owner == my_replica_id:
                    await cache_service.redis_client.delete(leader_lock_key)
            except Exception as release_err:
                logger.warning(f"Could not release reconciliation leader lock: {release_err}")

    async def _reconcile_locked(self):
        """
        Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
        marks them as failed, and corrects the global running jobs counter.

        This is the actual reconciliation logic. It is called by the public
        `reconcile_jobs` wrapper only after the leader lock has been acquired —
        so the scan runs on exactly one replica at a time.
        """
```

This inserts the new `reconcile_jobs` wrapper immediately above `_reconcile_locked`, preserving the latter's body at its original indentation. No other changes needed — the Python body of the original method remains intact under `_reconcile_locked`.

- [ ] **Step 3: Verify the file still parses as valid Python**

```bash
cd apps-microservices/crawler-service && python -c "import ast; ast.parse(open('app/core/crawler_manager.py').read()); print('syntax OK')"
```

Expected: `syntax OK`. If this fails, re-check Step 1 and Step 2 — specifically that the indentation level of the new `reconcile_jobs` method matches sibling methods (4 spaces for a class method).

- [ ] **Step 4: Add source-inspection tests for leader election**

Append to the existing `TestReconciliationLeaderElection` class in `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python

    def test_reconcile_jobs_acquires_leader_lock(self):
        """reconcile_jobs must attempt to acquire a SET NX leader lock at the top."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        assert "reconcile_leader_lock" in source, (
            "reconcile_jobs must use a 'reconcile_leader_lock' Redis key"
        )
        assert "nx=True" in source, (
            "reconcile_jobs must acquire the leader lock with SET NX"
        )
        assert "ex=" in source, (
            "reconcile_jobs must set a TTL on the leader lock"
        )

    def test_reconcile_jobs_returns_early_when_not_leader(self):
        """reconcile_jobs must return early when it does not acquire the lock."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        # Must have a guard that returns if acquisition failed
        assert "if not acquired" in source or "if acquired is False" in source, (
            "reconcile_jobs must guard on lock acquisition and return early when not leader"
        )

    def test_reconcile_jobs_releases_lock_ownership_safely(self):
        """reconcile_jobs must release the lock only if it still owns it,
        guarded by a finally block so a crash still triggers release attempt."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        assert "finally:" in source, (
            "reconcile_jobs must have a finally block for lock release"
        )
        # Ownership-safe release: read the current owner, compare, delete
        assert "current_owner" in source, (
            "reconcile_jobs must read the current lock owner before releasing"
        )
        assert "my_replica_id" in source, (
            "reconcile_jobs must track this replica's own id for ownership comparison"
        )

    def test_reconcile_jobs_delegates_to_reconcile_locked(self):
        """reconcile_jobs (public wrapper) must delegate actual work to _reconcile_locked."""
        import inspect
        from app.core import crawler_manager as cm

        assert hasattr(cm.CrawlerManager, "_reconcile_locked"), (
            "CrawlerManager must have a private _reconcile_locked method containing "
            "the actual reconciliation logic"
        )
        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        assert "self._reconcile_locked()" in source, (
            "reconcile_jobs wrapper must call self._reconcile_locked() "
            "to run the actual scanning logic"
        )

    def test_reconcile_locked_contains_scanning_logic(self):
        """The renamed _reconcile_locked method must contain the original scanning logic."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._reconcile_locked)
        # Smoke-check that the scanning logic is actually in _reconcile_locked
        assert "scan_keys_by_prefix" in source, (
            "_reconcile_locked must contain the original scan_keys_by_prefix call"
        )
        assert "stale_jobs_count" in source, (
            "_reconcile_locked must contain the original stale-job counter"
        )
```

- [ ] **Step 5: Run the tests**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestReconciliationLeaderElection -v
```

Expected: all 5 tests in `TestReconciliationLeaderElection` PASS (the 2 from earlier tasks + 3 new).

Then run the full test file:

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS (pre-existing + all new).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler-service): add leader election to reconcile_jobs to prevent duplicate webhooks"
```

---

### Task 4: Document the reconciliation leader election in CLAUDE.md

**Goal:** Record the new Redis lock key, the TTL formula, and why leader election exists, so future changes don't silently remove or break the guard.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] A new section or sub-section documents the `reconcile_leader_lock` key
- [ ] The TTL formula (`RECONCILIATION_INTERVAL_SECONDS * 2`) is documented with rationale
- [ ] Link to the spec is included

**Verify:** `grep -q "reconcile_leader_lock" apps-microservices/crawler-service/CLAUDE.md`

**Steps:**

- [ ] **Step 1: Find a good insertion point in CLAUDE.md**

Open `apps-microservices/crawler-service/CLAUDE.md` and find the "## Exit Codes (Node.js → Python)" heading (or equivalent later section — a natural place is before it, after the archiving/robots/camoufox sections).

- [ ] **Step 2: Add the new section**

Insert the following markdown immediately **before** the `## Exit Codes` heading:

```markdown
## Reconciliation Leader Election

`reconcile_jobs` runs on every replica's monitoring loop. To prevent multiple replicas from detecting the same stale job simultaneously (and each firing a duplicate failure webhook), only one replica runs the full scan at a time.

- **Lock key:** `reconcile_leader_lock` (Redis `SET NX`)
- **Lock TTL:** `RECONCILIATION_INTERVAL_SECONDS * 2` — safety margin for slow scans; auto-recovers if leader dies
- **Ownership-safe release:** the `finally` block only deletes the lock if the current Redis value equals this replica's `replica_id` — prevents a slow leader from clobbering a new leader's lock after TTL expiry

Complementary protections in the same fix:
- `start_crawl` writes `last_heartbeat=now()` in the initial `job_data` to close the 60-second blind window between start and the first monitor-loop heartbeat tick.
- The stale-detection local override trusts `self.local_processes` (not `replica_id` in Redis) as the authoritative source of process ownership. A replica never kills a PID it owns, regardless of what Redis reports.

Spec: `docs/superpowers/specs/2026-04-18-reconciliation-leader-election-design.md`.

```

- [ ] **Step 3: Verify the grep target succeeds**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && grep -q "reconcile_leader_lock" apps-microservices/crawler-service/CLAUDE.md && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler-service): document reconciliation leader election and related webhook-dedup fixes"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Fresh `last_heartbeat` in `start_crawl` initial job_data | Task 1 |
| `last_heartbeat` set to `datetime.utcnow()` (not None, not missing) | Task 1 (test `test_start_crawl_writes_fresh_last_heartbeat`) |
| Remove `is_local_job` gate from stale-detection override | Task 2 |
| Trust `self.local_processes` regardless of Redis `replica_id` | Task 2 (test `test_stale_override_does_not_require_is_local_job`) |
| Leader lock via `SET NX reconcile_leader_lock` with TTL | Task 3 |
| Lock TTL = `RECONCILIATION_INTERVAL_SECONDS * 2` | Task 3 |
| Early return when not leader | Task 3 (test `test_reconcile_jobs_returns_early_when_not_leader`) |
| Ownership-safe lock release in `finally` block | Task 3 (test `test_reconcile_jobs_releases_lock_ownership_safely`) |
| Existing scanning logic unchanged | Confirmed — moved verbatim into `_reconcile_locked` (test `test_reconcile_locked_contains_scanning_logic`) |
| Public `reconcile_jobs` delegates to `_reconcile_locked` | Task 3 (test `test_reconcile_jobs_delegates_to_reconcile_locked`) |
| Redis key naming conventions preserved | Confirmed — no existing keys renamed |
| Node.js ↔ Python contract unchanged | Confirmed — no Node.js or API-layer files touched |
| Documentation of the leader election pattern | Task 4 |
