# crawler-service

Scalable web crawling service with FastAPI orchestrator and Node.js/Crawlee crawler engine.

## Tech Stack

- **Orchestrator:** Python 3.x, FastAPI, Uvicorn
- **Crawler Engine:** Node.js 22, TypeScript, Crawlee 3, Playwright 1.56.1
- **Browser:** Playwright (Chromium) + Camoufox (Firefox) for stealth
- **State:** Redis (job tracking, heartbeats, counters)
- **Shared lib:** `common-utils` (Python)

## Commands

### Python (orchestrator)
| Action | Command |
|--------|---------|
| Run | `uvicorn main:app --host 0.0.0.0 --port 8503` |
| Deps | `pip install -r requirements.txt` |

### Crawler (`crawler/`)
| Action | Command |
|--------|---------|
| Build | `npm run build` (tsc) |
| Dev | `npm run dev` (tsx) |
| Start | `npm run start` (node dist/main.js) |

## Docker

Multi-stage build (Node.js 22 + Playwright). Port **8503**. `NODE_OPTIONS="--max-old-space-size=5000 --expose-gc"`.

## Folder Structure

```
main.py                  # FastAPI app, startup/shutdown, background tasks
app/
  router/
    crawler.py           # Crawler REST endpoints
    migration.py         # Temporary migration routes
  core/
    config.py            # Settings (env vars)
    crawler_manager.py   # Job lifecycle management
  schemas/
    crawler.py           # Pydantic request/response models
    migration.py
crawler/
  src/
    main.ts              # Crawlee entry point
    routes.ts            # Playwright route handlers
    functions.ts         # Utility functions
    context.ts           # Crawlee context setup
    class/               # StatsManager, DedupManager, JsonlWriter, etc.
    interfaces/
  package.json, tsconfig.json
tests/
requirements.txt
```

## API Endpoints

- `POST /start` -- Start or resume a crawl job
- `POST /stop/{crawl_id}` -- Stop a running crawl
- `POST /force-finish/{crawl_id}` -- Force a stuck job to terminal state
- `GET /status` -- List all jobs (optional `?status=` filter)
- `GET /status/{crawl_id}` -- Single job status
- `GET /results/{crawl_id}` -- Download crawl results archive
- `GET /capacity` -- Current running/max capacity
- `POST /archive/{crawl_id}` -- Archive finished job to GCS
- `POST /stash/{crawl_id}` -- Stash a terminal crawl to GCS under stash/ (frees local disk)
- `POST /unstash/{crawl_id}` -- Restore a stashed crawl from GCS to local storage
- `POST /reindex-storage` -- Re-index orphaned jobs from disk
- `POST /reconcile-jobs` -- Fix counter drift
- `POST /prune-archives` -- Clean up old archives

## Update Mode (Archived Previous Crawl Handling)

When `crawl_mode=update`, the service validates and restores data from the previous crawl:

1. **Pre-flight validation** (`start_crawl`): Checks `previous_crawl_id` exists, is not `failed`, and has dataset files on disk.
2. **Auto-restore from GCS** (`_restore_archived_crawl`): If previous crawl is `archived` (data deleted), downloads the archive from GCS via the download daemon and extracts it. Uses a Redis lock (`restore_lock:{id}`) to prevent concurrent restorations.
3. **Node.js safety net** (`main.ts`): If URL consolidation produces 0 URLs in update mode, exits with code 4 (mapped to failure webhook).
4. **Post-crawl cleanup** (`_monitor_process`): Deletes restored data for archived previous crawls after the update crawl completes.

## Regional Path Exclusion

Prevents crawling duplicate French regional variants (e.g., `/fr-BE/`, `/fr-CA/`) when one French path (e.g., `/fr-FR/`) has been selected.

**How it works:**
1. Homepage detection (mode `"complete"`) returns `alternative_urls` with all French regional variants found via hreflang tags.
2. The crawler extracts path prefixes from alternatives, excludes the winner's prefix, and stores the rest in `context.excludedRegionalPaths`.
3. In **standard mode**, `transformRequestFunction` blocks discovered links matching excluded prefixes.
4. In **update mode**, two-phase seeding processes the homepage first, then seeds remaining URLs from the previous crawl with path filtering.

