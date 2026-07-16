# Auto-Stash Follow-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the auto-stash retrieve bug (a stashed crawl relaunched fresh instead of resuming) and expose the four auto-stash metadata fields on `GET /status`.

**Architecture:** Two surgical changes in `crawler-service` (Python) + one docs change. Fix A adds a resume-on-start inline unstash to `start_crawl` (mirrors the existing update-mode `previous_crawl_id` restore). Fix B adds four optional fields to `CrawlStatus` and maps them in both `get_status` return paths. No BO change; existing-data drain is an operator runbook step.

**Tech Stack:** Python 3.x / FastAPI, pytest + unittest.mock.

**Spec:** `docs/superpowers/specs/2026-06-02-auto-stash-followup-design.md`

---

## File Structure

| File | Change | Task |
|---|---|---|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | `start_crawl` resume-on-start unstash (Fix A); `get_status` map 4 fields both paths (Fix B) | 1, 2 |
| `apps-microservices/crawler-service/app/schemas/crawler.py` | `CrawlStatus` +4 optional fields (Fix B) | 2 |
| `apps-microservices/crawler-service/tests/test_auto_stash_resume_on_start.py` | new (Fix A tests) | 1 |
| `apps-microservices/crawler-service/tests/test_status_autostash_fields.py` | new (Fix B tests) | 2 |
| `apps-microservices/crawler-service/CLAUDE.md` | doc notes | 3 |

**Verified context (current code):**
- `start_crawl` (`crawler_manager.py:368`) builds a **fresh** `job_data` (`:391-403`) and writes it at `:470`, clobbering any prior record. So the prior record must be captured **before** `:470`. `_rollback_claim(decrement_counter=...)` closure is defined at `:477`. STORAGE SETUP (`makedirs` + `_cleanup_stale_state_for_relaunch`) is `:507-520`; the update-mode block is `:522-568`. The capacity INCR backstop ends ~`:505`.
- `_cleanup_stale_state_for_relaunch` (`:2899`) only unlinks `_completion_marker.json` — never datasets/request_queues. So unstash → STORAGE SETUP is safe (cleanup strips the restored stale marker; resume data survives).
- `unstash_crawl(self, job_info)` restores storage from `gs://stash/`, clears `stashed_at`, 2-phase GCS delete; raises 502/504 on failure.
- `get_status` (`:1365-1452`) has **two** `CrawlStatus` builds: snapshot path `return CrawlStatus(**snapshot_data)` (`:1395`, taken when `status != "running"` and `_status_snapshot.json` exists — i.e. terminal/stashed crawls) and the main path `return CrawlStatus(...)` (`:1439-1452`). It already enriches `snapshot_data["status"]` and `snapshot_data["is_error"]` before `:1395`.
- `CrawlStatus` (`schemas/crawler.py:140-158`).
- Test seam: `manager_with_mocks` fixture in `tests/test_start_crawl_capacity.py` (stubs `os.uname`, mocks `cache_service.get_key/set_json/increment_key/safe_decrement_key/delete_key` + `redis_client.set`→True). `cache_service.get_json` is NOT mocked by it — tests add it.
- tdd-gate: `crawler_manager.py` edits satisfied by existing `test_crawler_manager*.py`; `schemas/` path is gate-exempt. No shim needed.

---

### Task 1: Fix A — resume-on-start inline unstash

