# mcp-ringover-service

Custom MCP server exposing Ringover telephony data (calls, transcriptions, contacts) as MCP tools over SSE and streamable HTTP.

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP v2025-03-26 (JSON-RPC 2.0 over SSE + Streamable HTTP)
- **Backend communication:** Ringover public REST API (`https://public-api.ringover.com/v2`)
- **Dependencies:** Go stdlib only (no external deps)

## Build / Run

- **Port:** 8586
- **Docker build:** 2-stage (builder → runtime Alpine)
- **Run:** `/bin/mcp-ringover` (binary, no arguments needed)
- **Health check:** `GET /health`

```bash
# Docker build (from repo root)
docker compose --profile mcp build mcp-ringover-service
docker compose --profile mcp up mcp-ringover-service
```

## Folder Structure

```
mcp-ringover-service/
├── cmd/server/main.go              # Entry point, HTTP client setup, MCP server start
├── internal/
│   ├── config/config.go            # Environment-based configuration
│   ├── mcp/types.go                # MCP protocol types (JSON-RPC, tools)
│   ├── ringover/client.go          # HTTP client wrapping Ringover REST API
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── calls.go                # get_calls, get_call_details tools
│   │   ├── transcription.go        # get_call_transcription, get_call_summary, get_call_moments tools
│   │   ├── contacts.go             # list_contacts tool
│   │   └── users.go                # list_users tool
│   └── transport/
│       ├── sse.go                  # SSE server (MCP transport layer)
│       └── streamable_http.go      # Streamable HTTP transport
├── Dockerfile                      # 2-stage build
└── go.mod
```

## MCP Tools

| Tool | Ringover API Endpoint | Description |
|------|----------------------|-------------|
| `get_calls` | `GET /calls` | List recent calls with optional limit |
| `get_call_details` | `GET /calls/{callId}` | Get details for a specific call |
| `get_call_transcription` | `GET /public/empower/call/{calluuid}` | Get call transcription |
| `get_call_summary` | `GET /public/empower/call/{calluuid}/summary` | Get AI-generated call summary |
| `get_call_moments` | `GET /public/empower/call/{calluuid}/moments` | Get key moments from a call |
| `list_contacts` | `GET /contacts` | List all contacts |
| `list_users` | `GET /users` | List all Ringover users |

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
| `MCP_PORT` | 8586 | HTTP server port |
| `MCP_SERVICE_NAME` | mcp-ringover | Service name for MCP handshake |
| `MCP_SERVICE_VERSION` | 0.1.0 | Service version |
| `RINGOVER_API_KEY` | — | Ringover API key (required) |
| `RINGOVER_API_BASE_URL` | `https://public-api.ringover.com/v2` | Ringover API base URL |

## Prerequisites

1. Ringover account with API access
2. API key generated from Ringover Dashboard > Developer > API key

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ringover",
    "url": "http://mcp-ringover-service:8586",
    "tags": ["telephony", "ringover", "calls"],
    "tool_prefix": "ringover"
  }'
```
