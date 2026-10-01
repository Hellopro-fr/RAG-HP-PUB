# content-extractor-api-service — docker-compose Redis env wiring (Design)

- **Date:** 2026-06-22
- **Status:** Approved (design); pending implementation plan
- **Service:** `apps-microservices/content-extractor-api-service`
- **Cross-repo touch:** none (single `docker-compose.yml` service block)
- **Author:** Tech Lead (brainstorm session)
- **Related:** `docs/superpowers/specs/2026-06-20-content-extractor-async-cache-design.md` (the feature this completes the deployment of)

---

## 1. Problem & diagnosis

The async-cache effort (2026-06-20 spec, 12 tasks, commits `f784b635` → `29d6a6c7`) shipped Redis-backed code into the service — result cache + async job store — but the `docker-compose.yml` entry for `content-extractor-api-service` was never given the Redis environment variable. Its `environment:` block (L607-610) carries only:

```yaml
    environment:
      - PORT=8600
      - LOG_LEVEL=info
      - MAX_PAYLOAD_SIZE_MB=10
```

### 1.1 Root cause (verified against the code)

`common_utils.redis.cache_service.init_redis_pool()` reads the connection string from the **process environment directly**, not from the service's pydantic `Settings`:

```python
# libs/common-utils/src/common_utils/redis/cache_service.py:87-90
redis_url = os.getenv("REDIS_URL")
if not redis_url:
    logger.critical("REDIS_URL environment variable not set. Caching and state management will be unavailable.")
    redis_client = None
```

Consequences when `REDIS_URL` is unset in the container:

1. `redis_client` is set to `None` and a `CRITICAL` log line is emitted at startup.
2. Every async submit (`/clean-async`, `/extract/header-footer-async`) returns `503` **without** `Retry-After` (the "Redis unavailable" discriminator from the 2026-06-20 spec §7.4).
3. The result cache silently degrades to cache-less on both sync and async paths (graceful-degrade guard in `result_cache`).

The service's `Settings.REDIS_URL` default (`config.py:16`, `"redis://redis:6379"`) is **dead weight** — the pool never consults `Settings`; it reads `os.getenv` itself. The in-code comment at `config.py:14-15` already records this ("`cache_service.init_redis_pool()` reads REDIS_URL from the environment itself; this mirrors it for documentation"). So the config default cannot rescue a missing compose env var.

### 1.2 Established convention (what the fix mirrors)

Every other Redis-using service in `docker-compose.yml` sets the Redis URL with the identical composed line — 18 occurrences across the file (some are replica-variant blocks of the same service):

```yaml
      - REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}
```

The `REDIS_SECRET` / `REDIS_HOST` / `REDIS_PORT` primitives live in the deploy-time `.env` (not committed; gitignored). `image-comparison-service` (L1386-1389) is the closest peer — it sets `REDIS_URL` + `SERVICE_NAME` (plus its service-specific `MAX_CONCURRENT_JOBS`). `content-extractor-api-service` is the lone Redis-using service missing the line entirely.

Redis is **external** — there is no `redis` service defined in `docker-compose.yml`; the host comes from `REDIS_HOST`. So `Settings.REDIS_URL`'s `redis://redis:6379` default would not resolve even if it were consulted.

---

## 2. Goals / non-goals

### Goals
1. Wire `content-extractor-api-service` to the real authenticated Redis so the result cache and async job store function in deployment.
2. Do so with the smallest diff that matches the repo-wide convention.

### Non-goals
- No application code change (the Redis code already shipped and is correct).
- No async-staging flag change — `ASYNC_JOBS_ENABLED` stays at its `true` default (see §5).
- No `deploy:` replicas / resource-limit block (deferred — see §6).
- No api-gateway change — the `extractor-service: 60` downstream timeout is a separate, already-landed item (`api-gateway-go` commit `d6120318`, per 2026-06-20 spec §14).

---

## 3. Decision (locked in brainstorm)

**Option 1 — Minimal, convention-matching.** Add exactly two lines to the `environment:` block: the composed `REDIS_URL` and `SERVICE_NAME`. Everything else keeps its `config.py` / `Dockerfile` default, and remains tunable via the already-present `env_file: .env` without touching tracked compose.

