# tests/test_recover_no_clobber.py
"""get_job_or_recover must never overwrite a live Redis blob with a disk stub.

cache_service.get_json swallows a transient Redis error and returns None, which
is indistinguishable from "key absent". The recovery path then rebuilds an
8-field stub from disk; writing it with set_json destroyed the real blob:

  - status 'archived' -> 'finished' (the completion marker only ever carries
    finished/failed/stopped, so 'archived' is unrepresentable on disk), which
    makes get_results_archive skip its GCS branch -> /results 404s;
  - stashed_at and failure_callback_url dropped;
  - a key every other writer keeps persistent given a 7-day TTL -- after which
    it expires, is genuinely missing, and gets re-stubbed. Self-sustaining.

Measured on PROD 2026-08-07 (3-day log window): 345 recoveries over 266
distinct crawl_ids, rebuilt as 'finished' in 345 cases out of 345; 60/60
sampled blobs were stubs, and 24/24 of those had no local dataset left.

SET NX makes the phantom miss harmless: an existing blob wins, a genuinely
absent one is still indexed.
"""
import inspect
import json

import pytest
from unittest.mock import AsyncMock, patch

JOB_KEY = "crawl_job:6712"


def _storage_with_marker(tmp_path, crawl_id="6712", final_status="finished"):
    d = tmp_path / crawl_id
    d.mkdir()
    (d / "_completion_marker.json").write_text(json.dumps({"final_status": final_status}))
    return d


@pytest.mark.asyncio
async def test_recovery_indexes_with_nx_and_never_calls_set_json(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.router import crawler as mod

    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path), raising=False)
    _storage_with_marker(tmp_path)

    with patch.object(mod.cache_service, "get_json", AsyncMock(return_value=None)), \
         patch.object(mod.cache_service, "set_json", AsyncMock()) as set_json, \
         patch.object(mod.cache_service, "set_json_nx", AsyncMock(return_value=True)) as set_nx:
        recovered = await mod.get_job_or_recover("6712")

    set_json.assert_not_awaited()
    assert set_nx.await_count == 1
    args, kwargs = set_nx.await_args
    assert args[0] == JOB_KEY
    # The 7-day TTL of the original design is preserved: a genuinely orphaned
    # job must not linger in Redis forever.
    assert kwargs["ttl"] == 604800
    assert recovered["status"] == "finished"
    assert recovered["crawl_id"] == "6712"


@pytest.mark.asyncio
async def test_phantom_miss_does_not_destroy_the_existing_blob(tmp_path, monkeypatch):
    """Read errored but the key is really there: NX refuses, nothing is lost.

    The caller still gets a usable answer for this one request (degraded, and
    the client-side retry in init_redis_pool makes that window rare) -- what
    matters is that the live blob survives.
    """
    from app.core.config import settings
    from app.router import crawler as mod

    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path), raising=False)
    _storage_with_marker(tmp_path)

    with patch.object(mod.cache_service, "get_json", AsyncMock(return_value=None)), \
         patch.object(mod.cache_service, "set_json", AsyncMock()) as set_json, \
         patch.object(mod.cache_service, "set_json_nx", AsyncMock(return_value=False)) as set_nx:
        recovered = await mod.get_job_or_recover("6712")

    set_json.assert_not_awaited()
    assert set_nx.await_count == 1
    assert recovered["crawl_id"] == "6712"


@pytest.mark.asyncio
async def test_missing_storage_dir_still_404s(tmp_path, monkeypatch):
    """Unchanged behaviour: no blob and no storage subtree is a real 404."""
    from fastapi import HTTPException
    from app.core.config import settings
    from app.router import crawler as mod

    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path), raising=False)

    with patch.object(mod.cache_service, "get_json", AsyncMock(return_value=None)), \
         patch.object(mod.cache_service, "set_json_nx", AsyncMock(return_value=True)) as set_nx:
        with pytest.raises(HTTPException) as exc:
            await mod.get_job_or_recover("nope")

    assert exc.value.status_code == 404
    set_nx.assert_not_awaited()


def test_recovery_source_holds_no_plain_set_json():
    """Regression lock: a future edit must not reintroduce the clobbering write."""
    from app.router.crawler import get_job_or_recover

    src = inspect.getsource(get_job_or_recover)
    assert "set_json_nx(" in src, "recovery must index the stub with SET NX"
    assert "cache_service.set_json(" not in src, (
        "recovery must never write the disk stub unconditionally -- it can land "
        "on a live blob whose read merely errored"
    )
