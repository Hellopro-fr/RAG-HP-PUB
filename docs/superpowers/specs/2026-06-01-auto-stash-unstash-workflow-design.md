# Auto-Stash / Unstash Crawl Workflow — Design

- **Date:** 2026-06-01
- **Status:** Design — approved in brainstorming, pending implementation plan
- **Service:** `crawler-service` (Python orchestrator + Node crawler) + `tools/` daemons + Hellopro BO (minimal)
- **Branch:** `features/poc`
- **Predecessor specs:** `2026-05-19-stash-unstash-gcs-design.md`, `2026-05-19-stash-unstash-followup-fixes-design.md`, `2026-05-20-stash-bind-mount-and-cleanup-design.md`, `2026-05-21-stash-archive-lock-heartbeat-design.md`, `2026-05-22-stash-crawls-batch-script-design.md`, `2026-05-23-stash-script-poll-fallthrough-design.md`

> Line numbers in this document are **indicative** (captured during brainstorming). The implementation plan re-pins exact lines against the current tree.

---

## 1. Motivation

Stash/unstash exists today but is **operator-only** (manual `POST /stash` / `POST /unstash`, the `stash_crawls_batch.py` CLI). The goal is to fold stash/unstash into the crawl lifecycle **automatically**, so finished crawls don't sit on local disk indefinitely, while keeping the data invisibly retrievable for downloads, update-mode re-crawls, and archiving.

User intent (rough):
1. When a crawl finishes (success or failure) → stash it.
2. When a crawl starts and the same data was stashed → unstash it and continue.
3. When results are downloaded for a crawl whose data is stashed → unstash it.
4. When archive-time comes → move the crawl from stash into the GCS archive.

Brainstorming + adversarial code verification reshaped these rough ideas into the design below. The most important correction: **bullet 2 ("same-ID restart") does not exist in practice** — see §3 and §11 Decision D8.

## 2. Goals / Non-Goals

**Goals**
- Automatically stash terminal crawls once their local data is no longer needed on the fast path, reclaiming local disk.
- Keep stash fully transparent to consumers: `/results`, update-mode restore, and `/archive` "just work" on a stashed crawl.
- Survive service crash/restart with no data loss and no orphaned state.
- Minimize Hellopro-side change (target: timeout bumps only).
- Ship in independently-verifiable phases, gating the high-blast-radius automation behind a proven transparency layer.

**Non-Goals**
- Changing the manual stash/unstash endpoints' contract (they remain; automation reuses them).
- Server-side `BackgroundTasks` migration of stash/archive (deferred, predecessor-spec follow-up).
- Prometheus metrics (observability stays log-based, consistent with predecessor specs).
- Stashing **active** crawls (running/restarting_oom/stopping) — still blocked `409 CRAWL_IS_ACTIVE`.
- Migrating already-`archived` crawls back into stash.

## 3. Current State (verified)

