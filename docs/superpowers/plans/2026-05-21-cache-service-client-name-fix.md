# cache_service Client Name Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `crawler-py-` prefix in `cache_service.init_redis_pool()` with the `SERVICE_NAME` env var, so Redis `CLIENT LIST` reports the real owning service (api-gateway, api-recherche, etc.) instead of misleadingly tagging every Python client as `crawler-py-…`.

**Architecture:** Add a thin `_client_name()` helper next to `_replica_name()` that reads `SERVICE_NAME` (fallback `crawler-py`) and concatenates the hostname. Swap the one callsite in `init_redis_pool`. 7 services already set `SERVICE_NAME` in compose — they self-correct on next deploy. crawler-service needs one new line in `docker-compose.yml`.

**Tech Stack:** Python 3.12 (`redis.asyncio`), pytest + monkeypatch, docker compose YAML.

---

## Out of scope (per spec § 3)

- Other env vars (`MILVUS_CONCURRENCY_SERVICE_NAME`, `CLASSIFICATION_SERVICE_NAME`, `MCP_SERVICE_NAME`) — distinct keys, distinct purposes.
- cache_service public API — unchanged.
- Consumer service code (api-gateway, api-recherche, api-classification, …) — no changes; their env-set `SERVICE_NAME` already makes them work.
- The 70+ other Python services using `cache_service` without `SERVICE_NAME` set — they keep the `crawler-py` fallback until operator opts in. Deferred per-service follow-up.

## Plan-level test command

```bash
cd libs/common-utils && pytest tests/test_cache_service.py -v
```
Expected: 10 passed (8 existing + 2 new).

---

## Task 1: Add `_client_name()` helper + 2 unit tests

**Goal:** Replace hardcoded `client_name = f"crawler-py-{_replica_name()}"` in `init_redis_pool` with a `_client_name()` helper that uses `SERVICE_NAME` env var (fallback `crawler-py`). Cover with 2 unit tests.

**Files:**
- Modify: `libs/common-utils/src/common_utils/redis/cache_service.py:27-29` (add helper next to `_replica_name`) and `:81` (swap callsite).
- Modify: `libs/common-utils/tests/test_cache_service.py` (append 2 tests).

