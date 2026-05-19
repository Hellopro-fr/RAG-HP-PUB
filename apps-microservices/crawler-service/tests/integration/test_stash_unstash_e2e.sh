#!/bin/bash
# E2E test: stash + unstash round-trip against a real (test) GCS bucket.
# Requires: GCS_BUCKET_NAME env var, gcloud auth login already done,
# and docker-compose --profile crawling up running.
set -euo pipefail

: "${GCS_BUCKET_NAME:?Set GCS_BUCKET_NAME to a test bucket}"
SERVICE_URL="${SERVICE_URL:-http://localhost:8503/crawler}"
CRAWL_ID="e2e-stash-$(date +%s)"

cleanup() {
    gcloud storage rm "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" 2>/dev/null || true
    curl -s -X POST "$SERVICE_URL/force-finish/$CRAWL_ID?target_status=failed" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Step 1: Seed test crawl ==="
# Inject a fake crawl into Redis with synthetic on-disk data
docker exec -i $(docker ps -qf name=crawler-service | head -1) sh -c "
mkdir -p /app/storage/$CRAWL_ID
echo '{\"records\": [1,2,3]}' > /app/storage/$CRAWL_ID/dataset.json
" || { echo "Failed to seed crawl data"; exit 1; }

# (Step 1a) Manually register the job in Redis via direct redis-cli or via a test endpoint.
# Skip if your environment provides a fixture; otherwise use redis-cli:
redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" SET "crawl_job:$CRAWL_ID" \
  "{\"crawl_id\":\"$CRAWL_ID\",\"status\":\"failed\",\"storage_path\":\"/app/storage/$CRAWL_ID\",\"domain\":\"e2e.test\"}" \
  >/dev/null

echo "=== Step 2: POST /stash ==="
resp=$(curl -s -w "\n%{http_code}" -X POST "$SERVICE_URL/stash/$CRAWL_ID")
code=$(echo "$resp" | tail -1)
[ "$code" = "202" ] || { echo "FAIL: stash returned $code (expected 202)"; echo "$resp"; exit 1; }
echo "PASS — stash returned 202"

echo "=== Step 3: Wait for upload daemon ==="
for i in $(seq 1 60); do
    if gcloud storage ls "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" >/dev/null 2>&1; then
        echo "PASS — GCS object present after ${i}s"
        break
    fi
    sleep 1
done
gcloud storage ls "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" >/dev/null 2>&1 || { echo "FAIL: GCS object never appeared"; exit 1; }

echo "=== Step 4: Verify local data deleted ==="
docker exec -i $(docker ps -qf name=crawler-service | head -1) test ! -d "/app/storage/$CRAWL_ID" \
  || { echo "FAIL: local dir not deleted"; exit 1; }
echo "PASS"

echo "=== Step 5: POST /unstash ==="
resp=$(curl -s -w "\n%{http_code}" -X POST "$SERVICE_URL/unstash/$CRAWL_ID")
code=$(echo "$resp" | tail -1)
body=$(echo "$resp" | head -n -1)
[ "$code" = "200" ] || { echo "FAIL: unstash returned $code"; echo "$body"; exit 1; }
echo "$body" | grep -q "unstashed" || { echo "FAIL: missing unstashed status"; echo "$body"; exit 1; }
echo "PASS — unstash returned 200"

echo "=== Step 6: Verify local data restored + GCS cleaned ==="
docker exec -i $(docker ps -qf name=crawler-service | head -1) test -d "/app/storage/$CRAWL_ID" \
  || { echo "FAIL: local dir not restored"; exit 1; }
gcloud storage ls "gs://$GCS_BUCKET_NAME/stash/$CRAWL_ID.tar.gz" >/dev/null 2>&1 \
  && { echo "FAIL: GCS object still present (orphan)"; exit 1; } \
  || echo "PASS — GCS object cleaned"

echo ""
echo "E2E STASH/UNSTASH ROUND-TRIP PASS"