- `POST /stash/{id}` → `stash_crawl` (`crawler_manager.py` ~2198): **async**. Tars to `/app/stash/{id}.tar.gz` (`shutil.make_archive(..., 'gztar', root_dir=job_storage_path)`), sets orthogonal `stashed_at` ISO field in Redis, deletes local crawl data (keeps logs/markers), returns **202** *before* GCS upload. `upload_daemon.sh` (stash flow, `UPLOAD_GCS_PREFIX=stash`) uploads later and deletes the local tar.
- `POST /unstash/{id}` → `unstash_crawl` (`crawler_manager.py` ~2428): **sync**, blocks ≤ `UNSTASH_TIMEOUT_SECONDS` (300s) on a daemon download + 2-phase-commit GCS delete (`.request`→`.done`→`.unstash-confirmed`→`.unstash-cleanup-done`).
- `stashed_at` is **orthogonal to status** — a stashed crawl keeps its terminal status (`finished`/`failed`/`stopped`). No status enum change. Preserves the entire 409 conflict matrix and BO status parsing.
- `archive_crawl` (`crawler_manager.py` ~1859): tars with the **identical** `shutil.make_archive(..., 'gztar', root_dir=job_storage_path)` and uploads under `crawls/`. Since crawl data is immutable after a terminal state, **the stash tar is byte-equivalent in content to the archive tar.** ⇒ stash→archive can be a pure GCS rename.
- `get_results_archive` (`crawler_manager.py` ~1414): 3 branches — `running`→400, `archived`→GCS retrieve, **else**→`_generate_archive_sync`. **No `stashed_at` branch** — a stashed FINISHED crawl currently falls to the `else` branch and tries to tar an empty disk (corrupt/500). Endpoint `/results` at `crawler.py:299-341`, calls manager at ~311, returns `StreamingResponse`/`FileResponse` at ~330/336.
- Update mode (`start_crawl`, `crawler_manager.py` ~546) already calls `_restore_archived_crawl(previous_crawl_id)` (~2086-2136) — a **blocking** GCS restore (lock `restore_lock:{id}`, poll loop, `_retrieve_from_gcs_daemon`, tar extract, ownership-safe CAS release at ~2136). This is the same pattern unstash uses.
- Reconcile: `reconcile_jobs` (~2653-2686) is **leader-elected** (`reconcile_leader_lock`, `SET NX`, TTL 2× interval, ownership-safe CAS release), scheduled in `main.py` every `RECONCILIATION_INTERVAL_SECONDS` (300s). `_reconcile_locked` (~2773-3000) scans `crawl_job:*` via `SCAN` + pipeline fetch, iterates all jobs.
- **Crawl IDs are never reused.** `POST /start` takes a client-supplied `payload.id`; the BO launch cron (`script_lancer_enqueue_crawling.php:663`) always sends a fresh `id_domaine` for initial crawls and a *different* `storage_folder_name` for update crawls. There is **no same-ID restart** of a terminal crawl.
- BO `/results` callers: `getTemporaryResultsPath` (`fonctions_scrapping.php:140`) and `syncFinalResults` (`:196`), both `GET /results/{id}` via `sendRequest`→`call_api_hellopro`, inheriting the **300s default** timeout (no per-call override).
- BO archive caller: `3_archive_eligible_domains.php` `callArchiveEndpoint` (~39-70) normalizes all 2xx to code 200 and branches on **exact** `archive_status` strings `{pending_upload, already_in_gcs}` + substring `"already been archived"`; **any unknown value → marked `erreur`** (~399).

## 4. Design Overview

### 4.1 Principles
- Stash stays an **orthogonal `stashed_at` field**, never a status enum (preserves the 409 matrix + BO parsing).
- The auto-stash decision is made by a **leader-elected periodic sweep reading durable Redis state** — never inline in the terminal/webhook branch. This provably prevents the "stash races the completion webhook" failure (the BO always gets its first download from local disk).
- Stash fires only after the crawl is **consumed** (downloaded) + a grace window, OR after a long safety timeout, OR under disk pressure — never during the webhook→first-download window.
- Reuse proven mechanisms wholesale: existing `stash_crawl`/`unstash_crawl`, the `_restore_archived_crawl` restore pattern, the leader-elected reconcile loop, the daemon marker protocol.

### 4.2 Lifecycle

```
START ──▶ RUNNING ──(OOM relaunch loop)──▶ terminal { FINISHED | FAILED | STOPPED }
                                                  │
                                  BO GET /results  │  (success path)
                                  └─ serves from local, records downloaded_at (stream-start)
                                                  │
   leader-elected reconcile sweep (every tick) evaluates each terminal, stashed_at-unset,
   non-archived, no-lock-held crawl:
       stash-eligible IF
         (downloaded_at set AND now − downloaded_at ≥ GRACE)            ← happy path
         OR (now − finished_at ≥ SAFETY_TIMEOUT)                        ← never-downloaded / failed
         OR (disk ≥ HIGH_WATER AND crawl in top-N by size/age)          ← pressure override
                                                  │  (cap STASH_MAX_PER_SWEEP per tick)
                                                  ▼
                                STASHED  (stashed_at set, local data deleted, tar → gs://stash/)
                                                  │
        ┌───────────────────────┬───────────────────────────┬───────────────────────────┐
   update-mode start         GET /results                 POST /archive (BO cron)
   (previous_crawl_id        → transparent inline          → GCS move stash/{id}→crawls/{id}
    is stashed)                unstash → serve               (download_daemon), status=archived,
   → _restore_archived_crawl   + refresh downloaded_at        clear stashed_at, return
     extended to unstash       (re-stashes next sweep)        archive_status='pending_upload'
   → resume update                                          → ARCHIVED
```

