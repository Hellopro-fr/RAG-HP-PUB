from prometheus_client import Counter, Histogram

from app.core import metrics


def test_metric_types():
    assert isinstance(metrics.REQUEST_COUNT, Counter)
    assert isinstance(metrics.REQUEST_DURATION, Histogram)
    assert isinstance(metrics.DECISION_COUNT, Counter)
    assert isinstance(metrics.BATCH_SIZE, Histogram)
    assert isinstance(metrics.SYNC_ADMISSION_REJECTED, Counter)
