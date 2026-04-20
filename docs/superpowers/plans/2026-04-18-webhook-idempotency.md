# Webhook Idempotency — Client-Side Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate processing of failure webhooks on the PHP side by sending a stable `request_id` UUID (persisted in `job_data`) that PHP can dedupe against. Also bound shutdown to 5 seconds via a short-timeout single-attempt webhook path.

**Architecture:** Add two helpers to `CrawlerManager`: `_get_or_create_failure_request_id` (idempotent UUID generation persisted in `job_data`) and `_send_webhook_once` (single-attempt bounded-timeout send for the shutdown path). Update `_send_failure_webhook` to accept `request_id` and a `shutdown` flag. Update all 6 callsites to generate+persist the UUID before sending. Increase Docker `stop_grace_period` to 30s for safety margin.

**Tech Stack:** Python 3.12, `uuid.uuid4()`, `httpx.AsyncClient`, pytest + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-04-18-webhook-idempotency-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | MODIFY | Add 2 helpers (`_get_or_create_failure_request_id`, `_send_webhook_once`); update `_send_failure_webhook` signature; update all 6 callsites |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | MODIFY | Add `TestWebhookIdempotency` class with tests for helpers + `request_id` in params + shutdown short timeout |
| `docker-compose.yml` | MODIFY | Add `stop_grace_period: 30s` under the `crawler-service` block |
| `apps-microservices/crawler-service/CLAUDE.md` | MODIFY | Document the idempotency contract and expected PHP dedup behavior |

---

### Task 1: Add helpers `_get_or_create_failure_request_id` and `_send_webhook_once`

**Goal:** Create the two pure helpers that the callsite updates in Task 2 will depend on. They're testable independently and form the foundation for the rest of the plan.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (add `import uuid` + 2 methods on `CrawlerManager`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add `TestWebhookIdempotency` class with tests for both helpers)

**Acceptance Criteria:**
- [ ] `import uuid` added near the top of `crawler_manager.py`
- [ ] `_get_or_create_failure_request_id(job_info)` returns an existing UUID if `job_info["failure_webhook_request_id"]` is set; otherwise generates, stores in `job_info`, and returns a new UUID (as str)
- [ ] `_send_webhook_once(url, params, crawl_id, webhook_type, timeout)` sends a single HTTP GET, returns `True` on 2xx, `False` otherwise (no retries, no FAILED_CALLBACKS_KEY storage)
- [ ] 4 unit tests pass (see Step 2)

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestWebhookIdempotency -v`

**Steps:**

- [ ] **Step 1: Add `import uuid` near the top of `crawler_manager.py`**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, find the stdlib imports block near the top (around line 1-20). Locate a line like `import time` or `import shutil` and add `import uuid` nearby (alphabetical order preferred). Example:

**Find:**

```python
import time
```

**Replace with:**

```python
import time
import uuid
```

- [ ] **Step 2: Add the two helpers on `CrawlerManager`**

Insert these two methods immediately before the existing `_send_webhook_with_retry` method (around line 433). The exact "Find" anchor is the `_send_webhook_with_retry` header line:

**Find:**

```python
    async def _send_webhook_with_retry(self, url: str, params: dict, crawl_id: str, webhook_type: str):
        """
        Sends an HTTP GET webhook with exponential backoff retry.
        On exhaustion, stores the failed callback in Redis for manual replay.
        """
