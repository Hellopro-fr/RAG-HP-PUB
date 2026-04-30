# Crawler Stale-Detector Marker-Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the crawler-service stale-detector read `_completion_marker.json` before marking a job failed, so jobs that already terminated (Redis state drifted to non-terminal) are reconciled instead of fired as bogus failure webhooks.

**Architecture:** Add one private async helper `_load_completion_marker_or_none(storage_path)` to `CrawlerManager`. Insert a call at the top of the `if status in ("running","restarting_oom","stopping"):` branch inside `_reconcile_locked`. If marker is valid + terminal, reconcile Redis state from marker, decrement counter, release lock, skip webhook, `continue`. Else fall through to existing stale-failure logic.

**Tech Stack:** Python 3, FastAPI, asyncio, Redis (`cache_service`), `aiofiles`. Tests: pytest + pytest-asyncio + `pytest-mock` (`mocker`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-30-crawler-stale-detector-marker-check-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Modify | Add `_load_completion_marker_or_none` (~30 lines incl. docstring). Insert ~25-line block at top of `_reconcile_locked`'s non-terminal status branch (~L1900). |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | Modify | Add `TestStaleHandlerCompletionMarker` test class (4 cases) + helper unit tests (4 cases, optional small TestLoadCompletionMarker class). |

Single sub-problem (A). 2 files. ~150 LOC total. Tight for single plan.

**Pre-existing fixtures to reuse** (from `tests/test_crawler_manager.py`): the existing `TestStaleHandlerCounter` and `TestStaleHandlerKillProcess` classes already construct `CrawlerManager` instances with mocked `cache_service`. Read their setup to mirror the pattern.

---

## Task 1: Add `_load_completion_marker_or_none` helper + unit tests

**Goal:** New private async helper in `CrawlerManager` that reads + validates `_completion_marker.json`. Returns parsed dict if valid + terminal `final_status`, else `None`. Methods is dead code at end of task — `_reconcile_locked` not yet modified. Unit tests cover the 5 input scenarios independently.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — append helper inside `CrawlerManager` class. Place near other internal IO helpers (search for `_kill_process_group` or similar private methods to find a sensible insertion point).
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` — append new test class `TestLoadCompletionMarker` (or unit-test cluster) covering the helper.

**Acceptance Criteria:**
- [ ] `_load_completion_marker_or_none(self, storage_path: str) -> Optional[dict]` exists with full docstring per spec §4.1
- [ ] Helper returns `None` for: empty `storage_path`, missing file, IOError, malformed JSON, `final_status` not in `{"finished","failed","stopped"}`
- [ ] Helper returns parsed dict otherwise
- [ ] Uses `aiofiles.open` for async read
- [ ] Logs WARNING on `OSError` / `json.JSONDecodeError` / unknown `final_status`
- [ ] No callers wired in `_reconcile_locked` yet (dead code in this commit)
- [ ] `TestLoadCompletionMarker` test class with 5 cases passes
- [ ] `pytest tests/test_crawler_manager.py -v -k TestLoadCompletionMarker` → 5 PASS

**Verify:**

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestLoadCompletionMarker -v
```
Expected: 5 cases PASS, 0 fail.

```bash
grep -n "_load_completion_marker_or_none" apps-microservices/crawler-service/app/core/crawler_manager.py
```
Expected: 1 hit (definition only — no callers).

### Steps

- [ ] **Step 1: Read existing private helper style**

Open `apps-microservices/crawler-service/app/core/crawler_manager.py` around line 1865 (start of `_reconcile_locked`) and around line 844-855 (success-path marker write). Confirm:
- Existing `aiofiles.open` pattern: `async with aiofiles.open(marker_path, 'w') as f: await f.write(json.dumps(...))`
- Logger usage: `logger.warning(...)`, `logger.info(...)`
- Imports at top of file: `import os`, `import json`, `import aiofiles`, `from typing import Optional`

Pick insertion point inside the `CrawlerManager` class. Suggestion: immediately after `_kill_process_group` (search for that method name) or before `_reconcile_locked`. Preserve method ordering (private methods grouped).

- [ ] **Step 2: Read tests file structure**

Open `apps-microservices/crawler-service/tests/test_crawler_manager.py`. Find:
- `TestStaleHandlerCounter` class (~line 18-46) — note fixture pattern (likely `@pytest.fixture` for `manager`, mocked `cache_service`)
- `TestStaleHandlerKillProcess` class (~line 49-93) — async test pattern
- Imports at top of file

Note the `@pytest.mark.asyncio` decorator usage and any shared fixtures. Mirror these patterns.

- [ ] **Step 3: Write failing tests first (TDD red)**

Append to `tests/test_crawler_manager.py`:

```python
class TestLoadCompletionMarker:
    """
    Unit tests for CrawlerManager._load_completion_marker_or_none.

    Verifies the helper correctly distinguishes valid terminal markers
    from missing / malformed / unknown-status cases. Used by the
    reconciler stale-detection path to avoid spurious failure webhooks
    when Redis state has drifted from the on-disk completion marker.
    """

    @pytest.mark.asyncio
    async def test_empty_storage_path_returns_none(self, mocker):
        manager = _make_manager(mocker)
        result = await manager._load_completion_marker_or_none("")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_marker_file_returns_none(self, mocker, tmp_path):
        # tmp_path is a Path with no _completion_marker.json
        manager = _make_manager(mocker)
        result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_json_returns_none_and_logs_warning(
        self, mocker, tmp_path, caplog
    ):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text("{ not valid json")
        manager = _make_manager(mocker)
        with caplog.at_level("WARNING"):
            result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result is None
        assert any("failed to read" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_unknown_final_status_returns_none_and_logs_warning(
        self, mocker, tmp_path, caplog
    ):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text(json.dumps({"final_status": "weird_state", "exit_code": 0}))
        manager = _make_manager(mocker)
        with caplog.at_level("WARNING"):
            result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result is None
        assert any("unknown final_status" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("final_status", ["finished", "failed", "stopped"])
    async def test_valid_terminal_marker_returns_parsed_dict(
        self, mocker, tmp_path, final_status
    ):
        marker_data = {
            "final_status": final_status,
            "exit_code": 0,
            "end_timestamp": "2026-04-30T15:01:05.000000",
            "reason": "test",
        }
        marker = tmp_path / "_completion_marker.json"
        marker.write_text(json.dumps(marker_data))
        manager = _make_manager(mocker)
        result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result == marker_data


def _make_manager(mocker):
    """
    Builds a CrawlerManager with cache_service + dependencies mocked.
    Mirror the existing pattern used in TestStaleHandlerCounter (read it
    in the file before writing — copy that fixture verbatim if it lives
    inline). If a shared fixture already exists, use it instead.
    """
    # If existing fixture pattern uses mocker.patch on cache_service or
    # similar, replicate it here. Inspect TestStaleHandlerCounter to
    # confirm the canonical setup. Fall back to a bare CrawlerManager()
    # instantiation if the helper under test does NOT touch cache_service
    # (it only reads from disk).
    from app.core.crawler_manager import CrawlerManager
    return CrawlerManager()
```

NOTE on `_make_manager`: read `TestStaleHandlerCounter` first to see if there's an existing fixture (e.g. `@pytest.fixture def manager(...)`). If so, use that fixture instead of inventing `_make_manager`. The helper under test only reads from disk and uses `logger`, so a bare `CrawlerManager()` may work; but if `__init__` requires Redis/cache wiring, you must mock those.

If `pytest_collect` shows imports failing (e.g. `from app.core.crawler_manager import CrawlerManager` errors due to missing env), check existing tests for the canonical import path and PYTHONPATH setup.

- [ ] **Step 4: Run tests — confirm they FAIL**

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestLoadCompletionMarker -v
```
Expected: 5 FAIL with `AttributeError: 'CrawlerManager' object has no attribute '_load_completion_marker_or_none'`.

- [ ] **Step 5: Implement helper (TDD green)**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, insert the new method inside `CrawlerManager`. Indent with 4 spaces (match existing methods).

```python
    async def _load_completion_marker_or_none(self, storage_path: str) -> Optional[dict]:
        """
        Reads {storage_path}/_completion_marker.json and returns parsed dict if
        valid + has a recognized terminal final_status. Returns None otherwise.

        Used by _reconcile_locked to detect Redis state drift: a crawl may have
        completed (marker on disk) but Redis still shows status="running" due to
        a missed write, replica race, or aborted set_json. Trusting the marker
        avoids firing a spurious failure webhook.

        Pattern matches the read in app/router/crawler.py status endpoint.

        Suppresses all IO + JSON errors — failure to read = "no marker", which
        falls through to the existing stale-failure path (safest default).

        Args:
            storage_path: absolute path to the crawl's storage directory.

        Returns:
            Parsed marker dict (with final_status in {"finished","failed","stopped"})
            on success. None if the marker is missing, malformed, or has an
            unrecognized final_status.
        """
        if not storage_path:
            return None
        marker_path = os.path.join(storage_path, '_completion_marker.json')
        if not os.path.isfile(marker_path):
            return None
        try:
            async with aiofiles.open(marker_path, 'r') as f:
                content = await f.read()
            marker = json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                f"_load_completion_marker_or_none: failed to read {marker_path}: {e}"
            )
            return None

        final_status = marker.get("final_status")
        if final_status not in ("finished", "failed", "stopped"):
            logger.warning(
                f"_load_completion_marker_or_none: unknown final_status "
                f"'{final_status}' in {marker_path}"
            )
            return None
        return marker
