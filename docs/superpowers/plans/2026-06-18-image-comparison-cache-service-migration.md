# image-comparison-service → common_utils.redis.cache_service Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace image-comparison-service's inline `redis.asyncio.from_url` with the shared, hardened `common_utils.redis.cache_service` (bounded pool + socket timeouts + keepalive/health-check + `client_name`), and use `safe_decrement_key` for `comparator:running_count`. Keep keys/TTL/JSON/contract byte-identical.

**Architecture:** Drop `JobManager`'s private client + `connect_redis`/`close_redis`; wire the module-global `cache_service` via `init_redis_pool()`/`close_redis_pool()` in `main.py`; route all Redis ops through `cache_service.redis_client` (accessed as a module attribute at call time). In-process semaphore/`local_active_jobs` untouched. Scope S2 — no watchdog/perf work.

**Tech Stack:** Python 3.11, FastAPI, redis.asyncio (via `common_utils`), Docker. RAG-HP-PUB monorepo, branch `features/poc`. Build context = repo root.

Ref spec: `docs/superpowers/specs/2026-06-18-image-comparison-cache-service-migration-design.md`. Pattern source: `apps-microservices/crawler-service/{main.py,Dockerfile}`; API: `libs/common-utils/src/common_utils/redis/cache_service.py`.

**Repo root:** `D:\DevHellopro\Workspaces\RAG-HP-PUB` (all paths below are relative to it). Commits **both EN+FR**; do NOT push (user controls push/deploy).

**Remote-only:** local check = `python -m py_compile` (if Python present locally; else careful review). The real verification — `docker build` + deploy smoke — runs on the VM (user). No local Redis/build.

**Dependencies:** T2 ← T1 (the `common_utils` install must exist before the code imports it).

---

### Task 1: Build infra — install common_utils + set SERVICE_NAME

**Goal:** Make `common_utils` importable in the image and set the Redis client name, with ZERO behavior change (code still uses the old client until T2).

**Files:**
- Modify: `apps-microservices/image-comparison-service/Dockerfile`
- Modify: `docker-compose.yml` (the `image-comparison-service` service block)

**Acceptance Criteria:**
- [ ] Dockerfile copies `libs/common-utils` and `pip install -e`s it, BEFORE the requirements install.
- [ ] `docker-compose.yml` `image-comparison-service.environment` includes `SERVICE_NAME=image-comparison-service`.
- [ ] No Python code changed → service still builds and runs identically (common_utils present but unused).

**Verify:** (remote, user) `docker build -f apps-microservices/image-comparison-service/Dockerfile .` from repo root → builds; `python -c "import common_utils.redis.cache_service"` inside the image succeeds. Locally: visual diff only.

**Steps:**

- [ ] **Step 1: Dockerfile — add the shared-lib install**

In `apps-microservices/image-comparison-service/Dockerfile`, the current block is:
```dockerfile
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps-microservices/image-comparison-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```
Insert the shared-lib install between the apt-get block and the requirements copy, so it becomes:
```dockerfile
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Shared lib (Redis cache_service, etc.) — installed editable, like crawler-service
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Install Python dependencies
COPY apps-microservices/image-comparison-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

- [ ] **Step 2: docker-compose.yml — add SERVICE_NAME**

In `docker-compose.yml`, the `image-comparison-service` block's `environment:` is:
```yaml
    environment:
      - MAX_CONCURRENT_JOBS=4
      - REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}
```
Add the `SERVICE_NAME` line:
```yaml
    environment:
      - MAX_CONCURRENT_JOBS=4
      - REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}
      - SERVICE_NAME=image-comparison-service
```

- [ ] **Step 3: Commit (both EN+FR)**

```bash
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" add apps-microservices/image-comparison-service/Dockerfile docker-compose.yml
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" commit -m "build(image-comparison): install common_utils + SERVICE_NAME" -m "EN: Install the shared common_utils lib (editable) in the image-comparison-service image and set SERVICE_NAME for the Redis client_name, ahead of the cache_service migration. No code change yet.

