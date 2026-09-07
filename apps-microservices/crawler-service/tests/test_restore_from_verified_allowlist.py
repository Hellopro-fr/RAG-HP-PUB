"""Third recovery path: restore a reference crawl whose Redis blob is gone but whose
tar is GCS-verified.

Spec: docs/superpowers/specs/2026-09-02-restore-from-verified-allowlist-design.md

The tests that carry the weight are the fail-closed ones — they pin an ABSENCE (nothing
is attempted without an allowlist). A test of the happy path alone would pass just as
well with a fail-OPEN condition, which is precisely the defect not to introduce.
"""
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock
import os as _os

import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


# ---------------------------------------------------------------------------
# _is_archive_gcs_verified — the fail-closed predicate, tested in isolation
# ---------------------------------------------------------------------------

def test_gcs_verified_false_when_allowlist_absent():
    """No allowlist file => _load_reclean_allowlist returns None => never attempt.

    This is the guard that keeps behaviour byte-identical on any install without an
    allowlist. It must not be relaxed into "unknown means try".
    """
    mgr = CrawlerManager()
    mgr._load_reclean_allowlist = MagicMock(return_value=None)
    assert mgr._is_archive_gcs_verified("4688") is False


def test_gcs_verified_false_when_allowlist_empty():
    """An EMPTY allowlist is a valid state that must reject, not raise.

    Distinct from the absent case: the file exists and lists nothing.
    """
    mgr = CrawlerManager()
    mgr._load_reclean_allowlist = MagicMock(return_value=set())
    assert mgr._is_archive_gcs_verified("4688") is False


def test_gcs_verified_false_when_id_not_listed():
    """3559 measured 2026-09-02: its tar is genuinely not in GCS, the 400 is correct."""
    mgr = CrawlerManager()
    mgr._load_reclean_allowlist = MagicMock(return_value={"4688", "7046"})
    assert mgr._is_archive_gcs_verified("3559") is False


def test_gcs_verified_true_when_id_listed():
    mgr = CrawlerManager()
    mgr._load_reclean_allowlist = MagicMock(return_value={"4688", "7046"})
    assert mgr._is_archive_gcs_verified("4688") is True


def test_gcs_verified_compares_as_string():
    """The allowlist is read from a text file; a crawl_id may arrive as an int.

    Same trap as script_lancer_enqueue_crawling.php:1081 ("do not int-cast"): a strict
    comparison between an int and the file's strings would silently never match.
    """
    mgr = CrawlerManager()
    mgr._load_reclean_allowlist = MagicMock(return_value={"4688"})
    assert mgr._is_archive_gcs_verified(4688) is True


# ---------------------------------------------------------------------------
# start_crawl — the branch itself
# ---------------------------------------------------------------------------

_SENTINEL = 599  # proves the restore path was entered, and stops before the subprocess


def _scaffold(monkeypatch, tmp_path, prev_blob):
    """Minimal start_crawl harness. Mirrors test_auto_stash_update_restore.py.

    `isdir` deliberately distinguishes the two directories the code checks: the
    previous crawl's STORAGE dir must exist (otherwise the earlier "neither blob nor
    directory" branch raises its own 400 and never reaches the path under test), while
    its DATASETS dir must not (that is what makes has_local_data false).
    """
    _UnameStub = namedtuple(
        "uname_result", ["sysname", "nodename", "release", "version", "machine"]
    )
    monkeypatch.setattr(
        _os, "uname",
        lambda: _UnameStub("Linux", "test-replica", "5.0", "#1", "x86_64"),
        raising=False,
    )
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))

    cache_mocks = {
        "get_key": AsyncMock(),
        "set_json": AsyncMock(),
        "increment_key": AsyncMock(),
        "safe_decrement_key": AsyncMock(),
        "delete_key": AsyncMock(),
        "get_json": AsyncMock(),
    }
    for name, mock in cache_mocks.items():
        monkeypatch.setattr(cm_module.cache_service, name, mock)

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    monkeypatch.setattr(cm_module.cache_service, "redis_client", redis_mock)

    cache_mocks["get_key"].side_effect = ["10", "1"]   # max_global, running
    cache_mocks["increment_key"].return_value = 2

    cache_mocks["get_json"].side_effect = (
        lambda key: prev_blob if key == "crawl_job:100" else None
    )

    monkeypatch.setattr(_os.path, "isdir", lambda p: "datasets" not in str(p))

    manager = CrawlerManager()
    manager.local_processes = {}
    manager._cleanup_stale_state_for_relaunch = AsyncMock()
    manager._restore_previous_crawl = AsyncMock()
    manager._restore_archived_crawl = AsyncMock(
        side_effect=HTTPException(status_code=_SENTINEL, detail="sentinel")
    )
    return manager, cache_mocks


