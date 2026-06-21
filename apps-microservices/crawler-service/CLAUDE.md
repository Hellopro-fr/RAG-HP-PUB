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

## Auto-Stash Workflow

Folds the (previously operator-only) stash/unstash into the crawl lifecycle automatically. **Flag-gated: `AUTO_STASH_ENABLED` defaults `false`** — turning it on enables the sweep; the transparency hooks (below) are always active.

**Lifecycle:** a terminal crawl is stashed once it's *consumed* + a grace window, or after a long safety timeout, or under disk pressure. It stays invisibly retrievable, and graduates from stash to archive via a GCS-side move.

**Trigger — the sweep (`_reconcile_locked`):** the leader-elected reconcile loop collects terminal, non-`stashed_at`, non-`archived` crawls each tick and stashes the eligible ones via background `asyncio.create_task` (so a multi-GB tar never holds the leader lock). Eligibility (`_is_stash_eligible`, pure/fail-open):
- **grace** — `downloaded_at` set AND `now - downloaded_at ≥ STASH_GRACE_SECONDS`. Grace governs *exclusively* when `downloaded_at` is present (a just-downloaded crawl is protected even if it finished long ago).
- **timeout** — never downloaded AND `now - finished_at ≥ STASH_SAFETY_TIMEOUT_SECONDS` (this also doubles as the investigation window for failed crawls).
- **disk pressure** — when `_disk_used_pct() ≥ STASH_DISK_HIGH_WATER_PCT`, the largest terminal crawls are stashed early regardless of grace.
Capped at `STASH_MAX_PER_SWEEP` per tick; an in-flight set on the leader prevents re-selecting a crawl whose tar is still running.

**New `job_data` fields (orthogonal, cached on write):** `finished_at` (stamped at every terminal transition via `_stamp_terminal_fields`), `downloaded_at` (stamped on a successful `GET /results` serve), `size_bytes`. The sweep reads these from Redis — no per-job disk I/O in the leader-held critical section.

**Transparency (always on):**
- `GET /results` on a stashed crawl → `get_results_archive` unstashes inline, re-reads `job_info`, then serves (502 if the job vanished). Sole result-serving path.
- Update mode (`start_crawl`) → `_restore_previous_crawl` unstashes a stashed `previous_crawl_id` (the real "start → unstash, continue" path; same-ID restart does not exist). Archived previous crawls still go through `_restore_archived_crawl`.

**Stash → archive (move):** `POST /archive` on a stashed **finished** crawl → `_move_stash_to_archive` writes a `.move-request` marker; the move-flow daemon does `gcloud storage mv stash/{id} → crawls/{id}` (same-bucket server-side rewrite); on `.move-done` the service `_mark_as_archived` + clears `stashed_at`, returning `archive_status='pending_upload'` (a known string — the BO's `3_archive_eligible_domains.php` needs no change). A stashed failed/stopped crawl falls through to the existing finished-only 400 guard.

**Crash/restart durability:** optimistic stash (delete local before GCS upload) is kept — `/app/stash` is a persisted volume; the upload daemon resumes after restart. The sweep re-queues a dead-lettered tar (`_requeue_stash_orphan`, logs `STASH_UPLOAD_ORPHAN`). Cross-replica safety rests on the Redis `stash_lock`; the leader in-flight set is a throughput optimization.

**Observability (log-based):** `AUTO_STASH crawl_id=… reason=grace|timeout|disk_pressure`, `STASH_UPLOAD_ORPHAN`, `STASH_MOVE_LIMBO`, plus the existing `UNSTASH_GCS_ORPHAN`.

**Tunables (`app/core/config.py`):** `AUTO_STASH_ENABLED` (false), `STASH_GRACE_SECONDS` (3600), `STASH_SAFETY_TIMEOUT_SECONDS` (172800), `STASH_DISK_HIGH_WATER_PCT` (85), `STASH_MAX_PER_SWEEP` (5); move flow: `MOVE_REQUESTS_PATH`, `MOVE_RESULTS_PATH`, `MOVE_SOURCE_PREFIX` (stash), `MOVE_TARGET_PREFIX` (crawls), `MOVE_TIMEOUT_SECONDS` (120) — prefix names match the daemon's env vars. BO `/results` callers use a 900s timeout to cover inline unstash.

**Rollout:** Phase 1 (transparency) is safe to ship with `AUTO_STASH_ENABLED=false`. Enable the sweep (Phase 2) only after transparency is proven. The move-flow daemon (Phase 3) runs as a `download_daemon.sh` instance with `ENABLE_MOVE=true`.

Spec: `docs/superpowers/specs/2026-06-01-auto-stash-unstash-workflow-design.md`. Plan: `docs/superpowers/plans/2026-06-01-auto-stash-unstash-workflow.md`.

### Follow-up (2026-06-02)

- **Resume-on-start unstash.** `start_crawl` now unstashes the **started crawl's own id** when `stashed_at` is set — not just the update-mode `previous_crawl_id`. The prior Redis record is captured before the fresh `job_data` write; if stashed, `unstash_crawl` runs inline before STORAGE SETUP so the crawl resumes from its restored `request_queue` instead of starting fresh and orphaning the GCS stash. `stashed_at` is preserved into the fresh `job_data` so `unstash_crawl`'s TOCTOU re-read doesn't 409 `NOT_STASHED`. `is_restart` (OOM relaunch) skips it. Independent of the `previous_crawl_id` restore — both can fire in one start.
- **Status visibility.** `GET /status/{id}` (and the list) now expose `stashed_at`, `downloaded_at`, `finished_at`, `size_bytes` (optional/nullable on `CrawlStatus`, mapped in both the main and snapshot `get_status` paths — a stashed crawl takes the snapshot path). Legacy crawls return `null`; BO contract unchanged.
- **Failed/never-downloaded crawls DO stash** — via the 48h safety-timeout, not the download-grace path. `finished_at` is stamped at the terminal transition *before* the failure webhook is dispatched, so a failed webhook delivery never blocks stashing.
- **Existing data (pre-feature crawls):** old terminal crawls lack `finished_at`/`downloaded_at`, so the sweep won't time-stash them. Drain them once with `python tools/stash_crawls_batch.py` after deploy (`stash_crawl` doesn't require `finished_at`). Steady-state thereafter is covered by download-grace + the sweep.

