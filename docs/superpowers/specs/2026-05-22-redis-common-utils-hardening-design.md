# Redis Connection Layer Hardening — `common_utils` + 11-Service Rollout

**Status:** Approved (brainstorm closed 2026-05-22)
**Author:** sandrianirinaharivelo
**Spec location:** `docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md`

## 1. Problem

Production Redis (k8s pod `redis-84dd44c664-gb2ml`) returns:

```
ERR max number of clients reached
```

Audit of 19 services across Python, Go, and Node shows three "camps":

| Camp | Services | Pattern |
|---|---|---|
| A — `common_utils.cache_service` | api-gateway, api-recherche-service, api-classification-service, crawler-service (py) | Shared lib with bounded pool (`REDIS_MAX_CONNECTIONS=20`), named clients, keepalive, shutdown close. |
| B — ad-hoc `redis.from_url` | api-detection-langue-fr, api-rest-milvus, database-recherche-service, 5×qdrant-database, website-processor-service, image-comparison-service, image-download-service | Each service inlines its own `from_url` call. No pool cap, no client name, partial cleanup. |
| C — non-Python | api-gateway-go, crawler-monitor-backend (Go); crawler-service Node subprocess, redis-client-frontend (Node) | Native bounded clients per language. Out of scope for this spec — addressed separately. |

Camp B is the root cause of the connection-cap exhaustion under load. All 11 Camp B services hold singleton clients (no per-request leaks), but their pools are unbounded and unnamed — `CLIENT LIST` cannot attribute leaks to a source service.

## 2. Goals

1. Harden the existing `common_utils.redis.cache_service` async helper so its current behavior is provably correct.
2. Add a **sync** binding in `common_utils` so the 7 sync (pika-based) Camp B services can migrate without rewriting consumers.
3. Standardize client identity to `{service}-{HOSTNAME}-pid{N}` across all replicas for greppable diagnostics.
4. Migrate all 11 Camp B services to the shared lib over 4 rollout tiers.

## 3. Non-Goals

- Replacing redis-py with a gRPC proxy. Already evaluated and rejected (latency tax, new SPOF, redis-py feature reimplementation, diagnostics regression).
- Migrating Camp C (Go/Node). They have native bounded clients. Their drift is tracked separately (`crawler-service/CLAUDE.md` § Deferred follow-ups).
- Rewriting sync RabbitMQ consumers to async. Out of scope; would multiply blast radius.
- Operator-side actions (`CONFIG SET timeout 300`, `tcp-keepalive 60`). Already documented in `crawler-service/CLAUDE.md`; this spec assumes they're applied.

## 4. Findings — `common_utils.redis.cache_service` audit

| # | Requirement | Status | Evidence (`cache_service.py` lines) | Fix |
|---|---|---|---|---|
| 1.a | `max_connections` set explicitly | ✓ | 108 | — |
| 1.b | Configurable via env | ✓ | 93 | Keep `REDIS_MAX_CONNECTIONS` name (4 services + compose use it). |
| 1.c | Default = 20 | ✓ | 21 | — |
| 1.d | Pool exhaustion → reject (not block) | ✓ | redis-py default `ConnectionPool` raises `ConnectionError` immediately | — |
| 2.a | `CLIENT SETNAME` on every new pool conn | ✓ | 113 | — |
| 2.b | Identity format `{service}-{pod}-pid{N}` | ✗ | 44–45 (PID dropped when HOSTNAME present) | **Diff 1.** Append PID unconditionally. |
| 2.c | `service_name` from env, loud on unset | ✗ | 44 (silent fallback to `'crawler-py'`) | **Diff 1.** Warn + use `unset-service` fallback. |
| 3.a | Connection released on every command path | ✓ | redis-py `Redis.execute_command` releases in finally | — |
| 3.b | `scan_iter` releases per RPC | ✓ | 213 | — |
| 3.c | Pipeline helpers expose context manager | n/a | not exposed | Document constraint in module docstring. |
| 3.d | Pubsub subscribe helpers expose close | n/a | not exposed (only publish) | Document. |
| 4.a | PING on acquire or periodic | ✓ | 112 (`health_check_interval=30s`) | — |
| 4.b | Initial connectivity check | ✓ | 115 | — |
| 4.c | Retry with backoff on transient err | ✗ | crawler-service has its own `_redis_call_with_retry` wrapper, not shared | **Diff 2.** Add opt-in `call_with_retry` helper. |
| 4.d | Stale connections evicted from pool | ✓ | redis-py closes on `ConnectionError`/`TimeoutError` | — |
| 5 | TCP keepalive | ✓ | 109 | — |
| 6 | Socket timeouts bounded | ✓ | 110–111 | — |
| 7 | Sync binding for pika consumers | ✗ | only async exists | **Diff 4.** New `cache_service_sync.py`. |
| 8 | Graceful close on partial init failure | ✓ | 124–128 | — |
| 9 | Concurrent `init_redis_pool` calls | partial | 82–85 (no lock between ping and assign) | **Diff 3.** asyncio.Lock guard. |