async def _start(manager):
    return await manager.start_crawl(
        crawl_id="200",
        domain="example.com",
        start_url="https://example.com/",
        callback_url="https://example.com/cb",
        failure_callback_url=None,
        params={"crawlMode": "update", "previousCrawlId": "100"},
    )


@pytest.mark.asyncio
async def test_no_blob_but_gcs_verified_attempts_restore(monkeypatch, tmp_path):
    """The dead end measured on 4688: no blob, no local data, tar verified in GCS.

    Before this path existed, start_crawl raised 400 here and the update replayed it
    forever. The sentinel proves _restore_archived_crawl was entered with the previous
    crawl's id — and that the 400 was NOT raised.
    """
    manager, _ = _scaffold(monkeypatch, tmp_path, prev_blob=None)
    manager._is_archive_gcs_verified = MagicMock(return_value=True)

    with pytest.raises(HTTPException) as exc:
        await _start(manager)

    assert exc.value.status_code == _SENTINEL, "the restore path was not taken"
    manager._restore_archived_crawl.assert_awaited_once_with("100")
    # The blob is missing, so the blob-dispatching helper must not be used.
    manager._restore_previous_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_no_allowlist_still_rejects_400_and_attempts_nothing(monkeypatch, tmp_path):
    """THE test that matters: without an allowlist, nothing is attempted.

    Pins the absence. Were the condition fail-OPEN, this would attempt a restore for
    every reference crawl whose data is gone — including those whose tar does not exist.
    """
    manager, cache_mocks = _scaffold(monkeypatch, tmp_path, prev_blob=None)
    manager._load_reclean_allowlist = MagicMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await _start(manager)

    assert exc.value.status_code == 400
    manager._restore_archived_crawl.assert_not_called()
    manager._restore_previous_crawl.assert_not_called()
    cache_mocks["safe_decrement_key"].assert_awaited_once()   # claim rolled back


@pytest.mark.asyncio
async def test_id_absent_from_allowlist_still_rejects_400(monkeypatch, tmp_path):
    """3559's shape: the allowlist exists and does not list this crawl."""
    manager, _ = _scaffold(monkeypatch, tmp_path, prev_blob=None)
    manager._load_reclean_allowlist = MagicMock(return_value={"4688", "7046"})

    with pytest.raises(HTTPException) as exc:
        await _start(manager)

    assert exc.value.status_code == 400
    manager._restore_archived_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_failed_previous_crawl_is_not_resurrected(monkeypatch, tmp_path):
    """A previous crawl explicitly in status 'failed' must stay rejected.

    Its 400 is raised before the dataset check, so the allowlist must never even be
    consulted — a GCS-verified tar does not make a failed crawl usable.
    """
    manager, _ = _scaffold(
        monkeypatch, tmp_path, prev_blob={"crawl_id": "100", "status": "failed"}
    )
    manager._is_archive_gcs_verified = MagicMock(return_value=True)

    with pytest.raises(HTTPException) as exc:
        await _start(manager)

    assert exc.value.status_code == 400
    manager._is_archive_gcs_verified.assert_not_called()
    manager._restore_archived_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_archived_blob_keeps_the_existing_route(monkeypatch, tmp_path):
    """Non-regression: an 'archived' blob still goes through _restore_previous_crawl.

    The new path must not steal the existing one, whose blob dispatch also covers the
    stashed case.
    """
    manager, _ = _scaffold(
        monkeypatch, tmp_path, prev_blob={"crawl_id": "100", "status": "archived"}
    )
    manager._is_archive_gcs_verified = MagicMock(return_value=True)
    manager._restore_previous_crawl = AsyncMock(
        side_effect=HTTPException(status_code=_SENTINEL, detail="sentinel")
    )

    with pytest.raises(HTTPException) as exc:
        await _start(manager)

    assert exc.value.status_code == _SENTINEL
    manager._restore_previous_crawl.assert_awaited_once()
    manager._restore_archived_crawl.assert_not_called()
    # An archived blob is self-sufficient: the allowlist is short-circuited.
    manager._is_archive_gcs_verified.assert_not_called()