```

Verify imports already present in the file: `os`, `json`, `aiofiles`, `Optional` from typing. If `Optional` not imported, add `from typing import Optional` to the existing typing import or top-of-file.

- [ ] **Step 6: Run tests — confirm they PASS**

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestLoadCompletionMarker -v
```
Expected: 5 PASS.

If pytest fails to import the test file: check that `tests/test_crawler_manager.py` already has `import json` and `import pytest` at the top (existing tests use them). If not, add them.

- [ ] **Step 7: Confirm `_reconcile_locked` not modified**

```bash
grep -nE "_load_completion_marker_or_none|_reconcile_locked" apps-microservices/crawler-service/app/core/crawler_manager.py
```
Expected: 1 hit for `_load_completion_marker_or_none` (definition) + 1 hit for `_reconcile_locked` (definition). NO call to `_load_completion_marker_or_none` from inside `_reconcile_locked` yet.

- [ ] **Step 8: Commit (FR per session preference; ask EN/FR/both before committing)**

Stage only the two modified files:
```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
```

Suggested FR commit message:

```
feat(crawler-service): ajout helper _load_completion_marker_or_none

Ajoute une methode privee async sur CrawlerManager pour lire et valider
le fichier {storage_path}/_completion_marker.json. Retourne le dict
parse si final_status in {finished, failed, stopped}, sinon None
(chemin vide / fichier absent / JSON invalide / final_status inconnu).

Utilise aiofiles + json. Toutes les erreurs IO et de parsing sont
absorbees (log WARNING). Le caller doit traiter None comme "pas de
marker" et appliquer son comportement par defaut.

Aucun changement de comportement dans ce commit : le helper n'est pas
encore appele depuis _reconcile_locked. Le branchement arrive dans le
commit suivant.

Tests : nouvelle classe TestLoadCompletionMarker (5 cas — chemin vide,
fichier absent, JSON malforme, final_status inconnu, marker valide
parametrise sur les 3 etats terminaux).

Spec : docs/superpowers/specs/2026-04-30-crawler-stale-detector-marker-check-design.md
```

