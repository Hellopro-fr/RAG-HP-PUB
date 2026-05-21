# Stash + Archive Lock Heartbeat — Design Spec

**Date:** 2026-05-21
**Status:** Approved (post-brainstorming)
**Branch:** `features/poc`
**Incident reference:** crawl 6250 stash failure on 2026-05-20

---

## 1. Problem Statement

A `POST /stash/6250` request on 2026-05-20 produced three concurrent tar processes across three crawler-service replicas, and two of them failed mid-tar with `FileNotFoundError` because the winning replica had already deleted source files via its post-stash cleanup.

The user issued a single manual POST. Three replicas ran the operation. The end state: one valid tar in `/app/stash/`, two HTTP 500 responses, source data partially deleted, operator confusion.

### 1.1 Observed log timeline (crawl 6250)

| Time | Replica | Event |
|---|---|---|
| 19:44:46 | 6 | `Stash disk state for '6250'` — pre-flight log fires inside `stash_crawl` AFTER lock acquire |
| 19:54:46 | 1 | `Stash disk state for '6250'` — second replica enters `stash_crawl` |
| 20:04:46 | 7 | `Stash disk state for '6250'` — third replica enters `stash_crawl` |
| 20:07:25 | 6 | `Stashed crawl '6250' (2116600178 bytes) -> /app/stash/6250.tar.gz` — first finishes (≈23 min tar) |
| 20:07:25 | 6 | `Marked crawl '6250' as stashed at … in Redis.` |
| 20:07:28 | 1 | `Failed to create stash archive for '6250': [Errno 2] No such file or directory: '/app/storage/6250/./storage/datasets/nouveauxmarchands.com/000004613.json'` |
| 20:07:30 | 7 | Same `FileNotFoundError` on a different dataset file |
| 20:07:31 | 7 | `POST /stash/6250 HTTP/1.0 500` |
| 20:07:33 | 6 | `Cleaned data (kept logs) for stashed crawl '6250'.` |

The 10-minute spacing between pre-flight logs (19:44 → 19:54 → 20:04) matches `STASH_LOCK_TTL_SECONDS = 600` exactly. Each replica acquired a fresh lock the moment the previous lock TTL expired.

## 2. Root Cause

Three independent defects compound into the observed failure mode.

### 2.1 Lock TTL synchronized with nginx upstream timeout

- `apps-microservices/crawler-service/app/core/config.py`: `STASH_LOCK_TTL_SECONDS = 600`.
- `apps-microservices/api-gateway-go/nginx.conf`: `proxy_read_timeout 600s; proxy_next_upstream error timeout http_503 non_idempotent;` on `/crawler/` location.

A POST that runs longer than 600s on the upstream triggers nginx's `proxy_next_upstream` retry — `non_idempotent` explicitly authorizes POST retry. nginx picks the next replica via round-robin. The same 600-second mark is when the in-flight replica's `stash_lock:{id}` TTL expires. The retry-time and the TTL-expiry time coincide by construction.

### 2.2 No TTL renewal during long-running operations

A 2.1 GB crawl takes roughly 23 minutes to tar via `shutil.make_archive('gztar', …)`. No code path renews the Redis lock TTL while the tar runs. The lock expires at 600s and the work continues. Any concurrent caller acquires a fresh lock and starts a second tar against the same source directory.

### 2.3 Cleanup races concurrent readers

`stash_crawl` performs:

1. Tar source directory → write to `/app/stash/.staging/{id}.tar.gz`.
2. Atomic move to `/app/stash/{id}.tar.gz`.
3. Set `stashed_at` in Redis.
4. `_cleanup_data_keep_logs(job_storage_path)` — `os.walk` + `os.remove` every dataset file in place.

When two replicas run in parallel (because of §2.1 + §2.2), the winner's step 4 deletes source files that the loser's step 1 (`tarfile.gettarinfo` → `os.lstat`) is mid-read. `FileNotFoundError` propagates → HTTP 500 → partial tar discarded.

## 3. Risk Surface Beyond Stash

The same class of bug exists at varying severities across operations.

| Operation | Endpoint sync? | Lock TTL | nginx upstream timeout | Lock value | Concurrent-execution risk |
|---|---|---|---|---|---|
| Stash | Yes | 600s | 600s | replica-id-tagged | **HIGH** — observed failure |
| Archive | Yes | 1800s | 600s | constant `"1"` (not ownership-safe) | **MEDIUM** — would race on tar > 30 min; replica crash leaves zombie lock |
| Unstash | Yes (bounded `UNSTASH_TIMEOUT_SECONDS = 300`) | 600s | 600s | replica-id-tagged | **LOW** — op time-bounded below nginx timeout |
| Download daemon flow | No (file-marker driven) | n/a | n/a | n/a | None — no synchronous HTTP retry path |

