# Stash/Unstash Follow-Up Fixes (Final Review Blockers)

> **Date:** 2026-05-19
> **Status:** Approved — ready for plan writing
> **Repo:** `RAG-HP-PUB`
> **Branch:** `features/poc`
> **Companion:** `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md` (the original feature spec, amended by this follow-up).

---

## 1. Problem

Final `superpowers-extended-cc:code-reviewer` audit of the stash/unstash feature (commits `21bf809f..7ebbb0c8`) flagged 7 items. Two were invalidated by direct verification against HEAD:

- **Compose mount regression** — FALSE. Archive-flow mounts live in the root `docker-compose.yml`, not the service-local `apps-microservices/crawler-service/docker-compose.yaml`. The service-local file only adds the 3 new stash mounts on top of the pre-existing `crawler_data:/app/storage` named volume. No regression.
- **`× 1.5` gzip multiplier missing in `_estimate_archive_required_bytes`** — FALSE. `crawler_manager.py:1533` returns `int(total * 1.5)`. Callsite at `stash_crawl:1944-1945` correctly applies the 1 GB floor on top.

Six actionable items remain. They group into three buckets:

- **Falsified observability** (1 item) — Prometheus counters promised in spec §2.10 + §10 and documented in `CLAUDE.md` as shipping; not implemented in code. `prometheus_client` is not imported anywhere in `crawler-service`.
- **Correctness bugs** (4 items) — extract-safety, two TOCTOU races, pre-flight fail-open violation.
- **Test coverage gap** (1 item) — `test_unstash_writes_request_marker` asserts only the timeout path; the marker write itself is unverified.

## 2. Goals

- Remove the false Prometheus claim from documentation and the original spec. Replace with structured log-line observability that operators can grep in production logs.
- Patch `tarfile.extractall` to use `filter="data"` so the unstash path is safe under CVE-2007-4559 and forward-compatible with Python 3.14's hard-reject default.
- Close the two TOCTOU races in `stash_crawl` / `unstash_crawl` by re-validating `stashed_at` and status on a fresh Redis read AFTER the ownership lock is acquired.
- Wrap the `stash_crawl` pre-flight measurement helpers in `try/except` so a measurement exception is logged and skipped (fail-open) rather than escalating to a generic 500.
- Replace the no-op `test_unstash_writes_request_marker` with a concrete capture that asserts the marker file path and content.

## 3. Non-Goals

- `datetime.utcnow()` → `datetime.now(timezone.utc)` migration. Project-wide deprecation; separate spec.
- Idempotent `gcloud rm` in `download_daemon.sh` 2-phase commit branch (orphan loop risk on flaky GCS). Defer until observed in production.
- gunzip CRC integrity check for stash tar (improvement, not a bug).
- Other test gaps from the audit (lock-held `operation` discriminator, `STASH_SHARED_PATH NOT cleaned` negative assert, lock release on failure path, daemon 2-phase failure-retention). Each is a separate single-test addition; not blocking deploy.

## 4. Architecture

No architectural change. All edits are surgical patches inside existing functions or single-line replacements in docs.

### 4.1 Observability replacement

Where the original spec promised a Prometheus counter, the implementation emits a structured `logger.warning` line with grep-friendly prefix. Example for the orphan case:

```python
logger.warning(
    f"UNSTASH_GCS_ORPHAN crawl_id={crawl_id} "
    f"elapsed_seconds={elapsed:.2f} "
    f"reason=cleanup_grace_expired"
)
```

Operators grep `UNSTASH_GCS_ORPHAN` in `crawler.log` to find orphans. Trade-off: no Grafana panel, but no new dependency and zero risk of false advertisement.

### 4.2 TOCTOU re-validation pattern

After lock acquire in both `stash_crawl` and `unstash_crawl`:

```python
# Re-validate after lock acquire: another replica may have completed the
# concurrent operation in the window between caller's job_info snapshot
# and our lock claim.
fresh_job_info = await cache_service.get_json(job_key)
if fresh_job_info is None:
    await self._release_ownership_lock(stash_lock_key, lock_value)
    raise HTTPException(404, detail="Job vanished from Redis during stash claim.")
# ... apply same pre-condition checks against fresh_job_info ...
```

The same `_release_ownership_lock(key, lock_value)` helper used in the `finally` block is reused here. On mismatch, we release explicitly so the `finally` block sees `lock_value = None` and does nothing.

### 4.3 Pre-flight fail-open wrap

