# syntax=docker/dockerfile:1.7

# Stage 1: Build
FROM golang:1.24-alpine AS builder
WORKDIR /src

RUN apk add --no-cache git

# Download dependencies first — this layer is cached until go.mod / go.sum change,
# regardless of source edits.
COPY apps-microservices/mcp-gateway-service/go.mod apps-microservices/mcp-gateway-service/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

# Copy the rest of the source.
COPY apps-microservices/mcp-gateway-service/ .

# Build with module + compile caches mounted so subsequent builds reuse
# already-compiled packages even when the source layer is invalidated.
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build -o mcp-gateway ./cmd/server/

# Stage 2: Minimal runtime image
FROM alpine:3.20
# su-exec lets the entrypoint drop privileges from root → appuser AFTER
# fixing the mounted volume's ownership.
RUN apk add --no-cache ca-certificates wget su-exec && \
    adduser -D -u 1000 appuser

WORKDIR /app
COPY --from=builder /src/mcp-gateway .
COPY apps-microservices/mcp-gateway-service/entrypoint.sh /entrypoint.sh
RUN mkdir -p /data/uploads/icons /data/uploads/images && \
    chown -R appuser:appuser ./mcp-gateway /data/uploads && \
    chmod +x /entrypoint.sh

# NOTE: container starts as root so the entrypoint can chown the mounted
# /data/uploads volume; it then drops to appuser via su-exec.
EXPOSE 8592

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:8592/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
