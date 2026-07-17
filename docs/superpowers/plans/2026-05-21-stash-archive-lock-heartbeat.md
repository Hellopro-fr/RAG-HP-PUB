# Stash + Archive Lock Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the concurrent-stash race observed on crawl 6250 (2026-05-20) and harden the matching archive flow against the same class of bug, without breaking the PHP cron caller contract.

**Architecture:** Add an async-context-managed `_LockHeartbeat` helper that renews Redis lock TTLs via Lua compare-and-set while long-running stash/archive tar operations hold the lock. Migrate `archive_lock:{id}` from the constant-value `SET NX` pattern to the existing ownership-safe `_acquire_ownership_lock`/`_release_ownership_lock` pair. Disable nginx upstream POST retry on `/crawler/(stash|unstash|archive)/` routes at both api-gateway-go and api-gateway nginx configs (parity). Delete the unused `apps-microservices/crawler-service/nginx.conf` to remove operator confusion.

**Tech Stack:** Python 3.12 (FastAPI), asyncio, Redis (Lua scripting via `redis.eval`), pytest + pytest-asyncio, nginx 1.x.

**Spec:** `docs/superpowers/specs/2026-05-21-stash-archive-lock-heartbeat-design.md`.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/app/core/config.py` | Modify | Add 3 new settings + bump 1 existing |
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Modify | Add `_LockHeartbeat` class; integrate in `stash_crawl` + `archive_crawl`; migrate archive lock |
| `apps-microservices/crawler-service/tests/test_lock_heartbeat.py` | Create | Unit tests for the helper |
| `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` | Modify | Add stash integration tests (long-tar, crash sim) |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | Modify | Add archive integration tests (long-tar, response shape, ownership-safe release) |
| `apps-microservices/api-gateway-go/nginx.conf` | Modify | Regex location for stash/unstash/archive — `proxy_next_upstream off` |
| `apps-microservices/api-gateway/nginx.conf` | Modify | Same change as api-gateway-go (parity) |
| `apps-microservices/crawler-service/nginx.conf` | Delete | Unused; not mounted in docker-compose |
| `apps-microservices/crawler-service/README.md` | Modify | Remove line 19 reference to nginx.conf |

---

## Commit message convention

Every task commits with **bilingual EN+FR Conventional Commits** per project rules (`.claude/rules/commit-messages.md`).

Subject under 72 chars. Body has `EN:` then `FR:` paragraphs.

### Graphify hook clobber recipe

The `chore(graphify) post-pull --update` post-commit hook may overwrite the commit subject. If `git log -1 --format="%s"` shows `chore(graphify): ...` instead of your subject, run this recipe:

```bash
# 1. Re-write the EDITMSG with the correct message (keep heredoc verbatim)
cat > .git/COMMIT_EDITMSG <<'EOF'
<correct subject under 72 chars>

EN:
<English body paragraph>

FR:
<French body paragraph>
EOF

# 2. Read the file back so Edit/Write tools see it
cat .git/COMMIT_EDITMSG

# 3. Amend without re-opening editor
git commit --amend -F .git/COMMIT_EDITMSG

# 4. Verify
git log -1 --format="%s"
```

---

## Task 0: Add lock heartbeat config + bump STASH_LOCK_TTL

**Goal:** Add 3 new settings + bump `STASH_LOCK_TTL_SECONDS` from 600 to 1800.

**Native task:** #32.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py` (insert at line 47 between the stash block and the GCS_DOWNLOAD line; bump line 44)

**Acceptance Criteria:**
- [ ] `STASH_LOCK_TTL_SECONDS: int = 1800` (was 600)
- [ ] `ARCHIVE_LOCK_TTL_SECONDS: int = 1800` (new, makes hardcoded value explicit)
- [ ] `LOCK_HEARTBEAT_INTERVAL_SECONDS: int = 300`
- [ ] `LOCK_HEARTBEAT_MAX_DURATION_SECONDS: int = 14400`
- [ ] `Settings()` instantiates without error
- [ ] No env-var name collision with existing `.env` files

**Verify:** `python -c "from app.core.config import settings; print(settings.STASH_LOCK_TTL_SECONDS, settings.ARCHIVE_LOCK_TTL_SECONDS, settings.LOCK_HEARTBEAT_INTERVAL_SECONDS, settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS)"` → `1800 1800 300 14400`

**Steps:**

- [ ] **Step 1: Modify `config.py` — bump `STASH_LOCK_TTL_SECONDS` and add the three new fields**

Replace lines 43-47 (the existing "Stash flow Redis lock TTLs and timeouts" block) with:

```python
    # Stash flow Redis lock TTLs and timeouts (seconds).
    # STASH_LOCK_TTL is bumped to 1800s (was 600s) so it exceeds nginx
    # proxy_read_timeout (600s on /crawler/ default location) and survives
    # any single nginx retry window; the heartbeat below renews TTL
    # mid-operation to handle larger crawls.
    STASH_LOCK_TTL_SECONDS: int = 1800
    UNSTASH_LOCK_TTL_SECONDS: int = 600
    UNSTASH_TIMEOUT_SECONDS: int = 300
    UNSTASH_CLEANUP_GRACE_SECONDS: int = 30

    # Archive flow Redis lock TTL (seconds). Previously hardcoded in
    # crawler_manager.archive_crawl; surfaced here for parity with stash
    # and for tunability.
    ARCHIVE_LOCK_TTL_SECONDS: int = 1800

    # Long-running lock heartbeat (used by stash + archive).
    # INTERVAL = TTL / 6 → up to 5 missed renewals before TTL expires
    # (defense against transient Redis latency).
    # MAX_DURATION = 4h hard cap; past this, heartbeat stops renewing so
    # a truly hung op cannot indefinitely hold the lock.
    LOCK_HEARTBEAT_INTERVAL_SECONDS: int = 300
    LOCK_HEARTBEAT_MAX_DURATION_SECONDS: int = 14400
```

- [ ] **Step 2: Verify the file imports cleanly**

Run:

```bash
cd apps-microservices/crawler-service
python -c "from app.core.config import settings; print(settings.STASH_LOCK_TTL_SECONDS, settings.ARCHIVE_LOCK_TTL_SECONDS, settings.LOCK_HEARTBEAT_INTERVAL_SECONDS, settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS)"
```

Expected output: `1800 1800 300 14400`

- [ ] **Step 3: Commit (bilingual EN+FR)**

