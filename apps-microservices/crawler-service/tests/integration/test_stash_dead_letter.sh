#!/bin/bash
# Dead-letter test: point upload daemon at invalid bucket, drop a fake .tar.gz,
# verify dead_letter/ contains the file after 3 retries.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
UPLOAD="$ROOT/tools/upload_daemon.sh"
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/watch"

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

# Drop a tiny fake archive
echo "fake" > "$TMPDIR/watch/test.tar.gz"

# Run daemon for long enough to exhaust 3 retries (assuming CHECK_INTERVAL=60 -> 4 cycles = 240s).
# For test purposes the daemon needs faster retries; tweak via env or run for full TTL.
GCS_BUCKET_NAME=nonexistent-test-bucket-$RANDOM \
UPLOAD_WATCH_DIR="$TMPDIR/watch" \
UPLOAD_GCS_PREFIX=stash \
timeout 270 bash "$UPLOAD" 2>&1 > "$TMPDIR/daemon.log" || true

# Verify file moved to dead_letter
if [ -f "$TMPDIR/watch/dead_letter/test.tar.gz" ]; then
    echo "PASS — file moved to dead_letter after 3 retries"
else
    echo "FAIL — file not in dead_letter"
    echo "Daemon log:"
    cat "$TMPDIR/daemon.log" | tail -30
    exit 1
fi
