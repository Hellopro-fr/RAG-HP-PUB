# Design — Fix singular `/status/{crawl_id}` 500 on malformed Redis blobs

**Date:** 2026-05-19
**Status:** Approved (design); pending implementation plan
**Author:** Rindra ANDRIANJANAKA (designed with Claude)
**Service:** `apps-microservices/crawler-service` (Python, FastAPI, asyncio)
**Branch:** `features/poc`

**Related work:**
- Predecessor: commit `508de256` (2026-05-03) "guard get_status against malformed Redis job blobs" — added malformed-blob guard at `get_status()` + heal-on-read in plural `get_all_statuses`. This spec fixes the singular `/status/{crawl_id}` endpoint that was missed by that commit.

---

## 1. Problem Statement

### 1.1 Observed incident

`GET /status/6664` returns 500 with the following logs:

```
ERROR | app.core.crawler_manager | Skipping malformed job entry (missing 'crawl_id'): keys=['cpu', 'domain', 'id', 'ram', 'replica_id', 'start_time', 'status', 'total_ram']
ERROR | uvicorn.error | Exception in ASGI application
fastapi.exceptions.ResponseValidationError: 1 validation error:
  {'type': 'model_attributes_type', 'loc': ('response',), 'msg': 'Input should be a valid dictionary or object to extract fields from', 'input': None}
File "/app/app/router/crawler.py", line 274, in get_crawl_status
```

The Redis blob for crawl 6664 has key `id` instead of `crawl_id` (plus `cpu`/`ram`/`total_ram` — likely written by an older code version or a resource-monitor service, not the current `start_crawl` builder).

### 1.2 Root cause

Commit `508de256` (predecessor) fixed the PLURAL endpoint `/status` against this exact blob shape by:
- In `get_all_statuses`: deriving `crawl_id` from the Redis key suffix and injecting it via `setdefault` before passing the dict downstream
- Changing `get_status()` return type to `Optional[CrawlStatus]` so it can guard and return None instead of raising KeyError

But the SINGULAR endpoint `/status/{crawl_id}` was NOT updated:
- `get_job_or_recover(crawl_id)` (the FastAPI dependency at `router/crawler.py:23`) returns the raw `job_info` dict from Redis at line 34 WITHOUT the `setdefault` heal
- `get_crawl_status` endpoint at line 274 passes the malformed dict to `get_status()`
- `get_status()` sees `crawl_id` missing, logs the error, returns None
- The endpoint's `response_model=CrawlStatus` is non-optional → Pydantic raises `ResponseValidationError` on the None response
- FastAPI translates to HTTP 500

### 1.3 Scope of this spec

Patch the singular `/status/{crawl_id}` endpoint to mirror the plural-endpoint heal-on-read pattern, plus convert the genuine "malformed beyond healing" case to HTTP 404 instead of 500. Does not investigate WHY blob 6664 has `id` instead of `crawl_id` (separate forensic / migration concern). Does not introduce a cleanup script.

---

## 2. Goals & Non-Goals

### Goals

- **G1:** `GET /status/{crawl_id}` no longer returns 500 when the Redis blob is missing `crawl_id` but the key suffix has it.
- **G2:** Symmetric with plural endpoint heal-on-read pattern (`setdefault('crawl_id', from_key_suffix)`).
- **G3:** When `get_status()` returns None despite the heal (e.g. `storage_path` also missing), raise HTTP 404 with a clear message instead of letting Pydantic surface a 500.
- **G4:** Healthy jobs unchanged — 200 + CrawlStatus body identical to today.
- **G5:** Plural endpoint untouched — its self-heal still works.
- **G6:** No new dependencies, no schema change, no new Redis writes.

### Non-Goals

- **NG1:** Forensic investigation into WHY blob 6664 has `id` instead of `crawl_id`. Likely a legacy or external writer. Out of scope.
- **NG2:** Cleanup script to backfill legacy blobs. Out of scope.
- **NG3:** Push the `setdefault` heal further into `get_status()` itself (option C from brainstorming). Predecessor commit chose caller-side heal; sticking with that pattern.
- **NG4:** Changes to `get_all_statuses` (plural endpoint). Already working.
- **NG5:** Changes to the storage-recovery branch (L36+ in `get_job_or_recover`). That path reconstructs a full job_info from disk and already includes `crawl_id`. Not affected by this bug.
- **NG6:** Telemetry counter for malformed-blob hits.

---

## 3. Architecture

### 3.1 Two-line change in `get_job_or_recover` + endpoint None-check

**File:** `apps-microservices/crawler-service/app/router/crawler.py`

