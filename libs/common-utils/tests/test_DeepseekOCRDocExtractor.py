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
