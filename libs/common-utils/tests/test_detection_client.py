"""Tests for common_utils.detection_client.DetectionClient."""
import asyncio
import os
import pytest
import httpx
import respx


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Reset contract env vars to known defaults so tests are hermetic."""
    for var in (
        "DETECTION_MAX_CONCURRENCY",
        "DETECTION_REQUEST_TIMEOUT_S",
        "DETECTION_MAX_RETRIES",
        "DETECTION_BACKOFF_BASE_S",
    ):
        monkeypatch.delenv(var, raising=False)


class TestDetectionClientBasic:

    @pytest.mark.asyncio
    @respx.mock
    async def test_detect_success(self):
        from common_utils.detection_client import DetectionClient
        respx.post("http://detect/api/v1/detect").mock(
            return_value=httpx.Response(200, json={"ok": True, "url": "https://x", "method": "langHtml"})
        )
        client = DetectionClient("http://detect")
        result = await client.detect("https://x", mode="simple")
        assert result["ok"] is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_503_honoring_retry_after(self):
        from common_utils.detection_client import DetectionClient
        route = respx.post("http://detect/api/v1/detect").mock(
            side_effect=[
                httpx.Response(503, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"ok": True, "url": "https://x", "method": "m"}),
            ]
        )
        client = DetectionClient("http://detect")
        result = await client.detect("https://x")
        assert result["ok"] is True
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_exhausts_retries_and_raises(self, monkeypatch):
        from common_utils.detection_client import DetectionClient
        monkeypatch.setenv("DETECTION_MAX_RETRIES", "1")
        respx.post("http://detect/api/v1/detect").mock(
            return_value=httpx.Response(503, headers={"Retry-After": "0"})
        )
        client = DetectionClient("http://detect")
        with pytest.raises(httpx.HTTPStatusError):
            await client.detect("https://x")

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_503_error_does_not_retry(self):
        from common_utils.detection_client import DetectionClient
        route = respx.post("http://detect/api/v1/detect").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        client = DetectionClient("http://detect")
        with pytest.raises(httpx.HTTPStatusError):
            await client.detect("https://x")
        assert route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_concurrency_semaphore_caps_inflight(self, monkeypatch):
        """With DETECTION_MAX_CONCURRENCY=2, at most 2 requests are in flight at once."""
        from common_utils.detection_client import DetectionClient
        monkeypatch.setenv("DETECTION_MAX_CONCURRENCY", "2")

        in_flight = {"current": 0, "peak": 0}

        def _handler(request):
            in_flight["current"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
            import time
            time.sleep(0.02)
            in_flight["current"] -= 1
            return httpx.Response(200, json={"ok": True, "url": "https://x", "method": "m"})

        respx.post("http://detect/api/v1/detect").mock(side_effect=_handler)
        client = DetectionClient("http://detect")
        await asyncio.gather(*[client.detect(f"https://x/{i}") for i in range(10)])
        assert in_flight["peak"] <= 2
