# Stash Bind-Mount Pre-Flight + Cleanup Scope Alignment

**Author:** Rindra ANDRIANJANAKA
**Date:** 2026-05-20
**Service:** `apps-microservices/crawler-service`
**Status:** Design approved — pending implementation plan
**Parent specs:**
- `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`
- `docs/superpowers/specs/2026-05-19-stash-unstash-followup-fixes-design.md`

---

## 1. Context

A production stash test on `2026-05-20 11:58:21` (crawl `1958`) revealed two latent issues in the stash/unstash flow shipped in commits `21bf809f..374c541b` + follow-ups.

**Symptom log:**

```
crawler-service-4 | WARNING | app.core.crawler_manager | Could not get disk state
  for '/app/stash': [Errno 2] No such file or directory: '/app/stash'
crawler-service-4 | INFO | Stashed crawl '1958' (147552574 bytes) -> /app/stash/1958.tar.gz
crawler-service-4 | INFO | Marked crawl '1958' as stashed at 2026-05-20T11:59:27.067104 in Redis.
crawler-service-4 | INFO | Deleted local storage for stashed crawl '1958'.
crawler-service-4 | INFO | "POST /stash/1958 HTTP/1.0" 202
```

**Diagnosis:** the running container was created on `2026-05-20T11:16:16` — BEFORE compose commit `14a02524` added the three stash bind-mounts. Docker-compose volume changes only apply at container creation, so the running container had stale mount declarations. `docker inspect` confirmed only 4 mounts (archive flow only) were active — none for stash.

When `POST /stash/1958` fired:

1. `os.makedirs("/app/stash", exist_ok=True)` (inside `_create_stash_archive`) silently created an **ephemeral in-container directory** in the overlay filesystem.
2. The 147 MB tar was written there.
3. Redis `stashed_at` was set; local crawl dir deleted.
4. The host-side upload daemon polls a HOST directory (`./crawler_stash/`) which received no file — the bind-mount that should have bridged container → host did not exist.
5. The tar lives only in the container's overlay layer; a `docker-compose down` would have destroyed it permanently.

The user rescued the tar with `docker cp` before recreate. The flow as shipped offered **no diagnostic** — the 202 response and INFO logs made it look like success.

A second observation emerged: the cleanup phase ran `shutil.rmtree(job_storage_path)`, which **removed the entire crawl folder including `crawler.log`, `_completion_marker.json`, and other markers**. The user expected only the data subdirs (datasets, request queues) to be deleted — matching the existing `archive_crawl._cleanup_local_data` behavior that preserves logs and markers for local inspection. The current stash code diverges silently from this established convention.

## 2. Scope

### In scope

- **Issue B — Defensive bind-mount pre-flight:** A new `_verify_bind_mount(path, label)` helper method on `CrawlerManager`. Called from `stash_crawl` (for `STASH_SHARED_PATH`) and from `unstash_crawl` (for `STASH_DOWNLOAD_REQUESTS_PATH` and `STASH_DOWNLOAD_RESULTS_PATH`). Raises `503 BIND_MOUNT_MISSING` with operator-actionable detail when `os.path.ismount()` returns False (covers both non-existent paths and ordinary dirs created by `os.makedirs`).
- **Issue C — Cleanup scope alignment:** Replace `shutil.rmtree(job_storage_path)` in `stash_crawl` with a `_cleanup_data_keep_logs()` inner function that mirrors `archive_crawl._cleanup_local_data`. Same `files_to_keep` set. Walks bottom-up, removes unkept files, removes empty subdirs.
- **Unit tests:** 5 new tests covering helper happy path, helper rejection paths (non-existent and ordinary dir), stash endpoint 503 propagation, unstash endpoint 503 propagation, and cleanup keep-logs file presence assertion.
- **Documentation:** new troubleshooting section in `docs/daemon_guide.md` covering: (a) the 503 `BIND_MOUNT_MISSING` symptom and recreate procedure, (b) recovery of tars trapped in pre-fix ephemeral container layers via `docker cp`.

