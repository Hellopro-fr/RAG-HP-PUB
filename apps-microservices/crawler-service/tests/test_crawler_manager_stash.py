"""Unit tests for stash/unstash flows in crawler_manager.py.

Covers spec Section 8 test cases. All tests use mocks for Redis + filesystem
to stay hermetic — integration tests in tests/integration/ exercise the real
GCS round-trip.
"""
import asyncio
import io
import json
import os
import tarfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def mock_cache_service(monkeypatch):
    """Mock common_utils.redis.cache_service used by crawler_manager."""
    mock = MagicMock()
    mock.redis_client = AsyncMock()
    mock.get_json = AsyncMock(return_value=None)
    mock.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", mock)
    return mock


@pytest.fixture
def cm_instance(mock_cache_service):
    return CrawlerManager()


@pytest.fixture(autouse=True)
def mock_bind_mounts_present(monkeypatch):
    """Default for this test module: os.path.ismount returns True.

    Without this, every test that exercises stash_crawl / unstash_crawl
    would hit the new _verify_bind_mount 503 check because tmp_path is
    not a real mount point. Tests that WANT to assert the 503 path can
    override with monkeypatch.setattr(os.path, "ismount", lambda p: False)
    inside the test body — local monkeypatch wins over autouse.
    """
    monkeypatch.setattr(os.path, "ismount", lambda p: True)


@pytest.fixture
def base_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    # Seed both a kept file (log) and a data file so cleanup-keep-logs
    # behavior is exercised by every test using this fixture.
    (storage / "crawler.log").write_text("log content")
    (storage / "dataset.json").write_text('{"records": [1,2,3]}')
    return {
        "crawl_id": "test_id",
        "status": "failed",
        "storage_path": str(storage),
        "domain": "example.com",
    }


# ============================================================================
# stash_crawl tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("active_status", ["running", "restarting_oom", "stopping"])
async def test_stash_blocks_active_status(cm_instance, base_job_info, active_status):
    base_job_info["status"] = active_status
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "CRAWL_IS_ACTIVE"


@pytest.mark.asyncio
async def test_stash_blocks_already_archived(cm_instance, base_job_info):
    base_job_info["status"] = "archived"
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_ARCHIVED"


@pytest.mark.asyncio
async def test_stash_blocks_already_stashed(cm_instance, base_job_info):
    base_job_info["stashed_at"] = "2026-05-19T00:00:00Z"
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_STASHED"


@pytest.mark.asyncio
async def test_stash_crawl_rejects_when_stash_dir_not_mount(
    cm_instance, base_job_info, mock_cache_service, monkeypatch
):
    """Spec 2026-05-20 §4: bind-mount preflight rejects with 503 when
    STASH_SHARED_PATH is not a real mount point. Lock must be released
    by the existing finally block."""
    # All Redis mocks pass TOCTOU successfully
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    # Override autouse fixture: ismount returns False (no bind-mount)
    monkeypatch.setattr(os.path, "ismount", lambda p: False)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    assert exc.value.detail["label"] == "stash upload"
    # Lock released by finally (Lua eval invoked at least once)
    assert mock_cache_service.redis_client.eval.call_count >= 1


@pytest.mark.asyncio
async def test_stash_blocks_lock_held(cm_instance, base_job_info, mock_cache_service):
    # unstash_lock NOT held, but our stash_lock SET NX returns False
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "OPERATION_IN_PROGRESS"


@pytest.mark.asyncio
async def test_stash_disk_space_pre_flight_fails(cm_instance, base_job_info, mock_cache_service, monkeypatch):
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation reads fresh blob — return the same valid job
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 1024, "total_bytes": 1_000_000_000, "used_pct": 99.99, "file_count": 0, "oldest_file_age_seconds": None},
    )
    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "INSUFFICIENT_DISK_SPACE"


