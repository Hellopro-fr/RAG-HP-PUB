# mcp-hellodata-service

Custom MCP server exposing the BO's buyer-targeting engine (HelloData) as MCP
tools: filtered counting, paginated sampling, and CSV export of buyer
selections, over Streamable HTTP.

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP (JSON-RPC 2.0 over Streamable HTTP, single `/mcp` endpoint — no SSE)
- **Backend communication:** HelloData engine REST API on Ecritel (`/admin/mcp/hellodata`), Bearer token
- **Dependencies:** Go stdlib only (no external deps — `go.mod` declares none)

## Build / Run

- **Port:** 8597
- **Docker build:** 2-stage (builder → runtime Alpine, non-root user)
- **Run:** `/bin/mcp-hellodata` (binary, no arguments needed)
- **Health check:** `GET /health` — the only endpoint that answers without an identity; it carries no business data

```bash
# Docker build (from repo root)
docker compose --profile mcp build mcp-hellodata-service
docker compose --profile mcp up mcp-hellodata-service
```

## Folder Structure

```
mcp-hellodata-service/
├── cmd/server/main.go               # Entry point: wiring, HTTP mux, /health
├── internal/
│   ├── config/config.go             # Environment-based configuration (Charger)
│   ├── mcp/types.go                 # MCP protocol types (JSON-RPC, tools)
│   ├── hellodata/
│   │   ├── client.go                # HTTP client wrapping the HelloData engine (Bearer auth)
│   │   └── types.go                 # Engine request/response types
│   ├── acces/acces.go               # Authorization decision (admin role OR static allowlist)
│   ├── filtre/filtre.go             # Filter-tree validation/translation
│   ├── tools/
│   │   ├── registry.go              # Tool definitions (hellodata_compter, _echantillon, _export_csv)
│   │   ├── handler.go                # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── selection.go             # Tool implementations, calls into hellodata.Client
│   │   └── jetons.go                 # Download-token issuance/table for the CSV export flow
│   ├── download/proxy.go            # /download/ HTTP proxy that redeems a token for a CSV
│   └── transport/http.go            # /mcp Streamable HTTP handler, identity extraction from headers
├── Dockerfile                       # 2-stage build, non-root Alpine
└── go.mod
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `hellodata_compter` | Counts buyers matching a filter tree. Fast approximate mode (capped at 10000) by default; `exact=true` gives the real count but can take over a minute. |
| `hellodata_echantillon` | Reads buyers matching the filter, page by page (up to 2000 rows/call, 50 by default, cursor-based pagination). |
| `hellodata_export_csv` | Renders one page (≤2000 rows) of the selection as a CSV download URL. Link expires after 15 minutes and does not survive a service restart. |

There is no `hellodata_export_statut` tool: exports are single-page and
rendered directly by `hellodata_export_csv` — no async job to poll.

## MCP Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp` | POST | Streamable HTTP transport (stateless JSON-RPC) |
| `/download/{token}` | GET | Redeems a short-lived token issued by `hellodata_export_csv` for the CSV |
| `/health` | GET | Liveness probe — no identity required, no business data returned |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8597 | HTTP server port |
| `HELLODATA_BASE_URL` | — | Base URL of the HelloData engine (`/admin/mcp/hellodata` on Ecritel), required |
| `HELLODATA_TOKEN` | — | Bearer token presented to the engine, required |
| `HELLODATA_PUBLIC_URL` | — | Public base URL used to build the `/download` links returned to the LLM |
| `HELLODATA_ALLOWED_EMAILS` | — (empty) | Comma-separated addresses authorized in addition to `admin` role. Loaded once at startup, normalized (lowercased, trimmed). Empty/absent = only `admin` passes. Never set a real value in this repo or in `docker-compose.yml` — the repo is public; reference it as `${HELLODATA_ALLOWED_EMAILS}` only, set the real value in a local, untracked `.env`. |

## Accès

**L'autorisation se décide dans ce service, pas dans le gateway.** Le
gateway ne pose qu'une barrière de rôle minimale (`min_role = readonly`,
qui écarte les chemins sans identité — tokens de scope, grants
`client_credentials`) et injecte deux en-têtes non signés,
`X-End-User-Email` et `X-End-User-Role`, dérivés de l'identité
authentifiée. La décision nominative — qui a le droit d'appeler ce
service — est prise ici, dans `internal/acces`, à partir de ces en-têtes :
rôle `admin`, ou adresse présente dans `HELLODATA_ALLOWED_EMAILS`. Toute
absence d'identité (en-tête vide) refuse ; seul `/health` répond sans
identité, et il ne renvoie aucune donnée métier.

Cette décision n'a de sens que si le service n'est **joignable que depuis
le réseau Docker interne** — d'où `expose:` et jamais `ports:` dans
`docker-compose.yml` : si un tiers peut atteindre le port 8597
directement, il peut forger `X-End-User-Role: admin` et la liste
d'autorisés ne protège plus rien. La frontière réseau **est** la
garantie.

Raisonnement complet (pourquoi pas `server_authorizations` ni
`GateAllowsEmail` côté gateway, ce que le gateway injecte exactement, et
le caractère provisoire assumé de la liste statique) : voir le § 7.1 de
`docs/superpowers/specs/2026-09-21-mcp-hellodata-selection-design.md`.

## Prerequisites

1. Network access to the HelloData engine on Ecritel (`HELLODATA_BASE_URL`) and a valid `HELLODATA_TOKEN`.
2. `HELLODATA_ALLOWED_EMAILS` populated in a local, untracked `.env` if any non-admin caller needs access.

## What This Provides to Other Services

- MCP-accessible buyer counting, sampling, and CSV export from the BO's HelloData targeting engine.
- A per-call, per-identity authorization boundary that the gateway defers to rather than duplicating.
