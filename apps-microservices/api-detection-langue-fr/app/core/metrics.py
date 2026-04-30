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
