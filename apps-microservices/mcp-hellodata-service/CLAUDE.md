# mcp-hellodata-service

Custom MCP server exposing the BO's buyer-targeting engine (HelloData) as MCP
tools: filtered counting, paginated sampling, and CSV export of buyer
selections, plus SMS / call campaigns (selection with history, responses),
over Streamable HTTP.

## Tech Stack

- **Language:** Go 1.24
- **Protocol:** MCP (JSON-RPC 2.0 over Streamable HTTP, single `/mcp` endpoint — no SSE)
- **Backend communication:** HelloData engine REST API on the BO (`/admin/mcp/hellodata`), Bearer token; campaign responses go to the FRONT webhook (`/partenaires_externes/mcp/hellodata`), its own Bearer token. Both speak the same contract: `POST {base}/index.php?action=<name>`, JSON body, `{code, response}` envelope.
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
│   │   └── types.go                 # Engine request/response types (PageCSV.Lien, Recuperation.URLCSV: BO signed links)
│   ├── acces/acces.go               # Authorization re-check (admin role OR gateway-reported grant)
│   ├── filtre/filtre.go             # Filter-tree validation/translation
│   ├── tools/
│   │   ├── registry.go              # Tool definitions (selection + campaign tools)
│   │   ├── handler.go                # MCP request handler (initialize, tools/list, tools/call)
│   │   ├── selection.go             # Selection tools (compter, echantillon, export_csv), calls into hellodata.Client
│   │   ├── campagnes.go             # Campaign tools (recup_acheteur, bilan_campagnes, enregistrer_reponses)
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
| `hellodata_export_csv` | `export_csv` | Renders one page (≤2000 rows) of the selection as a CSV download URL: the BO's signed `download.php` link (header `X-Hellodata-Lien`, 15 minutes, CSV regenerated on each download). Falls back to a wrapper `/download` token only when the engine sends no link, or a link whose scheme+host differ from `HELLODATA_BASE_URL`. |
| `hellodata_recup_acheteur` | `recup_acheteur` | BO. Selects `n` (1–2000) buyers for a campaign (created when its `code` is unknown), deduplicated by phone, filter combining `acheteur` criteria and `hist_*` history leaves. Returns counters and `url_csv`: the BO's signed `download.php` link from the engine's `url_csv` field (fallback: a wrapper `/download` token); the CSV itself is never inline. `cree_par` is the caller's `X-End-User-Email`, never an argument. |
| `hellodata_bilan_campagnes` | `bilan_campagnes` | BO. Lists campaigns with their counters (sent, positive, negative_contactable, negative_stop, no answer); optional `code`. |
| `hellodata_enregistrer_reponses` | `enregistrer_reponses` | FRONT webhook. Records ≤500 provider responses classified by the LLM (`positive` / `negative_contactable` / `negative_stop`). |

There is no `hellodata_export_statut` tool: exports are single-page and
rendered directly by `hellodata_export_csv` — no async job to poll.

The `filtre` input schema (`schemaFiltre`, `internal/tools/registry.go`) is a
plain `"type": "object"` with NO `$ref`: a `#/definitions/...` reference
resolves from the root of the tool's `inputSchema`, so one nested inside the
property is broken, and claude.ai then sent `filtre` as a JSON string
(`filtre illisible: cannot unmarshal string`) on every filter tool. The
recursive shape is described in the text and enforced by `filtre.Valider`.
`normaliserFiltre` also accepts a stringified object and forwards the object
to the engine. Tests: `internal/tools/filtre_chaine_test.go`.

## MCP Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp` | POST | Streamable HTTP transport (stateless JSON-RPC) |
| `/download/{token}` | GET | Fallback only: redeems a short-lived token for the CSV when the engine sent no signed link. The service is `expose:`-only, so this route is not publicly reachable — the normal path is the BO's `download.php?t=<ticket>` link |
| `/health` | GET | Liveness probe — no identity required, no business data returned |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | 8597 | HTTP server port |
| `HELLODATA_BASE_URL` | — | Base URL of the HelloData engine (`/admin/mcp/hellodata` on Ecritel), required |
| `HELLODATA_TOKEN` | — | Bearer token presented to the engine, required |
| `HELLODATA_PUBLIC_URL` | — | Public base URL of the fallback `/download` links. Not needed once the BO serves `download.php` (links come from the engine) |
| `HELLODATA_WEBHOOK_URL` | — | Base URL of the FRONT webhook (`/partenaires_externes/mcp/hellodata`), required |
| `HELLODATA_WEBHOOK_TOKEN` | — | Bearer token presented to the webhook (distinct from `HELLODATA_TOKEN`), required |

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
restreintes (`email`, `mobile`) de `echantillon` / `export_csv`. **En
revanche**, le CSV de `recup_acheteur` porte `telephone_normalise` pour tout
appelant autorisé : c'est la liste à transmettre au prestataire (spec
campagnes § 6.1). La précondition 5 (droit aux colonnes téléphone) n'étant
pas tranchée, ce point reste à valider. Seul `/health` répond sans
identité, et il ne renvoie aucune donnée métier.

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
2. The FRONT webhook (`HELLODATA_WEBHOOK_URL`) and its `HELLODATA_WEBHOOK_TOKEN` — the service refuses to start without them.
3. The four campaign tables (`historique_campagne_*_ia`, database `edgb2b`) — read and written by the BO and the webhook, never by this service.
4. A `server_authorizations` grant on the hellodata server (gateway `/server-authorizations` screen) for each non-admin caller.

## What This Provides to Other Services

- MCP-accessible buyer counting, sampling, and CSV export from the BO's HelloData targeting engine.
- SMS / call campaign workflow: selection crossed with response history, campaign report, response recording.
- A per-call, per-identity re-check of the gateway's access decision (defense in depth).
