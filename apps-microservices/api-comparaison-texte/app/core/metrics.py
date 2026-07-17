from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "comparison_requests_total",
    "Total comparison HTTP requests",
    ["endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "comparison_request_duration_seconds",
    "Comparison request duration in seconds",
    ["endpoint"],
)
DECISION_COUNT = Counter(
    "comparison_decision_total",
    "Comparison decisions",
    ["decision"],
)
BATCH_SIZE = Histogram(
    "comparison_batch_size",
    "Number of items per batch request",
)
SYNC_ADMISSION_REJECTED = Counter(
    "comparison_sync_admission_rejected_total",
    "Sync requests shed by the admission guard (SYNC_MAX_INFLIGHT)",
)
