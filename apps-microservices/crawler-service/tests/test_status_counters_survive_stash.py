"""F8 — root cause: /status counters are computed live from disk
(_count_files_in_dir, crawler_manager.py stats block). Stash deletes local data,
so post-stash /status read 0 — nothing 'zeroes' the blob itself. Fix: persist
final counts into the blob at finalize, serve them when the dataset dir is gone."""
import os

import pytest

from app.core.crawler_manager import CrawlerManager


def _job(tmp_path, **extra):
    job = {"crawl_id": "900", "status": "finished", "domain": "x.fr",
           "start_url": "https://x.fr/", "start_time": "2026-06-01T00:00:00",
           "storage_path": str(tmp_path)}
    job.update(extra)
    return job


def _make_dataset(storage_path: str, dir_name: str, n_files: int) -> None:
    path = os.path.join(storage_path, "storage", "datasets", dir_name)
    os.makedirs(path, exist_ok=True)
    for i in range(n_files):
        with open(os.path.join(path, f"{i:09d}.json"), "w") as f:
            f.write("{}")
    # Crawlee metadata file — must be excluded from counts
    with open(os.path.join(path, "__metadata__.json"), "w") as f:
        f.write("{}")


def test_finalize_persists_final_counters(tmp_path):
    """_persist_final_counters stamps disk counts into the blob at finalize."""
    mgr = CrawlerManager()
    job = _job(tmp_path)
    _make_dataset(str(tmp_path), "x.fr", 4)
    _make_dataset(str(tmp_path), "error-x.fr", 2)

    mgr._persist_final_counters(job)

    assert job["final_urls_crawled"] == 4
    assert job["final_error_urls_crawled"] == 2


def test_finalize_persists_with_sanitized_dir_fallback(tmp_path):
    """Same dot→dash fallback as _send_success_webhook's disk count."""
    mgr = CrawlerManager()
    job = _job(tmp_path)
    _make_dataset(str(tmp_path), "x-fr", 3)
    _make_dataset(str(tmp_path), "error-x-fr", 1)

    mgr._persist_final_counters(job)

    assert job["final_urls_crawled"] == 3
    assert job["final_error_urls_crawled"] == 1


@pytest.mark.asyncio
async def test_status_serves_persisted_counters_when_disk_gone(tmp_path):
    """Post-stash (local data deleted): /status must report the persisted
    finals, not the zeros of an empty disk."""
    mgr = CrawlerManager()
    job = _job(tmp_path, stashed_at="2026-06-01T01:00:00",
               final_urls_crawled=428, final_error_urls_crawled=9)

    st = await mgr.get_status(job)

    assert st.urls_crawled == 428
    assert st.error_urls_crawled == 9


@pytest.mark.asyncio
async def test_status_stays_disk_derived_when_local_data_present(tmp_path):
    """Disk wins when the dataset dir exists — live crawls and fresh
    finishes stay accurate."""
    mgr = CrawlerManager()
    job = _job(tmp_path, final_urls_crawled=999)
    _make_dataset(str(tmp_path), "x.fr", 3)

    st = await mgr.get_status(job)

    assert st.urls_crawled == 3


@pytest.mark.asyncio
async def test_status_zero_when_neither_disk_nor_persisted(tmp_path):
    """Pre-existing behavior pinned: no disk, no finals → 0 (no fabrication)."""
    mgr = CrawlerManager()

    st = await mgr.get_status(_job(tmp_path))

    assert st.urls_crawled == 0
    assert st.error_urls_crawled == 0
