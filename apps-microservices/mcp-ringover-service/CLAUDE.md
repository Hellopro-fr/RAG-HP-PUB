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
│   ├── ringover/
│   │   ├── client.go               # HTTP client wrapping Ringover REST API
│   │   └── users.go                # Typed User/Team decoder + TeamsFromUsers aggregation
│   ├── tools/
│   │   ├── registry.go             # Tool registration and dispatch
│   │   ├── handler.go              # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── calls.go                # list_calls_by_date, search_calls, get_call_details tools
│   │   ├── scope.go                # User-scope helpers (effectiveUserIDs, ownership check)
│   │   ├── transcription.go        # get_call_transcription, get_call_summary, get_call_moments tools
│   │   ├── contacts.go             # list_contacts tool (deactivated)
│   │   └── users.go                # list_users tool + response filter under scope
│   └── transport/
│       ├── sse.go                  # SSE server (MCP transport layer)
│       ├── streamable_http.go      # Streamable HTTP transport
│       ├── scope.go                # Parses X-Ringover-Allowed-User-IDs into context
│       └── admin.go                # /admin/users and /admin/teams (X-Admin-Token)
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
| `/admin/users` | GET | Internal: list Ringover users (requires `X-Admin-Token`) |
| `/admin/teams` | GET | Internal: list Ringover teams derived from users (requires `X-Admin-Token`) |

## User-scope enforcement

The gateway may restrict a request to a subset of Ringover agents by setting
the `X-Ringover-Allowed-User-IDs` header with a comma-separated list of
numeric user IDs. When present:

- `list_calls_by_date` and `search_calls` switch from `GET /calls` to
  `POST /calls` with `filter: "ADVANCED"` and `advanced.users = [ids]` for
  true server-side filtering (Ringover's `GET /calls` has no user filter).
- `search_calls` additionally intersects any caller-supplied `user_id`
  argument with the allowed set — rejecting the call if the requested id is
  outside the scope.
- `get_call_details` verifies the response's `user_id` field is within the
  allowed set and returns an MCP error otherwise (`/calls/{id}` has no
  filter parameter; ownership is checked post-fetch).
- `list_users` (when registered) filters out users that are not in the
  allowed set.
- The Empower tools (`get_call_transcription`, `get_call_summary`,
  `get_call_moments`) apply the same post-fetch ownership check based on the
  response's `user_id` field. These tools are currently deactivated in
  `registry.go` (they require an Empower subscription), but the filter is
  wired and ready for re-activation.

Absent or empty header = unrestricted (preserves behaviour for direct,
non-gateway callers). A header parsed to zero valid IDs is treated as
"deny-all", not "unrestricted".

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8586 | HTTP server port |
| `MCP_SERVICE_NAME` | mcp-ringover | Service name for MCP handshake |
| `MCP_SERVICE_VERSION` | 0.1.0 | Service version |
| `RINGOVER_API_KEY` | — | Ringover API key (required) |
| `RINGOVER_API_BASE_URL` | `https://public-api.ringover.com/v2` | Ringover API base URL |
| `MCP_RINGOVER_ADMIN_TOKEN` | — | Shared secret enabling `/admin/*` endpoints. When empty the endpoints are disabled. |

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