### Out of scope

- Extending the bind-mount check to `archive_crawl` (same value, but separate change to keep this surgical).
- Startup-time bind-mount validation in `main.py` (fail-fast on boot). Useful but YAGNI for this iteration — per-endpoint 503 gives precise diagnostic at the call site that needs the mount.
- A `/health/bind-mounts` introspection endpoint. Ops-tool gold-plating; defer until requested.
- Optional `keep_logs=False` flag for callers that explicitly want full nuke. YAGNI.
- The unstash idempotency improvements identified in the earlier flow audit (LOW-1) — orthogonal, separate spec.

## 3. Architecture

### High-level flow (with new guards inline)

```
POST /stash/{id}
  1. Pre-condition checks (existing)
  2. Lock acquire (existing)
  3. TOCTOU re-validation against fresh Redis blob (existing)
  4. ★ NEW: _verify_bind_mount(STASH_SHARED_PATH, "stash upload")
            ── ismount? ─ no ─→ 503 BIND_MOUNT_MISSING (lock released by finally)
  5. Disk pre-flight (existing, fail-open)
  6. Tar to .staging + atomic rename (existing)
  7. Set Redis stashed_at (existing)
  8. ★ CHANGED: _cleanup_data_keep_logs() instead of full shutil.rmtree
  9. Return 202 (existing)

POST /unstash/{id}
  1. Pre-condition: stashed_at IS NOT NULL (existing)
  2. Lock acquire (existing)
  3. TOCTOU re-validation (existing)
  4. ★ NEW: _verify_bind_mount(STASH_DOWNLOAD_REQUESTS_PATH, "unstash requests")
            _verify_bind_mount(STASH_DOWNLOAD_RESULTS_PATH, "unstash results")
  5. Write .request marker, poll .done/.error (existing)
  6. ... rest of flow unchanged
```

### Components

| Component | Role |
|---|---|
| `crawler_manager.CrawlerManager._verify_bind_mount(path, label)` | NEW. Raises 503 if `os.path.ismount(path)` is False. |
| `crawler_manager.CrawlerManager.stash_crawl` | CHANGED. Calls `_verify_bind_mount` after TOCTOU. Replaces `_delete_local` (full nuke) with `_cleanup_data_keep_logs` (mirror archive). |
| `crawler_manager.CrawlerManager.unstash_crawl` | CHANGED. Calls `_verify_bind_mount` twice (requests + results dirs) after TOCTOU. |
| `tests/test_crawler_manager_stash.py` | NEW tests for helper + endpoint integration + cleanup file-set assertion. |
| `docs/daemon_guide.md` | NEW section: "Troubleshooting: 503 BIND_MOUNT_MISSING" + "Recovery from pre-fix stash trapped in ephemeral container". |

## 4. `_verify_bind_mount` helper

### Signature

```python
def _verify_bind_mount(self, path: str, label: str) -> None:
    """Raise 503 BIND_MOUNT_MISSING if path is not a real mount point.

    Detects the silent-data-loss case where docker-compose volumes
    were added but the container was not recreated. Without this guard
    Python's os.makedirs creates an ephemeral in-container dir; data
    written there is invisible to host-side daemons and lost on
    container recreate.

    Detection: os.path.ismount(p) returns True only for bind-mounts
    and named volumes — False for ordinary dirs (or non-existent paths).
    """
    if not os.path.ismount(path):
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "BIND_MOUNT_MISSING",
                "path": path,
                "label": label,
                "ops_action": "docker-compose --profile crawling up -d --force-recreate crawler-service",
                "hint": "Container was started before compose mount declaration; recreate required.",
            },
        )
```

### Response shape