Archive carries a second hazard not present in stash: its lock value is the constant string `"1"`, and release uses plain `redis.delete(lock_key)`. After a TTL expiry + race, a slow replica's `DEL` would unconditionally remove a new replica's lock — Compare-And-Delete is impossible without a unique value.

## 4. Caller Contract (Marketplace/BO)

Single observed caller for archive: `BO/script/rag/alimentation_site_web/archivage/3_archive_eligible_domains.php`. Cron-driven batch over a list of domains.

### 4.1 Behavior at `callArchiveEndpoint` (line 39)

- Delegates to `call_api_hellopro('POST', SERVICE_CRAWLING, "/archive/{id}")`.
- Default total CURL timeout: 300 s (`call_api_hellopro` default).
- Retries 3 attempts with exponential backoff **only on HTTP 503**.
- On non-503 error or curl timeout: returns immediately with `http_code = 0` or non-2xx body.

### 4.2 Cron's handling of archive responses (line 372+)

- `archive_status = 'already_in_gcs'` (HTTP 200) → cleanup Ecritel + `est_archiver = 1`.
- HTTP 409 with body matching `already been archived` → cleanup Ecritel + `est_archiver = 1` (treated as safe success signal).
- `archive_status = 'pending_upload'` (HTTP 200) → no cleanup, leaves `est_archiver = 0`, re-tried next cron tick.
- Any other error → log "ERREUR" + leave `est_archiver = 0`, re-tried next cron tick.

### 4.3 Implication for the fix

The PHP caller already tolerates 409 as a success signal and re-runs on the next cron tick. The fix must:

- Preserve the existing JSON response shape (`crawl_id`, `archive_status`, `archive_size_bytes`).
- Preserve the existing 409 conflict body shape (`detail` is the human string `"Crawl '{id}' has already been archived."`).
- Avoid producing new error categories the cron does not handle.

No PHP changes are needed.

## 5. Design

### 5.1 New helper `_LockHeartbeat`

Async context manager that runs a background asyncio task to renew a Redis lock TTL while a long-running operation holds the lock. Implemented in `apps-microservices/crawler-service/app/core/crawler_manager.py` next to `_acquire_ownership_lock`.

```python
class _LockHeartbeat:
    """
    Renews lock_key TTL via Lua compare-and-set every interval_seconds.
    Stops renewing on: max_duration_seconds reached, value mismatch
    (lock taken over), explicit task cancellation, or unrecoverable Redis
    error after retry.

    Usage:
        async with _LockHeartbeat(cm, key, value, ttl, interval, max_duration):
            await long_running_op()
    """

    def __init__(self, cm, lock_key, lock_value, ttl_seconds,
                 interval_seconds, max_duration_seconds):
        ...

    async def __aenter__(self) -> "_LockHeartbeat":
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self._run(), name=f"lock-heartbeat:{lock_key}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self):
        # Lua: only EXPIRE if value still matches expected.
        lua_refresh = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('expire', KEYS[1], ARGV[2]) "
            "else return 0 end"
        )
        try:
            while True:
                await asyncio.sleep(self._interval)
                if time.monotonic() - self._started_at > self._max_duration:
                    logger.error(f"Lock heartbeat {self._lock_key} exceeded max_duration")
                    return
                try:
                    res = await cache_service.redis_client.eval(
                        lua_refresh, 1, self._lock_key, self._lock_value, str(self._ttl)
                    )
                    if res == 0:
                        logger.warning(f"Lock {self._lock_key} no longer owned. Stopping.")
                        return
                except Exception as e:
                    logger.warning(f"Heartbeat refresh failed for {self._lock_key}: {e}")
        except asyncio.CancelledError:
            return
```

Safety properties:

- **Ownership-safe refresh** — Lua CAS prevents refreshing a lock that has already been taken over.
- **Bounded** — `max_duration_seconds` cap stops zombie renewals on truly hung ops, forcing eventual TTL expiry.
- **Cancel-on-exit** — `__aexit__` cancels and awaits the heartbeat task.
- **Crash-safe** — task dies with the replica, no zombie locks.

### 5.2 New config in `app/core/config.py`