```bash
git add apps-microservices/crawler-service/app/core/config.py
git commit -m "$(cat <<'EOF'
feat(crawler-service): add lock heartbeat config; bump STASH_LOCK_TTL to 1800s

EN:
Add LOCK_HEARTBEAT_INTERVAL_SECONDS (300s) and LOCK_HEARTBEAT_MAX_DURATION_SECONDS
(14400s) for use by the upcoming _LockHeartbeat helper. Surface
ARCHIVE_LOCK_TTL_SECONDS (1800s, previously hardcoded inside archive_crawl).
Bump STASH_LOCK_TTL_SECONDS from 600 to 1800 so a single TTL window is larger
than the nginx proxy_read_timeout (600s) — the heartbeat handles tars longer
than that.

FR:
Ajoute LOCK_HEARTBEAT_INTERVAL_SECONDS (300s) et
LOCK_HEARTBEAT_MAX_DURATION_SECONDS (14400s) pour le futur helper
_LockHeartbeat. Expose ARCHIVE_LOCK_TTL_SECONDS (1800s, anciennement
hardcode dans archive_crawl). Augmente STASH_LOCK_TTL_SECONDS de 600 a 1800
pour qu'une seule fenetre TTL soit superieure au proxy_read_timeout nginx
(600s) — le heartbeat gere les tars plus longs.
EOF
)"
```

If the graphify hook clobbers the subject, apply the recipe from the top of this plan.

```json:metadata
{"files":["apps-microservices/crawler-service/app/core/config.py"],"verifyCommand":"python -c \"from app.core.config import settings; print(settings.STASH_LOCK_TTL_SECONDS, settings.ARCHIVE_LOCK_TTL_SECONDS, settings.LOCK_HEARTBEAT_INTERVAL_SECONDS, settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS)\"","acceptanceCriteria":["STASH_LOCK_TTL_SECONDS=1800","ARCHIVE_LOCK_TTL_SECONDS=1800","LOCK_HEARTBEAT_INTERVAL_SECONDS=300","LOCK_HEARTBEAT_MAX_DURATION_SECONDS=14400","Settings imports cleanly"]}
```

---

## Task 1: Implement `_LockHeartbeat` helper + unit tests

**Goal:** Async context manager renewing a Redis lock TTL via Lua CAS while a long-running op holds the lock.

**Native task:** #33. Blocked by T0.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert after `_release_ownership_lock`, around line 1978)
- Create: `apps-microservices/crawler-service/tests/test_lock_heartbeat.py`

**Acceptance Criteria:**
- [ ] `_LockHeartbeat` is an async context manager (`__aenter__` starts task, `__aexit__` cancels + awaits)
- [ ] Refreshes via Lua CAS: only `EXPIRE` if the lock value still matches
- [ ] Stops renewing when `max_duration_seconds` elapsed (logs ERROR)
- [ ] Stops renewing when CAS returns 0, i.e. value mismatch (logs WARNING)
- [ ] Transient `Exception` from `redis.eval` is logged at WARNING and loop continues
- [ ] `asyncio.CancelledError` from `__aexit__` is swallowed cleanly
- [ ] 5 unit tests all pass

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_lock_heartbeat.py -v` → 5 passed

**Steps:**

- [ ] **Step 1: Write failing tests first (TDD red phase)**

Create `apps-microservices/crawler-service/tests/test_lock_heartbeat.py`:

```python
"""Unit tests for _LockHeartbeat helper.

The helper renews a Redis lock TTL via Lua compare-and-set every
LOCK_HEARTBEAT_INTERVAL_SECONDS while a long-running operation holds the lock.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.core.crawler_manager import _LockHeartbeat


@pytest.fixture
def cm_stub():
    """Minimal CrawlerManager stub (heartbeat only needs cache_service.redis_client)."""
    return object()


@pytest.mark.asyncio
async def test_heartbeat_renews_ttl_via_lua_cas(cm_stub):
    """Happy path: at least 2 renewals over 2.5 s with interval = 1 s, Lua returns 1."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        ):
            await asyncio.sleep(2.5)
    assert fake_redis.eval.await_count >= 2
    # Verify CAS args on first call
    args = fake_redis.eval.await_args_list[0].args
    assert "redis.call('get'" in args[0]  # Lua script
    assert args[1] == 1  # numkeys
    assert args[2] == "lk:1"  # KEYS[1]
    assert args[3] == "rid:abc"  # ARGV[1]
    assert args[4] == "10"  # ARGV[2] (TTL as str)


@pytest.mark.asyncio
async def test_heartbeat_stops_on_value_mismatch(cm_stub):
    """When Lua returns 0 (value mismatch, lock taken over), heartbeat stops."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(side_effect=[1, 0])  # first OK, second mismatch
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        ):
            await asyncio.sleep(3.5)
    # After mismatch, no further eval calls
    assert fake_redis.eval.await_count == 2


@pytest.mark.asyncio
async def test_heartbeat_stops_at_max_duration(cm_stub):
    """When max_duration elapsed, heartbeat stops renewing."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=2,
        ):
            await asyncio.sleep(4.0)
    # Past max_duration=2s with interval=1s: expect 2 renewals (at t=1, t=2),
    # then stop (t=3+ skipped).
    assert fake_redis.eval.await_count <= 3


@pytest.mark.asyncio
async def test_heartbeat_tolerates_transient_redis_error(cm_stub):
    """Redis exception during refresh logs WARNING + continues the loop."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(
        side_effect=[ConnectionError("boom"), 1, 1]
    )
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        ):
            await asyncio.sleep(3.5)
    assert fake_redis.eval.await_count >= 3


@pytest.mark.asyncio
async def test_heartbeat_cancels_cleanly_on_exit(cm_stub):
    """__aexit__ cancels the heartbeat task and awaits its cancellation."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        hb = _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        )
        async with hb:
            await asyncio.sleep(0.1)
        assert hb._task.done() or hb._task.cancelled()
```

- [ ] **Step 2: Run failing tests to confirm RED**

```bash
cd apps-microservices/crawler-service
pytest tests/test_lock_heartbeat.py -v
```

Expected: ImportError or 5 failures (helper does not exist yet).

- [ ] **Step 3: Implement `_LockHeartbeat` in `crawler_manager.py`**

Insert immediately after `_release_ownership_lock` (which ends at line 1977 in current file) — i.e. at line 1978, before `async def stash_crawl`:

```python
    # ---------------------------------------------------------------- #
    # Lock heartbeat
    # ---------------------------------------------------------------- #

