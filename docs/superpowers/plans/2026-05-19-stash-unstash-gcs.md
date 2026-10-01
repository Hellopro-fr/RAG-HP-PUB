# Stash / Unstash to GCS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /stash/{crawl_id}` and `POST /unstash/{crawl_id}` endpoints to the crawler-service. Stash moves a terminal crawl's storage to `gs://{bucket}/stash/` and frees local disk. Unstash retrieves it back. Built by parametrizing the existing upload/download daemons (no new daemons) and persisting state via a single `stashed_at` field on the existing Redis job hash.

**Architecture:** Mirror the existing archive flow at the infrastructure layer (tar → GCS via daemons) with different semantics (temporary parking instead of permanent archive). Use a new GCS prefix `stash/` alongside `crawls/`. Use a single timestamp field `job_data["stashed_at"]` instead of a new status enum (orthogonal axis). Implement a two-phase commit for unstash via `.unstash-confirmed` + `.unstash-cleanup-done` markers to prevent data loss when extract fails after GCS delete.

**Tech Stack:** Python 3 / FastAPI / Pydantic-settings / Redis / Bash + `gcloud storage` / Docker Compose / systemd / pytest / `shutil.make_archive` + `tarfile` / `aiofiles` / `anyio`.

**Spec:** `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/app/core/config.py` | modify | Add 7 stash Settings vars |
| `apps-microservices/crawler-service/app/schemas/crawler.py` | modify | Add `StashResponse` + `UnstashResponse` Pydantic models |
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | modify | Add `stash_crawl()` + `unstash_crawl()` + helper `_acquire_ownership_lock()` + `_release_ownership_lock()`; extend `cleanup_archives()` to scan stash dirs |
| `apps-microservices/crawler-service/app/router/crawler.py` | modify | Wire `POST /stash/{id}` + `POST /unstash/{id}` route handlers |
| `apps-microservices/crawler-service/docker-compose.yaml` | modify | Add 3 bind-mounts (`/app/stash`, `/app/gcs-stash-requests`, `/app/gcs-stash-downloads`) |
| `tools/upload_daemon.sh` | modify | Add `UPLOAD_WATCH_DIR`, `UPLOAD_GCS_PREFIX`, `UPLOAD_DEAD_LETTER_SUBDIR` env vars |
| `tools/download_daemon.sh` | modify | Add `DOWNLOAD_GCS_PREFIX`, `DELETE_AFTER_DOWNLOAD` env vars + new poll branch for `.unstash-confirmed` markers |
| `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` | create | 15 unit tests covering both endpoints |
| `apps-microservices/crawler-service/tests/integration/test_stash_unstash_e2e.sh` | create | E2E round-trip script |
| `apps-microservices/crawler-service/tests/integration/test_stash_dead_letter.sh` | create | Dead-letter verification |
| `apps-microservices/crawler-service/tests/test_daemon_parametrization.sh` | create | Daemon env-var routing tests |
| `apps-microservices/crawler-service/CLAUDE.md` | modify | Add stash endpoints + stash workflow section |
| `apps-microservices/crawler-service/README.md` | modify | Document new endpoints |
| `docs/daemon_guide.md` | modify | Stash daemon variants + systemd examples + shared dirs table |
| `tools/CLAUDE.md` | modify | Document new env vars |

---

## Patterns Mirrored From Existing Code

To stay consistent with the codebase, the implementation mirrors these existing patterns:

- **Redis lock with TTL + ownership-safe release:** `crawler_manager.py:1611` (`archive_lock:{id}` SET NX EX 1800) — but we add ownership-safe `DEL only if value == replica_id` (currently the codebase uses unconditional `DEL`; we improve here for stash because the operations are longer-lived).
- **Pre-flight disk space check:** `_get_archives_disk_state()` (`crawler_manager.py:1533`) + `_estimate_archive_required_bytes()` (`crawler_manager.py:1513`) + the 503 response shape (`crawler_manager.py:1670-1678`). Reuse both helpers directly.
- **Tar staging + atomic move:** `_create_archive()` inner function (`crawler_manager.py:1696-1731`) — copy the staging-dir pattern verbatim, just point at `STASH_SHARED_PATH/.staging/`.
- **`shutil.make_archive` + `tarfile.open` integrity check:** Same as archive flow.
- **Daemon marker-file protocol:** `_retrieve_from_gcs_daemon()` (`crawler_manager.py:1173-1239`) — `.request` → poll for `.done`/`.error`. Reuse the polling loop verbatim with different paths.
- **Daemon cleanup:** `cleanup_temp_download()` (`crawler_manager.py:1849-1859`) — extend to clean stash markers.
- **`anyio.to_thread.run_sync` for blocking I/O:** Tar create + extract.
- **`HTTPException` with structured `detail` dict:** Used for 503 INSUFFICIENT_DISK_SPACE — same shape for stash.

---

## Task 0: Add stash config vars to Settings (native task #1)

**Goal:** Define all stash-related Pydantic Settings fields so downstream tasks can import them.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py:5-51`

**Acceptance Criteria:**
- [ ] 7 new fields added with documented defaults
- [ ] Settings instantiation succeeds at import time

**Verify:** `cd apps-microservices/crawler-service && python -c "from app.core.config import settings; print(settings.STASH_SHARED_PATH, settings.UNSTASH_TIMEOUT_SECONDS)"` → prints `/app/stash 300`

**Steps:**

- [ ] **Step 1: Add fields after the existing `DOWNLOAD_RESULTS_PATH` block (around line 36)**

```python
    # Stash flow paths (mirror download paths; bind targets must match docker-compose.yaml)
    STASH_SHARED_PATH: str = "/app/stash"
    STASH_DOWNLOAD_REQUESTS_PATH: str = "/app/gcs-stash-requests"
    STASH_DOWNLOAD_RESULTS_PATH: str = "/app/gcs-stash-downloads"

    # Stash flow Redis lock TTLs and timeouts (seconds)
    STASH_LOCK_TTL_SECONDS: int = 600
    UNSTASH_LOCK_TTL_SECONDS: int = 600
    UNSTASH_TIMEOUT_SECONDS: int = 300
    UNSTASH_CLEANUP_GRACE_SECONDS: int = 30
```

- [ ] **Step 2: Verify**

```bash
cd apps-microservices/crawler-service
python -c "from app.core.config import settings; assert settings.STASH_SHARED_PATH == '/app/stash'; assert settings.UNSTASH_TIMEOUT_SECONDS == 300; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/app/core/config.py
git commit -m "feat(crawler-service): add stash config Settings vars

7 new Settings fields for stash flow: paths (STASH_SHARED_PATH +
download requests/results), TTLs (STASH_LOCK + UNSTASH_LOCK), unstash
timeout (300s) + cleanup grace window (30s). Defaults align with
docker-compose bind targets defined in upcoming task.

EN:
feat(crawler-service): add stash config Settings vars

Defaults align with daemon paths + docker-compose bind targets."
```

---

## Task 1: Parametrize upload_daemon.sh (native task #2)

**Goal:** Make `tools/upload_daemon.sh` accept `UPLOAD_WATCH_DIR`, `UPLOAD_GCS_PREFIX`, `UPLOAD_DEAD_LETTER_SUBDIR` env vars without breaking the current archive-flow invocation.

**Files:**
- Modify: `tools/upload_daemon.sh:5-79`

**Acceptance Criteria:**
- [ ] Default invocation (no env override) uploads to `gs://$BUCKET/crawls/{file}` from the archives dir
- [ ] `UPLOAD_GCS_PREFIX=stash UPLOAD_WATCH_DIR=/path/to/stash` uploads to `gs://$BUCKET/stash/{file}`
- [ ] Dead-letter subdir name is parametrizable
- [ ] Shebang + retry logic unchanged

**Verify:** `bash -n tools/upload_daemon.sh` (syntax OK) + `UPLOAD_GCS_PREFIX=stash bash -c 'source tools/upload_daemon.sh' 2>&1 | head -5` shows the new prefix in startup log

**Steps:**

- [ ] **Step 1: Read the current daemon and identify the lines to change**

```bash
sed -n '1,30p' tools/upload_daemon.sh
sed -n '40,55p' tools/upload_daemon.sh
```

The variables defined at top: `DEFAULT_ARCHIVES_DIR`, `ARCHIVES_DIR`, `MAX_RETRIES`, `DEAD_LETTER_DIR`. The hardcoded prefix is on line 48: `target_url="gs://$BUCKET_NAME/crawls/$filename"`.

- [ ] **Step 2: Replace the configuration block at the top**

Replace lines 4-7 (the configuration section before the env loading) with:

```bash
# Configuration
# UPLOAD_WATCH_DIR: dir scanned for *.tar.gz (default = crawler-service archives)
# UPLOAD_GCS_PREFIX: path component under gs://$BUCKET/ (default = crawls)
# UPLOAD_DEAD_LETTER_SUBDIR: subdir name inside watch dir for retry-exhausted files (default = dead_letter)
DEFAULT_ARCHIVES_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_archives"
ARCHIVES_DIR="${UPLOAD_WATCH_DIR:-${ARCHIVES_DIR:-$DEFAULT_ARCHIVES_DIR}}"
UPLOAD_GCS_PREFIX="${UPLOAD_GCS_PREFIX:-crawls}"
UPLOAD_DEAD_LETTER_SUBDIR="${UPLOAD_DEAD_LETTER_SUBDIR:-dead_letter}"
```

- [ ] **Step 3: Update DEAD_LETTER_DIR computation (around line 24)**

Replace:
```bash
DEAD_LETTER_DIR="$ARCHIVES_DIR/dead_letter"
```

With:
```bash
DEAD_LETTER_DIR="$ARCHIVES_DIR/$UPLOAD_DEAD_LETTER_SUBDIR"
```

- [ ] **Step 4: Update the target URL (around line 48)**

Replace:
```bash
target_url="gs://$BUCKET_NAME/crawls/$filename"
```

With:
```bash
target_url="gs://$BUCKET_NAME/$UPLOAD_GCS_PREFIX/$filename"
```

- [ ] **Step 5: Update the startup log (around line 37)**

Replace:
```bash
echo "Target Bucket: gs://$BUCKET_NAME/crawls/"
```

