# Design — Clean stale completion marker on crawl relaunch

**Date:** 2026-05-12
**Status:** Approved (design); pending implementation plan
**Author:** Rindra ANDRIANJANAKA (designed with Claude)
**Service:** `apps-microservices/crawler-service` (Python, FastAPI, asyncio)
**Branch:** `features/poc`

**Related work:**
- Predecessor (deployed): `2026-04-30-crawler-stale-detector-marker-check-design.md` — sub-problem A. Added marker check inside `_reconcile_locked` to absorb Redis state drift. This spec fixes a regression introduced by that change: stale markers on relaunch now mislead the reconciler.

---

## 1. Problem Statement

### 1.1 Observed incident — crawl 6229 (dropData=true relaunch)

User relaunched a previously-finished crawl `id_domaine=6229` with `dropData=true`. Within seconds of the new run starting, crawler-service log shows:

```
crawler-service-90  | 2026-05-12 12:06:58 | INFO | app.core.crawler_manager | Job '6229' has completion marker (final_status='finished') but Redis status is 'running'. Reconciling from marker; webhook skipped.
crawler-service-90  | 2026-05-12 12:06:58 | INFO | app.core.crawler_manager | Published update for '6229': status changed to 'finished'
```

The reconciler picked up the previous run's `_completion_marker.json` (still on disk from when crawl 6229 finished cleanly) and treated the new running crawl as already-finished. Success webhook for the new run was **silently skipped**. BO never receives notification that the new crawl completed.

### 1.2 Root cause

`start_crawl` at `crawler_manager.py:129+` creates the job storage directory with `os.makedirs(job_storage_path, exist_ok=True)`. Because `exist_ok=True`, an existing directory from a prior run is reused as-is. No cleanup. The Node.js subprocess receives `--dropdata=true` and cleans Crawlee's RequestQueue, datasets, dedup/stats managers — but the Python-owned `_completion_marker.json` is NOT in Node.js's domain. It persists.

Within ≤300s, the leader-elected reconciler ticks. Its marker-check (added by sub-problem A) reads the stale marker, treats it as ground truth, declares the running crawl finished, and skips the success-webhook dispatch path.

### 1.3 Scope generality

The marker file has **5 distinct writers** (per recon §2):
1. Process finalize (success path)
2. OOM max-restart failure
3. OOM relaunch failure
4. Force-finish endpoint (manual stop)
5. Reconciler stale-detection write

Any of these writers can leave a stuck marker on disk. The current incident illustrates writer #1, but writers #2-5 produce the same bug class on subsequent relaunch. A fix at `start_crawl` covers all 5 symmetrically.

---

## 2. Goals & Non-Goals

### Goals

- **G1:** When `start_crawl` is invoked for a `crawl_id` that has an existing `_completion_marker.json` on disk, the file is deleted BEFORE the new subprocess is spawned and BEFORE the reconciler can read it.
- **G2:** Fail-open semantics: if the cleanup fails (permission, IO), the start proceeds. Existing observed symptom (false reconciliation) is the worst case — no regression.
- **G3:** Single insertion point. Helper named `_cleanup_stale_state_for_relaunch(crawl_id, storage_path)` reserves the extension point for future cleanups (Redis lock, local_processes dict, other persistent files).
- **G4:** No change to the 5 marker writers. They remain correct for their own write event.
- **G5:** No change to the marker reader (`_load_completion_marker_or_none`) or the reconciler logic. Sub-problem A's behavior is preserved for the case it was designed for (Redis state drift on still-finished jobs).

### Non-Goals

- **NG1:** Cleanup of stale Redis `crawl_lock:{crawl_id}` key on start_crawl. Future work — extension point reserved in the helper.
- **NG2:** Cleanup of stale `local_processes[crawl_id]` dict entry. Future work.
- **NG3:** Audit of OTHER persistent files in `storage_path` that may survive across runs (logs, temp files, update_storage subdir). Future work; the current bug class is the marker file specifically.
- **NG4:** Cleanup of stale archive tarballs in `/app/storage/archives/`. Out of scope — separate spec (`2026-04-18-archive-disk-space-preflight-design.md`).
- **NG5:** Changes to the dropData semantics on the Node.js side. The fix is on the Python side because the marker is Python-owned.
- **NG6:** Changes to the marker write paths in any of the 5 writers.

