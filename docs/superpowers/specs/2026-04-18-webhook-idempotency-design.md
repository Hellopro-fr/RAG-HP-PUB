# Design: Webhook Delivery During Shutdown — Idempotent Failure Webhook

**Date:** 2026-04-18
**Service:** crawler-service (+ PHP endpoint `script_process_detect_fiche_produit.php`)
**Status:** Approved (pending PHP team coordination)

## Problem

When Docker restarts the crawler-service (`docker compose up -d`), active crawls receive `SIGTERM` from Docker, followed by `SIGKILL` after `stop_grace_period` (default 10s). During that window, the crawler's `shutdown()` handler tries to send a failure webhook for each active crawl.

The webhook logic has a 30-second timeout per attempt and retries up to 3 times with delays `[5, 30, 120]`. If the PHP endpoint is slow (or overwhelmed by 7 simultaneous replicas restarting), the webhook hangs past the 10s grace period and `SIGKILL` terminates the process mid-webhook. The webhook is lost.

The reconciliation fallback eventually detects the stale job (after `STALE_JOB_THRESHOLD_REMOTE = 600s` = 10 minutes) and fires the webhook itself — but by then the caller (PHP scheduler) has been waiting for notification, and (with the Issue #1/#2 fixes) the reconciliation's single webhook still takes 10+ minutes to arrive.

## Decision

Split the fix across both sides:

- **Client side (this project):** bound shutdown to 5 seconds via short timeout + single attempt. Pre-generate and persist a `request_id` UUID in `job_data["failure_webhook_request_id"]` so any retry path (shutdown, reconciliation, manual replay) uses the same UUID.
- **Server side (PHP):** dedupe by `request_id`. If the endpoint has seen a `request_id` before, return `HTTP 200` without reprocessing.

Result: guaranteed exactly-once processing (from the caller's perspective), even if the client sends the webhook multiple times across shutdown + reconciliation.

## Design

### Client-side changes (crawler-service)

#### 1. Helper: `_get_or_create_failure_request_id(job_info)`

A small pure helper on `CrawlerManager` that returns a stable UUID for the failure webhook:

```python
def _get_or_create_failure_request_id(self, job_info: dict) -> str:
    """Returns the failure webhook's request_id, generating + persisting one if absent.
    The UUID is stored in job_info so every retry path uses the same value —
    PHP dedupes by request_id, guaranteeing single processing regardless of
    how many times we send."""
    rid = job_info.get("failure_webhook_request_id")
    if rid:
        return rid
    rid = str(uuid.uuid4())
    job_info["failure_webhook_request_id"] = rid
    return rid
```

Callers are responsible for persisting `job_info` back to Redis via `cache_service.set_json` after calling this helper (since multiple downstream writes typically happen together).

#### 2. Modify `_send_failure_webhook`

Add `request_id` to the webhook params. Add a `shutdown=False` flag for the short-timeout single-attempt path:

```python
async def _send_failure_webhook(
    self, url: str, crawl_id: str, domain: str, exit_code: int,
    crawl_mode: str = "standard", request_id: str | None = None,
    shutdown: bool = False,
):
    # ... existing error_message mapping ...

    params = {
        "crawl_id": crawl_id, "domain": domain, "exit_code": exit_code,
        "timestamp": datetime.utcnow().isoformat(),
        "message_erreur_crawling": error_message,
    }
    if request_id:
        params["request_id"] = request_id

    if shutdown:
        # Bounded shutdown path: short timeout, no retries.
        # Delivery failure is OK — reconciliation replays with the same request_id,
        # PHP dedupes, no duplicate processing.
        await self._send_webhook_once(url, params, crawl_id, "failure", timeout=5.0)
    else:
        await self._send_webhook_with_retry(url, params, crawl_id, "failure")
```

Add a new `_send_webhook_once` helper that mirrors `_send_webhook_with_retry` but without the retry loop:

```python
async def _send_webhook_once(self, url: str, params: dict, crawl_id: str,
                              webhook_type: str, timeout: float = 5.0) -> bool:
    """Single-attempt webhook send with a custom timeout. Used by shutdown path
    to bound worst-case time. On failure, does NOT store in FAILED_CALLBACKS_KEY —
    reconciliation will replay with the same request_id."""
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
```

#### 3. Update all failure-webhook callsites to use the helper

Every site that calls `_send_failure_webhook` must:
1. Call `request_id = self._get_or_create_failure_request_id(job_info)`
2. Persist `job_info` back to Redis via `set_json`
3. Pass `request_id` to the webhook call

Callsites to update:
- `_cleanup_running_job` (shutdown path) — pass `shutdown=True`
- `_monitor_process` (normal exit path with failure exit code)
- `_relaunch_oom_crawl` (OOM max-restarts path)
- Reconciliation's stale-detection branch in `_reconcile_locked`

#### 4. Docker `stop_grace_period`

Add to `docker-compose.yml` under the `crawler-service` block:

```yaml
crawler-service:
  # ...existing fields...
  stop_grace_period: 30s
```

30 seconds = 5s webhook budget + 25s headroom for process kill, Redis writes, background task cancellation.

### Server-side changes (PHP endpoint)

Delivered as a handoff prompt (below) to the PHP team's Claude instance. Contract:

- Read `request_id` from the query string.
- Look up in dedup store keyed by `request_id`. TTL: at least 24 hours (the crawler's retry window).
- **If found:** return `HTTP 200` with a minimal body (e.g., `{"status": "duplicate"}`). NO side effects: no status update, no logs written as "new", no downstream calls.
- **If not found:** store the `request_id` with TTL, then process the webhook as today.

If `request_id` is absent (legacy callers during rollout), process without dedup — keeps backward compatibility.

### Interaction between the two sides

- The client sends a failure webhook with a UUID during shutdown. SIGKILL may interrupt it.
- Reconciliation on a new replica detects the stale job. It reads `job_data["failure_webhook_request_id"]` — **same UUID**. It sends the webhook again.
- PHP sees the same `request_id`. If the shutdown send actually made it to PHP, the second send is deduped. If the shutdown send was interrupted, the second send is processed normally.
- **Result: exactly-once processing.**

### What stays unchanged

- Webhook retry logic (`_send_webhook_with_retry`) — unchanged for non-shutdown paths
- `FAILED_CALLBACKS_KEY` and `/pending-callbacks` endpoint — unchanged
- Reconciliation leader election, fresh heartbeat, ownership-agnostic override (from the previous brainstorm) — unchanged
- Success webhook and stop webhook paths — unchanged (not triggered during shutdown; same pattern can be added later if needed)
- Python ↔ Node.js contract — unchanged

### Edge Cases

| Case | Behavior |
|------|----------|
| Shutdown webhook succeeds in < 5s | Delivered once; reconciliation path skipped (status already `failed`) |
| Shutdown webhook times out at 5s | Reconciliation replays with the same `request_id`; PHP dedupes |
| Shutdown webhook succeeds but SIGKILL hits before Redis `set_json` | Reconciliation uses the older (unset) UUID — no wait, `request_id` IS persisted before sending. Fine. |
| PHP endpoint temporarily down | Shutdown attempt fails at 5s; reconciliation retries; normal retry backoff applies when PHP recovers; PHP dedupes the eventual successful one |
| `request_id` absent from request (legacy caller) | PHP processes normally (backward compatible) |
| Two different replicas race to fire reconciliation webhook | Issue #1 fix (leader election) prevents this; only one replica acts |
| Same `crawl_id` reused by scheduler for new crawl after old one failed | New crawl's `job_data` is fresh (no `failure_webhook_request_id` field); new UUID generated. Previous crawl's dedup entry may still exist in PHP but has different UUID, so no conflict. |

### Files to modify

| File | Change |
|------|--------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Add `_get_or_create_failure_request_id` helper; add `_send_webhook_once` helper; update `_send_failure_webhook` signature; update all 4 failure-webhook callsites to generate + persist UUID; pass `shutdown=True` from `_cleanup_running_job` |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | Unit tests: UUID generated, persisted, reused on retry; `request_id` included in params; shutdown path uses short timeout |
| `docker-compose.yml` | Add `stop_grace_period: 30s` to `crawler-service` |
| `apps-microservices/crawler-service/CLAUDE.md` | Document the idempotency contract and the dedup behavior PHP is expected to implement |

## Alternatives Considered

### A. Client-side marker dedup (post-hoc)
Write `webhook_sent:{id}:failure` to Redis after the webhook returns 200. Other paths check before sending.

**Rejected:** still has a race window (SIGKILL between HTTP 200 and marker `SET`). Eliminates most duplicates but not all. User requires zero duplicates.

### C. Persist-first-remove-on-success queue (no idempotency)
Write pending callback to Redis before sending; remove after success. On startup, replay pending.

**Rejected:** same race as A at the "remove" step. Plus requires building a startup replay worker. More code, same outcome.

### D. Delegate entirely to reconciliation (no shutdown webhook)
Skip the webhook during shutdown. Reconciliation handles it.

**Rejected:** 10-minute delay until `STALE_JOB_THRESHOLD_REMOTE` triggers. Bad UX for the caller.

## Future Extensions

1. Extend `request_id` pattern to success and stop webhooks if duplicate scenarios emerge for those types.
2. After PHP-side dedup is in place, could shorten `STALE_JOB_THRESHOLD_REMOTE` since duplicate webhooks are now harmless.
3. Emit a Prometheus metric `webhook_duplicate_detected_total` from PHP (once idempotency is live) to observe dedup rate.
