# Design — Crawler stale-detector reads completion marker (sub-problem A)

**Date:** 2026-04-30
**Status:** Approved (design); pending implementation plan
**Author:** Rindra ANDRIANJANAKA (designed with Claude)
**Service:** `apps-microservices/crawler-service` (Python, FastAPI, asyncio)
**Branch:** `features/poc`

**Related work:**
- Sibling sub-problems (separate specs):
  - **B** — BO webhook idempotency (Marketplace repo, deployed): `Marketplace/docs/superpowers/specs/2026-04-30-crawler-webhook-idempotency-design.md`. BO-side absorbs bogus failure webhooks emitted by THIS bug; A fix stops emission at source.
  - **C** — BO re-enqueue guard (Marketplace, separate spec, not yet drafted).
  - **D** — Background-queue offload of `syncFinalResults` (Marketplace, separate spec, not yet drafted).

---

## 1. Problem Statement

### 1.1 Observed incident — crawl 6244 (`airchaud-diffusion.fr`, 11 626 files)

Reconstructed from `docker compose logs -f crawler-service | grep 6244`:

```
15:00:04 replica 85 — start crawl
15:01:05 replica 85 — finish exit 2; status changed to 'finished'; lock released; counter decremented
15:01:05 replica 85 — Created completion marker for crawl '6244'
15:01:05 replica 85 — Webhook 'success' for '6244' sent (attempt 1). Status: 200
... 6 minutes pass ...
15:07:40 replica 85 — STALE-DETECT fires: "Job '6244' (status: running, local) is stale! Last activity: 456s ago. Marking as failed."
15:07:41 replica 85 — Webhook 'failure' for '6244' sent (attempt 1). Status: 200 (exit_code=-1, OOM)
```

The success path correctly wrote `_completion_marker.json` and updated Redis state to `finished` at 15:01:05. Six minutes later, the leader-elected reconciler running on replica 85 still saw the job with `status="running"` in Redis and fired the stale-failure path, emitting a bogus failure webhook (`exit_code=-1`, `Out Of Memory`).

### 1.2 Root cause (this spec's scope)

`_reconcile_locked()` in `app/core/crawler_manager.py:1865` flags any job with `status in ("running", "restarting_oom", "stopping")` and stale `last_heartbeat` as failed. It NEVER reads the on-disk `_completion_marker.json`. So if Redis state drifts to non-terminal (whatever the cause) while the marker correctly indicates termination, the reconciler will mark the already-terminal job failed and emit a spurious failure webhook.

### 1.3 Out-of-scope root cause

Why does Redis show `status="running"` at 15:07:40 when `_on_process_complete` set it to `finished` at 15:01:05? Possible causes (not investigated here):
- Cross-replica `set_json` race during shutdown
- Aborted Redis pipeline mid-publish
- Earlier reconciler tick on a different replica overwrote with stale snapshot

This spec does NOT investigate or fix the drift root cause. The fix here is defensive: trust the marker (single-writer, on local disk, more reliable than Redis cross-replica state).

### 1.4 Why fix at the crawler-service when BO sub-problem B already absorbs the bogus webhook

BO sub-problem B (deployed) stops the bogus failure webhook from corrupting BO state. This sub-problem A stops the bogus webhook from being EMITTED. Both fixes complement each other — A removes the cause, B removes the consequence. Either alone closes the bug; together they survive a wider set of unforeseen orderings.

---

## 2. Goals & Non-Goals

### Goals

- **G1:** When `_reconcile_locked` would flag a job as stale-failed AND the on-disk completion marker says the crawl already terminated, reconcile Redis state from the marker and skip the failure webhook.
- **G2:** Marker missing or malformed → fall through to existing stale-failure path (current behavior, safest default).
- **G3:** No change to the existing successful or failed termination paths (`_on_process_complete`, `_handle_oom_max_restart`, `_on_oom_relaunch_failed`, `force_finish_crawl`). The existing marker writes at those paths are untouched.
- **G4:** New tests (4 cases) covering marker-finished / marker-failed / marker-missing / marker-malformed.
- **G5:** No new dependencies. Reuse existing `aiofiles` + `json` stdlib pattern.

### Non-Goals

