# Image-Comparison Feature Cache (Design C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-side, per-image-URL cache of the extracted comparison feature (`pHash` + HSV histogram) so a cache hit skips the image download, decode, and feature extraction — cutting NetIO/paid-proxy cost across jobs and `6_rescore` re-runs.

**Architecture:** Cache-aside on the shared Redis via `common_utils.redis.cache_service`. A new focused module `feature_cache.py` owns serialize⇄Redis (guarded, degrades to miss, never raises). `image_processor` is split so the pairwise comparison consumes a ready feature-map (`compare_features`) decoupled from extraction (`extract_features_for`). `job_manager.process_job_logic` orchestrates: MGET cached features → download+extract only misses → pipelined SET fresh → compare the merged map. Scores stay byte-identical; the API contract is unchanged; the only new Redis footprint is `imgfeat:<version>:*` keys with a bounded TTL.

**Tech Stack:** Python 3.11, FastAPI, redis.asyncio (shared `cache_service`), Pillow, imagehash, OpenCV (`cv2`), numpy, anyio.

**Spec:** `docs/superpowers/specs/2026-06-18-image-comparison-feature-cache-design.md`

**Branch / repo:** RAG-HP-PUB, off `features/poc` (tip has Design-1 merge `27019ebd` + spec `379187a7`). Execute in a worktree. Commits bilingual EN+FR, one per task, **no push**. Remote-only verify = `python -m py_compile`; `docker build` + deploy smoke = user on the VM.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `app/core/config.py` | 3 env-tunable cache knobs (enable / TTL / version) | T1 |
| `app/core/feature_cache.py` (**new**) | serialize⇄deserialize feature ⇄ Redis; guarded MGET get / pipelined SET; kill-switch; degrade-to-miss | T2 |
| `app/core/image_processor.py` | split `compare_batch` → `extract_features_for` + `compare_features` (math unchanged) | T3 |
| `app/core/job_manager.py` | `process_job_logic` cache-aside orchestration | T4 |
| `tests/test_feature_cache.py` (**new, optional**) | round-trip + degrade-to-miss unit tests (run on VM where deps exist) | T2 |

---

### Task 1: Config knobs

**Goal:** Add 3 env-tunable settings for the feature cache — no behavior change (nothing reads them yet).

**Files:**
- Modify: `apps-microservices/image-comparison-service/app/core/config.py`

**Acceptance Criteria:**
- [ ] `FEATURE_CACHE_ENABLED` (bool, default `True`), `FEATURE_CACHE_TTL_S` (int, default `604800`), `FEATURE_CACHE_VERSION` (str, default `"v1"`) added to `Settings`, each via `os.getenv` with a default.
- [ ] `FEATURE_CACHE_ENABLED` parses common truthy/falsy strings (so `FEATURE_CACHE_ENABLED=false` disables it).
- [ ] `python -m py_compile` clean; no other setting changed.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/config.py` → no output (success).

**Steps:**

- [ ] **Step 1: Add the knobs after the Design-1 block, before `settings = Settings()`**

In `app/core/config.py`, the current tail is:

```python
    # Async-submit backlog cap = MAX_CONCURRENT_JOBS * ASYNC_BACKLOG_FACTOR (per replica).
    ASYNC_BACKLOG_FACTOR: int = int(os.getenv("ASYNC_BACKLOG_FACTOR", "4"))

