# mcp-normalize-unite-service

MCP server exposing HelloPro unit normalization as MCP tools. Lets Claude and other LLM clients convert a raw quantity or range (value + unit + characteristic label) into the canonical unit used by the Graph-RAG pipeline, by calling the `graph-rag-normalize-unite-service` gRPC backend (pint).

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP v2025-03-26 (JSON-RPC 2.0 over SSE + Streamable HTTP)
- **Backend communication:** gRPC (`protos/grpc_stubs/graph_normalization.proto` for normalization; `protos/grpc_stubs/unit_registry.proto` for unit-registry-service)
- **Dependencies:** google.golang.org/grpc, google.golang.org/protobuf (no other external deps)

## Build / Run

- **Port:** 8602 (compose `expose` only — reached by mcp-gateway-service over `services-net`)
- **Docker build:** Multi-stage (protogen, generates both stub packages → builder → runtime Alpine, non-root user, `HEALTHCHECK` on `/health`)
- **Run:** `/bin/mcp-normalize-unite` (binary, no arguments needed)

```bash
# Docker build (from repo root)
docker compose --profile mcp build mcp-normalize-unite-service

# Tests (from repo root; generates the stubs and runs go test in a container)
scripts/mcp-normalize-test.sh
```

`proto/gen/` is generated and git-ignored. Plain `scripts/mcp-normalize-test.sh` runs the default package list; passing only flags drops it, so pass packages too (`scripts/mcp-normalize-test.sh ./... -v`).

## Folder Structure

```
mcp-normalize-unite-service/
├── cmd/server/main.go              # Entry point, gRPC connection, MCP server setup
├── internal/
│   ├── config/config.go            # Environment-based configuration
│   ├── config/config_test.go       # UNIT_WRITE_TOOLS_ENABLED parsing
│   ├── mcp/types.go                # MCP protocol types (copied from mcp-api-recherche-service)
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── normalize.go            # normalize_quantity + normalize_range handlers, argument validation
│   │   ├── units.go                # create/update/deactivate/get_unit handlers + registry helpers
│   │   ├── unit_types.go           # create/update/deactivate/get_unit_type + set_dimension_types handlers
│   │   ├── normalize_test.go       # Unit tests against a fake gRPC client (+ tools/list per write mode)
│   │   ├── units_test.go           # Unit tool tests against a fake unit-registry client
│   │   └── unit_types_test.go      # Unit-type tool tests against the same fake
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

Up to 11 tools (4 when write tools are disabled, see below): `normalize_quantity`, `normalize_range`, `create_unit`, `update_unit`, `deactivate_unit`, `get_unit`, `create_unit_type`, `update_unit_type`, `deactivate_unit_type`, `get_unit_type`, `set_dimension_types`.

| Tool | Arguments | Backend RPC |
|------|-----------|-------------|
| `normalize_quantity` | `label` (required), `value` (required, number or string), `unit`, `data_type` (`numeric` default, or `numeric_range`) | `NormalizeQuantity` |
| `normalize_range` | `label` (required), `min_value` and/or `max_value` (number or numeric string), `unit` | `NormalizeQuantity` once per bound, concurrently |
| `create_unit` / `update_unit` / `deactivate_unit` / `get_unit` | see `units.go` | unit-registry `RegisterUnit` / `UpdateUnit` / `DeleteUnit` / `GetUnit` |
| `create_unit_type` | `code`, `label` (required), `description` | `CreateUnitType` |
| `update_unit_type` | `id` or `code`, `label` and/or `description` | `UpdateUnitType` (field mask) |
| `deactivate_unit_type` | `id` or `code` | `DeactivateUnitType` |
| `get_unit_type` | `id` or `code`; none = list active types | `GetUnitType` / `ListUnitTypes` |
| `set_dimension_types` | `dimension`, `type_codes` (required; `[]` clears) | `SetDimensionTypes` |

`normalize_range` deliberately does **not** call the `NormalizeRange` RPC: when one bound fails to convert, that RPC still answers `success=true` and proto3 reports the missing bound as `0.0`. Per-bound `NormalizeQuantity` calls run the same backend code path (`normalize_range` is two `normalize(..., "numeric")` calls) and let the tool name the failing bound.

**Write tools are opt-in.** `create_unit`, `update_unit`, `deactivate_unit`, `create_unit_type`, `update_unit_type`,
`deactivate_unit_type` and `set_dimension_types` are registered only when `UNIT_WRITE_TOOLS_ENABLED` is `true`/`1`/`yes`
(case-insensitive); otherwise `tools/list` shows 4 tools and a write call answers `unknown tool`. `main.go` logs the mode.

Unit-registry writes send `authorization: Bearer $UNITS_ADMIN_KEY` (and `created_by`/`updated_by` = `mcp:<service name>`); token/code lookups and reads are unauthenticated.

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
| `UNIT_REGISTRY_GRPC_ADDR` | unit-registry-service:50059 | unit-registry-service gRPC address |
| `UNITS_ADMIN_KEY` | (empty) | Bearer key for unit-registry writes; empty = writes rejected |
| `UNIT_WRITE_TOOLS_ENABLED` | false | `true`/`1`/`yes` registers the 7 unit/unit-type write tools; anything else = read-only (compose default `false`) |

## Dependencies on Other Services

- **graph-rag-normalize-unite-service** (gRPC :50057, compose profile `graph-rag`) — pint-based unit normalization
- **unit-registry-service** (gRPC :50059) — unit and unit-type CRUD
- **mcp-gateway-service** — aggregates this backend. Registration is runtime data, not code: add the server from the admin Servers page (or `POST /api/v1/servers`) with the **base** URL `http://mcp-normalize-unite-service:8602` — the gateway probes `<base>/mcp` itself (`internal/transport/http_backend.go`). The gateway needs `ALLOW_INTERNAL_URLS=true` to accept a Docker-internal URL.

## Conventions

- Backend contract, read from `graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py`: an empty `label`, or a `data_type` other than `numeric`/`numeric_range`, makes the backend fail — the tool validates both before calling and defaults `data_type` to `numeric`.
- Invalid arguments never reach the backend (asserted in `normalize_test.go`).
- The gRPC connection is persistent (established at startup); each call carries a 10 s deadline.
- Numbers are sent with `strconv.FormatFloat(f, 'f', -1, 64)` — never scientific notation.
