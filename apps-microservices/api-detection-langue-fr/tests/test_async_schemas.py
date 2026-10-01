import pytest
from pydantic import ValidationError

from app.models.schemas import (
    BatchItem, BatchOpts, BatchCounts, DetectionMode,
    AsyncBatchSubmitRequest, AsyncBatchStatusResponse,
)
from app.core.config import settings
from app.core import metrics


def test_batchopts_defaults():
    o = BatchOpts()
    assert o.max_concurrency == 10 and o.use_nlp_detection is True
    assert BatchCounts(1, 2, 3).success_count == 1


def test_submit_request_defaults_and_limit():
    req = AsyncBatchSubmitRequest(items=[BatchItem(url="https://a.fr")])
    assert req.mode == DetectionMode.COMPLETE
    assert req.client_job_id is None
    with pytest.raises(ValidationError):
        AsyncBatchSubmitRequest(items=[BatchItem(url=f"https://a{i}.fr") for i in range(101)])


def test_status_response_optional_results():
    r = AsyncBatchStatusResponse(
        job_id="x", status="running", total=2, done=1,
        success_count=0, failed_count=0, error_count=0, poll_after_seconds=5,
    )
    assert r.results is None


def test_settings_present():
    assert settings.MAX_ACTIVE_JOBS == 8
    assert settings.JOB_RESULT_TTL_S < settings.JOB_TTL_ACTIVE_S
    assert settings.HEARTBEAT_INTERVAL_S < settings.STALE_THRESHOLD_S


def test_metrics_registered():
    for name in (
        "ASYNC_JOBS_SUBMITTED", "ASYNC_JOBS_ACTIVE", "ASYNC_JOBS_TERMINAL",
        "ASYNC_JOB_DURATION", "ASYNC_JOB_CAPACITY_REJECTED",
    ):
        assert hasattr(metrics, name)
