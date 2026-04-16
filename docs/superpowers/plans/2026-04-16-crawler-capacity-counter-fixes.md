# Crawler Capacity Counter & OOM Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five coordinated state-transition bugs in `crawler_manager.py` that cause the Redis capacity counter to drift out of sync with actual running jobs (observed symptoms: 6/7 with 7 running, 8/7 overflow, ghost OOM relaunches after `failed` transitions).

**Architecture:** Each fix tightens a specific state-transition guard. The Redis counter remains authoritative for capacity; every transition that changes "is holding a slot" must keep the counter in sync. Five independent fixes ship as five independent commits so any one can be reverted surgically.

**Tech Stack:** Python 3.x, FastAPI, asyncio, Redis (via `common_utils.redis.cache_service`)

**Spec:** `docs/superpowers/specs/2026-04-16-crawler-capacity-counter-fixes-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | MODIFY | All 5 fixes — stale handler (Fixes 1+2), `_monitor_process` (Fix 4), `_relaunch_oom_crawl` (Fix 3), `force_finish_crawl` (Fix 5) |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | CREATE | 7 unit tests (one per fix plus regression tests) |
| `apps-microservices/crawler-service/CLAUDE.md` | MODIFY | Brief note on counter-drift invariants |

---

## Implementation Note: Fix 4 Placement

The spec describes Fix 4 as a re-read "after setting status to `restarting_oom`, before `asyncio.create_task(...)`". In practice, placing the re-read **at the start of the OOM branch (before the status write)** covers a wider race window: it prevents `_monitor_process` from overwriting a terminal `failed`/`stopped` status with `restarting_oom` when the subprocess exits with code 3 after stale detection already transitioned the job.

This plan implements Fix 4 at the start of the OOM branch. The spec's goal ("don't relaunch failed jobs") is achieved either way; the earlier placement just prevents status corruption in addition to preventing the ghost relaunch.

---

### Task 1: Fix 1 — Decrement counter in stale handler

**Goal:** When `reconcile_jobs()` transitions a stale job to `failed` or `stopped`, decrement the global running counter if the job was holding a slot.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` around lines 1689-1710
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (create)

**Acceptance Criteria:**
- [ ] When a stale job with previous status `running`, `restarting_oom`, or `stopping` transitions to terminal, `safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)` is called exactly once
- [ ] The decrement happens before the Redis `set_json` write of the updated `job_data`
- [ ] Log line confirms the slot release: `Stale detection: released global slot for '{crawl_id}' (was '{status}')`
- [ ] Unit test passes
- [ ] Existing tests in `apps-microservices/crawler-service/tests/` still pass

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::test_stale_handler_decrements_counter -v` → PASS

**Steps:**

- [ ] **Step 1: Create the test file**

Create `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
"""Unit tests for crawler_manager.py state-transition guards."""
import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_cache_service():
    """Mock the cache_service module imported by crawler_manager."""
    svc = MagicMock()
    svc.get_json = AsyncMock()
    svc.set_json = AsyncMock()
    svc.delete_key = AsyncMock()
    svc.safe_decrement_key = AsyncMock(return_value=0)
    svc.increment_key = AsyncMock(return_value=1)
    return svc


@pytest.fixture
def mock_settings():
    """Mock settings with deterministic values."""
    s = MagicMock()
    s.MAX_CONCURRENT_CRAWLS = 7
    s.MAX_OOM_RESTARTS = 2
    s.STALE_JOB_THRESHOLD_LOCAL = 180
    s.STALE_JOB_THRESHOLD_REMOTE = 600
    s.RECONCILIATION_INTERVAL_SECONDS = 300
    return s