**Goal:** When `/start` is called on a crawl whose own id is stashed, unstash it from GCS before spawning so it resumes, instead of starting fresh and orphaning the stash.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`start_crawl`: capture prior record ~`:384`; unstash block before STORAGE SETUP ~`:506`)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_resume_on_start.py`

**Acceptance Criteria:**
- [ ] A stashed started id triggers `await self.unstash_crawl(prior_job_info)` before STORAGE SETUP.
- [ ] Unstash failure → `_rollback_claim(decrement_counter=True)` + the error propagates (HTTPException as-is; generic → 503).
- [ ] No prior record / no `stashed_at` → `unstash_crawl` NOT called.
- [ ] `is_restart=True` (OOM relaunch) → `unstash_crawl` NOT called.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_resume_on_start.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# apps-microservices/crawler-service/tests/test_auto_stash_resume_on_start.py
"""Fix A: resume-on-start inline unstash (auto-stash follow-up)."""
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException

from app.core import crawler_manager
from tests.test_start_crawl_capacity import manager_with_mocks  # reuse fixture


class _Sentinel(Exception):
    """Raised by a stubbed step AFTER the unstash point to stop start_crawl early."""


def _stashed_record(crawl_id="900"):
    return {"crawl_id": crawl_id, "status": "stopped", "domain": "x.fr",
            "storage_path": f"/app/storage/{crawl_id}", "stashed_at": "2026-06-01T00:00:00"}


async def _call_start(manager):
    return await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None, params={},
    )


@pytest.mark.asyncio
async def test_start_unstashes_stashed_id(manager_with_mocks, monkeypatch):
    manager, redis_mock, cache_mocks = manager_with_mocks
    monkeypatch.setattr(crawler_manager.cache_service, "get_json",
                        AsyncMock(return_value=_stashed_record()))
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    # Stub the step right after the unstash (storage cleanup) to stop start_crawl
    # before it spawns a real subprocess — proves we passed the unstash + continued.
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_unstash_failure_rolls_back(manager_with_mocks, monkeypatch):
    manager, redis_mock, cache_mocks = manager_with_mocks
    monkeypatch.setattr(crawler_manager.cache_service, "get_json",
                        AsyncMock(return_value=_stashed_record()))
    manager.unstash_crawl = AsyncMock(
        side_effect=HTTPException(status_code=502, detail={"error_code": "GCS_DOWNLOAD_FAILED"}))
    with pytest.raises(HTTPException) as exc:
        await _call_start(manager)
    assert exc.value.status_code == 502           # HTTPException propagates as-is
    cache_mocks["safe_decrement_key"].assert_awaited()  # rollback decremented the slot


@pytest.mark.asyncio
async def test_start_skips_unstash_when_not_stashed(manager_with_mocks, monkeypatch):
    manager, redis_mock, cache_mocks = manager_with_mocks
    monkeypatch.setattr(crawler_manager.cache_service, "get_json",
                        AsyncMock(return_value=None))  # fresh crawl, no prior record
    manager.unstash_crawl = AsyncMock()
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_start_skips_unstash_on_restart(manager_with_mocks, monkeypatch):
    manager, redis_mock, cache_mocks = manager_with_mocks
    # Even if a stashed record exists, is_restart must skip the resume-on-start path.
    monkeypatch.setattr(crawler_manager.cache_service, "get_json",
                        AsyncMock(return_value=_stashed_record()))
    manager.unstash_crawl = AsyncMock()
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await manager.start_crawl(
            domain="x.fr", start_url="https://x.fr/", crawl_id="900",
            callback_url="https://cb", failure_callback_url=None, params={},
            is_restart=True,
        )
    manager.unstash_crawl.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_resume_on_start.py -v`
Expected: FAIL — `unstash_crawl` never called (no resume-on-start logic yet); `test_start_unstash_failure_rolls_back` won't see the 502.

- [ ] **Step 3a: Capture the prior record before the fresh write**

In `start_crawl`, find (`:382-384`):
```python
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        lock_key = f"{CRAWL_LOCK_PREFIX}{crawl_id}"
        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)
```
Replace with:
```python
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        lock_key = f"{CRAWL_LOCK_PREFIX}{crawl_id}"
        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)

        # Capture the prior Redis record BEFORE the fresh job_data write below
        # (line ~470 overwrites it). Used by the resume-on-start unstash to detect
        # a stashed crawl being relaunched. is_restart (OOM relaunch) never stashes.
        prior_job_info = None if is_restart else await cache_service.get_json(job_key)
```

- [ ] **Step 3b: Insert the resume-on-start unstash before STORAGE SETUP**

Find (`:506-516`, the end of the capacity backstop + the start of STORAGE SETUP):
```python
        # --- STORAGE SETUP ---
        try:
            os.makedirs(job_storage_path, exist_ok=True)
            logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
```
Replace with:
```python
        # --- AUTO-STASH: resume-on-start ---
        # If this crawl's own data is stashed in GCS, restore it BEFORE storage
        # setup so the crawl resumes from its request_queue instead of starting
        # fresh (which would orphan the GCS stash + waste local disk). Runs before
        # _cleanup_stale_state_for_relaunch so the restored stale completion marker
        # is stripped. Mirrors the previous_crawl_id restore + /results unstash.
        if prior_job_info and prior_job_info.get("stashed_at"):
            logger.info(f"Crawl '{crawl_id}' is stashed; unstashing from GCS to resume "
                        f"instead of starting fresh.")
            try:
                await self.unstash_crawl(prior_job_info)
            except HTTPException:
                await _rollback_claim(decrement_counter=True)
                raise
            except Exception as e:
                await _rollback_claim(decrement_counter=True)
                logger.error(f"Failed to unstash crawl '{crawl_id}' on start: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to unstash crawl '{crawl_id}' from GCS: {str(e)}",
                )

        # --- STORAGE SETUP ---
        try:
            os.makedirs(job_storage_path, exist_ok=True)
            logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
```
NOTE: this placement is AFTER `_rollback_claim` is defined (`:477`) and after the capacity INCR backstop, so the slot is reserved and rollback is available — matching the update-mode restore's error handling. If the exact surrounding lines differ, anchor on `# --- STORAGE SETUP ---` and insert the block immediately before it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_resume_on_start.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit** (bilingual EN+FR via `.git/COMMIT_EDITMSG_AUTOSTASH`, `git -c commit.encoding=utf-8 commit -F` — main thread handles this)

