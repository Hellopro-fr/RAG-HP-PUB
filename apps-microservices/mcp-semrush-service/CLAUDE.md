# mcp-semrush-service

MCP server exposing Semrush SEO and competitive intelligence data as MCP tools over SSE and streamable HTTP.

## Tech Stack

- Node.js 20
- `server.js` (custom stdio MCP server for the Semrush API, Node stdlib only — no npm deps)
- `mcp-proxy` (Python, wraps stdio transport into SSE + streamable HTTP)
- Docker

## Run

```bash
docker compose --profile mcp build mcp-semrush-service
docker compose --profile mcp up mcp-semrush-service
```

## Architecture

`mcp-proxy` spawns `node /app/server.js` as a child process (stdio) and exposes it over HTTP on port 8588. `server.js` is a self-contained custom MCP server (Node `https`/`http`/`readline` stdlib only) calling the Semrush REST API directly — it does NOT wrap the `semrush-mcp` npm package. mcp-proxy exposes `/sse`, `/mcp`, and `/status` (no `/health`).

## Environment Variables

| Variable | Description |
|---|---|
| `SEMRUSH_API_KEY` | Semrush API key (requires active API subscription) |

Host-side (in `.env`):

| Variable | Description |
|---|---|
| `SEMRUSH_API_KEY` | Semrush API key |

## Prerequisites

1. Active Semrush account with API access (Standard API or Trends API subscription)
2. API key generated from Semrush dashboard

## MCP Tools Exposed

| Tool | Description |
|---|---|
| Domain analytics | Analyze domain traffic and rankings |
| Keyword research | Research keyword volume, difficulty, and opportunities |
| Backlink analysis | Analyze backlink profiles |
| Traffic insights | Get traffic estimates and sources |
| Competitive intelligence | Compare domains and market positioning |

## Endpoints

- `GET /sse` — SSE transport (streaming)
- `POST /mcp` — Streamable HTTP transport (stateless)

## Port

8588 (per docker-compose.yml and Dockerfile EXPOSE/CMD). MCP gateway=8581, recherche=8582, analytics=8583, gsc=8584.

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Semrush",
    "url": "http://mcp-semrush-service:8585",
    "tags": ["seo", "semrush", "analytics"],
    "tool_prefix": "semrush"
  }'
```