```
get_job_or_recover(crawl_id):
    job_info = await cache_service.get_json(job_key)
    if job_info:
        ── NEW: job_info.setdefault('crawl_id', crawl_id)
        return job_info
    # ... (existing disk recovery branch unchanged)

get_crawl_status(crawl_id, job_info: dict = Depends(get_job_or_recover)):
    status_data = await crawler_manager.get_status(job_info)
    ── NEW: if status_data is None: raise 404
    return status_data
```

### 3.2 What stays unchanged

- `crawler_manager.get_status()` body — already returns Optional[CrawlStatus] with malformed-blob guard
- `crawler_manager.get_all_statuses()` — plural endpoint self-heal
- `response_model=CrawlStatus` on the endpoint — kept non-optional; we raise 404 BEFORE returning, so Pydantic never sees None
- Disk-recovery branch of `get_job_or_recover` (L36+) — reconstructs full job_info, not affected
- Plural endpoint `/status`

---

## 4. Code shape

### 4.1 Site 1 — `get_job_or_recover` heal-on-read

```python
# OLD (router/crawler.py:30-34)
job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
job_info = await cache_service.get_json(job_key)

if job_info:
    return job_info

# NEW
job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
job_info = await cache_service.get_json(job_key)

if job_info:
    # Heal legacy / partial blobs missing crawl_id. Mirrors get_all_statuses
    # setdefault pattern (commit 508de256). Without this, downstream
    # get_status() returns None on the malformed-blob guard and the
    # singular /status/{crawl_id} endpoint's Pydantic response_model
    # fails with 500 (observed on crawl 6664 — blob had 'id' but not
    # 'crawl_id', likely written by an older code version or an
    # external resource-monitor service).
    job_info.setdefault('crawl_id', crawl_id)
    return job_info
```

### 4.2 Site 2 — endpoint None-check raises 404

```python
# OLD (router/crawler.py:274-279)
@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.
    """
    return await crawler_manager.get_status(job_info)

# NEW
@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.

    Raises 404 when get_status() returns None (malformed blob beyond heal-on-read —
    e.g. missing storage_path as well as crawl_id). Without this guard, Pydantic
    response_model validation would surface a 500 on the None response.
    """
    status_data = await crawler_manager.get_status(job_info)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job '{crawl_id}' state is malformed (missing required fields).",
        )
    return status_data
```

### 4.3 No new imports

`HTTPException` and `status` are already imported at top of `router/crawler.py` (used by `get_job_or_recover` disk-recovery branch line 42).

---

## 5. Failure modes

| # | Scenario | Outcome | Acceptable? |
|---|----------|---------|-------------|
| F1 | Blob has `crawl_id` already (happy path) | setdefault no-op. Existing flow. 200 + CrawlStatus body. | Yes — regression preserved. |
| F2 | Blob missing `crawl_id` only (the 6664 case) | setdefault injects from URL path. get_status() sees crawl_id ✓ + checks storage_path. If storage_path also missing → None → 404. Else → 200 + body. | Yes — primary fix. |
| F3 | Blob missing `crawl_id` AND `storage_path` | setdefault injects crawl_id. get_status() still returns None on storage_path guard. Endpoint raises 404. | Yes — clear semantics. |
| F4 | Job genuinely absent from Redis AND disk | `get_job_or_recover` raises 404 (unchanged behavior, line 42). | Yes — unchanged. |
| F5 | Job recovered from disk (L36+ branch) | Disk recovery builds full job_info including crawl_id. setdefault on the early-return path doesn't fire. | Yes — disk path untouched. |
| F6 | Plural endpoint regression | Untouched. Self-heal in get_all_statuses still works. | Yes. |
| F7 | Concurrent write changes blob mid-read | `cache_service.get_json` returns a snapshot. setdefault on local dict only. No race. | Yes. |
| F8 | `crawl_id` parameter from URL contains malicious / invalid chars | URL routing validates `{crawl_id}` as str. setdefault uses the string as-is — same input that already feeds Redis key construction (line 30). No new attack surface. | Yes. |

---

## 6. Verification

### 6.1 Local pytest (logic-shape style)

Optional. Tests are loose in this codebase; existing pattern at `tests/test_crawler_manager.py` is "logic-shape" assertions on small dicts. Sample additions:

