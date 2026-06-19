# Design — image-comparison-service: per-URL feature/pHash cache (Design C)

**Date:** 2026-06-18
**Status:** Validated (design)
**Author:** Rindra + Claude
**Scope:** "Design C" — a server-side, per-image-URL cache of the extracted comparison **feature** (`pHash` + HSV histogram), to cut redundant image **downloads** (NetIO ~5-6 GB/replica + paid Apify-proxy bandwidth) and the decode/extract CPU across comparison jobs. Separate from the merged **Design 1** (bounded downloads + per-job timeout + backpressure) and the merged **cache_service migration**.
**Service:** `apps-microservices/image-comparison-service` (RAG-HP-PUB), branch `features/poc`.

---

## 1. Objective

The same source image URL (`image_scrapping_ia.url_image_isi`) is downloaded and feature-extracted repeatedly: across different pages of one domain (shared logos/boilerplate), and — the dominant case — across **re-runs** of `6_rescore_images.php`, which is designed to be re-run (after MEP, to test a new algo, or via the Phase-2bis `dedup_perceptual` checkbox) and re-downloads every URL each time. Each comparison job currently re-downloads + re-decodes + re-hashes every image, even when the feature is already known.

**Goal:** cache the per-URL feature so a cache hit skips the network download, the decode, and the feature extraction entirely. Win is both latency and **paid proxy bandwidth** (when `APIFY_PROXY` is set). The cache lives on the shared Redis → it is shared across all replicas automatically.

## 2. Context (verified, this session)

- **What is cacheable — the feature, not the bytes.** `ImageProcessor.load_images()` downloads bytes (httpx) → decodes to `PIL.Image` (RGB) → `trim_borders()` → returns `{id: PIL.Image}`. Features are computed *later*, inside `compare_batch` (which runs in a worker thread via `anyio.to_thread.run_sync`) by `extract_features(pil_image)` → `{'phash': imagehash.ImageHash, 'hist': numpy.float32[512]}`. Comparison (`calculate_similarity`) reads **only** those two feature keys. So caching the feature dict per URL lets the service skip download + decode + extract on a hit. (`image_processor.py`: `load_images` ~L90-214, `extract_features` L216-243, `calculate_similarity` L246-285.)
- **Feature is threshold-independent.** The request `threshold` (default 90.0) is applied *after* compare (`job_manager.py` ~L148: `if res['score'] >= threshold`). The feature is identical for any threshold → the cache key excludes threshold, and a cached feature is valid across all callers/thresholds.
- **URL is a stable identity.** Each `ImageInput` derives a deterministic id `uuid5(NAMESPACE_URL, str(url))` when `id` is not supplied (`comparator.py` L16-19); `url` is a pydantic `HttpUrl` (canonicalised by `str()`). Callers MAY override `id`, so the cache MUST key on the URL, not on `inp.id`.
- **URL-stability data (live, `image_scrapping_ia`, 124,729 source URLs):** 28% carry a query string, 16% carry a cache-buster-like param, 65 distinct hosts. Decisive nuance: the **rescore re-run** win reads the *same stored* `url_image_isi` rows, so URLs are stable across re-runs regardless of cache-busters; cache-busters only fragment cross-*re-crawl* reuse, and a content-hash param self-invalidates (helps correctness). → URL is a sound key with strong hit potential.
- **Downstream safety (the correctness surface).** The service NEVER deletes; it returns `similar_pairs` (score ≥ threshold). The BO caller (`dedupePerceptual` in `extraction_images_pages/dedup_perceptual_lib.php`; `dedupeImageVariants` N3 in `fonctions_extraction_images_pages.php`) turns `similar_pairs` → `rejected_ids` → `est_pertinent_isi=0` (`6_rescore_images.php` ~L707-718) — a **logical, re-runnable exclusion**, NOT a row/file delete. Blast radius is bounded to one `(id_domaine, url_page_source)` page bucket (plus, for N3, the same pattern-normalised key). Every failure mode on the caller side already degrades to **keep-all** (timeout/empty/404/failed/breaker-open/oversize → never deletion).
- **Infra.** Redis is an **external, managed, shared** instance (~30 services); no `redis:` service, no `maxmemory`/policy in the repo → unknown eviction. Client `decode_responses=True` (text only — no raw bytes/pickle). Bounded pool `max_connections=20`/replica, `socket_timeout=10`. `MAX_CONCURRENT_JOBS=4`. Existing Redis keys: `job:{id}:status|result` (TTL `JOB_RESULT_TTL=86400`), `comparator:running_count`. No URL/feature/content cache exists today.
- **cache_service helpers** (`libs/common-utils/src/common_utils/redis/cache_service.py`): module-global `redis_client` (accessed at call time as `cache_service.redis_client` — never `from … import redis_client`, the global is rebound by `init_redis_pool`). `set_json(key, data, ttl)` / `get_json(key)` use `json.dumps(default=str)` (lossy for ImageHash/numpy → custom serialization required). `scan_keys_by_prefix`, `safe_decrement_key`, `delete_if_terminal` available. All helpers swallow exceptions (get returns None on miss OR error — indistinguishable).

