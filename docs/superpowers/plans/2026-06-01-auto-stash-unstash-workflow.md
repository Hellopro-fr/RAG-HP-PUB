# Auto-Stash / Unstash Crawl Workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the currently-manual stash/unstash into the crawl lifecycle automatically — terminal crawls stash to GCS once consumed (or after a safety timeout / under disk pressure), stay invisibly retrievable, and graduate from stash to archive via a GCS-side move.

**Architecture:** Three gated phases. P1 makes any stashed crawl transparently retrievable (`/results` inline-unstash, update-mode restore, `downloaded_at`/`finished_at`/`size_bytes` Redis fields). P2 adds a leader-elected auto-stash sweep inside the existing reconcile loop, flag-gated. P3 adds a GCS-side `stash/→crawls/` move daemon op invoked by `POST /archive` on a stashed crawl. Reuses existing `stash_crawl`/`unstash_crawl`/`_restore_archived_crawl`/reconcile machinery wholesale.

**Tech Stack:** Python 3.x / FastAPI (orchestrator), bash (GCS daemons), PHP (Hellopro BO — 1 file), pytest + unittest.mock, node:test (none here — no Node change).

**Spec:** `docs/superpowers/specs/2026-06-01-auto-stash-unstash-workflow-design.md`

---

## File Structure

| File | Responsibility | Phase |
|---|---|---|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | terminal-field writes, `/results` stashed branch, update-mode unstash, sweep + `_auto_stash_one` + `_is_stash_eligible`, orphan detection, `archive_crawl` move branch | P1,P2,P3 |
| `apps-microservices/crawler-service/app/router/crawler.py` | record `downloaded_at` on `/results` | P1 |
| `apps-microservices/crawler-service/app/core/config.py` | new auto-stash + move settings | P2,P3 |
| `apps-microservices/crawler-service/tests/test_auto_stash_*.py` | new unit tests | P1,P2,P3 |
| `tools/download_daemon.sh` | `.move-request` → `gcloud storage mv` loop | P3 |
| `tools/test_download_daemon_move.sh` | bash test for the move loop | P3 |
| `docker-compose.yml` | env passthrough + move-flow volumes/daemon instance | P2,P3 |
| `Hellopro/BO/.../fonctions_scrapping.php` | bump `/results` call timeout | P1 |
| `apps-microservices/crawler-service/CLAUDE.md`, `tools/CLAUDE.md` | document the feature | P3 |

**Conventions (verified):** Redis writes via `await cache_service.set_json(job_key, job_info)`; reads via `await cache_service.get_json(job_key)`; `job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"`. Tests `from app.core...` (conftest adds paths). `os.uname()` must be stubbed (Windows). Mock `cache_service` via `monkeypatch.setattr(cm_module, "cache_service", mock)`.

---

# PHASE 1 — Transparency Layer

*Ships first. No auto-stash yet. After this, manual stash coexists safely with normal ops.*

### Task 1: Cache `finished_at` + `size_bytes` into job_data at all terminal transitions

**Goal:** Every terminal transition writes `finished_at` (ISO) + `size_bytes` (int) into Redis `job_data` before persisting, so the P2 sweep reads pure Redis.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (4 sites: `_monitor_process` ~1122-1135, `_relaunch_oom_crawl` ~625-668, `force_finish_crawl` ~1253-1270, `_reconcile_locked` stale block ~2891-2951)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_fields.py`

**Acceptance Criteria:**
- [ ] A small helper `_stamp_terminal_fields(job_info)` sets `finished_at` (if absent) + `size_bytes` from `_estimate_archive_required_bytes(job_info["storage_path"])`.
- [ ] All 4 terminal sites call it immediately before their `cache_service.set_json(...)`.
- [ ] `finished_at` is not overwritten if already present (idempotent across reconcile re-runs).
- [ ] Helper never raises (fail-open).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_fields.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_fields.py
"""Unit tests for terminal-transition field stamping (auto-stash P1, Task 1)."""
from unittest.mock import patch
import pytest

from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def manager():
    return CrawlerManager()


def test_stamp_sets_finished_at_and_size(manager, tmp_path):
    job = {"crawl_id": "1", "storage_path": str(tmp_path), "status": "finished"}
    with patch.object(manager, "_estimate_archive_required_bytes", return_value=42):
        manager._stamp_terminal_fields(job)
    assert "finished_at" in job and job["finished_at"]
    assert job["size_bytes"] == 42


def test_stamp_preserves_existing_finished_at(manager, tmp_path):
    job = {"crawl_id": "1", "storage_path": str(tmp_path), "finished_at": "2026-01-01T00:00:00"}
    with patch.object(manager, "_estimate_archive_required_bytes", return_value=10):
        manager._stamp_terminal_fields(job)
    assert job["finished_at"] == "2026-01-01T00:00:00"  # not overwritten
    assert job["size_bytes"] == 10


def test_stamp_never_raises_on_bad_storage(manager):
    job = {"crawl_id": "1", "storage_path": None}
    manager._stamp_terminal_fields(job)  # must not raise
    assert "finished_at" in job
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_fields.py -v`
Expected: FAIL — `AttributeError: 'CrawlerManager' object has no attribute '_stamp_terminal_fields'`.

- [ ] **Step 3: Add the helper** (place near `_estimate_archive_required_bytes`, after line ~1807 in `crawler_manager.py`)

```python
    def _stamp_terminal_fields(self, job_info: dict) -> None:
        """Stamp finished_at (once) + size_bytes onto job_info before a terminal
        set_json. Inputs the auto-stash sweep (P2) reads from pure Redis.
        Fail-open: never raises."""
        try:
            if not job_info.get("finished_at"):
                job_info["finished_at"] = datetime.utcnow().isoformat()
            storage_path = job_info.get("storage_path")
            if storage_path:
                job_info["size_bytes"] = self._estimate_archive_required_bytes(storage_path)
        except Exception as e:
            logger.warning(f"_stamp_terminal_fields failed for "
                           f"'{job_info.get('crawl_id')}': {e}")
```

- [ ] **Step 4: Call it at the 4 terminal sites — immediately before each `set_json`**

In `_monitor_process` (~1134), change:
```python
            if failure_cause is not None:
                job_info["failure_cause"] = failure_cause
            await cache_service.set_json(job_key, job_info)
```
to:
```python
            if failure_cause is not None:
                job_info["failure_cause"] = failure_cause
            self._stamp_terminal_fields(job_info)
            await cache_service.set_json(job_key, job_info)
```

In `_relaunch_oom_crawl` (~666), change:
```python
            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
```
to:
```python
            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
            self._stamp_terminal_fields(job_info)
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
```

In `force_finish_crawl` (~1268), change:
```python
        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
        await cache_service.set_json(job_key, job_info)
```
to:
```python
        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
        self._stamp_terminal_fields(job_info)
        await cache_service.set_json(job_key, job_info)
```

