#!/bin/bash

# Download Daemon — Downloads archived crawl data from Google Cloud Storage
# Mirrors the upload_daemon.sh pattern: polls a shared volume for .request files,
# downloads the corresponding archive from GCS, and signals completion.
#
# Usage:
#   ./tools/download_daemon.sh
#
# Flow:
#   1. Service writes {crawl_id}.request to the requests directory
#   2. This daemon picks it up, downloads gs://{bucket}/crawls/{crawl_id}.tar.gz
#   3. Places the archive in the results directory + writes {crawl_id}.done
#   4. Service detects .done, streams the file to the client, then cleans up

# Configuration
DEFAULT_REQUESTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_requests"
REQUESTS_DIR="${DOWNLOAD_REQUESTS_PATH:-$DEFAULT_REQUESTS_DIR}"

DEFAULT_RESULTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_results"
RESULTS_DIR="${DOWNLOAD_RESULTS_PATH:-$DEFAULT_RESULTS_DIR}"

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
echo "Source Bucket:      gs://$BUCKET_NAME/crawls/"
echo "Poll interval:      ${CHECK_INTERVAL}s"

while true; do
    find "$REQUESTS_DIR" -maxdepth 1 -name "*.request" -print0 | while IFS= read -r -d '' request_file; do
        crawl_id=$(basename "$request_file" .request)
        echo "[$(date)] Download request received: $crawl_id"

        source_url="gs://$BUCKET_NAME/crawls/$crawl_id.tar.gz"
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

    sleep $CHECK_INTERVAL
done