**Key files:** `context.ts` (fields), `routes.ts` (population + filtering), `main.ts` (two-phase seeding), `DetectionLangueClient.ts` (helpers).

**Limitation:** Only path-based regional variants are filtered. Query-based variants (`?lang=fr-BE`) are not handled (deferred — see spec).

## Archiving — GCS Fallback

`POST /archive/{crawl_id}` checks three locations in order:
1. **Local `/app/archives/`** — if `.tar.gz` exists, skip re-generation, mark as `archived`.
2. **GCS via download daemon** — if archive was already uploaded, fix status to `archived` without re-archiving.
3. **Fresh archive** — create new `.tar.gz` from local data, mark as `archived`, upload daemon handles GCS.

The GCS fallback (step 2) handles legacy crawls stuck at `finished` due to a previous bug where `_mark_as_archived` was never called.

### Tmp file isolation via `.staging/`

Archives are first written to `/app/archives/.staging/{crawl_id}.tar.gz` and only moved to `/app/archives/{crawl_id}.tar.gz` after size and integrity checks pass. The upload daemon (`tools/upload_daemon.sh`) uses `find -maxdepth 1`, which ignores subdirectories — so it only sees completed archives.

**Do not change the daemon to scan subdirectories** without also updating the tmp file location in `_create_archive`. Otherwise the daemon will race the tmp file and cause `FileNotFoundError` during archiving.

### Pre-flight disk space check

Before creating a new archive, `archive_crawl` measures the source directory (`os.walk` + `size * 1.5` for gzip + safety margin, floored at 1 GB) and checks free space on `/app/archives/` via `shutil.disk_usage`. If free space is less than required, it responds with **503** carrying this body:

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

**Fail-open policy:** if the measurement helpers themselves raise (permissions, filesystem error), the check is skipped and archive creation proceeds. Broken measurement must never block archiving; the staging-dir `finally` block still cleans up partial files on disk-full.

Every archive attempt also logs a baseline disk state (`info`) and, on failure, a second disk state (`error`) so operational logs show the buffer pressure at both checkpoints.

Spec: `docs/superpowers/specs/2026-04-18-archive-disk-space-preflight-design.md`.

### Lock heartbeat (stash + archive)

Both `stash_crawl` and `archive_crawl` acquire a Redis lock (`stash_lock:{id}` / `archive_lock:{id}`) via the ownership-safe `_acquire_ownership_lock` / `_release_ownership_lock` pair (replica-id-tagged value + Lua CAS DEL). The tar + cleanup block is wrapped in `_LockHeartbeat`, a background asyncio task that re-runs `EXPIRE` on the lock every `LOCK_HEARTBEAT_INTERVAL_SECONDS` via Lua compare-and-set so the TTL never lapses mid-op.

Tunable settings (`app/core/config.py`):
- `STASH_LOCK_TTL_SECONDS` — default `1800`
- `ARCHIVE_LOCK_TTL_SECONDS` — default `1800`
- `UNSTASH_LOCK_TTL_SECONDS` — default `600` (unstash is time-bounded by `UNSTASH_TIMEOUT_SECONDS`)
- `LOCK_HEARTBEAT_INTERVAL_SECONDS` — default `300` (TTL / 6 → 5 missed renewals before TTL expiry)
- `LOCK_HEARTBEAT_MAX_DURATION_SECONDS` — default `14400` (4 h hard cap; past this the heartbeat stops renewing so a hung op cannot indefinitely hold the lock)

The matching nginx regex location at `apps-microservices/api-gateway-go/nginx.conf` (and the parity copy at `apps-microservices/api-gateway/nginx.conf`) sets `proxy_next_upstream off` on `/crawler/(stash|unstash|archive)/` to prevent POST retry fan-out across replicas. PHP client is the only retry layer (currently 503-only, see `3_archive_eligible_domains.php`).