```

**Replace with:**

```python
    def _get_or_create_failure_request_id(self, job_info: dict) -> str:
        """Returns the failure webhook's request_id, generating + persisting one if absent.

        The UUID is stored in job_info so every retry path (shutdown, reconciliation,
        OOM max-restarts, monitor, force-finish) uses the same value. PHP dedupes by
        request_id, guaranteeing single processing regardless of how many times we send.

        NOTE: the caller is responsible for persisting job_info back to Redis via
        cache_service.set_json — this helper only mutates the in-memory dict.
        """
        rid = job_info.get("failure_webhook_request_id")
        if rid:
            return rid
        rid = str(uuid.uuid4())
        job_info["failure_webhook_request_id"] = rid
        return rid

    async def _send_webhook_once(self, url: str, params: dict, crawl_id: str,
                                  webhook_type: str, timeout: float = 5.0) -> bool:
        """Single-attempt webhook send with a custom timeout.

        Used by the shutdown path to bound worst-case time. Does NOT retry and does
        NOT store in FAILED_CALLBACKS_KEY on failure — reconciliation will replay
        using the same request_id from job_info, and PHP dedupes.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=timeout)
                if 200 <= response.status_code < 300:
                    logger.info(f"Webhook '{webhook_type}' for '{crawl_id}' sent (shutdown). Status: {response.status_code}")
                    return True
                logger.warning(f"Webhook '{webhook_type}' for '{crawl_id}' got {response.status_code} during shutdown")
                return False
        except httpx.RequestError as e:
            logger.warning(f"Webhook '{webhook_type}' for '{crawl_id}' failed during shutdown: {e}")
            return False

    async def _send_webhook_with_retry(self, url: str, params: dict, crawl_id: str, webhook_type: str):
        """
        Sends an HTTP GET webhook with exponential backoff retry.
        On exhaustion, stores the failed callback in Redis for manual replay.
        """
```

- [ ] **Step 3: Add the test class to `test_crawler_manager.py`**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python


import uuid as _uuid_module
from unittest.mock import AsyncMock, MagicMock, patch


class TestWebhookIdempotency:
    """Tests for failure webhook idempotency helpers.
    The helpers are standalone and pure — tested directly, not via archive_crawl."""

    def _manager(self):
        """Instantiate CrawlerManager without running __init__ (avoids Redis setup)."""
        from app.core.crawler_manager import CrawlerManager
        return CrawlerManager.__new__(CrawlerManager)

    def test_get_or_create_generates_new_uuid_when_absent(self):
        """First call on a job_info with no request_id must generate and persist a new UUID."""
        mgr = self._manager()
        job_info: dict = {}

        rid = mgr._get_or_create_failure_request_id(job_info)

        assert isinstance(rid, str)
        # Must be a valid UUID
        _uuid_module.UUID(rid)  # raises ValueError if not a valid UUID
        # Must persist in the dict
        assert job_info["failure_webhook_request_id"] == rid

    def test_get_or_create_reuses_existing_uuid(self):
        """Second call must return the same UUID stored from the first call."""
        mgr = self._manager()
        existing = "550e8400-e29b-41d4-a716-446655440000"
        job_info = {"failure_webhook_request_id": existing}

        rid = mgr._get_or_create_failure_request_id(job_info)

        assert rid == existing
        # And the dict must not have been mutated to a different value
        assert job_info["failure_webhook_request_id"] == existing

    def test_send_webhook_once_returns_true_on_2xx(self):
        """Single-attempt send returns True on HTTP 200."""
        import asyncio
        mgr = self._manager()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "failure", timeout=1.0)
            )

        assert result is True

    def test_send_webhook_once_returns_false_on_timeout(self):
        """Single-attempt send returns False when httpx raises (timeout or connection error) and does NOT retry."""
        import asyncio
        import httpx
        mgr = self._manager()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("too slow"))
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "failure", timeout=1.0)
            )

        assert result is False
        # Must have been called exactly once — no retries
        assert mock_client.__aenter__.return_value.get.call_count == 1
```

- [ ] **Step 4: Run tests**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestWebhookIdempotency -v
```

Expected: 4 tests PASS.

Then confirm no regression:

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler-service): add request_id helper and single-attempt webhook sender"
```

---

### Task 2: Update `_send_failure_webhook` signature to accept `request_id` and `shutdown` flag

**Goal:** Plumb `request_id` through `_send_failure_webhook`'s params and add a `shutdown` flag that selects the single-attempt short-timeout path when True.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`_send_failure_webhook` around line 575)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add 2 tests to `TestWebhookIdempotency`)

**Acceptance Criteria:**
- [ ] `_send_failure_webhook` signature accepts `request_id: Optional[str] = None` and `shutdown: bool = False`
- [ ] When `request_id` is provided, it's included in the webhook params as `"request_id": request_id`
- [ ] When `shutdown=True`, the call routes through `_send_webhook_once` with `timeout=5.0`; otherwise through `_send_webhook_with_retry`
- [ ] Existing callsites (unchanged in this task — they don't pass the new args yet) still work because defaults preserve old behavior

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v`

**Steps:**

- [ ] **Step 1: Update the signature and body of `_send_failure_webhook`**

Find the existing method (around line 575):

**Find:**

```python
    async def _send_failure_webhook(self, url: str, crawl_id: str, domain: str, exit_code: int, crawl_mode: str = "standard"):
        # We process failures for both standard and update modes now
        # Determine message_erreur_crawling from context
        error_message = ""
        if exit_code == -1:
            error_message = "Out Of Memory"  # Special exit code for OOM max restarts or shutdown
        elif exit_code == 3:
            error_message = "Out Of Memory"  # OOM_RELAUNCH exit code
        elif exit_code == 4:
            error_message = "Update crawl failed: previous crawl data was empty or unavailable"
        elif exit_code in (137, -9):
            error_message = "Processus tué (SIGKILL) - OOM Kill ou redémarrage forcé"
        elif exit_code is not None and exit_code < 0:
            error_message = f"Processus terminé par signal {abs(exit_code)}"  # Signal-killed
        elif exit_code not in (0, 2, 3, 4, -1, 137):
            error_message = f"Erreur inattendue (code de sortie: {exit_code})"
        
        params = {
            "crawl_id": crawl_id, "domain": domain, "exit_code": exit_code,
            "timestamp": datetime.utcnow().isoformat(),
            "message_erreur_crawling": error_message
        }
        
        await self._send_webhook_with_retry(url, params, crawl_id, "failure")
```

**Replace with:**

```python
    async def _send_failure_webhook(self, url: str, crawl_id: str, domain: str, exit_code: int,
                                    crawl_mode: str = "standard",
                                    request_id: Optional[str] = None,
                                    shutdown: bool = False):
        # We process failures for both standard and update modes now
        # Determine message_erreur_crawling from context
        error_message = ""
        if exit_code == -1:
            error_message = "Out Of Memory"  # Special exit code for OOM max restarts or shutdown
        elif exit_code == 3:
            error_message = "Out Of Memory"  # OOM_RELAUNCH exit code
        elif exit_code == 4:
            error_message = "Update crawl failed: previous crawl data was empty or unavailable"
        elif exit_code in (137, -9):
            error_message = "Processus tué (SIGKILL) - OOM Kill ou redémarrage forcé"
        elif exit_code is not None and exit_code < 0:
            error_message = f"Processus terminé par signal {abs(exit_code)}"  # Signal-killed
        elif exit_code not in (0, 2, 3, 4, -1, 137):
            error_message = f"Erreur inattendue (code de sortie: {exit_code})"

        params = {
            "crawl_id": crawl_id, "domain": domain, "exit_code": exit_code,
            "timestamp": datetime.utcnow().isoformat(),
            "message_erreur_crawling": error_message
        }
        if request_id:
            params["request_id"] = request_id

        if shutdown:
            # Bounded shutdown path: 5-second timeout, no retries.
            # Delivery failure is acceptable — reconciliation replays with the same
            # request_id, PHP dedupes, no duplicate processing.
            await self._send_webhook_once(url, params, crawl_id, "failure", timeout=5.0)
        else:
            await self._send_webhook_with_retry(url, params, crawl_id, "failure")
```

Verify that `Optional` is already imported at the top of the file. If it is not, add it — search the import section for `from typing import ...` and add `Optional` to the list. Typical form:

```python
from typing import Dict, Optional, Any, List, Tuple
```

(If `Optional` is already there, skip this sub-step.)

- [ ] **Step 2: Add source-inspection tests to `TestWebhookIdempotency`**

Append to the existing `TestWebhookIdempotency` class in `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python

    def test_send_failure_webhook_signature_accepts_request_id_and_shutdown(self):
        """The updated _send_failure_webhook must accept request_id and shutdown kwargs."""
        import inspect
        from app.core import crawler_manager as cm

        sig = inspect.signature(cm.CrawlerManager._send_failure_webhook)
        assert "request_id" in sig.parameters, (
            "_send_failure_webhook must accept a request_id parameter"
        )
        assert "shutdown" in sig.parameters, (
            "_send_failure_webhook must accept a shutdown boolean parameter"
        )
        # Backward-compatible defaults
        assert sig.parameters["request_id"].default is None
        assert sig.parameters["shutdown"].default is False

    def test_send_failure_webhook_body_includes_request_id_when_provided(self):
        """Source inspection: the method body must add request_id to params when set,
        and must route through _send_webhook_once when shutdown=True."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._send_failure_webhook)
        assert 'params["request_id"] = request_id' in source, (
            "_send_failure_webhook must include request_id in the params dict when provided"
        )
        assert "_send_webhook_once" in source, (
            "_send_failure_webhook must route to _send_webhook_once when shutdown=True"
        )
        assert "timeout=5.0" in source, (
            "_send_webhook_once must be called with a 5-second timeout during shutdown"
        )
