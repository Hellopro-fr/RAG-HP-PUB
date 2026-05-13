# `mcp-zoho-service` — Per-User Zoho MCP Proxy

**Date:** 2026-05-12
**Scope:** new service under `apps-microservices/mcp-zoho-service/` + minimal gateway integration
**Status:** Draft

## Problem

The MCP gateway currently treats Zoho like any other MCP backend: one row in `mcp_servers` points to a single upstream URL, shared by all callers. Each end-user has their own Zoho CRM account at `crm.zoho.eu`; the gateway has no way to route a user's MCP call to their personal Zoho instance.

The just-shipped sheet-import + `created_by` feature lets operators register N per-user Zoho upstream URLs as `mcp_servers` rows (one per user), but the gateway has no logic that selects the right one per request — it only injects a downstream filter header, which Zoho's MCP backend doesn't currently honour.

## Goal

Introduce a new internal service `mcp-zoho-service` that the gateway treats as a single Zoho MCP backend. The service receives each MCP request, reads the caller's identity from headers injected by the gateway, looks up the correct upstream Zoho URL (admin's global one OR the caller's imported per-user one), and proxies the JSON-RPC payload there. When no match exists, the service returns a JSON-RPC error explaining that the caller has no Zoho configured.

This mirrors the `mcp-leexi-service` / `mcp-ringover-service` pattern (one bespoke service wrapping the provider, with per-user enforcement) but uses **routing** instead of **filtering** because Zoho user data lives in separate per-account silos at `crm.zoho.eu` rather than a multi-tenant DB Hellopro controls.

## Non-goals