In `_reconcile_locked` stale block (~2949), change:
```python
                        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
                        await cache_service.set_json(all_job_keys[i], job_data)
                        await self._publish_update(crawl_id, final_status)
```
to:
```python
                        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
                        self._stamp_terminal_fields(job_data)
                        await cache_service.set_json(all_job_keys[i], job_data)
                        await self._publish_update(crawl_id, final_status)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_fields.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit** (ask commit language EN/FR/both first)

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_fields.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 2: `/results` stashed branch — transparent inline unstash

**Goal:** `get_results_archive` detects a stashed crawl, unstashes it inline, refreshes `job_info`, then serves normally. Without this a stashed FINISHED crawl falls to `_generate_archive_sync` and produces a corrupt/500 archive.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`get_results_archive` ~1414-1446)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_results.py`

**Acceptance Criteria:**
- [ ] When `job_info.get("stashed_at")` is set, `get_results_archive` calls `await self.unstash_crawl(job_info)`, re-reads `job_info` from Redis, then continues to the existing finished/archived branches.
- [ ] After a successful unstash (`stashed_at` cleared), the crawl is served via the existing `_generate_archive_sync` path.
- [ ] If `unstash_crawl` raises (502/504), the error propagates — no fall-through to a corrupt archive.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_results.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_results.py
"""Unit tests for /results transparent unstash (auto-stash P1, Task 2)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager
from app.schemas.crawler import IncludeInArchive


@pytest.fixture
def manager(monkeypatch):
    mock = MagicMock()
    mock.get_json = AsyncMock()
    mock.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", mock)
    return CrawlerManager(), mock


@pytest.mark.asyncio
async def test_results_unstashes_then_serves(manager):
    mgr, cache = manager
    job = {"crawl_id": "7", "status": "finished", "stashed_at": "2026-01-01T00:00:00",
           "storage_path": "/app/storage/7", "domain": "x.fr"}
    # After unstash, Redis returns job WITHOUT stashed_at:
    cache.get_json.return_value = {**job, "stashed_at": None}
    mgr.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    with patch.object(mgr, "_generate_archive_sync", return_value="/tmp/7.tar.gz"):
        path, is_temp = await mgr.get_results_archive(job, [IncludeInArchive("dataset")])
    mgr.unstash_crawl.assert_awaited_once()
    assert path == "/tmp/7.tar.gz" and is_temp is False


@pytest.mark.asyncio
async def test_results_propagates_unstash_failure(manager):
    mgr, cache = manager
    job = {"crawl_id": "7", "status": "finished", "stashed_at": "t", "storage_path": "/s", "domain": "x"}
    mgr.unstash_crawl = AsyncMock(side_effect=HTTPException(status_code=502, detail="x"))
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, [IncludeInArchive("dataset")])
    assert exc.value.status_code == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_results.py -v`
Expected: FAIL — unstash not called (current code has no stashed branch).

- [ ] **Step 3: Add the stashed branch** — in `get_results_archive`, after the `running` guard and before the `archived` branch (~line 1423):

```python
        if job_info["status"] == "running":
             raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")

        # Auto-stash: a stashed crawl's local data is in GCS. Restore it inline,
        # then fall through to the normal serve path. unstash_crawl clears
        # stashed_at + deletes the GCS stash copy (2-phase). On failure it raises
        # 502/504 — do NOT fall through to a corrupt archive.
        if job_info.get("stashed_at"):
            logger.info(f"/results on stashed crawl '{crawl_id}': unstashing inline.")
            await self.unstash_crawl(job_info)
            job_info = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")

        # For archived crawls: local data is gone, retrieve from GCS via daemon
        if job_info["status"] == "archived":
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_results.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_results.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 3: Record `downloaded_at` on a successful `/results` serve

**Goal:** The `/results` endpoint persists `downloaded_at` (stream-start) to Redis so the P2 sweep's grace window can start. "Consumed" = download initiated (only observable point).

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/crawler.py` (`download_crawl_results` ~299-341)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_downloaded_at.py`

**Acceptance Criteria:**
- [ ] After `get_results_archive` returns and the archive file exists, but before returning the response, the endpoint persists `job_info["downloaded_at"] = datetime.utcnow().isoformat()` via `cache_service.set_json`.
- [ ] Persist failure does not break the download (wrapped, logged).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_downloaded_at.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test** (tests the helper, to keep it endpoint-framework-free)

```python
# apps-microservices/crawler-service/tests/test_auto_stash_downloaded_at.py
"""Unit tests for downloaded_at recording (auto-stash P1, Task 3)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import app.router.crawler as crawler_router


@pytest.mark.asyncio
async def test_record_downloaded_at_persists(monkeypatch):
    cache = MagicMock()
    cache.set_json = AsyncMock()
    monkeypatch.setattr(crawler_router, "cache_service", cache)
    job = {"crawl_id": "9"}
    await crawler_router._record_downloaded_at(job)
    cache.set_json.assert_awaited_once()
    assert "downloaded_at" in job


@pytest.mark.asyncio
async def test_record_downloaded_at_swallows_errors(monkeypatch):
    cache = MagicMock()
    cache.set_json = AsyncMock(side_effect=RuntimeError("redis down"))
    monkeypatch.setattr(crawler_router, "cache_service", cache)
    await crawler_router._record_downloaded_at({"crawl_id": "9"})  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_downloaded_at.py -v`
Expected: FAIL — `module 'app.router.crawler' has no attribute '_record_downloaded_at'`.

- [ ] **Step 3: Add the helper + call it.** Add near the top of `crawler.py` (after imports), the helper:

```python
async def _record_downloaded_at(job_info: dict) -> None:
    """Persist downloaded_at (stream-start) so the auto-stash grace window can
    start. Fail-open: a Redis hiccup must never break a download."""
    try:
        crawl_id = job_info["crawl_id"]
        job_info["downloaded_at"] = datetime.utcnow().isoformat()
        await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
    except Exception as e:
        logger.warning(f"Failed to record downloaded_at for "
                       f"'{job_info.get('crawl_id')}': {e}")
```

In `download_crawl_results`, after the `os.path.exists(archive_path)` check passes and before the `if is_temporary:` block (~line 324):

```python
        # Record the consume signal (stream-start) for the auto-stash sweep.
        await _record_downloaded_at(job_info)

        if is_temporary:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_downloaded_at.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/router/crawler.py apps-microservices/crawler-service/tests/test_auto_stash_downloaded_at.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 4: Update-mode restore handles a stashed previous crawl

