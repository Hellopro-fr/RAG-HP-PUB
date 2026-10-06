#!/usr/bin/env bash
# Generate Go stubs and run vet + tests for mcp-normalize-unite-service in a persistent container.
# The service is copied to /work inside the container, so go.sum and proto/gen never land in the repo.
# Usage: scripts/mcp-normalize-test.sh [go test args, default ./...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME=mcp-normalize-go-test

mounted="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/repo"}}{{.Source}}{{end}}{{end}}' "$NAME" 2>/dev/null || true)"
running="$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)"
if [ "$mounted" != "$ROOT" ] || [ "$running" != "true" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -v "$ROOT:/repo:ro" \
    -v mcp-normalize-gomod:/go/pkg/mod -v mcp-normalize-gocache:/root/.cache/go-build \
    golang:1.24-alpine sleep infinity >/dev/null
  docker exec "$NAME" sh -c 'apk add --no-cache bash protobuf protobuf-dev >/dev/null \
    && go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.6 \
    && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1'
fi

docker exec "$NAME" sh -c "rm -rf /work && cp -r /repo/apps-microservices/mcp-normalize-unite-service /work \
  && cd /work && PROTO_DIR=/repo/protos/grpc_stubs bash proto/generate.sh >/dev/null \
  && go mod tidy && go vet ./... && go test ${*:-./...}"