```
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_resume_on_start.py
```

---

### Task 2: Fix B — expose auto-stash fields on /status

**Goal:** Surface `stashed_at`, `downloaded_at`, `finished_at`, `size_bytes` on `GET /status` (both the snapshot and main paths), backward-compatibly.

**Files:**
- Modify: `apps-microservices/crawler-service/app/schemas/crawler.py` (`CrawlStatus` ~`:140-158`)
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`get_status`: snapshot enrich ~`:1392`, main build ~`:1439`)
- Test: `apps-microservices/crawler-service/tests/test_status_autostash_fields.py`

**Acceptance Criteria:**
- [ ] `CrawlStatus` has `stashed_at`, `downloaded_at`, `finished_at` (`Optional[str]=None`) + `size_bytes` (`Optional[int]=None`).
- [ ] Main path maps all four from `job_info`.
- [ ] Snapshot path injects all four from `job_info` into `snapshot_data` before constructing (so terminal/stashed crawls expose them).
- [ ] Absent fields → `null` (backward-compatible).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_status_autostash_fields.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# apps-microservices/crawler-service/tests/test_status_autostash_fields.py
"""Fix B: expose stashed_at/downloaded_at/finished_at/size_bytes on /status."""
import json
import os
import pytest

from app.core.crawler_manager import CrawlerManager


def _job(tmp_path, **extra):
    job = {"crawl_id": "900", "status": "finished", "domain": "x.fr",
           "start_url": "https://x.fr/", "start_time": "2026-06-01T00:00:00",
           "storage_path": str(tmp_path)}
    job.update(extra)
    return job


@pytest.mark.asyncio
async def test_status_main_path_maps_fields(tmp_path):
    mgr = CrawlerManager()
    job = _job(tmp_path, status="running",  # running → skip snapshot path
               stashed_at="2026-06-01T01:00:00", downloaded_at="2026-06-01T02:00:00",
               finished_at="2026-06-01T03:00:00", size_bytes=12345)
    st = await mgr.get_status(job)
    assert st.stashed_at == "2026-06-01T01:00:00"
    assert st.downloaded_at == "2026-06-01T02:00:00"
    assert st.finished_at == "2026-06-01T03:00:00"
    assert st.size_bytes == 12345


@pytest.mark.asyncio
async def test_status_null_when_absent(tmp_path):
    mgr = CrawlerManager()
    st = await mgr.get_status(_job(tmp_path, status="running"))
    assert st.stashed_at is None and st.downloaded_at is None
    assert st.finished_at is None and st.size_bytes is None


@pytest.mark.asyncio
async def test_status_snapshot_path_includes_fields(tmp_path):
    """Terminal/stashed crawls take the snapshot path — it must expose the fields."""
    mgr = CrawlerManager()
    snapshot = {"crawl_id": "900", "id_domaine": "900", "status": "finished",
                "domain": "x.fr", "start_url": "https://x.fr/",
                "start_time": "2026-06-01T00:00:00", "urls_crawled": 5,
                "error_urls_crawled": 0, "nfr_urls_crawled": 0}
    (tmp_path / "_status_snapshot.json").write_text(json.dumps(snapshot))
    job = _job(tmp_path, status="finished",
               stashed_at="2026-06-01T01:00:00", size_bytes=999)
    st = await mgr.get_status(job)
    assert st.stashed_at == "2026-06-01T01:00:00"
    assert st.size_bytes == 999
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_status_autostash_fields.py -v`
Expected: FAIL — `CrawlStatus` has no `stashed_at` (TypeError/AttributeError) or the fields are not mapped.

- [ ] **Step 3a: Add the fields to `CrawlStatus`**

In `schemas/crawler.py`, find the end of `CrawlStatus` (after the `is_error` field, `:152-158`):
```python
    is_error: Optional[str] = Field(
        None,
        description="Error category from _callback_payload.json "
                    "(e.g., 'stoppedManually', 'insufficientData', 'limitCrawl'). "
                    "Empty/null for successful crawls. Used by BO reconciliation "
                    "to route to the correct error branch."
    )
