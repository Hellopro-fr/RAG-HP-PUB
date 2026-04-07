"""Tests for the shared Prometheus metrics module."""
from prometheus_client import Counter, Histogram


def test_request_count_is_counter():
    from app.core.metrics import REQUEST_COUNT

    assert isinstance(REQUEST_COUNT, Counter)


def test_request_duration_is_histogram():
    from app.core.metrics import REQUEST_DURATION

    assert isinstance(REQUEST_DURATION, Histogram)


def test_extraction_method_is_counter():
    from app.core.metrics import EXTRACTION_METHOD

    assert isinstance(EXTRACTION_METHOD, Counter)


def test_request_count_labels():
    from app.core.metrics import REQUEST_COUNT

    # Accessing a labelled child should not raise
    child = REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="200")
    assert child is not None


def test_extraction_method_labels():
    from app.core.metrics import EXTRACTION_METHOD

    child = EXTRACTION_METHOD.labels(method="original")
    assert child is not None
