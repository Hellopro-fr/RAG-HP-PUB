"""Eligibility predicate matrix (auto-stash P2, Task 7)."""
from datetime import datetime, timedelta
import pytest
from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


@pytest.fixture
def mgr():
    return CrawlerManager()


def _now():
    return datetime(2026, 6, 1, 12, 0, 0)


def test_grace_elapsed_eligible(mgr):
    dl = (_now() - timedelta(seconds=settings.STASH_GRACE_SECONDS + 1)).isoformat()
    job = {"status": "finished", "downloaded_at": dl}
    assert mgr._is_stash_eligible(job, _now()) == (True, "grace")


def test_grace_not_elapsed_not_eligible(mgr):
    dl = (_now() - timedelta(seconds=10)).isoformat()
    job = {"status": "finished", "downloaded_at": dl}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_safety_timeout_eligible_when_never_downloaded(mgr):
    fin = (_now() - timedelta(seconds=settings.STASH_SAFETY_TIMEOUT_SECONDS + 1)).isoformat()
    job = {"status": "failed", "finished_at": fin}
    assert mgr._is_stash_eligible(job, _now()) == (True, "timeout")


def test_fresh_download_grace_governs_over_old_finish(mgr):
    """A just-downloaded crawl that finished long ago is NOT eligible: grace
    governs exclusively when downloaded_at is present (timeout must not override
    a fresh download's grace)."""
    job = {
        "status": "finished",
        "downloaded_at": (_now() - timedelta(seconds=30)).isoformat(),
        "finished_at": (_now() - timedelta(seconds=settings.STASH_SAFETY_TIMEOUT_SECONDS + 99999)).isoformat(),
    }
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_unparseable_download_falls_through_to_timeout(mgr):
    """If downloaded_at is garbage, fall through to the safety-timeout path."""
    job = {
        "status": "finished",
        "downloaded_at": "not-a-date",
        "finished_at": (_now() - timedelta(seconds=settings.STASH_SAFETY_TIMEOUT_SECONDS + 1)).isoformat(),
    }
    assert mgr._is_stash_eligible(job, _now()) == (True, "timeout")


@pytest.mark.parametrize("status", ["running", "restarting_oom", "stopping", "archived"])
def test_non_terminal_or_archived_not_eligible(mgr, status):
    job = {"status": status, "finished_at": "2000-01-01T00:00:00"}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_already_stashed_not_eligible(mgr):
    job = {"status": "finished", "stashed_at": "t", "finished_at": "2000-01-01T00:00:00"}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)


def test_garbage_timestamps_do_not_raise(mgr):
    job = {"status": "finished", "downloaded_at": "not-a-date", "finished_at": "nope"}
    assert mgr._is_stash_eligible(job, _now()) == (False, None)
