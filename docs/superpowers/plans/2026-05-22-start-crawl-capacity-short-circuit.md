# start_crawl Capacity Short-Circuit + Redis Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the bursty 503 storm + occasional transient Redis 500 in crawler-service by short-circuiting capacity checks before any Redis op (0 ops on replica-saturated rejection, 2 read-only ops on global-saturated rejection) and retrying transient Redis failures on the load-bearing path.

**Architecture:** Reorder `start_crawl` in `crawler_manager.py`: (A) local in-memory capacity check FIRST, (B) non-mutating global READ probe SECOND, (C) existing lock SET NX + INCR + race-safe rollback as the last-line defense. Add `Retry-After` header to both 503 paths. Wrap the 4 load-bearing Redis calls in a tight `_with_retry` (2× 50ms backoff on transient connection errors). One source file modified, one new test file with 5 tests.

**Tech Stack:** Python 3.12, FastAPI, `redis.asyncio`, pytest + pytest-asyncio + monkeypatch.

---

## Plan-level test command

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v
```
Expected: 5 passed.

Full regression suite (excludes pre-existing broken local tests documented in primer):
```bash
cd apps-microservices/crawler-service && python -m pytest tests/ -x -q --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py
```
Expected: no new failures vs baseline.

---

## Task 1: Add `_with_retry` helper + 2 unit tests

**Goal:** Introduce a side-effect-free retry wrapper for Redis ops that catches transient connection errors and retries with bounded backoff. Cover with 2 unit tests.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (add module-level constants + `_with_retry` helper near top, around line 50)
- Create: `apps-microservices/crawler-service/tests/test_start_crawl_capacity.py` (new file, 2 tests for now — Task 2 appends 3 more)

**Acceptance Criteria:**
- [ ] Module-level constants `REPLICA_CAP_RETRY_AFTER_S = 5`, `GLOBAL_CAP_RETRY_AFTER_S = 15`, `_REDIS_RETRY_ATTEMPTS = 2`, `_REDIS_RETRY_BACKOFF_MS = 50` defined.
- [ ] `_with_retry(callable_coro, *args, **kwargs)` async helper exported (module-private, prefixed with `_`).
- [ ] Retries on `(redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError)`.
- [ ] Other exceptions (e.g. `ValueError`, `HTTPException`) propagate immediately.
- [ ] Exhausts after `_REDIS_RETRY_ATTEMPTS + 1` total attempts (1 initial + 2 retries = 3) and re-raises the last exception.
- [ ] Sleeps `_REDIS_RETRY_BACKOFF_MS / 1000.0` seconds between attempts.
- [ ] 2 new tests pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v` → 2 passed.

**Steps:**

- [ ] **Step 1: Create the test file with 2 failing tests**

Path: `apps-microservices/crawler-service/tests/test_start_crawl_capacity.py`

```python
"""Tests for crawler_manager.start_crawl capacity short-circuit + Redis retry.

Spec: docs/superpowers/specs/2026-05-22-start-crawl-capacity-short-circuit-design.md
"""
import asyncio
import pytest
from unittest.mock import AsyncMock
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.mark.asyncio
async def test_with_retry_succeeds_on_second_attempt():
    """Retries once on transient ConnectionError, then succeeds."""
    from app.core import crawler_manager

    call_count = {"n": 0}

    async def flaky():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RedisConnectionError("transient")
        return "ok"

    result = await crawler_manager._with_retry(flaky)
    assert result == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_with_retry_exhausts_and_raises():
    """Exhausts all attempts (1 initial + 2 retries = 3) and re-raises."""
    from app.core import crawler_manager

    call_count = {"n": 0}

    async def always_fail():
        call_count["n"] += 1
        raise RedisConnectionError("permanent")

    with pytest.raises(RedisConnectionError, match="permanent"):
        await crawler_manager._with_retry(always_fail)
    # Default: _REDIS_RETRY_ATTEMPTS = 2 → 1 initial + 2 retries = 3 total.
    assert call_count["n"] == 3
```

- [ ] **Step 2: Run tests, confirm they fail (TDD red phase)**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v
```
Expected: `AttributeError: module 'app.core.crawler_manager' has no attribute '_with_retry'` for both tests.

- [ ] **Step 3: Add the constants + `_with_retry` helper to `crawler_manager.py`**

Edit `apps-microservices/crawler-service/app/core/crawler_manager.py`. Locate line 44 (the `FAILED_CALLBACKS_KEY = "crawl_jobs:failed_callbacks"` line) and insert IMMEDIATELY AFTER it (before the `# Replica identity` comment block at line 46-49):

