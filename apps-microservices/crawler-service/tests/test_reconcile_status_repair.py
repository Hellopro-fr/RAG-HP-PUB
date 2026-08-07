# tests/test_reconcile_status_repair.py
"""Reconciliation-side wiring of the archived-status repair.

Task 2 covers the refactor (allowlist hoisted, finished blobs accumulated);
Task 3 adds the pass itself to this same file.
"""
import inspect
import re

import pytest
from unittest.mock import AsyncMock, patch

from app.core.crawler_manager import CrawlerManager


def test_reclean_receives_the_allowlist_instead_of_loading_it():
    src = inspect.getsource(CrawlerManager._reclean_archived_leftovers)
    assert "_load_reclean_allowlist" not in src, (
        "the allowlist must be loaded once in _reconcile_locked and passed in, "
        "so the repair pass and the reclean share one read"
    )
    sig = inspect.signature(CrawlerManager._reclean_archived_leftovers)
    assert "verified" in sig.parameters


@pytest.mark.asyncio
async def test_reclean_still_deletes_nothing_without_an_allowlist():
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_cleanup_local_data") as cleanup:
        actioned = await mgr._reclean_archived_leftovers(
            [{"crawl_id": "1", "storage_path": "/nope"}], set(), None)
    assert actioned == 0
    cleanup.assert_not_called()


def test_reconcile_collects_finished_candidates():
    src = inspect.getsource(CrawlerManager._reconcile_locked)
    assert "finished_candidates" in src, (
        "the scan loop only collected status=='archived'; the repair pass needs "
        "the finished blobs from the same pass over the pipeline results"
    )
    assert src.count("_load_reclean_allowlist") == 1, (
        "exactly one allowlist read per tick"
    )


def test_allowlist_load_skipped_when_nothing_will_consume_it():
    """The hoisted read must stay gated on the condition that used to guard it
    from inside _reclean_archived_leftovers — otherwise it runs (and, on a
    missing allowlist file, logs a warning) on every tick forever, even with
    both consumers off or empty. Task 3 widens the gate to admit the repair
    pass as a second consumer: the read must still be skipped unless AT LEAST
    ONE of the two consumers will use it."""
    src = inspect.getsource(CrawlerManager._reconcile_locked)
    pattern = re.compile(
        r"_load_reclean_allowlist\(\)\s*"
        r"if\s*\(*\s*settings\.ARCHIVED_RECLEAN_ENABLED\s+and\s+archived_candidates\s*\)*\s*"
        r"or\s*\(*\s*settings\.ARCHIVED_STATUS_REPAIR_ENABLED\s+and\s+finished_candidates\s*\)*\s*"
        r"else\s+None",
        re.DOTALL,
    )
    assert pattern.search(src), (
        "the allowlist load must be conditioned on "
        "'(ARCHIVED_RECLEAN_ENABLED and archived_candidates) or "
        "(ARCHIVED_STATUS_REPAIR_ENABLED and finished_candidates)', not run unconditionally"
    )


# --- Task 3: the pass itself ------------------------------------------------

import os
import time

from app.core.config import settings


def _job(crawl_id="6712", status="finished", **over):
    j = {"crawl_id": crawl_id, "status": status, "storage_path": f"/app/storage/{crawl_id}"}
    j.update(over)
    return j


def _stat_map(snapshot=200.0, log=100.0):
    """os.path.getmtime side_effect: snapshot newer than log == archived, untouched."""
    def _getmtime(path):
        if path.endswith("_status_snapshot.json"):
            if snapshot is None:
                raise FileNotFoundError(path)
            return snapshot
        if path.endswith("crawler.log"):
            if log is None:
                raise FileNotFoundError(path)
            return log
        raise FileNotFoundError(path)
    return _getmtime


