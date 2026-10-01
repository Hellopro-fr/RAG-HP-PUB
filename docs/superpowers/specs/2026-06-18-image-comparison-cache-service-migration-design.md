# Design — image-comparison-service: migrate Redis access to `common_utils.redis.cache_service`

**Date:** 2026-06-18
**Status:** Validated (design)
**Author:** Rindra + Claude
**Scope:** S2 — shared-client swap + counter safety. (NOT the stale-job watchdog / download-timeout / feature-cache work — those are a separate design.)
**Service:** `apps-microservices/image-comparison-service` (RAG-HP-PUB).

---

## 1. Objective

Replace image-comparison-service's private, inline Redis client (`redis.asyncio.from_url(...)` in `JobManager`) with the **shared, hardened** `common_utils.redis.cache_service` module — the same one `crawler-service` uses. Gains: a **bounded connection pool**, **socket timeouts**, **keepalive + proactive health-check reconnect**, and a per-replica **`client_name`** — none of which the bare `from_url` has. Also adopt **`safe_decrement_key`** for the global running-count so it can never go negative / leak.

Hard requirement: keep Redis **keys, TTL, JSON wire-format, and the `/start` / `/status` / `/results` HTTP contract byte-identical** so BO callers (Ch.D dedup + the FP arsenal) and cross-replica polling are unaffected.

## 2. Context (verified)

### 2.1. Current state — `app/core/job_manager.py`
- `JobManager.connect_redis()` → `self.redis = redis.asyncio.from_url(settings.REDIS_URL, decode_responses=True)`. `main.py` startup calls `connect_redis()`, shutdown `close_redis()`.
- Keys: `job:{id}:status`, `job:{id}:result` (`ex=JOB_RESULT_TTL`, 24h); `comparator:running_count` via raw `incr`/`decr`.
- In-process (NOT Redis): `asyncio.Semaphore(MAX_CONCURRENT_JOBS)`, `local_active_jobs`, `try_acquire_local_slot` / `release_local_slot`.
- **Gaps vs the shared client:** no `max_connections` (unbounded pool → leak risk); no `socket_timeout` / `socket_connect_timeout` (a hung Redis op can wedge a job — a plausible contributor to the rare `HTTP 0 / poll-deadline`); no `socket_keepalive` / `health_check_interval` (stale connections after idle/network blips); no `client_name`; `decr` can drive `comparator:running_count` below zero / leak on a killed process.

### 2.2. Target — `libs/common-utils/src/common_utils/redis/cache_service.py`
- Module-global `redis_client` + `init_redis_pool()` / `close_redis_pool()`. `init_redis_pool` builds `redis.from_url(REDIS_URL, decode_responses=True, max_connections=REDIS_MAX_CONNECTIONS|20, socket_keepalive=True, socket_connect_timeout=5, socket_timeout=10, health_check_interval=30, client_name=<SERVICE_NAME>-<HOSTNAME>)`, pings, registers Lua scripts; re-pings if already initialized; closes a half-built client on failure (→ `redis_client=None`).
- Helpers: `set_json/get_json/set_json_nx/set_key/get_key/delete_key/scan_keys_by_prefix/increment_key/decrement_key/**safe_decrement_key**` (Lua, floor-0) / `**delete_if_terminal**` (Lua, deletes only if status `finished|failed`) / `publish/cache_or_execute`.

### 2.3. Reference wiring — `crawler-service`
- `main.py`: `from common_utils.redis.cache_service import init_redis_pool, close_redis_pool` → startup `await init_redis_pool()`, shutdown `await close_redis_pool()`. `from common_utils.redis import cache_service` then `cache_service.redis_client.<op>` + helpers. `crawler_manager` uses `safe_decrement_key` for the running-count.
- Dockerfile install pattern (build context = repo root):
  ```dockerfile
  COPY libs/common-utils /app/libs/common-utils
  RUN pip install -e /app/libs/common-utils
  ```

## 3. Design (S2)

### 3.1. `apps-microservices/image-comparison-service/Dockerfile`
Insert after the `apt-get` block, **before** `COPY apps-microservices/image-comparison-service/requirements.txt .` (build context is already repo-root, matching the existing `COPY apps-microservices/...` lines):
```dockerfile
# Shared lib (Redis cache_service, etc.)
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
```

