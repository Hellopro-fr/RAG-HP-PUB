"""archive_crawl stashed-branch move (auto-stash P3, Task 12)."""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def mgr(monkeypatch, tmp_path):
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value={"crawl_id": "70", "stashed_at": "t"})
    cache.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", cache)
    m = CrawlerManager()
    m._mark_as_archived = AsyncMock()
    return m, cache, tmp_path


def _iso_offset_from(path: str, seconds: float) -> str:
    """Naive-UTC ISO string `seconds` away from the mtime of `path`.

    Exact inverse of the conversion _move_done_is_fresh performs, so a test can
    place stashed_at on either side of a real file's mtime without guessing the
    clock.
    """
    ts = os.path.getmtime(path) + seconds
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None).isoformat()


def _epoch_of(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


STASH_ISO = "2026-01-01T00:00:00"


def test_predicate_absent_marker_is_not_fresh():
    """No marker means nothing to honour."""
    assert cm_module._move_done_is_fresh(None, STASH_ISO) is False


def test_predicate_marker_newer_than_stash_is_fresh():
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO) + 1, STASH_ISO) is True


def test_predicate_marker_older_than_stash_is_stale():
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO) - 1, STASH_ISO) is False


def test_predicate_equal_timestamps_are_stale():
    """Strictly newer: a stash and an archive inside the same second read as stale.
    We then delete, re-request, and the daemon replays its idempotent already-moved
    branch -- one extra round trip, correct outcome. The error leans the safe way."""
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO), STASH_ISO) is False


@pytest.mark.parametrize("stashed_at", [None, "", "t", "not-a-date"])
def test_predicate_without_usable_stashed_at_is_stale(stashed_at):
    """Absence of proof is not proof: without a parsable stashed_at we cannot
    establish that a marker is ours, so we do not honour it."""
    assert cm_module._move_done_is_fresh(_epoch_of(STASH_ISO) + 1, stashed_at) is False


@pytest.mark.asyncio
async def test_archive_stashed_routes_to_move(mgr):
    m, cache, _ = mgr
    m._move_stash_to_archive = AsyncMock()
    job = {"crawl_id": "70", "status": "finished", "stashed_at": "2026-01-01T00:00:00"}
    result = await m.archive_crawl(job)
    m._move_stash_to_archive.assert_awaited_once_with(job)
    assert result["archive_status"] == "pending_upload"


@pytest.mark.asyncio
async def test_archive_stashed_but_failed_does_not_move(mgr):
    """A stashed FAILED crawl must NOT take the move path; it falls through to
    the finished-only 400 guard (archive is for finished crawls only)."""
    m, cache, _ = mgr
    m._move_stash_to_archive = AsyncMock()
    job = {"crawl_id": "70", "status": "failed", "stashed_at": "2026-01-01T00:00:00"}
    with pytest.raises(HTTPException) as exc:
        await m.archive_crawl(job)
    assert exc.value.status_code == 400
    m._move_stash_to_archive.assert_not_called()


