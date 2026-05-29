# Stash / Unstash to GCS — Free Disk Investigation Workflow

**Author:** Rindra ANDRIANJANAKA
**Date:** 2026-05-19
**Service:** `apps-microservices/crawler-service`
**Status:** Design approved — pending implementation plan

---

## 1. Context

The crawler-service accumulates stale data on disk from crawls that failed (status `failed`) or were stopped (status `stopped`) and still require manual investigation before deletion. These crawls hold disk space indefinitely because:

- The existing `POST /archive/{crawl_id}` flow is meant for **completed crawls whose data is no longer needed locally** (delivered to GCS, local deleted) — it is not used for failed/stopped crawls under investigation.
- The `scheduled_archive_cleanup` task prunes only `/app/storage/archives/` (the cached `.tar.gz` results), not the raw crawl directories under `/app/storage/datasets/...`.
- Operators cannot safely delete raw crawl directories until investigation completes, which can take days or weeks.

This design introduces a new **stash / unstash** workflow that mirrors the archive flow at the infrastructure level (tar.gz to GCS via the existing daemons) but with different semantics:

- **Purpose:** temporarily free local disk space for crawls under investigation, with the ability to retrieve them later for analysis.
- **GCS layout:** a new prefix `gs://{bucket}/stash/` alongside the existing `gs://{bucket}/crawls/`.
- **Status modeling:** **no new status enum**. A single new field `job_data["stashed_at"]` (ISO 8601 timestamp, `null` when not stashed) acts as an orthogonal axis to the existing terminal statuses.

## 2. Scope

### In scope

- New endpoint `POST /stash/{crawl_id}` — bundles a crawl's storage dir into `.tar.gz`, uploads to GCS under `stash/`, deletes local data, sets `stashed_at`.
- New endpoint `POST /unstash/{crawl_id}` — downloads from GCS, extracts to original storage path, deletes GCS object, clears `stashed_at`.
- Parametrization of `tools/upload_daemon.sh` and `tools/download_daemon.sh` via env vars to support multiple GCS prefixes and watch directories.
- New systemd units for stash-flow daemons.
- New docker-compose volume mounts for stash staging and download directories.
- Two-phase commit protocol for safe GCS deletion on unstash (avoids data loss on extract failure).
- Disk-space pre-flight checks on both endpoints (mirror existing archive pattern).
- Redis locks (`stash_lock:{id}` and `unstash_lock:{id}`) with ownership-safe release (mirror `reconcile_leader_lock` pattern).
- Unit tests + integration tests + manual smoke test plan.
- Documentation updates across CLAUDE.md files, README, and daemon guide.

### Out of scope (deferred to V2)

- Auto-prune GCS stash older than N days (manual cleanup only).
- Batch stash endpoint with filters (one ID at a time).
- Direct transition between `crawls/` and `stash/` prefixes for `archived` crawls (must unarchive then re-stash through normal flow).
- Webhook notifications on stash/unstash completion.
- Stash from active states (`running`, `restarting_oom`, `stopping` blocked with 409).
- Stash compression tuning (uses same gzip default as archive).
- Cross-replica coordination for unstash (single replica handles via Redis lock — acceptable).

## 3. Architecture

### High-level flow

