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
