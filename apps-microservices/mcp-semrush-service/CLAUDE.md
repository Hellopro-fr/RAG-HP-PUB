# mcp-semrush-service

MCP server exposing Semrush SEO and competitive intelligence data as MCP tools over SSE and streamable HTTP.

## Tech Stack

- Node.js 20
- `server.js` — custom MCP server for the Semrush API, stdio-only, no npm dependencies
- `mcp-proxy` (Python, wraps stdio transport into SSE + streamable HTTP)
- Docker

## Run

```bash
docker compose --profile mcp build mcp-semrush-service
docker compose --profile mcp up mcp-semrush-service
```

## Architecture

`mcp-proxy` spawns `node /app/server.js` as a child process (stdio) and exposes it over HTTP on port 8588.

`server.js` is a hand-written JSON-RPC/stdio MCP server (zero npm dependencies; run `wc -l server.js` for the current line count). It replaced the community `semrush-mcp` package, which sent malformed requests: it omitted the required `target_type` parameter on backlink reports and used wrong base URLs for the Trends and balance endpoints (`server.js:4-8`).

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

23 tools. The 14 domain and keyword tools are hand-written in the `TOOLS` array; the 9
backlink tools are generated from the `BACKLINK_REPORTS` table.

| Category | Tools |
|---|---|
| Domain analytics | `domain_overview`, `domain_organic_keywords`, `domain_paid_keywords`, `competitors` |
| Keyword research | `keyword_overview`, `keyword_overview_single_db`, `batch_keyword_overview`, `keyword_organic_results`, `keyword_paid_results`, `keyword_ads_history`, `related_keywords`, `broad_match_keywords`, `phrase_questions`, `keyword_difficulty` |
| Backlinks | `backlinks`, `backlinks_domains`, `backlinks_overview`, `backlinks_anchors`, `backlinks_pages`, `backlinks_competitors`, `backlinks_geo`, `backlinks_tld`, `backlinks_matrix` — see [BACKLINKS.md](./BACKLINKS.md) |

**Disabled** (commented out in `server.js`, do not assume available): `traffic_summary` and `traffic_sources` require a separate Semrush Trends API subscription (`ERROR 130 :: API DISABLED`); `api_units_balance` was dropped as out of scope.

### Backlinks — cost warning

All 9 backlink tools bill **40 Semrush API units per returned line** (except
`backlinks_overview`, billed per request) and require a **Business plan**. `display_limit`
defaults to 10 and is clamped to 100 rows (4,000 units) by `MAX_DISPLAY_LIMIT` — Semrush's
own default is 10,000, which would cost 400,000 units per call. Read
[BACKLINKS.md](./BACKLINKS.md) before changing it.

## Tests

`npm test` runs `node --test` against `server.test.js`. No test makes a live Semrush call.
The test file is not copied into the Docker image.

## Endpoints

- `GET /sse` — SSE transport (streaming)
- `POST /mcp` — Streamable HTTP transport (stateless)

## Port

8588 (per `Dockerfile` `EXPOSE`/`CMD`). MCP port sequence: gateway=8581, recherche=8582, analytics=8583, gsc=8584.

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Semrush",
    "url": "http://mcp-semrush-service:8588",
    "tags": ["seo", "semrush", "analytics"],
    "tool_prefix": "semrush"
  }'
```
