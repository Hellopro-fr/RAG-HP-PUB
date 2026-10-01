# Embedding-service livelock: budget realignment + backpressure — Design

**Date:** 2026-07-02
**Status:** Approved
**Scope:** `apps-microservices/embedding-service` (consumer tunables) + `docker-compose.yml` (env). No shared-lib change, no model-service change.

## Context

Follow-up to the fail-fast fix (commit `1cc8c203`: `chunk_text` re-raises `AioRpcError`; `GRPC_TIMEOUT=45` on embedding-service). Fail-fast works as designed, but after deploy the pipeline shows **zero progression**: every message fails at the 45s gRPC deadline, returns via the 30s retry queue, and fails again — a retry livelock.

## Diagnosis (evidence-based)

Model-service arrival-time queue depths over 30 min (`[Queues -> H:x, M:y, L:z]`, `embedding_use_case.py:507`):

```
 87 H:0, M:0, L:1    19 H:0,M:0,L:2    10 H:0,M:0,L:3    ... max L:14
```

- `H≈0` throughout → **not** starvation by HIGH search traffic.
- `L` shallow (1–3 typical, 14 max) → **not** queue congestion; a queue this shallow clears in seconds.

Therefore the 45s deadline is consumed **inside processing**, not queue wait. Credible mechanism: large payloads (crawled pages → hundreds of chunks) are internally sliced into 64-text Triton batches; each batch acquires the non-HIGH `Semaphore(3)` **shared with all other concurrent requests' batches** (up to 40 in-flight: 4 replicas × prefetch 10). A fat message legitimately needs 45–120s — consistent with the pre-fix behavior where some messages completed at the old 120s cap ("sometimes pass on requeue"). Setting the deadline to 45s cut *into* the completion band, making large messages fail deterministically. GPU contention at Triton (embedding shares the GPU with reranker/LLM) is a possible aggravator, below this measurement's visibility.

## Decisions

1. **`GRPC_TIMEOUT` 45 → 110** (compose env, embedding-service only). Restores the observed completion band while keeping the fail-fast contract: the per-RPC deadline still fires before the outer cap, producing a clean retryable `DEADLINE_EXCEEDED` (requires the `chunk_text` re-raise already shipped in `1cc8c203`).
2. **Outer per-message timeout 120 → 240, env-driven** (`PROCESS_TIMEOUT`, default 240, read in `consumer.py`). Must stay > one full attempt: worst case is both RPCs hitting the deadline (ChunkText 110s + GetEmbeddings 110s = 220s) plus publish; 240 covers that with margin, so the gRPC deadline — not the outer cap — remains the primary failure path.
3. **`prefetch_count` 10 → 2, env-driven** (`PREFETCH_COUNT`, default 2, read in `consumer.py`). 4 replicas × 2 = 8 in-flight against 3 non-HIGH Triton slots. Purpose: *Semaphore-contention relief* — fewer concurrent requests means each request's batches acquire slots sooner, directly shortening per-request service time. Also thins the 30s retry herd.
4. **Both new tunables are env vars** so the next tuning round is a compose edit + restart, no image rebuild.

## Components

| # | File | Change |
|---|------|--------|
| 1 | `apps-microservices/embedding-service/app/messaging/consumer.py` | `PREFETCH_COUNT = int(os.getenv("PREFETCH_COUNT", "2"))` used in `set_qos`; `PROCESS_TIMEOUT = float(os.getenv("PROCESS_TIMEOUT", "240"))` used in `asyncio.wait_for`. Timeout log strings reference the actual value instead of a hardcoded "120s". |
| 2 | `docker-compose.yml` (embedding-service env) | `GRPC_TIMEOUT` 45 → 110; add `PREFETCH_COUNT=2`, `PROCESS_TIMEOUT=240` (explicit, self-documenting). |
| 3 | `apps-microservices/embedding-service/tests/` | Unit tests for the two env reads + the wait_for/QoS wiring (mocked aio_pika; no live RabbitMQ). |

DLQ reason string changes from `"Timeout de traitement (>120s)"` to the dynamic value (e.g. `">240s"`). Operators filtering the DLQ on the literal string must match the prefix `"Timeout de traitement"` only (the existing `dlq_requeuer` filter recommendation already does).

## Error handling

Unchanged. Classification stays: `ValueError`/`JSONDecodeError` permanent → DLQ; gRPC/`TimeoutError` transient → ≤3 retries → DLQ. This design only moves the *boundaries* (when timeouts fire), not the *routing*.

## Verify on deploy

1. Cancellation count should collapse: `docker compose logs --since 30m embedding-model-service | grep -c "annulée par le client"` (before vs after).
2. Durations: `docker compose exec embedding-service sh -c "tail -50 /logs/temps_embedding.log"` — expect the bulk < 110s.
3. RabbitMQ `embedding_queue` + `embedding_queue_retry` depths trending down; DLQ inflow ≈ 0 for the timeout reason.

## Deferred (Phase 2 — only if step-2 durations show tails > 110s)

Per-retry timeout ladder (first attempt 45s → retry 110s → final 300s): small messages stay snappy, only whales get patience. Requires threading a per-call timeout through `Embedding` → `embedding_client`. Not built until the tail is proven to exist.

## Rollback

Compose env revert + restart (no code path depends on the new values; defaults are baked as the chosen numbers).
