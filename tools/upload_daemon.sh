#!/bin/bash

# Configuration
# Path relative to this script (tools/) -> root -> apps-microservices/crawler-service/crawler_archives
DEFAULT_ARCHIVES_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_archives"
ARCHIVES_DIR="${ARCHIVES_DIR:-$DEFAULT_ARCHIVES_DIR}"
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
DEAD_LETTER_DIR="$ARCHIVES_DIR/dead_letter"

# Ensure archives directory exists
mkdir -p "$ARCHIVES_DIR"
mkdir -p "$DEAD_LETTER_DIR"

# Change ownership of the shared directories to the current user
# This is necessary because Docker creates volume mount points as root
sudo chown -R $USER:$USER "$ARCHIVES_DIR"
sudo chown -R $USER:$USER "$DEAD_LETTER_DIR"

echo "Starting Upload Daemon..."
echo "Watching directory: $ARCHIVES_DIR"
echo "Target Bucket: gs://$BUCKET_NAME/crawls/"

while true; do
    # Find all .tar.gz files in the directory (exclude dead_letter subdirectory)
    find "$ARCHIVES_DIR" -maxdepth 1 -name "*.tar.gz" -print0 | while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        retries_file="${file}.retries"
        echo "[$(date)] Found archive: $filename"

        # Upload to GCS
        # Structure: gs://{BUCKET}/crawls/{filename}
        target_url="gs://$BUCKET_NAME/crawls/$filename"

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

    # Wait for next cycle
    sleep $CHECK_INTERVAL
done
