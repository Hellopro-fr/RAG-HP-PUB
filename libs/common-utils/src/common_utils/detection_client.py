"""Shared HTTP client enforcing the api-detection-langue-fr call contract.

Contract env vars (with defaults):
  DETECTION_MAX_CONCURRENCY=5     max concurrent /detect calls per client instance
  DETECTION_REQUEST_TIMEOUT_S=180 httpx total timeout
  DETECTION_MAX_RETRIES=2         retries on 503 (server overload)
  DETECTION_BACKOFF_BASE_S=2      exponential backoff base when Retry-After absent

Retry policy:
  - Retries ONLY on HTTP 503.
  - Wait precedence: server `Retry-After` header if present, else
    `backoff_base * 2**attempt` seconds.
"""
import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DetectionClient:
    """HTTP client wrapper for api-detection-langue-fr enforcing the caller contract."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._sem = asyncio.Semaphore(int(os.getenv("DETECTION_MAX_CONCURRENCY", "5")))
        self._timeout = float(os.getenv("DETECTION_REQUEST_TIMEOUT_S", "180"))
        self._max_retries = int(os.getenv("DETECTION_MAX_RETRIES", "2"))
        self._backoff_base = float(os.getenv("DETECTION_BACKOFF_BASE_S", "2"))

    async def detect(self, url: str, mode: str = "complete", **kwargs: Any) -> dict:
        body = {"url": url, "mode": mode, **kwargs}
        return await self._request_with_retry("POST", "/api/v1/detect", json=body)

    async def detect_batch(self, items: list[dict], **kwargs: Any) -> dict:
        body = {"items": items, **kwargs}
        return await self._request_with_retry("POST", "/api/v1/detect-batch", json=body)

    async def check_url(self, url: str, track_redirect: bool = False) -> dict:
        params = {"url": url, "track_redirect": str(track_redirect).lower()}
        return await self._request_with_retry("GET", "/api/v1/check-url", params=params)

    async def _request_with_retry(self, method: str, path: str, **kwargs: Any) -> dict:
        full_url = f"{self._base_url}{path}"
        async with self._sem:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, connect=10.0)) as client:
                for attempt in range(self._max_retries + 1):
                    response = await client.request(method, full_url, **kwargs)
                    if response.status_code != 503:
                        response.raise_for_status()
                        return response.json()

                    if attempt >= self._max_retries:
                        response.raise_for_status()

                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            wait_s = float(retry_after)
                        except ValueError:
                            wait_s = self._backoff_base * (2 ** attempt)
                    else:
                        wait_s = self._backoff_base * (2 ** attempt)

                    logger.warning(
                        f"DetectionClient got 503 for {method} {path} "
                        f"(attempt {attempt + 1}/{self._max_retries + 1}); "
                        f"waiting {wait_s}s before retry"
                    )
                    await asyncio.sleep(wait_s)

        raise RuntimeError("DetectionClient retry loop exited without result")
