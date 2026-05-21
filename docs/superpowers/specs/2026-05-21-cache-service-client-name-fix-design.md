# cache_service Client Name Fix — Design

**Status:** Draft
**Date:** 2026-05-21
**Author:** Rindra ANDRIANJANAKA
**Scope:** `libs/common-utils/src/common_utils/redis/cache_service.py`, `docker-compose.yml`

## 1. Context

Spec-C (`2026-05-21-redis-connection-leak-fix-design.md`) bounded the Python Redis pool and added per-replica named clients so `CLIENT LIST` could attribute connections to their owner.

The naming implementation hardcoded the prefix `crawler-py-`:

```python
# Current (commit b6ac2b90)
client_name = f"crawler-py-{_replica_name()}"
```

But `libs/common-utils/cache_service.py` is shared by **10+ Python microservices** (api-gateway, api-classification, api-recherche, crawler-service, api-model, api-embedding, embedding-service, …). All of them now appear in `CLIENT LIST` as `crawler-py-<hostname>` — misleading for ops because the `crawler` prefix implies crawler-service ownership when it's actually any Python service.

Audit conducted on 2026-05-21 against:
- `apps-microservices/api-classification/main.py`
- `apps-microservices/api-classification/app/core/classifier.py`
- `apps-microservices/api-classification/app/router/classification.py`
- `apps-microservices/api-gateway/main.py`
- `apps-microservices/api-gateway/app/core/auth.py`
- `apps-microservices/api-gateway/app/routers/tokens.py`
- `apps-microservices/api-recherche/main.py`
- `apps-microservices/api-recherche/app/router/search.py`

confirmed:

- **Zero breaking changes** in the public API of `cache_service` post-Spec-C. All 14 helper signatures (`set_json`, `get_json`, …) and lifecycle functions (`init_redis_pool`, `close_redis_pool`) are unchanged.
- **Pool cap of 20** per process is safe under current load (api-gateway 10 workers × 20 = 200 conn/replica; api-recherche 8 × 20 = 160; api-classification 1 × 20 = 20 — tightest but acceptable; operator can raise via `REDIS_MAX_CONNECTIONS=40` if needed).
- **`socket_timeout=10s`** previously unbounded; bounded errors are caught by existing call-site `except Exception` handlers (strictly safer).
- The **only finding** is the misleading client-name prefix.

## 2. Goal

Replace the hardcoded `crawler-py-` prefix with a service-identifying value, so `CLIENT LIST` and `/admin/redis-debug` aggregations report correct ownership.

## 3. Non-goals

- Rename or alter any other env var in the project.
- Change cache_service public API.
- Modify any consumer service code outside docker-compose env passthrough.
- Refactor `_replica_name()` itself (it stays as the hostname helper).

## 4. Approach

**Use `SERVICE_NAME` env var** — already an established convention in the monorepo.

### Existing consumer

`libs/common-utils/src/common_utils/sso/credentials.py` reads `SERVICE_NAME` to resolve OAuth2 account-service credentials:

```
SERVICE_NAME=api-gateway
  → ACCOUNT_CLIENT_ID_API_GATEWAY
  → ACCOUNT_CLIENT_SECRET_API_GATEWAY
```

### Already-set services in `docker-compose.yml`

Seven services already set `SERVICE_NAME` for SSO purposes (verified by grep on 2026-05-21):

| Service | Compose line | Current value |
|---|---|---|
| `api-model-service` | L340 | `api-model-service` |
| `api-recherche-service` | L401 | `api-recherche-service` |
| `api-recherche-test-modification` | L429 | `api-recherche-test-modification` |
| `api-embedding-service` | L451 | `api-embedding-service` |
| `api-classification-service` | L501 | `api-classification-service` |
| `api-gateway` | L702 | `api-gateway` |
| `api-gateway` (duplicate worker line) | L753 | `api-gateway` |
| `embedding-service` | L1025 | `embedding-service` |

These services get the **correct Redis client name automatically** on next deploy without any compose change.

