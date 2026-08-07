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
    """The hoisted read must stay gated on the same condition that used to
    guard it from inside _reclean_archived_leftovers — otherwise it runs
    (and, on a missing allowlist file, logs a warning) on every tick forever,
    even with the reclean flag off or no archived candidates."""
    src = inspect.getsource(CrawlerManager._reconcile_locked)
    pattern = re.compile(
        r"_load_reclean_allowlist\(\)\s*"
        r"if\s*\(?\s*settings\.ARCHIVED_RECLEAN_ENABLED\s+and\s+archived_candidates\s*\)?\s*"
        r"else\s+None",
        re.DOTALL,
    )
    assert pattern.search(src), (
        "the allowlist load must be conditioned on "
        "'ARCHIVED_RECLEAN_ENABLED and archived_candidates', not run unconditionally"
    )
