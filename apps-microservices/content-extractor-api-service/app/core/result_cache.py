"""Redis-backed result cache for extraction outputs. Cache-aside, versioned key,
graceful-degrade.

CRITICAL: the shared cache_service helpers RAISE ConnectionError when there is no
Redis client (cache_service.py:145-146,156-157,168-169). Graceful degradation is a
property of THIS layer: every access is guarded on cache_service.redis_client being
truthy first (mirrors image-comparison feature_cache.py:65,92). Never raises."""
import hashlib
import logging
from typing import Optional

from common_utils.redis import cache_service

from app.core.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "extract"


def _key(job_type: str, digest: str) -> str:
    return f"{_PREFIX}:{job_type}:{settings.RESULT_CACHE_VERSION}:{digest}"


def clean_key(html: str, fmt: str) -> str:
    digest = hashlib.sha256(f"{fmt}\x00{html}".encode("utf-8")).hexdigest()
    return _key("clean", digest)


def header_footer_key(main_html: str, reference_htmls: list[str], debug: bool) -> str:
    # debug=False: the returned header/footer strings are order-independent
    # (HeaderFooterExtractor uses set-membership across refs) -> sort for a wider hit.
    # debug=True: the response carries order-dependent text_ref1/text_ref2 -> preserve order.
    refs = sorted(reference_htmls) if not debug else list(reference_htmls)
    parts = [main_html] + refs + [str(debug)]
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return _key("hf", digest)


async def get(key: str) -> Optional[dict]:
    """Cached body dict, or None on miss/disabled/no-client/error. Never raises."""
    if not settings.RESULT_CACHE_ENABLED:
        return None
    if not cache_service.redis_client:          # guard: bare helper raises if None
        return None
    try:
        return await cache_service.get_json(key)
    except Exception as e:
        logger.warning("result_cache get failed (%s: %s) — miss", type(e).__name__, e)
        return None


async def set(key: str, body: dict) -> None:
    """Write a result body. No-op when disabled/no-client; swallows all errors."""
    if not settings.RESULT_CACHE_ENABLED:
        return
    if not cache_service.redis_client:
        return
    try:
        await cache_service.set_json(key, body, ttl=settings.RESULT_CACHE_TTL_S)
    except Exception as e:
        logger.warning("result_cache set failed (%s: %s) — not cached", type(e).__name__, e)
