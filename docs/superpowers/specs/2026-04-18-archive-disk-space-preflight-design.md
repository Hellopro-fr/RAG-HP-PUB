# Design: Archive Pre-flight Disk Space Check + Diagnostics

**Date:** 2026-04-18
**Service:** crawler-service
**Status:** Approved

## Problem

Archiving a finished crawl via `POST /archive/{crawl_id}` fails with `OSError: [Errno 28] No space left on device` when the shared `/app/archives/` volume fills up. The failure manifests as a 500 response, leaves a partial staging file behind, and provides no visibility into why the disk was full (burst pressure, slow daemon, stuck daemon, or a single oversized archive — all plausible).

The previous fix (archive staging subdirectory, 2026-04-18) cleans up partial files correctly via a `finally` block but does nothing to prevent the disk from filling up in the first place.

## Decision

Add a **diagnostic-first** defense: measure the source directory size, check free space before calling `shutil.make_archive`, and reject with a clear **503** if insufficient. Always log disk state (free bytes, file count, oldest file age) on every archive attempt so we can see what's really happening in production.

This intentionally does **not** solve the producer/consumer throughput mismatch that causes the disk to fill. It makes the failure mode clean and observable, so we can decide with evidence whether further protection (concurrent-archive limit, stale cleanup, streaming upload, etc.) is needed.

## Design

### Threshold Calculation

For each archive request:

```
required_bytes = source_dir_size * 1.5
required_bytes = max(required_bytes, 1 GB)  // floor

state = disk_usage of /app/archives/
if state.free_bytes < required_bytes:
    reject with 503
```

Rationale:
- `1.5×` source size accounts for gzip overhead variability (rarely expands but we need headroom) and the brief moment where staging + final both exist simultaneously before `os.rename`.
- `1 GB` floor protects against measurement errors (e.g., `os.walk` returning 0 on a broken filesystem).

### Helper Functions

**`_estimate_archive_required_bytes(job_storage_path: str) -> int`**

Walks `job_storage_path` with `os.walk`, sums file sizes. Returns `int(total * 1.5)`. Floor applied by caller.

On error (permission, missing dir, broken symlink), returns the floor (1 GB) and logs a warning — fail-open.

**`_get_archives_disk_state(archives_dir: str) -> dict`**

Returns:

```python
{
    "free_bytes": int,              # shutil.disk_usage(archives_dir).free
    "total_bytes": int,
    "used_pct": float,              # 100 * (total - free) / total
    "file_count": int,              # *.tar.gz in archives_dir (excluding .staging/)
    "oldest_file_age_seconds": int | None,  # age of oldest *.tar.gz, None if empty
}
```

Used both for the pre-flight decision and for logging. On error, returns a degraded dict with `None` values and logs a warning — fail-open.

### Integration in `archive_crawl`

Insert immediately after the Redis lock is acquired (around line 1339, inside the `try:` block that wraps `_create_archive`) but before the GCS fallback check and before calling `_create_archive`.

Pseudocode:

```python
# Log baseline disk state for every archive attempt
try:
    baseline_state = _get_archives_disk_state(archives_dir)
    logger.info(f"Archive disk state for '{crawl_id}': {baseline_state}")
except Exception as e:
    logger.warning(f"Could not collect disk state for '{crawl_id}': {e}")

# Pre-flight check (only if measurement succeeded)
required_bytes = _estimate_archive_required_bytes(job_storage_path)
required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

state = _get_archives_disk_state(archives_dir)
if state.get("free_bytes") is not None and state["free_bytes"] < required_bytes:
    logger.warning(
        f"Rejecting archive '{crawl_id}': insufficient disk space. "
        f"Required: {required_bytes} bytes, Available: {state['free_bytes']} bytes. "
        f"Disk state: {state}"
    )
    raise HTTPException(
        status_code=503,
        detail={
            "error_code": "INSUFFICIENT_DISK_SPACE",
            "required_bytes": required_bytes,
            "available_bytes": state["free_bytes"],
            "disk_state": state,
        },
    )
```

### Failure Path Enrichment

In the existing `except Exception` block around `_create_archive` (currently re-raises as 500), add a second disk state log **after** the failure. This captures state at both pre-check and post-failure, so cases where the disk fills between the two (e.g., concurrent archives on other replicas) are visible in logs:

```python
except Exception as e:
    logger.error(f"Failed to archive crawl '{crawl_id}': {e}", exc_info=True)
    try:
        post_failure_state = _get_archives_disk_state(archives_dir)
        logger.error(f"Archive disk state at failure for '{crawl_id}': {post_failure_state}")
    except Exception:
        pass
    raise HTTPException(status_code=500, detail=f"Archiving failed: {str(e)}")
```