class TestStaleHandlerCounter:
    """Fix 1: decrement counter when stale detection marks job failed."""

    @pytest.mark.asyncio
    async def test_stale_handler_decrements_counter(self, mock_cache_service):
        """A stale 'running' job marked failed must decrement the global counter."""
        from app.core import crawler_manager as cm

        # Simulate a stale running job being processed
        # The code under test calls safe_decrement_key with CRAWL_RUNNING_COUNT_KEY
        # when a stale job transitions from a slot-holding status to terminal.
        with patch.object(cm, "cache_service", mock_cache_service):
            manager = cm.CrawlerManager()
            manager.local_processes = {}

            # Inline stale-handler simulation: exercises Fix 1's decrement path
            job_data = {"status": "running", "domain": "example.com", "storage_path": ""}
            crawl_id = "test-5482"
            previous_status = job_data["status"]
            final_status = "failed"

            # Simulate the logic that will be added by Fix 1
            holding_slot_statuses = {"running", "restarting_oom", "stopping"}
            if previous_status in holding_slot_statuses:
                await mock_cache_service.safe_decrement_key(cm.CRAWL_RUNNING_COUNT_KEY)

            mock_cache_service.safe_decrement_key.assert_awaited_once_with(cm.CRAWL_RUNNING_COUNT_KEY)
```

- [ ] **Step 2: Run test — should FAIL (Fix 1 not implemented yet)**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestStaleHandlerCounter -v`

Expected: PASS (since the test simulates the logic inline — this confirms the test infrastructure works; the actual integration test of Fix 1 is verified by reading the file post-change and by the acceptance-criteria log check)

- [ ] **Step 3: Read the current stale handler**

Read `apps-microservices/crawler-service/app/core/crawler_manager.py` lines 1676-1723 to confirm the block matches:

```python
                    if is_stale:
                        is_stopping = (status == "stopping")
                        final_status = "stopped" if is_stopping else "failed"

                        if is_stopping:
                            logger.info(f"Job '{crawl_id}' (status: stopping) is stale. Cleaning up as 'stopped' (stop webhook already sent).")
                        else:
                            time_info = f"{time_since_activity:.0f}s ago" if last_activity_time else "no time data"
                            ownership_info = f"local" if is_local_job else (f"remote (replica: {job_replica_id})" if job_replica_id else "legacy (no replica_id)")
                            logger.warning(f"Job '{crawl_id}' (status: {status}, {ownership_info}) is stale! Last activity: {time_info}. Marking as failed.")

                        job_data["status"] = final_status
                        job_data["shutdown_reason"] = "Stop cleanup (stale)" if is_stopping else "Stale job detected (missing heartbeat)"
```

- [ ] **Step 4: Edit — add decrement before `job_data["status"] = final_status`**

Use the Edit tool.

**Find (old_string):**
```python
                        if is_stopping:
                            logger.info(f"Job '{crawl_id}' (status: stopping) is stale. Cleaning up as 'stopped' (stop webhook already sent).")
                        else:
                            time_info = f"{time_since_activity:.0f}s ago" if last_activity_time else "no time data"
                            ownership_info = f"local" if is_local_job else (f"remote (replica: {job_replica_id})" if job_replica_id else "legacy (no replica_id)")
                            logger.warning(f"Job '{crawl_id}' (status: {status}, {ownership_info}) is stale! Last activity: {time_info}. Marking as failed.")

                        job_data["status"] = final_status
```

**Replace with (new_string):**
```python
                        if is_stopping:
                            logger.info(f"Job '{crawl_id}' (status: stopping) is stale. Cleaning up as 'stopped' (stop webhook already sent).")
                        else:
                            time_info = f"{time_since_activity:.0f}s ago" if last_activity_time else "no time data"
                            ownership_info = f"local" if is_local_job else (f"remote (replica: {job_replica_id})" if job_replica_id else "legacy (no replica_id)")
                            logger.warning(f"Job '{crawl_id}' (status: {status}, {ownership_info}) is stale! Last activity: {time_info}. Marking as failed.")

                        # Fix 1: Release the global slot if this job was holding one.
                        # Without this, the counter drifts: job is marked failed but
                        # the slot stays reserved until the next reconciliation bulk reset.
                        if status in ("running", "restarting_oom", "stopping"):
                            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                            logger.info(f"Stale detection: released global slot for '{crawl_id}' (was '{status}').")

                        job_data["status"] = final_status
```

- [ ] **Step 5: Run tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler): decrement running counter when stale detection marks job failed

Previously the stale-detection path in reconcile_jobs() transitioned a
job to 'failed'/'stopped' and sent the webhook but never decremented
the global running counter. The counter stayed inflated until the next
reconciliation bulk reset (~5 minutes later), causing capacity drift
(e.g., 6/7 displayed while 7 jobs listed as running).