class _LockHeartbeat:
    """
    Async context manager that renews a Redis lock TTL while a long-running
    operation holds the lock. Ownership-safe: only refreshes if the lock
    value still matches our expected_value, preventing accidental refresh
    of a lock taken over after our TTL lapsed.

    Bounded by max_duration_seconds: past this cap the heartbeat stops
    renewing, letting TTL expire so a truly hung op cannot indefinitely
    hold the lock.

    Usage:
        lock_value = await self._acquire_ownership_lock(key, ttl)
        try:
            async with _LockHeartbeat(self, key, lock_value, ttl, interval, max_duration):
                await long_running_op()
        finally:
            await self._release_ownership_lock(key, lock_value)
    """

    # Lua script: only EXPIRE if current value still matches expected.
    # Returns 1 on success, 0 on value mismatch (lock taken over).
    _LUA_REFRESH = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('expire', KEYS[1], ARGV[2]) "
        "else return 0 end"
    )

    def __init__(
        self,
        cm: "CrawlerManager",
        lock_key: str,
        lock_value: str,
        ttl_seconds: int,
        interval_seconds: int,
        max_duration_seconds: int,
    ):
        self._cm = cm
        self._lock_key = lock_key
        self._lock_value = lock_value
        self._ttl = ttl_seconds
        self._interval = interval_seconds
        self._max_duration = max_duration_seconds
        self._task: Optional[asyncio.Task] = None
        self._started_at: float = 0.0

    async def __aenter__(self) -> "_LockHeartbeat":
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(
            self._run(), name=f"lock-heartbeat:{self._lock_key}"
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                elapsed = time.monotonic() - self._started_at
                if elapsed > self._max_duration:
                    logger.error(
                        f"Lock heartbeat for '{self._lock_key}' exceeded "
                        f"max_duration_seconds={self._max_duration}; "
                        f"stopping renewals."
                    )
                    return
                try:
                    result = await cache_service.redis_client.eval(
                        self._LUA_REFRESH, 1,
                        self._lock_key, self._lock_value, str(self._ttl),
                    )
                    if result == 0:
                        logger.warning(
                            f"Lock '{self._lock_key}' no longer owned by us "
                            f"(value mismatch). Stopping heartbeat."
                        )
                        return
                except Exception as e:
                    logger.warning(
                        f"Lock heartbeat refresh failed for "
                        f"'{self._lock_key}': {e}"
                    )
        except asyncio.CancelledError:
            return
```

Note on module-level placement: `_LockHeartbeat` is defined at module level (not inside `CrawlerManager`) so it can be instantiated with `_LockHeartbeat(self, ...)` from inside `stash_crawl` and `archive_crawl`. The `cm` parameter is reserved for future ergonomics (currently unused inside `_run`) — leaving it in keeps the call site self-documenting.

Required imports (verify they exist at top of file; add if missing):

```python
import asyncio
import time
from typing import Optional
```

These are likely already imported. Check the existing top of `crawler_manager.py`. If `time` is missing, add it.

- [ ] **Step 4: Run unit tests to confirm GREEN**

```bash
cd apps-microservices/crawler-service
pytest tests/test_lock_heartbeat.py -v
```

Expected output: `5 passed`.

- [ ] **Step 5: Commit (bilingual EN+FR)**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_lock_heartbeat.py
git commit -m "$(cat <<'EOF'
feat(crawler-service): add _LockHeartbeat async context manager

EN:
Renews a Redis lock TTL via Lua compare-and-set every interval seconds
while a long-running operation holds the lock. Ownership-safe: refresh only
when the current value matches expected. Bounded by max_duration_seconds.
Cancel-safe via __aexit__. Used in upcoming stash + archive integrations.

FR:
Renouvelle le TTL d'un lock Redis via compare-and-set Lua a chaque
intervalle pendant qu'une operation longue tient le lock. Ownership-safe :
refresh uniquement quand la valeur courante correspond. Borne par
max_duration_seconds. Cancel-safe via __aexit__. Sera utilise dans les
prochaines integrations stash + archive.
EOF
)"
```

```json:metadata
{"files":["apps-microservices/crawler-service/app/core/crawler_manager.py","apps-microservices/crawler-service/tests/test_lock_heartbeat.py"],"verifyCommand":"cd apps-microservices/crawler-service && pytest tests/test_lock_heartbeat.py -v","acceptanceCriteria":["_LockHeartbeat is async context manager","Lua CAS refresh","max_duration cap","value-mismatch stop","transient redis error tolerated","asyncio.CancelledError swallowed","5 unit tests pass"]}
```

---

## Task 2: Wrap `stash_crawl` tar + cleanup with `_LockHeartbeat`

**Goal:** Integrate the heartbeat helper in `stash_crawl` so the lock TTL survives a tar longer than `STASH_LOCK_TTL_SECONDS`.

**Native task:** #34. Blocked by T1.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (around lines 2065-2199, inside `stash_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`

**Acceptance Criteria:**
- [ ] `async with _LockHeartbeat(...)` wraps the tar + Redis-stashed_at + cleanup block
- [ ] The existing `finally: await self._release_ownership_lock(stash_lock_key, lock_value)` is preserved unchanged
- [ ] All pre-existing stash tests still pass
- [ ] New integration test: `test_stash_lock_survives_long_tar` — mocked tar sleeps past initial TTL, concurrent caller gets 409 throughout
- [ ] New integration test: `test_stash_lock_released_on_replica_crash_simulation` — lock without heartbeat expires past TTL → fresh acquire succeeds

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager_stash.py -v` → all pass (existing + new)

**Steps:**

- [ ] **Step 1: Write new integration tests first**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`:

```python
@pytest.mark.asyncio
async def test_stash_lock_survives_long_tar(
    cm_instance, base_job_info, monkeypatch, mock_redis
):
    """A tar that runs longer than the initial TTL keeps the lock via heartbeat.

    Scenario: STASH_LOCK_TTL=2s, heartbeat interval=0.5s, tar mock sleeps 4s.
    A concurrent stash_crawl call mid-tar must get 409 OPERATION_IN_PROGRESS.
    """
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "STASH_LOCK_TTL_SECONDS", 2)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(
        cfg.settings, "LOCK_HEARTBEAT_MAX_DURATION_SECONDS", 30
    )

    # Use a real Redis-like mock that supports SET NX + EVAL semantics
    # (see existing mock_redis fixture). If the fixture uses a stub that
    # does not implement TTL refresh, swap to fakeredis or extend the
    # stub. For now we assert via call counts.

    tar_call_count = {"n": 0}

    async def slow_create_archive():
        # Simulate a 4s tar (2x initial TTL); during this time, heartbeat
        # must refresh the lock at least once.
        tar_call_count["n"] += 1
        await asyncio.sleep(4)
        return "/app/stash/test.tar.gz", 1024

    monkeypatch.setattr(
        cm_instance, "_create_stash_archive_for_test", slow_create_archive,
        raising=False,
    )

    # Spy on heartbeat refresh calls
    refresh_count = {"n": 0}
    original_eval = mock_redis.eval

    async def counting_eval(script, numkeys, *args):
        if "expire" in script.lower():
            refresh_count["n"] += 1
        return await original_eval(script, numkeys, *args) if asyncio.iscoroutinefunction(original_eval) else original_eval(script, numkeys, *args)

    mock_redis.eval = counting_eval

    task1 = asyncio.create_task(cm_instance.stash_crawl(base_job_info))
    await asyncio.sleep(2.5)  # past initial TTL=2s

    # Concurrent attempt must see lock still held
    with pytest.raises(HTTPException) as exc_info:
        await cm_instance.stash_crawl(base_job_info)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail.get("error_code") == "OPERATION_IN_PROGRESS"

    result = await task1
    assert result["status"] == "stashing"
    # Heartbeat fired at least once before tar completion
    assert refresh_count["n"] >= 1


@pytest.mark.asyncio
async def test_stash_lock_released_on_replica_crash_simulation(
    cm_instance, mock_redis, monkeypatch
):
    """Without heartbeat, lock TTL expires naturally → next acquire succeeds."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "STASH_LOCK_TTL_SECONDS", 1)

    lock_key = "stash_lock:crash_sim_123"
    # Acquire the lock without a heartbeat (simulates a replica that died)
    value = await cm_instance._acquire_ownership_lock(lock_key, 1)
    assert value is not None

    await asyncio.sleep(1.5)  # past TTL

    # Fresh acquire must succeed (lock auto-expired in Redis)
    new_value = await cm_instance._acquire_ownership_lock(lock_key, 1)
    assert new_value is not None
```

Notes for the implementer:
- The first test depends on the existing `mock_redis` fixture. If the fixture is a plain dict-based stub without TTL semantics, replace with `fakeredis.aioredis.FakeRedis` (already in `requirements.txt` for some services — check). If unavailable, fall back to a hand-rolled stub that tracks `SET NX EX` semantics + Lua eval for `EXPIRE`. Document the choice inline.
- The second test only exercises `_acquire_ownership_lock` + Redis TTL — it does not call `stash_crawl`. It validates that the heartbeat is NOT the only thing keeping the lock alive (TTL fallback works).

- [ ] **Step 2: Run new tests to confirm RED**

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager_stash.py::test_stash_lock_survives_long_tar tests/test_crawler_manager_stash.py::test_stash_lock_released_on_replica_crash_simulation -v
```

Expected: 2 failures (heartbeat not yet integrated, or refresh_count never incremented).

- [ ] **Step 3: Integrate `_LockHeartbeat` in `stash_crawl`**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, locate the `try:` block at line 2065 inside `stash_crawl`. The current structure is:

```python
        try:
            # Defensive bind-mount check
            self._verify_bind_mount(settings.STASH_SHARED_PATH, "stash upload")
            ...
            final_path, archive_size = await anyio.to_thread.run_sync(_create_stash_archive)
            ...
            # set Redis stashed_at
            ...
            # cleanup data keep logs
            ...
            return {...}

        finally:
            await self._release_ownership_lock(stash_lock_key, lock_value)
```

Modify the `try:` body to wrap the long-running work in `async with _LockHeartbeat(...)`:

```python
        try:
            async with _LockHeartbeat(
                self,
                stash_lock_key,
                lock_value,
                ttl_seconds=settings.STASH_LOCK_TTL_SECONDS,
                interval_seconds=settings.LOCK_HEARTBEAT_INTERVAL_SECONDS,
                max_duration_seconds=settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS,
            ):
                # --- Defensive bind-mount check (spec 2026-05-20 §4) ---
                self._verify_bind_mount(settings.STASH_SHARED_PATH, "stash upload")

                stash_dir = settings.STASH_SHARED_PATH
                target_tar = os.path.join(stash_dir, f"{crawl_id}.tar.gz")
                job_storage_path = job_info["storage_path"]

                # --- Pre-flight disk space check (fail-open per spec §5.1) ---
                try:
                    baseline_state = self._get_archives_disk_state(stash_dir)
                    logger.info(f"Stash disk state for '{crawl_id}': {baseline_state}")
                    required_bytes = self._estimate_archive_required_bytes(job_storage_path)
                    required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

                    if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
                        logger.warning(
                            f"Rejecting stash '{crawl_id}': insufficient disk space. "
                            f"Required: {required_bytes}, Available: {baseline_state['free_bytes']}"
                        )
                        raise HTTPException(
                            status_code=503,
                            detail={
                                "error_code": "INSUFFICIENT_DISK_SPACE",
                                "required_bytes": required_bytes,
                                "available_bytes": baseline_state["free_bytes"],
                                "disk_state": baseline_state,
                            },
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.warning(
                        f"Stash pre-flight measurement failed for '{crawl_id}': {e}. "
                        f"Proceeding without disk-space check (fail-open)."
                    )

                # --- Tar via staging dir + atomic move (mirror archive flow) ---
                def _create_stash_archive():
                    staging_dir = os.path.join(stash_dir, ".staging")
                    os.makedirs(staging_dir, exist_ok=True)
                    os.makedirs(stash_dir, exist_ok=True)
                    staging_base = os.path.join(staging_dir, crawl_id)
                    staging_path = None
                    try:
                        staging_path = shutil.make_archive(staging_base, 'gztar', root_dir=job_storage_path)
                        if os.path.getsize(staging_path) == 0:
                            raise RuntimeError(f"Stash archive at '{staging_path}' is empty (0 bytes).")
                        # Integrity check
                        with tarfile.open(staging_path, 'r:gz') as t:
                            t.getnames()
                        os.rename(staging_path, target_tar)
                        staging_path = None  # transferred ownership
                        return target_tar, os.path.getsize(target_tar)
                    finally:
                        if staging_path and os.path.exists(staging_path):
                            try:
                                os.remove(staging_path)
                            except OSError:
                                pass

                try:
                    final_path, archive_size = await anyio.to_thread.run_sync(_create_stash_archive)
                    logger.info(f"Stashed crawl '{crawl_id}' ({archive_size} bytes) -> {final_path}")
                except Exception as e:
                    logger.error(f"Failed to create stash archive for '{crawl_id}': {e}", exc_info=True)
                    try:
                        post_failure_state = self._get_archives_disk_state(stash_dir)
                        logger.error(f"Stash disk state at failure for '{crawl_id}': {post_failure_state}")
                    except Exception:
                        pass
                    raise HTTPException(status_code=500, detail=f"Stash archive creation failed: {str(e)}")

                # --- Mark as stashed in Redis (BEFORE deleting local data) ---
                stashed_at = datetime.utcnow().isoformat()
                job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
                fresh_job_info = await cache_service.get_json(job_key)
                if not fresh_job_info:
                    logger.error(f"Cannot mark '{crawl_id}' as stashed: job not found in Redis after stash tar created.")
                    raise HTTPException(status_code=500, detail="Job vanished from Redis during stash.")
                fresh_job_info["stashed_at"] = stashed_at
                await cache_service.set_json(job_key, fresh_job_info)
                logger.info(f"Marked crawl '{crawl_id}' as stashed at {stashed_at} in Redis.")

                # --- Cleanup data files; keep logs + markers (spec 2026-05-20 §5) ---
                try:
                    def _cleanup_data_keep_logs():
                        files_to_keep = {
                            'crawler.log', '_callback_payload.json',
                            '_completion_marker.json', '_status_snapshot.json',
                            '_exit_reason.json', '_update_report.json',
                            'update_stats.json',
                            'timing.jsonl', 'timing-summary.json',
                        }
                        if not os.path.isdir(job_storage_path):
                            return
                        for root, dirs, files in os.walk(job_storage_path, topdown=False):
                            for name in files:
                                if name not in files_to_keep:
                                    try:
                                        os.remove(os.path.join(root, name))
                                    except OSError:
                                        pass
                            for name in dirs:
                                try:
                                    os.rmdir(os.path.join(root, name))
                                except OSError:
                                    pass  # non-empty (kept file inside) → leave dir

                    await anyio.to_thread.run_sync(_cleanup_data_keep_logs)
                    logger.info(f"Cleaned data (kept logs) for stashed crawl '{crawl_id}'.")
                except Exception as e:
                    logger.warning(f"Data cleanup failed for stashed '{crawl_id}' (tar is safe): {e}")

                return {
                    "crawl_id": crawl_id,
                    "status": "stashing",
                    "stash_path": f"gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz",
                    "stashed_at": stashed_at,
                }

        finally:
            await self._release_ownership_lock(stash_lock_key, lock_value)
```

The only structural change is the new `async with _LockHeartbeat(...)` wrapper. All inner logic is preserved verbatim. The outer `finally` still releases the lock on every exit path (success, HTTPException, unexpected exception).

- [ ] **Step 4: Run all stash tests**

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager_stash.py -v
```

Expected: all existing tests + 2 new tests pass.

- [ ] **Step 5: Commit (bilingual EN+FR)**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git commit -m "$(cat <<'EOF'
fix(crawler-service): wrap stash_crawl tar+cleanup with _LockHeartbeat

EN:
Stash operations on large crawls (e.g. 2.1 GB observed at 23 min tar) would
let the 600s lock TTL expire mid-op; nginx then retried the POST on the next
upstream replica, which acquired a fresh lock and started a second tar over
the same source dir. The first replica's post-tar cleanup deleted files
mid-read for the others (incident: crawl 6250, 2026-05-20). Wrap the
tar + stashed_at + cleanup block in _LockHeartbeat so the TTL is refreshed
every 300s via Lua CAS while the op runs.

FR:
Les operations stash sur des crawls volumineux (ex. 2.1 GB observe en 23
min de tar) laissaient le TTL de 600s du lock expirer en cours d'execution
; nginx retentait alors le POST sur la replique upstream suivante, qui
acquerait un lock frais et demarrait un second tar sur le meme repertoire
source. Le cleanup post-tar de la premiere replique supprimait des fichiers
en cours de lecture pour les autres (incident : crawl 6250, 2026-05-20).
Encapsule le bloc tar + stashed_at + cleanup dans _LockHeartbeat pour
rafraichir le TTL toutes les 300s via Lua CAS pendant l'execution.
EOF
)"
```

```json:metadata
{"files":["apps-microservices/crawler-service/app/core/crawler_manager.py","apps-microservices/crawler-service/tests/test_crawler_manager_stash.py"],"verifyCommand":"cd apps-microservices/crawler-service && pytest tests/test_crawler_manager_stash.py -v","acceptanceCriteria":["async with _LockHeartbeat wraps tar+cleanup","Existing tests pass","test_stash_lock_survives_long_tar passes","test_stash_lock_released_on_replica_crash_simulation passes"]}
```

---

## Task 3: Migrate `archive_lock` to ownership-safe + heartbeat

**Goal:** Replace the constant-value `SET NX` + raw `DEL` archive lock with the existing ownership-safe pair, and wrap the tar block with `_LockHeartbeat`. Preserve the PHP cron caller contract.

**Native task:** #35. Blocked by T1.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (around lines 1678-1851 inside `archive_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add 3 tests)