### 3.2. `main.py`
- Add `from common_utils.redis.cache_service import init_redis_pool, close_redis_pool`.
- `startup_event`: replace `await job_manager.connect_redis()` → `await init_redis_pool()`.
- `shutdown_event`: replace `await job_manager.close_redis()` → `await close_redis_pool()`.

### 3.3. `app/core/job_manager.py`
- Remove `import redis.asyncio as redis`, the `self.redis` field (and its `Optional[redis.Redis]` hint), `connect_redis()`, `close_redis()`.
- Add `from common_utils.redis import cache_service`.
- Replace **every** `self.redis.<op>` with `cache_service.redis_client.<op>` — identical operations; **status/result writes keep the exact `Model.json()` serialization** (`cache_service.redis_client.set(f"job:{id}:status", JobStatus(...).json(), ex=...)`). Replace `if (not) self.redis` guards with `if (not) cache_service.redis_client`.
- **Counter (S2):** keep INCR as `cache_service.redis_client.incr(GLOBAL_RUNNING_COUNT_KEY)` (under the existing `if cache_service.redis_client:` guard); change the `finally` DECR to `await cache_service.safe_decrement_key(GLOBAL_RUNNING_COUNT_KEY)` (Lua floor-0 → never negative).
- **Unchanged:** `__init__` semaphore + `local_active_jobs`, `try_acquire_local_slot` / `release_local_slot` / `is_local_full`, all job logic, keys, TTL.

### 3.4. `docker-compose.yml`
`image-comparison-service.environment` += `SERVICE_NAME=image-comparison-service` (so `client_name` in Redis `CLIENT LIST` is `image-comparison-service-<host>`; without it the lib falls back to the literal `crawler-py`). Pool/timeout env (`REDIS_MAX_CONNECTIONS`, …) left at defaults.

### 3.5. The load-bearing gotcha
`cache_service.redis_client` is a **module global set at startup by `init_redis_pool()`**. Access it as a **module attribute at call time** — `from common_utils.redis import cache_service` then `cache_service.redis_client`. **Never** `from common_utils.redis.cache_service import redis_client` (that binds `None` at import, before init). All `JobManager` Redis ops are async and run post-startup, so the attribute is populated.

## 4. Behavior preservation
- Keys (`job:{id}:status`, `job:{id}:result`, `comparator:running_count`), TTL (`JOB_RESULT_TTL`), and status/result JSON shape (Pydantic `.json()`) — **unchanged** → BO client + cross-replica poll see identical data.
- The `/start` / `/status` / `/results` router contract — untouched (no router changes).
- Minor, intentional difference: counter ops via the shared layer are **best-effort** (the helper logs + returns on a Redis error rather than raising). Acceptable — the counter is advisory (the client never gates on it), and the floor-0 safety is the point.
- `requirements.txt` keeps its `redis` line (harmless; `common_utils` also declares it). No need to touch.

## 5. Verification (remote — RAG-HP-PUB)
- `python -m py_compile main.py app/core/job_manager.py`.
- **`docker build`** the service on the VM (build context = repo root) — proves `common_utils` installs and all imports resolve. This is the key build check (cannot build locally).
- Run image-comparison-service's test suite if one exists.
- Smoke (deploy): `GET /capacity` + one real compare job → logs show `Successfully connected to Redis`, `CLIENT LIST` shows `client_name=image-comparison-service-<host>`, status/result round-trip OK, `comparator:running_count` stays ≥ 0.

## 6. Blast radius / out of scope
- **image-comparison-service only.** Contract + key schema unchanged → BO consumers (Ch.D dedup, FP arsenal `isImagesSimilars*` / `batchCompareImagesMicroservice`) unaffected. `common_utils` is an already-proven shared dependency (crawler-service et al.).
- The bounded pool (default `max_connections=20`) is far above this service's need (`MAX_CONCURRENT_JOBS=4`/replica) — no throttling risk.
- **Out of scope (separate design, already discussed):** stale-job watchdog / reconcile loop (the `HTTP 0` poll-deadline fix), download-timeout tightening + per-image cap, feature/pHash cache, concurrency tuning. **S2 sets the watchdog up cheaply** — `delete_if_terminal`, `scan_keys_by_prefix`, and `safe_decrement_key` (the exact building blocks crawler's `reconcile_jobs` uses) are now available to image-comparison.

---

**End design — 2026-06-18.**