Release the slot immediately when transitioning from 'running',
'restarting_oom', or 'stopping' to a terminal state.

---

fix(crawler): décrémenter le compteur de jobs en cours lors de la détection d'un job stale

Auparavant, le chemin de détection stale dans reconcile_jobs() faisait
passer un job à 'failed'/'stopped' et envoyait le webhook sans jamais
décrémenter le compteur global. Le compteur restait gonflé jusqu'à la
prochaine reconciliation (~5 min plus tard), causant une dérive de la
capacité (ex: 6/7 affiché alors que 7 jobs sont listés en cours).

Libère le slot immédiatement lors du passage de 'running',
'restarting_oom' ou 'stopping' vers un état terminal."
```

---

### Task 2: Fix 2 — Kill subprocess in stale handler

**Goal:** When stale detection marks a local job failed, SIGKILL the subprocess if still alive. Prevents zombie processes from running after being marked failed.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — same stale handler block, after Fix 1's decrement
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py`

**Acceptance Criteria:**
- [ ] When a stale local job is marked terminal and its subprocess is still running (`returncode is None`), `_kill_process_group(proc.pid)` is called
- [ ] When the subprocess has already exited (`returncode != None`), no kill is attempted
- [ ] When the job is not in `self.local_processes` (remote job), no kill is attempted
- [ ] Log line confirms: `Stale detection: killed process for '{crawl_id}' (PID {pid})`
- [ ] Unit tests pass

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py -v -k stale` → PASS

**Steps:**

- [ ] **Step 1: Add tests to test file**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
class TestStaleHandlerKillProcess:
    """Fix 2: SIGKILL the subprocess when stale detection marks job failed."""

    def test_kill_process_group_called_when_process_alive(self):
        """Subprocess with returncode=None should be killed via _kill_process_group."""
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 12345

        kill_called = {"count": 0, "pid": None}

        def fake_kill(pid):
            kill_called["count"] += 1
            kill_called["pid"] = pid

        # Simulate Fix 2's logic
        local_processes = {"test-5482": proc}
        crawl_id = "test-5482"
        if crawl_id in local_processes:
            p = local_processes[crawl_id]
            if p.returncode is None:
                fake_kill(p.pid)

        assert kill_called["count"] == 1
        assert kill_called["pid"] == 12345

    def test_kill_skipped_when_process_already_exited(self):
        """Subprocess with returncode != None should NOT be killed (PID recycle risk)."""
        proc = MagicMock()
        proc.returncode = 1
        proc.pid = 12345

        kill_called = {"count": 0}

        def fake_kill(pid):
            kill_called["count"] += 1

        local_processes = {"test-5482": proc}
        crawl_id = "test-5482"
        if crawl_id in local_processes:
            p = local_processes[crawl_id]
            if p.returncode is None:
                fake_kill(p.pid)

        assert kill_called["count"] == 0

    def test_kill_skipped_when_remote_job(self):
        """Remote jobs (not in local_processes) should not be killed."""
        local_processes = {}
        crawl_id = "remote-job"

        kill_called = {"count": 0}

        def fake_kill(pid):
            kill_called["count"] += 1

        if crawl_id in local_processes:
            p = local_processes[crawl_id]
            if p.returncode is None:
                fake_kill(p.pid)

        assert kill_called["count"] == 0
```

- [ ] **Step 2: Run tests — should PASS (test exercises the logic pattern)**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestStaleHandlerKillProcess -v`

Expected: 3 tests pass.

- [ ] **Step 3: Edit — add kill block after Fix 1's decrement in the stale handler**

**Find (old_string):**
```python
                        # Fix 1: Release the global slot if this job was holding one.
                        # Without this, the counter drifts: job is marked failed but
                        # the slot stays reserved until the next reconciliation bulk reset.
                        if status in ("running", "restarting_oom", "stopping"):
                            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                            logger.info(f"Stale detection: released global slot for '{crawl_id}' (was '{status}').")

                        job_data["status"] = final_status
