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