```
                              POST /stash/{id}
                                    ↓
                       crawler_service (Python)
                       — check status ∈ {failed, stopped, finished} + stashed_at IS NULL
                       — acquire Redis lock stash_lock:{id} (SET NX, TTL 600s)
                       — pre-flight disk space measurement (mirror archive logic)
                       — tar.gz → /app/stash/.staging/{id}.tar.gz
                       — integrity check + atomic move → /app/stash/{id}.tar.gz
                       — set job_data["stashed_at"] = ISO timestamp (Redis HSET)
                       — delete local crawl storage dir
                       — release Redis lock (ownership-safe DEL)
                                    ↓
                        stash_upload_daemon (host, systemd)
                        — scan /app/stash/*.tar.gz (maxdepth 1, ignore .staging/)
                        — gcloud storage cp → gs://{bucket}/stash/{id}.tar.gz
                        — delete local tar.gz on success
                        — retry 3x → /app/stash/dead_letter/

                              POST /unstash/{id}
                                    ↓
                       crawler_service (Python)
                       — check stashed_at IS NOT NULL
                       — acquire Redis lock unstash_lock:{id} (SET NX, TTL 600s)
                       — pre-flight disk space (extracted size ≈ tar × 2 + safety floor 500MB)
                       — write /app/gcs-stash-requests/{id}.request
                                    ↓
                        stash_download_daemon (host, systemd)
                        — scan *.request (poll 5s)
                        — gcloud storage cp gs://{bucket}/stash/{id}.tar.gz → /app/gcs-stash-results/{id}.tar.gz
                        — write {id}.done marker
                                    ↓
                       crawler_service (Python)
                       — poll {id}.done (existing pattern, bounded by UNSTASH_TIMEOUT_SECONDS)
                       — extract tar.gz → original storage path
                       — write {id}.unstash-confirmed marker (signals extract success)
                                    ↓
                        stash_download_daemon
                        — scan *.unstash-confirmed
                        — gcloud storage rm gs://{bucket}/stash/{id}.tar.gz
                        — write {id}.unstash-cleanup-done marker
                                    ↓
                       crawler_service (Python)
                       — poll {id}.unstash-cleanup-done
                       — clear job_data["stashed_at"] (Redis HDEL or HSET null)
                       — cleanup .tar.gz + .done + .request + .unstash-confirmed + .unstash-cleanup-done
                       — release Redis lock
                       — return 200 to caller
```

### Components

| Component | Role |
|---|---|
| `app/router/crawler.py` | Defines `POST /stash/{id}` and `POST /unstash/{id}` route handlers |
| `app/core/crawler_manager.py` | Adds `stash_crawl()` and `unstash_crawl()` methods; reuses existing tar/extract/disk-check helpers from archive flow |
| `app/core/config.py` | Adds `STASH_SHARED_PATH`, `STASH_DOWNLOAD_REQUESTS_PATH`, `STASH_DOWNLOAD_RESULTS_PATH`, `STASH_LOCK_TTL_SECONDS`, `UNSTASH_LOCK_TTL_SECONDS`, `UNSTASH_TIMEOUT_SECONDS` |
| `app/schemas/crawler.py` | Adds response models `StashResponse`, `UnstashResponse` |
| `tools/upload_daemon.sh` | Adds optional env vars `UPLOAD_WATCH_DIR`, `UPLOAD_GCS_PREFIX`, `UPLOAD_DEAD_LETTER_SUBDIR` (defaults preserve current behavior) |
| `tools/download_daemon.sh` | Adds optional env vars `DOWNLOAD_GCS_PREFIX`, `DELETE_AFTER_DOWNLOAD` (defaults preserve current behavior); adds new poll loop for `*.unstash-confirmed` markers when `DELETE_AFTER_DOWNLOAD=true` |
| `apps-microservices/crawler-service/docker-compose.yaml` | Adds three new volume mounts for stash staging and download dirs |
| Systemd units | 4 total: `crawler-upload.service`, `crawler-upload-stash.service`, `crawler-download.service`, `crawler-download-stash.service` |

## 4. Data Model

### Redis hash extension

Existing keys (no change):

```
crawl_jobs:running_count       → integer counter
crawl_job:{crawl_id}           → hash with fields: id, status, start_time, last_heartbeat, ...
```

New field on `crawl_job:{crawl_id}` hash:

```
stashed_at                     → ISO 8601 UTC timestamp string (e.g., "2026-05-19T14:32:08Z")
                                 absent or empty when crawl is not stashed
```

### Redis locks

| Key | TTL | Purpose |
|---|---|---|
| `stash_lock:{crawl_id}` | `STASH_LOCK_TTL_SECONDS` (default 600s) | Prevents concurrent stash on same id |
| `unstash_lock:{crawl_id}` | `UNSTASH_LOCK_TTL_SECONDS` (default 600s) | Prevents concurrent unstash on same id |

