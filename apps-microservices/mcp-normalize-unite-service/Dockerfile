# ── Stage 1: Generate Go gRPC stubs ──────────────────────────────────────────
FROM golang:1.24-alpine AS protogen

RUN apk add --no-cache protobuf protobuf-dev
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.6
RUN go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1

WORKDIR /build

# Copy proto definitions
COPY protos/grpc_stubs/graph_normalization.proto /protos/grpc_stubs/

# Copy service source
COPY apps-microservices/mcp-normalize-unite-service/ /build/

# Module path base for generated Go packages
ENV MOD=github.com/hellopro/mcp-normalize-unite/proto/gen

RUN mkdir -p /build/proto/gen/graph_normalization && \
    protoc --proto_path=/protos/grpc_stubs \
        --go_out=/build/proto/gen/graph_normalization --go_opt=paths=source_relative \
        --go_opt=Mgraph_normalization.proto=${MOD}/graph_normalization \
        --go-grpc_out=/build/proto/gen/graph_normalization --go-grpc_opt=paths=source_relative \
        --go-grpc_opt=Mgraph_normalization.proto=${MOD}/graph_normalization \
        /protos/grpc_stubs/graph_normalization.proto

# ── Stage 2: Build Go binary ─────────────────────────────────────────────────
FROM golang:1.24-alpine AS builder

WORKDIR /build
COPY --from=protogen /build/ /build/

RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mcp-normalize-unite ./cmd/server/

# ── Stage 3: Minimal runtime ─────────────────────────────────────────────────
FROM alpine:3.20

RUN apk add --no-cache ca-certificates && adduser -D -H -u 10001 mcp
COPY --from=builder /bin/mcp-normalize-unite /bin/mcp-normalize-unite

USER mcp

EXPOSE 8602

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:${MCP_PORT:-8602}/health || exit 1

ENTRYPOINT ["/bin/mcp-normalize-unite"]
