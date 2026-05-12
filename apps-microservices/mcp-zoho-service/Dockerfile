# syntax=docker/dockerfile:1
FROM golang:1.24-alpine AS builder
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/mcp-zoho-service ./cmd/server

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget && adduser -D -u 10001 zoho
USER zoho
COPY --from=builder /out/mcp-zoho-service /usr/local/bin/mcp-zoho-service
EXPOSE 8596
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8596/health || exit 1
ENTRYPOINT ["/usr/local/bin/mcp-zoho-service"]