Spec: `docs/superpowers/specs/2026-06-02-auto-stash-followup-design.md`. Plan: `docs/superpowers/plans/2026-06-02-auto-stash-followup.md`.

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

## Success / Stop Webhook Idempotency (PW-A)

Success and stop webhooks carry a single shared `terminal_webhook_request_id`
(in `job_info`), reused by `_send_success_webhook` and `_send_stop_webhook`. A
force-finish stop(`finished`) after a natural success therefore carries the SAME id
and dedupes. The stop webhook reaches BO's *success* branch (it sends no
`crawl_id`+`exit_code`), which is why it shares the success id.

Every sender persists `job_info` via `cache_service.set_json` before sending so a
replay reuses the same id. BO dedupes via `is_duplicate_crawler_webhook(request_id, 'success')`
for success+stop and `'failure'` for failures, into the `crawler_webhook_dedup` table.

## Exit Codes (Node.js → Python)

| Code | Meaning | Python Behavior |
|------|---------|-----------------|
| 0 | Success | Status: `finished`, success webhook |
| 2 | Partial success | Status: `finished`, success webhook |
| 3 | OOM relaunch | Status: `restarting_oom`, auto-relaunch (up to `MAX_OOM_RESTARTS`) |
| 4 | Update mode no data | Status: `failed`, failure webhook with descriptive message |
| 5 | Redis connection lost (Node-side sustained loss) | Status: `failed`, failure webhook with `failure_cause=redis_lost` |
| 6 | Progress stall (no URL progress for threshold) | Status: `failed`, failure webhook with `failure_cause=progress_stalled` |
| 7 | Update mode: domain changed (all/most URLs redirect off-domain) | Status: `failed`, failure webhook with `failure_cause=domain_changed` |
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
| 7 | `domain_changed` | Update crawl aborted: all/most seeded URLs redirect off-domain (relocated site). Homepage fast-path or external-redirect ratio breaker. Spec `docs/superpowers/specs/2026-06-09-external-redirect-breaker-design.md`. |
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

## Redis Connection Leak Prevention

Three client-side prongs + one operator-side step prevent the connection-cap exhaustion that recurred until each crawler-service restart.

### Python side (`libs/common-utils` cache_service)

`init_redis_pool()` now builds a bounded, keepalive-protected client with proactive health checks. All connections are named per-replica for `CLIENT LIST` attribution.

