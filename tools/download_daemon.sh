#!/bin/bash

# Download Daemon — Downloads archived crawl data from Google Cloud Storage
# Mirrors the upload_daemon.sh pattern: polls a shared volume for .request files,
# downloads the corresponding archive from GCS, and signals completion.
#
# Usage:
#   ./tools/download_daemon.sh
#
# Environment variables:
#   GCS_BUCKET_NAME          (required)  Source bucket.
#   DOWNLOAD_REQUESTS_PATH   (optional)  Host dir polled for .request markers
#                                        (default: apps-microservices/crawler-service/crawler_download_requests).
#                                        Must match the crawler-service host bind source for
#                                        compose target /app/download_requests; same env var name
#                                        as Python (app/core/config.py) for cross-layer parity.
#   DOWNLOAD_RESULTS_PATH    (optional)  Host dir where downloaded archives + .done/.error
#                                        markers are written (default:
#                                        apps-microservices/crawler-service/crawler_download_results).
#                                        Same parity rules as DOWNLOAD_REQUESTS_PATH.
#   DOWNLOAD_GCS_PREFIX      (optional)  GCS path prefix under the bucket (default: crawls).
#                                        Set to "stash" for the stash/unstash flow.
#   DELETE_AFTER_DOWNLOAD    (optional)  Enable 2-phase commit GCS cleanup (default: false).
#                                        When true, daemon scans for {id}.unstash-confirmed,
#                                        deletes the GCS source, and writes {id}.unstash-cleanup-done.
#
# Flow (archive download, DELETE_AFTER_DOWNLOAD=false):
#   1. Service writes {crawl_id}.request to the requests directory
#   2. This daemon picks it up, downloads gs://{bucket}/{prefix}/{crawl_id}.tar.gz
#   3. Places the archive in the results directory + writes {crawl_id}.done
#   4. Service detects .done, streams the file to the client, then cleans up
#
# Flow (stash unstash, DELETE_AFTER_DOWNLOAD=true):
#   Steps 1-4 above, then:
#   5. Service extracts tar successfully, writes {crawl_id}.unstash-confirmed
#   6. Daemon detects .unstash-confirmed, deletes GCS source, writes .unstash-cleanup-done
#   7. Service polls .unstash-cleanup-done to clear Redis stash flag

# Configuration
DEFAULT_REQUESTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_requests"
REQUESTS_DIR="${DOWNLOAD_REQUESTS_PATH:-$DEFAULT_REQUESTS_DIR}"

DEFAULT_RESULTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_results"
RESULTS_DIR="${DOWNLOAD_RESULTS_PATH:-$DEFAULT_RESULTS_DIR}"
DOWNLOAD_GCS_PREFIX="${DOWNLOAD_GCS_PREFIX:-crawls}"
DELETE_AFTER_DOWNLOAD="${DELETE_AFTER_DOWNLOAD:-false}"

# Load .env from parent directory
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

if [ -z "$GCS_BUCKET_NAME" ]; then
    echo "ERROR: GCS_BUCKET_NAME is not set. Please check your .env file."
    exit 1
fi

BUCKET_NAME="$GCS_BUCKET_NAME"
CHECK_INTERVAL=5 # Seconds (faster than upload daemon since the user is waiting)

# Ensure directories exist
mkdir -p "$REQUESTS_DIR" "$RESULTS_DIR"

echo "Starting Download Daemon..."
echo "Watching requests: $REQUESTS_DIR"
echo "Writing results:   $RESULTS_DIR"
echo "Source Bucket:      gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/"
echo "Delete after dl:   $DELETE_AFTER_DOWNLOAD"
echo "Poll interval:      ${CHECK_INTERVAL}s"

while true; do
    find "$REQUESTS_DIR" -maxdepth 1 -name "*.request" -print0 | while IFS= read -r -d '' request_file; do
        crawl_id=$(basename "$request_file" .request)
        echo "[$(date)] Download request received: $crawl_id"

        source_url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"
        target_path="$RESULTS_DIR/$crawl_id.tar.gz"
        done_marker="$RESULTS_DIR/$crawl_id.done"
        error_marker="$RESULTS_DIR/$crawl_id.error"

        echo "Downloading $source_url ..."
        if gcloud storage cp "$source_url" "$target_path"; then
            echo "Download successful: $target_path"

            # Signal completion
            touch "$done_marker"
            rm "$request_file"
            echo "Ready for pickup: $crawl_id"
        else
            echo "ERROR: Download failed for $crawl_id."

            # Write error marker so the service doesn't wait forever
            echo "Download failed from $source_url at $(date)" > "$error_marker"
            rm "$request_file"
        fi
    done

    # Phase 2 (2-phase commit): scan for service-written .unstash-confirmed markers
    # and delete the GCS source. Only active when DELETE_AFTER_DOWNLOAD=true.
    # Service writes {id}.unstash-confirmed after successful extract; daemon
    # responds by deleting the GCS object and writing {id}.unstash-cleanup-done.
    if [ "$DELETE_AFTER_DOWNLOAD" = "true" ]; then
        find "$RESULTS_DIR" -maxdepth 1 -name "*.unstash-confirmed" -print0 | while IFS= read -r -d '' confirm_file; do
            crawl_id=$(basename "$confirm_file" .unstash-confirmed)
            source_url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"
            cleanup_done="$RESULTS_DIR/$crawl_id.unstash-cleanup-done"

            echo "[$(date)] Extract confirmed for $crawl_id, deleting GCS source..."
            if gcloud storage rm "$source_url"; then
                echo "GCS source deleted: $source_url"
                touch "$cleanup_done"
                rm "$confirm_file"
            else
                echo "WARNING: gcloud storage rm failed for $source_url. Leaving .unstash-confirmed for retry on next poll."
                # Intentionally do NOT touch cleanup_done and do NOT remove confirm_file:
                # the service will time out and operator can investigate. Next daemon
                # poll cycle will retry the gcloud rm.
            fi
        done
    fi

    sleep $CHECK_INTERVAL
done