- No per-user Zoho OAuth token storage (deferred — would be a follow-up feature once Hellopro hosts its own Zoho OAuth flow).
- No admin UI inside the new service. Operators continue registering per-user Zoho instances via the existing sheet-import flow on the gateway.
- No retroactive backfill or data migration.
- No multi-instance per user. If a single user has 2+ imported Zoho rows, the service picks the oldest (`ORDER BY created_at ASC`) and logs a warning. Multi-instance support is a v2.
- No streaming MCP transport in v1 (Zoho MCP currently does not stream). HTTP `POST /mcp` only.
- No changes to the shipped Zoho filter feature (`X-Zoho-Allowed-User` header on `scope_tokens` + `oauth2_clients`). It stays dormant when the only Zoho backend in `mcp_servers` is the service URL (Step 1 won't trigger because the service row has `template_slug=''`; Step 2 admin filter still works if anyone configures it).

## Affected surfaces

| Layer | Touched |
|---|---|
| **New service** | `apps-microservices/mcp-zoho-service/` — Go 1.24 / net/http, multi-stage Dockerfile, port 8596 |
| **Gateway runtime** | `internal/gateway/scoped_gateway.go` — inject `X-End-User-Email` + `X-End-User-Login` on Zoho-tagged backends |
| **Gateway constructor** | `internal/gateway/gateway.go` — no struct change; headers pulled from existing ctx |
| **docker-compose.yml** | New `mcp-zoho-service` block, port `8596:8596`, depends_on `mysql` |
| **CLAUDE.md (service-level)** | `apps-microservices/mcp-zoho-service/CLAUDE.md` (new) and a one-line addition to root `CLAUDE.md` service map |
| **Tests** | new service has `routing/`, `crypto/`, `http/` test packages |

## Design

### Architecture

`mcp-zoho-service` is a stateless HTTP proxy that speaks MCP streamable-HTTP. The gateway sees it as a regular MCP backend. The service:

1. Receives `POST /mcp` from the gateway with a JSON-RPC body and identity headers.
2. Resolves the caller's upstream Zoho URL (cached in-memory, 60s TTL).
3. Forwards the JSON-RPC body to that URL with the upstream's decrypted auth headers.
4. Returns the upstream response verbatim.

The service has no local persistent state. It reads `mcp_servers` and `server_authorizations` from the gateway's MySQL via a dedicated read-only DB account. It uses the same `ENCRYPTION_KEY` as the gateway to decrypt `mcp_servers.auth_headers` blobs.

### Sequence

```
[ Claude.ai ] POST /mcp + Bearer/X-MCP-Scope-Token
       ↓
[ mcp-gateway ]
       ↓ end_user_email in ctx (set by OAuth2 middleware)
       ↓ requestHeadersFor(backend) — Zoho case adds X-End-User-Email + X-End-User-Login
       ↓ proxies JSON-RPC to backend.URL = http://mcp-zoho-service:8596/mcp
       ↓ + Authorization (static, from backend.auth_headers if any)
       ↓ + X-Admin-Token: $ZOHO_ADMIN_TOKEN
       ↓
[ mcp-zoho-service ]
       ↓ readHeaders → email, login
       ↓ cache.get(email) → (upstreamURL, decryptedHeaders) ?
       ↓   miss → resolve():
       ↓       adminRow = SELECT … FROM mcp_servers WHERE tool_prefix='zoho' AND template_slug='' AND is_active LIMIT 1
       ↓       isAdmin = SELECT 1 FROM server_authorizations WHERE server_id=adminRow.id AND email=:email
       ↓       if isAdmin → use adminRow
       ↓       else:
       ↓           userRow = SELECT … FROM mcp_servers
       ↓                     WHERE tool_prefix LIKE 'zoho%' AND template_slug!=''
       ↓                       AND is_active AND matches(created_by, :email, :login)
       ↓                     ORDER BY created_at ASC LIMIT 1
       ↓           if userRow → use userRow
       ↓           else → NoMatchErr
       ↓       decrypt(row.auth_headers)
       ↓   cache.set(email, …, 60s)
       ↓ POST upstreamURL + decryptedHeaders + body  (or JSON-RPC -32001 error envelope on NoMatchErr)
       ↓ relay response
       ↓
[ Upstream Zoho MCP (crm.zoho.eu/...) ]
```

### Matching algorithm

```go
// matchesUserEmail returns true when the imported server's created_by maps
// to the caller's identity. Tries (1) full-email equality (case-insensitive)
// then (2) login-portion fallback (local-part before '@'). The login fallback
// covers cross-domain cases like alice@hp.fr vs alice@hellopro.fr.
//
// Never matches when serverCreatedBy or both identity inputs are empty.
func matchesUserEmail(serverCreatedBy, endUserEmail, endUserLogin string) bool {
	if serverCreatedBy == "" {
		return false
	}
	if endUserEmail != "" && strings.EqualFold(serverCreatedBy, endUserEmail) {
		return true
	}
	serverLogin := loginPart(serverCreatedBy)
	if serverLogin == "" {
		return false
	}
	switch {
	case endUserLogin != "" && strings.EqualFold(serverLogin, endUserLogin):
		return true
	case endUserEmail != "" && strings.EqualFold(serverLogin, loginPart(endUserEmail)):
		return true
	}
	return false
}

func loginPart(email string) string {
	at := strings.IndexByte(email, '@')
	if at <= 0 {
		return ""
	}
	return email[:at]
}
```

The SQL pre-filter narrows by `(LOWER(created_by) = LOWER(:email) OR LOWER(created_by) LIKE LOWER(CONCAT(:login, '@%')))`, then Go-side `matchesUserEmail` confirms.

### File inventory

```
apps-microservices/mcp-zoho-service/
├── CLAUDE.md                       # service docs
├── Dockerfile                      # multi-stage golang:1.24-alpine → alpine:3.20
├── go.mod / go.sum
├── cmd/server/main.go              # entry point: HTTP server, graceful shutdown (10s drain)
├── internal/
│   ├── config/config.go            # env loader (port, MYSQL_DSN, ENCRYPTION_KEY, ZOHO_GATEWAY_TOKEN, cache TTL)
│   ├── crypto/decrypt.go           # AES-256-GCM decrypt — algorithmic mirror of gateway's internal/crypto
│   ├── db/
│   │   ├── mysql.go                # connection pool (max 10 open / 2 idle), context-aware
│   │   └── queries.go              # prepared statements: FindAdminZohoServer, FindUserZohoImport, IsAdminGranted
│   ├── routing/
│   │   ├── resolver.go             # Resolve(ctx, email, login) → (upstreamURL string, headers map[string]string, error)
│   │   ├── cache.go                # in-memory TTL cache (60s default), sync.RWMutex
│   │   └── match.go                # matchesUserEmail, loginPart
│   ├── proxy/
│   │   └── proxy.go                # forwardJSONRPC: net/http client with 30s timeout, body relay
│   ├── mcp/
│   │   └── error.go                # JSON-RPC error envelope helpers (code -32001 "no_zoho_configured")
│   └── transport/
│       ├── handler.go              # POST /mcp, GET /health (always 200 unless DB is dead), middleware chain
│       └── middleware.go           # logging, recovery, X-Admin-Token validation, identity-header extraction
└── README.md (optional)
```

### Configuration

| Env var | Default | Description |
|---|---|---|
| `ZOHO_ROUTER_PORT` | `8596` | HTTP listen port. Adjacent to mcp-google-templates-runner (8595). |
| `MYSQL_DSN` | — | Read-only access to gateway DB. Dedicated user with `SELECT` on `mcp_servers` + `server_authorizations` only. |
| `ENCRYPTION_KEY` | — | Hex 32-byte AES-256 key. Identical to gateway's `ENCRYPTION_KEY`. Required to decrypt `mcp_servers.auth_headers`. |
| `ZOHO_GATEWAY_TOKEN` | — | Shared secret. Service rejects requests whose `X-Admin-Token` header doesn't match. |
| `ZOHO_ROUTING_CACHE_TTL` | `60` | Seconds. Email → upstream-URL cache lifetime. |
| `LOG_LEVEL` | `info` | `debug` / `info` / `warn` / `error`. |

Gateway side gains:

| Env var | Default | Description |
|---|---|---|
| `ZOHO_INTERNAL_URL` | — | In-cluster URL of mcp-zoho-service (e.g. `http://mcp-zoho-service:8596`). Mirrors `LEEXI_INTERNAL_URL`. Currently not used at boot — present for parity / future health checks. |
| `ZOHO_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` on every outbound MCP call to mcp-zoho-service. Must equal `ZOHO_GATEWAY_TOKEN` on the service side. |

### Gateway integration

The gateway change is minimal:

1. **Header injection on Zoho-tagged backends**: extend `requestHeadersFor` (or `injectZohoHeader`) to add `X-End-User-Email` and `X-End-User-Login` whenever the active `backend.ToolPrefix == "zoho"` AND an end-user email exists in ctx. Login portion is derived in-flight (`strings.Split(email, "@")[0]`).
2. **Admin token**: include `X-Admin-Token: $ZOHO_ADMIN_TOKEN` on every outbound MCP call to mcp-zoho-service. The static `mcp_servers.auth_headers` for the service row carries this — operators register it on the admin row at deployment time.
3. **No DTO change**, no proto change. The existing `MCPServer` row pointing at `http://mcp-zoho-service:8596/mcp` (with `tool_prefix='zoho'`) is the only operator-facing artefact.

### MCP error contract (no-match)

When the caller has no matching Zoho server and is not in the admin grant list, the service returns:

```json
{
  "jsonrpc": "2.0",
  "id": <request id>,
  "error": {
    "code": -32001,
    "message": "no Zoho server configured for alice@hp.fr",
    "data": {
      "end_user_email": "alice@hp.fr",
      "category": "no_zoho_configured"
    }
  }
}
```

HTTP status is `200` — the JSON-RPC envelope carries the error per spec. The gateway forwards this verbatim to the MCP client; Claude.ai shows the message in its tool error UI.

For `tools/list` calls in this state, the service returns the same error envelope. (Alternative: return empty `tools[]` array. Open to revisit in v1.1 — current spec is "error on every method" for clarity.)

### Authentication & trust model

- **Gateway → Service**: shared bearer secret `X-Admin-Token`. Network ACL keeps service reachable only from gateway hosts. Trust-the-header model — the service believes whatever `X-End-User-Email` the gateway sends.
- **Service → Upstream Zoho**: static auth headers from the matched `mcp_servers.auth_headers` (decrypted on demand). These are typically `Authorization: Bearer …` tokens minted when the operator registered the user's connection.
- **No JWT validation on the service**. The token authorisation lives at the gateway level (already enforced by OAuth2 / X-MCP-Scope-Token middleware). The service inherits that trust via the admin-token header.

### Caching

In-memory TTL cache keyed by `(email)`. Value: `{upstreamURL, decryptedHeaders, expiresAt}`. Lookups during cache miss perform exactly 1–2 DB queries (admin lookup + import lookup). Cache invalidation strategies (v1 = TTL only):

| Trigger | Behaviour |
|---|---|
| Cache miss | Resolve from DB, set entry. |
| TTL expiry | Next request re-resolves. |
| Import added on gateway side | Up to TTL seconds of staleness. Acceptable for v1. |
| Service restart | Cache empty. First request per user re-resolves. |

A v2 webhook from the gateway (`POST /admin/invalidate-email`) is on the back burner; not in scope here.

### Validation rules

| Condition | Behaviour |
|---|---|
| Missing `X-End-User-Email` header | 400 with `{"error":"missing_end_user_email"}`. |
| Missing `X-Admin-Token` or mismatch | 401 with `{"error":"invalid_admin_token"}`. |
| Admin Zoho row missing | 503 with `{"error":"misconfigured: no admin Zoho row"}`. |
| Admin grant matched | Route to admin row's URL + decrypted headers. |
| Imported Zoho matched | Route to user row's URL + decrypted headers. |
| Multiple imported Zoho rows for same user | Use the oldest (created_at ASC). Emit a `WARN` log. |
| No match | JSON-RPC error -32001. |
| Upstream Zoho returns 4xx/5xx | Relay verbatim. No retry in v1. |
| Upstream Zoho timeout (30s) | Relay as JSON-RPC -32603 internal error with message "upstream Zoho timeout". |
| Cache hit | No DB query, headers reused. |

### Tests

`internal/routing/match_test.go`:

1. Exact email match (case-insensitive) → true.
2. Login-portion match with different domains → true.
3. Login-portion match with same domain → true.
4. Empty `serverCreatedBy` → false (regardless of inputs).
5. Empty both `endUserEmail` AND `endUserLogin` → false.
6. Malformed `serverCreatedBy` (`@hp.fr`) → false.

`internal/routing/resolver_test.go`:

1. Admin email in `server_authorizations` → admin URL.
2. Non-admin, exact email match → user URL.
3. Non-admin, login-portion match → user URL.
4. Non-admin, no match → `NoMatchErr`.
5. Email empty → `InvalidErr`.
6. Admin Zoho row missing → `MisconfigErr`.
7. Multi-match → oldest by created_at; warn logged.
8. Cache hit on second call within TTL (verify with call counter mock).
9. Cache miss after TTL.

`internal/crypto/decrypt_test.go`: round-trip ciphertext with a known plaintext + key, verifying the algorithm matches gateway's `internal/crypto/encrypt.go`.

`internal/transport/handler_test.go`:

1. Valid request → upstream `httptest.Server` receives body + decrypted headers.
2. Missing `X-End-User-Email` → 400.
3. Wrong `X-Admin-Token` → 401.
4. No-match resolver → 200 JSON-RPC envelope with code -32001.
5. Admin Zoho row missing → 503.

`gateway` side (extend `internal/gateway/scoped_gateway_test.go`):

1. Zoho-tagged backend + end-user-email in ctx → outbound headers include `X-End-User-Email` + `X-End-User-Login`.
2. Zoho-tagged backend + no end-user-email → headers omit those two keys.
3. Non-Zoho backend → headers do not include them.

### docker-compose entry

```yaml
mcp-zoho-service:
  build:
    context: ./apps-microservices/mcp-zoho-service
    dockerfile: Dockerfile
  container_name: mcp-zoho-service
  ports:
    - "8596:8596"
  environment:
    ZOHO_ROUTER_PORT: 8596
    MYSQL_DSN: ${MCP_GATEWAY_MYSQL_DSN_READONLY}
    ENCRYPTION_KEY: ${MCP_GATEWAY_ENCRYPTION_KEY}
    ZOHO_GATEWAY_TOKEN: ${ZOHO_GATEWAY_TOKEN}
    ZOHO_ROUTING_CACHE_TTL: 60
    LOG_LEVEL: info
  depends_on:
    mysql:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://localhost:8596/health"]
    interval: 30s
    timeout: 5s
    retries: 3
  restart: unless-stopped
  networks:
    - rag-network
```

## Rollout

1. Land the new service + tests; merge first as a no-op (no gateway change yet).
2. Add the gateway-side header injection (`X-End-User-Email`, `X-End-User-Login`) on the Zoho path. Deploy.
3. Admin registers one `mcp_servers` row: `name='Zoho'`, `tool_prefix='zoho'`, `template_slug=''`, `url='http://mcp-zoho-service:8596/mcp'`, with `auth_headers` containing `{"X-Admin-Token": "<ZOHO_GATEWAY_TOKEN>"}` (this is decrypted on outbound, then forwarded).
4. Existing manual Zoho row (if any) is replaced by this one. The previously-stored upstream URL becomes the **admin's** Zoho URL — operator captures it into a new `mcp_servers` row with `tool_prefix='zoho'`, `template_slug=''` but `is_active=true` AND adds themselves into `server_authorizations` for that row.

Wait — there's an ambiguity to resolve at rollout: the row pointing at mcp-zoho-service has `tool_prefix='zoho' AND template_slug=''`. But so does the admin's actual Zoho row. The service's "find admin row" query (`tool_prefix='zoho' AND template_slug='' LIMIT 1`) would collide.

Fix: the admin row must be marked distinctly. Three options:
- (a) Use a different `tool_prefix` (e.g. `zoho_admin`) for the admin upstream row.
- (b) Add a sentinel tag or a dedicated column (heavy).
- (c) The service queries by URL: any `mcp_servers` row whose URL is NOT the service's own URL.

Choosing (c) — query reads `MYSELF_URL` from env (`ZOHO_SELF_URL`) and excludes that row from candidates. Practical, no schema change, makes the wiring explicit.

Updated env var:

| Env var | Default | Description |
|---|---|---|
| `ZOHO_SELF_URL` | — | The URL the gateway calls this service on (e.g. `http://mcp-zoho-service:8596/mcp`). Used to exclude the service's own row when picking the admin upstream. |

## Impact

| Component | LOC estimate |
|---|---|
| New service (Go) | ~1200 LOC including tests |
| Gateway header injection | ~30 LOC |
| docker-compose entry | ~25 LOC |
| Service CLAUDE.md | ~120 LOC |
| Root CLAUDE.md update | 1 line |
| Total | ~1400 LOC |

## Risks

- **Shared `ENCRYPTION_KEY` across two services**: same operational discipline as today's gateway-only key. Rotate in lockstep if ever rotated.
- **Trust-the-header model**: anyone with `ZOHO_GATEWAY_TOKEN` can claim any identity. Mitigation: token rotation runbook + network ACL.
- **DB schema coupling**: service depends on `mcp_servers.tool_prefix`, `template_slug`, `created_by`, `is_active`, `url`, `auth_headers`. Any schema change to those columns breaks the service. Mitigation: pin column list in queries, document in service CLAUDE.md.
- **Cache staleness on import (≤60s)**: imports take effect within one TTL window. Acceptable for v1. Webhook-fed invalidation is a future optimisation.
- **Self-row exclusion**: the admin row must NOT have its `url` equal to `ZOHO_SELF_URL`. Service skips self-equal rows when picking the admin Zoho. Document the convention in service CLAUDE.md and validate at boot.
- **JSON-RPC error on tools/list**: callers may see a confusing "no Zoho configured" error even before they call a tool. Could be alleviated by returning empty `tools[]` on `tools/list` while erroring on `tools/call`. Decision deferred; v1 errors on every method.
- **The shipped Zoho filter feature becomes inert**: not a regression — admin filter still works if any admin chooses to set it (sends `X-Zoho-Allowed-User` to this service). Service simply ignores that header for routing decisions; if a downstream upstream cared, it would still see it. No code removal needed; just acknowledged in CLAUDE.md.

## Open questions (resolved before merge)

- `mcp_servers.auth_headers` for the admin row vs the service row: the service row's auth_headers carry the `X-Admin-Token`; the admin upstream Zoho's auth_headers carry whatever Zoho expects. The service decrypts the upstream's auth_headers on its side, not the service-row's. The gateway-side outbound (gateway → service) uses the service-row's decrypted auth_headers in the normal `requestHeadersFor` path.
- Health endpoint check: `GET /health` returns 200 always once boot succeeds. A deeper liveness probe (DB ping) is v1.1.
- Metrics: not in v1. Add Prometheus `/metrics` once usage justifies it.
