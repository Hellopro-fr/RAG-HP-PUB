# Agent Task Board backend (atb-server). Build context: this directory.
# SQLX_OFFLINE uses the committed .sqlx query cache: no database at build time.

# ---------- build ----------
FROM rust:1.96-slim-bookworm AS builder
WORKDIR /app
ENV SQLX_OFFLINE=true CARGO_TERM_COLOR=never

# Dependency layer: manifests + empty sources, cached until Cargo.toml / Cargo.lock change.
COPY Cargo.toml Cargo.lock ./
COPY crates/core/Cargo.toml crates/core/Cargo.toml
COPY crates/server/Cargo.toml crates/server/Cargo.toml
RUN mkdir -p crates/core/src crates/server/src \
 && touch crates/core/src/lib.rs crates/server/src/lib.rs \
 && echo 'fn main() {}' > crates/server/src/main.rs \
 && cargo build --release -p atb-server --bin atb-server \
 && rm -rf crates/core/src crates/server/src

COPY .sqlx .sqlx
COPY migrations migrations
COPY crates crates
RUN touch crates/core/src/lib.rs crates/server/src/lib.rs crates/server/src/main.rs \
 && cargo build --release -p atb-server --bin atb-server

# ---------- runtime ----------
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home atb
COPY --from=builder /app/target/release/atb-server /usr/local/bin/atb-server
USER atb
ENV RUST_LOG=info BIND_ADDR=0.0.0.0:8621
EXPOSE 8621
ENTRYPOINT ["atb-server"]
CMD ["serve"]
