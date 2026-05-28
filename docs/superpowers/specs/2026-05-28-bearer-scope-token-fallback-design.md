# Bearer scope-token fallback — design

**Date:** 2026-05-28
**Service:** `apps-microservices/mcp-gateway-service`
**Branch target:** `features/poc`

## Problem

Scope tokens issued by `POST /api/v1/tokens` (prefix `mcp_`, 52 chars) are only accepted via the custom HTTP header `X-MCP-Scope-Token`. Standard MCP clients (Claude.ai web, Cursor, VS Code MCP) cannot set custom headers — they only support `Authorization: Bearer <token>`. Today, presenting a scope token in `Authorization: Bearer` fails JWT validation in `oauth2.CombinedMiddleware` and the request is rejected with `401 invalid_token + WWW-Authenticate: Bearer …`, which kicks the client into the OAuth2 discovery flow it cannot complete (the gateway's OAuth2 Authorization Server requires `/authorize` + consent, not appropriate for these scope-token-only clients).

## Goal

Accept a `/tokens`-issued scope token presented in `Authorization: Bearer`. OAuth2 JWT path remains untouched.

## Non-goals

- New token type, format, or storage.
- Changes to OAuth2 Authorization Server (`/authorize`, `/token`, `/register`, `/.well-known/oauth-authorization-server`).
- Changes to scope-token issuance, revocation, expiry, scoping, filters (Leexi/Ringover/Zoho/BDD), or instruction injection.
- Migration off the legacy `X-MCP-Scope-Token` header — both keep working.

## Decisions

| Item | Decision |
|---|---|
| Trigger | Scope token (`mcp_*`) sent in `Authorization: Bearer` |
| OAuth2 JWT path | Unchanged |
| Bearer discriminator | Prefix: value starts `mcp_` → scope-token path. Else → existing JWT path. |
| Both headers present | `X-MCP-Scope-Token` wins (current behavior is opposite — see Behavior change) |
| Failure on scope path | 401 invalid / 403 revoked/expired, **no** `WWW-Authenticate` header |
| Audit | Emit `auth_source=bearer` or `auth_source=x-mcp-scope-token` in log lines + Slack reason |
| UI | Token detail card + creation modal expose Bearer snippet alongside `X-MCP-Scope-Token`; Bearer default for new generation |

## Architecture

Three files touched. No new tables, env vars, packages, or dependencies. Cache layer reused as-is (lookup keyed by `sha256(rawToken)` — header source is irrelevant to the hash).

```
internal/oauth2/middleware.go       — CombinedMiddleware: reorder + Bearer discriminator
internal/scopetoken/middleware.go   — extract ValidateAndBuildContext helper, accept authSource
internal/ui/static/index.html       — render Bearer snippet alongside X-MCP-Scope-Token
```

## Behavior change

| Request | Today | After |
|---|---|---|
| `X-MCP-Scope-Token: mcp_…` (only) | scope path, 200 | scope path, 200 (unchanged) |
| `Authorization: Bearer <jwt>` (only) | OAuth2 path, 200 | OAuth2 path, 200 (unchanged) |
| `Authorization: Bearer mcp_…` (only) | OAuth2 path → 401 `invalid_token` + `WWW-Authenticate` | scope path, 200 (**new**) |
| Both, scope token + JWT | OAuth2 wins | scope path wins (**reversal** — flagged) |
| Both, scope token + `Bearer mcp_…` | OAuth2 path → 401 | scope path wins on `X-MCP-Scope-Token` value |
| Neither | 401 + `WWW-Authenticate` | 401 + `WWW-Authenticate` (unchanged) |

The dual-credential reversal is the only behavior change for existing clients. Assessment: low risk — no known client sends both, and any that does today already gets the OAuth2 client's scope, which is set up separately from the scope token. Migration note will be added to the service CLAUDE.md.

## Component changes

### `internal/scopetoken/middleware.go`

Extract validation core into a reusable function:

```go
// ValidateAndBuildContext validates rawToken and returns a context populated
// with the scope state from the token's DB row, or writes an error response
// and returns ok=false. authSource ("x-mcp-scope-token" | "bearer") is
// recorded in log lines and Slack reasons.
func ValidateAndBuildContext(
    w http.ResponseWriter, r *http.Request,
    rawToken, authSource string,
    cache *Cache, repo *repository.TokenRepo,
    instructionRepo *repository.InstructionRepo,
    slackClient *slack.Client,
) (context.Context, bool)
```

Existing `Middleware` becomes a thin wrapper that reads `X-MCP-Scope-Token`, applies the `required` flag, and delegates to the helper with `authSource="x-mcp-scope-token"`. The body of the existing `Middleware` (hash → cache → DB → IsActive/ExpiresAt → context build) moves into the helper with no logic changes other than the `authSource` log/Slack tag.

Log line on accept: `[scope] accepted token=<first 8 chars of hash> source=<authSource>`.
Slack `notifyUnauthorized` reasons include ` (source=<authSource>)`.

### `internal/oauth2/middleware.go`

New order in `CombinedMiddleware`:

```
1. X-MCP-Scope-Token present and non-empty
   → scopetoken.ValidateAndBuildContext(token, "x-mcp-scope-token")
2. Else Authorization: Bearer present
   2a. Value starts with "mcp_"
       → scopetoken.ValidateAndBuildContext(token, "bearer")
   2b. Otherwise
       → existing JWT path (ValidateAccessToken + OAuth2 cache + filter decoding)
3. Else: 401 + WWW-Authenticate (unchanged)
```

The JWT branch keeps its current body verbatim, including `WWW-Authenticate: Bearer error="invalid_token"` on validation failure. The reorder + Bearer dispatch are the only edits to this file.

### `internal/ui/static/index.html`

Two code sites build the `args` array:

- `updateTokenCardJSON` (~L1620): token detail card rendering.
- `createScopeToken` result block (~L1645): post-creation success card.

Both gain a small tab/toggle (default = **Bearer**, alternate = `X-MCP-Scope-Token`). Bearer variant uses `--header "Authorization: Bearer <token>"`; legacy variant unchanged.

Caption beneath the toggle (FR, matching surrounding copy):

> *Utilisez **Bearer** pour Claude.ai, Cursor et les clients MCP standards. Utilisez **X-MCP-Scope-Token** pour les intégrations personnalisées qui supportent les en-têtes personnalisés.*

Clipboard-copy logic copies whichever variant is active.

## Data flow

```
Client ──► Authorization: Bearer mcp_…  OR  X-MCP-Scope-Token: mcp_…
              │
              ▼
      oauth2.CombinedMiddleware
        1. X-MCP-Scope-Token? ─yes─┐
        2. Bearer starts "mcp_"? ──┤── scopetoken.ValidateAndBuildContext
        2b. Bearer JWT? ──── existing JWT path
              │
              ▼  (context with AllowedServers / Tools / filters / instructions)
      ScopedGateway (unchanged)
```

`EndUserEmailContextKey` remains unset for scope-token requests via either header — consistent with current behavior; OAuth2 self-filter mode is still rejected for scope tokens.

## Error handling

| Path | Condition | Status | WWW-Authenticate |
|---|---|---|---|
| scope (either header) | invalid hash | 401 `{"error":"invalid scope token"}` | — |
| scope | revoked / expired | 403 | — |
| OAuth2 JWT | invalid JWT | 401 `{"error":"invalid_token"…}` | yes (existing) |
| OAuth2 JWT | revoked / expired | 403 | — |
| All | missing both | 401 | yes (existing) |

Slack `UnauthorizedEvent` cooldown by `(ip, endpoint)` reused unchanged. Reason string carries `auth_source=…`.

## Audit / observability

- `auth_source` appears in `[scope]` log lines on accept, in Slack `UnauthorizedEvent.Reason` on reject. No DB schema change to `audit_logs` — log aggregation can index the tag.
- No new metrics. (If a counter is added later, partition by `auth_source` label.)

## Testing

**Unit — `internal/oauth2/middleware_test.go`** (new cases):
1. `Bearer mcp_<valid>`, no `X-MCP-Scope-Token` → 200, allowed-servers context set.
2. `Bearer mcp_<revoked>` → 403.
3. `Bearer mcp_<unknown>` → 401, no `WWW-Authenticate`.
4. `Bearer <valid-jwt>` → 200, OAuth2 cache path runs (regression).
5. Both headers, X-MCP-Scope-Token valid, Bearer arbitrary → scope path wins, JWT validator not called.
6. `Bearer foobar` (no `mcp_` prefix, not a JWT) → 401 + `WWW-Authenticate` (falls into JWT branch).

**Unit — `internal/scopetoken/middleware_test.go`**:
7. Table-driven: `ValidateAndBuildContext` produces identical context shape for `authSource="bearer"` vs `authSource="x-mcp-scope-token"`.
8. Existing `Middleware` tests stay green (regression).

**Manual smoke**:
- `curl -H "Authorization: Bearer mcp_<valid>" https://gateway/mcp` returns MCP initialize success.
- Claude.ai MCP config with `Authorization: Bearer mcp_*` connects without OAuth2 round-trip.
- Existing OAuth2 client (Zoho) still completes initialize.

No new tests for the UI beyond visual sanity (snippet renders correctly, clipboard copy yields the expected JSON).

## Rollout

Single PR. No DB migration. No env-var changes. No backwards-compat shim — both headers continue to work indefinitely.

CLAUDE.md update: add a row to the "MCP Transports" section describing the Bearer alias and the precedence rule.

## Risks

| Risk | Mitigation |
|---|---|
| OAuth2-client + scope-token dual-creds clients see reversed precedence | None known to exist; behavior change documented in CLAUDE.md + PR description |
| `Bearer mcp_*` interpreted as OAuth2 access token by intermediaries (proxies, WAFs) | Token is opaque hex; no semantic collision. Same exposure surface as today's `X-MCP-Scope-Token`. |
| Log volume increase from `[scope] accepted` lines | Same log frequency as today's scope-token path; only the `source=` tag is new |
| Prefix `mcp_` clash with a real OAuth2 access token | OAuth2 access tokens are HS256 JWTs (`x.y.z` shape with `.`). No conflict possible |
