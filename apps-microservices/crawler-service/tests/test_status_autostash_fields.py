"""Fix B: expose stashed_at/downloaded_at/finished_at/size_bytes on /status."""
import json
import pytest

from app.core.crawler_manager import CrawlerManager


def _job(tmp_path, **extra):
    job = {"crawl_id": "900", "status": "finished", "domain": "x.fr",
           "start_url": "https://x.fr/", "start_time": "2026-06-01T00:00:00",
           "storage_path": str(tmp_path)}
    job.update(extra)
    return job


@pytest.mark.asyncio
async def test_status_main_path_maps_fields(tmp_path):
    mgr = CrawlerManager()
    job = _job(tmp_path, status="running",  # running → skip snapshot path
               stashed_at="2026-06-01T01:00:00", downloaded_at="2026-06-01T02:00:00",
               finished_at="2026-06-01T03:00:00", size_bytes=12345)
    st = await mgr.get_status(job)
    assert st.stashed_at == "2026-06-01T01:00:00"
    assert st.downloaded_at == "2026-06-01T02:00:00"
    assert st.finished_at == "2026-06-01T03:00:00"
    assert st.size_bytes == 12345


@pytest.mark.asyncio
async def test_status_null_when_absent(tmp_path):
    mgr = CrawlerManager()
    st = await mgr.get_status(_job(tmp_path, status="running"))
    assert st.stashed_at is None and st.downloaded_at is None
    assert st.finished_at is None and st.size_bytes is None


@pytest.mark.asyncio
async def test_status_snapshot_path_includes_fields(tmp_path):
    """Terminal/stashed crawls take the snapshot path — it must expose the fields."""
    mgr = CrawlerManager()
    snapshot = {"crawl_id": "900", "id_domaine": "900", "status": "finished",
                "domain": "x.fr", "start_url": "https://x.fr/",
                "start_time": "2026-06-01T00:00:00", "urls_crawled": 5,
                "error_urls_crawled": 0, "nfr_urls_crawled": 0}
    (tmp_path / "_status_snapshot.json").write_text(json.dumps(snapshot))
    job = _job(tmp_path, status="finished",
               stashed_at="2026-06-01T01:00:00", downloaded_at="2026-06-01T02:00:00",
               finished_at="2026-06-01T03:00:00", size_bytes=999)
    st = await mgr.get_status(job)
    assert st.stashed_at == "2026-06-01T01:00:00"
    assert st.downloaded_at == "2026-06-01T02:00:00"
    assert st.finished_at == "2026-06-01T03:00:00"
    assert st.size_bytes == 999