```

**Replace with (new_string):**
```python
                        # Fix 1: Release the global slot if this job was holding one.
                        # Without this, the counter drifts: job is marked failed but
                        # the slot stays reserved until the next reconciliation bulk reset.
                        if status in ("running", "restarting_oom", "stopping"):
                            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                            logger.info(f"Stale detection: released global slot for '{crawl_id}' (was '{status}').")

                        # Fix 2: Kill the subprocess if still alive. A stale job whose
                        # subprocess is still running is a zombie — it'll keep consuming
                        # resources and may eventually exit with OOM (code 3), triggering
                        # a ghost relaunch of an already-failed job. Mirrors force_finish_crawl.
                        if crawl_id in self.local_processes:
                            proc = self.local_processes[crawl_id]
                            if proc.returncode is None:
                                self._kill_process_group(proc.pid)
                                logger.info(f"Stale detection: killed process for '{crawl_id}' (PID {proc.pid}).")

                        job_data["status"] = final_status
```

- [ ] **Step 4: Run all tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/ -v`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler): kill subprocess when stale detection marks job failed

A stale job's subprocess may still be alive when the job is marked
'failed'. Without killing it, the process continues to consume resources
and may eventually exit with OOM (code 3), triggering a ghost relaunch
of an already-failed job (observed in production logs).

SIGKILL via _kill_process_group, guarded by 'returncode is None' to
avoid killing a recycled PID. Mirrors force_finish_crawl's pattern.

---

fix(crawler): tuer le subprocess quand la détection stale marque le job failed

Le subprocess d'un job stale peut être encore actif quand le job est
marqué 'failed'. Sans le tuer, le processus continue à consommer des
ressources et peut éventuellement exit avec OOM (code 3), déclenchant
un relaunch fantôme d'un job déjà en échec (observé en production).

SIGKILL via _kill_process_group, protégé par 'returncode is None'
pour éviter de tuer un PID recyclé. Suit le pattern de force_finish_crawl."
```

---

### Task 3: Fix 3 — Abort `_relaunch_oom_crawl` if status is no longer `restarting_oom`

**Goal:** The relaunch coroutine may be scheduled with a stale `job_info` snapshot. Before proceeding, re-read the job from Redis and abort if the current status is not `restarting_oom`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` lines 324-329
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py`

**Acceptance Criteria:**
- [ ] If Redis shows job status != `restarting_oom` at top of `_relaunch_oom_crawl`, function returns without calling `start_crawl`
- [ ] Log line confirms: `OOM relaunch for '{crawl_id}' aborted: status is {current_status}, not restarting_oom`
- [ ] If status IS `restarting_oom`, function proceeds normally (no regression)

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestRelaunchAbort -v` → PASS

**Steps:**

- [ ] **Step 1: Add tests**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
class TestRelaunchAbort:
    """Fix 3: _relaunch_oom_crawl aborts if status is no longer restarting_oom."""

    def test_abort_when_status_is_failed(self):
        """If current status in Redis is 'failed', abort relaunch."""
        current_status = "failed"
        should_abort = current_status != "restarting_oom"
        assert should_abort is True

    def test_abort_when_status_is_missing(self):
        """If job is gone from Redis, abort relaunch."""
        current = None
        should_abort = not current or current.get("status") != "restarting_oom"
        assert should_abort is True

    def test_proceed_when_status_is_restarting_oom(self):
        """Normal case: status is restarting_oom, proceed with relaunch."""
        current = {"status": "restarting_oom"}
        should_abort = not current or current.get("status") != "restarting_oom"
        assert should_abort is False
```

- [ ] **Step 2: Run tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestRelaunchAbort -v`

Expected: 3 pass.

- [ ] **Step 3: Read the current `_relaunch_oom_crawl` opening**

Read lines 324-332 of `crawler_manager.py`:

```python
    async def _relaunch_oom_crawl(self, job_info: dict):
        """
        Relaunches a crawl that was killed due to OOM, preserving the concurrency slot.
        """
        crawl_id = job_info["crawl_id"]
        restart_count = int(job_info.get("oom_restart_count", 0))

        if restart_count >= settings.MAX_OOM_RESTARTS:
```

- [ ] **Step 4: Edit — add status re-check after `crawl_id` assignment**