- **NG1:** Investigate or fix the Redis status drift root cause. Separate.
- **NG2:** Change marker writing in the existing stale-failure path (`crawler_manager.py:1985-1997`). Untouched.
- **NG3:** Telemetry / metrics around reconciliation events. Future work.
- **NG4:** Periodic marker-vs-Redis sweep cron. Future work.
- **NG5:** Apply marker check to non-stale jobs (fresh heartbeat). Defer until production data justifies.

---

## 3. Architecture

### 3.1 Single insertion point

Inside `_reconcile_locked` per-job loop (`crawler_manager.py:1892-2039`), at the top of the `if status in ("running", "restarting_oom", "stopping"):` branch (currently L1900), call a new helper that loads + validates the marker. If the marker indicates terminal state, reconcile Redis and `continue` (skip stale logic for that job).

### 3.2 Component diagram

```
_reconcile_locked  (existing, modified)
  │
  ├─ for each job in Redis (existing)
  │    │
  │    ├─ if status in ("running", "restarting_oom", "stopping"):
  │    │    │
  │    │    ├─ NEW: marker = await _load_completion_marker_or_none(storage_path)
  │    │    │    if marker:
  │    │    │      - decrement CRAWL_RUNNING_COUNT_KEY
  │    │    │      - delete CRAWL_LOCK_PREFIX + crawl_id
  │    │    │      - job_data["status"] = marker["final_status"]
  │    │    │      - cache_service.set_json(...)
  │    │    │      - _publish_update(crawl_id, marker_status)
  │    │    │      - log INFO "Reconciling from marker; webhook skipped"
  │    │    │      - continue
  │    │    │
  │    │    └─ (existing heartbeat-stale logic untouched)
  │    │
  │    └─ elif status in ("failed", "finished"):
  │         (existing — orphan lock cleanup, untouched)
  │
  └─ counter drift correction (existing, untouched)

_load_completion_marker_or_none  (NEW)
  - reads {storage_path}/_completion_marker.json
  - returns parsed dict if final_status in {"finished","failed","stopped"}
  - else returns None (missing / malformed / unknown final_status)
```

### 3.3 What stays unchanged

- `_on_process_complete` (success path marker write — `crawler_manager.py:844-855`).
- `_handle_oom_max_restart` (OOM-fail marker — `:356-366`).
- `_on_oom_relaunch_failed` (relaunch-fail marker — `:418-428`).
- `force_finish_crawl` (manual stop marker — `:959-968`).
- Stale-detection marker write (`:1985-1997`) — still fires for true stale jobs (no marker case).
- Counter correction (`:2042-2056`).
- Lock orphan cleanup for `failed`/`finished` (`:2029-2035`).

---

## 4. Code shape

### 4.1 New helper

```python
async def _load_completion_marker_or_none(self, storage_path: str) -> Optional[dict]:
    """
    Reads {storage_path}/_completion_marker.json and returns parsed dict if
    valid + has a recognized terminal final_status. Returns None otherwise.

    Used by _reconcile_locked to detect Redis state drift: a crawl may have
    completed (marker on disk) but Redis still shows status="running" due to
    a missed write, replica race, or aborted set_json. Trusting the marker
    avoids firing a spurious failure webhook.

    Pattern matches the read in app/router/crawler.py status endpoint.

    Suppresses all IO + JSON errors — failure to read = "no marker", which
    falls through to the existing stale-failure path (safest default).

    Args:
        storage_path: absolute path to the crawl's storage directory.

    Returns:
        Parsed marker dict (with final_status in {"finished","failed","stopped"})
        on success. None if the marker is missing, malformed, or has an
        unrecognized final_status.
    """
    if not storage_path:
        return None
    marker_path = os.path.join(storage_path, '_completion_marker.json')
    if not os.path.isfile(marker_path):
        return None
    try:
        async with aiofiles.open(marker_path, 'r') as f:
            content = await f.read()
        marker = json.loads(content)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(
            f"_load_completion_marker_or_none: failed to read {marker_path}: {e}"
        )
        return None

    final_status = marker.get("final_status")
    if final_status not in ("finished", "failed", "stopped"):
        logger.warning(
            f"_load_completion_marker_or_none: unknown final_status "
            f"'{final_status}' in {marker_path}"
        )
        return None
    return marker
```

