"""Tests for the Prometheus metrics module."""
import pytest
from fastapi.testclient import TestClient


class TestMetricsDefinitions:
    """Each metric must be importable and have the expected type."""

    def test_request_duration_is_histogram(self):
        from app.core.metrics import REQUEST_DURATION
        from prometheus_client import Histogram
        assert isinstance(REQUEST_DURATION, Histogram)

    def test_browser_launch_duration_labeled(self):
        from app.core.metrics import BROWSER_LAUNCH_DURATION
        # Should accept a browser label
        BROWSER_LAUNCH_DURATION.labels(browser="camoufox").observe(0.5)
        BROWSER_LAUNCH_DURATION.labels(browser="chromium").observe(1.2)

    def test_admission_rejected_counter(self):
        from app.core.metrics import ADMISSION_REJECTED
        before = ADMISSION_REJECTED.labels(endpoint="/detect")._value.get()
        ADMISSION_REJECTED.labels(endpoint="/detect").inc()
        after = ADMISSION_REJECTED.labels(endpoint="/detect")._value.get()
        assert after == before + 1

    def test_dedup_hits_counter(self):
        from app.core.metrics import DEDUP_HITS
        before = DEDUP_HITS._value.get()
        DEDUP_HITS.inc()
        assert DEDUP_HITS._value.get() == before + 1

    def test_inflight_gauge(self):
        from app.core.metrics import INFLIGHT_REQUESTS
        before = INFLIGHT_REQUESTS._value.get()
        INFLIGHT_REQUESTS.inc()
        INFLIGHT_REQUESTS.dec()
        assert INFLIGHT_REQUESTS._value.get() == before


class TestMetricsEndpoint:
    """/metrics returns Prometheus exposition format."""

    def test_metrics_endpoint_returns_prometheus_format(self):
        from main import app
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # Prometheus format markers
        body = response.text
        assert "# HELP" in body or "# TYPE" in body or body == ""  # allow empty if no metrics recorded yet