```python

# Capacity short-circuit + Redis retry (Spec 2026-05-22).
# See docs/superpowers/specs/2026-05-22-start-crawl-capacity-short-circuit-design.md
REPLICA_CAP_RETRY_AFTER_S = 5
GLOBAL_CAP_RETRY_AFTER_S = 15
_REDIS_RETRY_ATTEMPTS = 2  # 2 retries = 3 total attempts
_REDIS_RETRY_BACKOFF_MS = 50
```

Then locate a good insertion point for the helper. The existing helper `_rollback_claim` is nested inside `start_crawl`. The new `_with_retry` should be at MODULE level (so tests can import it directly). Add it AFTER the module-level constants (after the `REPLICA_ID` line ~50). The exact insertion: find the first `class` or `async def` at module level after line 50 — insert BEFORE that:

```python


async def _with_retry(callable_coro, *args, **kwargs):
    """Run a Redis call with bounded retry on transient connection errors.

    Wraps `cache_service.*` async helpers. On (RedisConnectionError, RedisTimeoutError,
    OSError) retries up to _REDIS_RETRY_ATTEMPTS times with _REDIS_RETRY_BACKOFF_MS ms
    backoff between attempts. Other exceptions propagate immediately.

    Spec: docs/superpowers/specs/2026-05-22-start-crawl-capacity-short-circuit-design.md
    """
    from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

    last_exc = None
    for attempt in range(_REDIS_RETRY_ATTEMPTS + 1):
        try:
            return await callable_coro(*args, **kwargs)
        except (RedisConnectionError, RedisTimeoutError, OSError) as e:
            last_exc = e
            if attempt < _REDIS_RETRY_ATTEMPTS:
                await asyncio.sleep(_REDIS_RETRY_BACKOFF_MS / 1000.0)
                logger.warning(
                    f"Redis transient error on attempt {attempt + 1}/{_REDIS_RETRY_ATTEMPTS + 1}: {e}. Retrying."
                )
                continue
            raise last_exc
```

- [ ] **Step 4: Re-run tests, confirm green (TDD green phase)**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Run broader regression suite**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/ -x -q --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py
```
Expected: no new failures vs baseline (existing crawler_manager tests still green; the new helper is purely additive).

- [ ] **Step 6: Commit**

Ask user for commit language first (per project rule). Then write `.git/COMMIT_EDITMSG` via the Write tool (UTF-8) — never via shell heredoc. Then:

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_start_crawl_capacity.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Commit message body (bilingual):

```
feat(crawler-service): add _with_retry helper for Redis ops

EN:
New module-level _with_retry async helper wraps Redis calls with
2-attempt retry (50ms backoff) on transient ConnectionError /
TimeoutError / OSError. Other exceptions propagate immediately.
Adds REPLICA_CAP_RETRY_AFTER_S=5 and GLOBAL_CAP_RETRY_AFTER_S=15
constants for upcoming Retry-After header support. 2 unit tests
cover the retry-then-succeed and retry-then-exhaust paths.
Spec 2026-05-22 start_crawl-capacity-short-circuit (Task 1 of 2).

FR:
Nouveau helper async _with_retry au niveau module qui enveloppe les
appels Redis avec un retry 2-attempts (50ms backoff) sur les
transitoires ConnectionError / TimeoutError / OSError. Les autres
exceptions se propagent immediatement. Ajoute les constantes
REPLICA_CAP_RETRY_AFTER_S=5 et GLOBAL_CAP_RETRY_AFTER_S=15 pour le
support Retry-After header a venir. 2 tests unitaires couvrent les
chemins retry-puis-succes et retry-puis-epuisement.
Spec 2026-05-22 start_crawl-capacity-short-circuit (Tache 1 sur 2).
```

---

## Task 2: Reorder `start_crawl` + `Retry-After` + apply retry

**Goal:** Apply Spec § 3.1 reorder: local capacity check FIRST (0 Redis ops), global READ probe SECOND (2 Redis ops), existing lock + INCR + race-safe rollback THIRD. Add `Retry-After` header to both 503 responses. Wrap the 4 load-bearing Redis calls with `_with_retry`. Cover with 3 integration tests.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py:340-447` (the `start_crawl` body — specifically the section from lock SET NX through capacity checks).
- Modify: `apps-microservices/crawler-service/tests/test_start_crawl_capacity.py` (append 3 integration tests).