```

- [ ] **Step 3: Run tests**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS (the 4 from Task 1 + 2 new + pre-existing).

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler-service): _send_failure_webhook accepts request_id and shutdown flag"
```

---

### Task 3: Update all 6 failure-webhook callsites

**Goal:** At every callsite, generate-or-reuse the `request_id` via the helper, persist `job_info` back to Redis, and pass `request_id` (and `shutdown=True` for the shutdown path) to `_send_failure_webhook`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (6 callsites)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (1 source-inspection test)

**Acceptance Criteria:**
- [ ] All 6 `_send_failure_webhook` callsites call `_get_or_create_failure_request_id(job_info)` immediately before the webhook and persist `job_info` via `cache_service.set_json` before the webhook call
- [ ] All 6 callsites pass `request_id=<uuid>` to `_send_failure_webhook`
- [ ] The shutdown callsite (`_cleanup_running_job`) additionally passes `shutdown=True`
- [ ] Source-inspection test confirms all 6 callsites reference `_get_or_create_failure_request_id`

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v`

**Steps:**

The 6 callsites are at lines ~372, ~425, ~798, ~909, ~1353, ~1923 (line numbers will shift as edits are applied — use the Find patterns below as anchors).

- [ ] **Step 1: Update callsite in `_relaunch_oom_crawl` — OOM max-restarts path (~line 372)**

Generate the request_id BEFORE `set_json` so the UUID is persisted in the same write. This preserves the original single-path flow (no duplicated delete/set/publish).

**Find:**

```python
            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            await self._publish_update(crawl_id, "failed")

            if job_info.get("failure_callback_url"):
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    -1, # Special exit code for max restart fail
                    job_info.get("crawl_mode", "standard")
                ))
