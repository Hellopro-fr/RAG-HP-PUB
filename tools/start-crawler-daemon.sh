#!/bin/bash
# tools/start-crawler-daemon.sh
# Interactive launcher for the 4 crawler-service daemon variants
# (archive + stash, upload + download). Detects existing screen sessions
# and prompts per-daemon to skip/restart/start.
#
# Note: the Stash Download daemon also runs the Phase-3 stash->crawls move loop
# (ENABLE_MOVE=true). download_daemon.sh always runs its download loop and only
# additionally runs the move loop when ENABLE_MOVE=true, so the move is folded
# into that single daemon — do NOT start a second move-enabled instance (two
# daemons would race the same gcloud mv).
#
# Usage:
#   bash tools/start-crawler-daemon.sh
#
# Prerequisites:
#   - GNU screen installed
#   - GCS_BUCKET_NAME in .env at repo root
#   - Host stash bind-source dirs pre-created + chowned (see
#     docs/daemon_guide.md "Troubleshooting: 503 BIND_MOUNT_MISSING")
#
# Exit codes:
#   0 - completed (some daemons may have been skipped)
#   1 - aborted via 'q' or fatal error

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOGS_DIR="$REPO_ROOT/logs"
mkdir -p "$LOGS_DIR"

STASH_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_stash"
STASH_REQ_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_stash_download_requests"
STASH_RES_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_stash_download_results"
MOVE_REQ_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_move_requests"
MOVE_RES_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_move_results"

# Daemon table: NAME|SCREEN|SCRIPT|ENV_VARS
DAEMONS=(
    "Archive Upload|crawler-upload-archive|tools/upload_daemon.sh|"
    "Stash Upload|crawler-upload-stash|tools/upload_daemon.sh|UPLOAD_WATCH_DIR=$STASH_DIR UPLOAD_GCS_PREFIX=stash"
    "Archive Download|crawler-download-archive|tools/download_daemon.sh|"
    "Stash Download|crawler-download-stash|tools/download_daemon.sh|DOWNLOAD_REQUESTS_PATH=$STASH_REQ_DIR DOWNLOAD_RESULTS_PATH=$STASH_RES_DIR DOWNLOAD_GCS_PREFIX=stash DELETE_AFTER_DOWNLOAD=true ENABLE_MOVE=true MOVE_REQUESTS_PATH=$MOVE_REQ_DIR MOVE_RESULTS_PATH=$MOVE_RES_DIR"
)

is_running() {
    screen -ls 2>/dev/null | grep -q "\.$1[[:space:]]"
}

get_pid() {
    screen -ls 2>/dev/null | grep "\.$1[[:space:]]" \
        | awk -F'.' '{print $1}' | tr -d ' \t'
}

stop_daemon() {
    local screen_name="$1"
    echo "  Stopping $screen_name..."
    screen -X -S "$screen_name" quit 2>/dev/null || true
    sleep 1
}

start_daemon() {
    local name="$1"
    local screen_name="$2"
    local script="$3"
    local env_vars="$4"
    local log_file="$LOGS_DIR/$screen_name.log"

    # Build "export KEY=VAL; ..." prefix for env vars
    local exports=""
    if [ -n "$env_vars" ]; then
        for kv in $env_vars; do
            exports="${exports}export $kv; "
        done
    fi

    echo "  Starting $name (log: $log_file)..."
    screen -dmS "$screen_name" \
        bash -c "${exports}$script 2>&1 | tee -a '$log_file'"
    sleep 1

    if is_running "$screen_name"; then
        echo "  OK $name running in screen $screen_name (PID $(get_pid "$screen_name"))"
    else
        echo "  FAIL: $name not running. Check $log_file"
        return 1
    fi
}

echo "==================================="
echo "Crawler Daemon Launcher"
echo "==================================="

for entry in "${DAEMONS[@]}"; do
    IFS='|' read -r name screen_name script env_vars <<< "$entry"

    echo ""
    echo "=== $name ==="

    if is_running "$screen_name"; then
        echo "Already running in screen: $screen_name (PID $(get_pid "$screen_name"))"
        read -rp "(s)kip / (r)estart / (q)uit [s]: " choice
        choice="${choice:-s}"
        case "$choice" in
            r|R)
                stop_daemon "$screen_name"
                start_daemon "$name" "$screen_name" "$script" "$env_vars"
                ;;
            q|Q)
                echo "Aborted by user."
                exit 1
                ;;
            *)
                echo "  Skipped."
                ;;
        esac
    else
        echo "Not running."
        read -rp "(s)tart / (n)o / (q)uit [n]: " choice
        choice="${choice:-n}"
        case "$choice" in
            s|S|y|Y)
                start_daemon "$name" "$screen_name" "$script" "$env_vars"
                ;;
            q|Q)
                echo "Aborted by user."
                exit 1
                ;;
            *)
                echo "  Skipped."
                ;;
        esac
    fi
done

echo ""
echo "=== Summary ==="
running=$(screen -ls 2>/dev/null \
    | grep -E "\.crawler-(upload|download)-(archive|stash)" || true)
if [ -n "$running" ]; then
    echo "$running"
else
    echo "No crawler daemons running."
fi