Both locks use **ownership-safe release**: the `finally` block deletes the lock only if the current Redis value equals this replica's `replica_id`. This mirrors the `reconcile_leader_lock` pattern and prevents a slow operation from clobbering a new acquirer's lock after TTL expiry.

### State transition matrix

| Current state | `POST /stash` | `POST /unstash` |
|---|---|---|
| `running` / `restarting_oom` / `stopping` | 409 `CRAWL_IS_ACTIVE` | 409 `NOT_STASHED` |
| `archived` (no `stashed_at`) | 409 `ALREADY_ARCHIVED` | 409 `NOT_STASHED` |
| terminal (`failed`/`stopped`/`finished`) + `stashed_at` IS NULL | 200 → proceed | 409 `NOT_STASHED` |
| terminal + `stashed_at` IS NOT NULL | 409 `ALREADY_STASHED` | 200 → proceed |
| `stash_lock` held | 409 `OPERATION_IN_PROGRESS` | 409 `OPERATION_IN_PROGRESS` |
| `unstash_lock` held | 409 `OPERATION_IN_PROGRESS` | 409 `OPERATION_IN_PROGRESS` |

## 5. API Endpoints

### `POST /stash/{crawl_id}`

**Behavior:** Asynchronous tar creation on the request thread, then daemon-driven GCS upload. The response returns 202 once the tar is safely in `/app/stash/` and Redis has been updated.

**Pre-conditions:**
- `crawl_id` exists in Redis
- Status ∈ {`failed`, `stopped`, `finished`}
- `stashed_at` IS NULL
- No `stash_lock:{id}` held by another replica

**Pre-flight disk space check** (mirror archive flow):
- Source dir size measured via `os.walk` × 1.5 + 1GB floor for safety margin
- `shutil.disk_usage('/app/stash')` checked
- Fail-open: if measurement helpers raise (permissions, FS errors), check skipped and stash proceeds

**Responses:**

| HTTP | Body | When |
|---|---|---|
| 202 Accepted | `{"crawl_id": "...", "status": "stashing", "stash_path": "gs://{bucket}/stash/{id}.tar.gz", "stashed_at": "2026-05-19T14:32:08Z"}` | Tar created in `/app/stash/`, Redis flag set, daemon upload pending |
| 409 Conflict | `{"detail": {"error_code": "CRAWL_IS_ACTIVE", "current_status": "running"}}` | Status not terminal |
| 409 Conflict | `{"detail": {"error_code": "ALREADY_STASHED", "stashed_at": "..."}}` | `stashed_at` already populated |
| 409 Conflict | `{"detail": {"error_code": "ALREADY_ARCHIVED"}}` | Status is `archived` (data lives under `crawls/` prefix instead) |
| 409 Conflict | `{"detail": {"error_code": "OPERATION_IN_PROGRESS"}}` | `stash_lock` or `unstash_lock` already held |
| 503 Service Unavailable | `{"detail": {"error_code": "INSUFFICIENT_DISK_SPACE", "required_bytes": ..., "available_bytes": ..., "disk_state": {...}}}` | Pre-flight check failed (same payload shape as archive endpoint) |
| 404 Not Found | `{"detail": "Crawl not found"}` | Unknown id |
| 500 Internal Server Error | Generic | Unexpected exception |

### `POST /unstash/{crawl_id}`

**Behavior:** Synchronous wait on daemon download + service-side extract + two-phase GCS delete. Mirrors the existing `_restore_archived_crawl` pattern. Bounded by `UNSTASH_TIMEOUT_SECONDS` (default 300s).

**Pre-conditions:**
- `crawl_id` exists in Redis
- `stashed_at` IS NOT NULL
- No `unstash_lock:{id}` held
- Pre-flight disk space: extracted size ≈ tar × 2 + 500MB floor

**Responses:**

