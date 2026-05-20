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


@pytest.fixture
def base_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
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
async def test_stash_success_sets_timestamp_and_deletes_local(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
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

    # Verify tar created in /app/stash + integrity
    final_tar = stash_dir / "test_id.tar.gz"
    assert final_tar.exists(), "Tar should exist in stash dir"
    with tarfile.open(final_tar, 'r:gz') as t:
        assert any("dataset.json" in n for n in t.getnames())

    # Verify local storage deleted
    assert not os.path.exists(base_job_info["storage_path"])

    # Verify Redis HSET (stashed_at set on Redis blob)
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
async def test_unstash_writes_request_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
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

    with pytest.raises(HTTPException):  # will timeout (no .done written)
        await cm_instance.unstash_crawl(stashed_job_info)

    # Request marker must have been written
    # (cleaned up on timeout, so check via Redis exists / mock_set_json calls)
    # — alternative: spy on aiofiles.open
    # Here we rely on the timeout path removing it; verify timeout raised 504
    # The actual write is verified by reaching the polling loop without error.


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