```

**Replace with:**

```python
            # Generate request_id before set_json so the UUID is persisted in the
            # same Redis write. Reconciliation/retries read the same UUID later
            # and PHP dedupes → no duplicate processing.
            request_id = None
            if job_info.get("failure_callback_url"):
                request_id = self._get_or_create_failure_request_id(job_info)

            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            await self._publish_update(crawl_id, "failed")

            if request_id:
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    -1, # Special exit code for max restart fail
                    job_info.get("crawl_mode", "standard"),
                    request_id=request_id,
                ))
```

- [ ] **Step 2: Update callsite in `_relaunch_oom_crawl` — OOM relaunch failure (~line 425)**

Same pattern: generate request_id before the `set_json`.

**Find:**

```python
            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            await self._publish_update(crawl_id, "failed")
            if job_info.get("failure_callback_url"):
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    -1,
                    job_info.get("crawl_mode", "standard")
                ))
```

**Replace with:**

```python
            # Generate request_id before set_json so the UUID is persisted in the
            # same Redis write. Reconciliation/retries read the same UUID later
            # and PHP dedupes → no duplicate processing.
            request_id = None
            if job_info.get("failure_callback_url"):
                request_id = self._get_or_create_failure_request_id(job_info)

            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            await self._publish_update(crawl_id, "failed")
            if request_id:
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    -1,
                    job_info.get("crawl_mode", "standard"),
                    request_id=request_id,
                ))
```

- [ ] **Step 3: Update callsite in `_monitor_process` — normal failure exit (~line 798)**

**Find:**

```python
            # --- WEBHOOK LOGIC ---
            if is_success and job_info.get("callback_url"):
                logger.info(f"Crawl '{crawl_id}' succeeded. Triggering success webhook.")
                asyncio.create_task(self._send_success_webhook(job_info))
            elif not is_success and job_info.get("failure_callback_url"):
                logger.info(f"Crawl '{crawl_id}' failed. Triggering failure webhook.")
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    exit_code,
                    job_info.get("crawl_mode", "standard")
                ))