| HTTP | Body | When |
|---|---|---|
| 200 OK | `{"crawl_id": "...", "status": "unstashed", "restored_to": "/app/storage/datasets/...", "elapsed_seconds": 42.3}` | Extract succeeded, GCS object deleted, `stashed_at` cleared |
| 409 Conflict | `{"detail": {"error_code": "NOT_STASHED"}}` | `stashed_at` is null or absent |
| 409 Conflict | `{"detail": {"error_code": "OPERATION_IN_PROGRESS"}}` | Lock held |
| 503 Service Unavailable | `{"detail": {"error_code": "INSUFFICIENT_DISK_SPACE", ...}}` | Pre-flight failed |
| 504 Gateway Timeout | `{"detail": {"error_code": "UNSTASH_TIMEOUT", "elapsed_seconds": 300}}` | Daemon didn't write `.done` in time |
| 502 Bad Gateway | `{"detail": {"error_code": "GCS_DOWNLOAD_FAILED", "marker_content": "..."}}` | Daemon wrote `.error` marker |
| 502 Bad Gateway | `{"detail": {"error_code": "EXTRACT_FAILED", "exception": "..."}}` | Tar extract raised; `stashed_at` preserved, no GCS delete triggered |
| 404 Not Found | `{"detail": "Crawl not found"}` | Unknown id |
| 500 Internal Server Error | Generic | Unexpected exception |

### Observability

Both endpoints emit:
- Structured logs with baseline disk state on entry, second disk state on failure (mirror archive pattern)
- Prometheus counters `stash_total{result=success|failure}` and `unstash_total{result=success|failure|timeout}`
- Prometheus histogram `unstash_duration_seconds` (request → response)

## 6. Daemon Changes

### `tools/upload_daemon.sh` parametrization

Three new optional env vars (defaults preserve current behavior):

| Env var | Default | Effect |
|---|---|---|
| `UPLOAD_WATCH_DIR` | `apps-microservices/crawler-service/crawler_archives` | Dir scanned for `.tar.gz` |
| `UPLOAD_GCS_PREFIX` | `crawls` | Path component under `gs://$BUCKET/` |
| `UPLOAD_DEAD_LETTER_SUBDIR` | `dead_letter` | Subdir name for retry-exhausted files |

Critical line change (replace hardcoded `crawls/` in URL build):

```bash
target_url="gs://$BUCKET_NAME/$UPLOAD_GCS_PREFIX/$filename"
```

### `tools/download_daemon.sh` parametrization

Two new optional env vars + new poll branch:

| Env var | Default | Effect |
|---|---|---|
| `DOWNLOAD_REQUESTS_PATH` | `…/crawler_download_requests` | (already exists) Dir scanned for `*.request` |
| `DOWNLOAD_RESULTS_PATH` | `…/crawler_download_results` | (already exists) Dir for downloaded archives + markers |
| `DOWNLOAD_GCS_PREFIX` | `crawls` | Source path under `gs://$BUCKET/` |
| `DELETE_AFTER_DOWNLOAD` | `false` | If `true`, daemon also scans `*.unstash-confirmed` markers and deletes the corresponding GCS object |

Critical changes:

```bash
# Source URL uses prefix env var
source_url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"

# Two-phase GCS delete: only deletes after service confirms extract success
if [ "$DELETE_AFTER_DOWNLOAD" = "true" ]; then
    find "$RESULTS_DIR" -maxdepth 1 -name "*.unstash-confirmed" -print0 | while IFS= read -r -d '' confirm_file; do
        crawl_id=$(basename "$confirm_file" .unstash-confirmed)
        source_url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"
        cleanup_done="$RESULTS_DIR/$crawl_id.unstash-cleanup-done"

        echo "[$(date)] Extract confirmed for $crawl_id, deleting GCS source..."
        if gcloud storage rm "$source_url"; then
            echo "GCS source deleted: $source_url"
            touch "$cleanup_done"
        else
            echo "WARNING: Failed to delete GCS stash $source_url — marker preserved, manual cleanup needed"
            # Do NOT write cleanup_done — service will time out and operator can investigate
        fi
        rm "$confirm_file"
    done
fi
```

**Failed GCS delete = log warning, do NOT fail the unstash.** Data is already restored locally and the service has extracted it. An orphan GCS object becomes a manual cleanup task. This trade-off favors caller success over GCS consistency, which is acceptable because `stashed_at` (the source of truth for stash state) is cleared based on `.unstash-cleanup-done` arrival — without that marker, the service times out and operator can investigate.

