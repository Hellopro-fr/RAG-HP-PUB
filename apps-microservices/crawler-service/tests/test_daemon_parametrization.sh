#!/bin/bash
# Verify upload_daemon.sh and download_daemon.sh respect env-var overrides
# without touching real GCS. Uses string-grep on startup log output.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
UPLOAD="$ROOT/tools/upload_daemon.sh"
DOWNLOAD="$ROOT/tools/download_daemon.sh"

echo "=== Test 1: upload_daemon.sh default env preserves crawls/ prefix ==="
out=$(GCS_BUCKET_NAME=testbucket timeout 2 bash "$UPLOAD" 2>&1 || true)
echo "$out" | grep -q "Target Bucket: gs://testbucket/crawls/" || { echo "FAIL: default prefix wrong"; echo "$out"; exit 1; }
echo "PASS"

echo "=== Test 2: upload_daemon.sh UPLOAD_GCS_PREFIX=stash routes to stash/ ==="
TMPDIR=$(mktemp -d); mkdir -p "$TMPDIR/watch"
out=$(GCS_BUCKET_NAME=testbucket UPLOAD_WATCH_DIR="$TMPDIR/watch" UPLOAD_GCS_PREFIX=stash timeout 2 bash "$UPLOAD" 2>&1 || true)
echo "$out" | grep -q "Target Bucket: gs://testbucket/stash/" || { echo "FAIL: stash prefix not routed"; echo "$out"; exit 1; }
rm -rf "$TMPDIR"
echo "PASS"

echo "=== Test 3: download_daemon.sh default env preserves crawls/ prefix ==="
out=$(GCS_BUCKET_NAME=testbucket timeout 2 bash "$DOWNLOAD" 2>&1 || true)
echo "$out" | grep -q "Source Bucket:      gs://testbucket/crawls/" || { echo "FAIL: default prefix wrong"; echo "$out"; exit 1; }
echo "$out" | grep -q "Delete after dl:   false" || { echo "FAIL: DELETE_AFTER_DOWNLOAD default not false"; echo "$out"; exit 1; }
echo "PASS"

echo "=== Test 4: download_daemon.sh DELETE_AFTER_DOWNLOAD=true picks up .unstash-confirmed ==="
TMPDIR=$(mktemp -d); mkdir -p "$TMPDIR/req" "$TMPDIR/res"
touch "$TMPDIR/res/test123.unstash-confirmed"
out=$(GCS_BUCKET_NAME=nonexistent DOWNLOAD_REQUESTS_PATH="$TMPDIR/req" DOWNLOAD_RESULTS_PATH="$TMPDIR/res" \
     DOWNLOAD_GCS_PREFIX=stash DELETE_AFTER_DOWNLOAD=true timeout 8 bash "$DOWNLOAD" 2>&1 || true)
echo "$out" | grep -q "Extract confirmed for test123" || { echo "FAIL: cleanup branch not entered"; echo "$out"; exit 1; }
# Marker retained on failure (gcloud rm fails because bucket doesn't exist)
[ -f "$TMPDIR/res/test123.unstash-confirmed" ] || { echo "FAIL: marker removed despite failure"; exit 1; }
rm -rf "$TMPDIR"
echo "PASS"

echo ""
echo "ALL DAEMON PARAMETRIZATION TESTS PASS"
