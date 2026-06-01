#!/bin/bash
# Test the move loop of download_daemon.sh with a mocked gcloud.
set -euo pipefail
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Mock gcloud:
#   - "42": mv succeeds.
#   - "already": mv fails (source gone) but ls(dst) succeeds -> idempotent done.
#   - "fail": mv fails AND ls(dst) fails -> genuine failure.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/gcloud" <<'EOF'
#!/bin/bash
# args: storage mv SRC DST   OR   storage ls SRC
if [ "$2" = "mv" ]; then
  case "$3" in
    *already.tar.gz) exit 1 ;;   # source already gone
    *fail.tar.gz)    exit 1 ;;   # genuine move failure
    *) echo "moved $3 -> $4"; exit 0 ;;
  esac
fi
if [ "$2" = "ls" ]; then
  case "$3" in
    *crawls/already.tar.gz) exit 0 ;;  # target present -> already moved
    *) exit 1 ;;                        # target absent (incl. fail) -> not moved
  esac
fi
exit 0
EOF
chmod +x "$TMP/bin/gcloud"
export PATH="$TMP/bin:$PATH"

export GCS_BUCKET_NAME="test-bucket"
export MOVE_REQUESTS_PATH="$TMP/req"
export MOVE_RESULTS_PATH="$TMP/res"
export ENABLE_MOVE="true"
mkdir -p "$MOVE_REQUESTS_PATH" "$MOVE_RESULTS_PATH"

# Source the daemon's functions only (no infinite loop).
source "$(dirname "$0")/download_daemon.sh" --source-functions-only

# Happy path
echo "1" > "$MOVE_REQUESTS_PATH/42.move-request"
process_move_requests
[ -f "$MOVE_RESULTS_PATH/42.move-done" ] || { echo "FAIL: 42.move-done missing"; exit 1; }
[ ! -f "$MOVE_REQUESTS_PATH/42.move-request" ] || { echo "FAIL: request not consumed"; exit 1; }

# Idempotent already-moved path
echo "1" > "$MOVE_REQUESTS_PATH/already.move-request"
process_move_requests
[ -f "$MOVE_RESULTS_PATH/already.move-done" ] || { echo "FAIL: already.move-done missing (idempotent)"; exit 1; }

# Genuine failure path: .move-error written, NO .move-done, request consumed.
echo "1" > "$MOVE_REQUESTS_PATH/fail.move-request"
process_move_requests
[ -f "$MOVE_RESULTS_PATH/fail.move-error" ] || { echo "FAIL: fail.move-error missing"; exit 1; }
[ -s "$MOVE_RESULTS_PATH/fail.move-error" ] || { echo "FAIL: fail.move-error is empty"; exit 1; }
[ ! -f "$MOVE_RESULTS_PATH/fail.move-done" ] || { echo "FAIL: fail wrongly marked done"; exit 1; }
[ ! -f "$MOVE_REQUESTS_PATH/fail.move-request" ] || { echo "FAIL: fail request not consumed"; exit 1; }

echo "OK"