### Volume mounts (docker-compose.yaml)

```yaml
crawler-service:
  volumes:
    # Existing
    - ./crawler_archives:/app/archives
    - ./crawler_download_requests:/app/gcs-requests
    - ./crawler_download_results:/app/gcs-downloads
    # New for stash flow
    - ./crawler_stash:/app/stash
    - ./crawler_stash_download_requests:/app/gcs-stash-requests
    - ./crawler_stash_download_results:/app/gcs-stash-downloads
```

### Config (`app/core/config.py`)

```python
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... existing fields ...

    STASH_SHARED_PATH: Path = Path("/app/stash")
    STASH_DOWNLOAD_REQUESTS_PATH: Path = Path("/app/gcs-stash-requests")
    STASH_DOWNLOAD_RESULTS_PATH: Path = Path("/app/gcs-stash-downloads")

    STASH_LOCK_TTL_SECONDS: int = 600
    UNSTASH_LOCK_TTL_SECONDS: int = 600
    UNSTASH_TIMEOUT_SECONDS: int = 300
    UNSTASH_CLEANUP_GRACE_SECONDS: int = 30  # Section 7 edge case 5: GCS-rm fallback window
```

### Systemd units

Four units total. The two existing units (`crawler-upload.service`, `crawler-download.service`) remain unchanged because env var defaults preserve current behavior.

`~/.config/systemd/user/crawler-upload-stash.service`:

```ini
[Unit]
Description=Crawler Stash Upload Daemon

[Service]
Environment="UPLOAD_WATCH_DIR=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash"
Environment="UPLOAD_GCS_PREFIX=stash"
ExecStart=%h/workspaces/RAG-HP-PUB/tools/upload_daemon.sh
Restart=always
RestartSec=10
ExecStartPre=/bin/mkdir -p %h/workspaces/RAG-HP-PUB/logs
StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon_stash.log
StandardError=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon_stash.log

[Install]
WantedBy=default.target
```

`~/.config/systemd/user/crawler-download-stash.service`:

```ini
[Unit]
Description=Crawler Stash Download Daemon

[Service]
Environment="DOWNLOAD_REQUESTS_PATH=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash_download_requests"
Environment="DOWNLOAD_RESULTS_PATH=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash_download_results"
Environment="DOWNLOAD_GCS_PREFIX=stash"
Environment="DELETE_AFTER_DOWNLOAD=true"
ExecStart=%h/workspaces/RAG-HP-PUB/tools/download_daemon.sh
Restart=always
RestartSec=10
ExecStartPre=/bin/mkdir -p %h/workspaces/RAG-HP-PUB/logs
StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/download_daemon_stash.log
StandardError=append:%h/workspaces/RAG-HP-PUB/logs/download_daemon_stash.log

[Install]
WantedBy=default.target
```

## 7. Error Handling & Edge Cases

### 1. Tar creation failure mid-stash

- Tar partial in `/app/stash/.staging/` cleaned via `finally` block (mirror archive flow)
- Redis `stashed_at` NOT set (only set after atomic move succeeds)
- Lock released
- Local crawl dir NOT deleted (delete only after Redis flag set)
- Caller may safely retry

### 2. Upload daemon crash post-tar

- Tar in `/app/stash/{id}.tar.gz` waiting (visible to daemon scan)
- Redis `stashed_at` already SET (data effectively offloaded — local crawl dir deleted)
- Daemon restart picks up file, uploads, deletes local tar
- **Risk window:** local dir deleted + GCS not yet uploaded. Daemon crash over extended period means data lives only in `/app/stash/{id}.tar.gz` until daemon recovers. Mitigation: `/app/stash/` is a persisted Docker volume so service restarts do not lose it.

### 3. Download daemon crash mid-unstash

- `.request` written, no `.done` after `UNSTASH_TIMEOUT_SECONDS` → 504 timeout to caller
- Caller retries → new `.request` overwrites (idempotent at FS level)
- Redis `stashed_at` still SET (correct, since data is still in GCS)
- `unstash_lock` TTL expires → next call proceeds

