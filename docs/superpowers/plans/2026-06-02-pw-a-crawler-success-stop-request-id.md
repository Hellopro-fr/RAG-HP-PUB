# PW-A Crawler Half — request_id on Success/Stop Webhooks (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit a stable, persisted `request_id` on the success and stop webhooks (shared per job) so the BO endpoint can dedup duplicate terminal deliveries, mirroring the already-shipped failure-webhook idempotency.

**Architecture:** Add `_get_or_create_terminal_webhook_request_id(job_info)` (mirrors `_get_or_create_failure_request_id`, distinct key `terminal_webhook_request_id`). Both `_send_success_webhook` and `_send_stop_webhook` call it, set `params["request_id"]`, and persist `job_info` to Redis (`cache_service.set_json`) before sending — so reconciliation / `/pending-callbacks` replays and a force-finish-stop-after-success reuse the same id. BO consumes it via `is_duplicate_crawler_webhook(rid, 'success')` (BO half, separate plan).

**Tech Stack:** Python (asyncio, httpx), Redis via `cache_service`, pytest. Runs in CI/locally (unlike BO).

**Repo / working dir:** `RAG-HP-PUB` at `D:\DevHellopro\Workspaces\RAG-HP-PUB`. All commands and commits run **from that directory** (it is a separate git repo from Marketplace). Commits follow the RAG-HP-PUB convention (English Conventional Commits).

**Spec:** `Marketplace/docs/superpowers/specs/2026-06-02-pw-a-success-webhook-idempotency-design.md` (§3). Prior art: `RAG-HP-PUB/docs/superpowers/specs/2026-04-18-webhook-idempotency-design.md` (failure idempotency; "Future Extensions #1" = this work).

**Pre-verified (this plan):**
- `CRAWL_JOB_PREFIX = "crawl_job:"` is module-level in `crawler_manager.py:30` (in scope in both senders).
- `cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)` is the established persist pattern (failure helper callsites L662/L727).
- `_send_success_webhook` (L822) ends with `await self._send_webhook_with_retry(str(callback_url), params, crawl_id, "success")` (L921); `crawl_id = job_info["crawl_id"]` (L824).
- `_send_stop_webhook` (L953) ends with `await self._send_webhook_with_retry(str(url), params, crawl_id, "stop")` (L1010); `crawl_id = job_info['crawl_id']` (L958).
- `_get_or_create_failure_request_id` (L740-755) is the helper to mirror. Existing tests for it: `tests/test_crawler_manager.py` L542-565 (class with `_manager()` factory using `CrawlerManager.__new__`).
- The stop webhook reaches BO's **success** branch (no `crawl_id`+`exit_code` in its params, L997-1008) — which is exactly why it needs `request_id` shared with success.

---

### Task 1: Add `_get_or_create_terminal_webhook_request_id` helper (TDD)

**Goal:** A pure helper returning a stable per-job UUID for terminal (success/stop) webhooks.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert after `_get_or_create_failure_request_id`, which ends at L755)
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add a test class)

**Acceptance Criteria:**
- [ ] `_get_or_create_terminal_webhook_request_id(job_info)` returns a valid UUID string, persists it under `job_info["terminal_webhook_request_id"]`, and reuses it on subsequent calls.
- [ ] Distinct key from `failure_webhook_request_id` (failure path untouched).
- [ ] New tests pass.

**Verify:** from `apps-microservices/crawler-service/`: `pytest tests/test_crawler_manager.py -v -k "terminal"` → all PASS

**Steps:**

- [ ] **Step 1: Write failing tests** (append a new class to `tests/test_crawler_manager.py`)

```python
class TestTerminalWebhookRequestId:
    """PW-A: stable request_id shared by success + stop webhooks."""

    def _manager(self):
        from app.core.crawler_manager import CrawlerManager
        return CrawlerManager.__new__(CrawlerManager)

    def test_terminal_request_id_generated_when_absent(self):
        mgr = self._manager()
        job_info: dict = {}
        rid = mgr._get_or_create_terminal_webhook_request_id(job_info)
        assert isinstance(rid, str)
        _uuid_module.UUID(rid)  # raises if not a valid UUID
        assert job_info["terminal_webhook_request_id"] == rid

    def test_terminal_request_id_reused(self):
        mgr = self._manager()
        existing = "11111111-2222-3333-4444-555555555555"
        job_info = {"terminal_webhook_request_id": existing}
        rid = mgr._get_or_create_terminal_webhook_request_id(job_info)
        assert rid == existing
        assert job_info["terminal_webhook_request_id"] == existing

    def test_success_and_stop_share_one_id(self):
        # Both senders call the same helper with the same job_info, so a natural
        # success followed by a force-finish stop carries ONE id -> PHP dedupes.
        mgr = self._manager()
        job_info: dict = {}
        rid_success = mgr._get_or_create_terminal_webhook_request_id(job_info)
        rid_stop = mgr._get_or_create_terminal_webhook_request_id(job_info)
        assert rid_success == rid_stop

    def test_terminal_id_distinct_from_failure_id_key(self):
        mgr = self._manager()
        job_info: dict = {}
        mgr._get_or_create_terminal_webhook_request_id(job_info)
        assert "terminal_webhook_request_id" in job_info
        assert "failure_webhook_request_id" not in job_info
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_crawler_manager.py -v -k "terminal"`
Expected: FAIL — `AttributeError: … has no attribute '_get_or_create_terminal_webhook_request_id'`