Use HEREDOC `<<'EOF'` with bare `$var`.

⚠️ **Branch reminder:** ensure you are on `features/poc` branch before committing. Run `git branch --show-current` to confirm.

⚠️ **Graphify hook quirk:** the `graphify` post-commit hook may stage and rebuild graph artifacts in `graphify-out/`. If `git status` after commit shows `graphify-out/*` modified, that's the hook output — leave it alone. Do NOT add it to your commit. Verify your commit contains EXACTLY the 2 intended files via `git show HEAD --stat`.

```bash
git commit -m "$(cat <<'EOF'
<bilingual subject + body produced after user picks language; default FR per session>
EOF
)"
git show HEAD --stat   # MUST show exactly 2 files
```

If `git show` reveals extra files (e.g. WIP TS files in the index): `git reset --soft HEAD~1`, `git restore --staged <unwanted-file>`, recommit. Same recovery as the spec commit `8b578a3c` did earlier in this branch.

---

## Task 2: Wire helper into `_reconcile_locked` + integration tests

**Goal:** Activate the fix. Insert the marker check at the top of the `if status in ("running","restarting_oom","stopping"):` branch in `_reconcile_locked`. If marker is valid + terminal, reconcile Redis from marker and `continue`. Add 4 integration tests (`TestStaleHandlerCompletionMarker`) covering the new code path.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — insert ~25-line block at top of `_reconcile_locked`'s non-terminal-status branch (~L1900).
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` — append `TestStaleHandlerCompletionMarker` class (4 cases).

**Acceptance Criteria:**
- [ ] Insertion at top of `if status in ("running","restarting_oom","stopping"):` branch, BEFORE the heartbeat extraction (`last_heartbeat_str = ...`)
- [ ] When marker valid + terminal: `cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)`, `cache_service.delete_key(CRAWL_LOCK_PREFIX + crawl_id)`, `job_data["status"] = marker["final_status"]`, `del job_data["last_heartbeat"]` (if present), `cache_service.set_json(...)`, `_publish_update(crawl_id, marker_status)`, `continue`
- [ ] NO call to `_send_failure_webhook` when marker absorbs the case
- [ ] When marker missing/invalid: existing logic runs unchanged
- [ ] INFO log message present: `Job '{X}' has completion marker (final_status='{Y}') but Redis status is '{Z}'. Reconciling from marker; webhook skipped.`
- [ ] All 4 `TestStaleHandlerCompletionMarker` cases pass
- [ ] All existing `TestStaleHandler*` tests still pass (regression guard)

**Verify:**

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestStaleHandlerCompletionMarker -v
```
Expected: 4 PASS.

