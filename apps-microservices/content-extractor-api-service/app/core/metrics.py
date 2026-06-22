from prometheus_client import Counter, Gauge, Histogram

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

ASYNC_JOBS_SUBMITTED = Counter(
    "extract_async_jobs_submitted_total", "Async batch jobs accepted (202)",
)
ASYNC_JOBS_ACTIVE = Gauge(
    "extract_async_jobs_active", "Currently reserved/in-flight async jobs",
)
ASYNC_JOBS_TERMINAL = Counter(
    "extract_async_jobs_terminal_total", "Async jobs reaching a terminal status", ["status"],
)
ASYNC_JOB_DURATION = Histogram(
    "extract_async_job_duration_seconds", "Async job wall-clock from running to terminal",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)
ASYNC_JOB_CAPACITY_REJECTED = Counter(
    "extract_async_job_capacity_rejected_total", "Submits rejected because MAX_ACTIVE_JOBS reached",
)