- [ ] **Step 3: Add the helper after `_get_or_create_failure_request_id` (after L755)**

```python
    def _get_or_create_terminal_webhook_request_id(self, job_info: dict) -> str:
        """Returns a stable request_id shared by the SUCCESS and STOP webhooks of a job.

        Stored in job_info under "terminal_webhook_request_id" so every terminal delivery
        for this job — natural success, force-finish stop, reconciliation replay,
        /pending-callbacks replay — carries the SAME id. PHP dedupes on it, so the
        completion pipeline runs exactly once even when a success is followed by a
        force-finish stop(finished) (both reach PHP's success branch).

        Distinct from failure_webhook_request_id so the (already-shipped) failure path is
        untouched. The caller MUST persist job_info back to Redis via cache_service.set_json.
        """
        rid = job_info.get("terminal_webhook_request_id")
        if rid:
            return rid
        rid = str(uuid.uuid4())
        job_info["terminal_webhook_request_id"] = rid
        return rid
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/test_crawler_manager.py -v -k "terminal"`
Expected: 4 PASS

- [ ] **Step 5: Commit** (from `D:\DevHellopro\Workspaces\RAG-HP-PUB`)

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler): add terminal webhook request_id helper (PW-A)

Mirrors _get_or_create_failure_request_id with a distinct key
(terminal_webhook_request_id) shared by the success and stop webhooks
so a force-finish-stop-after-success pair dedupes on the PHP side."
```

---

### Task 2: Wire `request_id` + Redis persist into both senders

**Goal:** `_send_success_webhook` and `_send_stop_webhook` attach the shared `request_id` and persist `job_info` before sending.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`_send_success_webhook` before the L921 send; `_send_stop_webhook` before the L1010 send)
- Test: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (source-inspection tests — mirrors the existing `test_send_failure_webhook_body_includes_request_id_when_provided` pattern, since these senders do file IO that is impractical to fully mock)

**Acceptance Criteria:**
- [ ] Both senders call `_get_or_create_terminal_webhook_request_id(job_info)`, set `params["request_id"]`, and `await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)` **before** the retry send.
- [ ] Source-inspection tests assert all three on each sender.
- [ ] Existing tests still pass.

**Verify:** from `apps-microservices/crawler-service/`: `pytest tests/test_crawler_manager.py -v -k "terminal or success_webhook or stop_webhook"` → all PASS

**Steps:**

- [ ] **Step 1: Add source-inspection tests** (append to `TestTerminalWebhookRequestId`)

```python
    def test_success_webhook_source_wires_request_id_and_persist(self):
        import inspect
        from app.core import crawler_manager as cm
        src = inspect.getsource(cm.CrawlerManager._send_success_webhook)
        assert "_get_or_create_terminal_webhook_request_id" in src, \
            "_send_success_webhook must obtain the shared terminal request_id"
        assert 'params["request_id"]' in src, \
            "_send_success_webhook must add request_id to params"
        assert "set_json" in src, \
            "_send_success_webhook must persist job_info to Redis before sending"

    def test_stop_webhook_source_wires_request_id_and_persist(self):
        import inspect
        from app.core import crawler_manager as cm
        src = inspect.getsource(cm.CrawlerManager._send_stop_webhook)
        assert "_get_or_create_terminal_webhook_request_id" in src, \
            "_send_stop_webhook must obtain the shared terminal request_id"
        assert 'params["request_id"]' in src, \
            "_send_stop_webhook must add request_id to params"
        assert "set_json" in src, \
            "_send_stop_webhook must persist job_info to Redis before sending"
```

- [ ] **Step 2: Run, verify they fail**

Run: `pytest tests/test_crawler_manager.py -v -k "success_webhook or stop_webhook"`
Expected: FAIL on the two new assertions (request_id not yet wired).

- [ ] **Step 3: Wire `_send_success_webhook`** — insert before the final send at L921.

Context — existing lines L919-921:
```python
        # --- END: Ensure message_erreur_crawling is present ---

        await self._send_webhook_with_retry(str(callback_url), params, crawl_id, "success")