```python
try:
    baseline_state = self._get_archives_disk_state(stash_dir)
    required_bytes = self._estimate_archive_required_bytes(job_storage_path)
    required_bytes = max(required_bytes, 1_073_741_824)
    if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
        raise HTTPException(503, detail={...})
except HTTPException:
    raise  # propagate the 503
except Exception as e:
    logger.warning(
        f"Stash pre-flight measurement failed for '{crawl_id}': {e}. "
        f"Proceeding without disk-space check."
    )
```

Mirrors the existing `archive_crawl` pattern.

### 4.4 Test rewrite shape

Replace timeout-only assertion in `test_unstash_writes_request_marker`:

```python
async def _capture_marker():
    for _ in range(50):
        await asyncio.sleep(0.05)
        files = list(req_dir.glob("*.request"))
        if files:
            return files[0].name, files[0].read_text()
    return None, None

capture_task = asyncio.create_task(_capture_marker())
# Run unstash with short timeout so it bails after the marker is written.
with pytest.raises(HTTPException):
    await cm_instance.unstash_crawl(stashed_job_info)
name, content = await capture_task
assert name == "test_id.request"
assert content == "test_id"
```

## 5. Implementation

### 5.1 `apps-microservices/crawler-service/app/core/crawler_manager.py`

**(a) `unstash_crawl` extract — line 2142**
```python
# OLD:
tar.extractall(path=target_storage)
# NEW:
tar.extractall(path=target_storage, filter="data")
```

**(b) `stash_crawl` TOCTOU — insert after line 1934 (post `_acquire_ownership_lock`)**

Add a fresh-read + re-validation block. The existing fresh-read at line 2001 (right before the local-data delete) is too late — the tar is already written and Redis still has stale state. Move the fresh-read earlier; reuse the same code path for both the existing late check and the new early check.

```python
# Re-validate AFTER lock acquire (TOCTOU close).
job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
fresh_job_info = await cache_service.get_json(job_key)
if fresh_job_info is None:
    await self._release_ownership_lock(stash_lock_key, lock_value)
    lock_value = None
    raise HTTPException(404, detail=f"Job '{crawl_id}' vanished from Redis.")
fresh_status = fresh_job_info.get("status")
if fresh_status in ("running", "restarting_oom", "stopping"):
    await self._release_ownership_lock(stash_lock_key, lock_value)
    lock_value = None
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error_code": "CRAWL_IS_ACTIVE", "current_status": fresh_status},
    )
if fresh_status == "archived":
    await self._release_ownership_lock(stash_lock_key, lock_value)
    lock_value = None
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error_code": "ALREADY_ARCHIVED"},
    )
if fresh_job_info.get("stashed_at"):
    await self._release_ownership_lock(stash_lock_key, lock_value)
    lock_value = None
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error_code": "ALREADY_STASHED", "stashed_at": fresh_job_info["stashed_at"]},
    )
# Use the fresh blob from here on.
job_info = fresh_job_info
```