**Acceptance Criteria:**
- [ ] Archive uses `_acquire_ownership_lock(archive_lock_key, settings.ARCHIVE_LOCK_TTL_SECONDS)` (returns replica-id-tagged value)
- [ ] On lock-held → 409 `"Archiving for crawl '{id}' is already in progress."` (exact same string)
- [ ] Release in `finally` uses `_release_ownership_lock(archive_lock_key, lock_value)` (ownership-safe Lua DEL)
- [ ] Tar + `_mark_as_archived` + return are wrapped in `_LockHeartbeat`
- [ ] 409 "already been archived" body string at line 1665 unchanged (PHP regex match dependency)
- [ ] Success response shape unchanged: `{'crawl_id', 'archive_status', 'archive_size_bytes'}`
- [ ] 3 new tests pass: long-tar holds lock, response shape unchanged, ownership-safe release

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -k archive -v` → all pass

**Steps:**

- [ ] **Step 1: Write new tests first**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
import asyncio
import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_archive_lock_holds_during_long_tar(
    cm_instance, archive_job_info, monkeypatch
):
    """Tar that runs past initial TTL keeps lock via heartbeat; concurrent
    attempt gets 409."""
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "ARCHIVE_LOCK_TTL_SECONDS", 2)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_MAX_DURATION_SECONDS", 30)

    async def slow_tar():
        await asyncio.sleep(4)

    # Patch the heavy tar to a fast sleep, but keep the lock logic
    monkeypatch.setattr(
        cm_instance, "_create_archive_for_test", slow_tar, raising=False,
    )

    task1 = asyncio.create_task(cm_instance.archive_crawl(archive_job_info))
    await asyncio.sleep(2.5)  # past initial TTL=2s

    with pytest.raises(HTTPException) as exc_info:
        await cm_instance.archive_crawl(archive_job_info)
    assert exc_info.value.status_code == 409
    assert "already in progress" in str(exc_info.value.detail).lower()

    result = await task1
    assert "archive_status" in result


def test_archive_409_body_string_unchanged():
    """The PHP cron at 3_archive_eligible_domains.php line 375 matches
    `already been archived` via stripos. Asserting the literal string
    remains so we cannot accidentally regress the caller contract."""
    import inspect
    from app.core import crawler_manager as cm_module
    src = inspect.getsource(cm_module.CrawlerManager.archive_crawl)
    assert "already been archived" in src, (
        "PHP cron depends on this exact substring at line 1665; do not change."
    )
    assert "is already in progress" in src, (
        "Lock-held 409 detail string is also a caller-visible contract."
    )


@pytest.mark.asyncio
async def test_archive_lock_release_is_ownership_safe(cm_instance):
    """A different replica's value cannot DEL our lock."""
    lock_key = "archive_lock:ownership_test"
    our_value = await cm_instance._acquire_ownership_lock(lock_key, 60)
    assert our_value is not None

    # Pretend a different replica tries to release with the wrong value
    released = await cm_instance._release_ownership_lock(lock_key, "wrong-replica-id")
    assert released is False

    # Our own release succeeds
    released = await cm_instance._release_ownership_lock(lock_key, our_value)
    assert released is True
```

