"""Stash upload-orphan re-queue (auto-stash P2, Task 9)."""
import os
from unittest.mock import patch
import pytest
from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_requeue_moves_deadletter_back(tmp_path):
    mgr = CrawlerManager()
    stash_dir = tmp_path
    dead = stash_dir / "dead_letter"
    dead.mkdir()
    (dead / "55.tar.gz").write_text("data")
    with patch("app.core.crawler_manager.settings") as s:
        s.STASH_SHARED_PATH = str(stash_dir)
        moved = mgr._requeue_stash_orphan("55")
    assert moved is True
    assert (stash_dir / "55.tar.gz").exists()
    assert not (dead / "55.tar.gz").exists()


@pytest.mark.asyncio
async def test_requeue_noop_when_no_deadletter(tmp_path):
    mgr = CrawlerManager()
    with patch("app.core.crawler_manager.settings") as s:
        s.STASH_SHARED_PATH = str(tmp_path)
        assert mgr._requeue_stash_orphan("99") is False


@pytest.mark.asyncio
async def test_requeue_skips_when_target_exists(tmp_path):
    """Never overwrite a pending tar already at the watch dir with the
    dead-lettered copy; leave the dead-letter copy for the operator."""
    mgr = CrawlerManager()
    dead = tmp_path / "dead_letter"
    dead.mkdir()
    (dead / "55.tar.gz").write_text("old")
    (tmp_path / "55.tar.gz").write_text("fresh")  # pending upload already present
    with patch("app.core.crawler_manager.settings") as s:
        s.STASH_SHARED_PATH = str(tmp_path)
        moved = mgr._requeue_stash_orphan("55")
    assert moved is False
    assert (tmp_path / "55.tar.gz").read_text() == "fresh"  # not overwritten
    assert (dead / "55.tar.gz").exists()  # dead-letter copy preserved