The `finally` block must check `if lock_value is not None: await self._release_ownership_lock(...)` (already the case per the helper's `None`-guard).

**(c) `unstash_crawl` TOCTOU — symmetric**

Insert after the `_acquire_ownership_lock` call. Re-validate `stashed_at IS NOT NULL`. On mismatch, release + raise 409 `NOT_STASHED`.

**(d) `stash_crawl` pre-flight fail-open — wrap lines 1942-1960**

```python
try:
    baseline_state = self._get_archives_disk_state(stash_dir)
    logger.info(f"Stash disk state for '{crawl_id}': {baseline_state}")
    required_bytes = self._estimate_archive_required_bytes(job_storage_path)
    required_bytes = max(required_bytes, 1_073_741_824)
    if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
        logger.warning(
            f"Rejecting stash '{crawl_id}': insufficient disk space. "
            f"Required: {required_bytes}, Available: {baseline_state['free_bytes']}"
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "INSUFFICIENT_DISK_SPACE",
                "required_bytes": required_bytes,
                "available_bytes": baseline_state["free_bytes"],
                "disk_state": baseline_state,
            },
        )
except HTTPException:
    raise
except Exception as e:
    logger.warning(
        f"Stash pre-flight measurement failed for '{crawl_id}': {e}. "
        f"Proceeding without disk-space check (fail-open)."
    )
```

**(e) Orphan log line — rewrite for grep-friendly prefix**

Current orphan branch at `crawler_manager.py:2171-2176`:

```python
if gcs_cleanup_status == "deferred":
    logger.warning(
        f"Unstash cleanup-done marker not arrived within "
        f"{settings.UNSTASH_CLEANUP_GRACE_SECONDS}s for '{crawl_id}'. "
        f"GCS object may be orphaned at gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz."
    )
```

Replace with canonical grep prefix:

```python
if gcs_cleanup_status == "deferred":
    logger.warning(
        f"UNSTASH_GCS_ORPHAN crawl_id={crawl_id} "
        f"elapsed_seconds={settings.UNSTASH_CLEANUP_GRACE_SECONDS} "
        f"reason=cleanup_grace_expired "
        f"gcs_path=gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz"
    )
```

Operators run `grep UNSTASH_GCS_ORPHAN crawler.log` to inventory orphans.

### 5.2 `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`

**(a) Replace `test_unstash_writes_request_marker`** with the concrete-capture version from §4.4.

**(b) Add `test_stash_toctou_revalidation_blocks_concurrent_winner`**

```python
@pytest.mark.asyncio
async def test_stash_toctou_revalidation_blocks_concurrent_winner(cm_instance, base_job_info, mock_cache_service, monkeypatch):
    # Caller-passed job_info has no stashed_at; lock acquire succeeds.
    # Fresh Redis read inside stash_crawl returns the SAME crawl with
    # stashed_at set by a concurrent winner.
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    stashed_blob = dict(base_job_info)
    stashed_blob["stashed_at"] = "2026-05-19T10:00:00Z"
    mock_cache_service.get_json = AsyncMock(return_value=stashed_blob)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_STASHED"
    # Lock must have been released (eval called for compare-and-delete).
    assert mock_cache_service.redis_client.eval.call_count >= 1
```

**(c) Add `test_unstash_toctou_revalidation_blocks_concurrent_winner`** — symmetric. Caller-passed has `stashed_at`, fresh Redis read returns `stashed_at = None`. Assert 409 `NOT_STASHED` + lock released.

### 5.3 `apps-microservices/crawler-service/CLAUDE.md`

In the Stash section, replace the bullet that promises the Prometheus counter:

```markdown
# OLD:
7. On grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'` (orphan GCS object — `unstash_gcs_orphan_total` Prometheus counter incremented)

# NEW:
7. On grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'`. Orphan GCS object is logged as `UNSTASH_GCS_ORPHAN crawl_id=… elapsed_seconds=…` for operator grep.
```

### 5.4 `docs/daemon_guide.md`

In the orphan-troubleshooting block, replace:

```markdown
# OLD:
Prometheus counter `unstash_gcs_orphan_total` is incremented.

# NEW:
The service logs `UNSTASH_GCS_ORPHAN crawl_id=… elapsed_seconds=… reason=cleanup_grace_expired` in `crawler.log`. Grep that prefix to inventory orphans.
```

### 5.5 `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`

Append an "Amendment 2026-05-19" section at the bottom documenting:
- Prometheus counters scope-out (replaced by structured log lines).
- TOCTOU race close (re-validation after lock acquire).
- `tarfile.extractall(filter="data")` hardening.
- `stash_crawl` pre-flight fail-open wrap.
- `test_unstash_writes_request_marker` rewritten with real capture.

Reference this follow-up spec by path.

## 6. Test plan

- New unit tests added to `test_crawler_manager_stash.py`. Existing 15 pass count goes to 17 (or 18 after rewriting the no-op one).
- `pytest tests/test_crawler_manager_stash.py -v` → all pass.
- Full suite `pytest --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py --ignore=tests/test_routes_invalid_page.py -q` → no regression.
- Daemon parametrization `bash apps-microservices/crawler-service/tests/test_daemon_parametrization.sh` → 4/4 pass (unchanged).
- Static grep: `grep -E "unstash_gcs_orphan_total|prometheus_client" apps-microservices/crawler-service docs/ -r` should match ONLY the amendment section in the spec doc (historical reference), not active code or docs.

## 7. Risks

- **TOCTOU fix adds 1 Redis hop per stash/unstash.** Negligible (1ms typical).
- **TOCTOU release calls `_release_ownership_lock` twice on the failure path** (once in early-return, once in `finally`). Helper's `None`-guard makes the second call a no-op; verify by ensuring `lock_value = None` is set after the early release.
- **Test polling helper** (`_capture_marker` with `asyncio.sleep(0.05)`) is timing-sensitive. Use generous retry count (50 iterations × 50ms = 2.5s) so CI machines under load don't flake.
- **Spec amendment in-place** vs new spec file. Convention: in-place amendment at bottom of existing spec, dated, with cross-reference to this follow-up spec.

## 8. Migration / Deploy

- No env var changes. No new dependencies.
- Deploy single rolling update of crawler-service. No daemon restart required (daemons untouched).
- Operator action: update any Grafana panels that referenced the never-shipped `unstash_gcs_orphan_total` counter (likely none, since the counter never existed). Document grep query for the new log prefix in operator handoff.

## 9. Out of scope (deferred follow-ups)

See §3.