FR: Installe la lib partagee common_utils (editable) dans l'image image-comparison-service et definit SERVICE_NAME pour le client_name Redis, en amont de la migration cache_service. Aucun changement de code pour l'instant."
```

---

### Task 2: Code — migrate JobManager + main.py to cache_service

**Goal:** Replace the private Redis client with `cache_service`; counter via `safe_decrement_key`. Behavior byte-identical.

**Files:**
- Modify: `apps-microservices/image-comparison-service/main.py`
- Modify: `apps-microservices/image-comparison-service/app/core/job_manager.py`

**blockedBy:** Task 1.

**Acceptance Criteria:**
- [ ] `main.py` startup calls `init_redis_pool()`, shutdown calls `close_redis_pool()` (no more `job_manager.connect_redis/close_redis`).
- [ ] `job_manager.py`: `import redis.asyncio as redis`, `self.redis`, `connect_redis()`, `close_redis()` removed; `from common_utils.redis import cache_service` added.
- [ ] Every Redis op uses `cache_service.redis_client.<op>` (status/result keep `.json()`); guards use `cache_service.redis_client`.
- [ ] Global counter: INCR via `cache_service.redis_client.incr(...)`; the `finally` DECR via `await cache_service.safe_decrement_key(...)`.
- [ ] Semaphore / `local_active_jobs` / `try_acquire_local_slot` / `release_local_slot` / `is_local_full` / keys / TTL / router contract unchanged.
- [ ] `cache_service.redis_client` accessed as a module attribute at call time (never imported by name).
- [ ] `python -m py_compile` clean on both files.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/main.py apps-microservices/image-comparison-service/app/core/job_manager.py` → no output (success). Then (remote, user) `docker build` + deploy smoke: `GET /capacity` + one compare job → logs `Successfully connected to Redis`; `CLIENT LIST` shows `name=image-comparison-service-<host>`; `job:{id}:status`/`result` round-trip; `comparator:running_count` stays ≥ 0.

**Steps:**

- [ ] **Step 1: main.py — wire init/close_redis_pool**

In `apps-microservices/image-comparison-service/main.py`, after the existing import `from app.core.job_manager import job_manager` add:
```python
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool
```
Change `startup_event`:
```python
@app.on_event("startup")
async def startup_event():
    logger.info("Image Comparison Service starting up.")
    await init_redis_pool()
```
Change `shutdown_event`:
```python
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Service shutting down.")
    await close_redis_pool()
```

- [ ] **Step 2: job_manager.py — imports + remove private client**

Top of `app/core/job_manager.py`: remove the line `import redis.asyncio as redis`. Add (with the other `from app.core...`/`from common_utils...` imports):
```python
from common_utils.redis import cache_service
```
In `class JobManager.__init__`, remove the line:
```python
        self.redis: Optional[redis.Redis] = None
```
(Keep `self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)` and `self.local_active_jobs = 0`. Keep `from typing import Optional` — still used by return hints.)

Delete the two methods entirely:
```python
    async def connect_redis(self):
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info(f"Connected to Redis at {settings.REDIS_URL}")

    async def close_redis(self):
        if self.redis:
            await self.redis.close()
```

- [ ] **Step 3: job_manager.py — swap reads (get_capacity / get_job_status / get_job_result / list_jobs)**

`get_capacity`:
```python
        global_count = 0
        if cache_service.redis_client:
            val = await cache_service.redis_client.get(GLOBAL_RUNNING_COUNT_KEY)
            global_count = int(val) if val else 0
```
`get_job_status`:
```python
    async def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        if not cache_service.redis_client: return None
        data = await cache_service.redis_client.get(f"job:{job_id}:status")
        if not data: return None
        return JobStatus(**json.loads(data))
```
`get_job_result`:
```python
    async def get_job_result(self, job_id: str) -> Optional[ComparisonResult]:
        if not cache_service.redis_client: return None
        data = await cache_service.redis_client.get(f"job:{job_id}:result")
        if not data: return None
        return ComparisonResult(**json.loads(data))
```
`list_jobs` — replace the three `self.redis` references:
```python
    async def list_jobs(self, limit: int = 100) -> List[JobStatus]:
        """Scans Redis for all job statuses."""
        if not cache_service.redis_client: return []

        job_keys = []
        async for key in cache_service.redis_client.scan_iter("job:*:status", count=limit):
            job_keys.append(key)
            if len(job_keys) >= limit:
                break

        if not job_keys:
            return []

        jobs_data = await cache_service.redis_client.mget(job_keys)

        results = []
        for data in jobs_data:
            if data:
                try:
                    results.append(JobStatus(**json.loads(data)))
                except Exception:
                    continue
        return results
```

- [ ] **Step 4: job_manager.py — process_job_logic (counter + status/result writes)**