settings = Settings()
```

Replace it with:

```python
    # Async-submit backlog cap = MAX_CONCURRENT_JOBS * ASYNC_BACKLOG_FACTOR (per replica).
    ASYNC_BACKLOG_FACTOR: int = int(os.getenv("ASYNC_BACKLOG_FACTOR", "4"))

    # --- Per-URL feature cache (Design C) ---
    # Cache-aside store of the extracted feature {phash, hist} keyed by image URL, on the
    # shared Redis. A hit skips download+decode+extract. Eviction is safe (miss -> recompute);
    # TTL is the SOLE staleness guardrail against a URL whose bytes change in place.
    FEATURE_CACHE_ENABLED: bool = os.getenv("FEATURE_CACHE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    # 7 days. Bounds the wrongful-exclusion window; expires before a weeks-later algo re-run.
    FEATURE_CACHE_TTL_S: int = int(os.getenv("FEATURE_CACHE_TTL_S", "604800"))
    # Algorithm version tag in the cache key. Bump when trim_borders / extract_features change
    # so old (incompatible) cached features are ignored rather than mixed in.
    FEATURE_CACHE_VERSION: str = os.getenv("FEATURE_CACHE_VERSION", "v1")

settings = Settings()
```

- [ ] **Step 2: Verify**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/config.py`
Expected: success (no output).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/image-comparison-service/app/core/config.py
git commit -m "feat(image-comparison): add feature-cache config knobs (enable/TTL/version)" \
  -m "EN: Add FEATURE_CACHE_ENABLED (true), FEATURE_CACHE_TTL_S (604800=7d), FEATURE_CACHE_VERSION (v1) via os.getenv with defaults. No behavior change yet (nothing reads them)." \
  -m "FR: Ajoute FEATURE_CACHE_ENABLED (true), FEATURE_CACHE_TTL_S (604800=7j), FEATURE_CACHE_VERSION (v1) via os.getenv avec defauts. Aucun changement de comportement (rien ne les lit encore)."
```

```json:metadata
{"files":["apps-microservices/image-comparison-service/app/core/config.py"],"verifyCommand":"python -m py_compile apps-microservices/image-comparison-service/app/core/config.py","acceptanceCriteria":["3 settings via os.getenv w/ defaults","FEATURE_CACHE_ENABLED parses truthy/falsy strings","py_compile clean","no behavior change"]}
```

---

### Task 2: `feature_cache.py` module

**Goal:** A self-contained module that serializes the feature ⇄ JSON text, keys it by URL, and reads/writes Redis through `cache_service` — guarded, kill-switch-aware, and degrading every failure to a cache miss (never raising into a job).

**Files:**
- Create: `apps-microservices/image-comparison-service/app/core/feature_cache.py`
- Create (optional, VM-run): `apps-microservices/image-comparison-service/tests/test_feature_cache.py`

**Depends on:** Task 1 (reads `settings.FEATURE_CACHE_*`).

**Acceptance Criteria:**
- [ ] `feature_key(url)` → `f"imgfeat:{settings.FEATURE_CACHE_VERSION}:{uuid.uuid5(uuid.NAMESPACE_URL, url)}"`.
- [ ] `serialize_feature(feature)` → JSON string `{"phash": <16-hex>, "hist": [<512 floats>]}`.
- [ ] `deserialize_feature(raw)` → `{"phash": imagehash.ImageHash, "hist": np.float32 ndarray}`; returns `None` on ANY error.
- [ ] `get_features(urls)` async → `{url: feature}` for hits only; one MGET; returns `{}` when disabled / no client / RedisError / empty input.
- [ ] `set_features(url_to_feature)` async → one pipelined SET with `ex=FEATURE_CACHE_TTL_S`; no-op when disabled / no client / empty; swallows errors.
- [ ] Redis client accessed only at call time via `cache_service.redis_client` (never imported as a name).
- [ ] No function raises; all degrade to miss/no-op.
- [ ] `python -m py_compile` clean.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/feature_cache.py` → success. (Round-trip/degrade unit tests run on the VM where cv2/imagehash/numpy are installed — see Step 3.)

**Steps:**

- [ ] **Step 1: Create `app/core/feature_cache.py`**

```python
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import imagehash
import numpy as np

from common_utils.redis import cache_service
from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis key namespace for cached per-URL features. The version segment lets an
# algorithm change (trim_borders / extract_features) invalidate old entries by bump.
_KEY_PREFIX = "imgfeat"


def feature_key(url: str) -> str:
    """Deterministic Redis key for an image URL's cached feature.

    Mirrors the service's own id derivation (uuid5(NAMESPACE_URL, url) in
    comparator.py) so the key is stable across jobs/replicas and never leaks a
    long/signed URL into Redis.
    """
    return f"{_KEY_PREFIX}:{settings.FEATURE_CACHE_VERSION}:{uuid.uuid5(uuid.NAMESPACE_URL, url)}"


def serialize_feature(feature: Dict[str, Any]) -> str:
    """Serialize an extract_features() output to JSON text.

    The shared Redis client uses decode_responses=True, so values must be text.
    phash (imagehash.ImageHash) -> its 16-char hex string; hist (np.float32 array)
    -> a plain float list. Both round-trip losslessly for the comparison ops.
    """
    return json.dumps({
        "phash": str(feature["phash"]),
        "hist": feature["hist"].tolist(),
    })


def deserialize_feature(raw: str) -> Optional[Dict[str, Any]]:
    """Rebuild a feature dict from cached JSON text. Returns None on ANY error
    (corrupt JSON, missing field, bad hex) so the caller treats it as a miss.

    The rebuilt types MUST match extract_features(): phash as imagehash.ImageHash
    (supports `-` for Hamming distance) and hist as a contiguous float32 ndarray
    (cv2.compareHist requires float32)."""
    try:
        data = json.loads(raw)
        phash = imagehash.hex_to_hash(data["phash"])
        hist = np.array(data["hist"], dtype=np.float32)
        return {"phash": phash, "hist": hist}
    except Exception as e:
        logger.warning(f"feature_cache: deserialize failed ({type(e).__name__}: {e}) — treating as miss")
        return None


async def get_features(urls: List[str]) -> Dict[str, Dict[str, Any]]:
    """Batch-read cached features for the given URLs. Returns {url: feature} for
    hits only. Degrades to {} (all-miss) when disabled, no Redis client, on any
    RedisError, or empty input — never raises."""
    if not settings.FEATURE_CACHE_ENABLED:
        return {}
    client = cache_service.redis_client
    if not client or not urls:
        return {}

    keys = [feature_key(u) for u in urls]
    try:
        values = await client.mget(keys)
    except Exception as e:
        logger.warning(f"feature_cache: MGET failed ({type(e).__name__}: {e}) — all miss")
        return {}

    hits: Dict[str, Dict[str, Any]] = {}
    for url, raw in zip(urls, values):
        if not raw:
            continue
        feature = deserialize_feature(raw)
        if feature is not None:
            hits[url] = feature
    return hits


async def set_features(url_to_feature: Dict[str, Dict[str, Any]]) -> None:
    """Batch-write freshly extracted features in one pipeline with the cache TTL.
    No-op when disabled / no client / empty; swallows all errors (a failed write
    just means a future miss). Writes are idempotent (deterministic feature)."""
    if not settings.FEATURE_CACHE_ENABLED:
        return
    client = cache_service.redis_client
    if not client or not url_to_feature:
        return

    try:
        pipe = client.pipeline()
        for url, feature in url_to_feature.items():
            pipe.set(feature_key(url), serialize_feature(feature), ex=settings.FEATURE_CACHE_TTL_S)
        await pipe.execute()
    except Exception as e:
        logger.warning(f"feature_cache: pipelined SET failed ({type(e).__name__}: {e}) — not cached")
```

- [ ] **Step 2: Verify compile**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/feature_cache.py`
Expected: success (no output).

- [ ] **Step 3: Create the optional unit test (run on the VM where cv2/imagehash/numpy exist)**

Create `apps-microservices/image-comparison-service/tests/test_feature_cache.py`:

```python
"""Unit tests for feature_cache serialization. Run on the VM (needs cv2/imagehash/numpy/PIL):
    cd apps-microservices/image-comparison-service && python -m pytest tests/test_feature_cache.py -v
No Redis required — these cover the pure serialize/deserialize seam."""
import numpy as np
import cv2
import imagehash
from PIL import Image

from app.core.feature_cache import serialize_feature, deserialize_feature, feature_key
from app.core.image_processor import ImageProcessor


def _make_feature(seed: int):
    rng = np.random.default_rng(seed)
    arr = (rng.random((64, 64, 3)) * 255).astype("uint8")
    return ImageProcessor.extract_features(Image.fromarray(arr, "RGB"))


def test_round_trip_preserves_hamming_and_correlation():
    f1 = _make_feature(1)
    f2 = _make_feature(2)
    r1 = deserialize_feature(serialize_feature(f1))
    r2 = deserialize_feature(serialize_feature(f2))
    assert r1 is not None and r2 is not None
    # pHash Hamming distance identical after round-trip
    assert (f1["phash"] - f2["phash"]) == (r1["phash"] - r2["phash"])
    # Histogram correlation identical (rebuilt hist must be float32 + same shape)
    orig = cv2.compareHist(f1["hist"], f2["hist"], cv2.HISTCMP_CORREL)
    back = cv2.compareHist(r1["hist"], r2["hist"], cv2.HISTCMP_CORREL)
    assert abs(orig - back) < 1e-6
    assert r1["hist"].dtype == np.float32


def test_self_similarity_identical_after_round_trip():
    f1 = _make_feature(7)
    r1 = deserialize_feature(serialize_feature(f1))
    score_orig, _ = ImageProcessor.calculate_similarity(f1, f1)
    score_back, _ = ImageProcessor.calculate_similarity(r1, r1)
    assert score_orig == score_back == 100.0


def test_corrupt_payload_is_treated_as_miss():
    assert deserialize_feature("not json") is None
    assert deserialize_feature('{"phash": "zz"}') is None  # missing hist / bad hex
    assert deserialize_feature('{"hist": [1,2,3]}') is None  # missing phash


def test_feature_key_is_deterministic_and_namespaced():
    k = feature_key("https://example.com/a.jpg")
    assert k == feature_key("https://example.com/a.jpg")
    assert k.startswith("imgfeat:")
    assert feature_key("https://example.com/a.jpg") != feature_key("https://example.com/b.jpg")
```

- [ ] **Step 4: Verify the test compiles** (run on VM executes it)

Run: `python -m py_compile apps-microservices/image-comparison-service/tests/test_feature_cache.py`
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/image-comparison-service/app/core/feature_cache.py \
        apps-microservices/image-comparison-service/tests/test_feature_cache.py
git commit -m "feat(image-comparison): per-URL feature cache module (cache-aside, guarded)" \
  -m "EN: New feature_cache.py: feature_key (imgfeat:<version>:uuid5(url)), serialize/deserialize feature {phash hex, hist float list} (deserialize->None on any error), async get_features (one MGET, hits only) / set_features (one pipelined SET EX TTL). Kill-switch + guarded cache_service.redis_client (call-time); every failure degrades to miss/no-op, never raises. + round-trip/degrade unit tests (VM)." \
  -m "FR: Nouveau feature_cache.py : feature_key (imgfeat:<version>:uuid5(url)), serialize/deserialize du feature {phash hex, hist liste de floats} (deserialize->None sur toute erreur), async get_features (un MGET, hits seulement) / set_features (un SET pipeline EX TTL). Kill-switch + cache_service.redis_client garde (au call-time) ; toute erreur degrade en miss/no-op, ne leve jamais. + tests unitaires round-trip/degrade (VM)."
```

```json:metadata
{"files":["apps-microservices/image-comparison-service/app/core/feature_cache.py","apps-microservices/image-comparison-service/tests/test_feature_cache.py"],"verifyCommand":"python -m py_compile apps-microservices/image-comparison-service/app/core/feature_cache.py apps-microservices/image-comparison-service/tests/test_feature_cache.py","acceptanceCriteria":["feature_key imgfeat:<version>:uuid5(url)","serialize/deserialize round-trip preserves Hamming + compareHist; corrupt->None","get_features: kill-switch/no-client/RedisError/empty -> {}; one MGET; hits only","set_features: kill-switch/no-client/empty -> no-op; one pipelined SET EX TTL; swallow errors","redis_client accessed at call time only","never raises","py_compile clean"]}
```

---

### Task 3: Split `image_processor` — `extract_features_for` + `compare_features`

**Goal:** Decouple feature extraction from the pairwise comparison so the comparison can run on a feature-map that mixes cached + freshly extracted features. The scoring math is unchanged; existing callers of `compare_batch` get identical results.

**Files:**
- Modify: `apps-microservices/image-comparison-service/app/core/image_processor.py:287-323` (the `compare_batch` method)

**Depends on:** none (independent of the cache). Sequence after T2 for clean review.

**Acceptance Criteria:**
- [ ] New `extract_features_for(images: Dict[str, Image.Image]) -> Dict[str, Dict]` = `{id: extract_features(img)}`.
- [ ] New `compare_features(features_map: Dict[str, Dict], inputs: List[ImageInput]) -> List[Dict]` containing the EXACT pairwise loop currently in `compare_batch` (same `calculate_similarity`, smart-identity, weighting, rounding, output keys), with the same `n < 2 → []` guard.
- [ ] `compare_batch` keeps its signature and delegates: `extract_features_for` then `compare_features` → byte-identical output.
- [ ] `calculate_similarity`, `extract_features`, `trim_borders`, `load_images` UNCHANGED.
- [ ] `python -m py_compile` clean.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/image_processor.py` → success.

**Steps:**

- [ ] **Step 1: Replace the `compare_batch` method (lines 287-323) with the split**

Current:

```python
    @staticmethod
    def compare_batch(images: Dict[str, Image.Image], inputs: List[ImageInput]) -> List[Dict]:
        """
        Compares images and maps IDs back to URLs if available.
        """
        ids = list(images.keys())
        n = len(ids)
        if n < 2:
            return []
            
        # Create map for ID -> URL for quick lookup
        url_map = {inp.id: inp.url for inp in inputs}

        # 1. Feature Extraction (O(N))
        features_map = {}
        for img_id in ids:
            features_map[img_id] = ImageProcessor.extract_features(images[img_id])
            
        # 2. Comparison Matrix (O(N^2))
        results = []
        for i in range(n):
            for j in range(i + 1, n):
                id_a = ids[i]
                id_b = ids[j]
                
                score, details = ImageProcessor.calculate_similarity(features_map[id_a], features_map[id_b])
                
                results.append({
                    "image_a_id": id_a,
                    "image_a_url": url_map.get(id_a),
                    "image_b_id": id_b,
                    "image_b_url": url_map.get(id_b),
                    "score": round(score, 2),
                    "method_details": details
                })
                
        return results
```

Replace with:

```python
    @staticmethod
    def extract_features_for(images: Dict[str, Image.Image]) -> Dict[str, Dict]:
        """Extract features for a map of {id: PIL.Image} (O(N)). Used for the
        cache-miss images; cached features are merged in by the caller."""
        return {img_id: ImageProcessor.extract_features(img) for img_id, img in images.items()}

    @staticmethod
    def compare_features(features_map: Dict[str, Dict], inputs: List[ImageInput]) -> List[Dict]:
        """Pairwise comparison (O(N^2)) over a ready feature-map (cached + fresh),
        mapping ids back to URLs. Scoring math is unchanged from compare_batch."""
        ids = list(features_map.keys())
        n = len(ids)
        if n < 2:
            return []

        # Create map for ID -> URL for quick lookup
        url_map = {inp.id: inp.url for inp in inputs}

        results = []
        for i in range(n):
            for j in range(i + 1, n):
                id_a = ids[i]
                id_b = ids[j]

                score, details = ImageProcessor.calculate_similarity(features_map[id_a], features_map[id_b])

                results.append({
                    "image_a_id": id_a,
                    "image_a_url": url_map.get(id_a),
                    "image_b_id": id_b,
                    "image_b_url": url_map.get(id_b),
                    "score": round(score, 2),
                    "method_details": details
                })

        return results

    @staticmethod
    def compare_batch(images: Dict[str, Image.Image], inputs: List[ImageInput]) -> List[Dict]:
        """
        Compares images and maps IDs back to URLs if available.
        Thin pipeline: extract features for all images, then compare the map.
        """
        if len(images) < 2:
            return []
        features_map = ImageProcessor.extract_features_for(images)
        return ImageProcessor.compare_features(features_map, inputs)
```

- [ ] **Step 2: Verify**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/image_processor.py`
Expected: success (no output).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/image-comparison-service/app/core/image_processor.py
git commit -m "refactor(image-comparison): split compare_batch into extract_features_for + compare_features" \
  -m "EN: Decouple feature extraction from the pairwise comparison so the cache path can compare a map mixing cached + freshly extracted features. compare_batch keeps its signature and delegates; scoring math (calculate_similarity / smart-identity / weighting / rounding) and load_images are unchanged -> byte-identical output." \
  -m "FR: Decouple l'extraction des features de la comparaison par paires pour que le chemin cache puisse comparer une map melangeant features caches + fraichement extraits. compare_batch garde sa signature et delegue ; le calcul des scores (calculate_similarity / smart-identity / ponderation / arrondi) et load_images sont inchanges -> sortie byte-identique."
```

```json:metadata
{"files":["apps-microservices/image-comparison-service/app/core/image_processor.py"],"verifyCommand":"python -m py_compile apps-microservices/image-comparison-service/app/core/image_processor.py","acceptanceCriteria":["extract_features_for(images)->{id:feature}","compare_features(features_map,inputs) = exact current pairwise loop + n<2 guard","compare_batch delegates, byte-identical output","calculate_similarity/extract_features/load_images unchanged","py_compile clean"]}
```

---

### Task 4: `process_job_logic` cache-aside orchestration

**Goal:** Before downloading, MGET cached features for the URL inputs; download + extract only the misses (plus all base64 `content` inputs); pipelined-SET the freshly extracted URL-miss features; compare the merged feature-map. `similar_pairs` stays byte-identical. Design-1's failed-list, per-job `wait_for`, and counter handling are preserved.

**Files:**
- Modify: `apps-microservices/image-comparison-service/app/core/job_manager.py:1-13` (import), `:125-144` (the load+compare region inside `process_job_logic`)

**Depends on:** Task 2 (`feature_cache`), Task 3 (`extract_features_for` / `compare_features`).

**Acceptance Criteria:**
- [ ] Partition inputs: cacheable = `inp.url and not inp.content`; everything else (base64 `content`, or neither) goes straight to download.
- [ ] `get_features([str(url)...])` → map hits back to `inp.id`; misses + non-cacheable inputs are downloaded via `load_images`.
- [ ] Fresh features extracted via `extract_features_for` in a worker thread (`anyio.to_thread.run_sync`); URL-miss fresh features written via `set_features` (content inputs NOT cached).
- [ ] Comparison runs on `{**cached, **fresh}` via `compare_features` in a worker thread; `inputs` (full list) passed for the URL map.
- [ ] "No valid images" guard fires on the MERGED map being empty (not on `images_map`), so an all-cache-hit job is NOT mis-failed.
- [ ] `failed_images`, `threshold` filtering, `ComparisonResult` shape, status writes, semaphore, `finally` counter, and the `except` path are UNCHANGED.
- [ ] `python -m py_compile` clean.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/job_manager.py` → success.

**Steps:**

- [ ] **Step 1: Add the imports**

Current top of `app/core/job_manager.py`:

```python
import anyio
from common_utils.redis import cache_service

from app.core.config import settings
from app.schemas.comparator import ComparisonResult, SimilarityPair, JobStatus, CapacityResponse
from app.core.image_processor import ImageProcessor
```

Replace with:

```python
import anyio
from common_utils.redis import cache_service

from app.core.config import settings
from app.schemas.comparator import ComparisonResult, SimilarityPair, JobStatus, CapacityResponse
from app.core.image_processor import ImageProcessor
from app.core import feature_cache
```

- [ ] **Step 2: Replace the load + compare region inside `process_job_logic`**

Current (lines 125-144, inside the `async with self.semaphore:` `try`):

```python
                    logger.info(f"Job {job_id}: Loading {len(inputs)} images...")

                    images_map, failed_ids = await ImageProcessor.load_images(inputs)

                    if not images_map:
                        raise Exception("No valid images could be loaded/downloaded.")

                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=40.0).json(),
                        ex=settings.JOB_RESULT_TTL
                    )

                    logger.info(f"Job {job_id}: Processing comparisons...")

                    raw_results = await anyio.to_thread.run_sync(
                        ImageProcessor.compare_batch,
                        images_map,
                        inputs
                    )
```

Replace with:

```python
                    logger.info(f"Job {job_id}: Loading {len(inputs)} images...")

                    # Cache-aside: read cached per-URL features first; only download+extract misses.
                    # Cacheable = pure URL inputs. Base64 `content` inputs (and any input with
                    # neither url nor content) are never cached and always go to load_images.
                    url_inputs = [inp for inp in inputs if inp.url and not inp.content]
                    other_inputs = [inp for inp in inputs if not (inp.url and not inp.content)]

                    cached_by_url = await feature_cache.get_features([str(inp.url) for inp in url_inputs])
                    cached_features = {
                        inp.id: cached_by_url[str(inp.url)]
                        for inp in url_inputs if str(inp.url) in cached_by_url
                    }
                    miss_url_inputs = [inp for inp in url_inputs if str(inp.url) not in cached_by_url]

                    # Download only the misses + the uncacheable inputs.
                    to_load = miss_url_inputs + other_inputs
                    images_map, failed_ids = await ImageProcessor.load_images(to_load)

                    # Extract features for the freshly downloaded images (off the event loop).
                    fresh_features = await anyio.to_thread.run_sync(
                        ImageProcessor.extract_features_for,
                        images_map
                    )

                    # Cache the freshly extracted URL-miss features (content inputs are not cached).
                    await feature_cache.set_features({
                        str(inp.url): fresh_features[inp.id]
                        for inp in miss_url_inputs if inp.id in fresh_features
                    })

                    all_features = {**cached_features, **fresh_features}
                    logger.info(
                        f"Job {job_id}: features ready | cached={len(cached_features)} "
                        f"fresh={len(fresh_features)} failed={len(failed_ids)}"
                    )

                    if not all_features:
                        raise Exception("No valid images could be loaded/downloaded.")

                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=40.0).json(),
                        ex=settings.JOB_RESULT_TTL
                    )

                    logger.info(f"Job {job_id}: Processing comparisons...")

                    raw_results = await anyio.to_thread.run_sync(
                        ImageProcessor.compare_features,
                        all_features,
                        inputs
                    )
```

- [ ] **Step 3: Verify**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/job_manager.py`
Expected: success (no output).

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/image-comparison-service/app/core/job_manager.py
git commit -m "feat(image-comparison): cache-aside feature lookup in process_job_logic" \
  -m "EN: MGET cached per-URL features; download+extract only misses (+ all base64 content inputs); pipelined-SET fresh URL-miss features; compare the merged {cached, fresh} map via compare_features. similar_pairs byte-identical; the No-valid-images guard now checks the merged map (an all-hit job is not mis-failed). failed_images, threshold filtering, result shape, semaphore, wait_for, and the counter finally are unchanged. Safe: miss/error/eviction -> download, never a fabricated verdict; content inputs uncacheable." \
  -m "FR: MGET des features par URL caches ; download+extract uniquement des miss (+ tous les inputs base64 content) ; SET pipeline des features fraiches des URL-miss ; comparaison sur la map fusionnee {caches, frais} via compare_features. similar_pairs byte-identique ; le garde No-valid-images verifie desormais la map fusionnee (un job tout-hit n'est pas faussement echoue). failed_images, filtrage par seuil, forme du resultat, semaphore, wait_for et le finally du compteur inchanges. Sur : miss/erreur/eviction -> download, jamais de verdict fabrique ; inputs content non cachables."
```

```json:metadata
{"files":["apps-microservices/image-comparison-service/app/core/job_manager.py"],"verifyCommand":"python -m py_compile apps-microservices/image-comparison-service/app/core/job_manager.py","acceptanceCriteria":["partition url vs content/other inputs","get_features mapped to id; misses+other downloaded","extract_features_for in thread; set_features for url-misses only","compare_features on {cached,fresh} in thread with full inputs","No-valid-images guard on merged map (all-hit not mis-failed)","failed_images/threshold/result/semaphore/wait_for/counter unchanged","py_compile clean"]}
```

---

## Self-Review

**1. Spec coverage:**
- §3.1 staleness/TTL/key/store/approach/server-side-only → T1 (TTL/version/enable), T2 (key/serialize/store), T4 (server-side orchestration, zero BO/API change). ✓
- §3.2 `feature_cache.py` API (feature_key/serialize/deserialize/get_features/set_features, kill-switch, guards, degrade-to-miss) → T2. ✓
- §3.3 split extract/compare, math unchanged → T3. ✓
- §3.4 orchestration (partition, get_features→id map, miss+content download, extract in thread, set url-misses, compare merged, guard on merged) → T4. ✓
- §3.5 config knobs → T1. ✓
- §4 contract unchanged / byte-identical scores / safety floor / pool (MGET+pipeline) / cross-replica → T2 (MGET+pipeline, guards) + T3 (identical math) + T4 (failed/threshold/result/contract preserved). ✓
- §5 verification (py_compile + round-trip unit test + VM smoke) → each task's Verify + T2 test file. ✓

**2. Placeholder scan:** No TBD/TODO/"handle errors"/vague steps — every code step shows complete code. ✓

**3. Type consistency:** `extract_features_for` / `compare_features` names match between T3 (definition) and T4 (calls). `feature_cache.get_features` / `set_features` names match T2↔T4. `serialize_feature`/`deserialize_feature` consistent. `settings.FEATURE_CACHE_ENABLED/TTL_S/VERSION` names match T1↔T2. Feature dict keys (`phash`/`hist`) consistent with `extract_features`. ✓

No gaps found.