### 4. Unstash: extract fails post-download

- `.done` present, tar.gz downloaded, but extract throws (disk full mid-extract, corrupt tar)
- Service catches exception → 502 response with `EXTRACT_FAILED`
- **Key invariant:** service does NOT write `.unstash-confirmed`, so daemon does NOT delete GCS object
- `stashed_at` preserved → operator can retry unstash later
- Local partial extract cleaned via `try/finally`

### 5. GCS delete fails post-extract

- Service wrote `.unstash-confirmed`, daemon attempted `gcloud storage rm`, network/permission error
- Daemon logs warning, does NOT write `.unstash-cleanup-done`
- Service times out polling `.unstash-cleanup-done` → 504 with `UNSTASH_CLEANUP_TIMEOUT`
- `stashed_at` preserved (correct — GCS still has the data)
- Local data restored successfully (caller can investigate even though endpoint returned non-200)
- Manual cleanup workflow: operator confirms restoration via filesystem, then either retries unstash (which now finds GCS empty? no, GCS still has it) or manually deletes GCS object + clears Redis flag

**Refinement for edge case 5:** if the daemon's GCS-rm fails, the service should still complete the unstash from the caller's perspective (data is restored). Two options:

(a) Service times out → 504 → operator manually fixes. *Data restored but Redis says still stashed.*
(b) Service waits short for `.unstash-cleanup-done`, falls back to 200 with a warning field. *Redis cleared, GCS orphan flagged for cleanup.*

**Decision:** option (b). After polling `.unstash-cleanup-done` for `UNSTASH_CLEANUP_GRACE_SECONDS` (default 30s), if absent, return 200 with `gcs_cleanup_status: "deferred"` field and emit Prometheus counter `unstash_gcs_orphan_total` (scoped out — see Amendment 2026-05-19). Caller gets success, ops dashboard surfaces orphans.

### 6. Concurrent stash + unstash race

- Same `crawl_id` cannot logically be in both states: stash requires `stashed_at IS NULL`, unstash requires `stashed_at IS NOT NULL`. Mutually exclusive.
- If two replicas race to stash the same id, the lock (`stash_lock:{id}` SET NX) ensures only one proceeds; the other returns 409 `OPERATION_IN_PROGRESS`.

### 7. Reconciliation interaction

`reconcile_jobs` scans for stale heartbeats in `running`-style statuses. `stashed_at` is orthogonal — stale detection is unaffected. Stashed crawls are in terminal status (`failed`/`stopped`/`finished`), which reconciliation already ignores.

### 8. Cleanup interaction

`scheduled_archive_cleanup` cleans `/app/storage/archives/` (cached results) older than 24h. Extend this task to also clean:
- `/app/gcs-stash-downloads/` (`.tar.gz` + `.done` + `.error` artifacts from unstash flow) — same 24h policy
- `/app/gcs-stash-requests/` (stale `.request` files not consumed by daemon) — same 24h policy

Do NOT clean `/app/stash/` — those are pending uploads owned by the daemon.

### 9. Dead-letter for stash

Upload daemon retries 3x → moves to `/app/stash/dead_letter/`. Operator workflow same as archive dead-letter (manual investigation + retry via `gcloud storage cp`).

### 10. Restart resilience

- **Service restart mid-stash (after Redis flag set):** tar.gz on disk + Redis flag set → daemon completes upload independently. Acceptable.
- **Service restart mid-stash (before Redis flag set):** tar.gz in `.staging/` may be partial → orphan. On next startup, sweep `.staging/` of stash dir (mirror archive recovery if it exists, else implement). Lock auto-expires.
- **Service restart mid-unstash:** `.request` on disk → daemon completes download. Client gets connection drop. Client retries → idempotent: if `.done` already present, service extracts immediately; if `.unstash-confirmed` already present, daemon does its cleanup; flow completes.

## 8. Testing Strategy

### Unit tests (`tests/test_crawler_manager_stash.py`)