| Env var | Default | Purpose |
|---------|---------|---------|
| `REDIS_MAX_CONNECTIONS` | `20` | Pool cap per replica |
| `REDIS_SOCKET_TIMEOUT_S` | `10` | Per-command timeout |
| `REDIS_SOCKET_CONNECT_TIMEOUT_S` | `5` | Connect handshake timeout |
| `REDIS_HEALTH_CHECK_INTERVAL_S` | `30` | Proactive ping cadence |

`max_connections=0` is clamped to 1. When the pool is exhausted, `redis-py` raises `ConnectionError("Too many connections")` — surfaces as a 500 to the API caller, points us at the leak source rather than silently growing.

Client name: `crawler-py-{HOSTNAME or pid-N}`.

### Node side (crawler subprocess)

Heartbeat publishes and `DedupManager` operations now multiplex on a single shared Redis client created via `createSharedRedisClient(redisUrl, { crawlId, monitor })` in `crawler/src/redisClient.ts`. Halves per-crawl conn count (2 → 1) and halves the orphan blast radius when the process is OOM-killed.

`DedupManager` accepts `RedisClientType | string` — the URL form is preserved for backward compat (tests + legacy callers). When a shared client is injected, the owner attaches the `error` listener; `monitor.onError('dedup', …)` is not invoked on that path.

Client name: `crawler-node-{crawlId}`. Monitor attached as `'shared'`.

`StatsManager` now consumes the injected shared client (`ownsClient=false`) alongside the heartbeat/dedup/pushed/checked multiplex, eliminating its own separate idle-reaped connection — it was silently dropping stat writes when the server reaped its idle socket (`CONFIG timeout 300`) during quiet crawl gaps. The legacy URL constructor is retained for tests. See `docs/superpowers/specs/2026-06-17-statsmanager-redis-resilience-design.md`. `UrlConsolidator` likewise consumes the injected shared client (update mode, `ownsClient=false`) — no separate per-crawl Redis client remains. See `docs/superpowers/specs/2026-06-17-urlconsolidator-shared-client-design.md`.

### Server-side idle reap

`./redis_diagnose.sh --apply-timeout` (run once from the deploy host) sets:

- `CONFIG SET timeout 300` — server reaps idle conns after 5 min.
- `CONFIG SET tcp-keepalive 60` — TCP-level keepalive every 60s.
- `CONFIG REWRITE` — persists to `redis.conf` so the setting survives restart.

These complement the client-side keepalive — TCP-half-open conns left behind by SIGKILL'd Node processes are reaped automatically.

### Diagnostic tools

| Tool | View | Use |
|------|------|-----|
| `./redis_diagnose.sh` (repo root) | Server-side global | All conns Redis sees, names + addrs, config |
| `GET /admin/redis-debug` | Per-replica local | This replica's pool stats + global CLIENT LIST aggregation |

The endpoint is authenticated via existing `verify_api_key` (`X-API-Key` header). Sampled `CLIENT LIST` entries are projected to a whitelisted field set (`name/addr/age/idle/cmd/fd`) so future redis-py additions cannot silently widen the leak surface.

### Rollout (post-deploy)

1. Run `./redis_diagnose.sh` baseline → record `connected_clients`, name distribution.
2. Run `./redis_diagnose.sh --apply-timeout` once.
3. Deploy code (Python pool + Node shared client + admin endpoint together).
4. Run `./redis_diagnose.sh` again → expect `crawler-node-*` count = active crawls (not 2× active crawls); `timeout=300`; orphan count drops within 5 min.
5. Curl `/admin/redis-debug` per replica → expect `pool_stats.in_use` well below `max_connections`.

Spec: `docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md`.
Plan: `docs/superpowers/plans/2026-05-21-redis-connection-leak-fix.md`.

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