```json
{
  "detail": {
    "error_code": "BIND_MOUNT_MISSING",
    "path": "/app/stash",
    "label": "stash upload",
    "ops_action": "docker-compose --profile crawling up -d --force-recreate crawler-service",
    "hint": "Container was started before compose mount declaration; recreate required."
  }
}
```

### Edge case matrix

| Path state | `os.path.ismount` | Result |
|---|---|---|
| Non-existent | False | 503 (correct — never useful) |
| Ordinary dir (created by `os.makedirs`) | False | 503 (the bug we're catching) |
| Bind-mount source dir present on host | True | Proceed |
| Named volume | True | Proceed |
| Symlink to mount point | typically False | 503 (compose doesn't use symlinks in this codebase) |

### Call site placement

| Caller | Path | Label | Position |
|---|---|---|---|
| `stash_crawl` | `settings.STASH_SHARED_PATH` | `"stash upload"` | After TOCTOU re-validation, before disk pre-flight |
| `unstash_crawl` | `settings.STASH_DOWNLOAD_REQUESTS_PATH` | `"unstash requests"` | After TOCTOU re-validation, before `.request` write |
| `unstash_crawl` | `settings.STASH_DOWNLOAD_RESULTS_PATH` | `"unstash results"` | Immediately after the requests check |

Lock release semantics: both endpoints rely on the existing `finally: await self._release_ownership_lock(...)` block — a 503 raised between lock-acquire and the success path is automatically released.

## 5. `_cleanup_data_keep_logs` inner function

### Current code (to replace)

```python
# crawler_manager.py:2126-2133
try:
    def _delete_local():
        if os.path.isdir(job_storage_path):
            shutil.rmtree(job_storage_path)
    await anyio.to_thread.run_sync(_delete_local)
    logger.info(f"Deleted local storage for stashed crawl '{crawl_id}'.")
except Exception as e:
    logger.warning(f"Local cleanup failed for stashed '{crawl_id}' (tar is safe): {e}")
```

### New code

```python
try:
    def _cleanup_data_keep_logs():
        """Remove crawl data files but keep logs + completion markers for
        local inspection. Mirrors archive_crawl._cleanup_local_data; the
        tar already contains everything so unstash restores full state.

        files_to_keep: matches archive_crawl exactly so operator UX is
        consistent across both flows.
        """
        files_to_keep = {
            'crawler.log', '_callback_payload.json',
            '_completion_marker.json', '_status_snapshot.json',
            '_exit_reason.json', '_update_report.json',
            'update_stats.json',
            'timing.jsonl', 'timing-summary.json',
        }
        if not os.path.isdir(job_storage_path):
            return
        for root, dirs, files in os.walk(job_storage_path, topdown=False):
            for name in files:
                if name not in files_to_keep:
                    try:
                        os.remove(os.path.join(root, name))
                    except OSError:
                        pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass  # non-empty (kept file inside) → leave dir

    await anyio.to_thread.run_sync(_cleanup_data_keep_logs)
    logger.info(f"Cleaned data (kept logs) for stashed crawl '{crawl_id}'.")
except Exception as e:
    logger.warning(f"Data cleanup failed for stashed '{crawl_id}' (tar is safe): {e}")
```

### Behavior

| File/dir | Before fix | After fix |
|---|---|---|
| `/app/storage/{id}/crawler.log` | deleted | **kept** |
| `/app/storage/{id}/_completion_marker.json` | deleted | **kept** |
| `/app/storage/{id}/_callback_payload.json` | deleted | **kept** |
| `/app/storage/{id}/_status_snapshot.json` | deleted | **kept** |
| `/app/storage/{id}/_exit_reason.json` | deleted | **kept** |
| `/app/storage/{id}/_update_report.json` | deleted | **kept** |
| `/app/storage/{id}/update_stats.json` | deleted | **kept** |
| `/app/storage/{id}/timing.jsonl` | deleted | **kept** |
| `/app/storage/{id}/timing-summary.json` | deleted | **kept** |
| `/app/storage/{id}/storage/datasets/000001.json` | deleted | deleted |
| `/app/storage/{id}/storage/request_queues/...` | deleted | deleted |
| `/app/storage/{id}/storage/key_value_stores/...` | deleted | deleted |
| `/app/storage/{id}/` (dir itself) | deleted | **kept** (still contains logs) |

### Restore behavior (unstash)

`tarfile.extractall(target_storage, filter="data")` overwrites the kept logs with the tar's copies (same content) and recreates the data subdirs. `os.makedirs(target_storage, exist_ok=True)` does not error on the pre-existing dir. Net effect: identical to a from-scratch restore.

## 6. Tests

### Helper unit tests

```python
def test_verify_bind_mount_raises_503_when_not_mount(cm_instance, tmp_path):
    ordinary = tmp_path / "ephemeral"
    ordinary.mkdir()
    with pytest.raises(HTTPException) as exc:
        cm_instance._verify_bind_mount(str(ordinary), "test")
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    assert exc.value.detail["path"] == str(ordinary)
    assert exc.value.detail["label"] == "test"
    assert "force-recreate" in exc.value.detail["ops_action"]


def test_verify_bind_mount_raises_503_when_path_missing(cm_instance, tmp_path):
    missing = tmp_path / "nonexistent"
    with pytest.raises(HTTPException) as exc:
        cm_instance._verify_bind_mount(str(missing), "test")
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"


def test_verify_bind_mount_passes_when_ismount_true(cm_instance, monkeypatch, tmp_path):
    real = tmp_path / "mounted"
    real.mkdir()
    monkeypatch.setattr(os.path, "ismount", lambda p: str(p) == str(real))
    cm_instance._verify_bind_mount(str(real), "test")  # must not raise
```

### Endpoint integration tests

```python
@pytest.mark.asyncio
async def test_stash_crawl_rejects_when_stash_dir_not_mount(
    cm_instance, base_job_info, mock_cache_service, monkeypatch
):
    """503 BIND_MOUNT_MISSING propagates from stash_crawl. Lock is released."""
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))
    monkeypatch.setattr(os.path, "ismount", lambda p: False)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    # Lock released by finally block (Lua eval invoked at least once)
    assert mock_cache_service.redis_client.eval.call_count >= 1


@pytest.mark.asyncio
async def test_unstash_crawl_rejects_when_dir_not_mount(
    cm_instance, stashed_job_info, mock_cache_service, monkeypatch
):
    """503 BIND_MOUNT_MISSING propagates from unstash_crawl. Lock released."""
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))
    monkeypatch.setattr(os.path, "ismount", lambda p: False)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    assert mock_cache_service.redis_client.eval.call_count >= 1
```

### Cleanup scope unit test

```python
@pytest.mark.asyncio
async def test_stash_keeps_logs_and_markers_on_cleanup(
    cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path
):
    """Stash must keep logs + markers and delete only data files,
    mirroring archive_crawl._cleanup_local_data convention."""
    stash_dir = tmp_path / "stash"
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    # 2 files that must be kept
    (storage / "crawler.log").write_text("log content")
    (storage / "_completion_marker.json").write_text('{"final_status":"finished"}')
    # 1 data file at root + 1 data file in subdir — both must be deleted
    (storage / "dataset.json").write_text('{"records":[1,2,3]}')
    sub = storage / "storage" / "datasets"
    sub.mkdir(parents=True)
    (sub / "000001.json").write_text("data")
    base_job_info["storage_path"] = str(storage)

    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(os.path, "ismount", lambda p: True)
    monkeypatch.setattr(
        cm_instance, "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    await cm_instance.stash_crawl(base_job_info)

    # Kept
    assert (storage / "crawler.log").exists()
    assert (storage / "_completion_marker.json").exists()
    # Deleted
    assert not (storage / "dataset.json").exists()
    assert not (sub / "000001.json").exists()
    # Storage dir itself kept (still contains logs)
    assert storage.exists()
```

**Test count delta:** `+6` (3 helper + 2 endpoint integration + 1 cleanup). Existing 22 stash tests remain unchanged.

## 7. Documentation updates (`docs/daemon_guide.md`)

Add a new appendix section near the end:

```markdown
## Troubleshooting: 503 `BIND_MOUNT_MISSING`

Indicates the running container was started BEFORE `docker-compose.yaml`
declared the stash bind-mounts (commit `14a02524`). Docker-compose only
applies new volume declarations at container creation, so a plain
`docker-compose up -d` after editing the file does not bridge them.

### Fix

```bash
# 1. Stop the service
docker-compose --profile crawling stop crawler-service

# 2. Recreate (rebuilds the container with the new mounts)
docker-compose --profile crawling up -d --force-recreate crawler-service

# 3. Verify mounts
docker inspect $(docker ps -qf name=crawler-service) \
  --format='{{range .Mounts}}{{.Destination}} ({{.Type}}){{println}}{{end}}' \
  | grep -E "stash|gcs-stash"
```

Expected output:

```
/app/stash (bind)
/app/gcs-stash-requests (bind)
/app/gcs-stash-downloads (bind)
```

If any line is missing, the recreate did not apply the latest compose file.
Verify you pulled the commit `14a02524` and re-run.

## Recovery: stash tars trapped in pre-fix ephemeral container

If `POST /stash/{id}` returned 202 before the recreate, the tar lives in the
container's overlay filesystem at `/app/stash/{id}.tar.gz` instead of on the
host bind-mount. To rescue before recreating (which would destroy the layer):

```bash
CONTAINER=$(docker ps -qf name=crawler-service | head -1)

# Confirm tar present
docker exec "$CONTAINER" ls -la /app/stash/

# Rescue
docker cp "$CONTAINER":/app/stash/{id}.tar.gz ./recovered_{id}.tar.gz

# After --force-recreate, copy back to the bind-mount source
cp ./recovered_{id}.tar.gz \
   ./apps-microservices/crawler-service/crawler_stash/{id}.tar.gz

# Upload daemon will pick it up within CHECK_INTERVAL (60s)
# Verify GCS arrival:
gcloud storage ls "gs://${GCS_BUCKET_NAME}/stash/{id}.tar.gz"
```

Redis `stashed_at` is already set from the original stash call, so
`POST /unstash/{id}` will work once the tar reaches GCS.
```

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `os.path.ismount` semantics differ across OSes (Linux vs Mac vs WSL) | Service runs only in Linux containers. Verified behavior: bind-mounts and named volumes both register. |
| Symlinks in compose volume declarations bypass `ismount` | This codebase doesn't use symlinked compose volumes. If added later, follow up with `os.path.realpath` before check. |
| Test mocking `os.path.ismount` could mask real behavior | One non-mocked test (`test_verify_bind_mount_raises_503_when_not_mount`) uses real `tmp_path` to confirm `ismount` returns False on ordinary dirs. |
| Cleanup keep-logs leaves stale logs across multiple stash cycles for the same crawl ID | A second stash on the same ID is blocked by `ALREADY_STASHED` (409). Cycle requires unstash first; unstash extracts fresh content over the kept logs. |
| Operator misses the runbook and runs another `docker-compose up -d` without `--force-recreate` | The 503 fires every endpoint call until fixed. Log payload includes `ops_action` text spelling the command. |

## 9. Out of scope (deferred)

- Same bind-mount check applied to `archive_crawl` (defense in depth, separate spec).
- Startup-time mount validation (warn-on-boot).
- `/health/bind-mounts` introspection endpoint.
- Optional `keep_logs=False` query parameter for stash (caller-controlled cleanup).
- Unstash idempotency improvements (LOW-1 from earlier audit).
- Service-side detection of tars trapped in old ephemeral layer (would need cross-container introspection; runbook step suffices).
