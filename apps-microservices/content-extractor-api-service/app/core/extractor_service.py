"""Async orchestration over the pure cores: cache-aside + thread-offloaded CPU.
Shared by the sync routers and the async batch worker (DRY). The CPU work runs in
a thread (asyncio.to_thread) so the event loop is never blocked."""
import asyncio
import logging

from app.core import extractor_core, result_cache
from app.core.metrics import CACHE_HITS, CACHE_MISSES, EXTRACTION_METHOD
from app.schemas.clean import OutputFormat

logger = logging.getLogger(__name__)


async def run_clean(html: str, fmt: OutputFormat, force_refresh: bool = False) -> dict:
    key = result_cache.clean_key(html, fmt.value)
    if not force_refresh:
        cached = await result_cache.get(key)
        if cached is not None:
            CACHE_HITS.labels(job_type="clean").inc()
            return cached
    CACHE_MISSES.labels(job_type="clean").inc()
    content = await asyncio.to_thread(extractor_core.clean_core, html, fmt)
    body = {"content": content, "format": fmt.value, "content_length": len(content)}
    await result_cache.set(key, body)
    return body


async def run_header_footer(main_html: str, reference_htmls: list[str],
                            debug: bool = False, force_refresh: bool = False) -> dict:
    key = result_cache.header_footer_key(main_html, reference_htmls, debug)
    if not force_refresh:
        cached = await result_cache.get(key)
        if cached is not None:
            CACHE_HITS.labels(job_type="header_footer").inc()
            return cached
    CACHE_MISSES.labels(job_type="header_footer").inc()
    body = await asyncio.to_thread(
        extractor_core.header_footer_core, main_html, reference_htmls, debug
    )
    EXTRACTION_METHOD.labels(method=body.get("header_method", "none")).inc()
    EXTRACTION_METHOD.labels(method=body.get("footer_method", "none")).inc()
    await result_cache.set(key, body)
    return body
