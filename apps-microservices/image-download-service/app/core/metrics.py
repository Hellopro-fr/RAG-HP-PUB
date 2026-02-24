"""
Centralized Prometheus metrics for image-download-service.
All counters/gauges/histograms are declared here and imported by other modules.
Each metric carries a 'replica_id' label for per-replica monitoring.
"""
import os
import socket
from prometheus_client import (
    Counter, Gauge, Histogram, Info,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

# ---------------------------------------------------------------------------
# Registry (custom to avoid default process/platform collectors if desired)
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# Replica identification — unique per container/replica
# ---------------------------------------------------------------------------
REPLICA_ID = os.environ.get("HOSTNAME", socket.gethostname())

# Common label names shared across most metrics
_REPLICA_LABELS = ["replica_id"]
_DOMAIN_LABELS = ["replica_id", "domain"]

# ---------------------------------------------------------------------------
# 📥 DOWNLOADS
# ---------------------------------------------------------------------------
DOWNLOADS_TOTAL = Counter(
    "ids_downloads_total",
    "Total number of image downloads attempted",
    labelnames=["replica_id", "domain", "status"],  # status: success|failed|skipped
    registry=REGISTRY,
)

DOWNLOADS_IN_PROGRESS = Gauge(
    "ids_downloads_in_progress",
    "Number of downloads currently in progress",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

DOWNLOAD_DURATION_SECONDS = Histogram(
    "ids_download_duration_seconds",
    "Duration of individual image downloads",
    labelnames=_DOMAIN_LABELS,
    buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
    registry=REGISTRY,
)

DOWNLOAD_BYTES_TOTAL = Counter(
    "ids_download_bytes_total",
    "Total bytes downloaded (bandwidth)",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# ❌ HTTP ERRORS
# ---------------------------------------------------------------------------
HTTP_ERRORS_TOTAL = Counter(
    "ids_http_errors_total",
    "HTTP error responses received during downloads",
    labelnames=["replica_id", "domain", "status_code"],
    registry=REGISTRY,
)

DOWNLOAD_RETRIES_TOTAL = Counter(
    "ids_download_retries_total",
    "Total number of download retry attempts",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

DOWNLOAD_FAILURES_TOTAL = Counter(
    "ids_download_failures_total",
    "Downloads that failed after all retries",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 🔌 PROXY
# ---------------------------------------------------------------------------
PROXY_REQUESTS_TOTAL = Counter(
    "ids_proxy_requests_total",
    "Total requests made through the proxy",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

PROXY_ERRORS_TOTAL = Counter(
    "ids_proxy_errors_total",
    "Errors encountered via proxy",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

PROXY_ACTIVE = Gauge(
    "ids_proxy_active",
    "Whether proxy is configured and active (1=yes, 0=no)",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 🖼️ IMAGE PROCESSING
# ---------------------------------------------------------------------------
IMAGES_PROCESSED_TOTAL = Counter(
    "ids_images_processed_total",
    "Total images successfully processed",
    labelnames=["replica_id", "domain", "format"],  # format: jpg|png|gif|webp
    registry=REGISTRY,
)

IMAGES_SKIPPED_TOTAL = Counter(
    "ids_images_skipped_total",
    "Images skipped due to deduplication",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

IMAGE_PROCESSING_DURATION = Histogram(
    "ids_image_processing_duration_seconds",
    "Duration of image processing (resize + thumbnail)",
    labelnames=["replica_id", "domain", "processor"],  # processor: pil|vips
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
    registry=REGISTRY,
)

LARGE_IMAGES_VIPS_TOTAL = Counter(
    "ids_large_images_vips_total",
    "Images routed to pyvips due to large size (>50Mpx)",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 💾 STORAGE
# ---------------------------------------------------------------------------
DISK_USAGE_BYTES = Gauge(
    "ids_disk_usage_bytes",
    "Disk space used by image storage",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

DISK_TOTAL_BYTES = Gauge(
    "ids_disk_total_bytes",
    "Total disk space on storage volume",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

DISK_FREE_BYTES = Gauge(
    "ids_disk_free_bytes",
    "Free disk space on storage volume",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

DOMAIN_DISK_USAGE_BYTES = Gauge(
    "ids_domain_disk_usage_bytes",
    "Disk space used per domain",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 📨 RABBITMQ / MESSAGING
# ---------------------------------------------------------------------------
MESSAGES_RECEIVED_TOTAL = Counter(
    "ids_messages_received_total",
    "Total messages received from RabbitMQ",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

MESSAGES_PROCESSED_TOTAL = Counter(
    "ids_messages_processed_total",
    "Messages successfully processed",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

MESSAGES_SKIPPED_TOTAL = Counter(
    "ids_messages_skipped_total",
    "Messages skipped (source filter)",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

MESSAGES_DLQ_TOTAL = Counter(
    "ids_messages_dlq_total",
    "Messages sent to Dead Letter Queue",
    labelnames=["replica_id", "error_type"],  # error_type: permanent|exhausted
    registry=REGISTRY,
)

MESSAGES_RETRIED_TOTAL = Counter(
    "ids_messages_retried_total",
    "Messages sent for retry (nack)",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 🏷️ PRODUCTS / DOMAINS
# ---------------------------------------------------------------------------
PRODUCTS_PER_DOMAIN = Gauge(
    "ids_products_per_domain",
    "Number of products stored per domain",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

IMAGES_PER_DOMAIN = Gauge(
    "ids_images_per_domain",
    "Number of images stored per domain",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

UNSYNCED_PRODUCTS_PER_DOMAIN = Gauge(
    "ids_unsynced_products_per_domain",
    "Products not yet synced per domain",
    labelnames=_DOMAIN_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# 🖥️ SERVICE INFO
# ---------------------------------------------------------------------------
SERVICE_INFO = Info(
    "ids_service",
    "Image Download Service metadata",
    registry=REGISTRY,
)
SERVICE_INFO.info({
    "version": "2.0.0",
    "replica_id": REPLICA_ID,
})

SERVICE_UPTIME = Gauge(
    "ids_service_uptime_seconds",
    "Service uptime in seconds",
    labelnames=_REPLICA_LABELS,
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Helper: generate metrics output
# ---------------------------------------------------------------------------
def get_metrics() -> bytes:
    """Return Prometheus-formatted metrics bytes."""
    return generate_latest(REGISTRY)

def get_content_type() -> str:
    """Return the correct Content-Type header for Prometheus."""
    return CONTENT_TYPE_LATEST