- [ ] **Step 2: Run new tests to confirm RED**

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager.py::test_archive_lock_holds_during_long_tar tests/test_crawler_manager.py::test_archive_409_body_string_unchanged tests/test_crawler_manager.py::test_archive_lock_release_is_ownership_safe -v
```

Expected: 3 failures (the long-tar test would not get heartbeat refresh; the string test would still pass on current code since strings already exist; the ownership-safe test would pass since helpers exist — verify carefully which of these are red. The long-tar test is the load-bearing red.)

- [ ] **Step 3: Modify `archive_crawl` to use ownership-safe lock + heartbeat**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, replace the block at lines 1678-1851. Current block:

```python
        # Acquire a Redis lock to prevent concurrent archiving of the same crawl
        lock_key = f"archive_lock:{crawl_id}"
        # 30 min TTL: large crawls can take >5 min to archive via shutil.make_archive
        lock_acquired = await cache_service.redis_client.set(lock_key, "1", nx=True, ex=1800)
        if not lock_acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archiving for crawl '{crawl_id}' is already in progress."
            )

        try:
            # ... archive body (tar, _mark_as_archived, return) ...
        finally:
            await cache_service.redis_client.delete(lock_key)
```

Replace with:

```python
        # Acquire ownership-safe Redis lock (replica-id-tagged value).
        # ARCHIVE_LOCK_TTL_SECONDS = 1800; _LockHeartbeat refreshes mid-op
        # so the TTL never expires during a long tar.
        archive_lock_key = f"archive_lock:{crawl_id}"
        lock_value = await self._acquire_ownership_lock(
            archive_lock_key, settings.ARCHIVE_LOCK_TTL_SECONDS
        )
        if lock_value is None:
            # Exact string preserved — 3_archive_eligible_domains.php matches
            # this in its 409 success-signal logic. Do not modify.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archiving for crawl '{crawl_id}' is already in progress."
            )

        try:
            async with _LockHeartbeat(
                self,
                archive_lock_key,
                lock_value,
                ttl_seconds=settings.ARCHIVE_LOCK_TTL_SECONDS,
                interval_seconds=settings.LOCK_HEARTBEAT_INTERVAL_SECONDS,
                max_duration_seconds=settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS,
            ):
                # ... ENTIRE existing archive body unchanged ...
                # (tar, integrity, _mark_as_archived, return dict)
        finally:
            await self._release_ownership_lock(archive_lock_key, lock_value)
