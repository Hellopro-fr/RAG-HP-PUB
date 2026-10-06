#!/usr/bin/env bash
# Run pytest for libs/unit-registry, unit-registry-service or graph-rag-normalize-unite-service
# inside a persistent container (the image is built once, the container is reused).
# Usage: scripts/unit-registry-test.sh <repo-relative-dir> [pytest args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE=unit-registry-test:py310
NAME=unit-registry-test

if [ "${REBUILD:-0}" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" -f "$ROOT/libs/unit-registry/test.Dockerfile" "$ROOT/libs/unit-registry"
fi

mounted="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/repo"}}{{.Source}}{{end}}{{end}}' "$NAME" 2>/dev/null || true)"
running="$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)"
if [ "$mounted" != "$ROOT" ] || [ "$running" != "true" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -v "$ROOT:/repo" -w /repo \
    -e PYTHONPATH=/stubs:/repo/libs/unit-registry/src:/repo/libs/common-utils/src \
    -e PYTHONDONTWRITEBYTECODE=1 \
    "$IMAGE" sleep infinity >/dev/null
fi

# Python gRPC stubs are generated outside the bind mount so the repo stays clean.
docker exec "$NAME" sh -c 'rm -rf /stubs && mkdir -p /stubs \
  && python -m grpc_tools.protoc -I/repo/protos --python_out=/stubs --grpc_python_out=/stubs /repo/protos/grpc_stubs/*.proto \
  && touch /stubs/grpc_stubs/__init__.py'

dir="$1"; shift
docker exec -w "/repo/$dir" "$NAME" python -m pytest -p no:cacheprovider "$@"