### 4.2 Modified `_reconcile_locked` (insertion at top of `if status in (...):` branch, ~L1900)

```python
                if status in ("running", "restarting_oom", "stopping"):
                    # Marker check (NEW): Redis may show non-terminal status
                    # while the on-disk completion marker indicates the crawl
                    # already ended (state drift from missed write or replica
                    # race — observed on crawl 6244 where success path wrote
                    # marker + status='finished' but Redis status remained
                    # 'running' 6 minutes later when reconciler fired).
                    #
                    # Trust marker as ground truth; skip the failure webhook
                    # (already sent at original finalize) and reconcile Redis
                    # state. Counter decrement + lock release still required —
                    # those resources were held by the stale running entry.
                    storage_path = job_data.get("storage_path", "")
                    marker = await self._load_completion_marker_or_none(storage_path)
                    if marker:
                        marker_status = marker["final_status"]
                        logger.info(
                            f"Job '{crawl_id}' has completion marker "
                            f"(final_status='{marker_status}') but Redis status "
                            f"is '{status}'. Reconciling from marker; webhook skipped."
                        )
                        # Release global slot (was held by stale running entry).
                        await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                        # Release distributed lock if still held.
                        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
                        # Reconcile Redis state from marker.
                        job_data["status"] = marker_status
                        if "last_heartbeat" in job_data:
                            del job_data["last_heartbeat"]
                        await cache_service.set_json(all_job_keys[i], job_data)
                        await self._publish_update(crawl_id, marker_status)
                        # Skip remaining stale-detection logic for this job.
                        continue

                    # ... existing heartbeat/stale logic unchanged ...
                    last_heartbeat_str = job_data.get("last_heartbeat")
                    # (rest of L1904-2024 unchanged)
```

The single `continue` skips both the stale-failure path AND the `true_running_count += 1` / `stale_jobs_count += 1` accumulators. The reconciled job is no longer in either bucket. Counter logic at L2042-2056 will see `true_running_count` exclude this job → triggers self-correcting drift log if the counter was stale.

### 4.3 Tests (new class)

```python
class TestStaleHandlerCompletionMarker:
    """
    Verifies _reconcile_locked reads on-disk completion marker before
    declaring a job stale. Covers the crawl 6244 incident where Redis
    state drifted to 'running' despite successful finalize + marker write.
    """

    @pytest.mark.asyncio
    async def test_marker_finished_reconciles_redis_skips_webhook(
        self, mocker, tmp_path
    ):
        # Setup: Redis status='running', stale heartbeat (600s ago),
        # marker on disk says final_status='finished'.
        # Expect: cache_service.set_json called with status='finished';
        # NO _send_failure_webhook call; safe_decrement_key called once;
        # delete_key called for the lock.
        ...

    @pytest.mark.asyncio
    async def test_marker_failed_reconciles_redis_skips_webhook(
        self, mocker, tmp_path
    ):
        # Same as above with marker.final_status='failed'.
        # Webhook was already sent by original failure path; reconciler
        # must NOT re-send.
        ...

    @pytest.mark.asyncio
    async def test_marker_missing_falls_through_to_stale_failure(
        self, mocker, tmp_path
    ):
        # No marker file + stale heartbeat → existing stale path fires
        # (webhook sent, status set to 'failed').
        ...

    @pytest.mark.asyncio
    async def test_marker_malformed_falls_through_to_stale_failure(
        self, mocker, tmp_path
    ):
        # Marker file exists but invalid JSON → fall through, log warning.
        ...
```

Tests reuse fixtures from existing `TestStaleHandlerCounter` / `TestStaleHandlerKillProcess`. Mock `cache_service`; use real `aiofiles.open` against `tmp_path` for the marker file.

---

## 5. Failure modes