```python
STASH_LOCK_TTL_SECONDS: int = 1800              # was 600
ARCHIVE_LOCK_TTL_SECONDS: int = 1800            # newly explicit (was hardcoded in archive_crawl)
LOCK_HEARTBEAT_INTERVAL_SECONDS: int = 300      # renew every 5 min
LOCK_HEARTBEAT_MAX_DURATION_SECONDS: int = 14400  # absolute cap, 4 h
```

Ratio `TTL / interval = 6` gives 5 missed renewals of slack before TTL expires. Conservative against transient Redis latency.

### 5.3 Stash integration

`stash_crawl` (around line 2065-2199 of `crawler_manager.py`) — wrap the existing tar + Redis update + cleanup block inside an `async with _LockHeartbeat(...)` block. The existing `try/finally` releasing the lock stays unchanged.

```python
lock_value = await self._acquire_ownership_lock(stash_lock_key, settings.STASH_LOCK_TTL_SECONDS)
# … existing TOCTOU re-validation …
try:
    async with _LockHeartbeat(
        self, stash_lock_key, lock_value,
        ttl_seconds=settings.STASH_LOCK_TTL_SECONDS,
        interval_seconds=settings.LOCK_HEARTBEAT_INTERVAL_SECONDS,
        max_duration_seconds=settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS,
    ):
        self._verify_bind_mount(settings.STASH_SHARED_PATH, "stash upload")
        # … pre-flight disk check (unchanged) …
        final_path, archive_size = await anyio.to_thread.run_sync(_create_stash_archive)
        # … mark stashed_at (unchanged) …
        # … cleanup data keep logs (unchanged) …
finally:
    await self._release_ownership_lock(stash_lock_key, lock_value)
```

### 5.4 Archive lock migration + heartbeat

`archive_crawl` (around line 1679 of `crawler_manager.py`).

**Before:**

```python
lock_key = f"archive_lock:{crawl_id}"
lock_acquired = await cache_service.redis_client.set(lock_key, "1", nx=True, ex=1800)
if not lock_acquired:
    raise HTTPException(409, detail=f"Archiving for crawl '{crawl_id}' is already in progress.")
try:
    # … tar + cleanup …
finally:
    await cache_service.redis_client.delete(lock_key)
```

**After:**

```python
archive_lock_key = f"archive_lock:{crawl_id}"
lock_value = await self._acquire_ownership_lock(archive_lock_key, settings.ARCHIVE_LOCK_TTL_SECONDS)
if lock_value is None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Archiving for crawl '{crawl_id}' is already in progress."
    )
try:
    async with _LockHeartbeat(
        self, archive_lock_key, lock_value,
        ttl_seconds=settings.ARCHIVE_LOCK_TTL_SECONDS,
        interval_seconds=settings.LOCK_HEARTBEAT_INTERVAL_SECONDS,
        max_duration_seconds=settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS,
    ):
        # … existing archive body (tar, _mark_as_archived, return body) …
finally:
    await self._release_ownership_lock(archive_lock_key, lock_value)
```

The 409 string body is preserved verbatim so the PHP cron's `stripos('already been archived')` match (line 375 of `3_archive_eligible_domains.php`) still works. The success response body shape (`archive_status`, `archive_size_bytes`) is unchanged.

### 5.5 nginx config changes

Two files updated in parity per project convention:

- `apps-microservices/api-gateway-go/nginx.conf` (currently in routing path)
- `apps-microservices/api-gateway/nginx.conf` (legacy, kept in sync)

Add a regex location ahead of the existing `/crawler/` prefix location:

```nginx
# Long-running synchronous endpoints — POST retry must NOT happen at nginx layer.
# Each retry would hit a different backend replica, which acquires a fresh lock
# after the previous replica's lock TTL expires, causing concurrent tar + cleanup
# race (incident: crawl 6250, 2026-05-20). Lock + heartbeat handle replica-side
# serialization. PHP client is responsible for any retry policy.
location ~ ^/crawler/(stash|unstash|archive)/ {
    set $crawler_backend "http://crawler-service:8503";
    rewrite ^/crawler/(.*) /$1 break;

    proxy_pass $crawler_backend;
    proxy_next_upstream off;
    proxy_read_timeout 14400s;       # matches LOCK_HEARTBEAT_MAX_DURATION_SECONDS
    proxy_connect_timeout 60s;
    proxy_send_timeout 14400s;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Existing default crawler routing — unchanged.
location /crawler/ {
    ...
    proxy_next_upstream error timeout http_503 non_idempotent;
    proxy_read_timeout 600s;
    ...
}
```

### 5.6 Dead-code deletion