### 4.3 Why the sweep (not `_monitor_process`)
If stash fired in the terminal branch, the BO's post-200 background `syncFinalResults` could hit deleted data. Because stash requires `downloaded_at` + grace (or a long timeout), it **cannot** fire during the webhook→first-download window. No race, no ordering dependency. (OOM relaunch also cannot collide: stash is terminal-only and OOM crawls are `restarting_oom` = slot held — verified.)

## 5. Data Model Changes

New `job_data` fields in Redis (all additive, orthogonal, no status enum). Cached **on write** so the sweep reads pure Redis and the leader-held critical section stays cheap (Decision D9):

| Field | Written when | Source | Drives |
|---|---|---|---|
| `finished_at` (ISO) | terminal transition in `_monitor_process` / OOM-fail / force-finish / stale | `_completion_marker.json` `end_timestamp` (mirror into Redis) | safety-timeout eligibility |
| `downloaded_at` (ISO) | `/results` served (stream-start), at `crawler.py:~311` before returning the response | `datetime.utcnow().isoformat()` | grace eligibility |
| `size_bytes` (int) | at the terminal transition (alongside `finished_at`) | `_estimate_archive_required_bytes(storage_path)` | disk-pressure ordering (top-N by size) |

Old jobs lacking these fields degrade gracefully: missing `finished_at`/`size_bytes` → fall back to the safety-timeout / on-demand estimate; missing `downloaded_at` → treated as never-downloaded (safety-timeout path).

`stashed_at` (existing) continues to route unstash/archive.

## 6. Phase 1 — Transparency Layer

*Makes any stashed crawl invisibly retrievable. Ships first; no auto-stash yet. Once in prod, manual stash is safe to coexist with normal operations.*

**1a. `/results` stashed branch** — `get_results_archive` (`crawler_manager.py:~1414`): add, **before** the `_generate_archive_sync` fall-through (~1437):
```
if job_info.get("stashed_at"):
    await self.unstash_crawl(job_info)          # blocking ≤ UNSTASH_TIMEOUT_SECONDS
    job_info = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")   # refresh: stashed_at now cleared
# fall through → serve from now-local data
```
Inline unstash reuses the existing 2-phase mechanism. On unstash failure, propagate its existing error (502/504) — do **not** fall through to a corrupt archive.

**1b. Record `downloaded_at`** — `/results` endpoint (`crawler.py:~311`), after `get_results_archive` returns and **before** building the response: persist `job_info["downloaded_at"] = utcnow().isoformat()`. Semantics: "consumed" = **download initiated** (stream-start) — the only observable point; there is no stream-completion hook.

**1c. Bullet 2 = update-mode restore (not same-ID)** — extend `_restore_archived_crawl` (`crawler_manager.py:~2086-2136`) so that when a `previous_crawl_id` has `stashed_at` set (not only `status==archived`), it unstashes it from `gs://stash/` (same lock + GCS-daemon + extract + CAS-release pattern it already uses for archived). The launched crawl has a *different* id; the **previous** crawl is the unstash subject. No same-ID code path is added (it never occurs).

**1d. BO timeout bump** — raise the timeout on the two `/results` callers (`fonctions_scrapping.php:140, 196`) to `~900s` (covers a large inline unstash; default is 300s and `sendRequest` passes no override). Add explicit error handling on these two calls (the BO has no global timeout safety net here — surprise S3).

