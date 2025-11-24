#!/bin/bash

# Configuration
# Path relative to this script (tools/) -> root -> apps-microservices/crawler-service/crawler_archives
ARCHIVES_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_archives"
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

# Ensure archives directory exists
mkdir -p "$ARCHIVES_DIR"

echo "Starting Upload Daemon..."
echo "Watching directory: $ARCHIVES_DIR"
echo "Target Bucket: gs://$BUCKET_NAME/crawls/"

while true; do
    # Find all .tar.gz files in the directory
    # We use a loop to handle filenames with spaces correctly, though unlikely here
    find "$ARCHIVES_DIR" -maxdepth 1 -name "*.tar.gz" -print0 | while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        echo "[$(date)] Found archive: $filename"
        
        # Upload to GCS
        # Structure: gs://{BUCKET}/crawls/{filename}
        target_url="gs://$BUCKET_NAME/crawls/$filename"
        
        echo "Uploading to $target_url ..."
        if gcloud storage cp "$file" "$target_url"; then
            echo "Upload successful."
            
            # Remove local file on success
            rm "$file"
            echo "Deleted local file: $file"
        else
            echo "ERROR: Upload failed for $file. Retrying in next cycle."
        fi
    done
    
    # Wait for next cycle
    sleep $CHECK_INTERVAL
done