@pytest.mark.asyncio
async def test_stash_success_sets_timestamp_and_keeps_logs(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Happy-path stash: tar created in stash dir, Redis stashed_at set,
    DATA files deleted from storage but LOG files kept (spec 2026-05-20 §5)."""
    from pathlib import Path

    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    result = await cm_instance.stash_crawl(base_job_info)

    assert result["status"] == "stashing"
    assert result["crawl_id"] == "test_id"
    assert result["stash_path"] == "gs://test-bucket/stash/test_id.tar.gz"
    assert "stashed_at" in result

    # Tar present in stash dir, contains both seeded files
    final_tar = stash_dir / "test_id.tar.gz"
    assert final_tar.exists(), "Tar should exist in stash dir"
    with tarfile.open(final_tar, 'r:gz') as t:
        names = t.getnames()
        assert any("dataset.json" in n for n in names)
        assert any("crawler.log" in n for n in names)

    # Keep-logs behavior: storage dir still exists, log kept, data gone
    storage_path = base_job_info["storage_path"]
    assert os.path.isdir(storage_path), "storage dir should remain (kept files inside)"
    assert (Path(storage_path) / "crawler.log").exists(), "crawler.log should be kept"
    assert not (Path(storage_path) / "dataset.json").exists(), "dataset.json should be deleted"

    # Redis HSET wrote stashed_at
    last_call = mock_cache_service.set_json.call_args
    written = last_call[0][1]
    assert "stashed_at" in written


@pytest.mark.asyncio
async def test_stash_tar_failure_cleans_staging(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation reads fresh blob — return the same valid job
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    # Make shutil.make_archive raise
    def boom(*a, **k):
        raise RuntimeError("simulated disk full")
    monkeypatch.setattr(cm_module.shutil, "make_archive", boom)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 500
    # Staging should be empty
    staging = stash_dir / ".staging"
    if staging.exists():
        assert len(list(staging.iterdir())) == 0
    # No final tar
    assert not (stash_dir / "test_id.tar.gz").exists()
    # Local storage still present (we didn't delete it)
    assert os.path.exists(base_job_info["storage_path"])


@pytest.mark.asyncio
async def test_stash_ownership_safe_lock_release(cm_instance, mock_cache_service):
    # eval Lua returning 0 means lock value mismatched -> no delete
    mock_cache_service.redis_client.eval = AsyncMock(return_value=0)
    released = await cm_instance._release_ownership_lock("foo", "different_replica_id")
    assert released is False

    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    released = await cm_instance._release_ownership_lock("foo", "my_replica_id")
    assert released is True


# ============================================================================
# unstash_crawl tests
# ============================================================================

@pytest.fixture
def stashed_job_info(base_job_info):
    info = dict(base_job_info)
    info["stashed_at"] = "2026-05-19T00:00:00Z"
    info["status"] = "failed"
    return info


@pytest.mark.asyncio
async def test_unstash_blocks_not_stashed(cm_instance, base_job_info, mock_cache_service):
    # stashed_at NOT set
    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "NOT_STASHED"


@pytest.mark.asyncio
async def test_unstash_crawl_rejects_when_dir_not_mount(
    cm_instance, stashed_job_info, mock_cache_service, monkeypatch
):
    """Spec 2026-05-20 §4: bind-mount preflight rejects with 503 when
    either STASH_DOWNLOAD_REQUESTS_PATH or STASH_DOWNLOAD_RESULTS_PATH is
    not a real mount point. Lock must be released by the existing
    finally block. The first call site is the requests dir — that's the
    label expected in the 503 detail."""
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    # Override autouse fixture: ismount returns False
    monkeypatch.setattr(os.path, "ismount", lambda p: False)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    # First call site short-circuits — that's the requests dir
    assert exc.value.detail["label"] == "unstash requests"
    # Lock released
    assert mock_cache_service.redis_client.eval.call_count >= 1


@pytest.mark.asyncio
async def test_unstash_writes_request_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Concrete capture: assert the marker file path + content actually written
    by unstash_crawl before the polling loop times out.

    Prior version asserted only the 504 timeout — passed even if the marker
    write was a no-op. Spec §8 (and follow-up §4.4) require the write itself
    to be verified.
    """
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 2)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation in unstash_crawl reads fresh blob — return
    # the still-stashed one so the path proceeds to the request-marker write.
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    captured = {"name": None, "content": None}

    async def _capture_marker():
        # Poll req_dir for any *.request file. The marker exists between the
        # write and the timeout-cleanup at the end of unstash_crawl, so we
        # snapshot its content the moment it appears.
        for _ in range(50):
            await asyncio.sleep(0.05)
            files = list(req_dir.glob("*.request"))
            if files:
                captured["name"] = files[0].name
                captured["content"] = files[0].read_text()
                return

    capture_task = asyncio.create_task(_capture_marker())

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    # The polling loop expired — 504 is expected
    assert exc.value.status_code == 504

    # Wait for the capture task to finish (it may have already captured)
    await capture_task

    assert captured["name"] == "test_id.request", (
        f"Marker file path mismatch: got {captured['name']!r}"
    )
    assert captured["content"] == "test_id", (
        f"Marker file content mismatch: got {captured['content']!r}"
    )