Rejected alternatives:
- **Explicit ops knobs** (pin `UVICORN_WORKERS` / `ASYNC_JOBS_ENABLED` / `MAX_ACTIVE_JOBS` / `RESULT_CACHE_ENABLED` in compose): duplicates `config.py` defaults → two sources of truth that can drift; the same knobs are already settable via `.env`. Violates DRY for marginal discoverability gain.
- **Full mirror + `deploy:` block** (replicas + CPU/mem limits): premature. The only live caller (Hellopro BO `script_build_jsonl_header_footer.php:163`) is **synchronous and low-volume**; the crawler ×7 async consumer that justifies replicas does not exist yet (2026-06-20 spec §2 non-goal). `replicas: 1` is a no-op (Compose default), and `cpus`/`memory` limits would be uncalibrated guesses — the 2026-06-20 spec §12 says to measure p95 first (debug/fallback chain can double CPU; uncalibrated limits risk throttling valid slow extractions).

---

## 4. The change

`docker-compose.yml`, service `content-extractor-api-service`, `environment:` block:

```yaml
    environment:
      - PORT=8600
      - LOG_LEVEL=info
      - MAX_PAYLOAD_SIZE_MB=10
      - SERVICE_NAME=content-extractor-api-service
      - REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}
    env_file:
      - .env
```

- **`REDIS_URL`** — the fix. Composed from deploy-`.env` primitives; identical to the repo-wide convention. Read by `cache_service.init_redis_pool()` at startup.
- **`SERVICE_NAME`** — `cache_service.py:44` uses it for worker/owner identity in the shared Redis; unset falls back to `"crawler-py"`, mislabeling this service. `image-comparison-service` sets it for the same reason.

`env_file: .env` (L611-612) is preserved. No other line changes.

### Data flow after the fix
deploy `.env` (`REDIS_SECRET` / `REDIS_HOST` / `REDIS_PORT`) → Compose interpolation → `REDIS_URL` in container env → `init_redis_pool()` connects → `redis_client` live → result cache active on sync **and** async paths; async job store functional. `UVICORN_WORKERS` stays `2` via `Dockerfile:28` (`--workers ${UVICORN_WORKERS:-2}`); all other knobs hold `config.py` defaults.

---

## 5. `ASYNC_JOBS_ENABLED` — left at default `true` (rationale)

The 2026-06-20 spec §17 staged async off first. That staging is unnecessary here: async live is **inert** — no crawler caller submits jobs, so there is zero blast radius on the live BO sync path. The component that benefits the live sync caller is the **result cache**, which is independent of the async flag. Staging only matters when the staged thing has blast radius; async here has none. So `ASYNC_JOBS_ENABLED` is left at its `true` default, and the async endpoints simply become functional (and idle) once Redis is wired.

---

## 6. Blast radius / risk

- **Scope:** one `docker-compose.yml` service block. Zero application, Dockerfile, or cross-service change.
- **Placeholders proven:** every other Redis-using service already interpolates `${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}` → the primitives exist in the deploy `.env`.
- **Network/profiles:** Redis is external (no `redis` compose service); reachable from both profiles the service declares (`["app", "crawling"]`).
- **Degraded path unchanged:** if `REDIS_*` were ever unset at deploy, Compose interpolates empty → malformed URL → `init_redis_pool` ping fails → `redis_client=None` → graceful degrade (sync works cache-less; async `503` without `Retry-After`). No worse than the current (broken) state.
- **Async activation:** goes live at default `true`, but inert (no caller). Result cache begins serving the live BO sync path immediately.

---

## 7. Verification

- **Static (local):** `docker compose config` resolves `REDIS_URL` with no `variable is not set` warning.
- **Post-deploy smoke (operator, on the VM):**
  1. Container startup logs **must NOT** contain `REDIS_URL environment variable not set` (`cache_service.py:89`) — the single line that proves/disproves the fix.
  2. `GET /health` → `200`.
  3. `POST /clean` with the same payload twice → second response is a cache hit; `extract_cache_hits_total` increments.
  4. `POST /clean-async` with one item → `202 {job_id}` → poll `GET /jobs/{job_id}` → `completed` (proves the Redis job store is live).

---

## 8. Testing

No pytest change. A `docker-compose.yml` environment line is not application code (the `tdd-gate` hook targets Edit/Write on production code, not YAML). Validation is the §7 static check + post-deploy smoke.

---

## 9. Files touched (summary)

**RAG-HP-PUB (`features/poc`):**
- `docker-compose.yml` — two lines added to the `content-extractor-api-service` `environment:` block.

**Hellopro / other repos:** none.
