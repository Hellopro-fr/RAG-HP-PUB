#!/bin/bash
# Generate Go gRPC stubs from proto definitions.
# Run from the service root directory.
# Requires: protoc, protoc-gen-go, protoc-gen-go-grpc

set -euo pipefail

PROTO_DIR="${PROTO_DIR:-../../protos/grpc_stubs}"
OUT_DIR="./proto/gen"
MOD="github.com/hellopro/mcp-api-recherche/proto/gen"

declare -A PROTOS=(
  [embedding]="embedding.proto"
  [database]="database.proto"
  [reranking]="reranking.proto"
  [llm]="llm.proto"
)

for pkg in "${!PROTOS[@]}"; do
  proto="${PROTOS[$pkg]}"
  mkdir -p "$OUT_DIR/$pkg"
  echo "Generating Go stubs for $proto -> $OUT_DIR/$pkg/"
  protoc \
    --proto_path="$PROTO_DIR" \
    --go_out="$OUT_DIR/$pkg" \
    --go_opt=paths=source_relative \
    --go_opt="M${proto}=${MOD}/${pkg}" \
    --go-grpc_out="$OUT_DIR/$pkg" \
    --go-grpc_opt=paths=source_relative \
    --go-grpc_opt="M${proto}=${MOD}/${pkg}" \
    "$PROTO_DIR/$proto"
done

echo "Proto generation complete."