```bash
python -m pytest tests/test_crawler_manager.py -v -k TestStaleHandler
```
Expected: ALL existing TestStaleHandler* tests still PASS + 4 new ones PASS.

```bash
grep -nE "_load_completion_marker_or_none|continue\s*$" apps-microservices/crawler-service/app/core/crawler_manager.py | head -10
```
Expected: definition + 1 call inside `_reconcile_locked`.

### Steps

- [ ] **Step 1: Re-read `_reconcile_locked` body**

Open `apps-microservices/crawler-service/app/core/crawler_manager.py` lines 1892-2030 to confirm exact line numbers and surrounding code (line numbers may have shifted slightly due to Task 1's helper insertion).

Locate this block (around L1900 pre-Task 2):

```python
                if status in ("running", "restarting_oom", "stopping"):
                    # Check for staleness — applies to both running and restarting_oom jobs.
                    # A restarting_oom job holds a concurrency slot but may be orphaned
                    # if the replica that owned it crashed without cleanup.
                    last_heartbeat_str = job_data.get("last_heartbeat")
```

The marker-check block must be inserted IMMEDIATELY after the `if status in (...)` line and BEFORE the existing comment + `last_heartbeat_str` line.

- [ ] **Step 2: Write failing integration tests first (TDD red)**

Append to `tests/test_crawler_manager.py`:

```python
class TestStaleHandlerCompletionMarker:
    """
    Verifies _reconcile_locked reads the on-disk completion marker before
    declaring a job stale. Covers the crawl 6244 incident: Redis state
    drifted to status='running' despite the success path having written
    a finished marker, causing a bogus failure webhook.
    """

    @pytest.mark.asyncio
    async def test_marker_finished_reconciles_redis_skips_webhook(
        self, mocker, tmp_path
    ):
        # Setup: Redis has a job with status='running' + stale heartbeat
        # (well past STALE_JOB_THRESHOLD_LOCAL = 180s) + storage_path
        # pointing to tmp_path. Marker on disk says final_status='finished'.
        marker_data = {
            "final_status": "finished",
            "exit_code": 0,
            "end_timestamp": "2026-04-30T15:01:05.000000",
            "reason": "process_complete",
        }
        (tmp_path / "_completion_marker.json").write_text(json.dumps(marker_data))

        stale_time = (datetime.utcnow() - timedelta(seconds=600)).isoformat()
        job_key = "crawl_jobs:6244"
        job_data = {
            "crawl_id": "6244",
            "status": "running",
            "last_heartbeat": stale_time,
            "storage_path": str(tmp_path),
            "domain": "test.example",
            "failure_callback_url": "http://bo.example/webhook",
            "crawl_mode": "standard",
            "replica_id": os.uname().nodename,
        }

        manager = _make_manager_with_redis(mocker, jobs={job_key: job_data})

        # Spy on _send_failure_webhook to assert it is NOT called.
        webhook_spy = mocker.patch.object(manager, "_send_failure_webhook")
        decrement_spy = mocker.patch.object(
            manager._cache_service_or_global(), "safe_decrement_key"  # see _make_manager_with_redis for shape
        )
        delete_spy = mocker.patch.object(
            manager._cache_service_or_global(), "delete_key"
        )
        set_json_spy = mocker.patch.object(
            manager._cache_service_or_global(), "set_json"
        )

        await manager._reconcile_locked()

        # Webhook NOT sent.
        webhook_spy.assert_not_called()
        # Counter decremented exactly once.
        assert decrement_spy.call_count == 1
        # Lock deleted.
        delete_spy.assert_any_call("crawl_lock:6244")
        # Redis updated with marker_status.
        set_json_args = set_json_spy.call_args_list
        assert any(
            (call.args[0] == job_key and call.args[1].get("status") == "finished")
            for call in set_json_args
        )

    @pytest.mark.asyncio
    async def test_marker_failed_reconciles_redis_skips_webhook(
        self, mocker, tmp_path
    ):
        # Same as above but marker.final_status='failed'. Webhook was
        # already sent at original failure path; reconciler must NOT re-send.
        marker_data = {
            "final_status": "failed",
            "exit_code": 137,
            "end_timestamp": "2026-04-30T15:00:00.000000",
            "reason": "sigkill",
        }
        (tmp_path / "_completion_marker.json").write_text(json.dumps(marker_data))

        stale_time = (datetime.utcnow() - timedelta(seconds=600)).isoformat()
        job_key = "crawl_jobs:6245"
        job_data = {
            "crawl_id": "6245",
            "status": "running",
            "last_heartbeat": stale_time,
            "storage_path": str(tmp_path),
            "domain": "test.example",
            "failure_callback_url": "http://bo.example/webhook",
            "crawl_mode": "standard",
            "replica_id": os.uname().nodename,
        }

        manager = _make_manager_with_redis(mocker, jobs={job_key: job_data})
        webhook_spy = mocker.patch.object(manager, "_send_failure_webhook")
        set_json_spy = mocker.patch.object(
            manager._cache_service_or_global(), "set_json"
        )

        await manager._reconcile_locked()

        webhook_spy.assert_not_called()
        assert any(
            (call.args[0] == job_key and call.args[1].get("status") == "failed")
            for call in set_json_spy.call_args_list
        )

    @pytest.mark.asyncio
    async def test_marker_missing_falls_through_to_stale_failure(
        self, mocker, tmp_path
    ):
        # No marker file + stale heartbeat → existing stale path fires.
        # Asserts _send_failure_webhook IS called (regression guard).
        stale_time = (datetime.utcnow() - timedelta(seconds=600)).isoformat()
        job_key = "crawl_jobs:6246"
        job_data = {
            "crawl_id": "6246",
            "status": "running",
            "last_heartbeat": stale_time,
            "storage_path": str(tmp_path),  # tmp_path has NO marker file
            "domain": "test.example",
            "failure_callback_url": "http://bo.example/webhook",
            "crawl_mode": "standard",
            "replica_id": os.uname().nodename,
        }

        manager = _make_manager_with_redis(mocker, jobs={job_key: job_data})
        webhook_spy = mocker.patch.object(manager, "_send_failure_webhook")

        await manager._reconcile_locked()

        # Webhook IS sent (existing stale path).
        webhook_spy.assert_called()

    @pytest.mark.asyncio
    async def test_marker_malformed_falls_through_to_stale_failure(
        self, mocker, tmp_path, caplog
    ):
        # Marker file exists but invalid JSON → fall through, log warning.
        (tmp_path / "_completion_marker.json").write_text("{ not valid json")

        stale_time = (datetime.utcnow() - timedelta(seconds=600)).isoformat()
        job_key = "crawl_jobs:6247"
        job_data = {
            "crawl_id": "6247",
            "status": "running",
            "last_heartbeat": stale_time,
            "storage_path": str(tmp_path),
            "domain": "test.example",
            "failure_callback_url": "http://bo.example/webhook",
            "crawl_mode": "standard",
            "replica_id": os.uname().nodename,
        }

        manager = _make_manager_with_redis(mocker, jobs={job_key: job_data})
        webhook_spy = mocker.patch.object(manager, "_send_failure_webhook")

        with caplog.at_level("WARNING"):
            await manager._reconcile_locked()

        # Webhook IS sent (existing stale path).
        webhook_spy.assert_called()
        # WARNING logged for the malformed marker.
        assert any("failed to read" in r.message for r in caplog.records)


def _make_manager_with_redis(mocker, jobs: dict):
    """
    Builds a CrawlerManager with cache_service mocked to return the given
    jobs dict on scan_keys_by_prefix + pipeline.execute().

    Mirror the existing pattern used in TestStaleHandlerCounter — read it
    in the file before writing this helper. If the existing pattern uses
    a different name (e.g. _build_manager, fixture-based), use that
    instead and adapt these tests accordingly.
    """
    from app.core.crawler_manager import CrawlerManager
    manager = CrawlerManager()

    # Patch cache_service.scan_keys_by_prefix to return the jobs' keys.
    mocker.patch(
        "app.core.crawler_manager.cache_service.scan_keys_by_prefix",
        return_value=list(jobs.keys()),
    )

    # Patch the Redis pipeline to return jobs as JSON strings in order.
    fake_pipe = mocker.MagicMock()
    fake_pipe.get = mocker.MagicMock()
    fake_pipe.execute = mocker.AsyncMock(
        return_value=[json.dumps(j) for j in jobs.values()]
    )
    mocker.patch(
        "app.core.crawler_manager.cache_service.redis_client.pipeline",
        return_value=fake_pipe,
    )
    mocker.patch(
        "app.core.crawler_manager.cache_service.set_json",
        new_callable=mocker.AsyncMock,
    )
    mocker.patch(
        "app.core.crawler_manager.cache_service.delete_key",
        new_callable=mocker.AsyncMock,
    )
    mocker.patch(
        "app.core.crawler_manager.cache_service.safe_decrement_key",
        new_callable=mocker.AsyncMock,
    )
    mocker.patch(
        "app.core.crawler_manager.cache_service.get_key",
        new_callable=mocker.AsyncMock,
        return_value="0",
    )
    mocker.patch.object(manager, "_publish_update", new_callable=mocker.AsyncMock)
    # Avoid leader-lock complications: skip directly to _reconcile_locked.
    return manager
```

Add at top of test file (if not already present):
```python
import json
import os
from datetime import datetime, timedelta
import pytest
```

NOTE on `_make_manager_with_redis`: the exact mock surface depends on how `cache_service` is wired. Read existing `TestStaleHandlerCounter` setup BEFORE writing this — copy its mock pattern. If the existing tests use a `fake_redis` or `aioredis` mock, use the same. The skeleton above is a starting point; expect to adapt to the file's conventions.

Also: `manager._cache_service_or_global()` is a placeholder for "however the existing tests refer to the patched cache_service". If `cache_service` is module-level, patch via the module path (`app.core.crawler_manager.cache_service.X`). Adjust the spies accordingly.

- [ ] **Step 3: Run tests — confirm they FAIL**

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestStaleHandlerCompletionMarker -v
```
Expected: 4 FAIL. The first two fail because the marker-check block doesn't exist yet (so `_send_failure_webhook` IS called). The last two should still PASS (they assert webhook IS called, which is current behavior — but they may fail on mock setup).

If mock setup errors dominate, fix mock shape first, re-run, then ensure tests 1+2 fail with `webhook_spy.assert_not_called()` AssertionError. That's the proper red.

- [ ] **Step 4: Implement marker-check block (TDD green)**

In `_reconcile_locked` body, find:

```python
                if status in ("running", "restarting_oom", "stopping"):
                    # Check for staleness — applies to both running and restarting_oom jobs.
                    # A restarting_oom job holds a concurrency slot but may be orphaned
                    # if the replica that owned it crashed without cleanup.
                    last_heartbeat_str = job_data.get("last_heartbeat")
```

Insert the new block IMMEDIATELY after the `if status in (...)` line, BEFORE the existing comment:

```python
                if status in ("running", "restarting_oom", "stopping"):
                    # Marker check (NEW): Redis may show non-terminal status
                    # while the on-disk completion marker indicates the crawl
                    # already ended (state drift from missed write or replica
                    # race — observed on crawl 6244 where success path wrote
                    # marker + status='finished' but Redis status remained
                    # 'running' 6 minutes later when reconciler fired).
                    #
                    # Trust marker as ground truth; skip the failure webhook
                    # (already sent at original finalize) and reconcile Redis
                    # state. Counter decrement + lock release still required —
                    # those resources were held by the stale running entry.
                    storage_path = job_data.get("storage_path", "")
                    marker = await self._load_completion_marker_or_none(storage_path)
                    if marker:
                        marker_status = marker["final_status"]
                        logger.info(
                            f"Job '{crawl_id}' has completion marker "
                            f"(final_status='{marker_status}') but Redis status "
                            f"is '{status}'. Reconciling from marker; webhook skipped."
                        )
                        # Release global slot (was held by stale running entry).
                        await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                        # Release distributed lock if still held.
                        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
                        # Reconcile Redis state from marker.
                        job_data["status"] = marker_status
                        if "last_heartbeat" in job_data:
                            del job_data["last_heartbeat"]
                        await cache_service.set_json(all_job_keys[i], job_data)
                        await self._publish_update(crawl_id, marker_status)
                        # Skip remaining stale-detection logic for this job.
                        continue

                    # Check for staleness — applies to both running and restarting_oom jobs.
                    # A restarting_oom job holds a concurrency slot but may be orphaned
                    # if the replica that owned it crashed without cleanup.
                    last_heartbeat_str = job_data.get("last_heartbeat")
                    # ... (rest of L1904-2024 unchanged)
```

Match indentation: the new block is at the same indent level as `last_heartbeat_str = job_data.get(...)`. The `if status in (...)` line is one less indent.

- [ ] **Step 5: Run tests — confirm they PASS**

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestStaleHandlerCompletionMarker -v
```
Expected: 4 PASS.

- [ ] **Step 6: Run full TestStaleHandler regression**

```bash
python -m pytest tests/test_crawler_manager.py -v -k TestStaleHandler
```
Expected: ALL existing TestStaleHandler* tests still PASS + 4 new TestStaleHandlerCompletionMarker PASS.

If a regression appears (existing tests fail), the marker-check block is leaking into the wrong scope or `continue` is skipping logic that other tests depend on. Re-read the diff carefully.

- [ ] **Step 7: Run helper unit tests too (regression for Task 1)**

```bash
python -m pytest tests/test_crawler_manager.py::TestLoadCompletionMarker -v
```
Expected: 5 PASS (still).

- [ ] **Step 8: Confirm `_reconcile_locked` modification is minimal**

```bash
git diff apps-microservices/crawler-service/app/core/crawler_manager.py | head -80
```

Expected: ONLY the marker-check block added. No deletions. The existing stale-detection logic (heartbeat extraction, `is_stale` computation, kill process, webhook send, etc.) untouched.

- [ ] **Step 9: Commit (FR)**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
```

Suggested FR commit message:

```
fix(crawler-service): _reconcile_locked lit le completion marker avant marquage failed

Active le correctif pour le bug observe sur crawl 6244 : le reconciler
voyait status=running dans Redis 6 min apres que le chemin success ait
ecrit le marker disque + mis Redis a finished, et envoyait un failure
webhook spurieux (exit_code=-1, OOM) a BO.

Le bloc d'insertion (top de la branche `if status in (running,
restarting_oom, stopping):`) lit {storage_path}/_completion_marker.json
via _load_completion_marker_or_none. Si valide :

  * decremente CRAWL_RUNNING_COUNT_KEY (slot etait reserve)
  * libere CRAWL_LOCK_PREFIX:{id}
  * met job_data["status"] = marker.final_status (finished/failed/stopped)
  * supprime last_heartbeat
  * persiste via set_json + _publish_update
  * continue (skip stale logic)

PAS de webhook envoye — celui d'origine a deja ete livre au moment de
la finalisation. La cause racine du drift Redis est hors scope (separe).

Tests : nouvelle classe TestStaleHandlerCompletionMarker (4 cas) :
  * marker finished -> reconcile + skip webhook
  * marker failed -> reconcile + skip webhook
  * marker missing -> chemin stale existant (regression guard)
  * marker malforme -> fallthrough + log WARNING

Pas de regression sur TestStaleHandlerCounter / TestStaleHandlerKillProcess.

Sibling deploye (BO sous-probleme B) :
  Marketplace/docs/superpowers/specs/2026-04-30-crawler-webhook-idempotency-design.md

Spec : docs/superpowers/specs/2026-04-30-crawler-stale-detector-marker-check-design.md
```

