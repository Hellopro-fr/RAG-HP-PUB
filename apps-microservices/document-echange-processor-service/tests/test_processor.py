"""Download-error classification wiring in process_document_data_for_templating.

The service package (``app/`` is renamed to ``document_echange_processor_service``
in the image) and Presidio are only importable in the container/CI, so this test
is skipped locally. The pure predicate it relies on is unit-tested in common-utils
(``test_DeepseekOCRDocExtractor.py::test_is_transient_download_error_*``).
"""

import asyncio

import httpx
import pytest

processor = pytest.importorskip(
    "document_echange_processor_service.core.processor"
)


def _status_error(code):
    req = httpx.Request("GET", "https://www.hellopro.fr/x/y.jpg")
    return httpx.HTTPStatusError(
        f"{code}", request=req, response=httpx.Response(code, request=req)
    )


class _FakeExtractor:
    """Stands in for DeepseekOCRDocExtractor; fails the download with a chosen error."""

    def __init__(self, exc):
        self._exc = exc

    async def _download_file(self, url):
        raise self._exc

    def _validate_pdf_page_count(self, *args, **kwargs):
        pass


def _first_status(exc, monkeypatch):
    monkeypatch.setattr(
        processor, "DeepseekOCRDocExtractor", lambda *a, **k: _FakeExtractor(exc)
    )
    monkeypatch.setattr(processor, "AnonymizeText", lambda *a, **k: None)
    docs = [{"data": {"document": "https://www.hellopro.fr/x/y.jpg"}}]
    results = asyncio.run(processor.process_document_data_for_templating(docs))
    return results[0]["status"]


def test_download_404_is_permanent(monkeypatch):
    assert _first_status(_status_error(404), monkeypatch) == "error"


def test_download_503_is_transient(monkeypatch):
    assert _first_status(_status_error(503), monkeypatch) == "transient_error"


def test_download_timeout_is_transient(monkeypatch):
    req = httpx.Request("GET", "https://www.hellopro.fr/x/y.jpg")
    assert (
        _first_status(httpx.ConnectTimeout("t", request=req), monkeypatch)
        == "transient_error"
    )
