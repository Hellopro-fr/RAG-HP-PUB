"""Prometheus metrics for api-detection-langue-fr.

Exposed at /metrics. Used to drive the post-rollout decision on whether
the Approach 3 refactor (browser pool + queue) is needed (see spec).
"""
from prometheus_client import Counter, Gauge, Histogram

# End-to-end request duration distribution.
REQUEST_DURATION = Histogram(
    "detect_request_duration_seconds",
    "End-to-end request duration in seconds",
    labelnames=("endpoint", "status"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

# Cost of browser cold-start. Drives the Approach 3 decision: if this
# dominates request duration, a warm browser pool would be a direct win.
BROWSER_LAUNCH_DURATION = Histogram(
    "detect_browser_launch_duration_seconds",
    "Time to launch a Camoufox or Chromium browser",
    labelnames=("browser",),
    buckets=(0.5, 1, 2, 5, 10, 20, 45),
)

# Count of 503s emitted by the admission middleware.
ADMISSION_REJECTED = Counter(
    "detect_admission_rejected_total",
    "Requests rejected by the admission middleware",
    labelnames=("endpoint",),
)

# Count of coalesced duplicate URL fetches.
DEDUP_HITS = Counter(
    "detect_dedup_hits_total",
    "Concurrent requests for the same URL that were coalesced",
)

# Current number of admitted in-flight requests.
INFLIGHT_REQUESTS = Gauge(
    "detect_inflight_requests",
    "Current concurrent admitted requests",
)

# Queue depth on the Playwright browser semaphore.
BROWSER_SEMAPHORE_WAITERS = Gauge(
    "detect_browser_semaphore_waiters",
    "Number of coroutines waiting on the browser semaphore",
)

# Page-validation outcomes (after fetch, before DomainFR).
VALIDATION_VERDICTS = Counter(
    "detection_validation_verdicts_total",
    "Page validation outcomes (valid, http_error, soft_404, redirected_to_home)",
    labelnames=("verdict",),
)

# Homepage fallback triggers and outcomes.
HOMEPAGE_FALLBACK_TRIGGERED = Counter(
    "detection_homepage_fallback_triggered_total",
    "Homepage fallback triggers and their outcomes",
    labelnames=("outcome",),
)

# Times alternative-URL validation was skipped because validate_alternatives=false.
VALIDATION_SKIPPED = Counter(
    "detection_alt_validation_skipped_total",
    "Times alternative-URL validation (httpx + browser + Case-6) was skipped because validate_alternatives=false",
)

# Async job API metrics.
ASYNC_JOBS_SUBMITTED = Counter(
    "detect_async_jobs_submitted_total",
    "Async batch jobs accepted (202)",
)
ASYNC_JOBS_ACTIVE = Gauge(
    "detect_async_jobs_active",
    "Currently reserved/in-flight async jobs",
)
ASYNC_JOBS_TERMINAL = Counter(
    "detect_async_jobs_terminal_total",
    "Async jobs reaching a terminal status",
    labelnames=("status",),
)
ASYNC_JOB_DURATION = Histogram(
    "detect_async_job_duration_seconds",
    "Async job wall-clock from running to terminal",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)
ASYNC_JOB_CAPACITY_REJECTED = Counter(
    "detect_async_job_capacity_rejected_total",
    "Submits rejected because MAX_ACTIVE_JOBS was reached",
)