**Acceptance Criteria:**
- [ ] `_client_name()` exported (module-level, not nested).
- [ ] Returns `f"{SERVICE_NAME}-{HOSTNAME or pid-N}"` when `SERVICE_NAME` env var is non-empty.
- [ ] Returns `f"crawler-py-{HOSTNAME or pid-N}"` when `SERVICE_NAME` is unset, empty, or whitespace.
- [ ] `init_redis_pool` callsite uses `_client_name()` instead of literal `f"crawler-py-…"`.
- [ ] 2 new tests pass: env-set path + fallback path.
- [ ] 8 pre-existing `test_cache_service.py` tests still pass (the `_isolate_env` fixture does not set `SERVICE_NAME`, so they hit the fallback that matches today's `crawler-py-crawler-service-test` assertion).

**Verify:** `cd libs/common-utils && pytest tests/test_cache_service.py -v` → 10 passed.

**Steps:**

- [ ] **Step 1: Append the 2 failing tests to `test_cache_service.py`**

Path: `libs/common-utils/tests/test_cache_service.py`

Append at the end of the file (after the existing `test_init_falls_back_to_pid_when_hostname_unset`):

```python


@pytest.mark.asyncio
async def test_client_name_uses_service_name_env_when_set(reset_cache_service, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "api-gateway")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    # HOSTNAME is set to "crawler-service-test" by the autouse fixture.
    assert kwargs["client_name"] == "api-gateway-crawler-service-test"


@pytest.mark.asyncio
async def test_client_name_falls_back_to_crawler_py_when_unset(reset_cache_service, monkeypatch):
    # SERVICE_NAME explicitly empty (set then deleted by autouse fixture). Belt-and-suspenders:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["client_name"].startswith("crawler-py-")
```

Also extend the `_isolate_env` fixture at the top of the file. Locate:

```python
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Reset Redis env vars to known defaults so tests are hermetic."""
    for var in (
        "REDIS_URL",
        "REDIS_MAX_CONNECTIONS",
        "REDIS_SOCKET_TIMEOUT_S",
        "REDIS_SOCKET_CONNECT_TIMEOUT_S",
        "REDIS_HEALTH_CHECK_INTERVAL_S",
        "HOSTNAME",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://:secret@10.0.0.1:6379")
    monkeypatch.setenv("HOSTNAME", "crawler-service-test")
```

Add `"SERVICE_NAME"` to the deletion tuple so the fallback path is hermetic. Result:

```python
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Reset Redis env vars to known defaults so tests are hermetic."""
    for var in (
        "REDIS_URL",
        "REDIS_MAX_CONNECTIONS",
        "REDIS_SOCKET_TIMEOUT_S",
        "REDIS_SOCKET_CONNECT_TIMEOUT_S",
        "REDIS_HEALTH_CHECK_INTERVAL_S",
        "HOSTNAME",
        "SERVICE_NAME",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://:secret@10.0.0.1:6379")
    monkeypatch.setenv("HOSTNAME", "crawler-service-test")
```

- [ ] **Step 2: Run tests, confirm 2 new failures (helper doesn't exist yet)**

```bash
cd libs/common-utils && pytest tests/test_cache_service.py -v
```
Expected: 8 pass, 2 fail with `AssertionError: assert kwargs["client_name"] == "api-gateway-crawler-service-test"` (currently it's `crawler-py-crawler-service-test`).

- [ ] **Step 3: Add `_client_name()` helper in `cache_service.py`**

Path: `libs/common-utils/src/common_utils/redis/cache_service.py`

Locate the existing `_replica_name()` function (around line 27-29):

```python
def _replica_name() -> str:
    # Container hostname is per-replica (docker compose --scale gives unique names).
    return os.getenv("HOSTNAME") or f"pid-{os.getpid()}"
```

Insert the new helper IMMEDIATELY AFTER it (between `_replica_name` and `_ping_safe`):

```python
def _client_name() -> str:
    """
    Build the Redis CLIENT SETNAME value used by init_redis_pool.

    Reads SERVICE_NAME env var (the same convention used by
    common_utils.sso.credentials for OAuth2 client identity) and prefixes
    the per-replica hostname. Falls back to the literal 'crawler-py' when
    SERVICE_NAME is unset, empty, or whitespace — preserves the pre-fix
    naming so deploys that don't set the env var don't change behavior.

    See docs/superpowers/specs/2026-05-21-cache-service-client-name-fix-design.md
    """
    service = (os.getenv("SERVICE_NAME") or "").strip() or "crawler-py"
    return f"{service}-{_replica_name()}"
```

- [ ] **Step 4: Swap the `init_redis_pool` callsite**

In the same file, locate the line that currently builds `client_name`:

```python
    client_name = f"crawler-py-{_replica_name()}"
```

Replace with:

```python
    client_name = _client_name()
```

(Single-line replacement, no other change in `init_redis_pool`.)

- [ ] **Step 5: Re-run tests, confirm 10/10 green**

```bash
cd libs/common-utils && pytest tests/test_cache_service.py -v
```
Expected: 10 passed.

- [ ] **Step 6: Commit**

Ask user for commit language first (per project rule). Then write `.git/COMMIT_EDITMSG` via the Write tool (UTF-8), then:

```bash
git add libs/common-utils/src/common_utils/redis/cache_service.py libs/common-utils/tests/test_cache_service.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Commit message body (bilingual):

```
refactor(common-utils): SERVICE_NAME env var drives Redis client name

EN:
init_redis_pool now reads SERVICE_NAME (same convention used by
common_utils.sso.credentials for OAuth2 identity) to prefix the Redis
client_name. Falls back to the literal 'crawler-py' when SERVICE_NAME
is unset/empty/whitespace — preserves the post-Spec-C behavior for
deploys without the env var. 7 services that already set SERVICE_NAME
(api-gateway, api-recherche-service, api-classification-service,
api-model-service, api-recherche-test-modification, api-embedding-
service, embedding-service) self-correct on next deploy. 2 new unit
tests cover env-set + fallback paths.

FR:
init_redis_pool lit desormais SERVICE_NAME (meme convention utilisee
par common_utils.sso.credentials pour l'identite OAuth2) pour
prefixer le client_name Redis. Fallback sur le litteral 'crawler-py'
quand SERVICE_NAME est non defini / vide / blanc — preserve le
comportement post-Spec-C pour les deploys sans la variable d'env. 7
services qui definissent deja SERVICE_NAME (api-gateway, api-
recherche-service, api-classification-service, api-model-service,
api-recherche-test-modification, api-embedding-service, embedding-
service) s'auto-corrigent au prochain deploy. 2 nouveaux tests
unitaires couvrent les chemins env-defini + fallback.
```

---

## Task 2: Add `SERVICE_NAME=crawler-service` env line to compose

**Goal:** Set `SERVICE_NAME` on `crawler-service` so its Redis connections appear as `crawler-service-{hostname}` in `CLIENT LIST` instead of `crawler-py-{hostname}`.

**Files:**
- Modify: `docker-compose.yml` (crawler-service `environment:` block around L1356-1367).

**Acceptance Criteria:**
- [ ] `SERVICE_NAME=crawler-service` line appears under `crawler-service:` `environment:`.
- [ ] `docker compose -f docker-compose.yml config --quiet` validates clean (or `python -c "import yaml; yaml.safe_load(...)"` if docker not installed on host).
- [ ] Grep shows `SERVICE_NAME` in the crawler-service block.

**Verify:** `python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('YAML valid')" && grep -nE "SERVICE_NAME=crawler-service" docker-compose.yml`

**Steps:**

- [ ] **Step 1: Locate the crawler-service env block**

Open `docker-compose.yml`. The `crawler-service:` service is defined around line 1336. Its `environment:` block currently ends around line 1367 with:

```yaml
      - REDIS_MAX_CONNECTIONS=${REDIS_MAX_CONNECTIONS:-20}
      - REDIS_SOCKET_TIMEOUT_S=${REDIS_SOCKET_TIMEOUT_S:-10}
      - REDIS_SOCKET_CONNECT_TIMEOUT_S=${REDIS_SOCKET_CONNECT_TIMEOUT_S:-5}
      - REDIS_HEALTH_CHECK_INTERVAL_S=${REDIS_HEALTH_CHECK_INTERVAL_S:-30}
```

- [ ] **Step 2: Append the SERVICE_NAME line**

Immediately after the `REDIS_HEALTH_CHECK_INTERVAL_S` line (same 6-space + `- ` indentation), append:

```yaml
      - SERVICE_NAME=crawler-service
```

- [ ] **Step 3: Validate YAML**

```bash
python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('YAML valid')"
```
Expected: `YAML valid`.

If `docker` is installed on the host, additionally:
```bash
docker compose -f docker-compose.yml config --quiet
```
Expected: exit 0 (no output).

- [ ] **Step 4: Sanity grep**

```bash
grep -nE "SERVICE_NAME=crawler-service" docker-compose.yml
```
Expected: at least 1 line in the crawler-service block (around L1368).

- [ ] **Step 5: Commit**

Ask user for commit language. Then write `.git/COMMIT_EDITMSG` via Write tool, then:

```bash
git add docker-compose.yml
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Commit message body (bilingual):

```
chore(compose): set SERVICE_NAME=crawler-service for redis client name

EN:
crawler-service's Redis connections were tagged 'crawler-py-{hostname}'
by the post-Spec-C client_name logic. With Task 1's SERVICE_NAME-driven
helper now in place, this env line makes CLIENT LIST report
'crawler-service-{hostname}' for the actual crawler. Aligns crawler-
service with the 7 other Python services that already set SERVICE_NAME
for SSO purposes (api-gateway, api-recherche, api-classification, ...).

FR:
Les connexions Redis de crawler-service etaient taguees 'crawler-py-
{hostname}' par la logique de client_name post-Spec-C. Avec le helper
SERVICE_NAME-driven de la Tache 1 maintenant en place, cette ligne env
fait que CLIENT LIST reporte 'crawler-service-{hostname}' pour le vrai
crawler. Aligne crawler-service avec les 7 autres services Python qui
definissent deja SERVICE_NAME pour le SSO (api-gateway, api-recherche,
api-classification, ...).
```

---

## Self-review checklist

| Spec § | Requirement | Task |
|---|---|---|
| § 5.1 | Add `_client_name()` helper + use SERVICE_NAME env | T1 (Step 3) |
| § 5.1 | Fallback to `crawler-py` literal | T1 (Step 3) |
| § 5.1 | Swap callsite in `init_redis_pool` | T1 (Step 4) |
| § 5.2 | `SERVICE_NAME=crawler-service` in compose | T2 (Step 2) |
| § 6 | Test env-set path | T1 (Step 1, test 1) |
| § 6 | Test fallback path | T1 (Step 1, test 2) |
| § 6 | Existing 8 tests still pass | T1 (Step 5) |
| § 7 | Operational rollout | Covered by T1 + T2 commits; operator follows § 7 narrative for verification (`./redis_diagnose.sh`) |

**Placeholder scan:** none — all code blocks present, all paths exact, all commands explicit.

**Type consistency:** `_client_name()` signature consistent across T1 Step 3 (definition) and T1 Step 4 (callsite). Env var name `SERVICE_NAME` consistent between T1 (read) and T2 (set).
