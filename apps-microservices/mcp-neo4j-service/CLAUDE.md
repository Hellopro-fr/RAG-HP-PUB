# mcp-neo4j-service

MCP server exposing Neo4j graph database operations as MCP tools over SSE and streamable HTTP.

## Tech Stack

- Python 3.10
- `mcp-neo4j-cypher` (Neo4j Labs official MCP server, stdio-only)
- `mcp-proxy` (wraps stdio transport into SSE + streamable HTTP)
- Docker

## Run

```bash
docker compose --profile mcp build mcp-neo4j-service
docker compose --profile mcp up mcp-neo4j-service
```

## Architecture

`mcp-proxy` spawns `mcp-neo4j-cypher` as a child process (stdio) and exposes it over HTTP on port 8587. No custom Python code — the entire service is the proxy wrapping the upstream package.

## Environment Variables

| Variable | Description |
|---|---|
| `NEO4J_URI` | Neo4j connection URI (e.g., `bolt://neo4j:7687`) |
| `NEO4J_USERNAME` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `NEO4J_DATABASE` | Neo4j database name (default: `neo4j`) |

Host-side (in `.env`):

| Variable | Description |
|---|---|
| `NEO4J_MCP_URI` | Maps to `NEO4J_URI` inside the container |
| `NEO4J_MCP_USERNAME` | Maps to `NEO4J_USERNAME` inside the container |
| `NEO4J_MCP_PASSWORD` | Maps to `NEO4J_PASSWORD` inside the container |
| `NEO4J_MCP_DATABASE` | Maps to `NEO4J_DATABASE` inside the container |

## MCP Tools Exposed

| Tool | Description |
|---|---|
| `read_neo4j_cypher` | Execute read-only Cypher queries |
| `write_neo4j_cypher` | Execute write Cypher queries |
| `get_neo4j_schema` | Get graph schema (node labels, relationship types, properties) |

## Endpoints

- `GET /sse` — SSE transport (streaming)
- `POST /mcp` — Streamable HTTP transport (stateless)

## Port

8587 (follows MCP port sequence: gateway=8581, recherche=8582, analytics=8583, gsc=8584, semrush=8585, ringover=8586, neo4j=8587)

## Optional: Gateway Registration

```bash
curl -X POST http://localhost:8581/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Neo4j",
    "url": "http://mcp-neo4j-service:8587",
    "tags": ["database", "neo4j", "graph"],
    "tool_prefix": "neo4j"
  }'
```
