"""Tests for the fail-open pypdf page-count pre-gate + download resilience."""

import asyncio
from io import BytesIO

import httpx
import pytest

from common_utils.ocr.DeepseekOCRDocExtractor import (
    DeepseekOCRDocExtractor,
    is_transient_download_error,
    RETRYABLE_STATUS,
)


def _status_error(code):
    req = httpx.Request("GET", "https://www.hellopro.fr/x/y.jpg")
    return httpx.HTTPStatusError(
        f"{code}", request=req, response=httpx.Response(code, request=req)
    )


def _raise_unparseable(content):
    raise ValueError("Impossible de lire le PDF: startxref not found")


def test_validate_failopen_when_pypdf_cannot_parse(monkeypatch):
    """A PDF pypdf refuses (malformed trailer) must NOT be rejected here —
    it is deferred to the OCR renderer instead of permanent-DLQ."""
    ext = DeepseekOCRDocExtractor(max_pdf_pages=19)
    monkeypatch.setattr(ext, "_count_pdf_pages", _raise_unparseable)
    # must not raise
    ext._validate_pdf_page_count(BytesIO(b"%PDF-1.4 broken"), "f.pdf")


def test_validate_still_rejects_too_many_pages(monkeypatch):
    ext = DeepseekOCRDocExtractor(max_pdf_pages=19)
    monkeypatch.setattr(ext, "_count_pdf_pages", lambda content: 25)
    with pytest.raises(ValueError):
        ext._validate_pdf_page_count(BytesIO(b"x"), "f.pdf")


def test_validate_skips_non_pdf(monkeypatch):
    ext = DeepseekOCRDocExtractor()
    calls = []
    monkeypatch.setattr(ext, "_count_pdf_pages", lambda content: calls.append(1) or 1)
    ext._validate_pdf_page_count(BytesIO(b"x"), "f.jpg")
    assert calls == []  # image formats never hit the pypdf gate


def test_download_file_follows_redirects(monkeypatch):
    """_download_file must FOLLOW redirects. hellopro.fr intermittently 302s a
    PJ URL to itself (WAF/cookie gate); with follow_redirects=False the 302 was
    raised and the message permanently DLQ'd. Following it reaches the 200."""
    import asyncio
    import httpx

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            # 302 to the SAME url + Set-Cookie (the observed WAF/cookie gate)
            return httpx.Response(
                302, headers={"Location": str(request.url), "Set-Cookie": "s=1"}
            )
        return httpx.Response(200, content=b"JPEGDATA", headers={"Content-Type": "image/jpeg"})

    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        # Force the real client's redirect engine over a mocked transport,
        # preserving the follow_redirects kwarg the code under test passes.
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "common_utils.ocr.DeepseekOCRDocExtractor.httpx.AsyncClient", factory
    )

    ext = DeepseekOCRDocExtractor()
    content, filename = asyncio.run(
        ext._download_file("https://www.hellopro.fr/x/y.jpg")
    )

    assert content.read() == b"JPEGDATA"
    assert filename == "y.jpg"
    assert calls["n"] == 2  # proves the 302 was followed through to the 200


@pytest.mark.parametrize(
    "code,transient",
    [(404, False), (403, False), (400, False), (401, False), (410, False),
     (429, True), (500, True), (502, True), (503, True), (504, True), (408, True)],
)
def test_is_transient_download_error_by_status(code, transient):
    assert is_transient_download_error(_status_error(code)) is transient
    assert (code in RETRYABLE_STATUS) is transient


def test_is_transient_download_error_network_and_redirects():
    req = httpx.Request("GET", "https://x")
    assert is_transient_download_error(httpx.ConnectTimeout("t", request=req)) is True
    assert is_transient_download_error(httpx.ReadTimeout("t", request=req)) is True
    assert is_transient_download_error(httpx.ConnectError("c", request=req)) is True
    assert is_transient_download_error(httpx.TooManyRedirects("r", request=req)) is True
    assert is_transient_download_error(TimeoutError()) is True
    assert is_transient_download_error(ConnectionError()) is True


def test_is_transient_download_error_permanent_defaults():
    assert is_transient_download_error(ValueError("too many pages")) is False
    assert is_transient_download_error(Exception("boom")) is False


def test_download_file_raises_typed_status_error(monkeypatch):
    """A 404 must propagate as httpx.HTTPStatusError (status preserved), NOT be
    flattened to a base httpx.HTTPError — otherwise the caller cannot tell a
    permanent 404 from a retryable 503."""
    def handler(request):
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "common_utils.ocr.DeepseekOCRDocExtractor.httpx.AsyncClient", factory
    )

    ext = DeepseekOCRDocExtractor()
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        asyncio.run(ext._download_file("https://www.hellopro.fr/x/y.jpg"))
    assert excinfo.value.response.status_code == 404
