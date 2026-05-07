# apps-microservices/api-gateway-go/Dockerfile
# Build context: monorepo root.

FROM golang:1.24-alpine AS builder
WORKDIR /src

COPY apps-microservices/api-gateway-go/go.mod apps-microservices/api-gateway-go/go.sum ./
RUN go mod download

COPY apps-microservices/api-gateway-go/ ./
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/gateway \
    ./cmd/gateway

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /
COPY --from=builder /out/gateway /gateway
EXPOSE 8500
USER nonroot:nonroot
ENTRYPOINT ["/gateway"]
