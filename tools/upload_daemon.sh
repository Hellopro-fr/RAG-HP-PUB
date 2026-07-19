#!/bin/bash

# Configuration
# UPLOAD_WATCH_DIR: dir scanned for *.tar.gz (default = crawler-service archives)
# UPLOAD_GCS_PREFIX: path component under gs://$BUCKET/ (default = crawls)
# UPLOAD_DEAD_LETTER_SUBDIR: subdir name inside watch dir for retry-exhausted files (default = dead_letter)
DEFAULT_ARCHIVES_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_archives"
ARCHIVES_DIR="${UPLOAD_WATCH_DIR:-${ARCHIVES_DIR:-$DEFAULT_ARCHIVES_DIR}}"
UPLOAD_GCS_PREFIX="${UPLOAD_GCS_PREFIX:-crawls}"
UPLOAD_DEAD_LETTER_SUBDIR="${UPLOAD_DEAD_LETTER_SUBDIR:-dead_letter}"
# Load .env from parent directory
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    # Export variables from .env so they are available
    set -a
    source "$ENV_FILE"
    set +a
fi

if [ -z "$GCS_BUCKET_NAME" ]; then
    echo "ERROR: GCS_BUCKET_NAME is not set. Please check your .env file."
    exit 1
fi

BUCKET_NAME="$GCS_BUCKET_NAME"
CHECK_INTERVAL=60 # Seconds
MAX_RETRIES=3
DEAD_LETTER_DIR="$ARCHIVES_DIR/$UPLOAD_DEAD_LETTER_SUBDIR"

# Ensure archives directory exists
mkdir -p "$ARCHIVES_DIR"
mkdir -p "$DEAD_LETTER_DIR"

# Change ownership of the shared directories to the current user
# This is necessary because Docker creates volume mount points as root
sudo chown -R $USER:$USER "$ARCHIVES_DIR"
sudo chown -R $USER:$USER "$DEAD_LETTER_DIR"

# inotify fast path (optional). When inotify-tools is installed, the wait between
# scan cycles wakes early on filesystem activity in the watched dir(s) — a fresh
# tar is uploaded in seconds instead of up to CHECK_INTERVAL later. The periodic
# full scan is KEPT as the safety net (events missed during a restart or mid-scan
# emit no signal). Without inotifywait the behavior is byte-identical to before
# (plain sleep). NOTE: duplicated in download_daemon.sh — keep in sync.
INOTIFY_AVAILABLE=false
if command -v inotifywait >/dev/null 2>&1; then
    INOTIFY_AVAILABLE=true
fi

# wait_next_cycle <timeout_seconds> <dir> [dir...] — sleep-with-early-wake.
wait_next_cycle() {
    local timeout="$1"; shift
    if [ "$INOTIFY_AVAILABLE" = "true" ]; then
        # Exit codes: 0 = event, 2 = timeout — the only healthy exits; both
        # proceed to the next scan. ANY other code (1 = missing dir / watch
        # limit exhausted, 127 = binary gone, ...) falls back to a plain sleep
        # for this cycle so a broken watch can never busy-loop the daemon.
        inotifywait -qq -t "$timeout" -e close_write -e moved_to -e create "$@" >/dev/null 2>&1
        local rc=$?
        if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
            sleep "$timeout"
        fi
    else
        sleep "$timeout"
    fi
}

echo "Starting Upload Daemon..."
echo "Watching directory: $ARCHIVES_DIR"
echo "Target Bucket: gs://$BUCKET_NAME/$UPLOAD_GCS_PREFIX/"
echo "Watch dir:     $ARCHIVES_DIR"
echo "Dead-letter:   $DEAD_LETTER_DIR"

while true; do
    # Liveness signal read by crawler-service GET /admin/daemon-state.
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$ARCHIVES_DIR/.daemon-heartbeat" 2>/dev/null || true

    # Find all .tar.gz files in the directory (exclude dead_letter subdirectory)
    find "$ARCHIVES_DIR" -maxdepth 1 -name "*.tar.gz" -print0 | while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        retries_file="${file}.retries"
        echo "[$(date)] Found archive: $filename"

        # Upload to GCS
        # Structure: gs://{BUCKET}/crawls/{filename}
        target_url="gs://$BUCKET_NAME/$UPLOAD_GCS_PREFIX/$filename"

        echo "Uploading to $target_url ..."
        if gcloud storage cp "$file" "$target_url"; then
            echo "Upload successful."

            # Remove local file and retry counter on success
            rm "$file"
            rm -f "$retries_file"
            echo "Deleted local file: $file"
        else
            # Read current retry count (default 0)
            current_retries=0
            if [ -f "$retries_file" ]; then
                current_retries=$(cat "$retries_file")
            fi
            current_retries=$((current_retries + 1))

            if [ "$current_retries" -ge "$MAX_RETRIES" ]; then
                echo "WARNING: Upload failed $MAX_RETRIES times for $file. Moving to dead_letter."
                mv "$file" "$DEAD_LETTER_DIR/"
                rm -f "$retries_file"
            else
                echo "ERROR: Upload failed for $file (attempt $current_retries/$MAX_RETRIES). Retrying in next cycle."
                echo "$current_retries" > "$retries_file"
            fi
        fi
    done

    # Wait for next cycle (early wake on new tars when inotify-tools is present)
    wait_next_cycle "$CHECK_INTERVAL" "$ARCHIVES_DIR"
done
