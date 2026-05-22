# apps-microservices/api-gateway-go/Dockerfile
# Build context: monorepo root.
#
# Multi-stage build:
#   1. `builder`  - golang:1.24.13-alpine compiles a static binary with
#                   BuildKit cache mounts for fast iterative rebuilds.
#   2. `runtime`  - gcr.io/distroless/static-debian12:nonroot (no shell,
#                   no package manager, UID/GID 65532). Smallest viable
#                   surface for a CGO-disabled Go binary.

# ---------- builder ----------
FROM golang:1.24.13-alpine AS builder

ENV CGO_ENABLED=0 \
    GOOS=linux \
    GOFLAGS=-trimpath

WORKDIR /src

# Dependency layer (cached as long as go.mod/go.sum are unchanged).
COPY apps-microservices/api-gateway-go/go.mod apps-microservices/api-gateway-go/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

# Source layer.
COPY apps-microservices/api-gateway-go/ ./

# Build with persistent module + build caches (BuildKit required).
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build \
        -ldflags="-s -w" \
        -o /out/gateway \
        ./cmd/gateway

# ---------- runtime ----------
FROM gcr.io/distroless/static-debian12:nonroot AS runtime

LABEL org.opencontainers.image.title="api-gateway-go" \
      org.opencontainers.image.source="https://github.com/Hellopro-fr/rag-hp-pub" \
      org.opencontainers.image.description="Go reverse-proxy gateway (JWT + API key) for the RAG-HP-PUB platform."

WORKDIR /app
COPY --from=builder /out/gateway /app/gateway

EXPOSE 8500
USER nonroot:nonroot
ENTRYPOINT ["/app/gateway"]