Counter INCR (the `# Increment Global Counter` block):
```python
        # Increment Global Counter
        if cache_service.redis_client:
            await cache_service.redis_client.incr(GLOBAL_RUNNING_COUNT_KEY)
```
The four status/result writes inside the `try`/`async with self.semaphore` — change each `await self.redis.set(...)` to `await cache_service.redis_client.set(...)`, keeping the `.json()` payloads and `ex=` exactly:
```python
                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=10.0).json(),
                        ex=settings.JOB_RESULT_TTL
                    )
```
```python
                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=40.0).json(),
                        ex=settings.JOB_RESULT_TTL
                    )
```
```python
                    ttl = settings.JOB_RESULT_TTL
                    await cache_service.redis_client.set(f"job:{job_id}:result", result.json(), ex=ttl)
                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="finished", progress=100.0).json(),
                        ex=ttl
                    )
```
The `except` block's failed-status write:
```python
                    await cache_service.redis_client.set(f"job:{job_id}:status", error_status.json(), ex=settings.JOB_RESULT_TTL)
```
The `finally` block — DECR becomes the floor-0 helper (S2):
```python
        finally:
            if cache_service.redis_client:
                await cache_service.safe_decrement_key(GLOBAL_RUNNING_COUNT_KEY)
```

- [ ] **Step 5: job_manager.py — submit_job_async / submit_job_sync initial status write**

In both `submit_job_async` and `submit_job_sync`, change the initial status write:
```python
        initial_status = JobStatus(job_id=job_id, status="queued", progress=0.0)
        await cache_service.redis_client.set(f"job:{job_id}:status", initial_status.json(), ex=settings.JOB_RESULT_TTL)
```
(The rest — `self.local_active_jobs += 1`, `asyncio.create_task(...)` in async; `return await self.process_job_logic(...)` in sync — unchanged.)

- [ ] **Step 6: Verify py_compile**

Run: `python -m py_compile apps-microservices/image-comparison-service/main.py apps-microservices/image-comparison-service/app/core/job_manager.py`
Expected: no output, exit 0. (If `python` is unavailable locally, do a careful read confirming no remaining `self.redis` / `import redis` references: `grep -n "self.redis\|import redis" apps-microservices/image-comparison-service/app/core/job_manager.py` → no matches.)

- [ ] **Step 7: Commit (both EN+FR)**

```bash
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" add apps-microservices/image-comparison-service/main.py apps-microservices/image-comparison-service/app/core/job_manager.py
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" commit -m "refactor(image-comparison): migrate Redis to common_utils cache_service" -m "EN: JobManager + main.py now use the shared common_utils.redis.cache_service (init/close_redis_pool, cache_service.redis_client) instead of an inline redis.from_url; comparator:running_count decrement via safe_decrement_key (floor-0). Keys/TTL/JSON/contract unchanged.

FR: JobManager + main.py utilisent desormais le module partage common_utils.redis.cache_service (init/close_redis_pool, cache_service.redis_client) au lieu d'un redis.from_url inline ; decrement de comparator:running_count via safe_decrement_key (plancher 0). Cles/TTL/JSON/contrat inchanges."
```

---

## Self-Review (done)

**1. Spec coverage:** §3.1 Dockerfile → T1 Step 1. §3.4 compose SERVICE_NAME → T1 Step 2. §3.2 main.py → T2 Step 1. §3.3 job_manager (imports/remove client → T2.2; reads → T2.3; counter+writes → T2.4; submit writes → T2.5; INCR raw / DECR safe_decrement_key → T2.4) ✓. §3.5 call-time-attribute gotcha → enforced by always writing `cache_service.redis_client` (never a bare import) ✓. §4 behavior preservation (keys/TTL/.json()) → preserved verbatim in every edit ✓. §5 verification → T1/T2 Verify ✓.

**2. Placeholders:** none — every step shows the exact before/after code.

**3. Type/name consistency:** `cache_service.redis_client` used uniformly; `safe_decrement_key` is the real helper name; `GLOBAL_RUNNING_COUNT_KEY` / `settings.JOB_RESULT_TTL` / key strings reused verbatim from the current file; `init_redis_pool`/`close_redis_pool` match the lib. Removed-symbol check: after T2, no `self.redis` / `import redis.asyncio` remain (grep in Step 6).

**Out of scope (per spec §6):** stale-job watchdog/reconcile, download-timeout/per-image cap, feature cache, concurrency tuning — separate design.