```

**Replace with:**

```python
            # --- WEBHOOK LOGIC ---
            if is_success and job_info.get("callback_url"):
                logger.info(f"Crawl '{crawl_id}' succeeded. Triggering success webhook.")
                asyncio.create_task(self._send_success_webhook(job_info))
            elif not is_success and job_info.get("failure_callback_url"):
                logger.info(f"Crawl '{crawl_id}' failed. Triggering failure webhook.")
                request_id = self._get_or_create_failure_request_id(job_info)
                await cache_service.set_json(job_key, job_info)
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    exit_code,
                    job_info.get("crawl_mode", "standard"),
                    request_id=request_id,
                ))
```

The `job_key` variable is already in scope in `_monitor_process` (defined at the top of the method).

- [ ] **Step 4: Update callsite in `force_finish_crawl` (~line 909)**

**Find:**

```python
        # Use appropriate webhook based on target status
        if target_status == "failed" and job_info.get("failure_callback_url"):
            asyncio.create_task(self._send_failure_webhook(
                str(job_info["failure_callback_url"]),
                crawl_id,
                job_info.get("domain", "unknown"),
                -1,  # Force-finish exit code
                job_info.get("crawl_mode", "standard")
            ))
```

**Replace with:**

```python
        # Use appropriate webhook based on target status
        if target_status == "failed" and job_info.get("failure_callback_url"):
            request_id = self._get_or_create_failure_request_id(job_info)
            await cache_service.set_json(job_key, job_info)
            asyncio.create_task(self._send_failure_webhook(
                str(job_info["failure_callback_url"]),
                crawl_id,
                job_info.get("domain", "unknown"),
                -1,  # Force-finish exit code
                job_info.get("crawl_mode", "standard"),
                request_id=request_id,
            ))
```

`job_key` is in scope in `force_finish_crawl`.

- [ ] **Step 5: Update callsite in `_cleanup_running_job` — shutdown path (~line 1353)**

This is the shutdown path — the one path that uses `shutdown=True`.

**Find:**

```python
                # 4. Send failure webhook
                if job_info.get("failure_callback_url"):
                    logger.info(f"Sending failure webhook for job '{crawl_id}'.")
                    # Use a special exit code like -1 for shutdown
                    await self._send_failure_webhook(
                        str(job_info["failure_callback_url"]),
                        crawl_id,
                        job_info["domain"],
                        -1,
                        job_info.get("crawl_mode", "standard")
                    )
```

**Replace with:**

```python
                # 4. Send failure webhook (bounded shutdown path: 5s timeout, single attempt)
                if job_info.get("failure_callback_url"):
                    logger.info(f"Sending failure webhook for job '{crawl_id}' (shutdown path).")
                    request_id = self._get_or_create_failure_request_id(job_info)
                    await cache_service.set_json(job_key, job_info)
                    # shutdown=True routes through _send_webhook_once (5s timeout, no retry).
                    # If delivery fails here, reconciliation replays with the same request_id
                    # and PHP dedupes by request_id — no duplicate processing.
                    await self._send_failure_webhook(
                        str(job_info["failure_callback_url"]),
                        crawl_id,
                        job_info["domain"],
                        -1,
                        job_info.get("crawl_mode", "standard"),
                        request_id=request_id,
                        shutdown=True,
                    )
```

`job_key` is defined at the top of `_cleanup_running_job`.

- [ ] **Step 6: Update callsite in reconciliation stale detection (~line 1923)**

This callsite is inside `_reconcile_locked` (after the Issue #1/#2 fixes — the scanning logic was renamed).

**Find:**

```python
                        # Only send failure webhook for non-stopping jobs
                        if not is_stopping and job_data.get("failure_callback_url"):
                            asyncio.create_task(self._send_failure_webhook(
                                str(job_data["failure_callback_url"]),
                                crawl_id,
                                job_data.get("domain", "unknown"),
                                -1,
                                job_data.get("crawl_mode", "standard")
                            ))
