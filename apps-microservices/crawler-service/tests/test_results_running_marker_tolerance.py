"""F2-B: /results tolerates a stale 'running' blob when the completion marker exists.

The completion marker (_completion_marker.json) is written by _monitor_process
BEFORE the webhook and is the disk source of truth — a genuinely active crawl
never has one. get_results_archive must heal the blob to the MARKER's
final_status (not hardcoded 'finished') instead of raising 400, and purge
last_heartbeat (terminal-blob invariant). A corrupt marker is treated as
"no marker" → 400.

The healed blob must also carry the final counters (F8: post-stash /status
recomputes from now-deleted dataset dirs → 0) and the terminal stamps
(finished_at/size_bytes, inputs of the auto-stash sweep) — without clobbering
a finished_at already landed by the F2-A rewrite.
"""
import inspect
import json

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_running_with_marker_is_tolerated_and_healed(tmp_path):
    mgr = CrawlerManager()
    (tmp_path / "_completion_marker.json").write_text(json.dumps({"final_status": "finished", "exit_code": 2}))
    dataset_dir = tmp_path / "storage" / "datasets" / "d"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "page1.json").write_text("{}")
    (dataset_dir / "page2.json").write_text("{}")
    job = {"crawl_id": "42", "status": "running", "domain": "d",
           "storage_path": str(tmp_path), "last_heartbeat": "x"}
    with patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj, \
         patch.object(CrawlerManager, "_generate_archive_sync", return_value="/tmp/a.tar.gz"):
        path, is_tmp = await mgr.get_results_archive(job, include=[])
    assert path == "/tmp/a.tar.gz"
    assert is_tmp is False
    assert job["status"] == "finished"
    assert "last_heartbeat" not in job
    # F8: the healed terminal blob must carry the final counters + terminal stamps,
    # or a later stash makes /status report 0 urls (BO downgrades the crawl).
    assert job["final_urls_crawled"] == 2
    assert job["final_error_urls_crawled"] == 0
    assert job.get("finished_at") is not None
    assert sj.await_count == 1


@pytest.mark.asyncio
async def test_running_with_failed_marker_heals_to_failed(tmp_path):
    mgr = CrawlerManager()
    (tmp_path / "_completion_marker.json").write_text(json.dumps({"final_status": "failed", "exit_code": -1}))
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path),
           "last_heartbeat": "x", "finished_at": "2026-01-01T00:00:00"}
    with patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj, \
         patch.object(CrawlerManager, "_generate_archive_sync", return_value="/tmp/a.tar.gz"):
        path, is_tmp = await mgr.get_results_archive(job, include=[])
    assert path == "/tmp/a.tar.gz"
    assert is_tmp is False
    assert job["status"] == "failed"
    assert "last_heartbeat" not in job
    # A finished_at already landed (e.g. by the F2-A rewrite) must NOT be clobbered.
    assert job["finished_at"] == "2026-01-01T00:00:00"
    assert sj.await_count == 1


def test_reconcile_marker_heal_stamps_counters_and_terminal_fields():
    """The reconcile marker-heal persists the same terminal blob as F2-B and has
    the same F8 exposure. Source-shape test (project style for _reconcile_locked:
    no Redis fixture): both helpers must be called before the heal's set_json."""
    from app.core import crawler_manager as cm

    source = inspect.getsource(cm.CrawlerManager._reconcile_locked)
    block = source[source.index("Reconciling from marker"):]
    before_set_json = block[:block.index("set_json(all_job_keys[i], job_data)")]
    assert "self._persist_final_counters(job_data)" in before_set_json, (
        "reconcile marker-heal must persist final counters before its terminal set_json (F8)"
    )
    assert "self._stamp_terminal_fields(job_data)" in before_set_json, (
        "reconcile marker-heal must stamp finished_at/size_bytes before its terminal set_json"
    )


@pytest.mark.asyncio
async def test_running_with_corrupt_marker_still_400(tmp_path):
    mgr = CrawlerManager()
    (tmp_path / "_completion_marker.json").write_text("not json")
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path)}
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, include=[])
    assert exc.value.status_code == 400
    assert "running" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_running_without_marker_still_400(tmp_path):
    mgr = CrawlerManager()
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path)}
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, include=[])
    assert exc.value.status_code == 400
    assert "running" in str(exc.value.detail)
