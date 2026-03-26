# rust-common-utils

Shared Rust library providing gRPC client wrappers for Rust-based microservices.

## Tech Stack

- Rust 2021 edition
- tonic 0.12 / prost 0.13 (gRPC + protobuf)
- serde / serde_json (serialization)
- tracing (logging)
- tonic-build 0.12 (build-time proto compilation)

## Build

```bash
cargo build
```

Proto files are compiled at build time via `build.rs`. It looks for protos in `/protos` (Docker) or `../../protos` (local dev).

## Folder Structure

```
src/
  lib.rs                  # Crate root, re-exports grpc_clients
  grpc_clients/
    mod.rs                # Module declarations + proto includes
    embedding.rs          # EmbeddingService client
    graph_database.rs     # GraphDatabaseService client
    graph_milvus.rs       # GraphMilvusService client
    graph_normalization.rs # GraphNormalizationService client
    llm.rs                # LLMService client
    reranking.rs          # RerankingService client
    spacy.rs              # SpacyService client
build.rs                  # tonic-build proto compilation (client-only)
```

## Conventions

- Client-only builds: `build_server(false)`, `build_client(true)`.
- Generated proto types live under `grpc_clients::proto::{service_name}`.
- One file per gRPC service client.

## What This Provides to Other Services

- Type-safe Rust gRPC clients for all RAG pipeline services (embedding, LLM, reranking, spacy, graph operations).
- Auto-generated message types from the shared `protos/` definitions.
