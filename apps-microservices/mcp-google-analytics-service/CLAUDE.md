# mcp-google-analytics-service

MCP server exposing Google Analytics 4 data (accounts, properties, reports) as MCP tools over SSE and streamable HTTP.

## Tech Stack

- Python 3.10
- `analytics-mcp` (Google's official GA4 MCP server, stdio-only)
- `mcp-proxy` (wraps stdio transport into SSE + streamable HTTP)
- Docker

## Run

```bash
# Build and start
docker compose --profile mcp build mcp-google-analytics-service
docker compose --profile mcp up mcp-google-analytics-service
```

## Architecture

`mcp-proxy` spawns `analytics-mcp` as a child process (stdio) and exposes it over HTTP on port 8583. No custom Python code — the entire service is the proxy wrapping the upstream package.

## Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON inside the container (set to `/secrets/gcp-credentials.json`) |
| `GOOGLE_PROJECT_ID` | GCP project ID with Analytics APIs enabled |

Host-side (in `.env`):

| Variable | Description |
|---|---|
| `GOOGLE_ANALYTICS_PROJECT_ID` | Maps to `GOOGLE_PROJECT_ID` inside the container |
| `GOOGLE_ANALYTICS_CREDENTIALS_PATH` | Host path to service account JSON (default: `./secrets/gcp-analytics-credentials.json`) |

## Prerequisites

1. GCP project with **Google Analytics Admin API** and **Google Analytics Data API** enabled
2. Service account with `analytics.readonly` scope and read access to target GA4 properties
3. Service account JSON key file placed on the host

## MCP Tools Exposed

| Tool | Description |
|---|---|
| `get_account_summaries` | Lists GA accounts and properties the service account can access |
| `get_property_details` | Returns details about a specific GA4 property |
| `list_google_ads_links` | Lists Google Ads links for a property |
| `run_report` | Runs a standard GA4 report (dimensions, metrics, date ranges) |
| `run_realtime_report` | Runs a realtime GA4 report |
| `get_custom_dimensions_and_metrics` | Lists custom dimensions and metrics for a property |

## Endpoints

- `GET /sse` — SSE transport (streaming)
- `POST /mcp` — Streamable HTTP transport (stateless)

## Port

8583 (follows MCP port sequence: gateway=8581, recherche=8582, analytics=8583)

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Google Analytics",
    "url": "http://mcp-google-analytics-service:8583",
    "tags": ["analytics", "google"],
    "tool_prefix": "ga"
  }'
```