```bash
git commit -m "$(cat <<'EOF'
<bilingual subject + body produced after user picks language; default FR per session>
EOF
)"
git show HEAD --stat   # MUST show exactly 2 files
```

Same `--stat` verification as Task 1 — guard against accidental WIP bundling. If extras appear, `git reset --soft HEAD~1` recovery.

---

## Task 3: Manual verification (docker compose smoke + Ecritel production)

**Goal:** Confirm the fix works end-to-end. Operations task — Claude prepares commands, user executes.

**Files:** None modified.

**Acceptance Criteria:**
- [ ] Docker compose smoke test passes: forced Redis state drift + reconciler tick → marker-driven reconciliation log line + Redis status updated + no webhook
- [ ] Production deploy (Ecritel) confirmed via container update
- [ ] After deploy, large crawl finishes normally; BO `php_errors.log` does NOT receive bogus failure webhook (cross-checked with BO sub-problem B `[webhook-lock] dropped` log absence)
- [ ] If a real stale job occurs (no marker), existing path still fires correctly (regression guard)

**Verify:** Steps 2-5 produce concrete log + Redis evidence per spec §6.

### Steps

- [ ] **Step 1: Pre-deploy local docker compose smoke**

```bash
cd apps-microservices/crawler-service
docker compose up -d crawler-service
docker compose logs -f crawler-service &
LOGS_PID=$!
```

