# Neo4j template instances — service-level access gate

**Date:** 2026-09-30
**Branch:** `features/neo4j-access-gate` (from `features/poc`)
**Status:** Approved design, pending implementation plan
**Related:** `2026-09-29-mcp-template-neo4j-design.md` (the template itself — its "read-only" flag is *database*-level access and is unchanged here); `2026-09-28-mcp-hellodata-server-authorizations-design.md` (same "admin OR grant" rule designed for HelloData, not implemented, lives on `features/mcp-bdd-table`).

## Goal

A Neo4j template instance must be **visible and usable only by**:

- gateway **admins** (`gateway_users.role = "admin"`), and
- users holding a **`server_authorizations` row for that exact instance** (managed from the existing `/server-authorizations` admin page).

Everybody else must neither see the instance (OAuth2 consent screen, `tools/list`, `resources/list`, `prompts/list`) nor be able to call it (`tools/call`, `resources/read`, `prompts/get`).

This is **service-level** access (who may reach the MCP server). It is independent of the per-instance `NEO4J_READ_ONLY` flag, which stays **database-level** (what the server may do in Neo4j).

## Current state (`features/poc`, 2026-09-30)

- No service-level gate applies to Neo4j instances: any caller whose scope token / OAuth2 client includes the server can list and call it. `mcp_servers.min_role` and its `GateAllowsEmail` gate exist only on `features/mcp-bdd-table` (#807), not on poc.
- `server_authorizations` exists on poc but means "unfiltered access" for filtered backends (leexi, ringover, bdd — `requestHeadersFor` Step 0) and "admin Zoho account" for Zoho. It never grants or denies access by itself.
- Available building blocks on poc: `ScopedGateway.isGatewayAdmin(email)` (`gatewayUserFinder.GetByEmail`), `ScopedGateway.isServerAuthorized(ctx, serverID)` / `serverAuthorizer.IsAuthorized(serverID, email)`, `scopetoken.EndUserEmailFromContext(ctx)`, `BackendServer.TemplateSlug` (echo of `mcp_servers.template_slug`), `TemplateRepo.GetBySlugAny(slug)` (includes inactive templates) and `templates.runner`.

## Decisions

| # | Topic | Decision |
|---|---|---|
| G1 | Which servers | **Neo4j template instances only**: a backend is *restricted* when `TemplateSlug != ""` and the template with that slug has `runner = "neo4j"` (so it also covers Neo4j templates created later from the "Créer" page). No new column, no generic per-server flag (explicitly not chosen). |
| G2 | Rule | Allowed ⇔ the request carries an end-user email **and** (`gateway_users.role == "admin"` with `is_allowed = true` **or** `server_authorizations(server_id, email)` exists). An admin disabled on the Users page (`is_allowed = false`) is not an admin for this gate, so offboarding also closes access through still-valid OAuth2 tokens. `is_allowed` is **not** applied to the grant path (account-synced users are created with `is_allowed = false`). |
| G3 | Callers without email | `mcp_…` scope tokens and `client_credentials` OAuth2 grants carry no end-user email → **always denied** on restricted servers. |
| G4 | Failure mode | **Fail-closed**: template / user lookup errors and unwired repositories → denied. A missing template row for a non-empty `template_slug` (FK is RESTRICT, so only a corrupted DB) → treated as restricted and denied. |
| G5 | Unrestricted servers | Behaviour unchanged, including the static `mcp-neo4j-service` (no `template_slug`), Google, Zoho, leexi, ringover, bdd, hellodata. |
| G6 | Grants management | Existing `/server-authorizations` page and REST API (lists every `mcp_servers` row). A grant on instance A never opens instance B. A grant keeps its existing "unfiltered" meaning on filtered backends — Neo4j instances inject no filter headers, so there is no conflict. |
| G7 | Base | Built directly on `features/poc` (not on #807). |
| G8 | Frontend | No change required. |

## Design

### Component — `internal/gateway/neo4j_access.go` (new)

```go
// templateRunnerLookup is the slice of *repository.TemplateRepo the policy needs.
type templateRunnerLookup interface {
	GetBySlugAny(slug string) (*db.Template, error)
}

// Neo4jAccess decides service-level access to Neo4j template instances.
type Neo4jAccess struct {
	templates templateRunnerLookup
	users     gatewayUserFinder // existing interface (GetByEmail)
	grants    serverAuthorizer  // existing interface (IsAuthorized)
	// slug → isNeo4j cache, TTL 60 s, guarded by a mutex
}

func NewNeo4jAccess(t templateRunnerLookup, u gatewayUserFinder, g serverAuthorizer) *Neo4jAccess

// Restricted reports whether b is a Neo4j template instance (fail-closed on lookup errors).
func (a *Neo4jAccess) Restricted(b *BackendServer) bool

// Allows reports whether the request's end user may reach b.
// Non-restricted backends → true. Restricted → G2/G3/G4.
func (a *Neo4jAccess) Allows(ctx context.Context, b *BackendServer) bool
```

- A nil `*Neo4jAccess` allows everything (keeps existing tests and non-wired setups unchanged) — `app.go` always wires it in production.
- The slug→runner cache avoids a DB query per tool listed; a runner change on a template with instances is already refused by the catalog import (409), so a 60 s TTL is safe. Grants and roles are **not** cached: revoking a grant takes effect on the next request.
- Log every denial on a *call* verb with backend id, template slug and caller email (never credentials); listing omissions are not logged per item.

### Wiring — `internal/app/app.go`

Build one `Neo4jAccess` from the existing `TemplateRepo`, `UserRepo` and `ServerAuthorizationRepo`, and pass it to the `Gateway` / `ScopedGateway` and to the `AuthServer` through setter methods, following the existing wiring pattern for optional collaborators.

### Enforcement points

| Where | Behaviour for a denied caller on a restricted backend |
|---|---|
| `ScopedGateway.handleToolsList` | the backend's tools are omitted |
| `ScopedGateway.handleToolsCall` | JSON-RPC error `access denied: this server requires an admin role or a server authorization`; the call is not forwarded |
| `ScopedGateway.handleResourcesList` / `handlePromptsList` | the backend's resources / prompts are omitted — these two handlers gain a `ctx context.Context` parameter (they have none on poc) |
| `ScopedGateway.handleResourcesRead` / `handlePromptsGet` | same JSON-RPC error, not forwarded |
| `ScopedGateway.handleInitialize` | capabilities are computed from the visible backends only, and every `per_server` LLM instruction none of whose `ServerIDs` is visible is dropped from `instructions` (an instruction bound to a hidden instance typically carries its graph schema); `general` instructions are kept |
| `AuthServer.renderConsent` (HTML) and `buildServerList` (JSON API) | the server is omitted from the list shown to the viewer |
| Consent **submission** (the POST that stores the selected servers) | a submitted server id the viewer is not allowed to see is dropped (never stored in the consent / OAuth2 client scope) |

Viewer identity: `scopetoken.EndUserEmailFromContext(ctx)` in the scoped gateway; the logged-in `mcp_session` email in the consent handlers.

### Data flow

1. Admin creates instance `neo4jprod` (Templates → Neo4j) → `mcp_servers.template_slug = "neo4j"`.
2. By default only admins see it. The admin opens `/server-authorizations`, picks `neo4jprod`, adds `alice@…`.
3. Alice's next consent screen lists `neo4jprod`; after consent, her `tools/list` shows `neo4jprod_*` tools and calls go through. Bob (no grant, not admin) never sees it; a hand-crafted `tools/call neo4jprod_read_neo4j_cypher` returns the access-denied error.
4. Removing Alice's grant takes effect on her next request.

## Error handling

| Case | Result |
|---|---|
| No end-user email (scope token, client_credentials) | denied (omitted / error) |
| Email unknown in `gateway_users` and no grant | denied |
| DB error on template / user / grant lookup | denied, logged |
| Template row missing for a non-empty `template_slug` | restricted and denied |
| Non-restricted backend | unchanged |

## Testing

- **Unit (`neo4j_access_test.go`):** restricted detection (neo4j runner → true; google runner / empty slug → false; lookup error or missing row → true); `Allows`: admin → true, grant on this server → true, grant on another server → false, no email → false, user lookup error → false, non-restricted backend → true without any lookup; the slug cache avoids a second template lookup within the TTL.
- **Scoped gateway:** for each of the 6 verbs, a restricted backend is omitted / denied for a non-granted user and served for an admin and for a granted user; an unrestricted backend is unaffected.
- **Consent:** HTML and JSON lists hide a restricted server from a non-granted viewer and show it to an admin / granted viewer; a consent POST naming a hidden server does not store it.
- Run in the persistent Go container (`docker exec … go test`), compared against the pre-existing cgo baseline.

## Out of scope

- A generic per-server "grant required" flag and switching HelloData to it (HelloData keeps its own spec).
- `min_role` on template instances.
- Frontend badges / hints for restricted instances.
- REST/UI listings (GET /api/v1/servers incl. include_all, GET /api/v1/servers/{id}, /api/v1/tools|resources|prompts) still list Neo4j instances and tool names to every authenticated web user — names only, no data or calls; follow-up: inject Neo4jAccess into api.Handler and filter these listings / refuse selecting a denied server in token and client forms.
- Reconciling with #807's `min_role` gate: when #807 is merged into poc, both gates sit at the same enforcement points and must be merged into one predicate — a known, mechanical follow-up.