@pytest.mark.asyncio
async def test_move_success_marks_archived(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        # The stash began BEFORE the marker was written -> the marker is this
        # stash's, so the freshness guard honours it (504-reconciliation path).
        await m._move_stash_to_archive(
            {"crawl_id": "70", "stashed_at": _iso_offset_from(done, -10)})
    m._mark_as_archived.assert_awaited_once_with("70")


@pytest.mark.asyncio
async def test_move_reconciles_preexisting_done_without_new_request(mgr):
    """Prior-504 limbo recovery: a FRESH pre-existing .move-done is reconciled
    (mark archived) WITHOUT writing a fresh .move-request."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        await m._move_stash_to_archive(
            {"crawl_id": "70", "stashed_at": _iso_offset_from(done, -10)})
        # No fresh request written — it reconciled the existing done marker.
        assert not os.path.exists(os.path.join(s.MOVE_REQUESTS_PATH, "70.move-request"))
    m._mark_as_archived.assert_awaited_once_with("70")


@pytest.mark.asyncio
async def test_move_error_raises_502(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        open(os.path.join(s.MOVE_RESULTS_PATH, "70.move-error"), "w").close()
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 502
        # 502 path removes BOTH the error marker and the request (no stale request).
        assert not os.path.exists(os.path.join(s.MOVE_RESULTS_PATH, "70.move-error"))
        assert not os.path.exists(os.path.join(s.MOVE_REQUESTS_PATH, "70.move-request"))


@pytest.mark.asyncio
async def test_move_timeout_raises_504_and_removes_request(mgr):
    """No .move-done/.move-error within MOVE_TIMEOUT_SECONDS -> 504, and the
    stale .move-request is removed so the daemon won't later process it."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1  # one poll tick then timeout
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 504
        assert not os.path.exists(os.path.join(s.MOVE_REQUESTS_PATH, "70.move-request"))


@pytest.mark.asyncio
async def test_move_stale_marker_is_deleted_and_move_replayed(mgr):
    """The bug this closes: an orphan .move-done from an earlier attempt made a
    later stash->crawls move be skipped, leaving the tar under stash/ while Redis
    said archived. The stale marker must be deleted and the move re-requested."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1  # one poll tick then timeout
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        # The stash began AFTER the marker -> the marker is an older attempt's.
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive(
                {"crawl_id": "70", "stashed_at": _iso_offset_from(done, +10)})
        # 504 proves the normal request+poll branch ran instead of reconciling.
        assert exc.value.status_code == 504
        assert not os.path.exists(done)
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_marker_without_stashed_at_is_treated_as_stale(mgr):
    """No stashed_at means no way to prove the marker is ours -> do not honour it."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 504
        assert not os.path.exists(done)
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_marker_vanishing_at_stat_is_treated_as_absent(mgr):
    """FileNotFoundError at getmtime = the marker disappeared between the exists
    check and the stat (race with the daemon or another replica). That is 'absent',
    not 'stale': the normal flow is already the right answer, and no 502 is due.
    The side effect really removes the file, so the exists() test three lines down
    sees what it would see in the real race."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()

        def _vanish(path):
            os.remove(path)  # the daemon (or another replica) got there first
            raise FileNotFoundError(path)

        with patch("app.core.crawler_manager.os.path.getmtime", side_effect=_vanish):
            with pytest.raises(HTTPException) as exc:
                await m._move_stash_to_archive(
                    {"crawl_id": "70", "stashed_at": "2026-01-01T00:00:00"})
        assert exc.value.status_code == 504  # timeout, not STASH_MOVE_STALE_MARKER
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_unreadable_marker_is_treated_as_stale(mgr):
    """Unreadable is not absent: a marker we cannot stat cannot be proven ours, so
    it must not be honoured. _mtime_or_none deliberately lets any OSError other
    than FileNotFoundError propagate (crawler_manager.py:86-88) — this pins the
    guard's handling of it."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        with patch("app.core.crawler_manager.os.path.getmtime",
                   side_effect=PermissionError("EACCES")):
            with pytest.raises(HTTPException) as exc:
                await m._move_stash_to_archive(
                    {"crawl_id": "70", "stashed_at": "2026-01-01T00:00:00"})
        assert exc.value.status_code == 504  # deleted, then normal flow timed out
        assert not os.path.exists(done)
    m._mark_as_archived.assert_not_called()


@pytest.mark.asyncio
async def test_move_undeletable_stale_marker_raises_502_without_archiving(mgr):
    """The assertion that matters: marking archived here would BE the bug, since
    the tar would still sit under stash/. An undeletable marker in the results dir
    is an infrastructure problem, not a situation to work around."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        done = os.path.join(s.MOVE_RESULTS_PATH, "70.move-done")
        open(done, "w").close()
        stashed_at = _iso_offset_from(done, +10)
        with patch("app.core.crawler_manager.os.remove",
                   side_effect=OSError("EPERM")):
            with pytest.raises(HTTPException) as exc:
                await m._move_stash_to_archive(
                    {"crawl_id": "70", "stashed_at": stashed_at})
        assert exc.value.status_code == 502
        assert exc.value.detail == {"error_code": "STASH_MOVE_STALE_MARKER"}
    m._mark_as_archived.assert_not_called()
