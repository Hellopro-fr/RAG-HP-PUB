# Stage 1: Build
FROM golang:1.24-alpine AS builder
WORKDIR /src

RUN apk add --no-cache git

COPY apps-microservices/mcp-gateway-service/ .
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -o mcp-gateway ./cmd/server/

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
