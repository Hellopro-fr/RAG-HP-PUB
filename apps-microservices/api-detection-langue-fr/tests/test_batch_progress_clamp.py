import pytest
from app.api import routes
from app.models.schemas import BatchItem, BatchOpts, DetectionMode, DetectionResponse


@pytest.mark.asyncio
async def test_progress_never_exceeds_total(monkeypatch):
    # Force every item to a Pass-2-retryable method so Pass-2 re-increments the counter.
    async def fake_detect(url=None, **kwargs):
        return DetectionResponse(ok=False, url=url, method='http_error_transient')

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    progress = []
    items = [BatchItem(url=f"http://x{i}.fr") for i in range(3)]
    opts = BatchOpts(proxy_url=None, use_nlp_detection=True, force_refresh=False,
                     max_concurrency=10, homepage_fallback=True, validate_alternatives=True)
    await routes._run_batch_core(items, DetectionMode.COMPLETE, opts,
                                 progress_cb=lambda d: progress.append(d))
    assert progress, "progress_cb never called"
    assert max(progress) <= len(items)     # never exceeds total despite Pass-2 retries