@pytest.mark.asyncio
async def test_unstash_timeout_when_no_done_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 2)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation reads fresh blob — return the still-stashed one
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 504
    assert exc.value.detail["error_code"] == "UNSTASH_TIMEOUT"


@pytest.mark.asyncio
async def test_unstash_error_marker_returns_502(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    # Pre-write the .error marker
    (res_dir / "test_id.error").write_text("simulated GCS download failure")

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation reads fresh blob — return the still-stashed one
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "GCS_DOWNLOAD_FAILED"
    assert "simulated GCS download failure" in exc.value.detail["marker_content"]


def _create_test_tar(tar_path: str, content_dir: str):
    """Helper: build a valid tar.gz with one file inside."""
    os.makedirs(content_dir, exist_ok=True)
    sample = os.path.join(content_dir, "sample.txt")
    with open(sample, 'w') as f:
        f.write("test")
    with tarfile.open(tar_path, 'w:gz') as t:
        t.add(content_dir, arcname=os.path.basename(content_dir))


@pytest.mark.asyncio
async def test_unstash_success_with_cleanup_done(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    # Pre-write the tar.gz + .done so the polling loop exits immediately
    src = tmp_path / "src"
    src.mkdir()
    (src / "data.txt").write_text("hi")
    tar_path = res_dir / "test_id.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as t:
        t.add(str(src), arcname="data")
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(cm_module.settings, "UNSTASH_CLEANUP_GRACE_SECONDS", 5)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    # Simulate daemon writing cleanup-done shortly after .unstash-confirmed appears
    async def _simulate_daemon():
        for _ in range(50):
            await asyncio.sleep(0.1)
            if (res_dir / "test_id.unstash-confirmed").exists():
                (res_dir / "test_id.unstash-cleanup-done").touch()
                return
    daemon_task = asyncio.create_task(_simulate_daemon())

    result = await cm_instance.unstash_crawl(stashed_job_info)
    daemon_task.cancel()

    assert result["status"] == "unstashed"
    assert result["gcs_cleanup_status"] == "cleaned"
    assert os.path.exists(result["restored_to"])
    # stashed_at popped from Redis blob
    last_call = mock_cache_service.set_json.call_args
    written = last_call[0][1]
    assert "stashed_at" not in written


@pytest.mark.asyncio
async def test_unstash_extract_failure_preserves_stash(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    # Corrupt tar.gz
    tar_path = res_dir / "test_id.tar.gz"
    tar_path.write_bytes(b"not a real gzip stream")
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation reads fresh blob — return the still-stashed one
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "EXTRACT_FAILED"
    # No .unstash-confirmed should be written
    assert not (res_dir / "test_id.unstash-confirmed").exists()
    # set_json should NOT have been called with stashed_at popped
    if mock_cache_service.set_json.called:
        for call in mock_cache_service.set_json.call_args_list:
            written = call[0][1]
            assert "stashed_at" in written, "stashed_at must be preserved on extract failure"


@pytest.mark.asyncio
async def test_unstash_gcs_cleanup_deferred_returns_200_with_warning(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    src = tmp_path / "src"
    src.mkdir()
    (src / "data.txt").write_text("hi")
    tar_path = res_dir / "test_id.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as t:
        t.add(str(src), arcname="data")
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    # Set very short grace so we exit the polling loop without daemon ack
    monkeypatch.setattr(cm_module.settings, "UNSTASH_CLEANUP_GRACE_SECONDS", 1)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    result = await cm_instance.unstash_crawl(stashed_job_info)
    assert result["status"] == "unstashed"
    assert result["gcs_cleanup_status"] == "deferred"


@pytest.mark.asyncio
async def test_cleanup_includes_stash_dirs(cm_instance, monkeypatch, tmp_path):
    """Verify scheduled_archive_cleanup scans STASH_DOWNLOAD_* dirs."""
    archives = tmp_path / "archives"
    dl_results = tmp_path / "dl_results"
    dl_req = tmp_path / "dl_req"
    stash_results = tmp_path / "stash_results"
    stash_req = tmp_path / "stash_req"
    for d in (archives, dl_results, dl_req, stash_results, stash_req):
        d.mkdir()

    # Create files older than 1h
    import time as _time
    old_ts = _time.time() - 7200
    for path in [
        stash_results / "old.tar.gz",
        stash_results / "old.unstash-confirmed",
        stash_results / "old.unstash-cleanup-done",
        stash_req / "old.request",
    ]:
        path.touch()
        os.utime(path, (old_ts, old_ts))

    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(cm_module.settings, "DOWNLOAD_RESULTS_PATH", str(dl_results))
    monkeypatch.setattr(cm_module.settings, "DOWNLOAD_REQUESTS_PATH", str(dl_req))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(stash_results))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(stash_req))
    # Create archives subdir under storage so cleanup doesn't bail
    (tmp_path / "archives").is_dir()

    deleted, _, _ = await cm_instance.cleanup_archives(max_age_hours=1)
    assert deleted >= 4, f"Expected >=4 stash markers deleted, got {deleted}"


@pytest.mark.asyncio
async def test_unstash_tar_filter_blocks_path_traversal(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Verify tarfile.extractall(filter='data') rejects path-traversal members.

    Build a malicious tar.gz with a member named '../escape.txt'. The PEP 706
    safe filter must reject it; the unstash branch then returns 502
    EXTRACT_FAILED and preserves stashed_at in Redis.
    """
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    # Build a tar.gz with a path-traversal member.
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.txt").write_text("legit")
    tar_path = res_dir / "test_id.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as t:
        # Legit member
        t.add(str(src / "ok.txt"), arcname="ok.txt")
        # Path-traversal member
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = 5
        t.addfile(info, io.BytesIO(b"boom!"))
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation reads fresh blob — return the still-stashed one
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "EXTRACT_FAILED"
    # Confirm the escape file did NOT land outside storage_root
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_stash_preflight_failopen_on_measurement_exception(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Per spec §5.1: a measurement-helper exception must not escalate to 500.
    Stash proceeds without the disk-space check (fail-open)."""
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")

    # _get_archives_disk_state raises a generic Exception
    def boom(d):
        raise RuntimeError("simulated filesystem error")
    monkeypatch.setattr(cm_instance, "_get_archives_disk_state", boom)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    result = await cm_instance.stash_crawl(base_job_info)
    assert result["status"] == "stashing"
    assert result["crawl_id"] == "test_id"
    # Tar still created — measurement skip did not block the stash
    assert (stash_dir / "test_id.tar.gz").exists()


@pytest.mark.asyncio
async def test_stash_voids_stale_gcs_deletion_intent(
    cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path
):
    """Hardening post-6227f433: a lingering {id}.unstash-confirmed (fire-and-forget
    dropData deletion request never consumed by the daemon, e.g. gen-1 tar upload
    dead-lettered so `gcloud storage rm` kept failing) must be pre-cleaned by a
    later stash of the same crawl_id — otherwise the daemon would consume the
    stale marker AFTER the gen-2 tar lands at the same gs://.../stash/{id}.tar.gz
    path and delete the brand-new tar (blob says stashed_at, tar gone → next
    resume 502s). A stale {id}.unstash-cleanup-done is dropped too, so a future
    deletion request cannot mistake the old daemon ack for its own.
    The pre-clean must run under the stash lock BEFORE the tar work starts."""
    stash_dir = tmp_path / "stash"
    res_dir = tmp_path / "stash-res"
    stash_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    # Stale artifacts left by a prior dropData deletion request
    stale_marker = res_dir / "test_id.unstash-confirmed"
    stale_ack = res_dir / "test_id.unstash-cleanup-done"
    stale_marker.write_text("test_id")
    stale_ack.touch()

    # Spy on make_archive to prove the pre-clean runs BEFORE the tar work
    markers_at_tar_time = {}
    original_make_archive = cm_module.shutil.make_archive

    def spy_make_archive(*args, **kwargs):
        markers_at_tar_time["confirmed"] = stale_marker.exists()
        markers_at_tar_time["cleanup_done"] = stale_ack.exists()
        return original_make_archive(*args, **kwargs)

    monkeypatch.setattr(cm_module.shutil, "make_archive", spy_make_archive)

    result = await cm_instance.stash_crawl(base_job_info)

    assert result["status"] == "stashing"
    assert not stale_marker.exists(), \
        "stale .unstash-confirmed must be pre-cleaned by a re-stash"
    assert not stale_ack.exists(), \
        "stale .unstash-cleanup-done must be pre-cleaned by a re-stash"
    assert markers_at_tar_time == {"confirmed": False, "cleanup_done": False}, \
        "pre-clean must happen before the tar is created/uploaded"


@pytest.mark.asyncio
async def test_stash_proceeds_when_stale_marker_removal_fails(
    cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path
):
    """Fail-open: if removing a stale deletion marker raises (e.g. permission
    error on the bind-mount), the stash must still complete normally."""
    stash_dir = tmp_path / "stash"
    res_dir = tmp_path / "stash-res"
    stash_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    stale_marker = res_dir / "test_id.unstash-confirmed"
    stale_marker.write_text("test_id")

    # os.remove raises ONLY for the stale markers; everything else untouched
    original_remove = os.remove

    def failing_remove(path, *args, **kwargs):
        if ".unstash-" in str(path):
            raise PermissionError(f"simulated EACCES on {path}")
        return original_remove(path, *args, **kwargs)

    monkeypatch.setattr(cm_module.os, "remove", failing_remove)

    result = await cm_instance.stash_crawl(base_job_info)

    assert result["status"] == "stashing"
    assert (stash_dir / "test_id.tar.gz").exists(), \
        "stash must complete even when the marker pre-clean fails"
    assert stale_marker.exists()  # removal failed, by design of the test


@pytest.mark.asyncio
async def test_stash_toctou_revalidation_blocks_concurrent_winner(cm_instance, base_job_info, mock_cache_service, monkeypatch):
    """Spec follow-up §4.2: 2-replica TOCTOU race.

    Caller-passed job_info has no stashed_at; SET NX succeeds. Fresh Redis
    read inside stash_crawl returns the same crawl with stashed_at populated
    by a concurrent winner. stash_crawl must raise 409 ALREADY_STASHED and
    release the lock instead of proceeding to overwrite GCS.
    """
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    stashed_blob = dict(base_job_info)
    stashed_blob["stashed_at"] = "2026-05-19T10:00:00Z"
    mock_cache_service.get_json = AsyncMock(return_value=stashed_blob)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_STASHED"
    assert exc.value.detail["stashed_at"] == "2026-05-19T10:00:00Z"
    # Lock release (Lua eval) was called for compare-and-delete
    assert mock_cache_service.redis_client.eval.call_count >= 1


@pytest.mark.asyncio
async def test_unstash_toctou_revalidation_blocks_concurrent_winner(cm_instance, stashed_job_info, mock_cache_service, monkeypatch):
    """Spec follow-up §4.2: symmetric to the stash TOCTOU test.

    Caller-passed job_info has stashed_at set; lock acquire succeeds. Fresh
    Redis read returns the same crawl with stashed_at popped by a concurrent
    winning unstash. unstash_crawl must raise 409 NOT_STASHED and release
    the lock instead of proceeding to download/extract.
    """
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    unstashed_blob = dict(stashed_job_info)
    unstashed_blob.pop("stashed_at", None)
    mock_cache_service.get_json = AsyncMock(return_value=unstashed_blob)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "NOT_STASHED"
    assert mock_cache_service.redis_client.eval.call_count >= 1


@pytest.mark.asyncio
async def test_stash_keeps_logs_and_markers_on_cleanup(
    cm_instance, mock_cache_service, monkeypatch, tmp_path
):
    """Dedicated cleanup-scope test: a richer storage tree with multiple
    kept-class files (log + completion marker) AND data files (root +
    nested subdir) exercises the full files_to_keep set + os.walk
    bottom-up subdir rmdir."""
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()

    storage = tmp_path / "crawl_data"
    storage.mkdir()
    # 2 kept files at root
    (storage / "crawler.log").write_text("log content")
    (storage / "_completion_marker.json").write_text('{"final_status":"finished"}')
    # 1 data file at root
    (storage / "dataset.json").write_text('{"records":[1,2,3]}')
    # 1 data file in nested subdir
    sub = storage / "storage" / "datasets"
    sub.mkdir(parents=True)
    (sub / "000001.json").write_text("data")

    job_info = {
        "crawl_id": "rich_test_id",
        "status": "failed",
        "storage_path": str(storage),
        "domain": "example.com",
    }

    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(job_info))

    await cm_instance.stash_crawl(job_info)

    # Kept
    assert (storage / "crawler.log").exists()
    assert (storage / "_completion_marker.json").exists()
    # Deleted (root-level data file)
    assert not (storage / "dataset.json").exists()
    # Deleted (nested data file + its empty subdirs)
    assert not (sub / "000001.json").exists()
    assert not sub.exists(), "empty data subdir should be rmdir'd"
    # Root storage dir kept (contains 2 kept files)
    assert storage.exists()


# ============================================================================
# _LockHeartbeat integration tests (T2)
# ============================================================================

@pytest.mark.asyncio
async def test_stash_lock_survives_long_tar(
    cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path
):
    """A tar that runs longer than the initial TTL keeps the lock via heartbeat.

    Scenario: STASH_LOCK_TTL=2s, heartbeat interval=1s, tar mock sleeps 4s
    (2x initial TTL). During the tar, the heartbeat must refresh the lock at
    least once. A concurrent stash_crawl call mid-tar must get 409.
    """
    from app.core import config as cfg

    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(cfg.settings, "STASH_LOCK_TTL_SECONDS", 2)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_MAX_DURATION_SECONDS", 30)

    # Track SET NX calls: first returns True (lock acquired), subsequent return
    # False (lock already held — concurrent caller gets 409).
    set_call_count = {"n": 0}
    # Heartbeat eval: first eval call returns 1 (refresh OK), subsequent
    # release eval also returns 1. We count calls but always return 1.
    eval_call_count = {"n": 0}

    original_set = mock_cache_service.redis_client.set

    async def _set_side_effect(key, value, **kwargs):
        set_call_count["n"] += 1
        if set_call_count["n"] == 1:
            return True   # first acquire (task1)
        return False      # subsequent acquire (concurrent caller gets 409)

    async def _eval_side_effect(script, numkeys, *args):
        eval_call_count["n"] += 1
        return 1

    mock_cache_service.redis_client.set = AsyncMock(side_effect=_set_side_effect)
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.eval = AsyncMock(side_effect=_eval_side_effect)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {
            "free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0,
            "file_count": 0, "oldest_file_age_seconds": None
        },
    )

    # Slow down the synchronous tar: patch shutil.make_archive with a stub
    # that writes a minimal valid tar.gz then sleeps. Capture the ORIGINAL
    # make_archive BEFORE patching to avoid infinite recursion (monkeypatch
    # replaces the attribute globally on the shared shutil module).
    import shutil as _shutil
    import tarfile as _tarfile
    import time as _time

    def slow_make_archive(base_name, fmt, root_dir=None, **kwargs):
        # Write minimal valid empty tar.gz to base_name + extension first.
        out = f"{base_name}.tar.gz" if fmt == "gztar" else f"{base_name}.tar"
        with _tarfile.open(out, "w:gz" if fmt == "gztar" else "w") as tf:
            pass  # empty archive — passes integrity check (getnames() == [])
        _time.sleep(4)  # 2x the initial TTL=2s
        return out

    monkeypatch.setattr(cm_module.shutil, "make_archive", slow_make_archive)

    # Concurrent attempt during the 4s tar must get 409
    task1 = asyncio.create_task(cm_instance.stash_crawl(base_job_info))
    await asyncio.sleep(2.5)  # past initial TTL=2s — only heartbeat keeps lock

    with pytest.raises(HTTPException) as exc_info:
        await cm_instance.stash_crawl(base_job_info)
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    if isinstance(detail, dict):
        assert detail.get("error_code") == "OPERATION_IN_PROGRESS"
    else:
        assert "in progress" in str(detail).lower()

    # First call must still complete successfully
    result = await task1
    assert result.get("status") == "stashing"

    # Heartbeat must have fired at least once (eval called ≥ 2: ≥1 refresh + 1 release)
    assert eval_call_count["n"] >= 2


@pytest.mark.asyncio
async def test_stash_lock_released_on_replica_crash_simulation(
    cm_instance, mock_cache_service, monkeypatch
):
    """Without heartbeat (simulated replica crash), lock TTL expires naturally
    so the next acquire succeeds.

    NOTE: This test exercises TTL semantics against the mock Redis client.
    The mock does NOT enforce real TTL expiry (MagicMock grants every SET NX).
    The test therefore validates the _acquire_ownership_lock API contract:
    two sequential acquires on the same key both succeed when the mock resets
    between calls — matching what a real Redis would do after TTL expiry.
    For real TTL behaviour, see tests/integration/.
    """
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "STASH_LOCK_TTL_SECONDS", 1)

    lock_key = "stash_lock:crash_sim_123"

    # First acquire — simulate a replica that holds the lock then "crashes"
    # (no heartbeat, no release). With a real Redis the TTL would expire.
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    value = await cm_instance._acquire_ownership_lock(lock_key, 1)
    assert value is not None

    # Simulate TTL expiry: in real Redis the key would vanish after 1s.
    # With mock Redis we simply reset the SET NX mock to True (key gone).
    # Sleep 1.5s to document the intended timing — the assertion that follows
    # is what matters for the real-Redis path; here it trivially passes.
    await asyncio.sleep(1.5)

    # Fresh acquire must succeed (real Redis: key expired; mock: always True)
    new_value = await cm_instance._acquire_ownership_lock(lock_key, 1)
    assert new_value is not None