@pytest.fixture
def repair_on(monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_MAX_PER_TICK", 10, raising=False)


@pytest.mark.asyncio
async def test_flag_off_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_ENABLED", False, raising=False)
    mgr = CrawlerManager()
    archived = []
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch("app.core.crawler_manager.os.path.getmtime") as gm:
        n = await mgr._repair_archived_status([_job()], {"6712"}, archived)
    assert n == 0
    mark.assert_not_awaited()
    gm.assert_not_called()
    assert archived == []


@pytest.mark.asyncio
async def test_no_allowlist_writes_nothing(repair_on):
    mgr = CrawlerManager()
    archived = []
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark:
        n = await mgr._repair_archived_status([_job()], None, archived)
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_not_in_gcs_list_skips_before_the_stat_block(repair_on):
    """Conditions 1-3 are free (finished_candidates is already all-'finished',
    stashed_at is a dict lookup, allowlist membership is a set lookup) and
    reject nearly all candidates — os.stat is real I/O and must not run for a
    candidate the allowlist alone already rejects."""
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch("app.core.crawler_manager.os.path.getmtime") as gm:
        n = await mgr._repair_archived_status([_job(crawl_id="9999")], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()
    gm.assert_not_called()


@pytest.mark.asyncio
async def test_repairs_and_hands_the_job_to_the_reclean(repair_on):
    mgr = CrawlerManager()
    archived = []
    job = _job()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()), \
         patch("app.core.crawler_manager.cache_service.get_json",
               AsyncMock(return_value={"crawl_id": "6712", "status": "finished"})):
        n = await mgr._repair_archived_status([job], {"6712"}, archived)
    assert n == 1
    mark.assert_awaited_once_with("6712")
    assert job["status"] == "archived"
    assert archived == [job], "a repaired job must be recleanable in the same tick"


@pytest.mark.asyncio
async def test_respects_the_per_tick_cap(repair_on, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_MAX_PER_TICK", 2, raising=False)
    mgr = CrawlerManager()
    jobs = [_job(crawl_id=str(i)) for i in range(5)]
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()), \
         patch("app.core.crawler_manager.cache_service.get_json",
               AsyncMock(return_value={"status": "finished"})):
        n = await mgr._repair_archived_status(jobs, {str(i) for i in range(5)}, [])
    assert n == 2
    assert mark.await_count == 2


@pytest.mark.asyncio
async def test_stale_relaunched_job_is_not_repaired(repair_on):
    """The predicate judged a snapshot taken at scan time, possibly thousands of
    blobs (and awaits) ago. A fresh re-read showing the crawl is no longer
    'finished' (e.g. relaunched to 'running') must veto the write — otherwise a
    live crawl gets flipped to 'archived' out from under its own process."""
    mgr = CrawlerManager()
    archived = []
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()), \
         patch("app.core.crawler_manager.cache_service.get_json",
               AsyncMock(return_value={"crawl_id": "6712", "status": "running"})):
        n = await mgr._repair_archived_status([_job()], {"6712"}, archived)
    assert n == 0
    mark.assert_not_awaited()
    assert archived == []


@pytest.mark.asyncio
async def test_vanished_job_is_not_repaired(repair_on):
    """cache_service.get_json returns None for BOTH 'absent' and 'read errored' —
    either way, a repair must not proceed on it."""
    mgr = CrawlerManager()
    archived = []
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()), \
         patch("app.core.crawler_manager.cache_service.get_json",
               AsyncMock(return_value=None)):
        n = await mgr._repair_archived_status([_job()], {"6712"}, archived)
    assert n == 0
    mark.assert_not_awaited()
    assert archived == []


@pytest.mark.asyncio
async def test_archive_lock_absent_is_not_held():
    mgr = CrawlerManager()
    fake = AsyncMock()
    fake.exists = AsyncMock(return_value=0)
    with patch("app.core.crawler_manager.cache_service.redis_client", fake):
        assert await mgr._archive_lock_held("6712") is False
    fake.exists.assert_awaited_once_with("archive_lock:6712", "stash_lock:6712")


@pytest.mark.asyncio
async def test_no_redis_client_is_fail_closed():
    mgr = CrawlerManager()
    with patch("app.core.crawler_manager.cache_service.redis_client", None):
        assert await mgr._archive_lock_held("6712") is True