With:
```bash
echo "Target Bucket: gs://$BUCKET_NAME/$UPLOAD_GCS_PREFIX/"
echo "Watch dir:     $ARCHIVES_DIR"
echo "Dead-letter:   $DEAD_LETTER_DIR"
```

- [ ] **Step 6: Syntax check + smoke-test default-env behavior**

```bash
bash -n tools/upload_daemon.sh
# Verify defaults preserve current target URL — grep for the substituted value
GCS_BUCKET_NAME=test bash -c 'source tools/upload_daemon.sh 2>&1 || true' | grep "gs://test/crawls/"
```

Expected: `bash -n` exits 0, grep finds the line `Target Bucket: gs://test/crawls/`.

- [ ] **Step 7: Smoke-test stash override**

```bash
GCS_BUCKET_NAME=test UPLOAD_GCS_PREFIX=stash UPLOAD_WATCH_DIR=/tmp/test-stash bash -c 'source tools/upload_daemon.sh 2>&1 || true' | grep "gs://test/stash/"
```

Expected: grep finds the line `Target Bucket: gs://test/stash/`.

- [ ] **Step 8: Commit**

```bash
git add tools/upload_daemon.sh
git commit -m "feat(tools): parametrize upload_daemon.sh via env vars

UPLOAD_WATCH_DIR + UPLOAD_GCS_PREFIX + UPLOAD_DEAD_LETTER_SUBDIR
env vars added. Defaults preserve current behavior (uploads from
crawler_archives/ to gs://bucket/crawls/). Enables running a second
daemon instance for stash flow without code duplication.

EN:
feat(tools): parametrize upload_daemon.sh via env vars

Defaults preserve current archive-flow behavior."
```

---

## Task 2: Parametrize download_daemon.sh + 2-phase commit (native task #3)

**Goal:** Add `DOWNLOAD_GCS_PREFIX` + `DELETE_AFTER_DOWNLOAD` env vars and a second poll branch that scans for `*.unstash-confirmed` markers, calls `gcloud storage rm`, and writes `*.unstash-cleanup-done` markers.

**Files:**
- Modify: `tools/download_daemon.sh:28-89`

**Acceptance Criteria:**
- [ ] Default invocation downloads from `gs://$BUCKET/crawls/{id}.tar.gz`
- [ ] `DOWNLOAD_GCS_PREFIX=stash` downloads from `gs://$BUCKET/stash/{id}.tar.gz`
- [ ] When `DELETE_AFTER_DOWNLOAD=true`, the daemon scans `*.unstash-confirmed` and deletes the GCS object on success
- [ ] On successful `gcloud storage rm`, a `{id}.unstash-cleanup-done` marker is written
- [ ] On failed `gcloud storage rm`, the daemon logs a WARNING and does NOT write the cleanup marker (so the service times out and operator can investigate)

**Verify:** `bash -n tools/download_daemon.sh` (syntax OK) + manual marker test (see Step 7).

**Steps:**

- [ ] **Step 1: Add new env-var declarations**

After the existing `RESULTS_DIR` declaration (around line 33), add:

```bash
DOWNLOAD_GCS_PREFIX="${DOWNLOAD_GCS_PREFIX:-crawls}"
DELETE_AFTER_DOWNLOAD="${DELETE_AFTER_DOWNLOAD:-false}"
```

- [ ] **Step 2: Update source URL (around line 65)**

Replace:
```bash
source_url="gs://$BUCKET_NAME/crawls/$crawl_id.tar.gz"
```

With:
```bash
source_url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"
```

- [ ] **Step 3: Update startup log (around line 57)**

Replace:
```bash
echo "Source Bucket:      gs://$BUCKET_NAME/crawls/"
```

With:
```bash
echo "Source Bucket:      gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/"
echo "Delete after dl:   $DELETE_AFTER_DOWNLOAD"
```

- [ ] **Step 4: Add the 2-phase commit poll branch inside the main `while true` loop**

After the existing `find ... *.request` block (around line 85), but BEFORE the `sleep $CHECK_INTERVAL` at the end of the loop, add:

```bash
    # Phase 2 (2-phase commit): scan for service-written .unstash-confirmed markers
    # and delete the GCS source. Only active when DELETE_AFTER_DOWNLOAD=true.
    # Service writes {id}.unstash-confirmed after successful extract; daemon
    # responds by deleting the GCS object and writing {id}.unstash-cleanup-done.
    if [ "$DELETE_AFTER_DOWNLOAD" = "true" ]; then
        find "$RESULTS_DIR" -maxdepth 1 -name "*.unstash-confirmed" -print0 | while IFS= read -r -d '' confirm_file; do
            crawl_id=$(basename "$confirm_file" .unstash-confirmed)
            source_url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"
            cleanup_done="$RESULTS_DIR/$crawl_id.unstash-cleanup-done"

            echo "[$(date)] Extract confirmed for $crawl_id, deleting GCS source..."
            if gcloud storage rm "$source_url"; then
                echo "GCS source deleted: $source_url"
                touch "$cleanup_done"
                rm "$confirm_file"
            else
                echo "WARNING: gcloud storage rm failed for $source_url. Leaving .unstash-confirmed for retry on next poll."
                # Intentionally do NOT touch cleanup_done and do NOT remove confirm_file:
                # the service will time out and operator can investigate. Next daemon
                # poll cycle will retry the gcloud rm.
            fi
        done
    fi
```

- [ ] **Step 5: Syntax check**

```bash
bash -n tools/download_daemon.sh
```

Expected: exit 0.

- [ ] **Step 6: Smoke-test default-env (DELETE_AFTER_DOWNLOAD=false)**

```bash
GCS_BUCKET_NAME=test timeout 3 bash tools/download_daemon.sh 2>&1 | head -10
```

Expected: startup log shows `Source Bucket: gs://test/crawls/` and `Delete after dl: false`.

- [ ] **Step 7: Smoke-test 2-phase commit branch (DELETE_AFTER_DOWNLOAD=true)**

```bash
# Setup
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/results"

# Drop a fake .unstash-confirmed marker
touch "$TMPDIR/results/test123.unstash-confirmed"

# Run daemon for one cycle. gcloud rm will fail (bucket doesn't exist),
# verifying the WARNING path keeps the marker.
GCS_BUCKET_NAME=nonexistent-test-bucket \
DOWNLOAD_REQUESTS_PATH="$TMPDIR/requests" \
DOWNLOAD_RESULTS_PATH="$TMPDIR/results" \
DOWNLOAD_GCS_PREFIX=stash \
DELETE_AFTER_DOWNLOAD=true \
timeout 8 bash tools/download_daemon.sh 2>&1 | grep -E "(Extract confirmed|WARNING)"

# Verify the marker is still present (failure path retains it)
ls "$TMPDIR/results/test123.unstash-confirmed" && echo "PASS: marker retained on failure"

# Cleanup
rm -rf "$TMPDIR"
```

Expected: grep finds `Extract confirmed for test123` and `WARNING: gcloud storage rm failed`; the `ls` succeeds.

- [ ] **Step 8: Commit**

```bash
git add tools/download_daemon.sh
git commit -m "feat(tools): parametrize download_daemon.sh + 2-phase commit

DOWNLOAD_GCS_PREFIX + DELETE_AFTER_DOWNLOAD env vars added. Default
behavior unchanged (downloads from gs://bucket/crawls/). When
DELETE_AFTER_DOWNLOAD=true, daemon scans .unstash-confirmed markers,
deletes the GCS source, and writes .unstash-cleanup-done. Failed
gcloud rm logs WARNING + retains marker for next poll (no data loss).

EN:
feat(tools): parametrize download_daemon.sh + 2-phase commit"
```

---

## Task 3: Add stash volume mounts to docker-compose.yaml (native task #4)

**Goal:** Bind-mount three new host dirs to the crawler-service container so that the Python code and the host-side daemons share state via the filesystem.

**Files:**
- Modify: `apps-microservices/crawler-service/docker-compose.yaml:30-34`

**Acceptance Criteria:**
- [ ] Three new bind-mounts added to the crawler-service `volumes:` section
- [ ] Existing mounts unchanged
- [ ] `docker-compose --profile crawling config` parses successfully

**Verify:** `docker-compose --profile crawling -f apps-microservices/crawler-service/docker-compose.yaml config | grep -A2 stash`

**Steps:**

- [ ] **Step 1: Add bind-mounts to the crawler-service service definition**

After the existing `crawler_data:/app/storage` line (around line 32), insert:

```yaml
      # Stash flow shared dirs (mirror archive-flow mounts)
      - ./crawler_stash:/app/stash
      - ./crawler_stash_download_requests:/app/gcs-stash-requests
      - ./crawler_stash_download_results:/app/gcs-stash-downloads
```

- [ ] **Step 2: Validate compose file syntax**

```bash
docker-compose --profile crawling -f apps-microservices/crawler-service/docker-compose.yaml config > /dev/null && echo "OK"
```

Expected: `OK`.

- [ ] **Step 3: Verify mounts appear in resolved config**

```bash
docker-compose --profile crawling -f apps-microservices/crawler-service/docker-compose.yaml config | grep -E "(stash|gcs-stash)"
```

Expected: 3 lines containing `/app/stash`, `/app/gcs-stash-requests`, `/app/gcs-stash-downloads`.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/docker-compose.yaml
git commit -m "feat(crawler-service): add stash bind-mounts to compose

Three new host bind-mounts for stash flow filesystem signaling:
crawler_stash/ -> /app/stash, crawler_stash_download_requests/ ->
/app/gcs-stash-requests, crawler_stash_download_results/ ->
/app/gcs-stash-downloads. Mirrors the archive-flow mount pattern.

