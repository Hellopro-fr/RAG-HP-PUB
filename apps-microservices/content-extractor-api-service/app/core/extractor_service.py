"""Async orchestration over the pure cores. The CPU work runs in a thread
(asyncio.to_thread) so the event loop is never blocked. Shared by the sync
routers and (later) the async batch worker. Cache-aside is layered in by a later task."""
import asyncio
import logging

from app.core import extractor_core
from app.core.metrics import EXTRACTION_METHOD
from app.schemas.clean import OutputFormat

logger = logging.getLogger(__name__)


async def run_clean(html: str, fmt: OutputFormat, force_refresh: bool = False) -> dict:
    content = await asyncio.to_thread(extractor_core.clean_core, html, fmt)
    return {"content": content, "format": fmt.value, "content_length": len(content)}


async def run_header_footer(main_html: str, reference_htmls: list[str],
                            debug: bool = False, force_refresh: bool = False) -> dict:
    body = await asyncio.to_thread(
        extractor_core.header_footer_core, main_html, reference_htmls, debug
    )
    EXTRACTION_METHOD.labels(method=body.get("header_method", "none")).inc()
    EXTRACTION_METHOD.labels(method=body.get("footer_method", "none")).inc()
    return body
