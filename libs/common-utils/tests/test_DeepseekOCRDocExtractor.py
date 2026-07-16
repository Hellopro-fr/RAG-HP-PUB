"""Tests for the fail-open pypdf page-count pre-gate."""

from io import BytesIO

import pytest

from common_utils.ocr.DeepseekOCRDocExtractor import DeepseekOCRDocExtractor


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