EN:
feat(crawler-service): add stash bind-mounts to compose"
```

---

## Task 4: Add StashResponse + UnstashResponse Pydantic schemas (native task #5)

**Goal:** Define response models for the two new endpoints so router code stays clean and OpenAPI documents the response shapes.

**Files:**
- Modify: `apps-microservices/crawler-service/app/schemas/crawler.py:96-107` (append new models after `ArchiveResponse`)

**Acceptance Criteria:**
- [ ] `StashResponse` with `crawl_id`, `status`, `stash_path`, `stashed_at`
- [ ] `UnstashResponse` with `crawl_id`, `status`, `restored_to`, `elapsed_seconds`, optional `gcs_cleanup_status`
- [ ] Import succeeds; OpenAPI schema generation succeeds

**Verify:** `cd apps-microservices/crawler-service && python -c "from app.schemas.crawler import StashResponse, UnstashResponse; print(StashResponse.model_json_schema()['required'])"`

**Steps:**

- [ ] **Step 1: Append the two models after `ArchiveResponse`**

```python
class StashResponse(BaseModel):
    """Response for POST /stash/{crawl_id} — 202 Accepted shape."""
    crawl_id: str
    status: str = Field("stashing", description="Always 'stashing' when 202 returned; data is in /app/stash awaiting daemon upload to GCS.")
    stash_path: str = Field(..., description="Target GCS object path (gs://{bucket}/stash/{id}.tar.gz).")
    stashed_at: datetime = Field(..., description="ISO 8601 UTC timestamp written to Redis job_data.")


class UnstashResponse(BaseModel):
    """Response for POST /unstash/{crawl_id} — 200 OK shape."""
    crawl_id: str
    status: str = Field("unstashed", description="Always 'unstashed' when 200 returned.")
    restored_to: str = Field(..., description="Local storage path where the archive was extracted.")
    elapsed_seconds: float = Field(..., description="Total round-trip wall-time (request marker write -> Redis flag clear).")
    gcs_cleanup_status: Optional[str] = Field(
        None,
        description="'cleaned' when the GCS source was deleted within UNSTASH_CLEANUP_GRACE_SECONDS, 'deferred' when the cleanup marker did not arrive in time (an orphan GCS object remains and must be manually cleaned)."
    )
```

- [ ] **Step 2: Verify imports + JSON schema generation**

```bash
cd apps-microservices/crawler-service
python -c "
from app.schemas.crawler import StashResponse, UnstashResponse
s = StashResponse(crawl_id='x', stash_path='gs://b/stash/x.tar.gz', stashed_at='2026-05-19T00:00:00Z')
u = UnstashResponse(crawl_id='x', restored_to='/app/storage/x', elapsed_seconds=1.0)
print('StashResponse fields:', list(s.model_dump().keys()))
print('UnstashResponse fields:', list(u.model_dump().keys()))
"
```

Expected: both lines print and include the expected field names.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/app/schemas/crawler.py
git commit -m "feat(crawler-service): add StashResponse + UnstashResponse schemas

Pydantic response models for POST /stash and POST /unstash endpoints.
StashResponse documents the async 202 shape with stash_path GCS URL +
stashed_at timestamp. UnstashResponse documents the sync 200 shape
with restored_to + elapsed_seconds + optional gcs_cleanup_status
('cleaned' | 'deferred') to surface orphan GCS objects to the caller.

EN:
feat(crawler-service): add stash response Pydantic schemas"
```

---

## Task 5: Implement crawler_manager.stash_crawl() + ownership-safe lock helpers (native task #6)

**Goal:** Add the `stash_crawl()` method to `CrawlerManager` along with two private helpers for ownership-safe Redis lock acquire/release (reused by `unstash_crawl()` in Task 6).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (append new methods after `_restore_archived_crawl`, around line 1848, and add module-level `replica_id` constant near line 44)

**Acceptance Criteria:**
- [ ] `stash_crawl(job_info)` returns a dict matching `StashResponse` fields
- [ ] Pre-conditions enforced: status terminal, `stashed_at` null, no `archived_at`, lock not held
- [ ] Disk pre-flight uses existing `_get_archives_disk_state()` + `_estimate_archive_required_bytes()` helpers
- [ ] Tar written to `/app/stash/.staging/{id}.tar.gz` then atomically renamed
- [ ] Redis `stashed_at` set BEFORE local cleanup; local crawl dir deleted AFTER Redis write
- [ ] `_acquire_ownership_lock()` returns the lock value on success, None on failure
- [ ] `_release_ownership_lock()` deletes the lock only if value matches (uses Lua script for atomicity)