```python
class TestStatusSingularEndpoint:
    @pytest.mark.asyncio
    async def test_get_job_or_recover_injects_crawl_id_on_legacy_blob(self, mocker):
        # legacy blob from Redis missing crawl_id
        legacy_blob = {'id': '6664', 'domain': 'example.com', 'status': 'running'}
        mocker.patch(
            "app.router.crawler.cache_service.get_json",
            return_value=legacy_blob,
        )
        from app.router.crawler import get_job_or_recover
        result = await get_job_or_recover('6664')
        assert result['crawl_id'] == '6664'

    @pytest.mark.asyncio
    async def test_get_job_or_recover_preserves_existing_crawl_id(self, mocker):
        modern_blob = {'crawl_id': '6664', 'domain': 'example.com', 'status': 'running'}
        mocker.patch(
            "app.router.crawler.cache_service.get_json",
            return_value=modern_blob,
        )
        from app.router.crawler import get_job_or_recover
        result = await get_job_or_recover('6664')
        assert result['crawl_id'] == '6664'  # not overwritten
```

Note: `mocker` fixture may not be available locally (per prior session findings). If pytest-mock missing, skip these tests and rely on Docker smoke + production verification.

### 6.2 Docker compose smoke

```bash
docker compose run --rm crawler-service python -m py_compile app/router/crawler.py
```
Expected: no output (clean).

Bring up crawler-service:
```bash
docker compose up -d crawler-service
```

Inject a malformed blob via Redis CLI (mirror the 6664 shape):

```bash
docker compose exec redis redis-cli SET "crawl_jobs:test-bad" '{"id":"test-bad","domain":"example.com","status":"running","cpu":1,"ram":1024,"replica_id":"node-1","start_time":"2026-05-19T08:00:00","total_ram":4096}'
```

Test singular endpoint:
```bash
curl -i http://localhost:<port>/status/test-bad
```

**Expected outcomes (depending on what's missing besides crawl_id):**
- If only `crawl_id` is missing (storage_path present) → 200 with CrawlStatus body, `crawl_id="test-bad"`
- If both `crawl_id` and `storage_path` missing → 404 with detail "state is malformed (missing required fields)"
- NOT 500.

Healthy blob test:
```bash
docker compose exec redis redis-cli SET "crawl_jobs:test-ok" '{"crawl_id":"test-ok","domain":"example.com","status":"running","storage_path":"/app/storage/test-ok","start_time":"2026-05-19T08:00:00"}'
curl -i http://localhost:<port>/status/test-ok
```

Expected: 200 + body.

Plural endpoint:
```bash
curl -i http://localhost:<port>/status
```

Expected: 200 + array containing entries (plural still works — regression check).

Cleanup:
```bash
docker compose exec redis redis-cli DEL "crawl_jobs:test-bad" "crawl_jobs:test-ok"
```

### 6.3 Production verification

After deploy:
- Re-run the original failing case: `curl https://<crawler-service>/status/6664`
- Expected: either 200 (if blob still has storage_path) or 404 (malformed beyond heal). Not 500.
- Check logs for `Skipping malformed job entry` line:
  ```bash
  docker compose logs crawler-service --since 1h | grep "Skipping malformed job entry"
  ```
  Some occurrences expected (operator already saw them); they continue to log because they fire BEFORE the endpoint-level 404. Confirm no `Exception in ASGI application` 500 traceback for `/status/{id}` after deploy.

---

## 7. Out of scope

- Forensic investigation of blob 6664's origin (legacy code? external service?). Separate effort.
- Cleanup script to backfill `crawl_id` into all legacy blobs in Redis. Separate spec if scale justifies.
- Pushing the heal-on-read into `get_status()` itself (architectural drift from 508de256's caller-side pattern).
- Changes to `get_all_statuses` (already works).
- Changes to `cache_service.get_json` signature or behavior.
- Adding telemetry counter for malformed-blob hits per endpoint.
- Adding a `LegacyBlobShape` model and explicit migration.

---

## 8. Open questions

- **[UNCLEAR]** Whether the disk-recovery branch of `get_job_or_recover` ever returns a job_info missing `crawl_id`. From the code (L82+) it always reconstructs `crawl_id` via the function parameter. Safe by construction, but worth confirming during the verification step.
- **[UNCLEAR]** Whether the 6664-style blobs (`cpu`/`ram`/`total_ram` fields) come from a known resource monitor in the stack or from a deprecated code path. Mentioned in commit 508de256's message as "legacy blobs from older code, or partial writes". Investigation deferred.

---

## 9. Future work

- Forensic: identify all writers of `crawl_jobs:*` keys outside `start_crawl` to catch field-name drift.
- Cleanup cron: backfill `crawl_id` on legacy Redis entries; remove stale fields like `cpu`/`ram`/`total_ram` if not used by current code.
- Telemetry: Prometheus counter `crawler_malformed_blob_total{endpoint,missing_field}` so operator can see if the problem worsens or self-resolves.
- Consider pushing all heal-on-read into a single `_normalize_job_info(job_info, crawl_id)` helper, used by both endpoints. Quality-of-life improvement once the problem space stabilizes.
