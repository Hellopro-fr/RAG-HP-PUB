# protos

Single source of truth for all Protocol Buffer service definitions used across the RAG pipeline.

## Tech Stack

- Protocol Buffers (proto3)
- Consumed by: Python (grpcio-tools), Rust (tonic-build)

## Folder Structure

```
grpc_stubs/
  database.proto             # Database CRUD service
  embedding.proto            # EmbeddingService: GetEmbeddings, Tokenize, Detokenize, ChunkText
  graph_database.proto       # Graph database operations
  graph_milvus.proto         # Graph-specific Milvus operations
  graph_normalization.proto  # Graph entity normalization
  llm.proto                  # LLMService: Chat, ChatStream, ChatBatch
  reranking.proto            # RerankingService: Rerank, RerankDocuments (with scores)
  spacy.proto                # SpaCy NLP service
```

## Conventions

- All protos use `syntax = "proto3"`.
- Package name matches the filename (e.g., `package embedding;`).
- Batch/plural RPCs use `repeated` fields (not streaming) for simplicity.
- Streaming is used only for `LLMService.ChatStream` (bidirectional).
- Optional fields use the `optional` keyword (proto3 field presence).
- Proto directory is mounted at `/protos` in Docker containers.

## Code Generation

- **Python:** Generated stubs are packaged in `libs/grpc-stubs/`.
- **Rust:** Compiled at build time by `libs/rust-common-utils/build.rs` via tonic-build.

## What This Provides to Other Services

- Canonical interface contracts for all gRPC inter-service communication.
- Both Python and Rust services derive their types and clients from these definitions.