**Acceptance Criteria:**
- [ ] Local capacity check (`active_local >= settings.MAX_CONCURRENT_CRAWLS`) fires BEFORE any Redis call.
- [ ] On replica-saturated rejection, NO `cache_service.*` method is invoked.
- [ ] Global READ probe (`get_key CRAWL_MAX_GLOBAL_KEY` + `get_key CRAWL_RUNNING_COUNT_KEY`) fires BEFORE lock SET NX / state set_json / INCR.
- [ ] On global-saturated probe rejection, NO `set_json` / `SET NX` / `INCR` is invoked (only the 2 read probes).
- [ ] Existing INCR-then-decrement race rollback preserved as last-line defense.
- [ ] Both 503 responses carry `Retry-After: <seconds>` header (`5` for replica, `15` for global).
- [ ] All 4 load-bearing Redis calls (lock SET NX, state set_json, INCR counter, probe reads) wrapped in `_with_retry`.
- [ ] Rollback calls (`safe_decrement_key`, `delete_key`) also wrapped in `_with_retry` for symmetry.
- [ ] 3 new integration tests pass (5 tests total in the test file).
- [ ] Broader regression suite: no new failures.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v` → 5 passed.

**Steps:**

- [ ] **Step 1: Append 3 failing integration tests to the test file**

Path: `apps-microservices/crawler-service/tests/test_start_crawl_capacity.py`

Append at end of file (after the 2 existing `_with_retry` tests):

```python


# ─── Integration tests for start_crawl reorder ─────────────────────────────────

@pytest.fixture
def manager_with_mocks(monkeypatch):
    """Construct a CrawlerManager with cache_service fully mocked.

    Returns (manager, redis_mock, cache_mocks) where cache_mocks is a dict
    of every cache_service.* method we touch in start_crawl.
    """
    from app.core import crawler_manager
    from app.core.crawler_manager import CrawlerManager

    # Mock every cache_service.* function start_crawl uses.
    cache_mocks = {
        "get_key": AsyncMock(),
        "set_json": AsyncMock(),
        "increment_key": AsyncMock(),
        "safe_decrement_key": AsyncMock(),
        "delete_key": AsyncMock(),
    }
    for name, mock in cache_mocks.items():
        monkeypatch.setattr(crawler_manager.cache_service, name, mock)

    # Mock the SET NX lock_key call (cache_service.redis_client.set).
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)  # Lock acquired by default.
    monkeypatch.setattr(crawler_manager.cache_service, "redis_client", redis_mock)

    manager = CrawlerManager()
    manager.local_processes = {}
    return manager, redis_mock, cache_mocks


@pytest.mark.asyncio
async def test_replica_saturated_returns_503_with_zero_redis_ops(manager_with_mocks):
    """Replica at MAX_CONCURRENT_CRAWLS: 503 with Retry-After=5, NO Redis calls."""
    from fastapi import HTTPException
    from app.core import crawler_manager
    from app.core.config import settings

    manager, redis_mock, cache_mocks = manager_with_mocks

    # Saturate local_processes with MAX_CONCURRENT_CRAWLS fake live subprocesses.
    class FakeProc:
        returncode = None  # alive
    for i in range(settings.MAX_CONCURRENT_CRAWLS):
        manager.local_processes[f"existing-{i}"] = FakeProc()

    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="6397",
            domain="atosafr.fr",
            start_url="https://atosafr.fr/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={},
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After") == str(crawler_manager.REPLICA_CAP_RETRY_AFTER_S)
    assert exc_info.value.detail["error_code"] == "REPLICA_CAPACITY_EXCEEDED"

    # No Redis op should have been invoked.
    redis_mock.set.assert_not_called()
    for name, mock in cache_mocks.items():
        assert mock.call_count == 0, f"cache_service.{name} should not have been called"


@pytest.mark.asyncio
async def test_global_saturated_returns_503_with_only_read_probe(manager_with_mocks):
    """Global READ probe shows full: 503 with Retry-After=15, only 2 get_key calls."""
    from fastapi import HTTPException
    from app.core import crawler_manager

    manager, redis_mock, cache_mocks = manager_with_mocks

    # local_processes empty (replica has room).
    # Probe returns: max=10, running=10.
    cache_mocks["get_key"].side_effect = [
        "10",  # CRAWL_MAX_GLOBAL_KEY
        "10",  # CRAWL_RUNNING_COUNT_KEY
    ]

    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="6397",
            domain="atosafr.fr",
            start_url="https://atosafr.fr/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={},
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After") == str(crawler_manager.GLOBAL_CAP_RETRY_AFTER_S)
    assert exc_info.value.detail["error_code"] == "GLOBAL_CAPACITY_EXCEEDED"

    # Only 2 get_key probes happened. No SET NX, no set_json, no INCR, no rollback.
    assert cache_mocks["get_key"].call_count == 2
    redis_mock.set.assert_not_called()
    assert cache_mocks["set_json"].call_count == 0
    assert cache_mocks["increment_key"].call_count == 0
    assert cache_mocks["safe_decrement_key"].call_count == 0
    assert cache_mocks["delete_key"].call_count == 0