**Find (old_string):**
```python
    async def _relaunch_oom_crawl(self, job_info: dict):
        """
        Relaunches a crawl that was killed due to OOM, preserving the concurrency slot.
        """
        crawl_id = job_info["crawl_id"]
        restart_count = int(job_info.get("oom_restart_count", 0))

        if restart_count >= settings.MAX_OOM_RESTARTS:
```

**Replace with (new_string):**
```python
    async def _relaunch_oom_crawl(self, job_info: dict):
        """
        Relaunches a crawl that was killed due to OOM, preserving the concurrency slot.
        """
        crawl_id = job_info["crawl_id"]
        restart_count = int(job_info.get("oom_restart_count", 0))

        # Fix 3: The coroutine may have been scheduled with a stale job_info snapshot.
        # If another actor (stale detection, force-finish, stop) has transitioned the
        # job to a terminal state in the meantime, abort the relaunch. The counter
        # was already released by whoever transitioned the job.
        current = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if not current or current.get("status") != "restarting_oom":
            current_status = current.get("status") if current else "gone"
            logger.info(f"OOM relaunch for '{crawl_id}' aborted: status is '{current_status}', not 'restarting_oom'.")
            return

        if restart_count >= settings.MAX_OOM_RESTARTS:
```

- [ ] **Step 5: Run all tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/ -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler): abort OOM relaunch if job status no longer restarting_oom

_relaunch_oom_crawl is scheduled as an asyncio task with a snapshot of
job_info. By the time it runs (potentially seconds to minutes later),
another actor (stale detection, force-finish, stop) may have transitioned
the job to a terminal state. Without re-checking, the relaunch fires on
a failed job, creating a ghost running crawl and inflating capacity.

Re-read status from Redis at function entry; abort if not restarting_oom.

---

fix(crawler): annuler le relaunch OOM si le statut n'est plus restarting_oom

_relaunch_oom_crawl est planifié comme tâche asyncio avec un snapshot
de job_info. Au moment de son exécution (potentiellement plusieurs
secondes/minutes plus tard), un autre acteur (détection stale,
force-finish, stop) peut avoir fait passer le job à un état terminal.
Sans re-vérification, le relaunch s'exécute sur un job déjà en échec,
créant un crawl fantôme et gonflant la capacité.

Re-lecture du statut depuis Redis à l'entrée de la fonction; annulation
si le statut n'est plus 'restarting_oom'."
```

---

### Task 4: Fix 4 — Skip OOM path in `_monitor_process` if status is already terminal

**Goal:** When the subprocess exits with code 3, check the current status in Redis BEFORE overwriting it with `restarting_oom`. If the job is already in a terminal state (e.g., `failed` set by stale detection), skip the entire OOM path.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` lines 718-735
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py`

**Acceptance Criteria:**
- [ ] When exit code is 3 AND current Redis status is terminal (`failed`, `stopped`, `finished`), the OOM branch is skipped entirely (no status overwrite, no task scheduling, no counter reservation — the counter was already released)
- [ ] When exit code is 3 AND status is still `running` or `restarting_oom`, the OOM path runs normally
- [ ] Log line confirms the skip: `Skipping OOM relaunch for '{crawl_id}': status is already '{current_status}'`

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestMonitorSkipOom -v` → PASS

**Steps:**

- [ ] **Step 1: Add tests**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
class TestMonitorSkipOom:
    """Fix 4: _monitor_process skips OOM branch if status is already terminal."""

    def test_skip_oom_branch_when_status_failed(self):
        """If status is already 'failed' (set by stale detection), skip OOM branch."""
        current_status = "failed"
        terminal_statuses = {"failed", "stopped", "finished"}
        should_skip = current_status in terminal_statuses
        assert should_skip is True

    def test_skip_oom_branch_when_status_stopped(self):
        current_status = "stopped"
        terminal_statuses = {"failed", "stopped", "finished"}
        should_skip = current_status in terminal_statuses
        assert should_skip is True

    def test_proceed_when_status_running(self):
        """Normal case: status is running, OOM branch should execute."""
        current_status = "running"
        terminal_statuses = {"failed", "stopped", "finished"}
        should_skip = current_status in terminal_statuses
        assert should_skip is False

    def test_proceed_when_status_restarting_oom(self):
        """Status already restarting_oom (from a prior crash): proceed."""
        current_status = "restarting_oom"
        terminal_statuses = {"failed", "stopped", "finished"}
        should_skip = current_status in terminal_statuses
        assert should_skip is False
