# mcp-classification-produit-service

MCP server exposing HelloPro product classification capabilities as MCP tools. Allows Claude and other LLM clients to classify products into categories via the MCP protocol.

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP v2025-03-26 (JSON-RPC 2.0 over SSE + Streamable HTTP)
- **Backend communication:** HTTP (proxies to api-classification-service)
- **Dependencies:** None (pure Go stdlib)

## Build / Run

- **Port:** 8593
- **Docker build:** Multi-stage (builder → runtime Alpine)
- **Run:** `/bin/mcp-classification-produit` (binary, no arguments needed)
- **Health check:** `GET /health`

```bash
# Docker build (from repo root)
docker compose --profile mcp build mcp-classification-produit-service

# Local build
cd apps-microservices/mcp-classification-produit-service
go build ./cmd/server/
```

## Folder Structure

```
mcp-classification-produit-service/
├── cmd/server/main.go              # Entry point, HTTP client, MCP server setup
├── internal/
│   ├── config/config.go            # Environment-based configuration
│   ├── mcp/types.go                # MCP protocol types (JSON-RPC, tools, resources)
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── helpers.go              # Result helpers + HTTP doPost/doGet
│   │   ├── schema.go               # Tool descriptions and JSON input schemas
│   │   ├── classify.go             # classify_product + classify_products_batch handlers
│   │   └── cache.go                # list_cached_categories + get_cached_category handlers
│   └── transport/
│       ├── sse.go                  # SSE transport (GET /sse, POST /message)
│       └── streamable_http.go      # Streamable HTTP transport (POST /mcp)
├── Dockerfile                      # 2-stage build (builder → Alpine runtime)
└── go.mod
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `classify_product` | Classify a single product (name, description) into a category. `id_produit` is optional — auto-generated as `auto-<hex>` if absent. |
| `classify_products_batch` | Classify a batch of products (up to 1200). Per-item `id_produit` is optional — auto-generated per item when absent. |
| `list_cached_categories` | List all cached category summaries from Redis |
| `get_cached_category` | Get cached summary for a specific category |

## MCP Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/sse` | GET | Open SSE stream, receive message endpoint URL |
| `/message` | POST | Send JSON-RPC request (requires `sessionId` query param) |
| `/mcp` | POST | Streamable HTTP transport (stateless) |
| `/health` | GET | Liveness probe |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8593 | HTTP server port |
| `MCP_SERVICE_NAME` | mcp-classification-produit | Service name for MCP handshake |
| `MCP_SERVICE_VERSION` | 0.1.0 | Service version |
| `CLASSIFICATION_API_URL` | http://api-classification-service:8577 | Classification API base URL |

## Dependencies on Other Services

- **api-classification-service** (HTTP, via api-classification-lb nginx) — product classification
- **mcp-gateway-service** (HTTP :8592) — MCP gateway that aggregates this service

## Conventions

- HTTP client timeout set to 5 minutes to handle slow batch classifications
- Responses are passed through as-is from the classification API (no deserialization)
- category_id URL parameter is escaped with url.PathEscape()
- SSE streams have unlimited write timeout for long-running requests