---

## 3. Architecture

### 3.1 Single new helper

```python
async def _cleanup_stale_state_for_relaunch(self, crawl_id: str, storage_path: str) -> None
```

Private method on `CrawlerManager`. Called from `start_crawl` after `os.makedirs(job_storage_path, exist_ok=True)`. Currently performs one cleanup (the completion marker). Reserves a single named extension point for the future items in NG1-NG3.

### 3.2 Why a helper for one cleanup

A direct 3-line `os.unlink` would also fix the bug. The helper is preferred because:
- It names the concept (relaunch cleanup) so future readers don't have to reverse-engineer intent.
- It centralizes additional cleanups (NG1, NG2) when their root causes are confirmed without churning the `start_crawl` call site again.
- It mirrors the helper style of sub-problem A's `_load_completion_marker_or_none` — same author / same pattern.

### 3.3 Component diagram

```
start_crawl(...)
  ├─ job_storage_path = .../<crawl_id>
  ├─ os.makedirs(job_storage_path, exist_ok=True)
  ├─ await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)   ── NEW
  │     └─ unlink {storage_path}/_completion_marker.json if exists
  │     └─ (future: delete crawl_lock, local_processes entry, ...)
  ├─ (existing) Redis state set to "running"
  └─ (existing) spawn Node.js subprocess

_reconcile_locked (per tick)
  └─ marker check (sub-problem A)
       └─ For any new crawl, marker is now ALWAYS gone at this point
         (unless the new run already terminated and wrote a fresh marker —
         in which case the new marker correctly indicates the new state).
```

### 3.4 What stays unchanged

- 5 marker writers (success / OOM / OOM-relaunch / force-finish / reconciler-stale)
- `_load_completion_marker_or_none` (marker reader)
- `_reconcile_locked` marker-check insertion site (sub-problem A)
- Node.js subprocess flow, dropData semantics
- Redis state-set in `start_crawl`
- `local_processes` dict population
- `crawl_lock:{crawl_id}` acquire

---

## 4. Code shape

### 4.1 New helper

```python
async def _cleanup_stale_state_for_relaunch(self, crawl_id: str, storage_path: str) -> None:
    """
    Wipes any persistent state from a prior run of this crawl_id that
    would mislead the reconciler or downstream consumers into thinking
    the new run is in a stale terminal state.

    Called at the top of start_crawl (after makedirs) BEFORE the new
    subprocess is spawned and BEFORE the new Redis state is written.

    Currently cleans:
      - {storage_path}/_completion_marker.json (any prior terminal marker:
        success, OOM-failure, OOM-relaunch-failure, force-finish, or
        reconciler-stale write — all 5 writers funnel here)

    Future items (deferred — see spec §7):
      - Stale crawl_lock:{crawl_id} Redis key
      - Stale local_processes[crawl_id] entry
      - Audit other persistent files in storage_path

    Fail-open: each cleanup logs and continues on error. A failed cleanup
    leaves the existing observed symptom (false marker reconciliation) —
    no regression. The error is surfaced in logs for triage.

    Args:
        crawl_id: identifier of the crawl being launched.
        storage_path: absolute path to {CRAWLER_STORAGE_PATH}/{crawl_id}/.
    """
    # 1. Completion marker — removes false signal that misleads the
    #    reconciler's marker-check (sub-problem A) into declaring the
    #    new running crawl finished and skipping its success webhook.
    marker_path = os.path.join(storage_path, '_completion_marker.json')
    if os.path.isfile(marker_path):
        try:
            os.unlink(marker_path)
            logger.info(f"Removed stale completion marker for crawl_id '{crawl_id}' (relaunch)")
        except OSError as e:
            logger.warning(f"Could not remove stale completion marker for '{crawl_id}': {e}")
```

### 4.2 Call site in `start_crawl`

In `crawler_manager.py` (currently ~L231-232 of `start_crawl`):