```

becomes:
```python
        # --- END: Ensure message_erreur_crawling is present ---

        # PW-A: stable request_id shared with the stop webhook; persist so reconciliation
        # / pending-callbacks replays reuse it and PHP dedupes the duplicate delivery.
        params["request_id"] = self._get_or_create_terminal_webhook_request_id(job_info)
        await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)

        await self._send_webhook_with_retry(str(callback_url), params, crawl_id, "success")
```

- [ ] **Step 4: Wire `_send_stop_webhook`** — insert before the final send at L1010.

Context — existing lines L1008-1010:
```python
            "message_erreur_crawling": self._map_error_to_message(is_error) if is_error else ""
        }
        
        await self._send_webhook_with_retry(str(url), params, crawl_id, "stop")
```

becomes:
```python
            "message_erreur_crawling": self._map_error_to_message(is_error) if is_error else ""
        }

        # PW-A: same shared request_id as the success webhook (a force-finish stop after a
        # natural success must dedupe against it on the PHP side); persist for replays.
        params["request_id"] = self._get_or_create_terminal_webhook_request_id(job_info)
        await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)

        await self._send_webhook_with_retry(str(url), params, crawl_id, "stop")
```

- [ ] **Step 5: Run the full affected set**

Run: `pytest tests/test_crawler_manager.py -v -k "terminal or success_webhook or stop_webhook"`
Expected: all PASS. Then full file: `pytest tests/test_crawler_manager.py -q` → no regressions.

- [ ] **Step 6: Commit** (from `D:\DevHellopro\Workspaces\RAG-HP-PUB`)

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler): emit shared request_id on success + stop webhooks (PW-A)

Both senders now attach terminal_webhook_request_id and persist job_info
to Redis before sending, so duplicate terminal deliveries (force-finish
after success, reconciliation / pending-callbacks replay) dedupe on the
PHP side. Closes the success/stop idempotency gap (failure path already done)."
```

---

### Task 3: Document the success/stop idempotency contract

**Goal:** Record the extended contract in the crawler-service CLAUDE.md so the dedup behavior is discoverable.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] A short subsection documents: success + stop webhooks carry a shared `terminal_webhook_request_id`; persisted in `job_info`; BO dedups via `is_duplicate_crawler_webhook(rid, 'success')`; failure path uses its own `failure_webhook_request_id`.

**Verify:** `grep -n "terminal_webhook_request_id" apps-microservices/crawler-service/CLAUDE.md` → matches.

**Steps:**

- [ ] **Step 1: Append this subsection** to `apps-microservices/crawler-service/CLAUDE.md` (under the existing webhook/idempotency documentation; if no such section exists, add it near the webhook description)

```markdown
## Webhook Idempotency

Terminal webhooks carry a stable, persisted `request_id` so the BO endpoint can
dedupe duplicate deliveries:

- **Failure** webhooks: `failure_webhook_request_id` (in `job_info`), reused across
  shutdown / reconciliation / OOM-restart / force-finish / monitor paths.
- **Success + Stop** webhooks (PW-A): a single shared `terminal_webhook_request_id`
  (in `job_info`), reused by `_send_success_webhook` and `_send_stop_webhook`. A
  force-finish stop(`finished`) after a natural success therefore carries the SAME id
  and dedupes. The stop webhook reaches BO's *success* branch (it sends no
  `crawl_id`+`exit_code`), which is why it shares the success id.

Every sender persists `job_info` via `cache_service.set_json` before sending so a
replay reuses the same id. BO dedupes via `is_duplicate_crawler_webhook(request_id, 'success')`
for success+stop and `'failure'` for failures, into the `crawler_webhook_dedup` table.
```

- [ ] **Step 2: Verify**

Run: `grep -n "terminal_webhook_request_id" apps-microservices/crawler-service/CLAUDE.md`
Expected: at least one match.

- [ ] **Step 3: Commit** (from `D:\DevHellopro\Workspaces\RAG-HP-PUB`)

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler): document success/stop webhook idempotency contract (PW-A)"
```

---

## Self-Review

**Spec coverage (§3):** §3.1 helper → Task 1. §3.2 wire both senders + persist → Task 2. §3.3 untouched failure path → preserved (distinct key, source-inspection test asserts failure key absent). Tests (§6) → Tasks 1+2. CLAUDE.md (§8) → Task 3. All covered.

**Placeholder scan:** none — exact code, exact `pytest`/`grep` commands, expected results.

**Type consistency:** helper name `_get_or_create_terminal_webhook_request_id` and key `terminal_webhook_request_id` identical across Task 1 (def + tests), Task 2 (both senders + tests), Task 3 (doc). `params["request_id"]` and `cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)` identical in both senders. `_uuid_module` alias reused from existing tests.

**Note:** independently shippable — adds `request_id`; harmless until BO's layer-1 consumes it (BO is already protected by its layer-2 guard). Deploy order-free.