### Compatibility verdict

- Both consumers (SSO + cache_service) read the same value verbatim; neither writes; both want the same canonical service identifier.
- Setting `SERVICE_NAME` does NOT auto-activate SSO behavior — `get_account_credentials()` is only invoked from code paths that explicitly request account-service auth. A service that sets `SERVICE_NAME=crawler-service` but never calls SSO sees zero side effect from the env var.
- No collision with related env vars: `MILVUS_CONCURRENCY_SERVICE_NAME`, `CLASSIFICATION_SERVICE_NAME`, `MCP_SERVICE_NAME` are distinct keys for distinct purposes.

### Backward compat

If `SERVICE_NAME` is unset, fall back to the current literal `crawler-py`. Existing deploys without the env var behave **identically** to today's commit `b6ac2b90`. Zero blast radius on rollout.

## 5. Components

### 5.1 `cache_service.py` change

Add a small helper next to `_replica_name`:

```python
def _client_name() -> str:
    # SERVICE_NAME identifies which microservice opened the conn — same env
    # var used by common_utils.sso.credentials for OAuth2 client lookup.
    # Fallback preserves the pre-fix literal so unconfigured services don't
    # change behavior on rollout.
    service = (os.getenv("SERVICE_NAME") or "").strip() or "crawler-py"
    return f"{service}-{_replica_name()}"
```

Replace the callsite inside `init_redis_pool`:

```python
# was: client_name = f"crawler-py-{_replica_name()}"
client_name = _client_name()
```

### 5.2 `docker-compose.yml` change

One new env line under `crawler-service:` — the only consumer of `cache_service` that does not already set `SERVICE_NAME`:

```yaml
- SERVICE_NAME=crawler-service
```

Other services using `cache_service` but missing the var (e.g. graph-rag-*, processor-*, dlq-manager) are out of scope for this spec — they fall back to `crawler-py` until their respective compose lines are added (deferred per-service follow-up).

## 6. Tests

Extend `libs/common-utils/tests/test_cache_service.py`. Two new tests:

| Test | Asserts |
|---|---|
| `test_client_name_uses_service_name_env_when_set` | `SERVICE_NAME=api-gateway` → `kwargs["client_name"] == "api-gateway-<HOSTNAME>"` |
| `test_client_name_falls_back_to_crawler_py_when_unset` | `SERVICE_NAME` unset → `kwargs["client_name"].startswith("crawler-py-")` (preserves current commit b6ac2b90 behavior) |

The 8 existing tests stay green — the `_isolate_env` fixture does not set `SERVICE_NAME`, so they hit the fallback branch that matches today's `crawler-py-crawler-service-test` assertion.

## 7. Operational rollout

1. Deploy the code change (no compose change needed yet).
2. The 7 services that already set `SERVICE_NAME` start emitting correctly-named Redis connections immediately.
3. Add `SERVICE_NAME=crawler-service` to crawler-service compose entry in a follow-up commit. Operator restarts the service. Crawler conns now appear as `crawler-service-<replica>-py` in `CLIENT LIST` (was `crawler-py-<replica>`).
4. Verify via `./redis_diagnose.sh` — the name distribution table now shows the real service taxonomy.

## 8. File touch summary

```
libs/common-utils/src/common_utils/redis/cache_service.py   MOD  add _client_name() helper + swap callsite
libs/common-utils/tests/test_cache_service.py               MOD  +2 unit tests
docker-compose.yml                                          MOD  +1 SERVICE_NAME line under crawler-service
```

## 9. References

- `docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md` — Spec-C (the change this fix amends).
- Commit `b6ac2b90` — introduced the `crawler-py-` hardcoded prefix.
- `libs/common-utils/src/common_utils/sso/credentials.py:1-101` — established SERVICE_NAME consumer.
- `docker-compose.yml:340, 401, 429, 451, 501, 702, 753, 1025` — services already setting SERVICE_NAME.
- Audit conversation 2026-05-21 — confirmed zero behavioral break in the 8 consumer files.
