"""Unit tests for the archived-leftover reclean sweep in crawler_manager.py.

archive_crawl marks status='archived' BEFORE _cleanup_local_data, and a
cleanup failure is only warned, never retried (/archive 409s on archived).
Other paths leave (or re-create) a multi-GB storage/ tree under an archived
crawl: the idempotent-retry and GCS-fallback archive branches (mark archived
with NO cleanup), GET /html re-extracting the full tar, and update-mode
_restore_archived_crawl when the update never finalizes. Result on prod:
dozens of archived dirs still holding multi-GB storage/ trees.

These tests cover _reclean_archived_leftovers directly (real tmp dirs) plus
source-inspection wiring checks on _reconcile_locked, which cannot be
invoked end-to-end here: it calls os.uname() (POSIX-only — fails on this
Windows dev box) and drives a real redis pipeline (same gap noted by
TestReconcileStaleHealWiring in test_crawler_manager_shutdown_finalize.py).
"""
import inspect
import json
import os
import time

import pytest

from app.core import crawler_manager as cm_module
from app.core.config import settings
from app.core.crawler_manager import CrawlerManager


MIN_AGE = 3600  # test-local grace, monkeypatched below

# Every crawl id used across these tests — the fixture allowlists them all,
# so pre-existing behaviors are exercised with the GCS-verified gate open.
ALL_TEST_IDS = ["crawl-a", "crawl-b", "crawl-c", "crawl-d", "crawl-e",
                "crawl-0", "crawl-1", "crawl-2", "crawl-3", "crawl-4",
                "crawl-bad", "crawl-ok", "crawl-gone", "crawl-no-path"]


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_ENABLED", True)
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_MIN_AGE_SECONDS", MIN_AGE)
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_MAX_PER_TICK", 3)
    allowlist = tmp_path / "verified_in_gcs.list"
    allowlist.write_text("\n".join(ALL_TEST_IDS) + "\n")
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_VERIFIED_LIST", str(allowlist))
    return CrawlerManager()


def _make_archived_dir(base, crawl_id: str, age_seconds: int = MIN_AGE * 2):
    """Build a realistic archived crawl dir: heavy storage/ tree + small
    sidecars at the root (which the reclean must NOT touch)."""
    root = base / crawl_id
    datasets = root / "storage" / "datasets"
    datasets.mkdir(parents=True)
    (datasets / "000000001.json").write_text(json.dumps({"url": "https://x.test"}))
    (root / "crawler.log").write_text("log line\n")
    (root / "_status_snapshot.json").write_text("{}")
    backdate = time.time() - age_seconds
    os.utime(root / "storage", (backdate, backdate))
    return root


def _job(crawl_id: str, root) -> dict:
    return {"crawl_id": crawl_id, "status": "archived", "storage_path": str(root)}


@pytest.mark.asyncio
async def test_old_leftover_removed_sidecars_survive(manager, tmp_path):
    root = _make_archived_dir(tmp_path, "crawl-a")

    actioned = await manager._reclean_archived_leftovers([_job("crawl-a", root)], set())

    assert actioned == 1
    assert not (root / "storage").exists()
    # Sidecars at the crawl-dir root are kept for investigation.
    assert (root / "crawler.log").is_file()
    assert (root / "_status_snapshot.json").is_file()


@pytest.mark.asyncio
async def test_active_prev_id_skipped(manager, tmp_path):
    """An in-flight update crawl restored this tree as previous_crawl_id —
    cleaning it would yank the dataset out from under the running crawl."""
    root = _make_archived_dir(tmp_path, "crawl-b")

    actioned = await manager._reclean_archived_leftovers(
        [_job("crawl-b", root)], active_prev_ids={"crawl-b"})

    assert actioned == 0
    assert (root / "storage" / "datasets" / "000000001.json").is_file()


@pytest.mark.asyncio
async def test_fresh_subtree_skipped(manager, tmp_path):
    """A subtree younger than the grace (e.g. a fresh /html extraction)
    must stay browsable."""
    root = _make_archived_dir(tmp_path, "crawl-c", age_seconds=0)

    actioned = await manager._reclean_archived_leftovers([_job("crawl-c", root)], set())

    assert actioned == 0
    assert (root / "storage").is_dir()


@pytest.mark.asyncio
async def test_cap_max_per_tick(manager, tmp_path):
    """5 eligible candidates, ARCHIVED_RECLEAN_MAX_PER_TICK=3 — exactly 3
    actioned this call, the remaining 2 left for the next tick."""
    jobs = []
    roots = []
    for i in range(5):
        root = _make_archived_dir(tmp_path, f"crawl-{i}")
        roots.append(root)
        jobs.append(_job(f"crawl-{i}", root))

    actioned = await manager._reclean_archived_leftovers(jobs, set())

    assert actioned == 3
    remaining = sum(1 for root in roots if (root / "storage").is_dir())
    assert remaining == 2


