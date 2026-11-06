#!/usr/bin/env bash
# The API contract crosses the service boundary as two committed files: the backend's
# openapi.json and the frontend's generated schema.d.ts. Fail if either is stale.
set -euo pipefail
cd "$(dirname "$0")/.."
FRONT=../agent-task-manager-frontend
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SQLX_OFFLINE=true cargo run -q -p atb-server -- dump-openapi >"$TMP/openapi.json"
if ! diff -q openapi.json "$TMP/openapi.json" >/dev/null; then
  echo "openapi.json is stale: run 'cargo run -p atb-server -- dump-openapi > openapi.json'" >&2
  exit 1
fi
(cd "$FRONT" && npx --no-install openapi-typescript ../agent-task-manager-backend/openapi.json \
  -o "$TMP/schema.d.ts" --empty-objects-unknown >/dev/null)
if ! diff -q "$FRONT/src/lib/api/schema.d.ts" "$TMP/schema.d.ts" >/dev/null; then
  echo "frontend schema.d.ts is stale: run 'npm run gen:api' in $FRONT" >&2
  exit 1
fi
echo ATB_OPENAPI_IN_SYNC