`apps-microservices/crawler-service/nginx.conf` is not mounted in `docker-compose.yml` (no `crawler-service-lb` container exists, unlike `api-classification-lb`, `api-rest-milvus-lb`, `nextjs-formulaire-hp-lb`). The only reference outside of graphify artifacts is a single mention in `apps-microservices/crawler-service/README.md` line 19. Delete the file and update the README to avoid future operator confusion about which nginx config controls crawler routing.

## 6. Behavior Under Common Scenarios

### 6.1 Tar runs longer than PHP curl timeout (5 min)

1. PHP CURL drops at 300 s, returns `http_code = 0`.
2. `callArchiveEndpoint` (line 39) sees non-503 → no retry → returns failure to the cron loop.
3. Cron logs `[GCP] ERREUR : ...` for that domain, increments `stats_domaines_erreurs`, leaves `est_archiver = 0`, continues to next domain.
4. nginx upstream stays connected (no client to forward to) — backend keeps tarring. Lock TTL is being refreshed by heartbeat.
5. Tar completes server-side. `_mark_as_archived` flips Redis status to `archived`. Upload daemon picks the tar up and pushes to GCS.
6. Next cron tick re-POSTs `/archive/{id}`. Backend pre-check sees `status == 'archived'` → returns 409 with body `"Crawl '{id}' has already been archived."`.
7. PHP cron `stripos('already been archived')` matches → cleanup Ecritel + UPDATE `est_archiver = 1`.

Net effect: that domain shows one transient error in stats, no data loss, self-heals on next tick.

### 6.2 Replica crash mid-tar

1. Heartbeat task is part of the crashing process — dies with it.
2. No further `EXPIRE` calls → TTL elapses at 1800 s.
3. Redis evicts `archive_lock:{id}` (or `stash_lock:{id}`).
4. Next caller's `_acquire_ownership_lock` succeeds. Operation re-runs from scratch.

No zombie lock. No manual cleanup needed.

### 6.3 nginx no-retry effective for stash

1. Client POSTs `/crawler/stash/{id}`.
2. Replica A acquires lock, starts tar, heartbeat running.
3. nginx `proxy_read_timeout` is 14400 s — far longer than any plausible tar duration. nginx waits.
4. Client (e.g. curl with `--max-time 60`) drops at 60 s. nginx detects client disconnect — backend keeps tarring.
5. No retry because `proxy_next_upstream off` is set on this regex location.
6. Backend finishes, persists state. Next operator query (`GET /status/{id}`) shows the result.

### 6.4 Concurrent stash request during in-flight operation

1. Replica A holds `stash_lock:{id}` with heartbeat renewing.
2. Client retries (or duplicate POST) hits Replica B via load balancer.
3. Replica B's `_acquire_ownership_lock` sees `stash_lock:{id}` present, returns `None`.
4. Replica B raises 409 `OPERATION_IN_PROGRESS`. Client receives it.

### 6.5 Heartbeat itself fails (Redis transient outage)

1. Heartbeat's Lua `eval` raises. Helper logs warning, continues the loop.
2. If outage persists past TTL (1800 s), lock expires while op is running. Another replica could acquire fresh lock and start a concurrent op.
3. Mitigation: the concurrent replica's `_create_stash_archive` writes to its own `.staging/{id}.tar.gz` then atomic-moves to `/app/stash/{id}.tar.gz` — `os.rename` is atomic on the same filesystem, the last writer wins. Cleanup still races, but is a worse-case the operator was already exposed to. Out of scope for this spec; observable via the `Lock '...' no longer owned by us` log line for ops alerting.

## 7. Testing Strategy

### 7.1 Unit tests (`tests/test_lock_heartbeat.py`, new file)

- `test_heartbeat_renews_ttl_via_lua_cas` — happy path, ≥ 2 renewals over 2.5 s with interval = 1 s.
- `test_heartbeat_stops_on_value_mismatch` — Lua returns 0 → heartbeat exits.
- `test_heartbeat_stops_at_max_duration` — bounded renewal count past max_duration.
- `test_heartbeat_tolerates_transient_redis_error` — `ConnectionError` once, recovers.
- `test_heartbeat_cancels_cleanly_on_exit` — `__aexit__` cancels and awaits.

### 7.2 Integration tests

`tests/test_crawler_manager_stash.py` additions:

- `test_stash_holds_lock_during_long_tar` — mock tar sleeps 4 s, TTL = 2 s, heartbeat interval = 0.5 s; concurrent caller gets 409 throughout.
- `test_stash_releases_lock_on_replica_crash_simulation` — acquire lock manually without heartbeat, sleep past TTL, verify re-acquire succeeds.
- `test_stash_response_shape_unchanged` — assert 200 body keys and 409 detail string.

