# mcp-api-recherche-service

MCP (Model Context Protocol) server exposing HelloPro search capabilities as MCP tools. Allows Claude and other LLM clients to query product catalogs, websites, quotes, exchanges, and pricing databases via the MCP protocol.

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP v2024-11-05 (JSON-RPC 2.0 over SSE)
- **Backend communication:** gRPC (protobuf)
- **Dependencies:** google.golang.org/grpc, google.golang.org/protobuf (no other external deps)

## Build / Run

- **Port:** 8580
- **Docker build:** Multi-stage (protogen → builder → runtime Alpine)
- **Run:** `/bin/mcp-api-recherche` (binary, no arguments needed)
- **Health check:** `GET /health`

```bash
# Docker build (from repo root)
docker build -f apps-microservices/mcp-api-recherche-service/Dockerfile -t mcp-api-recherche .

# Local build (requires protoc + go)
cd apps-microservices/mcp-api-recherche-service
bash proto/generate.sh
go build ./cmd/server/
```

## Folder Structure

```
mcp-api-recherche-service/
├── cmd/server/main.go              # Entry point, gRPC connections, MCP server setup
├── internal/
│   ├── config/config.go            # Environment-based configuration
│   ├── mcp/types.go                # MCP protocol types (JSON-RPC, tools, resources)
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── search.go               # search tool — full pipeline orchestration
│   │   ├── schema.go               # get_collection_schema tool
│   │   ├── rerank.go               # rerank tool
│   │   ├── embed.go                # embed_text tool
│   │   └── llm_chat.go             # llm_chat tool
│   ├── orchestrator/
│   │   ├── search.go               # Search pipeline (embed → search → rerank)
│   │   └── filter.go               # Milvus filter expression builder
│   └── transport/
│       └── sse.go                  # SSE server (MCP transport layer)
├── proto/
│   ├── gen/                        # Generated Go gRPC stubs (created at build time)
│   └── generate.sh                 # Proto generation script
├── Dockerfile                      # Multi-stage build
└── go.mod
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `search` | Full search pipeline: embedding → vector/hybrid/keyword search → reranking |
| `get_collection_schema` | Retrieve Milvus collection field names and types |
| `rerank` | Re-rank documents by relevance using cross-encoder model |
| `embed_text` | Generate CamemBERT-large embeddings (1024-dim vectors) |
| `llm_chat` | Send prompts to internal vLLM service |

## MCP Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/sse` | GET | Open SSE stream, receive message endpoint URL |
| `/message` | POST | Send JSON-RPC request (requires `sessionId` query param) |
| `/health` | GET | Liveness probe |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8580 | HTTP server port |
| `MCP_SERVICE_NAME` | mcp-api-recherche | Service name for MCP handshake |
| `MCP_SERVICE_VERSION` | 0.1.0 | Service version |
| `EMBEDDING_SERVICE_URL` | embedding-model-service:50052 | Embedding gRPC address |
| `DATABASE_SERVICE_URL` | database-recherche-service:50054 | Database gRPC address |
| `RERANKING_SERVICE_URL` | reranking-model-service:50053 | Reranking gRPC address |
| `LLM_SERVICE_URL` | llm-service:50051 | LLM gRPC address |

## Dependencies on Other Services

- **embedding-model-service** (gRPC :50052) — CamemBERT-large embeddings
- **database-recherche-service** (gRPC :50054) — Milvus vector/hybrid/keyword search
- **reranking-model-service** (gRPC :50053) — BAAI/bge-reranker-v2-m3 cross-encoder
- **llm-service** (gRPC :50051) — vLLM chat completion
- **mcp-gateway-service** (HTTP :8560) — MCP gateway that aggregates this service

## Conventions

- gRPC connections are persistent (established at startup, not per-request)
- Schema cache with 1-hour TTL to avoid repeated gRPC calls
- Filter expression builder ported from Python `api-recherche` service
- Parallel source search via goroutines
- Graceful degradation: reranking errors fall back to original order
