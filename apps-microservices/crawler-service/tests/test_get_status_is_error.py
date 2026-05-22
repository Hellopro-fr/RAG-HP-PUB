"""Integration tests verifying get_status populates is_error from _callback_payload.json."""
import json
import os
from datetime import datetime

import pytest

from app.core.crawler_manager import crawler_manager


@pytest.mark.asyncio
async def test_get_status_includes_is_error_when_payload_has_it(tmp_path):
    storage_path = str(tmp_path)
    # Write payload with isError + create dataset dir so main path runs
    (tmp_path / '_callback_payload.json').write_text(
        json.dumps({'isError': 'stoppedManually', 'isFinished': 1})
    )
    os.makedirs(os.path.join(storage_path, 'storage', 'datasets', 'example.com'), exist_ok=True)

    job_info = {
        'crawl_id': 'test-123',
        'storage_path': storage_path,
        'domain': 'example.com',
        'start_url': 'https://example.com',
        'start_time': datetime.utcnow(),
        'status': 'finished',
    }

    status = await crawler_manager.get_status(job_info)
    assert status is not None
    assert status.is_error == 'stoppedManually'


@pytest.mark.asyncio
async def test_get_status_is_error_none_for_clean_crawl(tmp_path):
    storage_path = str(tmp_path)
    # Payload without isError + dataset dir
    (tmp_path / '_callback_payload.json').write_text(json.dumps({'isFinished': 1}))
    os.makedirs(os.path.join(storage_path, 'storage', 'datasets', 'example.com'), exist_ok=True)

    job_info = {
        'crawl_id': 'test-456',
        'storage_path': storage_path,
        'domain': 'example.com',
        'start_url': 'https://example.com',
        'start_time': datetime.utcnow(),
        'status': 'finished',
    }

    status = await crawler_manager.get_status(job_info)
    assert status is not None
    assert status.is_error is None


@pytest.mark.asyncio
async def test_get_status_uses_snapshot_path_and_enriches_is_error(tmp_path):
    """Verify the snapshot-path branch of get_status reads _callback_payload.json and populates is_error."""
    storage_path = str(tmp_path)
    # Snapshot present + job not running → snapshot branch fires
    snapshot = {
        "crawl_id": "test-789",
        "id_domaine": "test-789",
        "status": "finished",
        "domain": "example.com",
        "start_url": "https://example.com",
        "start_time": datetime.utcnow().isoformat(),
        "urls_crawled": 0,
        "error_urls_crawled": 0,
        "nfr_urls_crawled": 0,
    }
    (tmp_path / '_status_snapshot.json').write_text(json.dumps(snapshot, default=str))
    (tmp_path / '_callback_payload.json').write_text(
        json.dumps({'isError': 'limitCrawl'})
    )

    job_info = {
        'crawl_id': 'test-789',
        'storage_path': storage_path,
        'domain': 'example.com',
        'start_url': 'https://example.com',
        'start_time': datetime.utcnow(),
        'status': 'finished',  # non-running triggers snapshot branch
    }

    status = await crawler_manager.get_status(job_info)
    assert status is not None
    assert status.is_error == 'limitCrawl'
