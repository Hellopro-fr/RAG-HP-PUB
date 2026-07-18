import pytest
from app.api import routes
from app.models.schemas import BatchItem, BatchOpts, BatchCounts, DetectionMode, DetectionResponse


@pytest.mark.asyncio
async def test_core_orders_and_counts(monkeypatch):
    async def fake_detect(url, **kwargs):
        ok = url.endswith(".fr")
        return DetectionResponse(ok=ok, url=url, method="url_tld" if ok else "nlp_negative")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://a.fr"), BatchItem(url="https://b.com"), BatchItem(url="https://c.fr")]
    results, counts = await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=3))

    assert [r.url for r in results] == ["https://a.fr", "https://b.com", "https://c.fr"]
    assert counts.success_count == 2 and counts.failed_count == 1 and counts.error_count == 0


@pytest.mark.asyncio
async def test_core_pass2_retries_fetch_failed(monkeypatch):
    calls = {"https://flaky.fr": 0}
    async def fake_detect(url, **kwargs):
        if url == "https://flaky.fr":
            calls[url] += 1
            if calls[url] == 1:
                return DetectionResponse(ok=False, url=url, method="fetch_failed")
            return DetectionResponse(ok=True, url=url, method="url_tld")
        return DetectionResponse(ok=True, url=url, method="url_tld")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://flaky.fr")]
    results, counts = await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1))
    assert results[0].ok is True and calls["https://flaky.fr"] == 2


@pytest.mark.asyncio
async def test_core_pass2_retries_fetch_empty_content(monkeypatch):
    calls = {"n": 0}
    async def fake_detect(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return DetectionResponse(ok=False, url=url, method="fetch_empty_content")
        return DetectionResponse(ok=True, url=url, method="direct_match")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://empty.fr")]
    results, counts = await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1))
    assert results[0].ok is True and calls["n"] == 2


@pytest.mark.asyncio
async def test_core_pass2_does_not_retry_timeout_error(monkeypatch):
    """'error' (incl. Timeout global item) is deliberately NOT Pass-2-retryable:
    a timed-out item already consumed its 300s of work; retrying inside the
    same saturated batch amplifies the pile-up (see 2026-07-18 spec)."""
    calls = {"n": 0}
    async def fake_detect(url, **kwargs):
        calls["n"] += 1
        return DetectionResponse(ok=False, url=url, method="error", error="Timeout global item (300s)")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://slow.fr")]
    results, counts = await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1))
    assert results[0].method == "error" and calls["n"] == 1


@pytest.mark.asyncio
async def test_core_progress_cb(monkeypatch):
    async def fake_detect(url, **kwargs):
        return DetectionResponse(ok=True, url=url, method="url_tld")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)
    seen = []
    items = [BatchItem(url=f"https://a{i}.fr") for i in range(3)]
    await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=3),
                                 progress_cb=lambda done: seen.append(done))
    assert sorted(seen) == [1, 2, 3]
