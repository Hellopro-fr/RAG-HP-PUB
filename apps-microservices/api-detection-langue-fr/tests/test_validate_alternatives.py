"""Tests for the validate_alternatives skip-all flag.
Spec: docs/superpowers/specs/2026-06-04-detection-langue-fr-validate-alternatives-flag-design.md
"""
import pytest

from app.models.schemas import (
    DetectionRequest,
    BatchDetectionRequest,
    AsyncBatchSubmitRequest,
    BatchItem,
    BatchOpts,
)


class TestValidateAlternativesSchema:
    def test_detection_request_default_true(self):
        assert DetectionRequest(url="https://example.com").validate_alternatives is True

    def test_detection_request_accepts_false(self):
        req = DetectionRequest(url="https://example.com", validate_alternatives=False)
        assert req.validate_alternatives is False

    def test_batch_request_default_true(self):
        req = BatchDetectionRequest(items=[BatchItem(url="https://example.com")])
        assert req.validate_alternatives is True

    def test_async_submit_request_default_true(self):
        req = AsyncBatchSubmitRequest(items=[BatchItem(url="https://example.com")])
        assert req.validate_alternatives is True

    def test_batch_opts_default_true_and_overridable(self):
        assert BatchOpts().validate_alternatives is True
        assert BatchOpts(validate_alternatives=False).validate_alternatives is False