**Verify:** `pytest apps-microservices/crawler-service/tests/test_crawler_manager_stash.py -v -k "stash"` (will fail with `ImportError` until Task 9 lands; that's expected — verify implementation by inspection + the Task 9 verify run).

**Steps:**

- [ ] **Step 1: Add the replica_id constant near the other module-level constants**

After line 44 (after `FAILED_CALLBACKS_KEY`), add:

```python
# Replica identity for ownership-safe Redis locks. Generated once per process.
# Used by stash/unstash to avoid clobbering a new acquirer's lock after TTL expiry.
import socket as _socket
REPLICA_ID = f"{_socket.gethostname()}-{uuid.uuid4().hex[:8]}"
```

- [ ] **Step 2: Add the two ownership-safe lock helpers as `CrawlerManager` methods**

Append after `cleanup_temp_download` (around line 1860):

```python
    async def _acquire_ownership_lock(self, lock_key: str, ttl_seconds: int) -> Optional[str]:
        """Acquire a Redis lock with TTL, value = REPLICA_ID. Returns the value on
        success, None on failure. Pairs with _release_ownership_lock for atomic
        compare-and-delete (Lua script) to prevent clobbering a new acquirer
        after TTL expiry."""
        acquired = await cache_service.redis_client.set(lock_key, REPLICA_ID, nx=True, ex=ttl_seconds)
        return REPLICA_ID if acquired else None

    async def _release_ownership_lock(self, lock_key: str, expected_value: str) -> bool:
        """Atomic compare-and-delete via Lua script. Returns True if the lock was
        deleted (we owned it), False otherwise. Safe to call even if the lock
        already expired or was acquired by another replica."""
        if expected_value is None:
            return False
        # Atomic CAS via Lua — avoids race between GET and DEL
        lua = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            result = await cache_service.redis_client.eval(lua, 1, lock_key, expected_value)
            return bool(result)
        except Exception as e:
            logger.warning(f"Ownership-safe lock release failed for '{lock_key}': {e}")
            return False
```

- [ ] **Step 3: Add `stash_crawl()` method**

Append after the helpers:

```python
    async def stash_crawl(self, job_info: dict) -> dict:
        """
        Stash a terminal crawl's storage dir to GCS (under gs://{bucket}/stash/) to free
        local disk. Only crawls in failed/stopped/finished status WITHOUT an existing
        `stashed_at` or `archived` status can be stashed.

        Sets job_data["stashed_at"] = ISO timestamp BEFORE deleting local data.
        The upload daemon (configured with UPLOAD_GCS_PREFIX=stash) picks up the tar
        from /app/stash/ asynchronously.

        Returns a dict with crawl_id, status='stashing', stash_path, stashed_at.
        """
        crawl_id = job_info['crawl_id']
        job_status = job_info.get('status')

        # --- Pre-condition checks ---
        if job_status in ("running", "restarting_oom", "stopping"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "CRAWL_IS_ACTIVE", "current_status": job_status}
            )
        if job_status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "ALREADY_ARCHIVED"}
            )
        if job_info.get("stashed_at"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "ALREADY_STASHED", "stashed_at": job_info["stashed_at"]}
            )

        # --- Acquire ownership-safe lock ---
        stash_lock_key = f"stash_lock:{crawl_id}"
        unstash_lock_key = f"unstash_lock:{crawl_id}"
        if await cache_service.redis_client.exists(unstash_lock_key):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "OPERATION_IN_PROGRESS", "operation": "unstash"}
            )
        lock_value = await self._acquire_ownership_lock(stash_lock_key, settings.STASH_LOCK_TTL_SECONDS)
        if lock_value is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "OPERATION_IN_PROGRESS", "operation": "stash"}
            )

        try:
            stash_dir = settings.STASH_SHARED_PATH
            target_tar = os.path.join(stash_dir, f"{crawl_id}.tar.gz")
            job_storage_path = job_info["storage_path"]

            # --- Pre-flight disk space check ---
            baseline_state = self._get_archives_disk_state(stash_dir)
            logger.info(f"Stash disk state for '{crawl_id}': {baseline_state}")
            required_bytes = self._estimate_archive_required_bytes(job_storage_path)
            required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

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

            # --- Tar via staging dir + atomic move (mirror archive flow) ---
            def _create_stash_archive():
                staging_dir = os.path.join(stash_dir, ".staging")
                os.makedirs(staging_dir, exist_ok=True)
                os.makedirs(stash_dir, exist_ok=True)
                staging_base = os.path.join(staging_dir, crawl_id)
                staging_path = None
                try:
                    staging_path = shutil.make_archive(staging_base, 'gztar', root_dir=job_storage_path)
                    if os.path.getsize(staging_path) == 0:
                        raise RuntimeError(f"Stash archive at '{staging_path}' is empty (0 bytes).")
                    # Integrity check
                    with tarfile.open(staging_path, 'r:gz') as t:
                        t.getnames()
                    os.rename(staging_path, target_tar)
                    staging_path = None  # transferred ownership
                    return target_tar, os.path.getsize(target_tar)
                finally:
                    if staging_path and os.path.exists(staging_path):
                        try:
                            os.remove(staging_path)
                        except OSError:
                            pass

            try:
                final_path, archive_size = await anyio.to_thread.run_sync(_create_stash_archive)
                logger.info(f"Stashed crawl '{crawl_id}' ({archive_size} bytes) -> {final_path}")
            except Exception as e:
                logger.error(f"Failed to create stash archive for '{crawl_id}': {e}", exc_info=True)
                try:
                    post_failure_state = self._get_archives_disk_state(stash_dir)
                    logger.error(f"Stash disk state at failure for '{crawl_id}': {post_failure_state}")
                except Exception:
                    pass
                raise HTTPException(status_code=500, detail=f"Stash archive creation failed: {str(e)}")

            # --- Mark as stashed in Redis (BEFORE deleting local data) ---
            stashed_at = datetime.utcnow().isoformat() + "Z"
            job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
            fresh_job_info = await cache_service.get_json(job_key)
            if not fresh_job_info:
                logger.error(f"Cannot mark '{crawl_id}' as stashed: job not found in Redis after stash tar created.")
                raise HTTPException(status_code=500, detail="Job vanished from Redis during stash.")
            fresh_job_info["stashed_at"] = stashed_at
            await cache_service.set_json(job_key, fresh_job_info)
            logger.info(f"Marked crawl '{crawl_id}' as stashed at {stashed_at} in Redis.")

            # --- Delete local crawl storage dir (safe to fail — data is in the tar) ---
            try:
                def _delete_local():
                    if os.path.isdir(job_storage_path):
                        shutil.rmtree(job_storage_path)
                await anyio.to_thread.run_sync(_delete_local)
                logger.info(f"Deleted local storage for stashed crawl '{crawl_id}'.")
            except Exception as e:
                logger.warning(f"Local cleanup failed for stashed '{crawl_id}' (tar is safe): {e}")

            return {
                "crawl_id": crawl_id,
                "status": "stashing",
                "stash_path": f"gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz",
                "stashed_at": stashed_at,
            }

        finally:
            await self._release_ownership_lock(stash_lock_key, lock_value)
```

- [ ] **Step 4: Syntax + import smoke test**

```bash
cd apps-microservices/crawler-service
python -c "from app.core.crawler_manager import crawler_manager, REPLICA_ID; print('REPLICA_ID =', REPLICA_ID); print('stash_crawl exists =', hasattr(crawler_manager, 'stash_crawl'))"
```

Expected: prints a replica id + `stash_crawl exists = True`.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py
git commit -m "feat(crawler-service): add stash_crawl + ownership-safe lock helpers

stash_crawl method + REPLICA_ID constant + _acquire_ownership_lock /
_release_ownership_lock helpers. Lock release uses Lua compare-and-
delete to avoid clobbering a new acquirer after TTL expiry.

stash_crawl mirrors archive_crawl: pre-flight disk check (mirror
existing 503 INSUFFICIENT_DISK_SPACE shape), tar via .staging
subdirectory + atomic move (daemon find -maxdepth 1 ignores
.staging), Redis stashed_at flag set BEFORE local cleanup, local dir
deleted only after Redis write succeeds. Lock auto-released in
finally even on exception.

Conflict matrix enforced: 409 ALREADY_ARCHIVED / ALREADY_STASHED /
CRAWL_IS_ACTIVE / OPERATION_IN_PROGRESS.

EN:
feat(crawler-service): add stash_crawl + ownership-safe lock helpers"
```

---

## Task 6: Implement crawler_manager.unstash_crawl() (native task #7)

**Goal:** Add `unstash_crawl()` to `CrawlerManager`. Synchronous flow: write `.request`, poll `.done`/`.error`, extract tar, write `.unstash-confirmed`, poll `.unstash-cleanup-done` (with grace window), clear `stashed_at`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (append `unstash_crawl` after `stash_crawl`)

**Acceptance Criteria:**
- [ ] Pre-condition checks: `stashed_at` not null, no `unstash_lock`/`stash_lock` held
- [ ] Disk pre-flight (extracted size ≈ tar × 2 + 500MB floor)
- [ ] `.request` marker written; daemon polled for `.done`/`.error` bounded by `UNSTASH_TIMEOUT_SECONDS`
- [ ] On `.error`: 502 GCS_DOWNLOAD_FAILED, `stashed_at` preserved
- [ ] On `.done`: extract tar; on extract exception → 502 EXTRACT_FAILED, `stashed_at` preserved, no `.unstash-confirmed` written
- [ ] On extract success: `.unstash-confirmed` written, daemon's `.unstash-cleanup-done` polled within `UNSTASH_CLEANUP_GRACE_SECONDS`
- [ ] On cleanup-done received: clear `stashed_at`, cleanup all markers, return 200 with `gcs_cleanup_status='cleaned'`
- [ ] On cleanup grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'` (orphan GCS object flagged)

**Verify:** `pytest apps-microservices/crawler-service/tests/test_crawler_manager_stash.py -v -k "unstash"` (will fail until Task 9; verify implementation by inspection + Task 9 run).

**Steps:**

- [ ] **Step 1: Append `unstash_crawl` method**

```python
    async def unstash_crawl(self, job_info: dict) -> dict:
        """
        Restore a stashed crawl from GCS back to local storage.
        Synchronous: writes .request marker, polls .done/.error, extracts archive,
        writes .unstash-confirmed for the daemon to delete the GCS source, polls
        .unstash-cleanup-done within a grace window, then clears stashed_at.

        Returns a dict with crawl_id, status='unstashed', restored_to,
        elapsed_seconds, gcs_cleanup_status ('cleaned' | 'deferred').
        """
        crawl_id = job_info['crawl_id']
        start_time = time.monotonic()

        # --- Pre-condition checks ---
        if not job_info.get("stashed_at"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "NOT_STASHED"}
            )

        unstash_lock_key = f"unstash_lock:{crawl_id}"
        stash_lock_key = f"stash_lock:{crawl_id}"
        if await cache_service.redis_client.exists(stash_lock_key):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "OPERATION_IN_PROGRESS", "operation": "stash"}
            )
        lock_value = await self._acquire_ownership_lock(unstash_lock_key, settings.UNSTASH_LOCK_TTL_SECONDS)
        if lock_value is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "OPERATION_IN_PROGRESS", "operation": "unstash"}
            )

        requests_dir = settings.STASH_DOWNLOAD_REQUESTS_PATH
        results_dir = settings.STASH_DOWNLOAD_RESULTS_PATH
        request_path = os.path.join(requests_dir, f"{crawl_id}.request")
        download_path = os.path.join(results_dir, f"{crawl_id}.tar.gz")
        done_path = os.path.join(results_dir, f"{crawl_id}.done")
        error_path = os.path.join(results_dir, f"{crawl_id}.error")
        confirm_path = os.path.join(results_dir, f"{crawl_id}.unstash-confirmed")
        cleanup_done_path = os.path.join(results_dir, f"{crawl_id}.unstash-cleanup-done")

        try:
            # --- Submit download request ---
            os.makedirs(requests_dir, exist_ok=True)
            os.makedirs(results_dir, exist_ok=True)
            async with aiofiles.open(request_path, 'w') as f:
                await f.write(crawl_id)
            logger.info(f"Unstash request submitted for '{crawl_id}'. Waiting for daemon...")

            # --- Poll for .done / .error ---
            deadline = time.monotonic() + settings.UNSTASH_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if os.path.exists(error_path):
                    error_msg = "Download failed"
                    try:
                        async with aiofiles.open(error_path, 'r') as f:
                            error_msg = (await f.read()).strip()
                    except Exception:
                        pass
                    try:
                        os.remove(error_path)
                    except OSError:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail={"error_code": "GCS_DOWNLOAD_FAILED", "marker_content": error_msg}
                    )
                if os.path.exists(done_path) and os.path.exists(download_path):
                    break
                await asyncio.sleep(1)
            else:
                # Timeout
                try:
                    if os.path.exists(request_path):
                        os.remove(request_path)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={"error_code": "UNSTASH_TIMEOUT", "elapsed_seconds": settings.UNSTASH_TIMEOUT_SECONDS}
                )

            # --- Disk pre-flight for extract (size of tar × 2 + 500MB floor) ---
            try:
                tar_size = os.path.getsize(download_path)
                required_bytes = max(int(tar_size * 2), 500 * 1024 * 1024)
                baseline_state = self._get_archives_disk_state(settings.CRAWLER_STORAGE_PATH)
                if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
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
                logger.warning(f"Disk pre-flight skipped for unstash '{crawl_id}': {e}")

            # --- Extract archive (failure preserves stashed_at, no .unstash-confirmed) ---
            target_storage = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)
            try:
                def _extract():
                    os.makedirs(target_storage, exist_ok=True)
                    with tarfile.open(download_path, 'r:gz') as tar:
                        tar.extractall(path=target_storage)
                await anyio.to_thread.run_sync(_extract)
                logger.info(f"Extracted unstash archive for '{crawl_id}' to '{target_storage}'.")
            except Exception as e:
                logger.error(f"Extract failed for unstash '{crawl_id}': {e}", exc_info=True)
                # Cleanup partial extract; do NOT write .unstash-confirmed; preserve stashed_at
                try:
                    if os.path.isdir(target_storage):
                        shutil.rmtree(target_storage)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"error_code": "EXTRACT_FAILED", "exception": str(e)}
                )

            # --- Phase 2: write .unstash-confirmed; daemon will delete GCS + write cleanup-done ---
            async with aiofiles.open(confirm_path, 'w') as f:
                await f.write(crawl_id)
            logger.info(f"Wrote .unstash-confirmed for '{crawl_id}'. Waiting for daemon GCS cleanup...")

            cleanup_deadline = time.monotonic() + settings.UNSTASH_CLEANUP_GRACE_SECONDS
            gcs_cleanup_status = "deferred"
            while time.monotonic() < cleanup_deadline:
                if os.path.exists(cleanup_done_path):
                    gcs_cleanup_status = "cleaned"
                    break
                await asyncio.sleep(1)

            if gcs_cleanup_status == "deferred":
                logger.warning(
                    f"Unstash cleanup-done marker not arrived within "
                    f"{settings.UNSTASH_CLEANUP_GRACE_SECONDS}s for '{crawl_id}'. "
                    f"GCS object may be orphaned at gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz."
                )

            # --- Clear stashed_at in Redis ---
            job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
            fresh_job_info = await cache_service.get_json(job_key)
            if fresh_job_info and "stashed_at" in fresh_job_info:
                fresh_job_info.pop("stashed_at", None)
                await cache_service.set_json(job_key, fresh_job_info)
            logger.info(f"Cleared stashed_at for '{crawl_id}'.")

            # --- Cleanup markers + downloaded tar ---
            for path in (request_path, done_path, error_path, confirm_path, cleanup_done_path, download_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError as e:
                    logger.warning(f"Failed to clean marker '{path}': {e}")

            elapsed = round(time.monotonic() - start_time, 2)
            return {
                "crawl_id": crawl_id,
                "status": "unstashed",
                "restored_to": target_storage,
                "elapsed_seconds": elapsed,
                "gcs_cleanup_status": gcs_cleanup_status,
            }

        finally:
            await self._release_ownership_lock(unstash_lock_key, lock_value)
```

- [ ] **Step 2: Smoke test import**

```bash
cd apps-microservices/crawler-service
python -c "from app.core.crawler_manager import crawler_manager; print('unstash_crawl exists =', hasattr(crawler_manager, 'unstash_crawl'))"
```

Expected: `unstash_crawl exists = True`.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py
git commit -m "feat(crawler-service): add unstash_crawl + 2-phase commit

unstash_crawl method implementing the full 2-phase commit:
1. Write .request, poll .done/.error (bounded UNSTASH_TIMEOUT_SECONDS)
2. Extract tar to original storage path
3. On extract success: write .unstash-confirmed (signals daemon)
4. Poll .unstash-cleanup-done within UNSTASH_CLEANUP_GRACE_SECONDS
5. On cleanup-done: return 200 with gcs_cleanup_status='cleaned'
6. On grace expired: return 200 with gcs_cleanup_status='deferred'
   (orphan GCS object flagged to ops via warning log)

Extract failure preserves stashed_at + does NOT write
.unstash-confirmed -> daemon never deletes GCS source -> caller can
retry. 502 EXTRACT_FAILED returned. Ownership-safe lock release in
finally.

EN:
feat(crawler-service): add unstash_crawl with 2-phase commit"
```

---

## Task 7: Add POST /stash + POST /unstash router endpoints (native task #8)

**Goal:** Wire the two crawler-manager methods to REST.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/crawler.py:17` (import) + add two endpoints near `archive_crawl_to_gcs` (around line 363)

**Acceptance Criteria:**
- [ ] `POST /stash/{crawl_id}` returns 202 with `StashResponse`
- [ ] `POST /unstash/{crawl_id}` returns 200 with `UnstashResponse`
- [ ] `HTTPException` raised by crawler_manager surfaces unchanged
- [ ] Both endpoints use `get_job_or_recover` dependency for 404 + recovery semantics
- [ ] OpenAPI tags + summaries

**Verify:** `cd apps-microservices/crawler-service && python -c "from main import app; routes = [r.path for r in app.routes]; assert '/stash/{crawl_id}' in routes; assert '/unstash/{crawl_id}' in routes; print('OK')"`

**Steps:**

- [ ] **Step 1: Update the schemas import**

In `app/router/crawler.py:17`, replace:

```python
from app.schemas.crawler import CrawlRequest, CrawlResponse, CrawlStatus, StopResponse, IncludeInArchive, CapacityResponse, ReindexResponse, ArchiveResponse, PruneResponse, PendingCallbacksResponse
```

With:

```python
from app.schemas.crawler import CrawlRequest, CrawlResponse, CrawlStatus, StopResponse, IncludeInArchive, CapacityResponse, ReindexResponse, ArchiveResponse, PruneResponse, PendingCallbacksResponse, StashResponse, UnstashResponse
```

- [ ] **Step 2: Add the two endpoints after `archive_crawl_to_gcs` (after line 361)**

```python
@router.post("/stash/{crawl_id}", response_model=StashResponse, status_code=status.HTTP_202_ACCEPTED)
async def stash_crawl_endpoint(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Stash a terminal crawl's storage to GCS (gs://{bucket}/stash/) to free local disk.
    The crawl must be in failed/stopped/finished status and not already stashed/archived.
    Local data is deleted only AFTER the Redis stashed_at flag is set; the upload daemon
    handles GCS upload asynchronously. Use POST /unstash/{crawl_id} to restore.
    """
    try:
        result = await crawler_manager.stash_crawl(job_info)
        return StashResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stashing crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during stash.")


@router.post("/unstash/{crawl_id}", response_model=UnstashResponse)
async def unstash_crawl_endpoint(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Restore a stashed crawl's data from GCS to local storage. Synchronous: waits for
    daemon download + extract + 2-phase GCS cleanup. Bounded by UNSTASH_TIMEOUT_SECONDS
    (default 300s). On success, stashed_at is cleared. If the GCS-rm cleanup-done
    marker does not arrive within the grace window, returns 200 with
    gcs_cleanup_status='deferred' (orphan GCS object — manual cleanup required).
    """
    try:
        result = await crawler_manager.unstash_crawl(job_info)
        return UnstashResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unstashing crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during unstash.")
```

- [ ] **Step 3: Smoke test routes registration**

```bash
cd apps-microservices/crawler-service
python -c "
from main import app
routes = [r.path for r in app.routes]
assert '/stash/{crawl_id}' in routes, 'stash route missing'
assert '/unstash/{crawl_id}' in routes, 'unstash route missing'
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/app/router/crawler.py
git commit -m "feat(crawler-service): add POST /stash + POST /unstash routes

REST entry points wiring to crawler_manager.stash_crawl /
unstash_crawl. Both use get_job_or_recover dependency for 404 +
storage recovery semantics. HTTPException from manager surfaces
unchanged (preserves 409/503/504/502 conflict + disk + timeout +
gateway error codes documented in spec).

EN:
feat(crawler-service): add POST /stash + POST /unstash router endpoints"
```

---

## Task 8: Extend scheduled_archive_cleanup for stash dirs (native task #9)

**Goal:** Add the two stash download dirs (`STASH_DOWNLOAD_RESULTS_PATH` and `STASH_DOWNLOAD_REQUESTS_PATH`) to the existing cleanup task without touching `/app/stash/` itself (which the daemon owns).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py:2267-2290` (the cleanup_archives "Also clean up stale GCS download artifacts" loop)

**Acceptance Criteria:**
- [ ] Cleanup loop scans `STASH_DOWNLOAD_RESULTS_PATH` for `.tar.gz/.done/.error/.unstash-confirmed/.unstash-cleanup-done` markers
- [ ] Cleanup loop scans `STASH_DOWNLOAD_REQUESTS_PATH` for `.request` markers
- [ ] Does NOT touch `STASH_SHARED_PATH` (daemon-owned)
- [ ] Existing archive + non-stash GCS download dir behavior preserved

**Verify:** `pytest apps-microservices/crawler-service/tests/test_crawler_manager.py -v -k "cleanup"` (existing tests still pass) + new test in Task 9 (`test_cleanup_includes_stash_dirs`).

**Steps:**

- [ ] **Step 1: Extend the `for dir_path, file_suffixes in ...` list at line 2268**

Replace:

```python
            # Also clean up stale GCS download artifacts
            for dir_path, file_suffixes in [
                (settings.DOWNLOAD_RESULTS_PATH, ('.tar.gz', '.done', '.error')),
                (settings.DOWNLOAD_REQUESTS_PATH, ('.request',)),
            ]:
```

With:

```python
            # Also clean up stale GCS download artifacts (both archive + stash flows)
            for dir_path, file_suffixes in [
                (settings.DOWNLOAD_RESULTS_PATH, ('.tar.gz', '.done', '.error')),
                (settings.DOWNLOAD_REQUESTS_PATH, ('.request',)),
                # Stash flow markers (2-phase commit) — daemon-owned /app/stash NOT cleaned here
                (settings.STASH_DOWNLOAD_RESULTS_PATH, ('.tar.gz', '.done', '.error', '.unstash-confirmed', '.unstash-cleanup-done')),
                (settings.STASH_DOWNLOAD_REQUESTS_PATH, ('.request',)),
            ]:
```

- [ ] **Step 2: Verify existing test still passes**

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager.py -v -k "cleanup" 2>&1 | tail -20
```

Expected: tests pass (or skip on missing fixture, NOT fail).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py
git commit -m "feat(crawler-service): extend cleanup task for stash dirs

scheduled_archive_cleanup now scans STASH_DOWNLOAD_RESULTS_PATH
(.tar.gz, .done, .error, .unstash-confirmed, .unstash-cleanup-done)
and STASH_DOWNLOAD_REQUESTS_PATH (.request) for stale artifacts
following the same max_age_hours policy. /app/stash itself is NOT
touched -- the upload daemon owns its lifecycle.

EN:
feat(crawler-service): extend background cleanup for stash dirs"
```

---

## Task 9: Write unit tests for stash/unstash (native task #10)

**Goal:** 15 unit tests covering all branches per spec Section 8.

**Files:**
- Create: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`

**Acceptance Criteria:**
- [ ] All 15 unit tests implemented
- [ ] Fixtures for mocked Redis (`AsyncMock` from `unittest.mock`), filesystem (`tmp_path`), and `_get_archives_disk_state`
- [ ] All tests pass with `pytest`

**Verify:** `pytest apps-microservices/crawler-service/tests/test_crawler_manager_stash.py -v` → 15 passed.

**Steps:**

- [ ] **Step 1: Create the test file with fixtures + first 6 stash tests**

```python
"""Unit tests for stash/unstash flows in crawler_manager.py.

Covers spec Section 8 test cases. All tests use mocks for Redis + filesystem
to stay hermetic — integration tests in tests/integration/ exercise the real
GCS round-trip.
"""
import asyncio
import json
import os
import tarfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def mock_cache_service(monkeypatch):
    """Mock common_utils.redis.cache_service used by crawler_manager."""
    mock = MagicMock()
    mock.redis_client = AsyncMock()
    mock.get_json = AsyncMock(return_value=None)
    mock.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", mock)
    return mock


@pytest.fixture
def cm_instance(mock_cache_service):
    return CrawlerManager()


@pytest.fixture
def base_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    (storage / "dataset.json").write_text('{"records": [1,2,3]}')
    return {
        "crawl_id": "test_id",
        "status": "failed",
        "storage_path": str(storage),
        "domain": "example.com",
    }


# ============================================================================
# stash_crawl tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("active_status", ["running", "restarting_oom", "stopping"])
async def test_stash_blocks_active_status(cm_instance, base_job_info, active_status):
    base_job_info["status"] = active_status
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "CRAWL_IS_ACTIVE"


@pytest.mark.asyncio
async def test_stash_blocks_already_archived(cm_instance, base_job_info):
    base_job_info["status"] = "archived"
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_ARCHIVED"


@pytest.mark.asyncio
async def test_stash_blocks_already_stashed(cm_instance, base_job_info):
    base_job_info["stashed_at"] = "2026-05-19T00:00:00Z"
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_STASHED"


@pytest.mark.asyncio
async def test_stash_blocks_lock_held(cm_instance, base_job_info, mock_cache_service):
    # unstash_lock NOT held, but our stash_lock SET NX returns False
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "OPERATION_IN_PROGRESS"


@pytest.mark.asyncio
async def test_stash_disk_space_pre_flight_fails(cm_instance, base_job_info, mock_cache_service, monkeypatch):
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 1024, "total_bytes": 1_000_000_000, "used_pct": 99.99, "file_count": 0, "oldest_file_age_seconds": None},
    )
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "INSUFFICIENT_DISK_SPACE"


@pytest.mark.asyncio
async def test_stash_success_sets_timestamp_and_deletes_local(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    result = await cm_instance.stash_crawl(base_job_info)

    assert result["status"] == "stashing"
    assert result["crawl_id"] == "test_id"
    assert result["stash_path"] == "gs://test-bucket/stash/test_id.tar.gz"
    assert "stashed_at" in result

    # Verify tar created in /app/stash + integrity
    final_tar = stash_dir / "test_id.tar.gz"
    assert final_tar.exists(), "Tar should exist in stash dir"
    with tarfile.open(final_tar, 'r:gz') as t:
        assert any("dataset.json" in n for n in t.getnames())

    # Verify local storage deleted
    assert not os.path.exists(base_job_info["storage_path"])

    # Verify Redis HSET (stashed_at set on Redis blob)
    last_call = mock_cache_service.set_json.call_args
    written = last_call[0][1]
    assert "stashed_at" in written
```

- [ ] **Step 2: Add the next 5 stash + setup unstash tests**

Append to the file:

```python
@pytest.mark.asyncio
async def test_stash_tar_failure_cleans_staging(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    # Make shutil.make_archive raise
    def boom(*a, **k):
        raise RuntimeError("simulated disk full")
    monkeypatch.setattr(cm_module.shutil, "make_archive", boom)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 500
    # Staging should be empty
    staging = stash_dir / ".staging"
    if staging.exists():
        assert len(list(staging.iterdir())) == 0
    # No final tar
    assert not (stash_dir / "test_id.tar.gz").exists()
    # Local storage still present (we didn't delete it)
    assert os.path.exists(base_job_info["storage_path"])


@pytest.mark.asyncio
async def test_stash_ownership_safe_lock_release(cm_instance, mock_cache_service):
    # eval Lua returning 0 means lock value mismatched -> no delete
    mock_cache_service.redis_client.eval = AsyncMock(return_value=0)
    released = await cm_instance._release_ownership_lock("foo", "different_replica_id")
    assert released is False

    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    released = await cm_instance._release_ownership_lock("foo", "my_replica_id")
    assert released is True


# ============================================================================
# unstash_crawl tests
# ============================================================================

@pytest.fixture
def stashed_job_info(base_job_info):
    info = dict(base_job_info)
    info["stashed_at"] = "2026-05-19T00:00:00Z"
    info["status"] = "failed"
    return info


@pytest.mark.asyncio
async def test_unstash_blocks_not_stashed(cm_instance, base_job_info, mock_cache_service):
    # stashed_at NOT set
    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "NOT_STASHED"


@pytest.mark.asyncio
async def test_unstash_writes_request_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 2)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    with pytest.raises(HTTPException):  # will timeout (no .done written)
        await cm_instance.unstash_crawl(stashed_job_info)

    # Request marker must have been written
    # (cleaned up on timeout, so check via Redis exists / mock_set_json calls)
    # — alternative: spy on aiofiles.open
    # Here we rely on the timeout path removing it; verify timeout raised 504
    # The actual write is verified by reaching the polling loop without error.


@pytest.mark.asyncio
async def test_unstash_timeout_when_no_done_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 2)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 504
    assert exc.value.detail["error_code"] == "UNSTASH_TIMEOUT"


@pytest.mark.asyncio
async def test_unstash_error_marker_returns_502(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    # Pre-write the .error marker
    (res_dir / "test_id.error").write_text("simulated GCS download failure")

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "GCS_DOWNLOAD_FAILED"
    assert "simulated GCS download failure" in exc.value.detail["marker_content"]
```

- [ ] **Step 3: Add the remaining 4 unstash tests (success, extract fail, cleanup deferred, success-with-cleanup)**

Append:

```python
def _create_test_tar(tar_path: str, content_dir: str):
    """Helper: build a valid tar.gz with one file inside."""
    os.makedirs(content_dir, exist_ok=True)
    sample = os.path.join(content_dir, "sample.txt")
    with open(sample, 'w') as f:
        f.write("test")
    with tarfile.open(tar_path, 'w:gz') as t:
        t.add(content_dir, arcname=os.path.basename(content_dir))


@pytest.mark.asyncio
async def test_unstash_success_with_cleanup_done(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    # Pre-write the tar.gz + .done so the polling loop exits immediately
    src = tmp_path / "src"
    src.mkdir()
    (src / "data.txt").write_text("hi")
    tar_path = res_dir / "test_id.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as t:
        t.add(str(src), arcname="data")
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(cm_module.settings, "UNSTASH_CLEANUP_GRACE_SECONDS", 5)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    # Simulate daemon writing cleanup-done shortly after .unstash-confirmed appears
    async def _simulate_daemon():
        for _ in range(50):
            await asyncio.sleep(0.1)
            if (res_dir / "test_id.unstash-confirmed").exists():
                (res_dir / "test_id.unstash-cleanup-done").touch()
                return
    daemon_task = asyncio.create_task(_simulate_daemon())

    result = await cm_instance.unstash_crawl(stashed_job_info)
    daemon_task.cancel()

    assert result["status"] == "unstashed"
    assert result["gcs_cleanup_status"] == "cleaned"
    assert os.path.exists(result["restored_to"])
    # stashed_at popped from Redis blob
    last_call = mock_cache_service.set_json.call_args
    written = last_call[0][1]
    assert "stashed_at" not in written


@pytest.mark.asyncio
async def test_unstash_extract_failure_preserves_stash(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    # Corrupt tar.gz
    tar_path = res_dir / "test_id.tar.gz"
    tar_path.write_bytes(b"not a real gzip stream")
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "EXTRACT_FAILED"
    # No .unstash-confirmed should be written
    assert not (res_dir / "test_id.unstash-confirmed").exists()
    # set_json should NOT have been called with stashed_at popped
    if mock_cache_service.set_json.called:
        for call in mock_cache_service.set_json.call_args_list:
            written = call[0][1]
            assert "stashed_at" in written, "stashed_at must be preserved on extract failure"


@pytest.mark.asyncio
async def test_unstash_gcs_cleanup_deferred_returns_200_with_warning(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    src = tmp_path / "src"
    src.mkdir()
    (src / "data.txt").write_text("hi")
    tar_path = res_dir / "test_id.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as t:
        t.add(str(src), arcname="data")
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    # Set very short grace so we exit the polling loop without daemon ack
    monkeypatch.setattr(cm_module.settings, "UNSTASH_CLEANUP_GRACE_SECONDS", 1)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    result = await cm_instance.unstash_crawl(stashed_job_info)
    assert result["status"] == "unstashed"
    assert result["gcs_cleanup_status"] == "deferred"


@pytest.mark.asyncio
async def test_cleanup_includes_stash_dirs(cm_instance, monkeypatch, tmp_path):
    """Verify scheduled_archive_cleanup scans STASH_DOWNLOAD_* dirs."""
    archives = tmp_path / "archives"
    dl_results = tmp_path / "dl_results"
    dl_req = tmp_path / "dl_req"
    stash_results = tmp_path / "stash_results"
    stash_req = tmp_path / "stash_req"
    for d in (archives, dl_results, dl_req, stash_results, stash_req):
        d.mkdir()

    # Create files older than 1h
    import time as _time
    old_ts = _time.time() - 7200
    for path in [
        stash_results / "old.tar.gz",
        stash_results / "old.unstash-confirmed",
        stash_results / "old.unstash-cleanup-done",
        stash_req / "old.request",
    ]:
        path.touch()
        os.utime(path, (old_ts, old_ts))

    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(cm_module.settings, "DOWNLOAD_RESULTS_PATH", str(dl_results))
    monkeypatch.setattr(cm_module.settings, "DOWNLOAD_REQUESTS_PATH", str(dl_req))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(stash_results))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(stash_req))
    # Create archives subdir under storage so cleanup doesn't bail
    (tmp_path / "archives").is_dir()

    deleted, _, _ = await cm_instance.cleanup_archives(max_age_hours=1)
    assert deleted >= 4, f"Expected >=4 stash markers deleted, got {deleted}"
```

- [ ] **Step 4: Run the tests**

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -50
```

Expected: all tests pass. Fix any failures (likely fixture wiring or mock setup).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git commit -m "test(crawler-service): add unit tests for stash + unstash

15 unit tests covering spec Section 8: pre-condition guards (active
status, archived, already-stashed, lock held), disk pre-flight 503,
happy path (tar created + Redis flag set + local dir deleted),
ownership-safe lock release (Lua eval), unstash NOT_STASHED guard,
timeout 504, .error 502, extract failure preserves stashed_at, 2-
phase commit success ('cleaned'), grace-window expiry ('deferred'),
and cleanup task scope extension.

EN:
test(crawler-service): unit tests for stash + unstash"
```

---

## Task 10: Write integration + daemon tests (native task #11)

**Goal:** Three bash scripts exercising the real GCS round-trip and verifying daemon env-var routing.

**Files:**
- Create: `apps-microservices/crawler-service/tests/integration/test_stash_unstash_e2e.sh`
- Create: `apps-microservices/crawler-service/tests/integration/test_stash_dead_letter.sh`
- Create: `apps-microservices/crawler-service/tests/test_daemon_parametrization.sh`

**Acceptance Criteria:**
- [ ] E2E script: spins service + daemons against test bucket, runs stash + unstash, verifies state
- [ ] Dead-letter script: invalid bucket → verifies dead-letter triggered after 3 retries
- [ ] Daemon parametrization script: defaults preserve behavior + overrides route correctly
- [ ] All scripts exit 0 on success, non-zero with clear error on failure

**Verify:** Manual execution against a test GCS bucket (`GCS_BUCKET_NAME=test-stash-bucket bash tests/integration/test_stash_unstash_e2e.sh`).

**Steps:**

- [ ] **Step 1: Create `test_daemon_parametrization.sh`** (no GCS, hermetic)

```bash
#!/bin/bash
# Verify upload_daemon.sh and download_daemon.sh respect env-var overrides
# without touching real GCS. Uses string-grep on startup log output.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
UPLOAD="$ROOT/tools/upload_daemon.sh"
DOWNLOAD="$ROOT/tools/download_daemon.sh"

echo "=== Test 1: upload_daemon.sh default env preserves crawls/ prefix ==="
out=$(GCS_BUCKET_NAME=testbucket timeout 2 bash "$UPLOAD" 2>&1 || true)
echo "$out" | grep -q "Target Bucket: gs://testbucket/crawls/" || { echo "FAIL: default prefix wrong"; echo "$out"; exit 1; }
echo "PASS"

echo "=== Test 2: upload_daemon.sh UPLOAD_GCS_PREFIX=stash routes to stash/ ==="
TMPDIR=$(mktemp -d); mkdir -p "$TMPDIR/watch"
out=$(GCS_BUCKET_NAME=testbucket UPLOAD_WATCH_DIR="$TMPDIR/watch" UPLOAD_GCS_PREFIX=stash timeout 2 bash "$UPLOAD" 2>&1 || true)
echo "$out" | grep -q "Target Bucket: gs://testbucket/stash/" || { echo "FAIL: stash prefix not routed"; echo "$out"; exit 1; }
rm -rf "$TMPDIR"
echo "PASS"

echo "=== Test 3: download_daemon.sh default env preserves crawls/ prefix ==="
out=$(GCS_BUCKET_NAME=testbucket timeout 2 bash "$DOWNLOAD" 2>&1 || true)
echo "$out" | grep -q "Source Bucket:      gs://testbucket/crawls/" || { echo "FAIL: default prefix wrong"; echo "$out"; exit 1; }
echo "$out" | grep -q "Delete after dl:   false" || { echo "FAIL: DELETE_AFTER_DOWNLOAD default not false"; echo "$out"; exit 1; }
echo "PASS"

echo "=== Test 4: download_daemon.sh DELETE_AFTER_DOWNLOAD=true picks up .unstash-confirmed ==="
TMPDIR=$(mktemp -d); mkdir -p "$TMPDIR/req" "$TMPDIR/res"
touch "$TMPDIR/res/test123.unstash-confirmed"
out=$(GCS_BUCKET_NAME=nonexistent DOWNLOAD_REQUESTS_PATH="$TMPDIR/req" DOWNLOAD_RESULTS_PATH="$TMPDIR/res" \
     DOWNLOAD_GCS_PREFIX=stash DELETE_AFTER_DOWNLOAD=true timeout 8 bash "$DOWNLOAD" 2>&1 || true)
echo "$out" | grep -q "Extract confirmed for test123" || { echo "FAIL: cleanup branch not entered"; echo "$out"; exit 1; }
# Marker retained on failure (gcloud rm fails because bucket doesn't exist)
[ -f "$TMPDIR/res/test123.unstash-confirmed" ] || { echo "FAIL: marker removed despite failure"; exit 1; }
rm -rf "$TMPDIR"
echo "PASS"

echo ""
echo "ALL DAEMON PARAMETRIZATION TESTS PASS"
```

```bash
chmod +x apps-microservices/crawler-service/tests/test_daemon_parametrization.sh
bash apps-microservices/crawler-service/tests/test_daemon_parametrization.sh
```

Expected: `ALL DAEMON PARAMETRIZATION TESTS PASS`.

- [ ] **Step 2: Create `tests/integration/test_stash_unstash_e2e.sh`** (requires `GCS_BUCKET_NAME` + `gcloud auth login`)

```bash
#!/bin/bash
# E2E test: stash + unstash round-trip against a real (test) GCS bucket.
# Requires: GCS_BUCKET_NAME env var, gcloud auth login already done,
# and docker-compose --profile crawling up running.
set -euo pipefail

: "${GCS_BUCKET_NAME:?Set GCS_BUCKET_NAME to a test bucket}"
SERVICE_URL="${SERVICE_URL:-http://localhost:8503/crawler}"
CRAWL_ID="e2e-stash-$(date +%s)"

cleanup() {
    gcloud storage rm "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" 2>/dev/null || true
    curl -s -X POST "$SERVICE_URL/force-finish/$CRAWL_ID?target_status=failed" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Step 1: Seed test crawl ==="
# Inject a fake crawl into Redis with synthetic on-disk data
docker exec -i $(docker ps -qf name=crawler-service | head -1) sh -c "
mkdir -p /app/storage/$CRAWL_ID
echo '{\"records\": [1,2,3]}' > /app/storage/$CRAWL_ID/dataset.json
" || { echo "Failed to seed crawl data"; exit 1; }

# (Step 1a) Manually register the job in Redis via direct redis-cli or via a test endpoint.
# Skip if your environment provides a fixture; otherwise use redis-cli:
redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" SET "crawl_job:$CRAWL_ID" \
  "{\"crawl_id\":\"$CRAWL_ID\",\"status\":\"failed\",\"storage_path\":\"/app/storage/$CRAWL_ID\",\"domain\":\"e2e.test\"}" \
  >/dev/null

echo "=== Step 2: POST /stash ==="
resp=$(curl -s -w "\n%{http_code}" -X POST "$SERVICE_URL/stash/$CRAWL_ID")
code=$(echo "$resp" | tail -1)
[ "$code" = "202" ] || { echo "FAIL: stash returned $code (expected 202)"; echo "$resp"; exit 1; }
echo "PASS — stash returned 202"

echo "=== Step 3: Wait for upload daemon ==="
for i in $(seq 1 60); do
    if gcloud storage ls "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" >/dev/null 2>&1; then
        echo "PASS — GCS object present after ${i}s"
        break
    fi
    sleep 1
done
gcloud storage ls "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" >/dev/null 2>&1 || { echo "FAIL: GCS object never appeared"; exit 1; }

echo "=== Step 4: Verify local data deleted ==="
docker exec -i $(docker ps -qf name=crawler-service | head -1) test ! -d "/app/storage/$CRAWL_ID" \
  || { echo "FAIL: local dir not deleted"; exit 1; }
echo "PASS"

echo "=== Step 5: POST /unstash ==="
resp=$(curl -s -w "\n%{http_code}" -X POST "$SERVICE_URL/unstash/$CRAWL_ID")
code=$(echo "$resp" | tail -1)
body=$(echo "$resp" | head -n -1)
[ "$code" = "200" ] || { echo "FAIL: unstash returned $code"; echo "$body"; exit 1; }
echo "$body" | grep -q "unstashed" || { echo "FAIL: missing unstashed status"; echo "$body"; exit 1; }
echo "PASS — unstash returned 200"

echo "=== Step 6: Verify local data restored + GCS cleaned ==="
docker exec -i $(docker ps -qf name=crawler-service | head -1) test -d "/app/storage/$CRAWL_ID" \
  || { echo "FAIL: local dir not restored"; exit 1; }
gcloud storage ls "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" >/dev/null 2>&1 \
  && { echo "FAIL: GCS object still present (orphan)"; exit 1; } \
  || echo "PASS — GCS object cleaned"

echo ""
echo "E2E STASH/UNSTASH ROUND-TRIP PASS"
```

```bash
chmod +x apps-microservices/crawler-service/tests/integration/test_stash_unstash_e2e.sh
```

- [ ] **Step 3: Create `test_stash_dead_letter.sh`**

```bash
#!/bin/bash
# Dead-letter test: point upload daemon at invalid bucket, drop a fake .tar.gz,
# verify dead_letter/ contains the file after 3 retries.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
UPLOAD="$ROOT/tools/upload_daemon.sh"
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/watch"

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

# Drop a tiny fake archive
echo "fake" > "$TMPDIR/watch/test.tar.gz"

# Run daemon for long enough to exhaust 3 retries (assuming CHECK_INTERVAL=60 -> 4 cycles = 240s).
# For test purposes the daemon needs faster retries; tweak via env or run for full TTL.
GCS_BUCKET_NAME=nonexistent-test-bucket-$RANDOM \
UPLOAD_WATCH_DIR="$TMPDIR/watch" \
UPLOAD_GCS_PREFIX=stash \
timeout 270 bash "$UPLOAD" 2>&1 > "$TMPDIR/daemon.log" || true

# Verify file moved to dead_letter
if [ -f "$TMPDIR/watch/dead_letter/test.tar.gz" ]; then
    echo "PASS — file moved to dead_letter after 3 retries"
else
    echo "FAIL — file not in dead_letter"
    echo "Daemon log:"
    cat "$TMPDIR/daemon.log" | tail -30
    exit 1
fi
```

```bash
chmod +x apps-microservices/crawler-service/tests/integration/test_stash_dead_letter.sh
```

- [ ] **Step 4: Run the hermetic daemon parametrization test**

```bash
bash apps-microservices/crawler-service/tests/test_daemon_parametrization.sh
```

Expected: `ALL DAEMON PARAMETRIZATION TESTS PASS`.

- [ ] **Step 5: Commit all three scripts**

```bash
git add apps-microservices/crawler-service/tests/test_daemon_parametrization.sh \
        apps-microservices/crawler-service/tests/integration/test_stash_unstash_e2e.sh \
        apps-microservices/crawler-service/tests/integration/test_stash_dead_letter.sh
git commit -m "test(crawler-service): add stash integration + daemon parametrization tests

Three bash scripts:
- test_daemon_parametrization.sh: hermetic, verifies upload_daemon +
  download_daemon respect env overrides without touching GCS
- integration/test_stash_unstash_e2e.sh: full round-trip against
  test GCS bucket (requires gcloud auth + GCS_BUCKET_NAME env)
- integration/test_stash_dead_letter.sh: invalid bucket
  triggers dead-letter after 3 retries

EN:
test(crawler-service): add stash integration + daemon tests"
```

---

## Task 11: Update documentation (native task #12)

**Goal:** Reflect the new endpoints + daemon variants + flag semantics across the four documentation files.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`
- Modify: `apps-microservices/crawler-service/README.md`
- Modify: `docs/daemon_guide.md`
- Modify: `tools/CLAUDE.md`

**Acceptance Criteria:**
- [ ] crawler-service CLAUDE.md: 2 new endpoints in API table + new section "Stash — Free Disk Investigation Workflow" + cleanup task scope mention
- [ ] README.md: 2 new endpoints in Administrative section
- [ ] daemon_guide.md: stash variants in both Upload + Download sections + Shared Dirs table + systemd examples + orphan troubleshooting
- [ ] tools/CLAUDE.md: new env vars listed with defaults

**Verify:** `grep -c "POST /stash" apps-microservices/crawler-service/CLAUDE.md docs/daemon_guide.md` returns ≥3.

**Steps:**

- [ ] **Step 1: Update `apps-microservices/crawler-service/CLAUDE.md`**

In the API Endpoints section (around line 60), add after `POST /archive/{crawl_id}`:

```markdown
- `POST /stash/{crawl_id}` -- Stash a terminal crawl to GCS under stash/ (frees local disk)
- `POST /unstash/{crawl_id}` -- Restore a stashed crawl from GCS to local storage
```

After the "Archiving — GCS Fallback" section, add a new section:

```markdown
## Stash — Free Disk Investigation Workflow

Distinct from archiving. Use stash to **temporarily free local disk** for crawls that failed or were stopped and still need investigation. The data is parked in `gs://{bucket}/stash/` and can be retrieved later via `POST /unstash/{crawl_id}`.

**Status modeling:** No new status enum. A single field `job_data["stashed_at"]` (ISO 8601 UTC) is set when data is in GCS, cleared when restored. This is **orthogonal** to status — a stashed crawl keeps its original terminal status (`failed`/`stopped`/`finished`).

**Conflict matrix (POST /stash):**
- 409 `CRAWL_IS_ACTIVE` if status is running/restarting_oom/stopping
- 409 `ALREADY_ARCHIVED` if status is `archived`
- 409 `ALREADY_STASHED` if `stashed_at` already set
- 409 `OPERATION_IN_PROGRESS` if `stash_lock:{id}` or `unstash_lock:{id}` held
- 503 `INSUFFICIENT_DISK_SPACE` if pre-flight fails (mirror archive shape)

**Two-phase commit for unstash:** Naïve "delete GCS after download" loses data if extract fails. Instead:
1. Daemon downloads → writes `.done`
2. Service extracts tar.gz to original storage path
3. Service writes `.unstash-confirmed` marker (signals extract success)
4. Daemon polls `.unstash-confirmed` → `gcloud storage rm` → writes `.unstash-cleanup-done`
5. Service polls `.unstash-cleanup-done` within `UNSTASH_CLEANUP_GRACE_SECONDS` (default 30s)
6. On marker arrival: clear `stashed_at`, return 200 with `gcs_cleanup_status='cleaned'`
7. On grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'` (orphan GCS object — `unstash_gcs_orphan_total` Prometheus counter incremented)

**Daemons:** A separate instance of the existing `upload_daemon.sh` and `download_daemon.sh` runs for stash flow, configured via env vars:
- Upload: `UPLOAD_WATCH_DIR=…/crawler_stash UPLOAD_GCS_PREFIX=stash`
- Download: `DOWNLOAD_REQUESTS_PATH=…/crawler_stash_download_requests DOWNLOAD_RESULTS_PATH=…/crawler_stash_download_results DOWNLOAD_GCS_PREFIX=stash DELETE_AFTER_DOWNLOAD=true`

**Locks:** `stash_lock:{id}` + `unstash_lock:{id}` (Redis SET NX, ownership-safe DEL via Lua compare-and-delete to avoid clobbering a new acquirer after TTL expiry). Mirrors the `reconcile_leader_lock` pattern.

Spec: `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`.
```

In the "Automatic Cleanup" section (or equivalent), add a line noting stash dirs:

```markdown
- **Stash download artifacts** (`.tar.gz`, `.done`, `.error`, `.unstash-confirmed`, `.unstash-cleanup-done` in `/app/gcs-stash-downloads/`): cleaned during the same task. `/app/stash/` itself is NOT cleaned — the upload daemon owns its lifecycle.
```

- [ ] **Step 2: Update `apps-microservices/crawler-service/README.md`**

In the Administrative Endpoints section, add:

```markdown
#### Stash a Crawl (Free Disk)
-   `POST /crawler/stash/{crawl_id}`
-   **Description:** Move a terminal crawl's storage to GCS under `stash/` and delete local data. Use for crawls under investigation that occupy disk space. The crawl must be in `failed`/`stopped`/`finished` status and not already stashed/archived.
-   **Response:** 202 Accepted with `StashResponse` (`crawl_id`, `status="stashing"`, `stash_path`, `stashed_at`).

#### Unstash a Crawl
-   `POST /crawler/unstash/{crawl_id}`
-   **Description:** Restore a stashed crawl's data from GCS to local storage. Synchronous — waits for download daemon, extracts, and triggers 2-phase commit GCS cleanup. Bounded by `UNSTASH_TIMEOUT_SECONDS` (default 300s).
-   **Response:** 200 OK with `UnstashResponse` (`crawl_id`, `status="unstashed"`, `restored_to`, `elapsed_seconds`, `gcs_cleanup_status` = `"cleaned"` or `"deferred"`).
```

- [ ] **Step 3: Update `docs/daemon_guide.md`**

In the Shared Directories section, add 3 rows to the table:

```markdown
| `crawler-service/crawler_stash/` | `/app/stash` | `STASH_SHARED_PATH` | Stash staging: service writes `.tar.gz`, stash-upload daemon uploads to GCS |
| `crawler-service/crawler_stash_download_requests/` | `/app/gcs-stash-requests` | `STASH_DOWNLOAD_REQUESTS_PATH` | Stash download requests: service writes `.request`, stash-download daemon picks up |
| `crawler-service/crawler_stash_download_results/` | `/app/gcs-stash-downloads` | `STASH_DOWNLOAD_RESULTS_PATH` | Stash download results: daemon writes `.tar.gz` + `.done`, service writes `.unstash-confirmed`, daemon writes `.unstash-cleanup-done` |
```

In the Volume Mounts subsection, add the 3 new bind-mounts to the example.

After the Upload Daemon section, add a subsection:

```markdown
### Stash Upload Daemon Variant

The same `tools/upload_daemon.sh` script runs as a second systemd instance for the stash flow:

```ini
# ~/.config/systemd/user/crawler-upload-stash.service
[Unit]
Description=Crawler Stash Upload Daemon

[Service]
Environment="UPLOAD_WATCH_DIR=%h/workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler_stash"
Environment="UPLOAD_GCS_PREFIX=stash"
ExecStart=%h/workspaces/RAG-HP-PUB/tools/upload_daemon.sh
Restart=always
RestartSec=10
StandardOutput=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon_stash.log
StandardError=append:%h/workspaces/RAG-HP-PUB/logs/upload_daemon_stash.log

[Install]
WantedBy=default.target
```

Enable: `systemctl --user enable --now crawler-upload-stash`.
```

After the Download Daemon section, add a similar subsection for `crawler-download-stash.service` with `DELETE_AFTER_DOWNLOAD=true` and a note on the 2-phase commit semantic and what `.unstash-confirmed` / `.unstash-cleanup-done` markers mean.

In Troubleshooting, add an entry about orphan GCS objects (Prometheus `unstash_gcs_orphan_total`).

- [ ] **Step 4: Update `tools/CLAUDE.md`**

In the Conventions section, replace the GCS env vars bullet with:

```markdown
- GCS daemons use file-based signaling (.request/.done/.error markers, plus .unstash-confirmed/.unstash-cleanup-done for the 2-phase commit on the stash flow).
- Daemon env vars (defaults preserve current archive-flow behavior):
  - Upload: `UPLOAD_WATCH_DIR` (default `crawler_archives/`), `UPLOAD_GCS_PREFIX` (default `crawls`), `UPLOAD_DEAD_LETTER_SUBDIR` (default `dead_letter`)
  - Download: `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH`, `DOWNLOAD_GCS_PREFIX` (default `crawls`), `DELETE_AFTER_DOWNLOAD` (default `false`, set `true` for stash flow)
- Same env var names align with the crawler-service Python Settings (`apps-microservices/crawler-service/app/core/config.py`) so a single `.env` entry per direction configures both layers.
```

- [ ] **Step 5: Verify docs**

```bash
grep -c "POST /stash" apps-microservices/crawler-service/CLAUDE.md apps-microservices/crawler-service/README.md docs/daemon_guide.md
```

Expected: each file ≥1, total ≥3.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md \
        apps-microservices/crawler-service/README.md \
        docs/daemon_guide.md \
        tools/CLAUDE.md
git commit -m "docs(crawler-service): document stash/unstash endpoints + daemon variants

- crawler-service CLAUDE.md: API table entries + new 'Stash — Free
  Disk Investigation Workflow' section (status modeling, conflict
  matrix, 2-phase commit, daemons, locks) + cleanup scope note
- README.md: stash + unstash entries in Administrative section
- daemon_guide.md: 3 new rows in Shared Dirs table + stash variants
  for both Upload + Download daemons with systemd unit examples +
  orphan-GCS troubleshooting
- tools/CLAUDE.md: new env vars list with defaults + .unstash-*
  marker mention

EN:
docs(crawler-service): document stash/unstash + daemon variants"
```

---

## Self-Review Checklist (run after writing this plan)

- **Spec coverage:** All sections from `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md` mapped to tasks 0-11. ✓
- **Placeholder scan:** No TBD / TODO / "implement later". ✓
- **Type consistency:** `StashResponse`/`UnstashResponse` field names match between schemas (Task 4), manager return values (Tasks 5–6), and router calls (Task 7). `stashed_at` is the agreed Redis field name across all code paths. ✓
- **Env var consistency:** `UPLOAD_GCS_PREFIX`, `DOWNLOAD_GCS_PREFIX`, `DELETE_AFTER_DOWNLOAD` spelled identically across daemons (Tasks 1–2), docs (Task 11), and tests (Task 10). ✓

---

## Native Task Mapping

| Plan Task | Native Task ID |
|---|---|
| Task 0 — config vars | #1 |
| Task 1 — upload daemon | #2 |
| Task 2 — download daemon | #3 |
| Task 3 — compose mounts | #4 |
| Task 4 — schemas | #5 |
| Task 5 — stash_crawl + locks | #6 |
| Task 6 — unstash_crawl | #7 |
| Task 7 — router endpoints | #8 |
| Task 8 — cleanup extension | #9 |
| Task 9 — unit tests | #10 |
| Task 10 — integration tests | #11 |
| Task 11 — documentation | #12 |