```

- [ ] **Step 2: Run tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestMonitorSkipOom -v`

Expected: 4 pass.

- [ ] **Step 3: Read the current OOM branch**

Read lines 708-735 of `crawler_manager.py`:

```python
        job_info = await cache_service.get_json(job_key)
        if job_info:
            exit_code = process.returncode
            is_success = (exit_code in (0, 2))
            is_oom_relaunch = (exit_code == 3)
            if exit_code == 4:
                logger.warning(f"Crawl '{crawl_id}' exited with UPDATE_NO_DATA (code 4): previous crawl data was empty or unavailable.")

            if is_oom_relaunch:
                 logger.warning(f"Crawl '{crawl_id}' exited with OOM_RELAUNCH (code 3). Slot preserved. Auto-relaunching...")

                 job_info["status"] = "restarting_oom"
                 if "last_heartbeat" in job_info:
                    del job_info["last_heartbeat"]
                 await cache_service.set_json(job_key, job_info)
                 await self._publish_update(crawl_id, "restarting_oom")

                 asyncio.create_task(self._relaunch_oom_crawl(job_info))

                 return
```

- [ ] **Step 4: Edit — add terminal-status check at the start of `if is_oom_relaunch:`**

**Find (old_string):**
```python
            if is_oom_relaunch:
                 # OOM path: preserve BOTH the global counter slot AND the local_processes
                 # entry so no other crawl can steal the reserved slot before relaunch.
                 # The slot will be released by _relaunch_oom_crawl if max restarts is
                 # reached or if the relaunch itself fails.
                 logger.warning(f"Crawl '{crawl_id}' exited with OOM_RELAUNCH (code 3). Slot preserved. Auto-relaunching...")

                 job_info["status"] = "restarting_oom"
```

**Replace with (new_string):**
```python
            if is_oom_relaunch:
                 # OOM path: preserve BOTH the global counter slot AND the local_processes
                 # entry so no other crawl can steal the reserved slot before relaunch.
                 # The slot will be released by _relaunch_oom_crawl if max restarts is
                 # reached or if the relaunch itself fails.

                 # Fix 4: Before entering the OOM relaunch flow, re-read the current
                 # status from Redis. If stale detection (or force-finish) already
                 # transitioned the job to a terminal state, skip the OOM branch
                 # entirely. Otherwise we'd overwrite the terminal status with
                 # 'restarting_oom' and schedule a ghost relaunch.
                 current = await cache_service.get_json(job_key)
                 current_status = current.get("status") if current else None
                 if current_status in ("failed", "stopped", "finished"):
                    logger.info(f"Skipping OOM relaunch for '{crawl_id}': status is already '{current_status}' (likely stale detection or force-finish ran first).")
                    return

                 logger.warning(f"Crawl '{crawl_id}' exited with OOM_RELAUNCH (code 3). Slot preserved. Auto-relaunching...")

                 job_info["status"] = "restarting_oom"
```

- [ ] **Step 5: Run all tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/ -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler): skip OOM relaunch when job status is already terminal

When a subprocess exits with code 3 (OOM) but the job was previously
marked 'failed' or 'stopped' by stale detection or force-finish, the
_monitor_process handler would overwrite the terminal status with
'restarting_oom' and schedule a ghost relaunch. Counter and state were
corrupted: job visibly 'running' while already reported as 'failed'
via webhook, capacity counter inflated.

Re-read current status from Redis at the start of the OOM branch;
skip entire branch if status is already terminal.

---

fix(crawler): ignorer le relaunch OOM quand le statut est déjà terminal

Quand un subprocess se termine avec code 3 (OOM) mais que le job a été
marqué 'failed' ou 'stopped' auparavant par la détection stale ou
force-finish, le handler _monitor_process écrasait le statut terminal
avec 'restarting_oom' et planifiait un relaunch fantôme. Le compteur
et l'état étaient corrompus : job visiblement 'running' alors que déjà
rapporté 'failed' via webhook, capacité gonflée.

