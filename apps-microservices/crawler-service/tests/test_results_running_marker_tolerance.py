"""F2-B: /results tolerates a stale 'running' blob when the completion marker exists.

The completion marker (_completion_marker.json) is written by _monitor_process
BEFORE the webhook and is the disk source of truth — a genuinely active crawl
never has one. get_results_archive must heal the blob instead of raising 400.
"""
import json

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_running_with_marker_is_tolerated_and_healed(tmp_path):
    mgr = CrawlerManager()
    (tmp_path / "_completion_marker.json").write_text(json.dumps({"final_status": "finished", "exit_code": 2}))
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path)}
    with patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj, \
         patch.object(CrawlerManager, "_generate_archive_sync", return_value="/tmp/a.tar.gz"):
        path, is_tmp = await mgr.get_results_archive(job, include=[])
    assert path == "/tmp/a.tar.gz"
    assert is_tmp is False
    assert job["status"] == "finished"
    assert sj.await_count == 1


@pytest.mark.asyncio
async def test_running_without_marker_still_400(tmp_path):
    mgr = CrawlerManager()
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path)}
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, include=[])
    assert exc.value.status_code == 400
    assert "running" in str(exc.value.detail)