### Fail-Open Policy

If the helpers themselves raise (permission errors, filesystem corruption, etc.):
- Log a warning
- Skip the pre-flight check (set `free_bytes=None`, which bypasses the `if` branch)
- Allow `_create_archive` to attempt anyway

Rationale: a broken measurement tool must never block archiving. The existing `finally` block in `_create_archive` still cleans up partial files if the archive fails for disk-space reasons.

### What Stays Unchanged

- `_create_archive` staging subdirectory logic (from previous fix)
- Upload daemon (`tools/upload_daemon.sh`)
- Redis lock pattern (`archive_lock:{crawl_id}`)
- Idempotency check (local `.tar.gz` exists → skip)
- GCS fallback (remote `.tar.gz` exists → skip)
- `_cleanup_local_data`
- `_mark_as_archived`
- Python orchestrator → Node.js contract

### 503 Response Contract

The 503 response body carries:

```json
{
  "detail": {
    "error_code": "INSUFFICIENT_DISK_SPACE",
    "required_bytes": 524288000,
    "available_bytes": 104857600,
    "disk_state": {
      "free_bytes": 104857600,
      "total_bytes": 21474836480,
      "used_pct": 99.51,
      "file_count": 47,
      "oldest_file_age_seconds": 7200
    }
  }
}
```

The caller can:
- See how much headroom was needed vs. available
- See that 47 files are backlogged — suggests daemon health issue
- See the oldest file is 2 hours old — confirms the daemon is struggling or stuck
- Retry after a backoff (the daemon is always draining)

### Files to Modify

| File | Change |
|------|--------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Add 2 helpers (`_estimate_archive_required_bytes`, `_get_archives_disk_state`) + pre-flight check in `archive_crawl` + failure-path disk state log |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | Unit tests: helpers behavior, fail-open on errors, 503 rejection when free_bytes < required |
| `apps-microservices/crawler-service/CLAUDE.md` | Brief note on the pre-flight behavior, 503 response, and fail-open policy |

### Edge Cases

| Case | Behavior |
|------|----------|
| Source dir missing | `os.walk` returns empty; required falls to 1 GB floor; proceed |
| Archives dir missing | `_create_archive`'s `os.makedirs` handles; `shutil.disk_usage` walks parent for usable stats |
| Very small crawl (< 1 GB source) | Floor of 1 GB protects against measurement errors |
| Disk fills between pre-check and `make_archive` (concurrent on other replica) | `make_archive` fails with OSError; `_create_archive`'s `finally` cleans up staging file; 500 response logs post-failure disk state |
| Permissions error on `shutil.disk_usage` | Fail-open: warning logged, archive attempt proceeds |
| Empty archives dir | `oldest_file_age_seconds` returns `None`; not treated as an error |

## Alternatives Considered

### B: Layered protection up front
Pre-flight check + Redis-based concurrent-archive limiter + stale-file cleanup + metrics, all implemented together.

**Rejected:** the user stated the root cause is unclear. Adding speculative protection without evidence of where the pressure comes from is over-engineering (YAGNI). Direction A (diagnostic first) delivers a clean failure mode AND the telemetry to decide what (if anything) else to add.

### C: Operational only
Add Grafana alerts, increase volume size, no code change.

**Rejected:** the current 500 response corrupts state mid-archive (partial files, inconsistent Redis status). A code-level fail-fast is needed regardless of volume sizing.

### Percentage-based threshold
Reject if free < 10% of volume.

**Rejected:** percentage thresholds ignore the size of the archive being created. A 4 GB crawl on a 100 GB volume with 5 GB free would be rejected by a 10% rule but succeed with room to spare. The source-size-aware formula handles both small and large crawls correctly.

### Fixed absolute threshold
Reject if free < 5 GB.

**Rejected:** same issue — no relation to the actual archive size. Either too conservative (rejects small crawls needlessly) or too permissive (allows a 10 GB crawl to fail).

## Future Extensions

Once telemetry from this change reveals the actual pattern in production, we can add (only if the data justifies it):

1. **Concurrent-archive limiter** — if logs show multiple replicas spike simultaneously, add a Redis counter for in-progress archives.
2. **Stale-file cleanup** — if logs show oldest files staying > 1 hour, investigate daemon health; a cleanup policy for GCS-already-uploaded files could follow.
3. **Direct-to-GCS streaming** — if the buffer pattern is fundamentally incompatible with sustained throughput, eliminate the local buffer entirely.
4. **Prometheus metrics** — if structured log analysis becomes unwieldy, export `archives_disk_free_bytes`, `archives_file_count`, `archives_oldest_age_seconds` as metrics.

Each of these is its own future brainstorming session.