**Real gaps:** 3 — client identity (2.b/2.c), retry helper (4.c), sync binding (7). Minor: init race (9).

## 5. Design

### 5.1 Identity format change

```
Before: {SERVICE_NAME or 'crawler-py'}-{HOSTNAME or pid-N}
After:  {SERVICE_NAME or 'unset-service'}-{HOSTNAME or 'no-hostname'}-pid{N}
```

- PID always present → multi-worker (gunicorn, uvicorn `--workers >1`) replicas now distinguishable.
- `unset-service` warning surfaces misconfiguration in logs without breaking startup.
- Format is strictly additive (suffix `-pid{N}`). Operators greppling on `^{service}-` still match.

### 5.2 Retry helper

New opt-in helper `call_with_retry(fn, *args, attempts=2, backoff_base_s=0.5, **kwargs)`:
- Retries on `ConnectionError`, `TimeoutError`, `OSError`.
- Other exceptions propagate immediately.
- Backoff: `backoff_base_s * 2**attempt`.
- Existing `set_json`, `get_json`, etc. keep their swallow-on-error semantics — callers opt in by wrapping.

Future cleanup: crawler-service's `_redis_call_with_retry` (`crawler_manager.py:61`) will be replaced by this in a follow-up PR.

### 5.3 Init race guard

Module-level `asyncio.Lock()` wraps `init_redis_pool()`. Microsecond cost at startup; no behavior change at steady state.

### 5.4 Sync binding

New file `libs/common-utils/src/common_utils/redis/cache_service_sync.py`:
- Same env vars, same `_client_name()` logic, same constants.
- Singleton client stored in module-global `redis_client`.
- Exposes `init_redis_pool_sync()`, `close_redis_pool_sync()`, `get_client()`.
- Helpers (set_json_sync, get_json_sync, etc.) **not** included in MVP — sync callers pass `get_client()` into their classes and call `.eval`, `.pipeline`, `.get`, `.set` directly. Add helpers only when a migration demands one.

**Why not full helper parity:** Sync services (qdrant ×5, website-processor, image-download) own custom logic around Lua scripts, pipelines, and rate-limiter sliding windows. Wrapping every redis-py method in a sync helper would duplicate ~200 lines for marginal abstraction value.

### 5.5 Env var name

Keep `REDIS_MAX_CONNECTIONS` (not `REDIS_POOL_MAX`). Already in compose + 4 services. Renaming = drift.

## 6. Migration — 11 Camp B services

### 6.1 Per-service requirements

For each migrated service:

1. Add `SERVICE_NAME=<exact-service-name>` to `docker-compose.yml` env block + Dockerfile `ENV` (or k8s manifest).
2. Replace ad-hoc `*.from_url` with `init_redis_pool[_sync]` from common_utils.
3. Wire shutdown close in FastAPI lifespan / `finally` block.
4. Run service-specific tests + smoke check (`redis-cli CLIENT LIST | grep <service>`).
5. One PR per service (or per coherent batch — see Tier 1) so revert blast radius = 1.

### 6.2 Tier order

| Tier | Services | Risk | Cadence |
|---|---|---|---|
| 1 | 5 qdrant database services (di, document, echange, product, website) | Low — identical sync pattern, batch consumer | 1 PR, all 5 |
| 2 | website-processor-service | Medium — Lua script `LUA_BATCH_SCRIPT` must re-register on new client | 1 PR |
| 3 | image-download-service | Medium — sync pipeline usage, rate limiter | 1 PR |
| 4 | image-comparison-service, database-recherche-service | Medium — async, already shutdown-wired | 2 PRs |
| 5 | api-rest-milvus, api-detection-langue-fr | High — hot path, multiple consumer sites of `redis_client` | 2 PRs, separate deploys |

### 6.3 Per-service gotchas