`tests/test_crawler_manager.py` (or `test_archive_crawl.py`) additions:

- `test_archive_holds_lock_during_long_tar` — mirror stash test.
- `test_archive_409_body_string_unchanged` — verifies the PHP-matched substring `"already been archived"` and `"is already in progress"` remain.
- `test_archive_lock_ownership_safe_release` — release with wrong replica-id is rejected.

### 7.3 Manual smoke (post-deploy)

```bash
# 1. Trigger stash with short client timeout (simulate client drop)
curl -X POST https://api.hellopro.eu/{SERVICE_CRAWLING}/stash/{big_crawl_id} --max-time 60

# 2. Watch Redis lock state
redis-cli TTL stash_lock:{big_crawl_id}    # hovers near 1800, refreshed every 300s

# 3. Tail logs across replicas
for n in 1 2 3 4 5 6 7; do
    docker logs crawler-service-$n 2>&1 | grep -E "(stash|heartbeat)" | tail -20 &
done

# 4. Verify exactly one replica processed the op
```

### 7.4 Pre-cutover gates

- `nginx -t` on both gateway containers → OK.
- `python -c "from app.core.config import settings; print(settings.STASH_LOCK_TTL_SECONDS, settings.LOCK_HEARTBEAT_INTERVAL_SECONDS)"` → `1800 300`.
- PHP cron dry-run on a known-archived crawl → 409 path triggers cleanup.

### 7.5 24-hour post-deploy regression watch

- `Failed to create stash archive` count → expect zero in healthy state.
- `FileNotFoundError` in stash/archive paths → expect zero.
- `Lock '...' no longer owned by us` → expect zero outside of explicit takeover scenarios.
- PHP cron `pending_upload` count should not spike (transition through 504-then-cleanup is normal but should be infrequent).

## 8. Error Handling

| Failure | Behavior |
|---|---|
| Redis unavailable at `_acquire_ownership_lock` | 503 surfaces to client; existing behavior unchanged |
| Redis unavailable during heartbeat refresh | Log WARNING, retry on next interval. If lock TTL elapses before recovery, another replica can race. Acceptable given existing exposure |
| Heartbeat task crash (programming bug) | `asyncio.create_task` exception escapes via `__aexit__` await; op proceeds without protection; logged. Out-of-scope to mitigate beyond logging |
| `_LockHeartbeat.__aenter__` itself raises | Op never starts; lock released by outer `finally`. Existing 500 path |
| Tar exception inside the `async with` | `__aexit__` cancels heartbeat; outer `finally` releases lock; 500 returned to client |
| `_release_ownership_lock` finds CAS mismatch (lock already gone) | Returns False; logged. No corruption |

## 9. Implementation Tasks

Native task IDs created during brainstorming. Final plan will refine.

- **T0 (#32)** — Add lock heartbeat config + bump `STASH_LOCK_TTL_SECONDS` + add `ARCHIVE_LOCK_TTL_SECONDS` constant.
- **T1 (#33)** — Implement `_LockHeartbeat` helper + unit tests.
- **T2 (#34)** — Wrap `stash_crawl` tar + cleanup block with `_LockHeartbeat`; new integration test.
- **T3 (#35)** — Migrate `archive_lock:{id}` to ownership-safe pair + `_LockHeartbeat`; preserve PHP cron contract.
- **T4 (#36)** — Update both gateway nginx configs: regex location for stash/unstash/archive with `proxy_next_upstream off` and `proxy_read_timeout 14400s`.
- **T5 (#37)** — Delete `apps-microservices/crawler-service/nginx.conf` + remove README ref.

Dependencies: T0 → T1 → T2, T3. T4 and T5 standalone.

## 10. Out of Scope

- Migrating `archive_crawl` or `stash_crawl` to a true asynchronous BackgroundTasks pattern (would break PHP cron's expectation of an `archive_status` in the immediate response body).
- Adding webhook callbacks for archive/stash completion.
- Removing `_archive_locks` in-process threading mutex (line 129 of `crawler_manager.py`) — that protects file-write atomicity, not the cross-replica race.
- PHP cron retry logic changes — current behavior tolerates the fix.
- Unstash heartbeat — covered by lower exposure; reconsider if `UNSTASH_TIMEOUT_SECONDS` is ever raised above the nginx upstream timeout.
- Prometheus counters for heartbeat health — operational logging is the project convention (cf. `UNSTASH_GCS_ORPHAN` precedent).
