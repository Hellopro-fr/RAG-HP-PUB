#!/usr/bin/env bash
# Smoke test of the whole stack behind the ingress:
#   docker compose up --build --wait, then health, web, OpenAPI, login, and a live SSE event
#   delivered THROUGH the ingress (proves Caddy does not buffer the stream).
# Prints ATB_SMOKE_OK on success.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
. ./.env
set +a
BASE="http://localhost:${ATB_PORT:-8620}"
JAR="$(mktemp)"
STREAM="$(mktemp)"
trap 'rm -f "$JAR" "$STREAM"; kill "${SSE_PID:-0}" 2>/dev/null || true' EXIT

docker compose up -d --build --wait >/dev/null

curl -fsS "$BASE/healthz" | grep -qx ok
curl -fsS "$BASE/readyz" | grep -qx ready
curl -fsS -o /dev/null "$BASE/login"
curl -fsS "$BASE/api/openapi.json" | grep -q '"openapi"'
# Pages without a session redirect to the login page.
test "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/projects")" = "307"

curl -fsS -c "$JAR" -H 'content-type: application/json' \
  -d "{\"login\":\"${ATB_BOOTSTRAP_ADMIN_LOGIN:-admin}\",\"password\":\"${ATB_BOOTSTRAP_ADMIN_PASSWORD}\"}" \
  "$BASE/api/auth/login" >/dev/null
PROJECT=$(curl -fsS -b "$JAR" -H 'content-type: application/json' \
  -d '{"name":"smoke test"}' "$BASE/api/projects" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')

# Open the stream through the ingress, then create a spec: its event must arrive within 2 s.
curl -sN -b "$JAR" "$BASE/api/projects/$PROJECT/stream" >"$STREAM" &
SSE_PID=$!
sleep 1
curl -fsS -b "$JAR" -H 'content-type: application/json' \
  -d '{"title":"s","body_md":"b","acceptance_criteria":[{"id":"AC-1","text":"t","verify":{"kind":"human"}}]}' \
  "$BASE/api/projects/$PROJECT/specs" >/dev/null
for _ in $(seq 1 20); do
  grep -q '^event: spec.version_proposed' "$STREAM" && break
  sleep 0.1
done
grep -q '^event: spec.version_proposed' "$STREAM" || { echo "SSE event not delivered through the ingress" >&2; exit 1; }

docker compose ps --format '{{.Service}} {{.Health}}' | grep -E '^(server|web|ingress) ' | grep -vq healthy && {
  echo "a service is not healthy" >&2
  exit 1
}
echo ATB_SMOKE_OK