Trigger any short test crawl (use existing test fixture / API endpoint).

Wait for the crawl to finish (status=finished + marker on disk).

Force Redis state drift (manually set status back to `running` with stale heartbeat):

```bash
TEST_ID=<crawl_id_from_test>
docker compose exec redis redis-cli SET "crawl_jobs:${TEST_ID}" "$(docker compose exec redis redis-cli GET "crawl_jobs:${TEST_ID}" | python3 -c 'import sys, json; d=json.loads(sys.stdin.read()); d["status"]="running"; d["last_heartbeat"]="2020-01-01T00:00:00"; print(json.dumps(d))')"
```

Wait ≤300s (next reconciler tick) OR manually call reconcile via the service's admin endpoint if one exists.

Expected logs:
```
Job '<crawl_id>' has completion marker (final_status='finished') but Redis status is 'running'. Reconciling from marker; webhook skipped.
```

Verify Redis status now `finished`:
```bash
docker compose exec redis redis-cli GET "crawl_jobs:${TEST_ID}" | python3 -m json.tool | grep status
```

Expected: `"status": "finished"`.

Verify NO failure webhook in BO logs (separate Marketplace tail):
```bash
# On BO Ecritel side, watch php_errors.log
grep "API Failure Webhook received for crawl ID: ${TEST_ID}" /var/log/php_errors.log
```