@pytest.mark.asyncio
async def test_race_overshoot_rolls_back(manager_with_mocks, monkeypatch, tmp_path):
    """Probe sees room, but INCR overshoots — race-safe rollback fires."""
    from fastapi import HTTPException
    from app.core.config import settings

    manager, redis_mock, cache_mocks = manager_with_mocks

    # Stub storage path to a tmp dir so makedirs doesn't fail.
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))

    # local_processes empty; probe says room available, but INCR overshoots.
    cache_mocks["get_key"].side_effect = [
        "10",  # CRAWL_MAX_GLOBAL_KEY
        "9",   # CRAWL_RUNNING_COUNT_KEY (probe sees 9/10 → ok to proceed)
    ]
    cache_mocks["increment_key"].return_value = 11  # race: other replica filled the slot

    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="6397",
            domain="atosafr.fr",
            start_url="https://atosafr.fr/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={},
        )

    assert exc_info.value.status_code == 503
    # Lock SET NX, state set_json, INCR all fired.
    redis_mock.set.assert_called_once()
    assert cache_mocks["set_json"].call_count == 1
    assert cache_mocks["increment_key"].call_count == 1
    # Race-safe rollback: decrement counter + delete lock + delete state.
    assert cache_mocks["safe_decrement_key"].call_count == 1
    assert cache_mocks["delete_key"].call_count == 2  # lock_key + job_key
```

- [ ] **Step 2: Run tests, confirm 3 new failures (TDD red phase)**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v
```
Expected: 2 pass (T1 helper tests), 3 fail (reorder not yet applied — local check still happens AFTER Redis ops).

- [ ] **Step 3: Apply the reorder to `crawler_manager.py:340-432`**

