#!/usr/bin/env bash
# Capture des réponses Express (référence) pour comparaison post-cutover.
#
# Usage :
#   bash tests/capture_snapshots.sh <NODE_URL> <ADMIN_PASSWORD>

set -euo pipefail

URL="${1:-http://localhost:3001}"
PWD="${2:?Usage: capture_snapshots.sh <URL> <ADMIN_PASSWORD>}"
SNAP_DIR="$(dirname "$0")/contract_snapshots"
mkdir -p "$SNAP_DIR"

TOKEN=$(curl -s -X POST "$URL/api/login" \
    -d "{\"password\":\"$PWD\"}" \
    -H "Content-Type: application/json" | jq -r .token)
[ "$TOKEN" = "null" ] && { echo "Login failed"; exit 1; }

ID=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/jobs" | jq -r '.[0].id // .[0]._id // empty')

ROUTES=(
    "/health"
    "/api/jobs"
    "/api/capacity"
    "/api/system/stats"
    "/api/system/health"
    "/api/audit"
    "/api/timeline"
    "/api/domains"
    "/api/alerts"
    "/api/replicas/history"
    "/api/callbacks"
    "/api/capacity-planning/ram"
    "/api/capacity/history"
)
if [ -n "$ID" ]; then
    ROUTES+=(
        "/api/jobs/$ID/details"
        "/api/jobs/$ID/performance"
        "/api/jobs/$ID/replay"
        "/api/jobs/$ID/dataset/counts"
        "/api/jobs/$ID/request-queues/analyze"
    )
fi

for r in "${ROUTES[@]}"; do
    fn="${r//\//_}"
    fn="${fn:1}"
    out=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL$r")
    if [ -n "$out" ]; then
        echo "$out" > "$SNAP_DIR/${fn}.json"
        echo "✅ Captured $r → ${fn}.json"
    else
        echo "⚠️  Empty response for $r"
    fi
done

echo ""
echo "Snapshots in $SNAP_DIR :"
ls -la "$SNAP_DIR"
