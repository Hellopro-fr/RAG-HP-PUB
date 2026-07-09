# ── Stage 1: Generate Go gRPC stubs ──────────────────────────────────────────
FROM golang:1.26-alpine AS protogen

RUN apk add --no-cache protobuf protobuf-dev
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
RUN go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

WORKDIR /build

# Copy proto definitions
COPY protos/grpc_stubs/ /protos/grpc_stubs/

# Copy service source
COPY apps-microservices/mcp-api-recherche-service/ /build/

# Module path base for generated Go packages
ENV MOD=github.com/hellopro/mcp-api-recherche/proto/gen

# Generate Go stubs into package-specific subdirectories.
RUN mkdir -p /build/proto/gen/embedding \
             /build/proto/gen/database \
             /build/proto/gen/reranking \
             /build/proto/gen/llm && \
    # Embedding
    protoc --proto_path=/protos/grpc_stubs \
        --go_out=/build/proto/gen/embedding --go_opt=paths=source_relative \
        --go_opt=Membedding.proto=${MOD}/embedding \
        --go-grpc_out=/build/proto/gen/embedding --go-grpc_opt=paths=source_relative \
        --go-grpc_opt=Membedding.proto=${MOD}/embedding \
        /protos/grpc_stubs/embedding.proto && \
    # Database
    protoc --proto_path=/protos/grpc_stubs \
        --go_out=/build/proto/gen/database --go_opt=paths=source_relative \
        --go_opt=Mdatabase.proto=${MOD}/database \
        --go-grpc_out=/build/proto/gen/database --go-grpc_opt=paths=source_relative \
        --go-grpc_opt=Mdatabase.proto=${MOD}/database \
        /protos/grpc_stubs/database.proto && \
    # Reranking
    protoc --proto_path=/protos/grpc_stubs \
        --go_out=/build/proto/gen/reranking --go_opt=paths=source_relative \
        --go_opt=Mreranking.proto=${MOD}/reranking \
        --go-grpc_out=/build/proto/gen/reranking --go-grpc_opt=paths=source_relative \
        --go-grpc_opt=Mreranking.proto=${MOD}/reranking \
        /protos/grpc_stubs/reranking.proto && \
    # LLM
    protoc --proto_path=/protos/grpc_stubs \
        --go_out=/build/proto/gen/llm --go_opt=paths=source_relative \
        --go_opt=Mllm.proto=${MOD}/llm \
        --go-grpc_out=/build/proto/gen/llm --go-grpc_opt=paths=source_relative \
        --go-grpc_opt=Mllm.proto=${MOD}/llm \
        /protos/grpc_stubs/llm.proto

# ── Stage 2: Build Go binary ─────────────────────────────────────────────────
FROM golang:1.26-alpine AS builder

WORKDIR /build
COPY --from=protogen /build/ /build/

# Bump deps CVE (Trivy) : x/net 0.40->0.55 (XSS/DoS/idna HIGH), grpc 1.72->1.79 (authz bypass CRITICAL).
# Fait au build (pas de Go/Docker local dispo) ; `go mod tidy` en dessous reconcilie go.sum.
# NB : go.mod/go.sum SOURCE restent a l'ancienne version -> a reconcilier au rapatriement poc (Go requis).
RUN go get golang.org/x/net@v0.55.0 google.golang.org/grpc@v1.79.3
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mcp-api-recherche ./cmd/server/

# ── Stage 3: Minimal runtime ─────────────────────────────────────────────────
FROM alpine:3.20

RUN apk add --no-cache ca-certificates
COPY --from=builder /bin/mcp-api-recherche /bin/mcp-api-recherche

EXPOSE 8580

ENTRYPOINT ["/bin/mcp-api-recherche"]