**Alternative-URL validation opt-out:** the homepage detect call (`routes.ts:473`, the crawler's only `mode:"complete"` call) sends `validateAlternatives: false` → POST body `validate_alternatives: false`. This stops the detection service from opening a browser to fetch/validate alternative-language URLs on the crawler's `html_content` calls (the OOM / `socket hang up` source). The crawler still receives parsed `alternative_urls` (hreflang prefixes) for Regional Path Exclusion. Internal-page detect calls use `mode:"simple"` and never trigger alt validation, so they need no flag.

## Detection Backpressure (Concurrency Cap + Handler-Timeout Alignment)

The default handler awaits a per-page detection call (the dominant phase — ~94% of
handler time on detection-gated sites). Crawlee's `AutoscaledPool` scales on **local**
CPU/event-loop/memory, all of which look idle while handlers `await` that HTTP call —
so left uncapped it ramps to 25+ concurrent handlers against only `DETECTION_MAX_CONCURRENCY`
(5) detect slots. The surplus handlers pile into the detection `p-limit` queue, inflating
per-page detect latency past `requestHandlerTimeoutSecs`. Crawlee then kills the handler
mid-detect and closes the page; the orphaned handler later hits `page.$$eval` (routes.ts
pre-batch dedup) on the dead page → `Pre-batch link extraction failed: ... Target page,
context or browser has been closed` (a swallowed symptom, surfaced via stderr as
`Erreur crawling`). With almost nothing finishing, `ProgressMonitor` fires (exit 6) and
relaunch loops — a death spiral. Incident: crawl 7033 (carflo.fr), 2026-06-19.

Two env-tunable levers (resolved in `httpStatusPolicy.ts`, wired in `functions.ts`):

| Variable | Default | Effect |
|---|---|---|
| `CRAWLER_MAX_CONCURRENCY` | `10` | `autoscaledPoolOptions.maxConcurrency`. ≈2× `DETECTION_MAX_CONCURRENCY`: overlaps nav/extract with the in-flight detects without growing the detect queue. Set inside `autoscaledPoolOptions` (not top-level) to avoid Crawlee's dual-specification error. |
| `REQUEST_HANDLER_TIMEOUT_S` | `200` | `requestHandlerTimeoutSecs`. Raised from 120 to exceed one nav (≤90) + one detect (`DETECTION_REQUEST_TIMEOUT_S` 180) so a slow-but-progressing page is not killed mid-detect (the prior 120<180 inversion). |

Tune both together: raising `DETECTION_MAX_CONCURRENCY` should be paired with a higher
`CRAWLER_MAX_CONCURRENCY`; detection-light deployments can raise the cap for throughput.
The upstream root (api-detection-langue-fr latency under load) is separate — this only
stops the crawler from amplifying it and tolerates the common slow case.

Spec: `docs/superpowers/specs/2026-06-21-crawler-detection-backpressure-design.md`.

## HTTP Status & Navigation Retry Policy

`page.goto` resolves on `domcontentloaded` (not Playwright's default `load`), so the
HTTP status is visible even on heavy pages whose sub-resources never settle. Default
`load` previously hung for the full `navigationTimeoutSecs` (90s) and the status was
never read — a real 404 timed out and was retried 5×. Content completeness is
unaffected: the handler re-settles content post-navigation via
`processPage`/`waitAndScroll` (bounded `networkidle` + scroll).

Status handling is a single source of truth in `crawler/src/httpStatusPolicy.ts`
(`classifyHttpStatus`), applied in the `routes.ts` default handler. `blockedStatusCodes`
is empty — Crawlee no longer pre-throws on status; every status reaches the handler.

| Class | Codes | Behavior |
|-------|-------|----------|
| permanent | 400, 401, 404, 405, 406, 410, 414, 423, 451, 501 | `request.noRetry = true` → fail once |
| block | 403, 429 | `session.retire()` → retry with fresh session |
| transient | 408, 425, 500, 502, 503, 504, 509, 521-526 | retry (≤ `maxRequestRetries`) |
| ok | all others (2xx/3xx + unlisted) | proceed to extraction |

Navigation timeouts (no HTTP response at all) are capped in `failedRequestHandler`:
after `TIMEOUT_MAX_RETRIES`, `request.noRetry` is set.

**Env vars (optional; defaults baked in, inherited by the Node subprocess):**

| Variable | Default | Effect |
|---|---|---|
| `NAVIGATION_WAIT_UNTIL` | `domcontentloaded` | `page.goto` wait condition. Allowed: `load`, `domcontentloaded`, `commit`, `networkidle`. Invalid → default. Set `load` to revert. |
| `TIMEOUT_MAX_RETRIES` | `2` | Max navigation-timeout retries before `noRetry`. |

Spec: `docs/superpowers/specs/2026-06-09-crawler-http-status-retry-policy-design.md`.

See also "Failure Classification & Auto-Recovery on Restart" below — `classifyFailure`
extends this module to transport errors and drives restart recovery.

## Failure Classification & Auto-Recovery on Restart

A failed request is classified so a same-id restart can recover the *recoverable*
ones without re-crawling genuine permanent failures. The authoritative "permanent"
signal is `request.noRetry` (set by the status policy, `PERMANENT_ERROR_MARKERS`, the
navigation-timeout cap, or a permanent WAF block); only the retried-but-exhausted
bucket is refined by `classifyFailure` (`crawler/src/httpStatusPolicy.ts`).

| Class | Source | Auto-recovered on restart? |
|-------|--------|----------------------------|
| permanent | `noRetry` set, or DNS/SSL/redirect markers, or permanent HTTP status | No |
| infra | transport faults — `NS_ERROR_PROXY_*`, `NS_ERROR_CONNECTION_REFUSED`, `NS_ERROR_NET_*`, `ECONNREFUSED/RESET`, `ETIMEDOUT`, `socket hang up` | Yes |
| transient | transient/block HTTP status (5xx/429/408/…) or navigation timeout | Yes |
| unknown | anything else (incl. `NS_ERROR_ABORT`, `browserController.newPage() failed` — ambiguous) | No |

Each permanently-failed request is written to the `error-{domain}` Crawlee dataset
with a `failure_class` field. On the next launch, `reclaimFailedRequest` runs **before**
the queue-health early-exit in `main.ts` and re-queues only the recoverable records
(resets `retryCount`/`handledAt`), then drops the error dataset. Legacy records with no
`failure_class` (pre-feature crawls) are treated as recoverable so old proxy victims are
not lost (bounded — permanent ones fail-fast on re-crawl).

**Why this exists:** a temporary proxy-gateway outage produced
`NS_ERROR_PROXY_CONNECTION_REFUSED` on valid URLs; without classification they burned the
full retry budget and were permanently lost, and `reclaimFailedRequest` was unreachable
for completed crawls (the queue-health `exit(0)` ran before it).

**Env var:**

| Variable | Default | Effect |
|---|---|---|
| `RECOVER_FAILED_ON_RESTART` | `true` | Auto-recover recoverable failures on a same-id restart. Set `false` to disable (revert to instant "already completed" exit). Node-only, inherited by the subprocess. |

Spec: `docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md`.

## Phase-2 limitDiez (zero-touch)

Auto-decides skipDiez vs bypassDiez from content evidence; never escalates limitDiez to a human. Tier-1 (URL heuristic) produces a *hypothesis*; tier-2 verifies it with real content.

**How it works:**
- URL fragments are kept as distinct request identities (`base`, `base#a`, `base#b` crawl separately), giving tier-2 real material to compare.
- A confident tier-1 outcome (skip/bypass/promoteTier2) does NOT commit directly — it ACTIVATES the tier-2 engine, which then has the final say.
- The engine buffers one `{fragment, content}` per fragment-stripped base; when a 2nd distinct `#`-variant of that base arrives, it cleans both pages via the content-extractor `/clean` (text mode) and classifies the pair by Jaccard similarity (match / mismatch / unusable). `/clean` failures or empty results count as unusable (no false vote).
- It commits `skipDiez` only on positive match-evidence (≥3 comparisons AND ≥80% match ratio) and `bypassDiez` on a mismatch-majority; otherwise it keeps sampling.
- If tier-1 escalates (≥100 hashes with no confident decision) the engine commits the **default** `bypassDiez` — the zero-touch floor, so the crawl never dies at 100 hashes. This floor is active even with the engine disabled (`DIEZ_TIER2_ENABLED=false`), so the crawl is safe without deploying the content-extractor.
- The committed decision is persisted to `_diez_decision.json` (with `source` ∈ {tier1, tier2, default} + comparison `evidence`); on a `skipDiez` that completes, stored dataset rows are stripped of `#` and exact duplicates dropped at shutdown.

**Env vars:**

| Variable | Default | Effect |
|---|---|---|
| `DIEZ_TIER2_ENABLED` | `false` | Gates the tier-2 verification engine. Off = zero-touch floor only (bypassDiez). |
| `CONTENT_EXTRACTOR_API_URL` | `http://content-extractor-api-service:8600` | Base URL for the content-extractor `/clean` endpoint. |
| `CONTENT_EXTRACTOR_TIMEOUT_S` | `20` | Per-call HTTP timeout (seconds). |
| `CONTENT_EXTRACTOR_MAX_CONCURRENCY` | `4` | Max concurrent `/clean` calls per crawl. |
| `CONTENT_EXTRACTOR_MAX_RETRIES` | `1` | Retries on transient errors. |
| `CONTENT_EXTRACTOR_RETRY_AFTER_CAP_S` | `5` | Max seconds the client waits on a 503 `Retry-After` before its single retry (caps server-suggested backoff so it can't stall the page handler). |

- Under content-extractor admission pressure the client honours `Retry-After` (capped) and classifies 503/timeout/network as **transient**; tier-2 does not count a transient failure as a comparison — it keeps the buffered page and retries on the base's next `#`-variant (organic backoff), so a service outage biases to the safe default (bypassDiez) rather than corrupting the match ratio.

**Co-deploy rule:** when `DIEZ_TIER2_ENABLED=true`, the content-extractor-api-service MUST be reachable. It now shares the `crawling` compose profile and the `services-net` network, so it starts alongside the crawler automatically. No extra compose override is needed.

Spec: `docs/superpowers/specs/2026-06-12-limitdiez-phase2-zero-touch` (Hellopro planning repo).

## Phase-2 limitQuestionMark (zero-touch)

Auto-resolves domain-specific `?`-params per-parameter and never escalates `limitQuestionMark` to a human. On top of the shipped Tier-1 observer, a Tier-2 engine buffers each `?`-page's content, groups by "URL with param `p` removed", and when two members differ in `p` (value-vs-value, or value-vs-absent) it cleans both via the content-extractor `/clean` and compares (Jaccard). A param is committed to `toRemove` ONLY on same-majority (compared≥3, same/compared≥0.8) — the single destructive action; different-majority is ruled content-shaping and kept.

**How it works:**
- The engine buffers one `{param_value, content}` entry per (base-URL, param) pair; when a 2nd distinct value of that param arrives for the same base, it cleans both pages via `/clean` (text mode) and classifies the pair as same/different/unusable. `/clean` failures or empty results count as unusable (no false vote).
- A param is committed to `toRemove` only on same-majority evidence (≥3 comparisons AND same/compared≥0.8). Different-majority means the param shapes content — it is kept and never removed.
- **Bounded zero-touch default:** near the 100-`?` ceiling (≥95 `?`-pages), once, the engine sets `bypassQuestionMark=true` + `breakLimit=false` (enables the 5000-dataset-item backstop). This disables the `limitQuestionMark` stop but bounds the crawl, so a facet-explosion trap cannot run away. The engine NEVER applies `skipQuestionMark`. Any already-committed `toRemove` strips remain in effect.
- Committed decisions are persisted to `_questionmark_decision.json` (`addedToRemove` list merged back into `toRemove` on OOM relaunch).
- `getQuestionMarkDecisionMode` reports the current state: `tier2-resolved` / `defaulted-bypassed` / `escalated` / `observed` / `unused`.

**Env vars:**

| Variable | Default | Effect |
|---|---|---|
| `QM_TIER2_ENABLED` | `false` | Gates the Tier-2 per-param engine. Off = Tier-1 observer only (no behaviour change). |
| `CONTENT_EXTRACTOR_API_URL` | `http://content-extractor-api-service:8600` | Shared with limitDiez phase-2. Base URL for the content-extractor `/clean` endpoint. |
| `CONTENT_EXTRACTOR_TIMEOUT_S` | `20` | Shared with limitDiez phase-2. Per-call HTTP timeout (seconds). |
| `CONTENT_EXTRACTOR_MAX_CONCURRENCY` | `4` | Shared with limitDiez phase-2. Max concurrent `/clean` calls per crawl. |
| `CONTENT_EXTRACTOR_MAX_RETRIES` | `1` | Shared with limitDiez phase-2. Retries on transient errors. |
| `CONTENT_EXTRACTOR_RETRY_AFTER_CAP_S` | `5` | Shared with limitDiez phase-2. Max seconds the client waits on a 503 `Retry-After` before its single retry. |

**Co-deploy rule:** when `QM_TIER2_ENABLED=true`, the content-extractor-api-service MUST be reachable. It shares the `crawling` compose profile and the `services-net` network (already configured for limitDiez) — no extra compose override is needed.

Spec: `docs/superpowers/specs/2026-06-16-limitquestionmark-phase2-zero-touch` (Hellopro planning repo).

## Conventions

- Nginx handles path stripping; routers have no prefix. Crawler spawned as child process by `crawler_manager`.

## Dependencies

Redis (state/counters), GCS (archive + restore), `common-utils`, `api-detection-langue-fr`.
