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
│   ├── acces/acces.go               # Authorization re-check (admin role OR gateway-reported grant)
│   ├── filtre/filtre.go             # Filter-tree validation/translation
│   ├── tools/
│   │   ├── registry.go              # Tool definitions (compter, echantillon, export_csv)
│   │   ├── handler.go                # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── selection.go             # Tool implementations, calls into hellodata.Client
│   │   └── jetons.go                 # Download-token issuance/table for the CSV export flow
│   ├── download/proxy.go            # /download/ HTTP proxy that redeems a token for a CSV
│   └── transport/http.go            # /mcp Streamable HTTP handler, identity extraction from headers (also used by /download)
├── Dockerfile                       # 2-stage build, non-root Alpine
└── go.mod
```

## MCP Tools

The service names its tools WITHOUT the `hellodata_` prefix: the gateway
adds it (`tool_prefix = "hellodata"`, `PrefixedToolName`), exactly as
`bdd_query_readonly` is the `bdd` prefix plus the `query_readonly` tool.
The name below is the one the LLM finally sees.

| Tool (name seen by the LLM) | Backend name | Description |
|------|------|-------------|
| `hellodata_compter` | `compter` | Counts buyers matching a filter tree. Fast approximate mode (capped at 10000) by default; `exact=true` gives the real count but can take over a minute. |
| `hellodata_echantillon` | `echantillon` | Reads buyers matching the filter, page by page (up to 2000 rows/call, 50 by default, cursor-based pagination). |
| `hellodata_export_csv` | `export_csv` | Renders one page (≤2000 rows) of the selection as a CSV download URL. Link expires after 15 minutes and does not survive a service restart. |

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

There is no allow-list variable any more: who may use the service is managed
in the gateway's `/server-authorizations` screen (see § Accès).

## Accès

**Le gateway décide, ce service re-vérifie.** Règle : rôle `admin` dans
`gateway_users`, **ou** une ligne `server_authorizations` (serveur
hellodata, e-mail de l'appelant), gérée depuis l'écran
`/server-authorizations` du gateway. Le gateway l'applique avec le même
contrôle que les instances Neo4j (`gateway.Neo4jAccess`, qui reconnaît ce
serveur à son `tool_prefix = "hellodata"`) : un appelant refusé ne voit pas
le serveur à l'écran de consentement OAuth2, reçoit un `tools/list` vide et
voit ses `tools/call` refusés sans transmission. Poser `min_role =
config-only` sur le serveur : il écarte les chemins sans identité (tokens de
scope, grants `client_credentials`) sans écarter un titulaire de grant au
rôle `config-only`. `read-only` l'écarterait, et `readonly` (sans tiret)
n'est pas un rôle : il refuse tout le monde, admins compris.

Le gateway injecte trois en-têtes non signés : `X-End-User-Email`,
`X-End-User-Role` (seulement si le rôle est résolu) et
`X-End-User-Granted: true` (seulement si un grant existe — jamais `false`).
`internal/acces` refuse sans e-mail, puis accepte `admin` ou `granted` ;
seule la valeur exacte `true` compte. Chaque appel d'outil accepté est
journalisé avec l'adresse et la source du droit (`admin` ou `grant`). Un
titulaire de grant n'est pas admin : il n'a pas accès aux colonnes
restreintes (`email`, `mobile`). Seul `/health` répond sans identité, et il
ne renvoie aucune donnée métier.

Cette re-vérification n'a de sens que si le service n'est **joignable que
depuis le réseau Docker interne** — d'où `expose:` et jamais `ports:` dans
`docker-compose.yml` : si un tiers peut atteindre le port 8597
directement, il peut forger `X-End-User-Role: admin` ou
`X-End-User-Granted: true`. La frontière réseau **est** la garantie.

Raisonnement complet : `docs/superpowers/specs/2026-09-28-mcp-hellodata-server-authorizations-design.md`
(il remplace D10, D11 et le § 7.1 de
`docs/superpowers/specs/2026-09-21-mcp-hellodata-selection-design.md`).

## Prerequisites

1. Network access to the HelloData engine on Ecritel (`HELLODATA_BASE_URL`) and a valid `HELLODATA_TOKEN`.
2. A `server_authorizations` grant on the hellodata server (gateway `/server-authorizations` screen) for each non-admin caller.

## What This Provides to Other Services

- MCP-accessible buyer counting, sampling, and CSV export from the BO's HelloData targeting engine.
- A per-call, per-identity re-check of the gateway's access decision (defense in depth).