```

Concrete diff at line 1678-1686 (replace 9 lines):

```python
        # OLD:
        # Acquire a Redis lock to prevent concurrent archiving of the same crawl
        # lock_key = f"archive_lock:{crawl_id}"
        # 30 min TTL: large crawls can take >5 min to archive via shutil.make_archive
        # lock_acquired = await cache_service.redis_client.set(lock_key, "1", nx=True, ex=1800)
        # if not lock_acquired:
        #     raise HTTPException(
        #         status_code=status.HTTP_409_CONFLICT,
        #         detail=f"Archiving for crawl '{crawl_id}' is already in progress."
        #     )

        # NEW:
        archive_lock_key = f"archive_lock:{crawl_id}"
        lock_value = await self._acquire_ownership_lock(
            archive_lock_key, settings.ARCHIVE_LOCK_TTL_SECONDS
        )
        if lock_value is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archiving for crawl '{crawl_id}' is already in progress."
            )
```

At line 1688 (replace the bare `try:` with the heartbeat-wrapped `try:`):

```python
        try:
            async with _LockHeartbeat(
                self,
                archive_lock_key,
                lock_value,
                ttl_seconds=settings.ARCHIVE_LOCK_TTL_SECONDS,
                interval_seconds=settings.LOCK_HEARTBEAT_INTERVAL_SECONDS,
                max_duration_seconds=settings.LOCK_HEARTBEAT_MAX_DURATION_SECONDS,
            ):
                # ... existing body lines 1689-1849 indented +4 spaces ...
```

All inner body lines 1689 through 1849 (the entire archive_crawl body up to and including the success `return` and the existing inner exception handlers) must be re-indented by 4 spaces to live inside the `async with`. The line 1850 `finally:` and line 1851 (old `delete`) become:

```python
        finally:
            await self._release_ownership_lock(archive_lock_key, lock_value)
```

Variable rename: the old `lock_key` is renamed `archive_lock_key` consistently throughout the function for clarity (mirrors `stash_lock_key` pattern).

- [ ] **Step 4: Run archive tests + full test suite for the file**

```bash
cd apps-microservices/crawler-service
pytest tests/test_crawler_manager.py -v
```

Expected: all archive tests pass (new + existing).

- [ ] **Step 5: Commit (bilingual EN+FR)**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "$(cat <<'EOF'
fix(crawler-service): archive_lock ownership-safe + _LockHeartbeat wrapper

EN:
archive_lock previously used a constant value '1' with raw DEL on release;
a slow replica's DEL after TTL expiry would silently unblock a new replica's
lock and enable the same concurrent-tar race seen in stash (crawl 6250).
Migrate to the existing ownership-safe acquire/release pair (replica-id-tagged
value + Lua CAS DEL), and wrap the tar body with _LockHeartbeat so the TTL
refreshes every 300s while archiving runs. PHP cron contract preserved:
409 detail strings and 200 response body shape unchanged.

FR:
archive_lock utilisait auparavant une valeur constante '1' avec un DEL brut
a la liberation ; un DEL tardif d'une replique apres expiration du TTL
supprimait silencieusement le lock d'une nouvelle replique et exposait au
meme race concurrent observe sur stash (crawl 6250). Migration vers la
paire ownership-safe acquire/release existante (valeur tagguee replica-id +
DEL Lua CAS), et encapsulation du corps tar avec _LockHeartbeat pour que
le TTL se rafraichisse toutes les 300s pendant l'archivage. Contrat du cron
PHP preserve : strings 409 et forme de la reponse 200 inchangees.
EOF
)"
```

```json:metadata
{"files":["apps-microservices/crawler-service/app/core/crawler_manager.py","apps-microservices/crawler-service/tests/test_crawler_manager.py"],"verifyCommand":"cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -k archive -v","acceptanceCriteria":["Ownership-safe acquire/release used","_LockHeartbeat wraps tar block","409 'already in progress' string unchanged","409 'already been archived' string unchanged","200 response body shape unchanged","3 new tests pass"]}
```

---

## Task 4: Disable nginx upstream POST retry on /stash + /unstash + /archive

**Goal:** Add a regex location BEFORE the existing `/crawler/` prefix location in both api-gateway-go and api-gateway nginx configs. The new location targets `/crawler/(stash|unstash|archive)/...` and disables `proxy_next_upstream`.