Expected: empty (no failure webhook delivered).

```bash
kill $LOGS_PID
docker compose down
```

- [ ] **Step 2: Production deploy**

Standard release path for `crawler-service` container update. Confirm new container is running on all replicas.

- [ ] **Step 3: Production observation — large crawl**

Pick a domain known to produce a large crawl (>5min syncFinalResults at BO side, e.g. >10k files). Trigger crawl. Watch logs:

```bash
docker compose logs -f crawler-service | grep -E "completion marker|stale|Reconciling"
```

Expected: zero `Marking as failed` lines for the just-finished crawl. Either:
- A success-path completion (no reconciler involvement) — happy path
- A `Reconciling from marker; webhook skipped` line — fix activated, would have been a bogus failure webhook before this commit

Cross-check BO side — `php_errors.log` should NOT show `API Failure Webhook received for crawl ID: <id>` for the just-finished crawl. Sub-problem B `[webhook-lock] dropped failure webhook` should also NOT fire (because A side stops emitting).

- [ ] **Step 4: Real stale regression check**

If you can produce a real stale job (e.g. SIGKILL the crawler subprocess on a replica), verify the existing stale-failure path still fires:

```
Job '<id>' (status: running, local) is stale! Last activity: ...s ago. Marking as failed.
Webhook 'failure' for '<id>' sent (attempt 1). Status: 200
```

