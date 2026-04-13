# mcp-leexi-service

Custom MCP server exposing Leexi call transcription, search, and summary as MCP tools over SSE and streamable HTTP.

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP v2025-03-26 (JSON-RPC 2.0 over SSE + Streamable HTTP)
- **Backend communication:** Leexi public REST API (`https://public-api.leexi.ai/v1`)
- **Authentication:** HTTP Basic Auth (API Key ID + Key Secret, base64-encoded)
- **Dependencies:** Go stdlib only (no external deps)

## Build / Run

- **Port:** 8589
- **Docker build:** 2-stage (builder → runtime Alpine)
- **Run:** `/bin/mcp-leexi` (binary, no arguments needed)
- **Health check:** `GET /health`

```bash
# Docker build (from repo root)
docker compose --profile mcp build mcp-leexi-service
docker compose --profile mcp up mcp-leexi-service
```

## Folder Structure

```
mcp-leexi-service/
├── cmd/server/main.go              # Entry point, HTTP client setup, MCP server start
├── internal/
│   ├── config/config.go            # Environment-based configuration
│   ├── mcp/types.go                # MCP protocol types (JSON-RPC, tools)
│   ├── leexi/client.go             # HTTP client wrapping Leexi REST API (Basic Auth)
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   └── calls.go                # search_calls, get_call_transcript, get_call_summary tools
│   └── transport/
│       ├── sse.go                  # SSE server (MCP transport layer)
│       └── streamable_http.go      # Streamable HTTP transport
├── Dockerfile                      # 2-stage build
└── go.mod
```

## MCP Tools

| Tool | Leexi API Endpoint | Description |
|------|-------------------|-------------|
| `search_calls` | `GET /calls` | Search and list calls/meetings with optional date filters and pagination |
| `get_call_transcript` | `GET /calls/{uuid}` | Get the full transcript (word-level + paragraph-level timestamps) |
| `get_call_summary` | `GET /calls/{uuid}` | Get the AI-generated summary, chaptering, and key topics |

## MCP Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/sse` | GET | Open SSE stream, receive message endpoint URL |
| `/message` | POST | Send JSON-RPC request (requires `sessionId` query param) |
| `/mcp` | POST | Streamable HTTP transport (stateless) |
| `/health` | GET | Liveness probe |
| `/admin/users` | GET | Internal: list Leexi workspace users (requires `X-Admin-Token`) |
| `/admin/teams` | GET | Internal: list Leexi teams derived from users (requires `X-Admin-Token`) |

## Owner-scope enforcement

The gateway may restrict a request to a subset of Leexi users by setting the
`X-Leexi-Allowed-Owners` header with a comma-separated list of `owner_uuid`s.
When present:

- `search_calls` force-injects the allowed list as `owner_uuid[]` query params,
  or rejects the call if the user-supplied `owner_uuid` is not in the set.
- `get_call_transcript` and `get_call_summary` validate the call's owner
  against the allowed set and refuse with an MCP error if the owner is outside
  the scope.

When the header is absent (e.g. direct non-gateway callers), the service runs
unrestricted — preserving its historical behaviour.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8589 | HTTP server port |
| `MCP_SERVICE_NAME` | mcp-leexi | Service name for MCP handshake |
| `MCP_SERVICE_VERSION` | 0.1.0 | Service version |
| `LEEXI_API_KEY_ID` | — | Leexi API Key ID (required) |
| `LEEXI_API_KEY_SECRET` | — | Leexi API Key Secret (required) |
| `LEEXI_API_BASE_URL` | `https://public-api.leexi.ai/v1` | Leexi API base URL |
| `MCP_LEEXI_ADMIN_TOKEN` | — | Shared secret enabling `/admin/*` endpoints. When empty the endpoints are disabled. |

## Prerequisites

1. Leexi account with API access
2. API Key ID and Key Secret from Leexi settings

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Leexi",
    "url": "http://mcp-leexi-service:8589",
    "tags": ["telephony", "leexi", "transcription", "meetings"],
    "tool_prefix": "leexi"
  }'
```

## What This Provides to Other Services

- MCP-accessible call transcription and summary from Leexi AI notetaker.
- Searchable call/meeting index for AI agents.