**Native task:** #36. Standalone (no dependency on T0-T3).

**Files:**
- Modify: `apps-microservices/api-gateway-go/nginx.conf`
- Modify: `apps-microservices/api-gateway/nginx.conf`

**Acceptance Criteria:**
- [ ] Regex location `~ ^/crawler/(stash|unstash|archive)/` added before the prefix `/crawler/` block in both files
- [ ] New location: `proxy_next_upstream off; proxy_read_timeout 14400s; proxy_send_timeout 14400s; proxy_connect_timeout 60s;`
- [ ] Standard proxy headers preserved (Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto)
- [ ] Existing `/crawler/` prefix block unchanged (keeps current retry behavior for /status, /capacity, /start)
- [ ] Comment block above the regex location citing the incident (crawl 6250, 2026-05-20)
- [ ] Both files pass `nginx -t` syntax check

**Verify:**

```bash
# api-gateway-go
docker run --rm \
    -v "$PWD/apps-microservices/api-gateway-go/nginx.conf:/etc/nginx/nginx.conf:ro" \
    nginx:alpine nginx -t

# api-gateway
docker run --rm \
    -v "$PWD/apps-microservices/api-gateway/nginx.conf:/etc/nginx/nginx.conf:ro" \
    nginx:alpine nginx -t
```

Expected: both report `nginx: configuration file /etc/nginx/nginx.conf test is successful`.

**Steps:**

- [ ] **Step 1: Modify `apps-microservices/api-gateway-go/nginx.conf`**

Insert the new regex location BEFORE the existing `location /crawler/` block (line 20). Final file structure:

```nginx
events {
    worker_connections 1024;
}

http {
    resolver 127.0.0.11 valid=5s;

    server {
        listen 8050;
        client_max_body_size 200m;

        # Long-running synchronous endpoints (stash, unstash, archive) — POST
        # retry must NOT happen at nginx layer. Each retry would hit a different
        # backend replica, which acquires a fresh lock after the previous
        # replica's lock TTL expires, causing a concurrent tar + cleanup race.
        # Incident reference: crawl 6250 on 2026-05-20.
        # Lock + heartbeat handle replica-side serialization. PHP client owns
        # the retry policy (3 attempts, 503-only).
        # nginx regex locations are matched BEFORE prefix locations, so this
        # block intercepts stash/unstash/archive before the generic /crawler/
        # location below.
        location ~ ^/crawler/(stash|unstash|archive)/ {
            set $crawler_backend "http://crawler-service:8503";
            rewrite ^/crawler/(.*) /$1 break;

            proxy_pass $crawler_backend;
            proxy_next_upstream off;
            proxy_read_timeout 14400s;       # matches LOCK_HEARTBEAT_MAX_DURATION_SECONDS
            proxy_send_timeout 14400s;
            proxy_connect_timeout 60s;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # 1. Crawler Service (existing default routing — retry behavior preserved)
        location /crawler/ {
            set $crawler_backend "http://crawler-service:8503";
            rewrite ^/crawler/(.*) /$1 break;

            proxy_pass $crawler_backend;
            proxy_next_upstream error timeout http_503 non_idempotent;
            proxy_read_timeout 600s;
            proxy_connect_timeout 600s;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # 2. Migration (Crawler Service)
        location /migration/ {
            # ... unchanged ...
        }

        # 3. Image Comparison Service
        location /comparator/ {
            # ... unchanged ...
        }

        # Root fallback
        location / {
            return 404;
        }
    }
}
```

- [ ] **Step 2: Apply identical change to `apps-microservices/api-gateway/nginx.conf`**

The two files are kept in parity. Use the same regex location block verbatim, inserted at the same position (before the existing `/crawler/` prefix block).

- [ ] **Step 3: Validate syntax (both files)**

```bash
docker run --rm \
    -v "$PWD/apps-microservices/api-gateway-go/nginx.conf:/etc/nginx/nginx.conf:ro" \
    nginx:alpine nginx -t

docker run --rm \
    -v "$PWD/apps-microservices/api-gateway/nginx.conf:/etc/nginx/nginx.conf:ro" \
    nginx:alpine nginx -t
```

Expected: each prints `nginx: the configuration file /etc/nginx/nginx.conf syntax is ok` then `nginx: configuration file /etc/nginx/nginx.conf test is successful`.

- [ ] **Step 4: Commit (bilingual EN+FR)**

```bash
git add apps-microservices/api-gateway-go/nginx.conf apps-microservices/api-gateway/nginx.conf
git commit -m "$(cat <<'EOF'
fix(gateways): disable nginx POST retry on /crawler/(stash|unstash|archive)/

EN:
The default /crawler/ location uses proxy_next_upstream with non_idempotent,
which retries POST requests on upstream timeout. For long-running endpoints
(stash, unstash, archive) this caused multiple replicas to run the same op
concurrently after the in-flight replica's lock TTL expired (incident: crawl
6250, 2026-05-20). Add a regex location matched before the prefix that
disables the retry and bumps proxy_read_timeout to 14400s, matching the
LOCK_HEARTBEAT_MAX_DURATION_SECONDS cap. Both api-gateway-go and api-gateway
updated in parity.

FR:
La location /crawler/ par defaut utilise proxy_next_upstream avec
non_idempotent, ce qui retente les requetes POST en cas de timeout upstream.
Pour les endpoints longs (stash, unstash, archive) cela faisait executer la
meme operation en parallele sur plusieurs repliques apres l'expiration du
TTL du lock de la replique en cours (incident : crawl 6250, 2026-05-20).
Ajout d'une location regex evaluee avant le prefix qui desactive le retry et
augmente proxy_read_timeout a 14400s, alignee sur la valeur de
LOCK_HEARTBEAT_MAX_DURATION_SECONDS. api-gateway-go et api-gateway mis a
jour en parite.
EOF
)"
```

```json:metadata
{"files":["apps-microservices/api-gateway-go/nginx.conf","apps-microservices/api-gateway/nginx.conf"],"verifyCommand":"docker run --rm -v $PWD/apps-microservices/api-gateway-go/nginx.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t && docker run --rm -v $PWD/apps-microservices/api-gateway/nginx.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t","acceptanceCriteria":["Regex location ahead of prefix in both files","proxy_next_upstream off","proxy_read_timeout 14400s","Existing /crawler/ block unchanged","nginx -t passes on both"]}
```

---

## Task 5: Delete dead `crawler-service/nginx.conf` + README cleanup

**Goal:** Remove the obsolete nginx.conf (no longer in docker-compose routing path) and the README line that mentions it, eliminating operator confusion about which config controls crawler routing.

**Native task:** #37. Standalone.

**Files:**
- Delete: `apps-microservices/crawler-service/nginx.conf`
- Modify: `apps-microservices/crawler-service/README.md` (line 19)

