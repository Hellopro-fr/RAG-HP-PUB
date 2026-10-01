"""Unit tests for _verify_terminal_status_persisted (F2-A, incident /results 400-running).

cache_service.set_json is fail-open — a silently lost terminal write leaves the
Redis blob 'running' and the BO's immediate GET /results 400s. The helper reads
back the blob after the terminal set_json; on mismatch it rewrites once and
re-checks. It must never raise.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_finalize_rewrites_when_status_readback_mismatches():
    mgr = CrawlerManager()
    job_info = {"crawl_id": "42", "status": "finished", "storage_path": "/tmp/x", "domain": "d"}
    readbacks = [{"crawl_id": "42", "status": "running"}, {"crawl_id": "42", "status": "finished"}]
    with patch("app.core.crawler_manager.cache_service.get_json", AsyncMock(side_effect=readbacks)) as gj, \
         patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj:
        await mgr._verify_terminal_status_persisted("crawl_job:42", job_info, "finished")
        assert sj.await_count == 1
        assert gj.await_count == 2


@pytest.mark.asyncio
async def test_finalize_no_rewrite_when_persisted():
    mgr = CrawlerManager()
    job_info = {"crawl_id": "42", "status": "finished"}
    with patch("app.core.crawler_manager.cache_service.get_json", AsyncMock(return_value={"status": "finished"})) as gj, \
         patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj:
        await mgr._verify_terminal_status_persisted("crawl_job:42", job_info, "finished")
        assert sj.await_count == 0
        assert gj.await_count == 1


@pytest.mark.asyncio
async def test_finalize_handles_blob_missing_without_raising():
    mgr = CrawlerManager()
    job_info = {"crawl_id": "42", "status": "finished"}
    with patch("app.core.crawler_manager.cache_service.get_json", AsyncMock(return_value=None)), \
         patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj:
        await mgr._verify_terminal_status_persisted("crawl_job:42", job_info, "finished")
        assert sj.await_count == 1  # rewrite attempted; second read still None -> critical log, no raise
