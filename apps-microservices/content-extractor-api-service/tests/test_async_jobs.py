import pytest
from pydantic import ValidationError

from app.schemas.async_jobs import (
    CleanAsyncRequest, HeaderFooterAsyncRequest, AsyncJobStatusResponse,
)


def test_clean_async_request_valid():
    req = CleanAsyncRequest(items=[{"html": "<p>x</p>", "format": "text"}])
    assert req.max_concurrency == 4
    assert req.items[0].html == "<p>x</p>"


def test_clean_async_request_rejects_empty():
    with pytest.raises(ValidationError):
        CleanAsyncRequest(items=[])


def test_hf_async_request_requires_two_refs():
    with pytest.raises(ValidationError):
        HeaderFooterAsyncRequest(items=[{"main_html": "<p>m</p>", "reference_htmls": ["<p>a</p>"]}])


def test_status_response_shape():
    r = AsyncJobStatusResponse(
        job_id="j", job_type="clean", status="completed", total=1, done=1,
        results=[{"content": "x"}], poll_after_seconds=2,
    )
    assert r.error is None