**Phase-1 verification:** manually stash a crawl → `GET /results` transparently unstashes + serves; update-mode crawl whose previous crawl is stashed → restores + resumes; `downloaded_at` observed populating.

## 7. Phase 2 — Auto-Stash Sweep

*The automation. Feature-flagged (`AUTO_STASH_ENABLED=false` by default); enabled only after Phase 1 is proven in prod.*

**2a. Host** — a sweep block inside `_reconcile_locked` (`crawler_manager.py:~2773-3000`), near the terminal-state handling (~2973). Reuses the existing leader lock + `crawl_job:*` scan + pipeline fetch (already in hand). Calling `stash_crawl` is safe — it takes a *distinct* `stash_lock:{id}`, no reentrancy/deadlock with `reconcile_leader_lock`.

**2b. Eligibility** — for each crawl with terminal status, `stashed_at` unset, not `archived`, no `stash_lock`/`unstash_lock` held:
```
eligible =
    (downloaded_at AND now − downloaded_at ≥ STASH_GRACE_SECONDS)
 OR (finished_at  AND now − finished_at   ≥ STASH_SAFETY_TIMEOUT_SECONDS)
 OR (disk_used_pct ≥ STASH_DISK_HIGH_WATER_PCT AND crawl ∈ top-N by size_bytes/age)
```
Stash at most `STASH_MAX_PER_SWEEP` per tick (largest/oldest first under pressure). Each eligible crawl → `stash_crawl(job_info)`; a `409` (ALREADY_STASHED / OPERATION_IN_PROGRESS) is treated as a no-op (coexists with manual + batch CLI).

**2c. Durability (Decision D11 — keep optimistic):** the auto path reuses `stash_crawl` unchanged (optimistic delete-local-before-upload; `/app/stash` is a persisted volume; daemon resumes after restart). Add the **orphan sweep**: a crawl with `stashed_at` set + `dead_letter/{id}.tar.gz` present → log `STASH_UPLOAD_ORPHAN` and re-queue (move back to the upload watch dir). Silent GCS gaps (neither local nor GCS) are covered by the existing `gcs_archive_audit.py`. Log the disk-preflight skip (fail-open) prominently on the auto path.

**Phase-2 verification (mocked):** finished + not-downloaded → stashed after safety timeout; downloaded → stashed after grace; disk filled → top-N stashed early; ineligible skipped; `MAX_PER_SWEEP` capped; non-leader replicas don't fire; 409 no-ops.

## 8. Phase 3 — Stash→Archive Move

*GCS-side, last. Logically after Phase 2.*

**3a. `/archive` stashed branch** — `archive_crawl` (`crawler_manager.py:~1859`): add a top branch — if `stashed_at` set + status `finished`: instead of `409`, write `.move-request`, poll `.move-done`/`.move-error`, on success `_mark_as_archived(crawl_id)` + clear `stashed_at`, return `archive_status='pending_upload'` (Decision D10 — **reuse the known string**, zero BO change; the BO collapses 2xx to 200 and branches on `pending_upload`).

**3b. Daemon owner = `download_daemon.sh`** (NOT upload). It already runs `gcloud storage rm` in 2-phase commit, has gcloud + creds + both prefix configs. Add a third marker loop doing `gcloud storage mv gs://{bucket}/stash/{id}.tar.gz gs://{bucket}/crawls/{id}.tar.gz` (same-bucket = **server-side rewrite**, instant at any size; pattern already used in `restore_from_reaudit.py:36` and the quarantine runbook). New `.move-request/.move-done/.move-error` config paths clone the existing marker settings (`config.py:~35-41`).

**3c. Idempotency (surprise S1 — `callArchiveEndpoint` has its own retry-on-503 loop):** the move tolerates double-fire — `stash/{id}` gone + `crawls/{id}` present → already moved, mark archived; both present → retry the `rm` half; `.move-error` → log `MOVE_ORPHAN` + retry next tick.