Spec: `docs/superpowers/specs/2026-05-21-stash-archive-lock-heartbeat-design.md`. Incident reference: crawl 6250 on 2026-05-20.

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
7. On grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'`. Orphan GCS object is logged as `UNSTASH_GCS_ORPHAN crawl_id=… elapsed_seconds=… reason=cleanup_grace_expired gcs_path=…` for operator grep (no Prometheus counter — operational observability is log-based).

**Daemons:** A separate instance of the existing `upload_daemon.sh` and `download_daemon.sh` runs for stash flow, configured via env vars:
- Upload: `UPLOAD_WATCH_DIR=…/crawler_stash UPLOAD_GCS_PREFIX=stash`
- Download: `DOWNLOAD_REQUESTS_PATH=…/crawler_stash_download_requests DOWNLOAD_RESULTS_PATH=…/crawler_stash_download_results DOWNLOAD_GCS_PREFIX=stash DELETE_AFTER_DOWNLOAD=true`

**Locks:** `stash_lock:{id}` + `unstash_lock:{id}` (Redis SET NX, ownership-safe DEL via Lua compare-and-delete to avoid clobbering a new acquirer after TTL expiry). Mirrors the `reconcile_leader_lock` pattern. The stash tar is wrapped in `_LockHeartbeat` so the TTL is refreshed mid-op — see "Lock heartbeat (stash + archive)" under the Archiving section for tunables.

**Background cleanup:** `cleanup_archives` also sweeps stale stash download artifacts (`.tar.gz`, `.done`, `.error`, `.unstash-confirmed`, `.unstash-cleanup-done` in `/app/gcs-stash-downloads/` + `.request` in `/app/gcs-stash-requests/`). `/app/stash/` itself is NOT cleaned — the upload daemon owns its lifecycle.

Spec: `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`.

## robots.txt Blanket Block Bypass

At startup, after fetching robots.txt, the crawler checks if the site has a blanket block (`Disallow: *` or `Disallow: /`) using a multi-path probe (`isBlanketBlock` in `robotsTxtGuard.ts`). Three diverse URLs are tested against `isAllowed()` — if all are blocked, `robots` is set to `undefined`, disabling all robots.txt filtering for the crawl.

- Detection is at startup only (not runtime)
- Bypass is transparent to the caller — no webhook contract change
- `robots_txt_bypassed: true` is included in `_callback_payload.json` for observability
- Selective blocks (e.g., `Disallow: /products/`) are NOT bypassed

## Camoufox Default Browser

The crawler uses **Camoufox** (stealth Firefox with C++ anti-detection patches) as the default browser. Unlike Crawlee's built-in fingerprinting (JavaScript injection), Camoufox spoofs `navigator.webdriver`, WebGL, WebRTC, AudioContext, and screen dimensions at the browser engine level — undetectable by JS inspection.

- **Default (`camoufox: true` or omitted):** Camoufox stealth Firefox via `camoufox-js` (official Apify package)
- **Opt-out (`camoufox: false`):** Falls back to Playwright multi-browser rotation (Chrome/Firefox/Safari)
- `camoufox_used: true/false` is included in `_callback_payload.json` for observability
- **Headless mode required:** `camoufoxLaunchOptions({ headless: true })` — Camoufox defaults to `headless: false`, which crashes in Docker (no DISPLAY/X11)
- Dependency: `camoufox-js` — browser binary baked into Docker image at build time
- **Dockerfile requirement:** The Camoufox binary is fetched in Stage 1 (builder) via `npx camoufox-js fetch` and must be explicitly copied to Stage 2: `COPY --from=builder /root/.cache/camoufox /root/.cache/camoufox`

## Reconciliation Leader Election

`reconcile_jobs` runs on every replica's monitoring loop. To prevent multiple replicas from detecting the same stale job simultaneously (and each firing a duplicate failure webhook), only one replica runs the full scan at a time.