**Goal:** When an update-mode crawl references a `previous_crawl_id` that is stashed, restore it via `unstash_crawl` (which knows the `stash/` prefix + 2-phase delete) instead of `_restore_archived_crawl` (which only knows `crawls/`). This is the real "start → unstash, continue" path (same-ID restart does not exist).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`start_crawl` update-mode block ~517-562)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_update_restore.py`

**Acceptance Criteria:**
- [ ] In the update-mode block, when `prev_job_info.get("stashed_at")` is set and local data is absent, the code calls `await self.unstash_crawl(prev_job_info)` (which restores + clears stashed_at), then proceeds.
- [ ] On `unstash_crawl` failure, `_rollback_claim(decrement_counter=True)` is called and the error becomes a 503 (mirrors the archived branch).
- [ ] The existing `archived`-restore branch is unchanged.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_update_restore.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_update_restore.py
"""Unit tests for update-mode stashed-previous-crawl restore (auto-stash P1, Task 4)."""
from unittest.mock import AsyncMock
import pytest

from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_restore_previous_routes_stashed_to_unstash():
    mgr = CrawlerManager()
    mgr.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    mgr._restore_archived_crawl = AsyncMock()
    prev = {"crawl_id": "100", "status": "finished", "stashed_at": "2026-01-01T00:00:00"}
    await mgr._restore_previous_crawl(prev, has_local_data=False)
    mgr.unstash_crawl.assert_awaited_once_with(prev)
    mgr._restore_archived_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_restore_previous_routes_archived_to_archive_restore():
    mgr = CrawlerManager()
    mgr.unstash_crawl = AsyncMock()
    mgr._restore_archived_crawl = AsyncMock()
    prev = {"crawl_id": "101", "status": "archived"}
    await mgr._restore_previous_crawl(prev, has_local_data=False)
    mgr._restore_archived_crawl.assert_awaited_once_with("101")
    mgr.unstash_crawl.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_update_restore.py -v`
Expected: FAIL — `'CrawlerManager' object has no attribute '_restore_previous_crawl'`.

- [ ] **Step 3: Extract a `_restore_previous_crawl` helper + wire it.** Add the helper (near `_restore_archived_crawl`, ~2086):

```python
    async def _restore_previous_crawl(self, prev_job_info: dict, has_local_data: bool) -> None:
        """For update mode: ensure the previous crawl's data is on local disk.
        Routes a stashed previous crawl through unstash_crawl (stash/ prefix +
        2-phase delete); an archived one through _restore_archived_crawl
        (crawls/ prefix). No-op if local data already present."""
        if has_local_data:
            return
        previous_crawl_id = prev_job_info["crawl_id"]
        if prev_job_info.get("stashed_at"):
            logger.info(f"Previous crawl '{previous_crawl_id}' is stashed. "
                        f"Unstashing from GCS before update crawl.")
            await self.unstash_crawl(prev_job_info)
        elif prev_job_info.get("status") == "archived":
            logger.info(f"Previous crawl '{previous_crawl_id}' is archived. "
                        f"Restoring from GCS before update crawl.")
            await self._restore_archived_crawl(previous_crawl_id)
```

Then replace the `if prev_status == "archived" and not has_local_data:` … `elif not has_local_data:` block (~543-562) with:

```python
            stashed = bool(prev_job_info.get("stashed_at")) if prev_job_info else False
            if (prev_status == "archived" or stashed) and not has_local_data:
                try:
                    await self._restore_previous_crawl(prev_job_info, has_local_data)
                except HTTPException:
                    await _rollback_claim(decrement_counter=True)
                    raise
                except Exception as e:
                    await _rollback_claim(decrement_counter=True)
                    logger.error(f"Failed to restore previous crawl '{previous_crawl_id}': {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Failed to restore previous crawl '{previous_crawl_id}' from GCS: {str(e)}"
                    )
            elif not has_local_data:
                await _rollback_claim(decrement_counter=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Previous crawl '{previous_crawl_id}' has no dataset files on disk "
                           f"and is not archived or stashed. Cannot proceed with update mode."
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_update_restore.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_update_restore.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 5: Bump BO `/results` call timeout (Hellopro)

**Goal:** Give the two BO `/results` callers a longer timeout so a big-crawl inline unstash (≤300s + archive gen) does not trip the 300s default. `sendRequest` currently passes no timeout.

**Files:**
- Modify: `Hellopro/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` (`sendRequest` ~109-115, `getTemporaryResultsPath` ~140, `syncFinalResults` ~196)

**Acceptance Criteria:**
- [ ] `sendRequest` accepts an optional `$timeout = 300` param and forwards it to `call_api_hellopro` (6th positional arg).
- [ ] The two `/results` calls pass `$timeout = 900`.
- [ ] No other caller's behavior changes (default stays 300).

**Verify:** Manual — `grep -n "sendRequest" fonctions_scrapping.php` shows the two `/results` calls passing `900`; existing non-`/results` calls unchanged. (No PHPUnit harness in this BO module; functional check: trigger a `/results` on a stashed crawl, confirm no cURL timeout before unstash completes.)

**Steps:**

- [ ] **Step 1: Add `$timeout` to `sendRequest`** (~109-115):

```php
    private function sendRequest($method, $endpoint, $payload = [], $isDownload = false, $timeout = 300) {
        $responseHeaders = [];
        return call_api_hellopro($method, $this->service, $endpoint, $payload, $isDownload, $timeout, $responseHeaders);
    }
```

- [ ] **Step 2: Pass 900 in `getTemporaryResultsPath`** (~140), change:

```php
        $archiveContent = $this->sendRequest('GET', "/results/{$crawl_id}", ['include' => $include], true);
```
to:
```php
        // 900s: a stashed crawl is unstashed inline server-side (≤300s + archive gen) before bytes flow.
        $archiveContent = $this->sendRequest('GET', "/results/{$crawl_id}", ['include' => $include], true, 900);
```

- [ ] **Step 3: Pass 900 in `syncFinalResults`** (~196), change:

```php
            $archiveContent = $this->sendRequest('GET', "/results/{$crawl_id}", ['includeAll' => $includeAll], true);
```
to:
```php
            // 900s: server may unstash inline before serving (auto-stash workflow).
            $archiveContent = $this->sendRequest('GET', "/results/{$crawl_id}", ['includeAll' => $includeAll], true, 900);