This is the largest edit. The current region (lines 340-432 per the spec's § 2.2 table) does:

```
Line 347-349  job_key / lock_key / job_storage_path construction
Line 351-368  job_data dict build
Line 370-380  Lock SET NX (op #1)
Line 382-383  State set_json (op #2)
Line 385-389  _rollback_claim helper definition
Line 397-417  Global cap check: get_key (op #3) + increment_key (op #4) + rollback path
Line 419-432  Local cap check + rollback path
```

Replace lines 347 through 432 (inclusive) with this new ordering:

```python
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        lock_key = f"{CRAWL_LOCK_PREFIX}{crawl_id}"
        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)

        # Build job data early (pid will be patched after spawn).
        # last_heartbeat is set to now() immediately so concurrent reconciliation
        # on other replicas sees a fresh heartbeat — preventing the 60s blind
        # window between start_crawl and the first monitor-loop tick.
        now = datetime.utcnow()
        job_data = {
            "crawl_id": crawl_id, "status": "starting", "domain": domain,
            "start_url": start_url, "start_time": now,
            "last_heartbeat": now,
            "storage_path": job_storage_path,
            "callback_url": callback_url,
            "failure_callback_url": failure_callback_url, "pid": None,
            "crawl_mode": params.get("crawlMode", "standard"),
            "previous_crawl_id": params.get("previousCrawlId"),
            "params": params,
            "oom_restart_count": oom_restart_count,
            "replica_id": os.uname().nodename
        }

        # --- CAPACITY SHORT-CIRCUITS (Spec 2026-05-22) ---
        # A. LOCAL capacity check — in-memory, ZERO Redis ops.
        # Runs BEFORE any Redis op so a saturated replica costs nothing on Redis.
        if not is_restart:
            active_local = sum(1 for p in self.local_processes.values() if p.returncode is None)
            if active_local >= settings.MAX_CONCURRENT_CRAWLS:
                logger.warning(
                    f"Max concurrent crawls for this replica reached. Rejecting job '{crawl_id}'. "
                    f"No Redis ops performed."
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    headers={"Retry-After": str(REPLICA_CAP_RETRY_AFTER_S)},
                    detail={
                        "error_code": "REPLICA_CAPACITY_EXCEEDED",
                        "message": "This service instance is at its maximum capacity.",
                        "replica_capacity": settings.MAX_CONCURRENT_CRAWLS,
                        "rejected_request": {"crawl_id": crawl_id, "domain": domain},
                    },
                )

        # B. GLOBAL capacity READ probe — 2 non-mutating Redis ops.
        # If full, return 503 BEFORE the mutating lock SET / state write / INCR.
        current_max_global = settings.DEFAULT_MAX_GLOBAL_CRAWLS
        if not is_restart:
            redis_max_global_str = await _with_retry(cache_service.get_key, CRAWL_MAX_GLOBAL_KEY)
            current_max_global = int(redis_max_global_str) if redis_max_global_str else settings.DEFAULT_MAX_GLOBAL_CRAWLS
            current_running_str = await _with_retry(cache_service.get_key, CRAWL_RUNNING_COUNT_KEY)
            current_running = int(current_running_str) if current_running_str else 0
            if current_running >= current_max_global:
                logger.warning(
                    f"Global capacity probe shows full ({current_running}/{current_max_global}). "
                    f"Rejecting '{crawl_id}'. No mutating Redis ops performed."
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    headers={"Retry-After": str(GLOBAL_CAP_RETRY_AFTER_S)},
                    detail={
                        "error_code": "GLOBAL_CAPACITY_EXCEEDED",
                        "message": "The service has reached its global concurrency limit.",
                        "global_limit": current_max_global,
                        "current_running": current_running,
                    },
                )

        # --- DISTRIBUTED LOCK via SET NX (mutating; runs only after capacity probes passed) ---
        # Lock key: crawl_lock:{id} with TTL — prevents duplicate crawl_ids across replicas.
        # State key: crawl_job:{id} — persists for observability, no locking semantics.
        if not is_restart:
            claimed = await _with_retry(
                cache_service.redis_client.set,
                lock_key, crawl_id, nx=True, ex=CRAWL_LOCK_TTL_SECONDS,
            )
            if not claimed:
                logger.warning(f"Crawl job '{crawl_id}' is already running globally (lock NX failed). Request rejected.")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A crawl job with ID '{crawl_id}' is already in progress."
                )

        # Write the state document (always, for both normal starts and OOM restarts)
        await _with_retry(cache_service.set_json, job_key, job_data)

        # --- CAPACITY RACE-SAFE BACKSTOP (last line of defense) ---
        # Helper to rollback both lock claim and counter on rejection.
        # INVARIANT: OOM restarts (is_restart=True) bypass both lock claim and capacity checks,
        # so rollback is never needed. If capacity checks are ever added for restarts,
        # this guard must be updated to also handle the restart path.
        async def _rollback_claim(decrement_counter: bool = False):
            if not is_restart:
                await _with_retry(cache_service.delete_key, lock_key)
                await _with_retry(cache_service.delete_key, job_key)
                if decrement_counter:
                    await _with_retry(cache_service.safe_decrement_key, CRAWL_RUNNING_COUNT_KEY)

        # Atomic global INCR with race-safe rollback. Probe (section B) may have been
        # stale by the time we get here (another replica raced ahead); INCR + check
        # is the final authority.
        if not is_restart:
            new_count = await _with_retry(cache_service.increment_key, CRAWL_RUNNING_COUNT_KEY)
            if new_count > current_max_global:
                await _with_retry(cache_service.safe_decrement_key, CRAWL_RUNNING_COUNT_KEY)
                await _with_retry(cache_service.delete_key, lock_key)
                await _with_retry(cache_service.delete_key, job_key)
                logger.warning(
                    f"Global concurrency limit reached after INCR race ({new_count - 1}/{current_max_global}). "
                    f"Rejecting '{crawl_id}'."
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    headers={"Retry-After": str(GLOBAL_CAP_RETRY_AFTER_S)},
                    detail={
                        "error_code": "GLOBAL_CAPACITY_EXCEEDED",
                        "message": "The service has reached its global concurrency limit.",
                        "global_limit": current_max_global,
                        "current_running": new_count - 1
                    }
                )
```

Notes:
- The `current_max_global = settings.DEFAULT_MAX_GLOBAL_CRAWLS` initializer outside the `if not is_restart:` block is needed so the race-safe backstop (later) has a value to compare against on the `is_restart=True` path, even though that path skips the check.
- The old local capacity check at lines 419-432 is now consumed by section A above. Delete the original block entirely (no replacement needed there — it's moved up).

- [ ] **Step 4: Re-run the integration tests, confirm green**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run broader regression suite**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/ -x -q --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py
```
Expected: no new failures vs baseline. Existing crawler_manager tests should still pass — the behavior of `start_crawl` is unchanged on accepted paths; only rejection paths are now faster + race backstop preserved.

- [ ] **Step 6: Commit**

Ask user for commit language. Then write `.git/COMMIT_EDITMSG` via Write tool, then:

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_start_crawl_capacity.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Commit message body (bilingual):

```
fix(crawler-service): short-circuit start_crawl capacity before Redis

EN:
start_crawl now performs the local capacity check BEFORE any Redis op
(0 ops on replica-saturated rejection, down from 7) and a non-mutating
global READ probe BEFORE the mutating lock SET NX + state set_json +
INCR (2 ops on global-saturated rejection, down from 7). Existing
INCR-then-decrement race rollback preserved as last-line defense.
Both 503 responses now carry Retry-After header (5s replica, 15s
global). All 4 load-bearing Redis ops wrapped in _with_retry to
absorb transient connection failures during BO bursts. 3 integration
tests cover the 3 rejection paths. Eliminates the bursty 503 storm
+ occasional Redis 500 observed under BO 5min-cron load.
Spec 2026-05-22 start_crawl-capacity-short-circuit (Task 2 of 2).

FR:
start_crawl effectue desormais la verif de capacite locale AVANT
toute op Redis (0 ops sur rejet par saturation replica, contre 7) et
une sonde GLOBALE non-mutante AVANT le lock SET NX + state set_json +
INCR mutants (2 ops sur rejet par saturation globale, contre 7). Le
rollback INCR-puis-decrement existant est preserve en derniere ligne
de defense. Les deux reponses 503 portent desormais l'en-tete
Retry-After (5s replica, 15s global). Les 4 ops Redis load-bearing
sont enveloppees dans _with_retry pour absorber les echecs de
connexion transitoires pendant les bursts BO. 3 tests d'integration
couvrent les 3 chemins de rejet. Elimine le storm 503 burstise + 500
Redis occasionnel observe sous la charge cron BO de 5min.
Spec 2026-05-22 start_crawl-capacity-short-circuit (Tache 2 sur 2).
```

---

## Self-review checklist

| Spec § | Requirement | Task |
|---|---|---|
| § 3.1 (A) | Local capacity check BEFORE any Redis op | T2 Step 3 (section A) |
| § 3.1 (B) | Global READ probe BEFORE mutating ops | T2 Step 3 (section B) |
| § 3.1 (C-E) | Existing lock SET + INCR + race backstop preserved | T2 Step 3 (post-section B) |
| § 3.2 | `Retry-After: 5` on replica 503 + `Retry-After: 15` on global 503 | T2 Step 3 (both `raise HTTPException` calls) |
| § 3.3 | `_with_retry` helper for transient Redis errors | T1 Step 3 |
| § 3.3 | All 4 load-bearing ops wrapped | T2 Step 3 (every `cache_service.*` call in the rewritten region) |
| § 4.3 Test 1 | Replica saturated → 503 with zero Redis ops | T2 Step 1 (`test_replica_saturated_returns_503_with_zero_redis_ops`) |
| § 4.3 Test 2 | Global saturated → 503 with only 2 read probes | T2 Step 1 (`test_global_saturated_returns_503_with_only_read_probe`) |
| § 4.3 Test 3 | Race overshoot → rollback | T2 Step 1 (`test_race_overshoot_rolls_back`) |
| § 4.3 Test 4 | `_with_retry` succeeds on retry | T1 Step 1 (`test_with_retry_succeeds_on_second_attempt`) |
| § 4.3 Test 5 | `_with_retry` exhausts and raises | T1 Step 1 (`test_with_retry_exhausts_and_raises`) |

**Placeholder scan:** none — every step has full code, exact paths, exact verify commands.

**Type consistency:** `_with_retry(callable_coro, *args, **kwargs)` signature consistent across T1 (definition) and T2 (callsites). `REPLICA_CAP_RETRY_AFTER_S` / `GLOBAL_CAP_RETRY_AFTER_S` constants consistent. `_REDIS_RETRY_ATTEMPTS=2` matches the assertion `call_count == 3` (1 initial + 2 retries) in the exhaustion test.

**Spec coverage:** complete. No requirements missing a task.
