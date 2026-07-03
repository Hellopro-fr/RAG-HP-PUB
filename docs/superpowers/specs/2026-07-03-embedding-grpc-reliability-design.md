# Embedding gRPC reliability: unblock ChunkText + shared channel + liveness deadlines — Design

**Date:** 2026-07-03
**Status:** Approved (scope), C3 deferred
**Scope:** `embedding-model-service` (server ChunkText), `libs/common-utils` (gRPC client channel), `docker-compose.yml` (embedding-service env). No Triton/model change.

## Context

Follow-up to the livelock fix (`e589cf5d`). After deploy, the pipeline showed two residual client-side gRPC errors: `CANCELLED` and `DEADLINE_EXCEEDED`. The user asked to root-cause them rather than tune another knob.

## Evidence (24h, production)

Model-service (`docker compose logs embedding-model-service`):
- Real errors (GetEmbeddings/Triton/worker): **0**. Triton logs clean. → server + GPU healthy.
- `Génération terminée avec succès`: **23003** → work completes.
- `annulée par le client`: **187** (server-observed client give-ups).

Consumer (`embedding-service`), `Erreur gRPC en appelant le service …`, deadline|cancelled:
- Total **833** — split: **ChunkText 484**, GetEmbeddings 335. By type: **deadline 709**, cancelled 106.

`temps_embedding.log` (GetEmbeddings round-trip, consumer side, n=7439): p50 0.25s, p95 23.5s, p99 36.6s, **max 109.0s** — censored at `GRPC_TIMEOUT=110`, so the true tail exceeds 110s.

## Root cause (two independent causes)

1. **ChunkText blocks the model-service event loop (dominant, 484).** `grpc_server.py:81` calls `self.use_case.chunk_text(...)` synchronously inside the async servicer. `chunk_text` (`embedding_use_case.py:539-549`) runs `RecursiveCharacterTextSplitter` whose `length_function` calls the HF tokenizer per candidate split — hundreds/thousands of synchronous encodes for a big page, on the event-loop thread. While it runs, every concurrent RPC (other ChunkTexts *and* GetEmbeddings) is frozen → cascading deadlines across both RPCs. GetEmbeddings, by contrast, already offloads its heavy CPU via `run_in_executor`.
2. **Client channel lifecycle + too-tight deadline (335 + 106).** `embedding_client.py` opens a fresh `async with grpc.aio.insecure_channel(...)` per call; teardown under an in-flight RPC (outer `PROCESS_TIMEOUT` cancel, or task cancel) terminates it `CANCELLED`. And `GRPC_TIMEOUT=110` sits inside the real completion band (censored max 109s), so legitimately-large pages breach it → `DEADLINE_EXCEEDED`, which retries re-embed (duplicate server work, inflating the 23003).

The 833 vs 187 gap is explained: most client give-ups **race the server to completion** (server logs success, counted in 23003; client already raised the error) or are ChunkText (no server "annulée" log). Confirms the work completes server-side; the client abandons/duplicates it.

## Decisions

### S1 — Offload ChunkText (server)
In `grpc_server.py` `ChunkText`, replace the synchronous call with:
```python
loop = asyncio.get_running_loop()
chunks = await loop.run_in_executor(
    None,
    functools.partial(self.use_case.chunk_text, request.text, request.chunk_size, request.chunk_overlap),
)
```
- Default executor (`None`): isolated from the embedding path's `_high_executor`/`_default_executor`; nothing else in the process uses the default executor, so ChunkText gets it exclusively.
- `chunk_text` unchanged (pure function). Adds `import asyncio`, `import functools` if absent.
- Rationale for `None` over a dedicated pool: KISS. If chunk concurrency ever needs bounding, add a dedicated `ThreadPoolExecutor` later (`# ponytail:` marker).