## 3. Design

### 3.1. Decision summary (validated)
| Decision | Choice |
|---|---|
| Staleness policy | **Plain bounded TTL, cache-aside, NO per-request revalidation** (Option A). |
| TTL | **7 days** (604800 s) — catches cross-page + same-run + near-term rescore re-runs; expires before a weeks-later algo re-run could serve stale. Env-tunable. |
| What to cache | The full feature dict `{phash, hist}` (BOTH — `hist` feeds the smart-identity rule and the weighted score; dropping it would change verdicts or require the download). |
| Cache key | `imgfeat:v1:{uuid5(NAMESPACE_URL, str(url))}` — URL-only, threshold-excluded, `v1` = algo version. |
| Store | Shared external Redis via `cache_service` (cross-replica reuse). |
| Approach | Per-URL feature cache, cache-aside; split `extract` from `compare`. NOT a bytes cache (Redis size), NOT in-process LRU (no cross-replica/cross-rerun sharing). |
| Surface | **Server-side only** — zero BO change, zero API-contract change. |

### 3.2. New module `app/core/feature_cache.py` (single responsibility)
- `feature_key(url: str) -> str` → `f"imgfeat:{settings.FEATURE_CACHE_VERSION}:{uuid.uuid5(uuid.NAMESPACE_URL, url)}"`.
- `serialize_feature(feature: dict) -> str` → JSON `{"phash": str(feature['phash']), "hist": feature['hist'].tolist()}`.
- `deserialize_feature(raw: str) -> dict | None` → `{'phash': imagehash.hex_to_hash(...), 'hist': np.array(..., dtype=np.float32)}`; returns `None` (treated as miss) on any parse/shape error.
- `async get_features(urls: list[str]) -> dict[str, dict]` → short-circuit `return {}` when `not settings.FEATURE_CACHE_ENABLED`; else guarded `if cache_service.redis_client:`; one **MGET** over the keys; deserialize each; skip `None`/errors. Returns `{url: feature}` for hits only. On `RedisError`/no client → returns `{}` (all miss).
- `async set_features(url_to_feature: dict[str, dict]) -> None` → short-circuit no-op when `not settings.FEATURE_CACHE_ENABLED`; else guarded; one **pipelined SET … EX FEATURE_CACHE_TTL_S** per entry; swallow `RedisError`.
- All paths degrade to "miss" — never raise into the job. The kill-switch lives entirely in these two functions, so `FEATURE_CACHE_ENABLED=false` makes `process_job_logic` download+extract every image exactly as today (get→`{}`→all miss; set→no-op).

### 3.3. `image_processor.py` — split extract from compare
- Keep `extract_features` as-is.
- Refactor `compare_batch` into a thin pipeline so the pairwise comparison consumes a **ready feature-map** instead of extracting internally: add `compare_features(feature_map: dict[id, feature], threshold-independent pairwise)` (the existing pairwise logic, unchanged math), and keep an `extract_features_for(images: dict[id, PIL.Image]) -> dict[id, feature]` helper for the miss path. `compare_batch`'s current callers get the same result; the math (`calculate_similarity`, smart-identity, weighting) is **unchanged**.