```
Add immediately after it (still inside the class):
```python
    stashed_at: Optional[str] = Field(None, description="ISO ts when data was moved to GCS stash; null if local.")
    downloaded_at: Optional[str] = Field(None, description="ISO ts of the last successful /results download (auto-stash grace start).")
    finished_at: Optional[str] = Field(None, description="ISO ts of the terminal transition (auto-stash safety-timeout start).")
    size_bytes: Optional[int] = Field(None, description="Estimated archive size in bytes (auto-stash disk-pressure ordering).")
```

- [ ] **Step 3b: Map the fields in the main `get_status` path**

In `crawler_manager.py`, find the main build (`:1439-1452`):
```python
        return CrawlStatus(
            crawl_id=crawl_id,
            id_domaine=crawl_id, # Legacy alias
            status=job_info["status"],
            domain=job_info["domain"],
            start_url=job_info["start_url"],
            start_time=job_info["start_time"],
            urls_crawled=urls_crawled,
            error_urls_crawled=error_urls_crawled,
            nfr_urls_crawled=nfr_urls_crawled,
            last_activity=last_url_time,
            last_heartbeat=job_info.get("last_heartbeat"),
            is_error=is_error,
        )
```
Replace the closing kwargs (`is_error=is_error,` then `)`) with:
```python
            last_heartbeat=job_info.get("last_heartbeat"),
            is_error=is_error,
            stashed_at=job_info.get("stashed_at"),
            downloaded_at=job_info.get("downloaded_at"),
            finished_at=job_info.get("finished_at"),
            size_bytes=job_info.get("size_bytes"),
        )
```

- [ ] **Step 3c: Enrich the snapshot path**

In `crawler_manager.py`, find the snapshot enrichment before `return CrawlStatus(**snapshot_data)` (`:1389-1395`):
```python
                # Override status with current Redis value — snapshot was taken before status transition
                snapshot_data["status"] = job_info["status"]
                # Enrich snapshot with isError from _callback_payload.json (snapshot may predate it,
                # and BO reconciliation needs it to route non-success terminal crawls correctly).
                snapshot_data["is_error"] = await _read_callback_isError(storage_path)
```
Add immediately after the `is_error` enrich line:
```python
                # Auto-stash metadata lives only in Redis job_data, never in the
                # disk snapshot — inject it so terminal/stashed crawls expose it.
                snapshot_data["stashed_at"] = job_info.get("stashed_at")
                snapshot_data["downloaded_at"] = job_info.get("downloaded_at")
                snapshot_data["finished_at"] = job_info.get("finished_at")
                snapshot_data["size_bytes"] = job_info.get("size_bytes")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_status_autostash_fields.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add apps-microservices/crawler-service/app/schemas/crawler.py apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_status_autostash_fields.py
```

---

### Task 3: Documentation

**Goal:** Document the resume-on-start behavior, the failed-crawl 48h-timeout stashing, the new `/status` fields, and the existing-data drain.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (Auto-Stash Workflow section)

**Acceptance Criteria:**
- [ ] Notes: (1) `start_crawl` unstashes a stashed started id inline (resume-on-start), not just the update-mode previous crawl; (2) failed/never-downloaded crawls stash via the 48h safety-timeout regardless of webhook delivery; (3) `GET /status` exposes the 4 fields; (4) existing-data drain = one-time `tools/stash_crawls_batch.py` run.
- [ ] Links the follow-up spec.

**Verify:** Manual — re-read the section; env/field names match Task 1 + 2.

**Steps:**

- [ ] **Step 1:** In `apps-microservices/crawler-service/CLAUDE.md`, in the "Auto-Stash Workflow" section, append a "Follow-up (2026-06-02)" subsection covering the four notes above and linking `docs/superpowers/specs/2026-06-02-auto-stash-followup-design.md`.

- [ ] **Step 2: Commit**

```
git add apps-microservices/crawler-service/CLAUDE.md
```

---

## Rollout / Operator Notes

- **Existing data drain (one-time):** after deploy, run `python tools/stash_crawls_batch.py` to bulk-stash current on-disk terminal crawls. `stash_crawl` doesn't require `finished_at`, so legacy crawls stash fine. Steady-state is then covered by download-grace (re-downloaded crawls get `downloaded_at`) + the sweep.
- **No BO change.** `/status` additions are optional/nullable; resume-on-start is fully server-side.

## Self-Review

- **Spec coverage:** Fix A (§2)→Task 1; Fix B (§3)→Task 2; docs (§6)→Task 3; existing-data (§4)→rollout note; webhook-error (§5)→doc note in Task 3. All spec sections covered.
- **No placeholders:** every step has real code + exact commands.
- **Type consistency:** `prior_job_info` (Task 1) defined once; `stashed_at`/`downloaded_at`/`finished_at`/`size_bytes` field names + `job_info.get(...)` mappings identical across schema, both get_status paths, and tests; `unstash_crawl(job_info)` signature matches the shipped method.
