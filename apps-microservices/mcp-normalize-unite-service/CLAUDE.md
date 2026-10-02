# mcp-normalize-unite-service

MCP server exposing HelloPro unit normalization as MCP tools. Lets Claude and other LLM clients convert a raw quantity or range (value + unit + characteristic label) into the canonical unit used by the Graph-RAG pipeline, by calling the `graph-rag-normalize-unite-service` gRPC backend (pint).

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP v2025-03-26 (JSON-RPC 2.0 over SSE + Streamable HTTP)
- **Backend communication:** gRPC (`protos/grpc_stubs/graph_normalization.proto`)
- **Dependencies:** google.golang.org/grpc, google.golang.org/protobuf (no other external deps)

## Build / Run

- **Port:** 8602 (compose `expose` only — reached by mcp-gateway-service over `services-net`)
- **Docker build:** Multi-stage (protogen → builder → runtime Alpine, non-root user, `HEALTHCHECK` on `/health`)
- **Run:** `/bin/mcp-normalize-unite` (binary, no arguments needed)

```bash
# Docker build (from repo root)
docker compose --profile mcp build mcp-normalize-unite-service

# Local build (requires protoc + protoc-gen-go + protoc-gen-go-grpc + go)
cd apps-microservices/mcp-normalize-unite-service
bash proto/generate.sh
go test ./... && go build ./cmd/server/
```

`proto/gen/` is generated and git-ignored. Without a local Go toolchain, run the tests in the Dockerfile's `protogen` stage: `docker build --target protogen -t mcpnu-protogen -f apps-microservices/mcp-normalize-unite-service/Dockerfile . && docker run --rm mcpnu-protogen sh -c 'go mod tidy && go test ./...'`.

## Folder Structure

```
mcp-normalize-unite-service/
├── cmd/server/main.go              # Entry point, gRPC connection, MCP server setup
├── internal/
│   ├── config/config.go            # Environment-based configuration
│   ├── mcp/types.go                # MCP protocol types (copied from mcp-api-recherche-service)
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── normalize.go            # normalize_quantity + normalize_range handlers, argument validation
│   │   └── normalize_test.go       # Unit tests against a fake gRPC client
│   └── transport/
│       ├── sse.go                  # SSE transport (GET /sse, POST /message, GET /health)
│       └── streamable_http.go      # Streamable HTTP transport (POST /mcp)
├── proto/
│   ├── gen/                        # Generated Go gRPC stubs (build time, git-ignored)
│   └── generate.sh                 # Proto generation script
├── Dockerfile
└── go.mod
```

## MCP Tools

| Tool | Arguments | Backend RPC |
|------|-----------|-------------|
| `normalize_quantity` | `label` (required), `value` (required, number or string), `unit`, `data_type` (`numeric` default, or `numeric_range`) | `NormalizeQuantity` |
| `normalize_range` | `label` (required), `min_value` and/or `max_value` (number or numeric string), `unit` | `NormalizeQuantity` once per bound, concurrently |

`normalize_range` deliberately does **not** call the `NormalizeRange` RPC: when one bound fails to convert, that RPC still answers `success=true` and proto3 reports the missing bound as `0.0`. Per-bound `NormalizeQuantity` calls run the same backend code path (`normalize_range` is two `normalize(..., "numeric")` calls) and let the tool name the failing bound.

A backend `success=false` is returned as an MCP tool error (`isError: true`) carrying the backend message plus the input label/value/unit.

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
| `MCP_PORT` | 8602 | HTTP server port |
| `MCP_SERVICE_NAME` | mcp-normalize-unite | Service name for MCP handshake |
| `MCP_SERVICE_VERSION` | 0.1.0 | Service version |
| `NORMALIZATION_SERVICE_URL` | graph-rag-normalize-unite-service:50057 | Normalization gRPC address |

## Dependencies on Other Services

- **graph-rag-normalize-unite-service** (gRPC :50057, compose profile `graph-rag`) — pint-based unit normalization
- **mcp-gateway-service** — aggregates this backend. Registration is runtime data, not code: add the server from the admin Servers page (or `POST /api/v1/servers`) with the **base** URL `http://mcp-normalize-unite-service:8602` — the gateway probes `<base>/mcp` itself (`internal/transport/http_backend.go`). The gateway needs `ALLOW_INTERNAL_URLS=true` to accept a Docker-internal URL.

## Conventions

- Backend contract, read from `graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py`: an empty `label`, or a `data_type` other than `numeric`/`numeric_range`, makes the backend fail — the tool validates both before calling and defaults `data_type` to `numeric`.
- Invalid arguments never reach the backend (asserted in `normalize_test.go`).
- The gRPC connection is persistent (established at startup); each call carries a 10 s deadline.
- Numbers are sent with `strconv.FormatFloat(f, 'f', -1, 64)` — never scientific notation.