@pytest.mark.asyncio
async def test_disabled_kill_switch_is_noop(manager, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_ENABLED", False)
    root = _make_archived_dir(tmp_path, "crawl-d")

    actioned = await manager._reclean_archived_leftovers([_job("crawl-d", root)], set())

    assert actioned == 0
    assert (root / "storage").is_dir()


@pytest.mark.asyncio
async def test_missing_storage_path_dir_no_crash(manager, tmp_path):
    """Nonexistent storage_path, and a job blob without storage_path at all
    (falls back to CRAWLER_STORAGE_PATH/crawl_id) — neither may raise."""
    jobs = [
        _job("crawl-gone", tmp_path / "does-not-exist"),
        {"crawl_id": "crawl-no-path", "status": "archived"},
    ]

    actioned = await manager._reclean_archived_leftovers(jobs, set())

    assert actioned == 0


@pytest.mark.asyncio
async def test_fallback_storage_path_from_crawl_id(manager, monkeypatch, tmp_path):
    """A blob missing storage_path resolves to CRAWLER_STORAGE_PATH/crawl_id."""
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))
    root = _make_archived_dir(tmp_path, "crawl-e")

    actioned = await manager._reclean_archived_leftovers(
        [{"crawl_id": "crawl-e", "status": "archived"}], set())

    assert actioned == 1
    assert not (root / "storage").exists()


@pytest.mark.asyncio
async def test_partial_cleanup_warns_and_continues(manager, monkeypatch, tmp_path):
    """_cleanup_local_data raising (partial rmtree) must not abort the sweep —
    the next candidate is still actioned."""
    root_bad = _make_archived_dir(tmp_path, "crawl-bad")
    root_ok = _make_archived_dir(tmp_path, "crawl-ok")

    real_cleanup = CrawlerManager._cleanup_local_data

    def flaky_cleanup(storage_path):
        if storage_path == str(root_bad):
            raise RuntimeError("storage/ tree only partially removed")
        real_cleanup(storage_path)

    monkeypatch.setattr(manager, "_cleanup_local_data", flaky_cleanup)

    actioned = await manager._reclean_archived_leftovers(
        [_job("crawl-bad", root_bad), _job("crawl-ok", root_ok)], set())

    # Both consumed a per-tick slot (attempted); only crawl-ok's tree is gone.
    assert actioned == 2
    assert (root_bad / "storage").is_dir()
    assert not (root_ok / "storage").exists()


@pytest.mark.asyncio
async def test_missing_allowlist_fail_closed(manager, monkeypatch, tmp_path):
    """No verified-in-GCS list -> no deletion at all, even for an otherwise
    fully eligible candidate (Redis 'archived' alone is not trusted)."""
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_VERIFIED_LIST",
                        str(tmp_path / "no-such.list"))
    root = _make_archived_dir(tmp_path, "crawl-a")

    actioned = await manager._reclean_archived_leftovers([_job("crawl-a", root)], set())

    assert actioned == 0
    assert (root / "storage").is_dir()


@pytest.mark.asyncio
async def test_unverified_id_skipped(manager, monkeypatch, tmp_path):
    """List present but the candidate's id is not in it -> silent skip."""
    allowlist = tmp_path / "partial.list"
    allowlist.write_text("some-other-crawl\n")
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_VERIFIED_LIST", str(allowlist))
    root = _make_archived_dir(tmp_path, "crawl-a")

    actioned = await manager._reclean_archived_leftovers([_job("crawl-a", root)], set())

    assert actioned == 0
    assert (root / "storage" / "datasets" / "000000001.json").is_file()


@pytest.mark.asyncio
async def test_allowlist_comments_and_blanks_parsed(manager, monkeypatch, tmp_path):
    """'#' comments and blank lines are ignored; an id after them is honored."""
    allowlist = tmp_path / "commented.list"
    allowlist.write_text(
        "# generated by tools/verify_archives_in_gcs.sh\n"
        "\n"
        "   \n"
        "crawl-a\n")
    monkeypatch.setattr(settings, "ARCHIVED_RECLEAN_VERIFIED_LIST", str(allowlist))
    root = _make_archived_dir(tmp_path, "crawl-a")

    actioned = await manager._reclean_archived_leftovers([_job("crawl-a", root)], set())

    assert actioned == 1
    assert not (root / "storage").exists()


class TestReconcileWiring:
    """Source-inspection checks that _reconcile_locked collects the
    candidates and dispatches the sweep, positioned and guarded correctly
    (see module docstring for why no end-to-end invocation)."""

    def test_collects_archived_candidates_and_active_prev_ids(self):
        source = inspect.getsource(cm_module.CrawlerManager._reconcile_locked)
        assert "archived_candidates" in source
        assert "active_prev_ids" in source
        assert '"starting", "running", "restarting_oom", "stopping"' in source, (
            "active_prev_ids must cover every in-flight status whose update "
            "restore could be yanked by the reclean"
        )
        assert 'previous_crawl_id' in source

    def test_dispatch_gated_on_kill_switch_after_scan_loop(self):
        source = inspect.getsource(cm_module.CrawlerManager._reconcile_locked)
        dispatch_idx = source.find("_reclean_archived_leftovers")
        assert dispatch_idx != -1, "_reconcile_locked must dispatch the reclean sweep"
        gate = "settings.ARCHIVED_RECLEAN_ENABLED and archived_candidates"
        gate_idx = source.find(gate)
        assert gate_idx != -1 and gate_idx < dispatch_idx, (
            "reclean dispatch must be gated on the ARCHIVED_RECLEAN_ENABLED "
            "kill-switch"
        )
        # Dispatched AFTER the scan loop so active_prev_ids is complete.
        scan_loop_idx = source.find("for i, job_raw in enumerate(all_jobs_raw)")
        assert scan_loop_idx != -1 and scan_loop_idx < dispatch_idx

    def test_cleanup_runs_off_event_loop(self):
        source = inspect.getsource(cm_module.CrawlerManager._reclean_archived_leftovers)
        assert "anyio.to_thread.run_sync(self._cleanup_local_data" in source, (
            "the rmtree must run off the event loop (worker thread), like "
            "every other blocking fs op in this module"
        )
