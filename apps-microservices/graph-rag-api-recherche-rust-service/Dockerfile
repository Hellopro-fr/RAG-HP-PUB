# ========================================================================
# Build stage
# ========================================================================
FROM rust:1.88-slim AS builder

# Install protobuf compiler for tonic-build
RUN apt-get update && apt-get install -y protobuf-compiler libprotobuf-dev pkg-config curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy proto files (shared across Python and Rust)
COPY protos /protos

# Copy shared Rust gRPC clients library
COPY libs/rust-common-utils /app/libs/rust-common-utils

# Copy manifests first for dependency caching
COPY apps-microservices/graph-rag-api-recherche-rust-service/Cargo.toml ./service/Cargo.toml
COPY apps-microservices/graph-rag-api-recherche-rust-service/build.rs ./service/build.rs

# Patch the path dependency to match Docker layout
RUN sed -i 's|path = "../../libs/rust-common-utils"|path = "/app/libs/rust-common-utils"|' /app/service/Cargo.toml

WORKDIR /app/service

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
COPY --from=builder /app/service/target/release/graph-rag-api-recherche-rust-service /app/server

ENV RUST_LOG=info
ENV RUST_BACKTRACE=1

EXPOSE 8528

CMD ["/app/server"]
