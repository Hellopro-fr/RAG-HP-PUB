from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

EXTRACTION_METHOD = Counter(
    "extraction_method_used_total",
    "Header/footer extraction method used",
    ["method"],
)

SYNC_ADMISSION_REJECTED = Counter(
    "extract_sync_admission_rejected_total",
    "Sync requests shed by the admission guard (SYNC_MAX_INFLIGHT)",
)


CACHE_HITS = Counter(
    "extract_cache_hits_total", "Result cache hits", ["job_type"],
)
CACHE_MISSES = Counter(
    "extract_cache_misses_total", "Result cache misses", ["job_type"],
)
