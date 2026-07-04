#!/bin/bash
# Build crawler-service with deploy identity baked in (served by GET /version).
# The docker-compose build args interpolate GIT_COMMIT/BUILD_DATE from the
# environment — this script computes them fresh so /version never lies.
#
# Usage:
#   ./tools/build_crawler.sh         # build only
#   ./tools/build_crawler.sh --up    # build + restart the service
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
docker compose --profile crawling build crawler-service

if [ "${1:-}" = "--up" ]; then
  docker compose --profile crawling up -d crawler-service
  echo "Restarted. Verify: curl -s http://localhost:8050/crawler/version"
fi