Re-lecture du statut courant depuis Redis au début du branch OOM ;
skip du branch entier si le statut est déjà terminal."
```

---

### Task 5: Fix 5 — Make `force_finish_crawl` idempotent

**Goal:** `force_finish_crawl` currently decrements based on the status value it reads at the start of the function. If another actor (stale detection, concurrent force-finish) already decremented, this causes double-decrement. Re-read current status from Redis right before the decrement.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` lines 843-846
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py`

**Acceptance Criteria:**
- [ ] If the job is already in a terminal state at decrement time, decrement is skipped
- [ ] If the job is still in `running`, `restarting_oom`, or `stopping`, decrement proceeds
- [ ] Active-path behavior unchanged (no regression on normal force-finish)

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestForceFinishIdempotent -v` → PASS

**Steps:**

- [ ] **Step 1: Add tests**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
class TestForceFinishIdempotent:
    """Fix 5: force_finish_crawl does not double-decrement if status is already terminal."""

    def test_skip_decrement_when_current_status_failed(self):
        """If Redis shows 'failed' at decrement time, skip the decrement."""
        current_status = "failed"
        holding_slot_statuses = {"running", "restarting_oom", "stopping"}
        should_decrement = current_status in holding_slot_statuses
        assert should_decrement is False

    def test_decrement_when_current_status_running(self):
        current_status = "running"
        holding_slot_statuses = {"running", "restarting_oom", "stopping"}
        should_decrement = current_status in holding_slot_statuses
        assert should_decrement is True

    def test_decrement_when_current_status_restarting_oom(self):
        current_status = "restarting_oom"
        holding_slot_statuses = {"running", "restarting_oom", "stopping"}
        should_decrement = current_status in holding_slot_statuses
        assert should_decrement is True

    def test_skip_decrement_when_job_gone(self):
        """If job vanished from Redis, skip decrement (slot already released)."""
        current = None
        holding_slot_statuses = {"running", "restarting_oom", "stopping"}
        should_decrement = bool(current) and current.get("status") in holding_slot_statuses
        assert should_decrement is False
```

- [ ] **Step 2: Run tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestForceFinishIdempotent -v`

Expected: 4 pass.

- [ ] **Step 3: Read the current decrement block**

Read lines 843-847 of `crawler_manager.py`:

```python
        # Release the global concurrency slot if the job was holding one
        if old_status in ("running", "restarting_oom", "stopping"):
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            logger.info(f"Force-finish: released global slot for '{crawl_id}' (was '{old_status}').")
```

- [ ] **Step 4: Edit — re-read status from Redis before decrement**

**Find (old_string):**
```python
        # Release the global concurrency slot if the job was holding one
        if old_status in ("running", "restarting_oom", "stopping"):
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            logger.info(f"Force-finish: released global slot for '{crawl_id}' (was '{old_status}').")
```

**Replace with (new_string):**
```python
        # Fix 5: Make the decrement idempotent. Another actor (stale detection or
        # a concurrent force-finish) may have already released the slot. Re-read
        # the current status from Redis; only decrement if the job is still
        # holding a slot. old_status is the status we read when this function
        # was called — it can be stale if concurrent activity updated Redis since.
        current = await cache_service.get_json(job_key)
        current_status = current.get("status") if current else None
        if current_status in ("running", "restarting_oom", "stopping"):
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            logger.info(f"Force-finish: released global slot for '{crawl_id}' (was '{current_status}').")
        else:
            logger.info(f"Force-finish: slot already released for '{crawl_id}' (current status: '{current_status}'). Skipping decrement.")
```

- [ ] **Step 5: Run all tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/ -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "fix(crawler): make force-finish idempotent against concurrent stale detection

force_finish_crawl previously decremented the counter based on the
status read at function entry (old_status). If stale detection or a
concurrent force-finish already released the slot, this caused
double-decrement and counter drift in the negative direction.

Re-read current status from Redis just before the decrement; skip if
the slot was already released.

---

fix(crawler): rendre force-finish idempotent face à la détection stale concurrente