| # | Scenario | Outcome | Acceptable? |
|---|----------|---------|-------------|
| F1 | Marker missing | Helper returns None. Existing stale logic runs (current behavior). | Yes — primary safe default. |
| F2 | Marker JSON malformed | Helper returns None + WARNING log. Existing stale logic runs. | Yes — defensive. |
| F3 | Marker `final_status="finished"` | Reconcile Redis → finished. Counter decrement. Lock release. NO webhook. | Yes — primary target (crawl 6244). |
| F4 | Marker `final_status="failed"` | Reconcile → failed. Counter decrement. Lock release. NO webhook (already sent at original failure). | Yes. |
| F5 | Marker `final_status="stopped"` | Reconcile → stopped. Counter decrement. Lock release. NO webhook. | Yes — same as stop-cleanup path. |
| F6 | Marker `final_status` unknown value | Helper returns None + WARNING log. Existing stale logic runs. | Yes — defensive. |
| F7 | `storage_path` missing/empty in job_data | Helper returns None immediately. Existing stale logic runs. | Yes. |
| F8 | Concurrent reconciler on different replica also reads marker | Both reconcile. `set_json` is last-writer-wins. Counter may double-decrement → drift, corrected by reconciliation L2042-2056. | Yes — counter self-corrects. |
| F9 | Marker file exists but unreadable (permission, IO error) | Helper returns None + WARNING log. Existing stale logic runs. | Yes — defensive. |
| F10 | Marker write was incomplete (partial JSON) | `json.JSONDecodeError` → helper returns None. Existing stale logic runs. | Yes — defensive. |

---

## 6. Verification (manual + automated)

### 6.1 Local pytest

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager.py::TestStaleHandlerCompletionMarker -v
```
Expected: 4 cases pass.

### 6.2 Local docker compose smoke test

1. Start crawler-service stack: `docker compose up -d crawler-service`
2. Trigger a short test crawl, let it finish normally
3. Force Redis state drift manually:
   ```bash
   docker compose exec redis redis-cli SET 'crawl_jobs:{id}' '{"crawl_id":"...","status":"running","last_heartbeat":"<6 min ago>","storage_path":"/app/storage/{id}",...}'
   ```
4. Wait next reconciliation tick (≤300s) OR manually call the reconciler
5. Expected log line:
   ```
   Job '{id}' has completion marker (final_status='finished') but Redis status is 'running'. Reconciling from marker; webhook skipped.
   ```
6. Verify Redis status now `finished`. Verify no failure webhook in BO logs (counterpart `script_process_detect_fiche_produit.php` `/var/log/php_errors.log`).

### 6.3 Production (Ecritel)

- Deploy crawler-service container update via standard release.
- Watch `docker compose logs -f crawler-service | grep "completion marker"` after next big crawl (>5min syncFinalResults).
- Confirm BO `php_errors.log` does NOT receive bogus failure webhook for the just-finished crawl. Cross-check with BO sub-problem B `[webhook-lock] dropped` log: it should NOT fire for those crawls anymore (because A side stops emitting).
- If a real stale job occurs (no marker, true crash), confirm existing stale path still works (failure webhook + status=failed in Redis).

---

## 7. Out of scope

- Redis status drift root cause investigation (separate spec).
- Marker write atomicity (current write-then-rename pattern not implemented; if torn writes are observed, separate spec).
- Periodic marker-vs-Redis reconciliation cron (future work).
- Telemetry counter `stale_marker_reconciliations_total{final_status="..."}` (future work).
- Apply marker check to non-stale jobs (defer until justified by production data).
- Co-location refactor of marker read/write helpers (extract `marker_io.py` module — future, only if a third reader appears).

---

## 8. Open questions

- **[UNCLEAR]** Cause of Redis status drift on crawl 6244. Possible: `set_json` race during cross-replica shutdown, aborted Redis pipeline, earlier reconciler overwrite. Investigate separately. **Not blocking this fix** — the fix masks the symptom defensively.
- **[UNCLEAR]** Whether marker check should also apply to fresh-heartbeat jobs. Currently only triggers when reconciler iterates non-terminal job. Defensible scope; can widen later.

---

## 9. Future work

- **Drift root cause investigation:** capture full Redis writes for crawl 6244-class scenarios. Separate spec if reproducible.
- **Marker write atomicity:** if torn writes observed, switch to write-temp-then-rename pattern.
- **Periodic marker reconciliation:** broader sweep cron that scans `/app/storage/*` for orphan markers (e.g. crawl row deleted from Redis but marker remains).
- **Telemetry:** Prometheus counter for marker-driven reconciliations, exit_code distribution for stale-detected failures.
- **Sub-problem D** (BO background-queue offload of `syncFinalResults`): would shrink the lock-hold window and reduce the chance of state drift during long sync.