- `test_stash_blocks_active_status` — 409 for `running`/`restarting_oom`/`stopping`
- `test_stash_blocks_already_archived` — 409 `ALREADY_ARCHIVED`
- `test_stash_blocks_already_stashed` — 409 `ALREADY_STASHED`
- `test_stash_blocks_lock_held` — mock Redis `SET NX` → False → 409
- `test_stash_disk_space_pre_flight_fails` — mock `disk_usage` → 503 `INSUFFICIENT_DISK_SPACE`
- `test_stash_success_sets_timestamp_and_deletes_local` — happy path: tar in `.staging`, atomic move, Redis flag set, local dir deleted
- `test_stash_tar_failure_cleans_staging` — mock tar exception → `.staging/` cleaned, Redis unchanged, lock released
- `test_stash_ownership_safe_lock_release` — mock Redis value mismatch → DEL skipped
- `test_unstash_blocks_not_stashed` — 409 `NOT_STASHED`
- `test_unstash_writes_request_marker` — verifies marker file path and content
- `test_unstash_success_extracts_and_clears_flag` — mock `.done` arrival, extract, `.unstash-confirmed` written, `.unstash-cleanup-done` polled, flag cleared, lock released
- `test_unstash_timeout_when_no_done_marker` — 504 `UNSTASH_TIMEOUT`
- `test_unstash_error_marker_returns_502` — daemon writes `.error` → service surfaces as 502
- `test_unstash_extract_failure_preserves_stash` — mock `tarfile.extractall` raises → 502 `EXTRACT_FAILED`, `stashed_at` preserved, no `.unstash-confirmed` written
- `test_unstash_gcs_cleanup_deferred_returns_200_with_warning` — mock no `.unstash-cleanup-done` within grace → 200 with `gcs_cleanup_status: deferred`

### Integration tests (Bash + docker-compose)

`tests/integration/test_stash_unstash_e2e.sh`:
- Spins up service + 2 daemons (archive + stash) against a test GCS bucket
- Creates a test crawl with synthetic data on disk
- `POST /stash/{id}` → polls until daemon uploads, verifies `gcloud storage ls gs://test-bucket/stash/{id}.tar.gz` and local dir gone
- `POST /unstash/{id}` → verifies local dir restored, GCS object gone, Redis flag cleared
- Asserts elapsed time within reasonable bound

`tests/integration/test_stash_dead_letter.sh`:
- Points daemon at invalid bucket → verifies dead-letter triggered after 3 retries

### Daemon tests (`tests/test_daemon_parametrization.sh`)

- Verify default env vars produce existing behavior (archives → `crawls/`)
- Verify `UPLOAD_GCS_PREFIX=stash` + `UPLOAD_WATCH_DIR=...` routes correctly
- Verify `DELETE_AFTER_DOWNLOAD=true` triggers `gcloud storage rm` only on `.unstash-confirmed` marker (NOT on `.done` alone)
- Verify `.unstash-cleanup-done` written on success path

### Manual smoke test plan

1. Spin up service + 4 daemons (archive + stash, upload + download)
2. Run a crawl that ends in `failed` status, verify data on disk under `/app/storage/datasets/`
3. `POST /stash/{id}` → 202 response, poll until `gcloud storage ls` shows GCS object, verify local dir gone, Redis `stashed_at` populated
4. `POST /unstash/{id}` → 200 response, verify local dir restored, GCS object gone, Redis flag cleared
5. Re-stash same id → verify full cycle works again
6. Concurrent stash on 2 different ids → verify both succeed in parallel
7. Stash + simulate daemon crash post-upload → verify recovery on daemon restart
8. Unstash + simulate extract failure (chmod restored dir to readonly) → verify 502 + `stashed_at` preserved + no GCS delete

## 9. Documentation Updates

### `apps-microservices/crawler-service/CLAUDE.md`

Add:
- `POST /stash/{id}` and `POST /unstash/{id}` to API Endpoints table
- New section "Stash — Free Disk Investigation Workflow" describing the `stashed_at` flag, two-phase commit protocol, and lock semantics
- Update "Automatic Cleanup" section to mention new directories included in the background task