### 3.4. `job_manager.process_job_logic` — orchestration (cache-aside)
1. Partition inputs: `url` inputs (cacheable) vs base64 `content` inputs (bypass — no key).
2. `cached = await feature_cache.get_features([url for each url-input])` → map back to `id` via the `url→id` map.
3. `miss_inputs` = url-inputs not in `cached` **+ all content inputs**.
4. `images, failed = await load_images(miss_inputs)` (reuses Design-1 bounded download) → PIL images for misses only.
5. In the worker thread: `fresh = extract_features_for(images)`.
6. `await feature_cache.set_features({url: fresh_feature for url-misses})` (content inputs not cached).
7. `compare_features({**cached, **fresh})` → identical pairwise scores → identical `similar_pairs`/result.
- The per-image `failed` list (Design-1) still routes only download/decode failures; cache misses are not failures.

### 3.5. Config (`app/core/config.py`, env-tunable)
| Setting | Default | Notes |
|---|---|---|
| `FEATURE_CACHE_ENABLED` | `true` | Kill-switch — when false, behaviour is exactly today's (download+extract all). |
| `FEATURE_CACHE_TTL_S` | `604800` | 7 days. Sole staleness guardrail. |
| `FEATURE_CACHE_VERSION` | `v1` | Bump when `trim_borders`/`extract_features` change → old entries ignored. |

## 4. Behavior preservation / contract
- **API contract unchanged:** `/start` (`sync`/async), `/status`, `/results`, `/capacity`, `/jobs`; keys `job:{id}:status|result`; TTL `JOB_RESULT_TTL`; the request/result JSON shapes. The cache adds only new `imgfeat:v1:*` keys.
- **Scores byte-identical:** a cache hit reconstructs the exact `{phash, hist}` (deterministic given the same downloaded+trimmed image) → identical `calculate_similarity` output → identical `similar_pairs`. The `v1` version tag guarantees a cached feature was produced by the *current* algorithm.
- **Safety floor intact:** cache miss / Redis error / deserialize failure → fall through to real download+extract; eviction is safe (cache-aside); the BO keep-all-on-uncertainty path is untouched. A stale-but-present feature (image swapped in place within the 7d window) is the only residual risk — bounded (logical re-runnable exclusion, same-page bucket) and accepted.
- **Pool safety:** one MGET + one pipelined SET batch per job (not N sequential awaits) under pool=20 / 4 concurrent jobs.
- **Cross-replica:** shared Redis → features cached by any replica are reused by all; writes idempotent (deterministic pHash, last-writer-wins correct).

## 5. Verification (remote — RAG-HP-PUB)
- `python -m py_compile app/core/feature_cache.py app/core/image_processor.py app/core/job_manager.py app/core/config.py`.
- Unit (if a harness exists; the seams are pure-function-testable): serialize⇄deserialize round-trip preserves pHash Hamming distance and `cv2.compareHist` correlation (rebuilt `hist` must be contiguous `float32`); `compare_features` on a hand-built feature-map equals the pre-refactor `compare_batch` output; `get_features` with no Redis client → `{}` (degrades to miss); deserialize of corrupt JSON → treated as miss.
- `docker build` on the VM (user).
- Smoke (deploy): run the same job twice → 2nd run logs cache hits + near-zero NetIO; `similar_pairs` byte-identical to the `FEATURE_CACHE_ENABLED=false` run; `scan imgfeat:v1:*` shows entries with a ~7d TTL; flip the kill-switch → behaviour reverts to download-all.

## 6. Blast radius / out of scope
- **image-comparison-service only.** No BO change, no API-contract change → Ch.D dedup (`dedupePerceptual`/`dedupeImageVariants`) and the FP arsenal are unaffected. The only new footprint is `imgfeat:v1:*` keys on the shared Redis (small, TTL'd, eviction-safe).
- **Out of scope:** conditional revalidation (HEAD/ETag — Option B, rejected); a raw-bytes cache; an in-process LRU; `MAX_CONCURRENT_JOBS` tuning; any BO-side caching.
- **Follow-ups (separate):** if the shared-Redis memory budget proves tight, base64-pack the histogram (`float32` bytes, ~2.7 KB vs ~4 KB JSON) or int-quantise it; characterise real hit-rate from logs after deploy to decide whether the histogram reuse justifies its size.

---

**End design — 2026-06-18.**
