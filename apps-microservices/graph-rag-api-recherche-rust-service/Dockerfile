# ========================================================================
# Build stage
# ========================================================================
FROM rust:1.88-slim AS builder

# Install protobuf compiler for tonic-build
RUN apt-get update && apt-get install -y protobuf-compiler libprotobuf-dev pkg-config curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy manifests first for dependency caching
COPY apps-microservices/graph-rag-api-recherche-rust-service/Cargo.toml ./
COPY apps-microservices/graph-rag-api-recherche-rust-service/build.rs ./

# Copy proto files
COPY protos /protos

# Create a dummy main.rs for dependency caching
RUN mkdir -p src && echo "fn main() {}" > src/main.rs

# Cache dependencies (allow failure for first build)
RUN cargo build --release 2>/dev/null || true

# Copy actual source code
COPY apps-microservices/graph-rag-api-recherche-rust-service/src/ src/

# Touch source files to invalidate the cached dummy binary
RUN touch src/main.rs

# Build the real application
RUN cargo build --release

# ========================================================================
# Runtime stage
# ========================================================================
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the compiled binary
COPY --from=builder /app/target/release/graph-rag-api-recherche-rust-service /app/server

ENV RUST_LOG=info
ENV RUST_BACKTRACE=1

EXPOSE 8527

CMD ["/app/server"]