### `apps-microservices/crawler-service/README.md`

Add stash endpoints to the Core/Administrative section with example payloads and curl invocations.

### `docs/daemon_guide.md`

Add:
- Stash daemon variants under "Upload Daemon" and "Download Daemon" sections
- Shared Directories table: 3 new rows (`/app/stash`, `/app/gcs-stash-requests`, `/app/gcs-stash-downloads`)
- Systemd unit examples for `crawler-upload-stash.service` and `crawler-download-stash.service`
- Note about `DELETE_AFTER_DOWNLOAD=true` and the two-phase commit semantic
- Updated troubleshooting section for orphaned GCS stash objects

### `tools/CLAUDE.md`

Update env var list to include new optional vars (`UPLOAD_WATCH_DIR`, `UPLOAD_GCS_PREFIX`, `DOWNLOAD_GCS_PREFIX`, `DELETE_AFTER_DOWNLOAD`) with defaults and example values.

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Daemon parametrization regresses existing archive flow | Env var defaults preserve current behavior; integration tests verify default-env produces identical output |
| Two-phase commit adds 5-second daemon poll latency to unstash | Acceptable for ops workflow (investigation is non-time-critical); poll interval inherited from existing download daemon |
| Orphan GCS objects accumulate when extract fails or GCS-rm fails | Prometheus counter `unstash_gcs_orphan_total` (scoped out — see Amendment 2026-05-19) + warning logs surface to ops; manual cleanup via `gcloud storage rm` |
| Disk fills during unstash extract | Pre-flight check rejects with 503 before extract attempt |
| Local stash tar.gz lost during service restart before upload | `/app/stash/` is a persisted Docker volume (add to docker-compose) |
| Operator confusion between `archived` and `stashed` flows | CLAUDE.md section explicitly contrasts the two; status table makes orthogonality clear |

## 11. Open Questions / V2 Candidates

- **Auto-prune stash older than N days:** would require periodic background task scanning GCS `stash/` and posting failure webhooks to ops. Deferred until manual workflow reveals retention need.
- **Batch stash endpoint:** `POST /stash-batch?status=failed&older_than_days=7` for cleanup days. Deferred — implement when manual one-by-one becomes painful.
- **Direct transition `archived` → `stashed`:** would require moving GCS object between prefixes. Deferred — operator can unarchive then stash via two calls.
- **Stash compression tuning:** investigate `.tar.zst` for better ratio if `.tar.gz` sizes are problematic. Deferred until storage cost data justifies.

---

## Amendment 2026-05-19

Final code review (`superpowers-extended-cc:code-reviewer`) of commits `21bf809f..7ebbb0c8` identified 6 blockers, addressed by follow-up spec `docs/superpowers/specs/2026-05-19-stash-unstash-followup-fixes-design.md`. Summary of contract changes:

- **§2.10 + §10 Prometheus counters** (`stash_total`, `unstash_total`, `unstash_duration_seconds`, `unstash_gcs_orphan_total`): **scoped out**. Replaced by structured `logger.warning` lines with grep-friendly prefixes (e.g., `UNSTASH_GCS_ORPHAN`). Rationale: `crawler-service` has no existing `prometheus_client` usage; adding the dependency + `/metrics` endpoint wiring is out of scope for this fix cycle. Operators rely on `crawler.log` grep until a dedicated observability spec ships.
- **§5.1 pre-flight fail-open**: clarified — `stash_crawl` now wraps the measurement helpers in `try/except` matching the `archive_crawl` pattern (was: implicit; now: explicit).
- **§7.2 unstash extract path**: `tarfile.extractall` now uses `filter="data"` per PEP 706 (CVE-2007-4559 hardening + Python 3.14 forward compat).
- **§5 stash + unstash pre-condition checks**: post-lock re-validation against fresh Redis blob added to close a 2-replica TOCTOU race window between caller's `job_info` snapshot and ownership lock acquisition.
- **§8 test_unstash_writes_request_marker**: replaced timeout-only assertion with concrete marker file path + content capture via `asyncio` polling helper.

See follow-up spec for full rationale and implementation details.