@pytest.mark.asyncio
async def test_archive_in_progress_is_skipped(repair_on):
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=True)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()):
        n = await mgr._repair_archived_status([_job()], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreadable_sidecar_skips_the_crawl(repair_on):
    """PermissionError is not "file absent" — it must not become a rejection
    bucket, it must take the crawl out of consideration."""
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime",
               side_effect=PermissionError("EACCES")):
        n = await mgr._repair_archived_status([_job()], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_recrawled_job_is_not_repaired(repair_on):
    """crawler.log newer than the snapshot: a run finished after the archive."""
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime",
               side_effect=_stat_map(snapshot=100.0, log=300.0)):
        n = await mgr._repair_archived_status([_job()], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_lock_probe_failure_is_fail_closed():
    mgr = CrawlerManager()
    fake = AsyncMock()
    fake.exists = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("app.core.crawler_manager.cache_service.redis_client", fake):
        assert await mgr._archive_lock_held("6712") is True


def test_pass_never_builds_a_blob():
    src = inspect.getsource(CrawlerManager._repair_archived_status)
    assert "_mark_as_archived" in src
    assert "set_json" not in src, (
        "the repair must go through _mark_as_archived (fresh re-read, TTL cleared, "
        "publish), never write a blob of its own"
    )


def test_pass_runs_before_the_reclean():
    src = inspect.getsource(CrawlerManager._reconcile_locked)
    assert src.index("_repair_archived_status") < src.index("_reclean_archived_leftovers"), (
        "repair must run first, or a repaired job waits a whole tick for cleanup"
    )


@pytest.mark.asyncio
async def test_repaired_job_is_recleaned_in_the_same_tick(monkeypatch, tmp_path):
    """Pins the design's most delicate ordering property (spec S5):
    archived_candidates starts EMPTY, is populated SOLELY by the repair pass,
    and is then consumed by the reclean in the same tick. It works only
    because _reconcile_locked runs the reclean right after the repair returns
    (test_pass_runs_before_the_reclean pins the source order; this test pins
    that the actual hand-off produces a real deletion, not just a list
    append). Real tmp dirs, like test_crawler_manager_reclean.py, rather than
    mocking os.path.getmtime — the reclean's own age gate reads a real mtime
    off the 'storage' subtree that _repair_archived_status never touches."""
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_MAX_PER_TICK", 10, raising=False)
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_MIN_AGE_SECONDS", 1, raising=False)
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_MAX_PER_TICK", 3, raising=False)

    root = tmp_path / "6712"
    (root / "storage" / "datasets").mkdir(parents=True)
    (root / "storage" / "datasets" / "000000001.json").write_text("{}")
    (root / "crawler.log").write_text("log\n")
    (root / "_status_snapshot.json").write_text("{}")
    old = time.time() - 200000  # settled archive: log older than snapshot, both ancient
    os.utime(root / "crawler.log", (old, old))
    os.utime(root / "_status_snapshot.json", (old + 50, old + 50))
    os.utime(root / "storage", (old + 50, old + 50))

    job = {"crawl_id": "6712", "status": "finished", "storage_path": str(root)}
    archived_candidates = []  # starts empty — the property under test

    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()), \
         patch("app.core.crawler_manager.cache_service.get_json",
               AsyncMock(return_value={"crawl_id": "6712", "status": "finished"})):
        repaired = await mgr._repair_archived_status([job], {"6712"}, archived_candidates)

    assert repaired == 1
    assert archived_candidates == [job], (
        "archived_candidates must be populated SOLELY by the repair pass"
    )

    actioned = await mgr._reclean_archived_leftovers(archived_candidates, set(), {"6712"})

    assert actioned == 1, "the reclean must consume the job the repair pass just appended"
    assert not (root / "storage").exists()
    assert (root / "crawler.log").is_file(), "sidecars at the crawl-dir root are kept"