| Service | Files | Gotchas |
|---|---|---|
| 5 qdrant | `app/main.py:28-37` (each) | None. Bare `sync_redis.from_url` → `init_redis_pool_sync()`. ~10 LOC each. |
| website-processor | `app/core/redis_manager.py` | `register_script(LUA_BATCH_SCRIPT)` must run against client returned by `init_redis_pool_sync()`. Move out of `__init__`. |
| image-download | `app/core/ratelimiter.py` + `app/main.py` (shutdown wire) | Pipeline usage already correct (`pipe.execute()` always called). Just swap client source. Wire `close_redis_pool_sync()` in FastAPI shutdown event. |
| image-comparison | `app/core/job_manager.py:26-32` | Replace `redis.from_url(...)` with `await init_redis_pool(); self.redis = cs.redis_client`. Existing `close_redis()` already wired. |
| database-recherche | `infrastructure/grpc_server.py:67-86` | Async client passed to `MilvusConcurrencyGuard` — guard accepts a reused client instance. |
| api-rest-milvus | `main.py:50-72` | `redis_client` referenced by guard, `app.state`, and stats prewarm. All must point to `cs.redis_client`. Add `await close_redis_pool()` to lifespan exit. |
| api-detection-langue-fr | `app/core/domain_fr.py:27-72` | Custom `DomainCache` class with own `_init_lock`. Refactor: drop local lock + `aioredis` import, read from `cs.redis_client`. Keep TTL constants. Wire `init_redis_pool()` in `main.py` lifespan. |

## 7. Verification

Five tests must pass before any rollout PR merges:

1. **Pool cap test** — open `N+1` concurrent ops against pool of size N, assert `ConnectionError` raised.
2. **Client name format test** — open inspector client, assert `CLIENT LIST` contains expected `{service}-{HOSTNAME}-pid{N}` entry.
3. **Connection-release test** — trigger N exceptions mid-op, assert `pool._in_use_connections` is empty after.
4. **Leak-detection script** — `bash leak_detect.sh` runs 100 ops, asserts `CLIENT LIST | grep $SERVICE_NAME | wc -l` drops to 0 within 30s.
5. **Sync binding parity test** — assert sync pool also caps + names correctly.

Tests live in `libs/common-utils/tests/`. Run via `pytest libs/common-utils/tests/ -v`.

### 7.1 Operator-side post-rollout checks

```bash
# Distinct service names — should show every replica
redis-cli CLIENT LIST | awk '{for(i=1;i<=NF;i++) if($i~/^name=/) print $i}' | sort | uniq -c | sort -rn

# Unnamed connections — should be 0
redis-cli CLIENT LIST | grep -c "name= "

# Total connections — upper bound = (services × replicas × REDIS_MAX_CONNECTIONS)
redis-cli INFO clients | grep connected_clients
```

## 8. Backwards Compatibility

- Camp A services (4) keep working without code changes. New client name format adds `-pid{N}` suffix; any `^crawler-py-` grep still matches.
- Existing `cache_service.py` test suite at `libs/common-utils/tests/test_cache_service.py` will need assertion updates for the new format. Done as part of Phase 2.
- No public API removed. All current helpers (`set_json`, `get_json`, etc.) keep their signatures and behavior.

## 9. Rollout Cadence

| Week | Action |
|---|---|
| 1 | Phase 2 lands in `common_utils`. Phase 3 tests pass on dev Redis container. |
| 2 | Tier 1 (5 qdrant services in 1 PR). Soak 48h. |
| 3 | Tier 2 + Tier 3 (website-processor, image-download). Soak 48h. |
| 4 | Tier 4 (image-comparison, database-recherche). Soak 48h. |
| 5 | Tier 5 (api-rest-milvus, api-detection-langue-fr). Separate PRs + deploys. |

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migrated service exceeds 20 conns under load | Med | Pool exhaustion → 500s | Per-service `REDIS_MAX_CONNECTIONS` env override. Monitor `pool._in_use_connections` via `/admin/redis-debug`. |
| Lua script (`website-processor`) loses registration after client swap | Low | NOTLOADED Redis errors | Re-register inside `RedisManager.__init__` against `get_client()`; covered by service-level tests. |
| api-detection-langue-fr lazy-init lock removal introduces race | Low | Init runs twice | `init_redis_pool()` is idempotent (already-pinged check + new lock). |
| Sync binding diverges from async over time | Med | Drift returns | Same env vars, same `_client_name()` logic. Long-term consolidation tracked as follow-up. |
| Operator forgets `CONFIG SET timeout 300` | Low | Orphans persist past pod crash | Documented in `crawler-service/CLAUDE.md` + post-rollout op check. |

## 11. Deliverables

- **Phase 2 (this PR):** Diffs 1–4 applied to `cache_service.py`, new `cache_service_sync.py`, updated `tests/test_cache_service.py` assertions, new `tests/test_cache_service_sync.py`.
- **Phase 3 (next PR):** End-to-end leak-detection script + pool-cap integration test (requires running Redis).
- **Phase 4 (subsequent PRs):** 5 batches, one per tier, in order.

## 12. References

- `libs/common-utils/src/common_utils/redis/cache_service.py` — async binding source.
- `apps-microservices/crawler-service/CLAUDE.md` § "Redis Connection Leak Prevention" — operator playbook.
- `docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md` — earlier client-side prong (crawler-service only).
- `docs/superpowers/specs/2026-05-21-cache-service-client-name-fix-design.md` — current `_client_name` rationale.