Expected: failure webhook sent, BO marks domain `statut_dspi=9`. No marker on disk (crawl was killed before completion path).

- [ ] **Step 5: Update primer + memory**

Update `~/.claude/primer.md` Active Project section with deploy outcome. Note any drift root cause findings (sub-problem A doesn't fix the Redis drift — only masks symptom; the drift may still happen and is now invisible).

If a notable surprise emerges (e.g. marker write atomicity issue — torn writes seen), record as a project memory.

---

## Self-Review

**Spec coverage:**
- §1 problem statement → addressed by Task 2 (marker check + reconcile)
- §3 architecture → Task 1 implements helper, Task 2 wires + tests
- §4.1 helper code → Task 1 verbatim
- §4.2 reconciler insertion → Task 2 verbatim
- §4.3 test class → Task 2 (4 cases) + Task 1 (5 unit cases)
- §5 failure modes F1-F10 → covered by Task 1's helper unit tests (F1, F2, F6, F7, F9, F10) + Task 2's integration tests (F3, F4, F5) + F8 (concurrent reconciler) is a runtime property documented but not testable without multi-replica fixture
- §6 verification → Task 3 implements all three layers (pytest local + docker compose smoke + production)
- §7 out of scope → respected: NG1 (drift root cause), NG2 (marker write path), NG3 (telemetry), NG4 (sweep cron), NG5 (fresh-heartbeat marker check)
- §8 open questions — flagged in spec, not blocking
- §9 future work — out of plan scope

**Placeholder scan:** clean. No TBD/TODO. The two `<bilingual subject + body produced after user picks language>` markers in commit blocks are intentional commit-time inputs.

**Type consistency:**
- `_load_completion_marker_or_none(self, storage_path: str) -> Optional[dict]` — used 1× in Task 2 reconciler insertion. Matches.
- `marker["final_status"]` access — assumes dict shape; helper guarantees this if it returns non-None.
- Lock-name constant `CRAWL_LOCK_PREFIX` and counter constant `CRAWL_RUNNING_COUNT_KEY` reused from existing module-level imports — no new constants introduced.

**Open mock-shape questions:**
- Tests reference `_make_manager_with_redis` and `_make_manager` helpers that aren't actual file conventions yet. Implementer MUST read `TestStaleHandlerCounter` first to copy the canonical fixture pattern. Plan flags this in Step 2 of both tasks.

**Branch hygiene:**
- Both commits on `features/poc`. Each commit's `git show HEAD --stat` MUST show exactly 2 files. WIP TS files (`DetectionLangueClient.ts`, `context.ts`, `functions.ts`, `main.ts`) are pre-existing index entries — implementer must verify they are NOT in the commit. Recovery via `git reset --soft HEAD~1` documented in Task 1 Step 8.