**Phase-3 verification:** `/archive` on stashed → `.move-request` written, polls `.move-done`, marks archived, returns `pending_upload`; idempotent already-moved path; bash move-loop test with mocked `gcloud`.

## 9. Crash / Restart & Failure Handling

| Scenario | Behavior |
|---|---|
| Service crash post-`stashed_at`, pre-upload | **No loss** — tar on persisted `/app/stash` volume; daemon (separate process) resumes upload. |
| Upload daemon dead-letters the tar | `stashed_at` set + `dead_letter/{id}.tar.gz` → sweep logs `STASH_UPLOAD_ORPHAN` + re-queues. |
| Silent GCS gap (neither local nor GCS) | Covered by `gcs_archive_audit.py` (periodic operator audit). |
| Move orphan (Phase 3) | Idempotent recovery (§8.3c). |
| Sweep × manual × batch CLI concurrency | All funnel through `stash_crawl` + `stash_lock`; sweep treats 409 as no-op. No double-stash. |
| nginx retry fan-out | N/A — auto-triggers fire in-process, not via nginx; `stash_lock` is the serialization guarantee. |
| Disk pre-flight fail-open at volume | A failed tar is caught + logged + sweep moves on; preflight-skip logged prominently. |
| Update-mode restore lock held on crash | Extended `_restore_archived_crawl` releases its lock in `finally` via CAS (existing template at ~2136) — never strands the domain (surprise S5: respects the BO webhook-lock guard). |
| OOM relaunch vs stash | No collision — stash is terminal-only; OOM crawls are `restarting_oom` (slot held). Verified. |

## 10. Hellopro Impact (consolidated)

- `/results`: **+ stashed branch (server)** + **2 timeout bumps + error hardening (BO, `fonctions_scrapping.php:140,196`)** — the entire BO change.
- `/archive`: returns `pending_upload` for moves → **BO unchanged** (`3_archive_eligible_domains.php` branches on the known string).
- `/status`: unaffected — stashed crawls keep status + markers (cleanup keeps markers), so dashboard polling works.
- Completion webhook: unaffected — stash via sweep, not the terminal branch → **no race** with the BO's post-200 `syncFinalResults`.
- Launch cron: unaffected — stateless on `crawl_id`.

## 11. Decisions Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Stash trigger | Grace window | Protect the fast download path; avoid churn. |
| D2 | Window type | Consumed-then-stash + safety timeout | Precise on the happy path, bounded disk use on abandoned crawls. |
| D3 | "Consumed" signal | BO `/results` download (stream-start) | Only observable consume point; recorded at `crawler.py:~311`. |
| D4 | Step-4 stash→archive | GCS-side move via `download_daemon` | Cheapest (server-side rewrite), no local round-trip; daemon owns GCS. |
| D5 | Trigger engine | Leader-elected reconcile sweep | Durable (Redis state), survives restart, no double-fire, proven pattern. |
| D6 | `/results` on stashed | Transparent inline unstash | Minimal BO change; service absorbs the state machine. **Real code change**, not timeout-only. |
| D7 | Disk pressure | Overrides grace (high-water → stash early) | Marries grace model with stash's original disk-relief purpose. |
| D8 | Bullet 2 ("start→unstash") | Extend update-mode `_restore_archived_crawl` for stashed previous crawl | Same-ID restart **does not exist** (verified); update mode is the real path. |
| D9 | Sweep field access | Cache `finished_at`/`downloaded_at`/`size_bytes` into `job_data` on write | Keeps the leader-held critical section cheap; additive + backward-compatible. |
| D10 | Phase-3 `archive_status` | Reuse `pending_upload` | Zero BO change; `3_archive_eligible_domains.php` branches on exact known strings. |
| D11 | Auto-stash durability | Keep optimistic async + orphan sweep | Frees disk immediately; smallest diff; residual risk = single-copy persisted-volume loss (same as today). |
| D12 | Sequencing | Phased within one spec (3 gated phases) | Isolates the unverifiable prod-timing assumption behind a phase gate. |