```

**Replace with:**

```python
                        # Only send failure webhook for non-stopping jobs.
                        # Use the persisted request_id so PHP dedupes against any prior
                        # attempt (e.g., from the shutdown path on the dying replica).
                        if not is_stopping and job_data.get("failure_callback_url"):
                            request_id = self._get_or_create_failure_request_id(job_data)
                            await cache_service.set_json(all_job_keys[i], job_data)
                            asyncio.create_task(self._send_failure_webhook(
                                str(job_data["failure_callback_url"]),
                                crawl_id,
                                job_data.get("domain", "unknown"),
                                -1,
                                job_data.get("crawl_mode", "standard"),
                                request_id=request_id,
                            ))
```

`all_job_keys[i]` is in scope inside the reconciliation loop (it's the key being processed in the current iteration).

- [ ] **Step 7: Append the source-inspection test to `TestWebhookIdempotency`**

```python

    def test_all_failure_webhook_callsites_use_request_id_helper(self):
        """Every callsite that sends a failure webhook must call
        _get_or_create_failure_request_id and pass request_id to the webhook."""
        import inspect
        from app.core import crawler_manager as cm

        # All 6 callsites live in these methods:
        methods_to_check = [
            cm.CrawlerManager._relaunch_oom_crawl,   # 2 callsites
            cm.CrawlerManager._monitor_process,      # 1 callsite
            cm.CrawlerManager.force_finish_crawl,    # 1 callsite
            cm.CrawlerManager._cleanup_running_job,  # 1 callsite (shutdown)
            cm.CrawlerManager._reconcile_locked,     # 1 callsite (reconciliation)
        ]

        for method in methods_to_check:
            source = inspect.getsource(method)
            assert "_get_or_create_failure_request_id" in source, (
                f"{method.__qualname__} must call _get_or_create_failure_request_id "
                f"before sending a failure webhook"
            )
            assert "request_id=" in source, (
                f"{method.__qualname__} must pass request_id= to _send_failure_webhook"
            )

    def test_shutdown_path_passes_shutdown_true(self):
        """_cleanup_running_job (shutdown path) must pass shutdown=True to _send_failure_webhook."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._cleanup_running_job)
        assert "shutdown=True" in source, (
            "_cleanup_running_job (shutdown path) must pass shutdown=True to route "
            "through the bounded single-attempt webhook send"
        )
```

- [ ] **Step 8: Run tests**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS (Task 1's 4 + Task 2's 2 + Task 3's 2 + pre-existing).

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler-service): thread request_id through all 6 failure-webhook callsites"
```

---

### Task 4: Increase Docker `stop_grace_period` to 30s

**Goal:** Give the bounded shutdown path (5s webhook) enough headroom for Redis writes, process cleanup, and background task cancellation.

**Files:**
- Modify: `docker-compose.yml` (the `crawler-service` service block)

**Acceptance Criteria:**
- [ ] `stop_grace_period: 30s` is added to the `crawler-service` service definition
- [ ] No other service definitions are modified
- [ ] YAML still parses (no syntax errors)

**Verify:** `docker compose config --services | grep crawler-service && python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('YAML OK')"`

**Steps:**

- [ ] **Step 1: Find the `crawler-service` block and add `stop_grace_period`**

Open `c:/Users/randr/Documents/Workspaces/RAG-HP-PUB/docker-compose.yml` and locate the `crawler-service:` block (around line 1202). Find an existing top-level field like `init: true` or `restart: unless-stopped` (whichever is present) and add `stop_grace_period: 30s` on the next line at the same indentation level.

Example targeted Find/Replace — if the current block contains `init: true`:

**Find:**

```yaml
  crawler-service:
    build:
      context: .
      dockerfile: ./apps-microservices/crawler-service/Dockerfile
    profiles: ["crawling"]
    init: true
```

**Replace with:**

```yaml
  crawler-service:
    build:
      context: .
      dockerfile: ./apps-microservices/crawler-service/Dockerfile
    profiles: ["crawling"]
    init: true
    stop_grace_period: 30s
```

If the exact `init: true` line is not present, insert `stop_grace_period: 30s` under any other existing field of the `crawler-service` block at the same indentation (4 spaces from the service block's start).

- [ ] **Step 2: Verify YAML parses**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('YAML OK')"
```

Expected: `YAML OK`.

- [ ] **Step 3: Verify the `crawler-service` definition now includes `stop_grace_period`**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && grep -A 10 "^  crawler-service:" docker-compose.yml | grep "stop_grace_period"
```

Expected output: `    stop_grace_period: 30s`

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(crawler-service): set stop_grace_period to 30s for bounded webhook shutdown"
```

---

### Task 5: Document the idempotency contract in CLAUDE.md

**Goal:** Record the client-side behavior and the PHP-side contract so future readers understand why `request_id` is generated and what PHP is expected to do with it.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] New "Failure Webhook Idempotency" section added before "Exit Codes (Node.js → Python)"
- [ ] Client behavior documented (request_id in job_data, bounded shutdown, reconciliation replay)
- [ ] PHP-side contract documented (dedup store, TTL ≥ 24h, backward compat)
- [ ] Spec reference included

**Verify:** `grep -q "failure_webhook_request_id" apps-microservices/crawler-service/CLAUDE.md`

**Steps:**

- [ ] **Step 1: Find the insertion point**

Open `apps-microservices/crawler-service/CLAUDE.md` and locate the `## Exit Codes (Node.js → Python)` heading. Insert the new section immediately before it.

- [ ] **Step 2: Add the section**

**Find:**

```markdown
Spec: `docs/superpowers/specs/2026-04-18-reconciliation-leader-election-design.md`.

## Exit Codes (Node.js → Python)
```

**Replace with:**

```markdown
Spec: `docs/superpowers/specs/2026-04-18-reconciliation-leader-election-design.md`.

## Failure Webhook Idempotency

Failure webhooks include a `request_id` UUID generated once per crawl failure and persisted in `job_data["failure_webhook_request_id"]`. PHP dedupes by this UUID so duplicate deliveries (common during shutdown + reconciliation replay) process at most once.

**Client-side (this service):**
- `_get_or_create_failure_request_id(job_info)` returns an existing UUID if present, else generates and persists one.
- The UUID is threaded through all 6 failure-webhook callsites: OOM max-restarts, OOM relaunch failure, monitor exit, force-finish, shutdown, reconciliation stale detection.
- Shutdown path uses a bounded `_send_webhook_once` (5-second timeout, no retries) via `shutdown=True`. If delivery fails, the persisted UUID lets reconciliation replay with the same identifier.
- Docker `stop_grace_period: 30s` gives the shutdown path enough headroom.

**PHP-side contract (`script_process_detect_fiche_produit.php`):**
- Read the `request_id` query parameter.
- Look up in a dedup store (Redis/MySQL/APC), TTL ≥ 24h.
- If found: return `HTTP 200` with no side effects.
- If not found: store, then process normally.
- If `request_id` is absent (legacy calls): process normally (backward compatible).

Spec: `docs/superpowers/specs/2026-04-18-webhook-idempotency-design.md`.

## Exit Codes (Node.js → Python)
```

- [ ] **Step 3: Verify the grep target succeeds**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && grep -q "failure_webhook_request_id" apps-microservices/crawler-service/CLAUDE.md && echo OK
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler-service): document failure webhook idempotency contract"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Helper: `_get_or_create_failure_request_id` (generate + persist in job_info) | Task 1 |
| Helper: `_send_webhook_once` (single attempt, bounded timeout, no FAILED_CALLBACKS_KEY storage) | Task 1 |
| `_send_failure_webhook` accepts `request_id` + `shutdown` flag | Task 2 |
| `request_id` added to params when provided | Task 2 |
| Shutdown routing through `_send_webhook_once` with 5s timeout | Task 2 |
| All 6 callsites generate+persist+pass `request_id` | Task 3 |
| Shutdown callsite uses `shutdown=True` | Task 3 (Step 5, callsite #5) |
| Docker `stop_grace_period: 30s` | Task 4 |
| CLAUDE.md documents client-side + PHP contract | Task 5 |
| Scope: failure webhooks only | Confirmed — no changes to `_send_success_webhook` or `_send_stop_webhook` |
| Backward compat when `request_id` is absent (legacy PHP) | Preserved — `request_id=None` default in new signature; `_send_webhook_with_retry` unchanged |
