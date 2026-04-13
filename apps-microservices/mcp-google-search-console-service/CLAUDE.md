# mcp-google-search-console-service

MCP server exposing Google Search Console data as MCP tools over SSE and streamable HTTP.

## Tech Stack

- Python 3.10
- `mcp-gsc` (community MCP server for Google Search Console, stdio-only)
- `mcp-proxy` (wraps stdio transport into SSE + streamable HTTP)
- Docker

## Run

```bash
docker compose --profile mcp build mcp-google-search-console-service
docker compose --profile mcp up mcp-google-search-console-service
```

## Architecture

`mcp-proxy` spawns `mcp-gsc` as a child process (stdio) and exposes it over HTTP on port 8584. No custom Python code — the entire service is the proxy wrapping the upstream package.

## Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REFRESH_TOKEN` | Google OAuth refresh token |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON inside the container |
| `GSC_SITE_URL` | Search Console property URL (e.g., `https://www.hellopro.fr`) |
| `GSC_SKIP_OAUTH` | Set to `true` to use service account instead of OAuth |

Host-side (in `.env`):

| Variable | Description |
|---|---|
| `GSC_GOOGLE_CLIENT_ID` | Maps to `GOOGLE_CLIENT_ID` |
| `GSC_GOOGLE_CLIENT_SECRET` | Maps to `GOOGLE_CLIENT_SECRET` |
| `GSC_GOOGLE_REFRESH_TOKEN` | Maps to `GOOGLE_REFRESH_TOKEN` |
| `GSC_CREDENTIALS_PATH` | Host path to service account JSON |
| `GSC_SITE_URL` | Search Console property URL |

## Prerequisites

1. Google Cloud project with **Search Console API** enabled
2. OAuth credentials or service account with Search Console access
3. Credentials file placed on the host

## MCP Tools Exposed

| Tool | Description |
|---|---|
| `get_search_analytics` | Retrieve search analytics data (up to 25,000 rows) |
| `inspect_url` | Inspect a URL in Search Console |
| `list_sitemaps` | List sitemaps for a property |
| `get_property_info` | Get property information |
| `get_quick_wins` | Detect quick-win SEO opportunities |

## Endpoints

- `GET /sse` — SSE transport (streaming)
- `POST /mcp` — Streamable HTTP transport (stateless)

## Port

8584 (follows MCP port sequence: gateway=8581, recherche=8582, analytics=8583, gsc=8584)

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Google Search Console",
    "url": "http://mcp-google-search-console-service:8584",
    "tags": ["seo", "google", "search-console"],
    "tool_prefix": "gsc"
  }'
```