## 12. Configuration (proposed defaults — tunable)

| Setting | Default | Drives |
|---|---|---|
| `AUTO_STASH_ENABLED` | `false` | Phase-2 master gate |
| `STASH_GRACE_SECONDS` | `3600` (1h) | after-download delay |
| `STASH_SAFETY_TIMEOUT_SECONDS` | `172800` (48h) | never-downloaded + failed-crawl investigation window |
| `STASH_DISK_HIGH_WATER_PCT` | `85` | pressure override |
| `STASH_MAX_PER_SWEEP` | `5` | daemon load cap |
| `AUTO_STASH_SWEEP_INTERVAL_SECONDS` | `= RECONCILIATION_INTERVAL_SECONDS` (300) | sweep cadence |
| BO `/results` timeout | `900s` | covers large inline unstash |

## 13. Observability (log-based, no Prometheus)

New grep prefixes: `AUTO_STASH crawl_id=… reason=grace|timeout|disk_pressure`, `STASH_UPLOAD_ORPHAN crawl_id=…`, `MOVE_ORPHAN crawl_id=…`. Existing `UNSTASH_GCS_ORPHAN` retained. Stuck inline-unstash on `/results` is **not** in the BO reconciliation pass (surprise S4) → detected via logs only.

## 14. Phase Gates / Rollout

- **Gate 1→2:** Phase 1 deployed; manual stash + transparent `/results` retrieval + update-mode stashed-restore verified in prod; `downloaded_at` observed populating.
- **Gate 2→3:** `AUTO_STASH_ENABLED` on; sweep stashing observed across all three triggers; no `/results` breakage; daemon upload backlog healthy; orphan rate acceptable.
- Phase 3 is independently shippable but logically follows Phase 2.

## 15. Testing Strategy

Repo test-seam pattern; pytest (Python) + node:test (TS) + bash for daemon loops.
- **P1:** `get_results_archive` stashed branch (mock `unstash_crawl`, assert serve + job_info refresh); `downloaded_at` persisted at stream-start; `_restore_archived_crawl` handles stashed `previous_crawl_id`.
- **P2:** eligibility predicate matrix (grace / timeout / disk-pressure combinations + boundaries); cached-field reads + graceful degradation when absent; 409 no-op; `MAX_PER_SWEEP` cap; leader-lock gating; orphan detection.
- **P3:** `/archive` stashed branch writes `.move-request` + polls; idempotent already-moved → mark archived; returns `pending_upload`; bash move-loop with mocked `gcloud`.

## 16. Open Questions / Deferred

- **[UNCLEAR resolved]** BO `/results` callers located (`fonctions_scrapping.php:140,196`); inherit 300s default → bumped in Phase 1.
- Tuning of `STASH_GRACE_SECONDS` / `STASH_SAFETY_TIMEOUT_SECONDS` / `STASH_DISK_HIGH_WATER_PCT` against real finish→download timing — observation-driven post-Phase-2.
- Server-side `BackgroundTasks` migration of stash/archive/move (predecessor-spec deferral) — out of scope.
- Confirmed-stash (wait-for-upload) — rejected (D11); revisit only if persisted-volume loss is observed.

## 17. Verification Provenance

Grounded by two adversarial-verification workflows over `crawler-service` + `tools/` + Hellopro BO:
1. Context map (5 explorers + synthesis) — stash/unstash mechanism, lifecycle hooks, GCS archiving, Hellopro orchestration, prior specs.
2. Design verification (5 adversarial verifiers + adjudicator) — confirmed/contradicted each design claim against code. Key contradiction: **same-ID restart does not exist** (D8). Confirmed: reconcile-as-sweep-host, `download_daemon` as move owner, `gcloud storage mv` server-side rewrite, OOM-vs-stash non-race, identical stash/archive tar content.