**Acceptance Criteria:**
- [ ] File removed via `git rm`
- [ ] README no longer mentions nginx.conf
- [ ] `git grep "crawler-service/nginx.conf"` returns only `graphify-out/` (regeneratable artifacts) — no production refs
- [ ] No docker-compose or Dockerfile breakage

**Verify:**

```bash
git ls-files apps-microservices/crawler-service/nginx.conf
# Expected: (empty)

grep -n "nginx.conf" apps-microservices/crawler-service/README.md
# Expected: (empty)

git grep "crawler-service/nginx.conf"
# Expected: only matches under graphify-out/
```

**Steps:**

- [ ] **Step 1: Verify no production refs (recheck before deletion)**

```bash
git grep -l "crawler-service/nginx.conf"
```

Expected: only `graphify-out/graph.html` and `graphify-out/graph.json` (regeneratable). If any other file appears, STOP and investigate before deleting.

- [ ] **Step 2: Delete the file**

```bash
git rm apps-microservices/crawler-service/nginx.conf
```

- [ ] **Step 3: Modify README to remove line 19**

Open `apps-microservices/crawler-service/README.md` and remove the bullet line:

```
-   `nginx.conf`: Nginx configuration file that acts as a reverse proxy and load balancer for the crawler service replicas.
```

If the line is part of a numbered or bulleted list of files, also rebalance adjacent context (e.g. preceding/following bullets) to maintain readability.

- [ ] **Step 4: Verify**

```bash
git ls-files apps-microservices/crawler-service/nginx.conf
grep -n "nginx.conf" apps-microservices/crawler-service/README.md
```

Both should be empty.

- [ ] **Step 5: Commit (bilingual EN+FR)**

```bash
git add apps-microservices/crawler-service/nginx.conf apps-microservices/crawler-service/README.md
git commit -m "$(cat <<'EOF'
chore(crawler-service): remove unused nginx.conf + README ref

EN:
The crawler-service nginx.conf is not mounted in docker-compose.yml (no
crawler-service-lb container exists, unlike api-classification-lb,
api-rest-milvus-lb, nextjs-formulaire-hp-lb). All crawler routing now flows
through api-gateway-go / api-gateway sidecars. Delete the file and the
README bullet that references it to avoid operator confusion about which
nginx config controls crawler routing.

FR:
Le nginx.conf de crawler-service n'est pas monte dans docker-compose.yml
(aucun container crawler-service-lb n'existe, contrairement a
api-classification-lb, api-rest-milvus-lb, nextjs-formulaire-hp-lb). Tout
le routing crawler passe maintenant par les sidecars api-gateway-go /
api-gateway. Suppression du fichier et de la ligne README qui le
reference, pour eviter toute confusion operationnelle sur la config nginx
en place.
EOF
)"
```

```json:metadata
{"files":["apps-microservices/crawler-service/nginx.conf","apps-microservices/crawler-service/README.md"],"verifyCommand":"git ls-files apps-microservices/crawler-service/nginx.conf && grep -n nginx.conf apps-microservices/crawler-service/README.md","acceptanceCriteria":["File deleted","README ref removed","No remaining production refs","docker-compose unaffected"]}
```

---

## Final integration test (after all tasks complete)

Once all 6 tasks land, run the full test suite and a manual smoke check.

```bash
cd apps-microservices/crawler-service
pytest tests/ -v
```

Expected: 100% pass.

**Manual smoke (post-deploy on dev server):**

```bash
# 1. Pick a finished, large terminal crawl (e.g. > 500 MB)
CRAWL_ID=<target_id>

# 2. Trigger stash with short client timeout (simulate operator drop)
curl -X POST "https://api.hellopro.eu/${SERVICE_CRAWLING}/stash/${CRAWL_ID}" --max-time 60 -i

# 3. Watch lock TTL in Redis from any replica
docker exec redis redis-cli TTL stash_lock:${CRAWL_ID}
# Expected: hovers around 1800, refreshes upward every ~300s

# 4. Tail logs across replicas
for n in $(docker ps --filter "name=crawler-service-" --format "{{.Names}}"); do
    docker logs "$n" 2>&1 | grep -E "(stash|heartbeat|FileNotFoundError)" | tail -10
done
# Expected: one replica logs Stashed + Cleaned data; no FileNotFoundError;
# no second replica reports concurrent stash attempt.

# 5. Verify the tar landed
docker exec crawler-service-1 ls -la /app/stash/${CRAWL_ID}.tar.gz
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Tasks covering it |
|---|---|
| §1 Problem statement | (informational, no task) |
| §2 Root cause analysis | (informational) |
| §3 Risk surface | T2 (stash), T3 (archive), T4 (nginx). Unstash deferred out per spec §10 |
| §4 Caller contract | T3 acceptance criteria preserve 409 strings + 200 response shape |
| §5.1 `_LockHeartbeat` helper | T1 |
| §5.2 Config additions | T0 |
| §5.3 Stash integration | T2 |
| §5.4 Archive migration | T3 |
| §5.5 nginx config | T4 |
| §5.6 Dead-code deletion | T5 |
| §6 Behavior under scenarios | Validated by T2, T3, T4 tests + final manual smoke |
| §7 Testing strategy | Tests inside T1, T2, T3; manual smoke at end of plan |
| §8 Error handling | Implementation detail inside T1 (`_LockHeartbeat`) and T3 (archive 500 path unchanged) |
| §9 Implementation tasks | All 6 tasks present |
| §10 Out of scope | Explicitly NOT implemented: unstash heartbeat, BackgroundTasks rewrite, webhook callbacks, Prometheus counters |

No gaps.

**2. Placeholder scan:** No "TBD", "TODO", "implement later", or "similar to Task N" patterns. Every code block contains complete content.

**3. Type / signature consistency:**

- `_LockHeartbeat.__init__` signature consistent across T1 definition, T2 stash usage, T3 archive usage: `(cm, lock_key, lock_value, ttl_seconds, interval_seconds, max_duration_seconds)`.
- `_acquire_ownership_lock(lock_key, ttl_seconds) -> Optional[str]` matches T1 (used in tests) and T3 (used in archive migration). Returns `REPLICA_ID` string on success — used as `lock_value` in heartbeat, then passed to `_release_ownership_lock(lock_key, expected_value)`.
- Settings names: `STASH_LOCK_TTL_SECONDS`, `ARCHIVE_LOCK_TTL_SECONDS`, `LOCK_HEARTBEAT_INTERVAL_SECONDS`, `LOCK_HEARTBEAT_MAX_DURATION_SECONDS` — same names everywhere they appear.
- nginx regex: `~ ^/crawler/(stash|unstash|archive)/` — same in both gateways.
- Lock keys: `stash_lock:{id}`, `archive_lock:{id}`, `unstash_lock:{id}` — consistent.

No inconsistencies found.
