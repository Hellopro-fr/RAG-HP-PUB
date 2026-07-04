#!/bin/bash
# Build crawler-service with deploy identity baked in (served by GET /version),
# and optionally restart + scale the replicas.
#
# Usage:
#   ./tools/build_crawler.sh              # build only
#   ./tools/build_crawler.sh --up         # build + up, scaled to 7 replicas (default)
#   ./tools/build_crawler.sh --up 4       # build + up, scaled to 4 replicas
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GIT_COMMIT="$(git rev-parse --short HEAD)"
BUILD_DATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# A dirty tree means the image won't match the commit — stamp it visibly.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  GIT_COMMIT="${GIT_COMMIT}-dirty"
  echo "WARNING: uncommitted changes in working tree -> stamping ${GIT_COMMIT}"
fi

export GIT_COMMIT BUILD_DATE

echo "Building crawler-service @ ${GIT_COMMIT} (${BUILD_DATE})"
docker compose build crawler-service

if [ "${1:-}" = "--up" ]; then
  REPLICAS="${2:-7}"
  echo "Starting crawler-service scaled to ${REPLICAS} replicas (--no-deps: siblings untouched)"
  docker compose up -d --no-deps --scale "crawler-service=${REPLICAS}" crawler-service

  # Nginx must re-resolve the service hostname to pick up new replica IPs.
  docker compose exec reverse-proxy nginx -s reload \
    || echo "WARNING: nginx reload failed (reverse-proxy not running?) — new replicas may not receive traffic until it is reloaded."

  echo "NOTE: the Redis capacity key is NOT touched by this script. If the replica"
  echo "count changed, sync it: ./apps-microservices/crawler-service/scale_crawlers.sh ${REPLICAS}"
  echo "Verify deploy: curl -s http://localhost:8050/crawler/version"
fi