```

- [ ] **Step 4: Verify**

Run: `grep -n "sendRequest(" "BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php"`
Expected: the two `/results` lines end with `, true, 900);`; other `sendRequest(` calls unchanged.

- [ ] **Step 5: Commit** (Hellopro repo)

```bash
git -C "C:/Users/randr/Documents/Workspaces/Hellopro" add BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php
git -C "C:/Users/randr/Documents/Workspaces/Hellopro" commit -F .git/COMMIT_EDITMSG
```

---

# PHASE 2 — Auto-Stash Sweep

*Flag-gated (`AUTO_STASH_ENABLED=false`). Enable only after P1 is proven in prod.*

### Task 6: Auto-stash config settings + docker-compose passthrough

**Goal:** Add the tunables the sweep reads.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py` (after line ~78, before `model_config`)
- Modify: `docker-compose.yml` (crawler-service `environment:` block ~1336-1351)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_config.py`

**Acceptance Criteria:**
- [ ] `config.py` gains `AUTO_STASH_ENABLED: bool = False`, `STASH_GRACE_SECONDS: int = 3600`, `STASH_SAFETY_TIMEOUT_SECONDS: int = 172800`, `STASH_DISK_HIGH_WATER_PCT: int = 85`, `STASH_MAX_PER_SWEEP: int = 5`.
- [ ] `docker-compose.yml` passes each through with an env default (`${AUTO_STASH_ENABLED:-false}` etc.).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_config.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_config.py
"""Auto-stash settings defaults (P2, Task 6)."""
from app.core.config import settings


def test_auto_stash_defaults():
    assert settings.AUTO_STASH_ENABLED is False
    assert settings.STASH_GRACE_SECONDS == 3600
    assert settings.STASH_SAFETY_TIMEOUT_SECONDS == 172800
    assert settings.STASH_DISK_HIGH_WATER_PCT == 85
    assert settings.STASH_MAX_PER_SWEEP == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'AUTO_STASH_ENABLED'`.

- [ ] **Step 3: Add settings** in `config.py` before `model_config` (~line 78):

```python
    # --- Auto-stash workflow (spec 2026-06-01) ---
    # Master gate for the auto-stash reconcile sweep (P2). Off by default.
    AUTO_STASH_ENABLED: bool = False
    # After a /results download, wait this long before stashing (happy path).
    STASH_GRACE_SECONDS: int = 3600
    # Stash a never-downloaded terminal crawl after this long (also the
    # investigation window for failed crawls).
    STASH_SAFETY_TIMEOUT_SECONDS: int = 172800
    # Disk-pressure override: at/above this used-% the sweep stashes the
    # largest terminal crawls early, regardless of grace.
    STASH_DISK_HIGH_WATER_PCT: int = 85
    # Cap on crawls stashed per sweep tick (bounds upload-daemon load).
    STASH_MAX_PER_SWEEP: int = 5
```

- [ ] **Step 4: Add docker-compose passthrough** in the `crawler-service` `environment:` block (after `SERVICE_NAME=crawler-service`, ~line 1349):

```yaml
      - AUTO_STASH_ENABLED=${AUTO_STASH_ENABLED:-false}
      - STASH_GRACE_SECONDS=${STASH_GRACE_SECONDS:-3600}
      - STASH_SAFETY_TIMEOUT_SECONDS=${STASH_SAFETY_TIMEOUT_SECONDS:-172800}
      - STASH_DISK_HIGH_WATER_PCT=${STASH_DISK_HIGH_WATER_PCT:-85}
      - STASH_MAX_PER_SWEEP=${STASH_MAX_PER_SWEEP:-5}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_config.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/config.py docker-compose.yml apps-microservices/crawler-service/tests/test_auto_stash_config.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 7: Eligibility predicate `_is_stash_eligible`

**Goal:** A pure, side-effect-free method deciding whether a terminal crawl is grace/timeout-eligible to stash, given `now`. (Disk-pressure selection is handled separately in Task 8.)

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (add method near reconcile)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_eligibility.py`

**Acceptance Criteria:**
- [ ] `_is_stash_eligible(job_data, now_dt) -> tuple[bool, str|None]` returns `(True, "grace")` if `downloaded_at` + `STASH_GRACE_SECONDS` elapsed; `(True, "timeout")` if `finished_at` + `STASH_SAFETY_TIMEOUT_SECONDS` elapsed; else `(False, None)`.
- [ ] Returns `(False, None)` for non-terminal status, `archived` status, or `stashed_at` already set.
- [ ] Missing/garbage `downloaded_at`/`finished_at` never raise (treated as absent).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_eligibility.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_eligibility.py
"""Eligibility predicate matrix (auto-stash P2, Task 7)."""
from datetime import datetime, timedelta
import pytest
from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


@pytest.fixture
def mgr():
    return CrawlerManager()


def _now():
    return datetime(2026, 6, 1, 12, 0, 0)


def test_grace_elapsed_eligible(mgr):
    dl = (_now() - timedelta(seconds=settings.STASH_GRACE_SECONDS + 1)).isoformat()
    job = {"status": "finished", "downloaded_at": dl}
    assert mgr._is_stash_eligible(job, _now()) == (True, "grace")


def test_grace_not_elapsed_not_eligible(mgr):
    dl = (_now() - timedelta(seconds=10)).isoformat()
    job = {"status": "finished", "downloaded_at": dl}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_safety_timeout_eligible_when_never_downloaded(mgr):
    fin = (_now() - timedelta(seconds=settings.STASH_SAFETY_TIMEOUT_SECONDS + 1)).isoformat()
    job = {"status": "failed", "finished_at": fin}
    assert mgr._is_stash_eligible(job, _now()) == (True, "timeout")


@pytest.mark.parametrize("status", ["running", "restarting_oom", "stopping", "archived"])
def test_non_terminal_or_archived_not_eligible(mgr, status):
    job = {"status": status, "finished_at": "2000-01-01T00:00:00"}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_already_stashed_not_eligible(mgr):
    job = {"status": "finished", "stashed_at": "t", "finished_at": "2000-01-01T00:00:00"}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_garbage_timestamps_do_not_raise(mgr):
    job = {"status": "finished", "downloaded_at": "not-a-date", "finished_at": "nope"}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_eligibility.py -v`
Expected: FAIL — `'CrawlerManager' object has no attribute '_is_stash_eligible'`.

- [ ] **Step 3: Add the method** (near `_reconcile_locked`):

```python
    def _is_stash_eligible(self, job_data: dict, now_dt: "datetime") -> Tuple[bool, Optional[str]]:
        """Grace/timeout eligibility for the auto-stash sweep. Pure, fail-open.
        Disk-pressure selection is handled by the caller (sweep)."""
        if job_data.get("status") not in ("finished", "failed", "stopped"):
            return (False, None)
        if job_data.get("stashed_at"):
            return (False, None)

        def _age(field):
            raw = job_data.get(field)
            if not raw:
                return None
            try:
                return (now_dt - datetime.fromisoformat(raw)).total_seconds()
            except (ValueError, TypeError):
                return None

        dl_age = _age("downloaded_at")
        if dl_age is not None and dl_age >= settings.STASH_GRACE_SECONDS:
            return (True, "grace")
        fin_age = _age("finished_at")
        if fin_age is not None and fin_age >= settings.STASH_SAFETY_TIMEOUT_SECONDS:
            return (True, "timeout")
        return (False, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_eligibility.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_eligibility.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 8: Wire the sweep into `_reconcile_locked`

**Goal:** During the reconcile scan, collect terminal candidates; after the loop, select eligible (grace/timeout) + disk-pressure top-N, cap at `STASH_MAX_PER_SWEEP`, and stash each via a background `_auto_stash_one` (so a long tar never blocks the leader lock). Gated by `AUTO_STASH_ENABLED`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`_reconcile_locked` loop + tail; add `_auto_stash_one`, `_disk_used_pct`)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_sweep.py`

**Acceptance Criteria:**
- [ ] Sweep runs only when `settings.AUTO_STASH_ENABLED`.
- [ ] Candidates = terminal, `stashed_at` unset, status != `archived`. Selected = grace/timeout-eligible ∪ (if disk ≥ HIGH_WATER) largest-by-`size_bytes`; capped at `STASH_MAX_PER_SWEEP`.
- [ ] Each selection is dispatched via `asyncio.create_task(self._auto_stash_one(job_data))` — the leader section does not await tar.
- [ ] `_auto_stash_one` calls `stash_crawl`, swallows 409 (debug log), logs other errors; emits `AUTO_STASH crawl_id=… reason=…`.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_sweep.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_sweep.py
"""Auto-stash sweep selection + dispatch (P2, Task 8)."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import pytest

from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


@pytest.fixture
def mgr():
    return CrawlerManager()


def _old_download():
    return (datetime.utcnow() - timedelta(seconds=settings.STASH_GRACE_SECONDS + 10)).isoformat()


@pytest.mark.asyncio
async def test_auto_stash_one_swallows_409(mgr):
    from fastapi import HTTPException
    mgr.stash_crawl = AsyncMock(side_effect=HTTPException(status_code=409, detail={"error_code": "ALREADY_STASHED"}))
    await mgr._auto_stash_one({"crawl_id": "1", "status": "finished"}, "grace")  # must not raise


@pytest.mark.asyncio
async def test_select_respects_cap_and_eligibility(mgr):
    jobs = [{"crawl_id": str(i), "status": "finished", "downloaded_at": _old_download(),
             "size_bytes": i} for i in range(10)]
    with patch.object(mgr, "_disk_used_pct", return_value=0):  # no pressure
        selected = mgr._select_stash_candidates(jobs, datetime.utcnow())
    assert len(selected) == settings.STASH_MAX_PER_SWEEP
    assert all(reason == "grace" for _job, reason in selected)


@pytest.mark.asyncio
async def test_disk_pressure_selects_largest(mgr):
    # None are grace/timeout-eligible (fresh), but disk pressure forces top-N by size.
    jobs = [{"crawl_id": str(i), "status": "finished", "size_bytes": i,
             "downloaded_at": datetime.utcnow().isoformat()} for i in range(10)]
    with patch.object(mgr, "_disk_used_pct", return_value=99):
        selected = mgr._select_stash_candidates(jobs, datetime.utcnow())
    ids = [j["crawl_id"] for j, _r in selected]
    assert ids == ["9", "8", "7", "6", "5"]  # largest first, capped at 5
    assert all(reason == "disk_pressure" for _j, reason in selected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_sweep.py -v`
Expected: FAIL — missing `_auto_stash_one` / `_select_stash_candidates` / `_disk_used_pct`.

- [ ] **Step 3: Add the helpers** (near `_reconcile_locked`):

```python
    def _disk_used_pct(self, path: str = None) -> float:
        """Used-% of the crawl storage filesystem. Fail-open → 0.0 (no pressure)."""
        try:
            target = path or settings.CRAWLER_STORAGE_PATH
            usage = shutil.disk_usage(target)
            return (usage.used / usage.total) * 100 if usage.total else 0.0
        except Exception as e:
            logger.warning(f"_disk_used_pct failed: {e}")
            return 0.0

    def _select_stash_candidates(self, jobs: List[dict], now_dt: "datetime") -> List[Tuple[dict, str]]:
        """From terminal non-stashed non-archived jobs, pick (job, reason) to stash
        this tick: grace/timeout-eligible, plus largest-by-size under disk pressure.
        Capped at STASH_MAX_PER_SWEEP."""
        eligible = []
        terminal = []
        for j in jobs:
            ok, reason = self._is_stash_eligible(j, now_dt)
            if ok:
                eligible.append((j, reason))
            elif j.get("status") in ("finished", "failed", "stopped") and not j.get("stashed_at"):
                terminal.append(j)

        selected = eligible[: settings.STASH_MAX_PER_SWEEP]

        if len(selected) < settings.STASH_MAX_PER_SWEEP and \
                self._disk_used_pct() >= settings.STASH_DISK_HIGH_WATER_PCT:
            already = {id(j) for j, _ in selected}
            extra = sorted(terminal, key=lambda j: j.get("size_bytes", 0), reverse=True)
            for j in extra:
                if len(selected) >= settings.STASH_MAX_PER_SWEEP:
                    break
                if id(j) not in already:
                    selected.append((j, "disk_pressure"))
        return selected

    async def _auto_stash_one(self, job_data: dict, reason: str) -> None:
        """Stash one crawl on behalf of the sweep. Swallows 409 (already
        stashed / in progress); logs other failures. Never raises."""
        crawl_id = job_data.get("crawl_id")
        try:
            logger.info(f"AUTO_STASH crawl_id={crawl_id} reason={reason}")
            await self.stash_crawl(job_data)
        except HTTPException as e:
            if e.status_code == 409:
                logger.debug(f"AUTO_STASH skip crawl_id={crawl_id}: {e.detail}")
            else:
                logger.warning(f"AUTO_STASH failed crawl_id={crawl_id}: {e.detail}")
        except Exception as e:
            logger.warning(f"AUTO_STASH error crawl_id={crawl_id}: {e}")
```

- [ ] **Step 4: Wire the sweep into `_reconcile_locked`.** The loop already parses every `job_data`. Accumulate terminal candidates, then dispatch after the loop. After `all_jobs_raw = await pipe.execute()` and before the `for i, job_raw ...` loop, add:

```python
        auto_stash_pool = []  # collected during scan; dispatched after the loop
```

Inside the loop, after `status = job_data.get("status")` (and before the `if status in ("running", ...)` block), add:

```python
                if settings.AUTO_STASH_ENABLED and \
                        status in ("finished", "failed", "stopped") and not job_data.get("stashed_at"):
                    auto_stash_pool.append(job_data)
```

After the `for` loop ends (and any existing post-loop counter reconciliation), add:

```python
        # --- Auto-stash sweep (spec 2026-06-01). Dispatch as background tasks so a
        # multi-GB tar never holds the reconcile leader lock. Each stash_crawl takes
        # its own stash_lock (idempotent; 409 = no-op). ---
        if settings.AUTO_STASH_ENABLED and auto_stash_pool:
            now_dt = datetime.utcnow()
            for job_data, reason in self._select_stash_candidates(auto_stash_pool, now_dt):
                asyncio.create_task(self._auto_stash_one(job_data, reason))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_sweep.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_sweep.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 9: Stash upload-orphan detection in the sweep

**Goal:** Detect crawls marked `stashed_at` whose tar was dead-lettered by the upload daemon (GCS upload failed), log `STASH_UPLOAD_ORPHAN`, and re-queue the tar back to the stash watch dir.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (sweep tail; add `_requeue_stash_orphan`)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_orphan.py`

**Acceptance Criteria:**
- [ ] For each scanned job with `stashed_at` set, if `{STASH_SHARED_PATH}/dead_letter/{id}.tar.gz` exists, log `STASH_UPLOAD_ORPHAN crawl_id=…` and move it back to `{STASH_SHARED_PATH}/{id}.tar.gz`.
- [ ] Runs only when `AUTO_STASH_ENABLED`. Fail-open (a move error is logged, not raised).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_orphan.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_orphan.py
"""Stash upload-orphan re-queue (auto-stash P2, Task 9)."""
import os
from unittest.mock import patch
import pytest
from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_requeue_moves_deadletter_back(tmp_path):
    mgr = CrawlerManager()
    stash_dir = tmp_path
    dead = stash_dir / "dead_letter"
    dead.mkdir()
    (dead / "55.tar.gz").write_text("data")
    with patch("app.core.crawler_manager.settings") as s:
        s.STASH_SHARED_PATH = str(stash_dir)
        moved = mgr._requeue_stash_orphan("55")
    assert moved is True
    assert (stash_dir / "55.tar.gz").exists()
    assert not (dead / "55.tar.gz").exists()


@pytest.mark.asyncio
async def test_requeue_noop_when_no_deadletter(tmp_path):
    mgr = CrawlerManager()
    with patch("app.core.crawler_manager.settings") as s:
        s.STASH_SHARED_PATH = str(tmp_path)
        assert mgr._requeue_stash_orphan("99") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_orphan.py -v`
Expected: FAIL — `'CrawlerManager' object has no attribute '_requeue_stash_orphan'`.

- [ ] **Step 3: Add the helper + wire it.** Add the method:

```python
    def _requeue_stash_orphan(self, crawl_id: str) -> bool:
        """If a stashed crawl's tar was dead-lettered (upload failed), move it
        back to the stash watch dir so the upload daemon retries. Returns True
        if a re-queue happened. Fail-open."""
        try:
            dead = os.path.join(settings.STASH_SHARED_PATH, "dead_letter", f"{crawl_id}.tar.gz")
            if not os.path.exists(dead):
                return False
            target = os.path.join(settings.STASH_SHARED_PATH, f"{crawl_id}.tar.gz")
            logger.warning(f"STASH_UPLOAD_ORPHAN crawl_id={crawl_id} "
                           f"reason=dead_letter_found action=requeue path={dead}")
            os.rename(dead, target)
            return True
        except Exception as e:
            logger.warning(f"STASH_UPLOAD_ORPHAN requeue failed crawl_id={crawl_id}: {e}")
            return False
```

In `_reconcile_locked`, inside the per-job loop where `status`/`stashed_at` are available, add (after the `auto_stash_pool.append` block from Task 8):

```python
                if settings.AUTO_STASH_ENABLED and job_data.get("stashed_at"):
                    self._requeue_stash_orphan(crawl_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_orphan.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_orphan.py
git commit -F .git/COMMIT_EDITMSG
```

---

# PHASE 3 — Stash→Archive Move

*GCS-side, last. Logically after Phase 2.*

### Task 10: Move-flow config paths + docker-compose volumes/daemon

**Goal:** Add the marker paths + GCS prefixes the move op uses, and the move-flow daemon instance.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py`
- Modify: `docker-compose.yml` (crawler-service volumes ~1325-1332)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_move_config.py`

**Acceptance Criteria:**
- [ ] `config.py` gains `MOVE_REQUESTS_PATH: str = "/app/gcs-move-requests"`, `MOVE_RESULTS_PATH: str = "/app/gcs-move-results"`, `MOVE_GCS_SOURCE_PREFIX: str = "stash"`, `MOVE_GCS_TARGET_PREFIX: str = "crawls"`, `MOVE_TIMEOUT_SECONDS: int = 120`.
- [ ] `docker-compose.yml` mounts `crawler_move_requests:/app/gcs-move-requests` and `crawler_move_results:/app/gcs-move-results`.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_move_config.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_move_config.py
"""Move-flow settings defaults (P3, Task 10)."""
from app.core.config import settings


def test_move_defaults():
    assert settings.MOVE_REQUESTS_PATH == "/app/gcs-move-requests"
    assert settings.MOVE_RESULTS_PATH == "/app/gcs-move-results"
    assert settings.MOVE_GCS_SOURCE_PREFIX == "stash"
    assert settings.MOVE_GCS_TARGET_PREFIX == "crawls"
    assert settings.MOVE_TIMEOUT_SECONDS == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_move_config.py -v`
Expected: FAIL — missing attributes.

- [ ] **Step 3: Add settings** in `config.py` (after the stash-flow paths, ~line 41):

```python
    # Stash->archive move flow (spec 2026-06-01 P3). Service writes .move-request;
    # the move-flow daemon does `gcloud storage mv stash/{id} crawls/{id}`.
    MOVE_REQUESTS_PATH: str = "/app/gcs-move-requests"
    MOVE_RESULTS_PATH: str = "/app/gcs-move-results"
    MOVE_GCS_SOURCE_PREFIX: str = "stash"
    MOVE_GCS_TARGET_PREFIX: str = "crawls"
    MOVE_TIMEOUT_SECONDS: int = 120
```

- [ ] **Step 4: Add docker-compose volumes** in the crawler-service `volumes:` block (after the stash-flow mounts, ~line 1332):

```yaml
      # Stash->archive move flow shared dirs
      - ./apps-microservices/crawler-service/crawler_move_requests:/app/gcs-move-requests
      - ./apps-microservices/crawler-service/crawler_move_results:/app/gcs-move-results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_move_config.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/config.py docker-compose.yml apps-microservices/crawler-service/tests/test_auto_stash_move_config.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 11: `download_daemon.sh` move loop

**Goal:** Add an `ENABLE_MOVE`-gated third loop that scans `MOVE_REQUESTS_PATH` for `{id}.move-request` and runs `gcloud storage mv` from source→target prefix, writing `{id}.move-done` / `{id}.move-error`.

**Files:**
- Modify: `tools/download_daemon.sh` (add env parsing + loop block before final `sleep`)
- Test: `tools/test_download_daemon_move.sh`

**Acceptance Criteria:**
- [ ] New env vars `MOVE_REQUESTS_PATH`, `MOVE_RESULTS_PATH`, `MOVE_SOURCE_PREFIX` (default `stash`), `MOVE_TARGET_PREFIX` (default `crawls`), `ENABLE_MOVE` (default `false`).
- [ ] When `ENABLE_MOVE=true`, each `{id}.move-request` triggers `gcloud storage mv gs://$BUCKET/$MOVE_SOURCE_PREFIX/{id}.tar.gz gs://$BUCKET/$MOVE_TARGET_PREFIX/{id}.tar.gz`; success → write `{id}.move-done` + rm request; failure → write `{id}.move-error` + rm request.
- [ ] Idempotent: a `move-request` for an already-moved object (source gone, target present) is treated as success (`move-done`).

**Verify:** `bash tools/test_download_daemon_move.sh` → prints `OK`.

**Steps:**

- [ ] **Step 1: Write the failing test** (mocks `gcloud` via a PATH shim)

```bash
# tools/test_download_daemon_move.sh
#!/bin/bash
# Test the move loop of download_daemon.sh with a mocked gcloud.
set -euo pipefail
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Mock gcloud: record the mv, simulate success; for id "already" simulate source-missing.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/gcloud" <<'EOF'
#!/bin/bash
# args: storage mv SRC DST   OR   storage ls SRC
if [ "$2" = "mv" ]; then
  case "$3" in
    *already.tar.gz) exit 1 ;;   # source already gone
    *) echo "moved $3 -> $4"; exit 0 ;;
  esac
fi
if [ "$2" = "ls" ]; then
  case "$3" in
    *crawls/already.tar.gz) exit 0 ;;  # target present -> already moved
    *) exit 1 ;;
  esac
fi
exit 0
EOF
chmod +x "$TMP/bin/gcloud"
export PATH="$TMP/bin:$PATH"

export GCS_BUCKET_NAME="test-bucket"
export MOVE_REQUESTS_PATH="$TMP/req"
export MOVE_RESULTS_PATH="$TMP/res"
export ENABLE_MOVE="true"
mkdir -p "$MOVE_REQUESTS_PATH" "$MOVE_RESULTS_PATH"

# Source the daemon's move function only (extracted in Step 3) to avoid the infinite loop.
source "$(dirname "$0")/download_daemon.sh" --source-functions-only

# Happy path
echo "1" > "$MOVE_REQUESTS_PATH/42.move-request"
process_move_requests
[ -f "$MOVE_RESULTS_PATH/42.move-done" ] || { echo "FAIL: 42.move-done missing"; exit 1; }
[ ! -f "$MOVE_REQUESTS_PATH/42.move-request" ] || { echo "FAIL: request not consumed"; exit 1; }

# Idempotent already-moved path
echo "1" > "$MOVE_REQUESTS_PATH/already.move-request"
process_move_requests
[ -f "$MOVE_RESULTS_PATH/already.move-done" ] || { echo "FAIL: already.move-done missing (idempotent)"; exit 1; }

echo "OK"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tools/test_download_daemon_move.sh`
Expected: FAIL — `process_move_requests: command not found` (function not yet defined / no `--source-functions-only` guard).

- [ ] **Step 3: Refactor the move logic into a sourceable function + add the guarded loop.** In `download_daemon.sh`, add near the top after the env block:

```bash
MOVE_REQUESTS_PATH="${MOVE_REQUESTS_PATH:-$(dirname "$0")/../apps-microservices/crawler-service/crawler_move_requests}"
MOVE_RESULTS_PATH="${MOVE_RESULTS_PATH:-$(dirname "$0")/../apps-microservices/crawler-service/crawler_move_results}"
MOVE_SOURCE_PREFIX="${MOVE_SOURCE_PREFIX:-stash}"
MOVE_TARGET_PREFIX="${MOVE_TARGET_PREFIX:-crawls}"
ENABLE_MOVE="${ENABLE_MOVE:-false}"
mkdir -p "$MOVE_REQUESTS_PATH" "$MOVE_RESULTS_PATH" 2>/dev/null || true

process_move_requests() {
    # Scan MOVE_REQUESTS_PATH for {id}.move-request; gcloud storage mv stash/->crawls/.
    find "$MOVE_REQUESTS_PATH" -maxdepth 1 -name "*.move-request" -print0 | while IFS= read -r -d '' move_file; do
        crawl_id=$(basename "$move_file" .move-request)
        src="gs://$GCS_BUCKET_NAME/$MOVE_SOURCE_PREFIX/$crawl_id.tar.gz"
        dst="gs://$GCS_BUCKET_NAME/$MOVE_TARGET_PREFIX/$crawl_id.tar.gz"
        done_marker="$MOVE_RESULTS_PATH/$crawl_id.move-done"
        error_marker="$MOVE_RESULTS_PATH/$crawl_id.move-error"
        echo "[$(date)] Move request: $crawl_id ($src -> $dst)"
        if gcloud storage mv "$src" "$dst"; then
            touch "$done_marker"; rm -f "$move_file"
        elif gcloud storage ls "$dst" >/dev/null 2>&1; then
            # Idempotent: source already gone + target present = already moved.
            echo "Already moved (source absent, target present): $crawl_id"
            touch "$done_marker"; rm -f "$move_file"
        else
            echo "ERROR: move failed for $crawl_id" > "$error_marker"; rm -f "$move_file"
        fi
    done
}

# Test hook: source the script with --source-functions-only to import functions
# without entering the daemon loop.
if [ "${1:-}" = "--source-functions-only" ]; then
    return 0 2>/dev/null || exit 0
fi
```

Then in the main `while true; do ... done` loop, before the final `sleep $CHECK_INTERVAL`, add:

```bash
    if [ "$ENABLE_MOVE" = "true" ]; then
        process_move_requests
    fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tools/test_download_daemon_move.sh`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/download_daemon.sh tools/test_download_daemon_move.sh
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 12: `archive_crawl` stashed branch — drive the move

**Goal:** When `POST /archive` hits a stashed crawl, write `.move-request`, poll `.move-done`/`.move-error`, then `_mark_as_archived` + clear `stashed_at`, returning `archive_status="pending_upload"` (known BO string). Idempotent.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`archive_crawl` top, ~1865; add `_move_stash_to_archive`)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_archive_move.py`

**Acceptance Criteria:**
- [ ] At the top of `archive_crawl`, before the existing `archived`/`finished` guards: if `job_info.get("stashed_at")`, call `await self._move_stash_to_archive(job_info)` and return `{"crawl_id", "archive_status": "pending_upload", "archive_size_bytes": None}`.
- [ ] `_move_stash_to_archive` writes `.move-request`, polls `.move-done` (success) / `.move-error` (502) up to `MOVE_TIMEOUT_SECONDS`, on success calls `_mark_as_archived(crawl_id)` + clears `stashed_at` in Redis, cleans markers.
- [ ] On `.move-error` → raise 502; on timeout → raise 504.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archive_move.py -v` → pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_archive_move.py
"""archive_crawl stashed-branch move (auto-stash P3, Task 12)."""
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def mgr(monkeypatch, tmp_path):
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value={"crawl_id": "70", "stashed_at": "t"})
    cache.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", cache)
    m = CrawlerManager()
    m._mark_as_archived = AsyncMock()
    return m, cache, tmp_path