```python
# OLD
os.makedirs(job_storage_path, exist_ok=True)
logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")

# NEW
os.makedirs(job_storage_path, exist_ok=True)
logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")

# Wipe any persistent state from a prior run of this crawl_id before
# spawning the new subprocess. Observed bug (crawl 6229 with dropData=true):
# old _completion_marker.json survives makedirs, reconciler then declares
# the new running crawl finished and skips its success webhook.
await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)
```

### 4.3 No new imports

`os.unlink`, `os.path.join`, `os.path.isfile` — already imported in the file.
`logger` — already in scope.

---

## 5. Failure modes

| # | Scenario | Outcome | Acceptable? |
|---|----------|---------|-------------|
| F1 | Marker exists from prior finished run → unlink succeeds | New run has clean state. Reconciler tick later sees no marker. Success webhook of new run fires normally. | Yes — primary target (the crawl 6229 case). |
| F2 | Marker exists from prior failed/stopped run (writers 2-5) | Same as F1 — unlink covers all 5 writer origins. | Yes — covers full bug class. |
| F3 | Marker missing (fresh crawl_id, never run before) | `os.path.isfile` returns False → no-op. | Yes — clean default. |
| F4 | Permission denied on unlink (chmod, mount, etc.) | `OSError` caught, log WARNING, proceed with start. Reconciler may still hit the stale marker → existing observed symptom (not a regression). | Yes — fail-open. |
| F5 | Two replicas concurrently call start_crawl for same crawl_id | Both call unlink. One succeeds, other gets `FileNotFoundError` (subclass of OSError) → caught, log WARNING, proceed. Higher-level `crawl_lock:{crawl_id}` arbitrates which replica actually owns the run. | Yes — graceful. |
| F6 | Reconciler ticks BETWEEN our unlink and the new run finishing | Reconciler reads the now-absent marker → `_load_completion_marker_or_none` returns None → existing heartbeat-stale logic runs against the new run's fresh state. Normal behavior. | Yes — designed semantics. |
| F7 | Marker file replaced by a directory (extremely unlikely) | `os.path.isfile` returns False → no-op. Subsequent marker write at finalize would fail to overwrite a directory, but that's an unrelated edge. | Yes. |
| F8 | `storage_path` empty string or None | `os.path.isfile('/_completion_marker.json')` returns False → no-op. Defensive. | Yes. |
| F9 | New marker written by another path AFTER our unlink BUT BEFORE the new subprocess starts | None of the 5 writers fire during the start window — they all post-finalize. Theoretical only. | Acceptable — non-occurring in practice. |
| F10 | Reconciler races our unlink: reads marker → declares stale → writes a NEW stale-failure marker | Tiny window between makedirs and unlink. Reconciler's stale check requires `last_heartbeat` aged > threshold. New crawl just started → heartbeat fresh → reconciler won't fire stale path. | Yes — protected by heartbeat freshness. |

---

## 6. Verification (manual on Ecritel post-deploy)

### 6.1 Pytest (logic-shape style matching existing project)

Optional. Existing project test pattern is loose (see `tests/test_crawler_manager.py:18-93`). If a tiny test is added:

```python
class TestCleanupStaleStateForRelaunch:
    @pytest.mark.asyncio
    async def test_unlinks_existing_marker(self, tmp_path):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text('{"final_status": "finished"}')
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        await manager._cleanup_stale_state_for_relaunch("test-123", str(tmp_path))
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_missing_marker_is_noop(self, tmp_path):
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        # Should not raise
        await manager._cleanup_stale_state_for_relaunch("test-456", str(tmp_path))

    @pytest.mark.asyncio
    async def test_permission_error_logged_not_raised(self, tmp_path, mocker, caplog):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text("{}")
        mocker.patch("os.unlink", side_effect=PermissionError("denied"))
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        with caplog.at_level("WARNING"):
            await manager._cleanup_stale_state_for_relaunch("test-789", str(tmp_path))
        assert any("Could not remove stale completion marker" in r.message for r in caplog.records)
```

Run via Docker (host pytest blocked by missing `common_utils` per prior session findings):

