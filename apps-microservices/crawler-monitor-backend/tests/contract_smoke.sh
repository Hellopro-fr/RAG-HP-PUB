#!/usr/bin/env bash
# Smoke test contractuel : compare les réponses Go aux snapshots Node de référence.
#
# Usage :
#   bash tests/contract_smoke.sh <URL> <ADMIN_PASSWORD>
#
# Exit 0 si toutes les routes match, N sinon avec diff visible.

set -euo pipefail

URL="${1:-http://localhost:3002}"
PWD="${2:?Usage: contract_smoke.sh <URL> <ADMIN_PASSWORD>}"
SNAP_DIR="$(dirname "$0")/contract_snapshots"

if [ ! -d "$SNAP_DIR" ] || [ -z "$(ls -A "$SNAP_DIR"/*.json 2>/dev/null)" ]; then
    echo "❌ No snapshots in $SNAP_DIR"
    echo "   Capturer d'abord les snapshots Node avec capture_snapshots.sh"
    exit 1
fi

TOKEN=$(curl -s -X POST "$URL/api/login" \
    -d "{\"password\":\"$PWD\"}" \
    -H "Content-Type: application/json" | jq -r .token)
if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo "❌ Login failed against $URL"
    exit 1
fi
echo "✅ Login OK"

FAILED=0
TOTAL=0

for snap in "$SNAP_DIR"/*.json; do
    [ -f "$snap" ] || continue
    TOTAL=$((TOTAL+1))
    fname=$(basename "$snap" .json)
    path="/${fname//_/\/}"

    expected=$(cat "$snap")
    actual=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL$path")

    if diff <(echo "$expected" | jq -S . 2>/dev/null) <(echo "$actual" | jq -S . 2>/dev/null) >/dev/null 2>&1; then
        echo "✅ $path"
    else
        echo "❌ $path"
        diff <(echo "$expected" | jq -S . 2>/dev/null) <(echo "$actual" | jq -S . 2>/dev/null) | head -10
        FAILED=$((FAILED+1))
    fi
done

echo ""
echo "Total : $TOTAL routes, $FAILED divergences"
exit $FAILED
