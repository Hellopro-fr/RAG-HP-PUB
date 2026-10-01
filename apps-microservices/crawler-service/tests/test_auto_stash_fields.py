"""Unit tests for terminal-transition field stamping (auto-stash P1, Task 1)."""
from unittest.mock import patch
import pytest

from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def manager():
    return CrawlerManager()


def test_stamp_sets_finished_at_and_size(manager, tmp_path):
    job = {"crawl_id": "1", "storage_path": str(tmp_path), "status": "finished"}
    with patch.object(manager, "_estimate_archive_required_bytes", return_value=42):
        manager._stamp_terminal_fields(job)
    assert "finished_at" in job and job["finished_at"]
    assert job["size_bytes"] == 42


def test_stamp_preserves_existing_finished_at(manager, tmp_path):
    job = {"crawl_id": "1", "storage_path": str(tmp_path), "finished_at": "2026-01-01T00:00:00"}
    with patch.object(manager, "_estimate_archive_required_bytes", return_value=10):
        manager._stamp_terminal_fields(job)
    assert job["finished_at"] == "2026-01-01T00:00:00"  # not overwritten
    assert job["size_bytes"] == 10


def test_stamp_never_raises_on_bad_storage(manager):
    job = {"crawl_id": "1", "storage_path": None}
    manager._stamp_terminal_fields(job)  # must not raise
    assert "finished_at" in job


def test_stamp_swallows_estimate_failure(manager, tmp_path):
    """Outer fail-open except: if size estimation raises, finished_at is still
    set and no exception propagates (size_bytes simply absent)."""
    job = {"crawl_id": "1", "storage_path": str(tmp_path)}
    with patch.object(manager, "_estimate_archive_required_bytes", side_effect=RuntimeError("boom")):
        manager._stamp_terminal_fields(job)  # must not raise
    assert "finished_at" in job
    assert "size_bytes" not in job