- **Lock key:** `reconcile_leader_lock` (Redis `SET NX`)
- **Lock TTL:** `RECONCILIATION_INTERVAL_SECONDS * 2` — safety margin for slow scans; auto-recovers if leader dies
- **Ownership-safe release:** the `finally` block only deletes the lock if the current Redis value equals this replica's `replica_id` — prevents a slow leader from clobbering a new leader's lock after TTL expiry
- **Architecture:** public `reconcile_jobs` is a thin wrapper around the lock; the actual scanning logic lives in `_reconcile_locked`

Complementary protections in the same fix:
- `start_crawl` writes `last_heartbeat=now()` in the initial `job_data` to close the 60-second blind window between start and the first monitor-loop heartbeat tick.
- The stale-detection local override trusts `self.local_processes` (not `replica_id` in Redis) as the authoritative source of process ownership. A replica never kills a PID it owns, regardless of what Redis reports.

Spec: `docs/superpowers/specs/2026-04-18-reconciliation-leader-election-design.md`.

## Failure Webhook Idempotency

Failure webhooks include a `request_id` UUID generated once per crawl failure and persisted in `job_data["failure_webhook_request_id"]`. PHP dedupes by this UUID so duplicate deliveries (common during shutdown + reconciliation replay) process at most once.

**Client-side (this service):**
- `_get_or_create_failure_request_id(job_info)` returns an existing UUID if present, else generates and persists one.
- The UUID is threaded through all 6 failure-webhook callsites: OOM max-restarts, OOM relaunch failure, monitor exit, force-finish, shutdown, reconciliation stale detection.
- Shutdown path uses a bounded `_send_webhook_once` (5-second timeout, no retries) via `shutdown=True`. If delivery fails, the persisted UUID lets reconciliation replay with the same identifier.
- Docker `stop_grace_period: 30s` gives the shutdown path enough headroom.

**PHP-side contract (`script_process_detect_fiche_produit.php`):**
- Read the `request_id` query parameter.
- Look up in a dedup store (Redis/MySQL/APC), TTL ≥ 24h.
- If found: return `HTTP 200` with no side effects.
- If not found: store, then process normally.
- If `request_id` is absent (legacy calls): process normally (backward compatible).

Spec: `docs/superpowers/specs/2026-04-18-webhook-idempotency-design.md`.

## Exit Codes (Node.js → Python)

| Code | Meaning | Python Behavior |
|------|---------|-----------------|
| 0 | Success | Status: `finished`, success webhook |
| 2 | Partial success | Status: `finished`, success webhook |
| 3 | OOM relaunch | Status: `restarting_oom`, auto-relaunch (up to `MAX_OOM_RESTARTS`) |
| 4 | Update mode no data | Status: `failed`, failure webhook with descriptive message |
| 5 | Redis connection lost (Node-side sustained loss) | Status: `failed`, failure webhook with `failure_cause=redis_lost` |
| 6 | Progress stall (no URL progress for threshold) | Status: `failed`, failure webhook with `failure_cause=progress_stalled` |
| Other | Failure | Status: `failed`, failure webhook |

## Redis Loss / Progress Stall Detection

The Node crawler runs two monitors that detect failure modes invisible to Python's existing stale detection:

| Monitor | Trigger | Exit code | Threshold env var |
|---------|---------|-----------|--------------------|
| `RedisHealthMonitor` (`crawler/src/class/RedisHealthMonitor.ts`) | Sustained Redis loss across all clients (heartbeat + dedup) | 5 | `REDIS_LOSS_THRESHOLD_MS` (default 60000) |
| `ProgressMonitor` (`crawler/src/class/ProgressMonitor.ts`) | No `requestsFinished` delta across stall window | 6 | `PROGRESS_STALL_THRESHOLD_MS` (default 600000) |

Both monitors call `gracefulShutdown(reason, exitCode)` on fire. Python `_monitor_process` maps the exit codes to `status=failed` and persists `failure_cause` in `job_data` via the shared `_classify_exit_code` helper. The failure webhook payload to Marketplace BO carries the same `failure_cause` field.

### `failure_cause` vocabulary

This is a cross-language contract between Python orchestrator and Marketplace BO PHP (`fonctions_scrapping.php:handle_crawler_webhook`).