@pytest.mark.asyncio
async def test_archive_stashed_routes_to_move(mgr):
    m, cache, _ = mgr
    m._move_stash_to_archive = AsyncMock()
    job = {"crawl_id": "70", "status": "finished", "stashed_at": "2026-01-01T00:00:00"}
    result = await m.archive_crawl(job)
    m._move_stash_to_archive.assert_awaited_once_with(job)
    assert result["archive_status"] == "pending_upload"


@pytest.mark.asyncio
async def test_move_success_marks_archived(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        # Daemon writes .move-done immediately:
        open(os.path.join(s.MOVE_RESULTS_PATH, "70.move-done"), "w").close()
        await m._move_stash_to_archive({"crawl_id": "70"})
    m._mark_as_archived.assert_awaited_once_with("70")


@pytest.mark.asyncio
async def test_move_error_raises_502(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        open(os.path.join(s.MOVE_RESULTS_PATH, "70.move-error"), "w").close()
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archive_move.py -v`
Expected: FAIL — no stashed branch / missing `_move_stash_to_archive`.

- [ ] **Step 3: Add the move helper** (near `archive_crawl`):

```python
    async def _move_stash_to_archive(self, job_info: dict) -> None:
        """Drive the GCS-side stash->archive move via the move-flow daemon:
        write .move-request, poll .move-done/.move-error, then mark archived +
        clear stashed_at. Idempotency lives in the daemon (already-moved=done)."""
        crawl_id = job_info["crawl_id"]
        req_dir = settings.MOVE_REQUESTS_PATH
        res_dir = settings.MOVE_RESULTS_PATH
        os.makedirs(req_dir, exist_ok=True)
        os.makedirs(res_dir, exist_ok=True)
        request_path = os.path.join(req_dir, f"{crawl_id}.move-request")
        done_path = os.path.join(res_dir, f"{crawl_id}.move-done")
        error_path = os.path.join(res_dir, f"{crawl_id}.move-error")

        async with aiofiles.open(request_path, "w") as f:
            await f.write(crawl_id)
        logger.info(f"Wrote .move-request for '{crawl_id}'. Waiting for daemon mv...")

        deadline = time.monotonic() + settings.MOVE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if os.path.exists(error_path):
                try: os.remove(error_path)
                except OSError: pass
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                    detail={"error_code": "STASH_MOVE_FAILED"})
            if os.path.exists(done_path):
                break
            await asyncio.sleep(1)
        else:
            try:
                if os.path.exists(request_path): os.remove(request_path)
            except OSError: pass
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                                detail={"error_code": "STASH_MOVE_TIMEOUT"})

        await self._mark_as_archived(crawl_id)
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        fresh = await cache_service.get_json(job_key)
        if fresh and "stashed_at" in fresh:
            fresh.pop("stashed_at", None)
            await cache_service.set_json(job_key, fresh)
        for p in (request_path, done_path, error_path):
            try:
                if os.path.exists(p): os.remove(p)
            except OSError: pass
        logger.info(f"Stash->archive move complete for '{crawl_id}'.")