```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py::TestCleanupStaleStateForRelaunch -v
```

### 6.2 Docker compose smoke test

1. Trigger a crawl on a small test domain. Let it finish naturally.
2. Confirm marker exists on disk:
   ```bash
   docker compose exec crawler-service ls -la /app/storage/<crawl_id>/_completion_marker.json
   ```
3. Relaunch the same `crawl_id` with `dropData=true`.
4. Immediately after relaunch start, confirm marker is GONE:
   ```bash
   docker compose exec crawler-service ls -la /app/storage/<crawl_id>/_completion_marker.json
   # Expected: No such file or directory (briefly, until new run completes)
   ```
5. Check logs for the cleanup line:
   ```bash
   docker compose logs -f crawler-service | grep "Removed stale completion marker"
   ```
   Expected: `Removed stale completion marker for crawl_id '<id>' (relaunch)`
6. Wait for the new run to finish.
7. Expected: success webhook dispatched normally. No `Reconciling from marker; webhook skipped` log line for this run.
8. Cross-check BO: `statut_crawler_eci=2` written via normal webhook path.

### 6.3 Production observation

After deploy, monitor for the regression-symptom log line:

```bash
docker compose logs crawler-service --since 24h | grep "Reconciling from marker; webhook skipped"
```

Expected: occurrences drop to near-zero. The marker-check path should now only fire for real Redis state drift (its original purpose), not for relaunches.

### 6.4 Regression check — fresh crawl_id

Trigger a crawl on a brand-new `crawl_id` (never run before). Expected:
- NO `Removed stale completion marker` log (marker didn't exist).
- Normal start_crawl flow.
- Crawl completes normally, marker written at finalize, success webhook dispatched.

### 6.5 Real Redis-drift case still works

Sub-problem A's primary scenario — Redis status drifts to running while marker on disk says finished — must still be caught. Manually force this:

1. Crawl finishes normally (marker exists, Redis status=finished).
2. Manually corrupt Redis to set status=running:
   ```bash
   docker compose exec redis redis-cli SET "crawl_jobs:<id>" '{"crawl_id":"<id>","status":"running",...stale_heartbeat...}'
   ```
3. **DO NOT** call start_crawl (no cleanup triggered).
4. Wait for reconciler tick.
5. Expected: `Reconciling from marker; webhook skipped` fires (sub-problem A's intended behavior).

This confirms the new cleanup doesn't break the existing sub-problem A path.

---

## 7. Out of scope

- Cleanup of stale `crawl_lock:{crawl_id}` Redis key (future — extension point reserved in helper).
- Cleanup of stale `local_processes[crawl_id]` dict entry (future).
- Audit of other persistent files in `storage_path` (logs, temp, update_storage subdir).
- Stale archive tarball cleanup (separate spec `2026-04-18-archive-disk-space-preflight-design.md`).
- Changes to dropData semantics on Node.js side.
- Changes to any of the 5 marker writers.
- Changes to the reader `_load_completion_marker_or_none` or the reconciler logic.
- Telemetry counter for relaunch cleanups.

---

## 8. Open questions

- **[UNCLEAR]** Whether other persistent files (logs, temp_dir, update_storage) exhibit the same stale-state issue on relaunch. Out of scope for this spec; flagged for future audit per NG3.
- **[UNCLEAR]** Whether the future cleanups (lock, local_processes) need the same fail-open semantics or stricter handling. Decide when those items become in-scope.

---

## 9. Future work

- **Extend the helper** to clean stale `crawl_lock:{crawl_id}` Redis key on start_crawl. Use `cache_service.delete_key`. Defensive against crashed prior runs.
- **Extend the helper** to clean `local_processes[crawl_id]` dict entry on start_crawl. `self.local_processes.pop(crawl_id, None)`.
- **Audit `storage_path`** for other persistent files that may mislead the reconciler or downstream consumers.
- **Telemetry counter** for relaunch cleanups (Prometheus `crawler_relaunch_marker_cleanups_total{result="removed|missing|failed"}`).
- **Generic cleanup framework** if more cleanup targets emerge — e.g. a registry of "stale-state cleaners" iterated on start.
