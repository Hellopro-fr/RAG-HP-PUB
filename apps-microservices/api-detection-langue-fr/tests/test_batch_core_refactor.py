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
async def test_core_progress_cb(monkeypatch):
    async def fake_detect(url, **kwargs):
        return DetectionResponse(ok=True, url=url, method="url_tld")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)
    seen = []
    items = [BatchItem(url=f"https://a{i}.fr") for i in range(3)]
    await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=3),
                                 progress_cb=lambda done: seen.append(done))
    assert sorted(seen) == [1, 2, 3]