### C1 — Shared persistent channel (common-utils)
In `embedding_client.py`, replace per-call channels with a module-level lazily-created singleton:
- A `_get_channel()` helper creates `grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL, options=[...keepalive...])` on first call (inside a running loop — grpc.aio channels bind to their loop; creating at import has no loop) and caches it in a module global.
- All 5 functions (`get_embeddings`, `get_embedding`, `tokenize`, `detokenize`, `chunk_text`) use `_get_channel()` + a per-call stub; no `async with` teardown.
- Keepalive options: `grpc.keepalive_time_ms`, `grpc.keepalive_timeout_ms`, `grpc.keepalive_permit_without_calls` — so an idle persistent channel stays healthy and detects dead peers.
- Error handling unchanged: `get_embeddings`/`chunk_text` still re-raise `AioRpcError` (transient → retry); tokenize/detokenize still graceful-empty.
- A `_reset_channel_for_tests()` (or module-global reset) keeps tests hermetic (each fresh event loop needs a fresh channel).

### C2 — Liveness deadlines (embedding-service compose env)
`GRPC_TIMEOUT` 110→**300**, `PROCESS_TIMEOUT` 240→**360**. Conservative upper liveness bounds above the censored tail; re-measure and lower after S1 unblocks the loop. Single `GRPC_TIMEOUT` covers chunk+embed (chunk won't approach it once non-blocking).

**Ordering assumption:** `PROCESS_TIMEOUT=360` keeps the gRPC deadline as the primary failure path (fires before the outer cap) *only because S1 makes ChunkText sub-minute* — realistic worst case is chunk (~seconds, off-loop) + embed (≤300) + publish ≈ 310 < 360. It does NOT preserve the old strict `PROCESS_TIMEOUT > 2×GRPC_TIMEOUT` invariant (that would need 600, too long a slot-hold). If post-deploy a pathological page makes both chunk AND embed run long and the outer cap fires (a CANCELLED reappears), the fix is a separate, smaller per-call chunk deadline — deferred until observed, not built preemptively.

### C3 — DEFERRED
Retry backoff+jitter needs a RabbitMQ topology change (immutable per-queue TTL → tiered retry queues). S1+C2 are expected to slash the error count and shrink the retry herd; add C3 only if residual herding is observed post-deploy.

## Components

| # | File | Change |
|---|------|--------|
| S1 | `apps-microservices/embedding-model-service/infrastructure/grpc_server.py` | `ChunkText` offloads `chunk_text` to `run_in_executor(None, ...)`; add `asyncio`/`functools` imports |
| C1 | `libs/common-utils/src/common_utils/grpc_clients/embedding_client.py` | module-level lazy shared channel + keepalive; 5 funcs reuse; test reset helper |
| C2 | `docker-compose.yml` | embedding-service env `GRPC_TIMEOUT=300`, `PROCESS_TIMEOUT=360` |
| tests | `embedding-model-service/tests/`, `libs/common-utils/tests/` | S1 offload + C1 single-channel-reuse (grpc/aio_pika faked in sys.modules, file-path module load) |

## Error handling

Unchanged classification. S1 changes *where* chunking runs, not its result or errors. C1 preserves the re-raise/graceful-empty split per function. C2 moves timeout boundaries only.

## Testing

- **S1**: mock `loop.run_in_executor`, assert `ChunkText` awaits it with the `chunk_text` partial and returns its chunks (proves offload, not on-loop execution).
- **C1**: patch `grpc.aio.insecure_channel` to count calls; assert **one** channel across N calls of mixed functions; assert all 5 build stubs from the shared channel; assert keepalive options passed. Reset the module channel between tests.
- Local constraint: `grpc`, `grpc_stubs`, `aio_pika` absent → fake in `sys.modules` (try-real-import-first), load modules by file path. Authoritative typecheck = Docker build on VM.

## Verify on deploy

1. ChunkText timeouts: `docker compose logs embedding-service | grep "service de Chunking" | grep -ciE "deadline|cancelled"` → expect ≈0.
2. CANCELLED: `grep -ci cancelled` → expect ≈0.
3. GetEmbeddings deadline: much reduced; re-check `temps_embedding.log` max no longer pinned at the deadline.
4. If retry herding persists → open C3.

## Rollback

C2 = env revert + restart. S1/C1 = revert commits + image rebuild. No data migration, no schema.

## Blast radius

- S1: `embedding-model-service` only → rebuild that image.
- C1: `libs/common-utils` → every embedding consumer (api-recherche, graph-rag-*, api-embedding-service, embedding-service). Shared channel is the gRPC-recommended pattern and backward-compatible; rebuild all embedding-consuming images.
- C2: `embedding-service` env only.