| Exit code | `failure_cause` | Origin |
|-----------|-----------------|--------|
| -1 | `oom_max_restarts` | OOM restart budget exhausted by `_relaunch_oom_crawl` |
| 3 | `oom_relaunch` | Node OOM, before max-restarts reached |
| 4 | `update_mode_no_data` | Update-mode crawl produced 0 URLs |
| 5 | `redis_lost` | `RedisHealthMonitor` fired |
| 6 | `progress_stalled` | `ProgressMonitor` fired |
| 137 / -9 | `killed_oom_system` | Process killed by OOM killer (SIGKILL) |
| other negative | `signal_killed` | Killed by signal (non-OOM) |
| other positive | `unknown` | Unexpected exit code |
| (none — not from exit code) | `service_shutdown` | Orchestrator graceful shutdown |
| (none — not from exit code) | `force_finished` | Operator-triggered force-finish |
| (none — not from exit code) | `stale_detected` | Reconciliation stale detection |
| (none — not from exit code) | `oom_relaunch_failed` | `start_crawl` raised during OOM relaunch |

**Why this exists (root cause of the bug this addresses):** Python's `last_heartbeat` is a process-liveness proxy (PID alive ⇒ heartbeat fresh), not a crawl-progress proxy. Node-side Redis failures were silently swallowed at `main.ts:382` and `DedupManager.ts:13` — heartbeat publishes kept failing forever while reconciliation never fired because Python kept refreshing `last_heartbeat`. These monitors close that gap by exiting the Node process deterministically.

### Troubleshooting false positives

- `progress_stalled` on a legitimately slow domain → raise `PROGRESS_STALL_THRESHOLD_MS` per-deployment via env (e.g. `1200000` for 20 min).
- `redis_lost` during a Redis maintenance window → preferred behavior; restart the crawl after maintenance completes.
- Both thresholds validate against `NaN` and non-positive values; invalid env strings fall back to the defaults.

### Manual smoke-test playbook

1. Trigger a crawl on a test domain.
2. After 30s: `docker pause <redis-container>` (or block port 6379 outbound from the crawler container with `iptables`).
3. Watch `crawler-service` logs — expect `event: redis_lost` JSON line within ~60s.
4. Process exits 5; verify Marketplace BO `crawl_events` row has `failure_cause=redis_lost`.
5. `docker unpause <redis-container>` and trigger a fresh crawl — verify normal completion (regression check).

For `progress_stalled` testing: set `PROGRESS_STALL_THRESHOLD_MS=120000` (2 min) in compose env for the test deployment, trigger a crawl on a hanging URL, wait 2 min, expect exit code 6.

Spec: `docs/superpowers/specs/2026-05-21-redis-loss-progress-stall-detection-design.md`.
Plan: `docs/superpowers/plans/2026-05-21-redis-loss-progress-stall-detection.md`.

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

## api-detection-langue-fr Caller Contract

`DetectionLangueClient` (`crawler/src/class/DetectionLangueClient.ts`) enforces the shared caller contract for api-detection-langue-fr. Behavior controlled via env vars:

| Variable | Default | Effect |
|---|---|---|
| `DETECTION_MAX_CONCURRENCY` | `5` | `p-limit` cap on concurrent `/detect` + `/check-url` calls |
| `DETECTION_REQUEST_TIMEOUT_S` | `180` | Axios timeout (seconds × 1000 ms) |
| `DETECTION_MAX_RETRIES` | `2` | Retries on HTTP 503 only (non-503 errors raise immediately) |
| `DETECTION_BACKOFF_BASE_S` | `2` | Exponential backoff base when server omits `Retry-After` |

On HTTP 503, precedence for the retry wait time is **server `Retry-After` header > exponential backoff (`backoffBase * 2**attempt`)**. Matches the Python `common_utils.detection_client.DetectionClient` behavior so both callers hit the detection service with identical semantics.

Spec: `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`.

## Conventions

- Nginx handles path stripping; routers have no prefix. Crawler spawned as child process by `crawler_manager`.

## Dependencies

Redis (state/counters), GCS (archive + restore), `common-utils`, `api-detection-langue-fr`.