```

- [ ] **Step 4: Add the stashed branch to `archive_crawl`.** At the very top of `archive_crawl`, after `crawl_id = job_info['crawl_id']` / `job_status = job_info.get('status')` (~1866) and before the `if job_status == "archived":` guard:

```python
        # Auto-stash: archiving a stashed crawl is a GCS-side move stash/->crawls/,
        # not a re-tar. Reuse archive_status='pending_upload' so the BO's
        # 3_archive_eligible_domains.php (exact-string branch) needs no change.
        if job_info.get("stashed_at"):
            await self._move_stash_to_archive(job_info)
            return {
                "crawl_id": crawl_id,
                "archive_status": "pending_upload",
                "archive_size_bytes": None,
            }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archive_move.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_archive_move.py
git commit -F .git/COMMIT_EDITMSG
```

---

### Task 13: Documentation

**Goal:** Document the feature in the service + tools CLAUDE.md so operators/devs understand the flow and the move-flow daemon instance.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (new "## Auto-Stash Workflow" section)
- Modify: `tools/CLAUDE.md` (move-flow daemon env vars + invocation)

**Acceptance Criteria:**
- [ ] crawler-service CLAUDE.md documents: trigger model (grace/timeout/disk-pressure), the new Redis fields, the sweep, `/results` transparent unstash, update-mode stashed restore, and the `AUTO_STASH_ENABLED` gate + tunables.
- [ ] tools/CLAUDE.md documents the move-flow daemon: `ENABLE_MOVE=true`, `MOVE_*` env vars, marker protocol, and the recommended invocation alongside the stash-flow daemon.
- [ ] Links the spec.

**Verify:** Manual — re-read both sections; confirm env var names match `config.py` (Task 6, 10) and the daemon (Task 11).

**Steps:**

- [ ] **Step 1: Add the crawler-service CLAUDE.md section** (after the existing "## Stash — Free Disk Investigation Workflow" section). Document the lifecycle diagram, the three new `job_data` fields, the sweep eligibility, the `/results`/update-mode transparency, the gate + tunables, and link `docs/superpowers/specs/2026-06-01-auto-stash-unstash-workflow-design.md`.

- [ ] **Step 2: Add the tools/CLAUDE.md move-flow daemon block** — document `ENABLE_MOVE`, `MOVE_REQUESTS_PATH`, `MOVE_RESULTS_PATH`, `MOVE_SOURCE_PREFIX=stash`, `MOVE_TARGET_PREFIX=crawls`, the `.move-request`/`.move-done`/`.move-error` markers, and that it runs as a third invocation of `download_daemon.sh` (or folded into the stash-flow instance with `ENABLE_MOVE=true`).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md tools/CLAUDE.md
git commit -F .git/COMMIT_EDITMSG
```