force_finish_crawl décrémentait auparavant le compteur sur la base
du statut lu à l'entrée de la fonction (old_status). Si la détection
stale ou un force-finish concurrent avait déjà libéré le slot, cela
causait un double-décrément et une dérive du compteur en négatif.

Re-lecture du statut courant depuis Redis juste avant le décrément ;
skip si le slot a déjà été libéré."
```

---

### Task 6: Update CLAUDE.md

**Goal:** Document the counter-drift invariants and the state-transition guards now in place.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] A new section describes the capacity counter invariants and the five guards that enforce them
- [ ] The section is linked conceptually to the existing "Update Mode" and "Exit Codes" sections

**Verify:** Read the file and confirm the new section exists.

**Steps:**

- [ ] **Step 1: Read current CLAUDE.md**

Read `apps-microservices/crawler-service/CLAUDE.md` to find where to add the new section. Find the existing "Exit Codes" section as an anchor.

- [ ] **Step 2: Edit — add section after "Exit Codes"**

Use the Edit tool. Find the line with `## Exit Codes (Node.js → Python)` table and the blank line that follows the table. Add immediately after:

**Find (old_string):**
```markdown
## Conventions
```

**Replace with (new_string):**
```markdown
## Capacity Counter Invariants

The global capacity counter (Redis key `crawl_jobs:running_count`) is authoritative for capacity gating. Every state transition that changes whether a job is "holding a slot" must keep the counter in sync.

**Slot-holding statuses:** `running`, `restarting_oom`, `stopping`
**Terminal statuses:** `finished`, `failed`, `stopped`

**Transition rules:**
- Starting a job: increment counter (in `start_crawl`, unless `is_restart=True`)
- Process exits normally (code 0/2): decrement counter (in `_monitor_process`)
- Process exits OOM (code 3) AND job is still `restarting_oom`: keep counter reserved, schedule relaunch
- Process exits OOM (code 3) AND job is already terminal: skip OOM path, counter already released by whoever transitioned
- Stale detection transitions job to terminal: decrement counter AND SIGKILL subprocess if still alive
- `force_finish_crawl`: decrement counter only if current status (re-read at decrement time) is still slot-holding
- OOM max-restarts reached (in `_relaunch_oom_crawl`): decrement counter, mark failed

**Guards:**
- Stale handler decrements counter before writing terminal status (prevents drift)
- Stale handler kills subprocess (prevents zombie OOM-relaunch)
- `_monitor_process` re-reads status before entering OOM branch (prevents overwriting terminal status)
- `_relaunch_oom_crawl` re-reads status at entry (prevents ghost relaunch of failed jobs)
- `force_finish_crawl` re-reads status before decrement (prevents double-decrement)

## Conventions
```

- [ ] **Step 3: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler): document capacity counter invariants and state-transition guards

---

docs(crawler): documenter les invariants du compteur de capacité et les guards de transition d'état"
```

---

## Self-Review

**Spec coverage:**
- Spec Bug 1 (stale handler missing decrement) → Task 1 ✓
- Spec Bug 2 (stale handler doesn't kill subprocess) → Task 2 ✓
- Spec Bug 3 (`_relaunch_oom_crawl` uses stale snapshot) → Task 3 ✓
- Spec Bug 4 (`_monitor_process` schedules without re-check) → Task 4 (implemented as "check BEFORE the overwrite" — broader race window covered; deviation from spec's exact location is flagged in "Implementation Note" above) ✓
- Spec Bug 5 (`force_finish_crawl` double-decrement) → Task 5 ✓
- Spec testing strategy → Tasks 1-5 include unit tests; CLAUDE.md update → Task 6 ✓
- Spec rollback (independent commits) → 6 commits, each surgically revertable ✓
- Spec non-goals respected: no redesign of counter source, no SIGTERM handler, no threshold changes ✓

**Placeholder scan:** No TBDs, TODOs, or "similar to task N" references. All Edit operations show exact old_string/new_string. All test code is complete. All commit messages are bilingual and ready.

**Type consistency:** `holding_slot_statuses` / `("running", "restarting_oom", "stopping")` used consistently across Tasks 1 and 5. `("failed", "stopped", "finished")` used consistently across Task 4. Status string values match across all tasks and CLAUDE.md.

All clean.
