# content-extractor-api-service

REST API exposing boilerpy3 HTML cleaning and HeaderFooterExtractor for external teams, internal services, and ad-hoc usage.

## Tech Stack

- Python 3.10 / FastAPI / Uvicorn (multi-worker via `UVICORN_WORKERS`)
- boilerpy3 (HTML cleaning)
- common-utils (HeaderFooterExtractor, Redis `cache_service`)
- Redis (async job store + result cache — **required for async, optional for sync**)
- Prometheus metrics

> **CPU offload:** all extraction (boilerpy3 + the 706-line BeautifulSoup `HeaderFooterExtractor`) is CPU-bound and runs via `asyncio.to_thread` so the event loop never blocks. The GIL means real parallelism comes from **processes** (`UVICORN_WORKERS` × replicas), not threads.

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/clean` | POST | boilerpy3 HTML cleaning (text or HTML output). Cached + non-blocking; may return `503 + Retry-After` when `SYNC_MAX_INFLIGHT` exceeded |
| `/extract/header-footer` | POST | Header/footer extraction with optional debug mode. Cached + non-blocking; same `503` admission as `/clean` |
| `/clean-async` | POST | Submit a **batch** of clean items → `202 {job_id}` (or `200` idempotent re-submit). Poll `/jobs/{job_id}` |
| `/extract/header-footer-async` | POST | Submit a **batch** of header/footer items → `202 {job_id}`. Poll `/jobs/{job_id}` |
| `/jobs/{job_id}` | GET | Poll an async job: `pending\|running\|completed\|failed\|stale`; `results` present at terminal; `404` when unknown/expired |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Async Job API + Result Cache

Batched async endpoints (for heavy consumers like the future 7-replica `crawler-service`) backed by an in-process asyncio worker + Redis job store (`app/core/async_jobs.py`), wired via a FastAPI `lifespan` in `main.py` (`app.state.job_manager`). The worker reuses the same `extractor_service.run_batch` core as the sync path (DRY). Design: `docs/superpowers/specs/2026-06-20-content-extractor-async-cache-design.md`; plan: `docs/superpowers/plans/2026-06-20-content-extractor-async-cache.md`.

- **Submit** (`POST /clean-async` | `/extract/header-footer-async`, body = `{items[], max_concurrency?, force_refresh?, client_job_id?}`): `202 {job_id, status, total, poll_after_seconds}`. With `client_job_id` set, a re-submit returns the existing job (`200`, atomic `SET NX` idempotency).
- **Poll** (`GET /jobs/{job_id}`): `{job_id, job_type, status, total, done, results?, error?, poll_after_seconds}`. `results` are **order-aligned with the submitted items**; per-item failures surface as `{"error": ...}` in that slot (the job is not failed wholesale). `stale` is computed on read (heartbeat older than `STALE_THRESHOLD_S` → dead worker).
- **503 discriminator** (callers read the header, not the body): capacity (`MAX_ACTIVE_JOBS` reached) → **`Retry-After` present** (retry); kill-switch (`ASYNC_JOBS_ENABLED=false`) or Redis unavailable → **no `Retry-After`** (do not retry).
- **Redis keys:** `extract:job:{job_id}` (record), `extract:jobidx:{client_job_id}` (idempotency), `extract:{clean|hf}:{RESULT_CACHE_VERSION}:{sha256(...)}` (result cache). Soft global cap = `MAX_ACTIVE_JOBS × workers × replicas` (no hard cap by default).
- **Result cache** (sync + async): versioned content-hash, 24h TTL, **graceful-degrade** — guards on `cache_service.redis_client` before the bare helpers (which raise without a client), so Redis-absent falls back to compute and never raises. Header/footer keys sort references only when `debug=False` (debug responses carry order-dependent fields). Bump `RESULT_CACHE_VERSION` on any extractor/boilerpy3 change.
- **Sync admission** (`SYNC_MAX_INFLIGHT`, default `0` = off): in-process guard; on saturation returns `503 + Retry-After` instead of queueing into a timeout.

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8600
```

## Test

```bash
python -m pytest tests/ -v
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8600` | Service port |
| `LOG_LEVEL` | `"info"` | Logging level |
| `MAX_PAYLOAD_SIZE_MB` | `10` | Max request body size (applies to async batch bodies too — callers chunk) |
| `UVICORN_WORKERS` | `2` | Worker processes per replica (CPU parallelism lever) |
| `REDIS_URL` | `redis://redis:6379` | Job store + result cache. Absent → async `503`; sync degrades cache-less |
| `RESULT_CACHE_ENABLED` | `true` | Result cache kill-switch |
| `RESULT_CACHE_TTL_S` | `86400` | Result cache TTL (24h) |
| `RESULT_CACHE_VERSION` | `v1` | Bump to invalidate cache on extractor/boilerpy3 change |
| `SYNC_MAX_INFLIGHT` | `0` | Sync admission cap (`0` = disabled) |
| `ASYNC_JOBS_ENABLED` | `true` | Async API kill-switch (`false` → submit `503`, no `Retry-After`) |
| `MAX_ACTIVE_JOBS` | `8` | Per-worker in-flight async jobs (capacity `503` + `Retry-After` beyond) |
| `DEFAULT_MAX_CONCURRENCY` | `4` | Default per-job item concurrency |
| `JOB_TTL_ACTIVE_S` | `7200` | TTL of a pending/running job record (heartbeat-refreshed) |
| `JOB_RESULT_TTL_S` | `3600` | TTL of a terminal job record (poll window) |
| `STALE_THRESHOLD_S` | `120` | No-heartbeat window after which poll reports `stale` |
| `HEARTBEAT_INTERVAL_S` | `5` | Heartbeat tick |
| `ASYNC_SUBMIT_RETRY_AFTER_S` | `15` | `Retry-After` value on capacity `503` (sync admission reuses it) |
| `ASYNC_POLL_HINT_MAX_S` | `30` | Upper bound on the `poll_after_seconds` hint |
| `SHUTDOWN_GRACE_S` | `5` | Bound on `JobManager.shutdown()` task drain |

## Dependencies

- **Redis required for the async API** (job store); **optional for sync** (result cache degrades gracefully when absent). No RabbitMQ, no SQL database.
- Sits behind `api-gateway` for auth (gateway downstream timeout key: `extractor-service`, 60s).
- Imports `HeaderFooterExtractor` + Redis `cache_service` from `libs/common-utils`.

## What This Provides to Other Services

- On-demand HTML content extraction without going through the RabbitMQ pipeline
- Header/footer detection API for external consumers
- Batched async submit→poll API + Redis result cache for high-volume consumers (e.g. the future replicated `crawler-service`)