---

## Rollout / Phase Gates

- **Gate 1→2:** Tasks 1-5 deployed. Verify in prod: manually stash a crawl → `GET /results` transparently unstashes + serves; update-mode crawl with a stashed previous crawl restores + resumes; `downloaded_at`/`finished_at`/`size_bytes` observed populating in Redis.
- **Gate 2→3:** Tasks 6-9 deployed with `AUTO_STASH_ENABLED=true`. Verify: never-downloaded crawl stashes after safety timeout; downloaded crawl stashes after grace; disk-pressure stashes largest first; no `/results` breakage; upload-daemon backlog healthy; `STASH_UPLOAD_ORPHAN` rate acceptable.
- **Phase 3** (Tasks 10-13): deploy the move-flow daemon (`ENABLE_MOVE=true`), then verify `POST /archive` on a stashed crawl moves `stash/→crawls/` and returns `pending_upload`.

## Self-Review

- **Spec coverage:** every spec §6/§7/§8 item maps to a task (P1→T1-5, P2→T6-9, P3→T10-12, docs→T13; config→T6,T10; observability prefixes→T8,T9; failure handling→T9,T12 idempotency). Decisions D1-D12 all reflected.
- **Type consistency:** `_stamp_terminal_fields`, `_is_stash_eligible`, `_select_stash_candidates`, `_auto_stash_one`, `_disk_used_pct`, `_requeue_stash_orphan`, `_restore_previous_crawl`, `_move_stash_to_archive` — each defined once and referenced consistently. `downloaded_at`/`finished_at`/`size_bytes`/`stashed_at` field names consistent across tasks. `archive_status="pending_upload"` matches the BO contract.
- **No placeholders:** every step has real code + exact commands.
