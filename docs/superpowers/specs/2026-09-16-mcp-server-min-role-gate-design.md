# Design — Per-server `min_role` access gate on the MCP gateway

- **Date:** 2026-09-16
- **Services:** `apps-microservices/mcp-gateway-service`, `apps-microservices/mcp-gateway-frontend`
- **Status:** Approved design — pending implementation plan
- **Author:** Claude (pair) + sandrianirinaharivelo@hellopro.fr
- **Related:** `2026-09-07-mcp-table-service-design.md` (amended by this design — see §8)

## 1. Problem

A registered MCP backend is visible to, and callable by, every authenticated
client. There is no way to say "this backend is for gateway admins only".

The trigger is `mcp-table-service` (spec of 2026-09-07): it exposes full CRUD
over the BDD used-tables registry — the curation layer that decides which
Hellopro MySQL tables and columns any MCP client may read. Handing that to a
non-admin is a privilege-escalation path: a `config-only` user who can call
`add_tables` + `add_fields` grants *themselves* read access to arbitrary
production tables through the separate `bdd` backend.

Two requirements, from the 2026-09-16 brainstorming:

1. A non-admin must not **see** such a server on the OAuth2 consent screen.
2. A non-admin must not be able to **call** it — hiding alone is not a gate.

## 2. What already exists (measured 2026-09-16)

- Roles: `gateway_users.role` ∈ {`admin`, `read-only`, `config-only`},
  with the ladder `auth.RoleLevelFor` (admin=3, read-only=2, config-only=1,
  unknown=0) in `internal/auth/role.go`.
- `mcp_servers` (`internal/db/models.go`) has **no** access-level column.
  Visibility is all-or-nothing per server.
- The OAuth2 consent screen builds its server list in **two** places, both
  starting from `s.serverRepo.ListActive()`:
  - `renderConsent` — `internal/authserver/authorize.go:240` (HTML)
  - `buildServerList` — `internal/authserver/authorize_api.go:424` (JSON)
  Each has a "pre-configured scope" branch (admin-assigned `client.Servers`)
  and a "show everything active" branch.
- `ScopedGateway` resolves an end-user email → role today for the Leexi and
  Ringover auto-self logic: `isGatewayAdmin`, `internal/gateway/scoped_gateway.go:547`.
  It returns `false` when the repo is unwired — permissive, because its caller
  treats "not admin" as "fall through to the configured filter".
- `scopetoken.EndUserEmailContextKey` (`internal/scopetoken/middleware.go:113`)
  is written in **exactly one place**: `internal/oauth2/middleware.go:245`, and
  only when the OAuth2 access token carries a non-empty `email` claim. The
  scope-token middleware never writes it.
- `handleToolsList` (`internal/gateway/scoped_gateway.go:195`) already performs
  **per-viewer backend omission**: `nonZohoAllowedIDs` (`:260`) drops every
  Zoho-tagged backend from the merged registry result when the viewer has no
  Zoho catalog, with the in-code rationale *"Returning the admin catalog by
  fallback would leak admin tools onto a non-admin client."*
- `applyZohoUserState` (`internal/authserver/authorize_api.go:521`) is the
  house pattern for consent-list post-processing: a pure function, unit-tested
  with no `AuthServer` plumbing.
- Frontend routes already carry a `meta.minRole` of `'config-only'` / `'admin'`
  (`mcp-gateway-frontend/src/router/index.ts`). The vocabulary exists; it has
  simply never been applied to a *server*.

## 3. Decisions taken during brainstorming

| Question | Decision |
|---|---|
| Enforcement depth | **Hide *and* hard-deny**, and additionally refuse `mcp_…` scope tokens outright. Hiding the consent entry is defeatable: an admin can pre-assign the server into an OAuth2 client's scope, a consent granted while the user was admin survives a demotion, and scope tokens never traverse `/authorize` at all. |
| Mechanism | **`min_role` column on `mcp_servers`**, reusing `auth.RoleLevelFor`. Chosen over a single-purpose `admin_only` boolean (cannot express "read-only and above" later) and over sniffing a tag / `tool_prefix` (the rule would live in magic strings, and an operator could ungate a server by editing a tag). |
| Admin UI | **Editable** — a "Niveau d'accès requis" select on the server create/edit form, admin-visible only, plus a badge in the server list. Without it the only way to gate a server is a manual `PATCH`, which will not be discovered. |
| Caching of the role lookup | **None.** One indexed query on `gateway_users` per request, exactly as `isGatewayAdmin` already does. A TTL cache would let a demoted admin keep access for the cache window. |

## 4. Goals / Non-goals

**Goals**
- One `min_role` column, default `''` (public) so **every existing server keeps
  today's behaviour** with no migration step beyond the column add.
- Four enforcement points (§5.3) sharing **one** predicate.
- Fail-closed at every branch, including an unwired repository.
- `min_role` editable from the admin UI by admins, visible as a badge.

**Non-goals**
- No change to `isAdminOnly` / `isReadOnlyPlus` in `internal/api/handler.go`.
  The browser admin API keeps its current role model; `read-only` users keep
  read access to the Tables BDD pages. This design gates the **MCP surface**,
  not the admin REST API. Conflating the two would silently change the admin
  UI, which was not requested.
- No per-*tool* role gating. Granularity is the server. Admins already have
  per-tool scoping on tokens and OAuth2 clients.
- No retroactive gating: no existing server's `min_role` is set by this work.
  `mcp-table-service` is the first consumer, and it sets its own at
  registration time.

## 5. Architecture

### 5.1 Schema

`internal/db/models.go`, on `MCPServer`:

```go
// MinRole is the minimum gateway_users.role required to see this server on
// the OAuth2 consent screen and to reach its tools. Empty = public.
MinRole string `gorm:"type:varchar(20);not null;default:''" json:"min_role"`
```

Accepted values: `''`, `config-only`, `read-only`, `admin`. Any other string is
**rejected on write** in the DTO layer (`internal/api/dto.go`) — an unknown
value must never be silently coerced to public. GORM auto-migration adds the
column; `init-db/init-mcp-gateway-db.sql` gains the matching DDL.

### 5.2 The predicate

One exported helper in `internal/gateway`, used by all four call sites:

```go
// GateAllows reports whether the caller behind ctx may see or reach srv.
// Fail-closed: every uncertain branch denies.
func GateAllows(srv db.MCPServer, ctx context.Context, users GatewayUserRepo) bool {
    if srv.MinRole == "" {
        return true // public — the path every existing server takes
    }
    if users == nil {
        return false // unwired repo ⇒ deny (see note below)
    }
    email, ok := scopetoken.EndUserEmailFromContext(ctx)
    if !ok || email == "" {
        return false // scope token, or client_credentials grant
    }
    u, err := users.GetByEmail(email)
    if err != nil || u == nil {
        return false
    }
    return auth.RoleLevelFor(u.Role) >= auth.RoleLevelFor(srv.MinRole)
}
```

Two properties worth naming, because both are load-bearing:

- **The email check is the scope-token exclusion.** Because
  `EndUserEmailContextKey` is written only on the OAuth2 bearer path and only
  for a non-empty `email` claim (§2), "there is an end-user email on this
  context" is already an exact proxy for "an authorization-code token with a
  real human behind it". It excludes `mcp_…` scope tokens *and*
  `client_credentials` grants in a single condition. This is an implicit
  coupling, so it is pinned by a regression test (§7) asserting the
  scope-token path leaves the key unset — not by a comment.
- **The `users == nil` branch inverts the existing convention.** `isGatewayAdmin`
  returns `false` when unwired and its callers read that as "not admin, use the
  configured filter" — permissive by design. Here "unknown" must mean "denied".
  To avoid two lookups with opposite failure semantics, `isGatewayAdmin` is
  refactored into `gatewayUserRole(email) (string, bool)` with `isGatewayAdmin`
  kept as a one-line wrapper, so Leexi/Ringover behaviour is provably unchanged.

### 5.3 The four enforcement points

| # | Site | Behaviour when `GateAllows` is false |
|---|---|---|
| 1 | `renderConsent` — `authorize.go:240` | server dropped from the HTML list |
| 2 | `buildServerList` — `authorize_api.go:424` | server dropped from the JSON list |
| 3 | `handleToolsList` — `scoped_gateway.go:195` | the server's tools are omitted |
| 4 | `handleToolsCall` — `scoped_gateway.go:348` | explicit MCP error |

(3) without (4) is not a gate: a client can call a tool name it learned from an
earlier, more privileged `tools/list`, or one a human read from the docs.

For (1) and (2), the filter is applied **immediately after the shared
`ListActive()` call**, through one pure helper:

```go
func FilterServersByGate(servers []db.MCPServer, ctx context.Context, users GatewayUserRepo) []db.MCPServer
```

Filtering at that seam covers **both** branches of both functions for free: the
pre-configured-scope branch resolves `client.Servers` through `serverMap`, which
is built from the filtered slice, so an admin-assigned gated server simply drops
out for a non-admin viewer rather than erroring the whole consent flow. A pure
function keeps it unit-testable with no `AuthServer` plumbing, matching
`applyZohoUserState` — which matters here because the Zoho logic already had to
be written twice across these two files, and a third divergent copy is the
predictable failure mode.

For (3), the mechanism already exists: build the allowed-id set minus the gated
backends, exactly as `nonZohoAllowedIDs` does for Zoho.

Every denial at (4) is logged with the email, the server id and the required
role. Denials at (1)–(3) are not logged per-request (they are the normal steady
state for every non-admin browsing the consent screen and would be pure noise).

### 5.4 Frontend (`mcp-gateway-frontend`)

- `min_role` added to the server TypeScript type and the API layer.
- A "Niveau d'accès requis" `<select>` on the server create/edit form
  (Public / config-only / read-only / admin), rendered only when the session
  role is `admin`.
- A badge on the server list/detail row when `min_role !== ''`.

## 6. Interaction with `mcp-table-service`

This gate is what makes that service admin-only, and it does so **without any
change to the act-as branch or to `isAdminOnly`**: its `mcp_servers` row is
registered with `min_role = 'admin'`, so a non-admin never reaches the service
at all. The two tools that spec assigned to `read-only`
(`list_registered_tables`, `get_table_info`) become unreachable for non-admins
as a consequence of the server-level gate, not through per-tool logic.

See §8 for the amendments this implies in the 2026-09-07 spec.

## 7. Testing

**`internal/gateway`**
- `GateAllows`: public server with no email → allow; gated + no email (scope
  token) → deny; gated + email with role below → deny; gated + email with role
  equal and above → allow; gated + unknown email → deny; gated + nil repo →
  deny; gated + repo error → deny.
- `FilterServersByGate`: mixed public/gated slice for admin, read-only and
  anonymous viewers; empty input; all-gated input.
- `handleToolsList`: gated backend's tools absent for a non-admin, present for
  an admin; Zoho behaviour unchanged (existing tests must stay green).
- `handleToolsCall`: gated backend returns an MCP error for a non-admin.
- **Regression pin:** the scope-token middleware path leaves
  `EndUserEmailContextKey` unset — the assumption §5.2 depends on.
- `isGatewayAdmin` returns identical results before and after the
  `gatewayUserRole` refactor (table test over the same inputs).

**`internal/authserver`**
- `renderConsent` and `buildServerList` each omit a gated server for a
  non-admin and keep it for an admin, in **both** the pre-configured-scope and
  the show-all branches.

**`internal/api`**
- `min_role` round-trips through POST/PUT/GET on `/api/v1/servers`.
- An invalid `min_role` string is rejected with 400.

**`mcp-gateway-frontend`**: router/store test that the select renders for an
admin session and not for a non-admin.

**Commands:** `go vet ./... && go build ./... && go test ./...` in
`mcp-gateway-service`; `npm run test` in `mcp-gateway-frontend`.

## 8. Amendments to `2026-09-07-mcp-table-service-design.md`

That spec is kept — its 13 tools, tool prefix `tables`, port 8597 and act-as
auth path all remain correct. Two of its statements are superseded:

1. **§3, "Privilege model" row** — role-mirroring (admin = all, `read-only` =
   list/get, `config-only` = denied) becomes **admin-only**, enforced by this
   gate at the server level. The act-as branch itself is unchanged: it resolves
   whatever role the user holds; the gate decides reachability.
2. **§4, non-goal "No per-role hiding in `tools/list`"** — struck. Its stated
   reason ("the gateway serves the cached discovery catalog … so hiding would
   not reach the client") is incorrect: `handleToolsList` already drops whole
   backends per viewer via `nonZohoAllowedIDs` (§2). The cache is the *source*
   of tool data; the *scope* is resolved per request.

Consequential edits in `docs/superpowers/plans/2026-09-07-mcp-table-service.md`:
the two read-only tool descriptions and their 403-message test expectations move
from `read-only` to `admin`, and the acceptance scenario that asserts a
read-only user can call `list_registered_tables` is replaced by one asserting a
read-only user cannot reach the server at all. No task is added or removed.

## 9. Documentation

- `apps-microservices/mcp-gateway-service/CLAUDE.md`: add `min_role` to the
  `mcp_servers` description, a convention bullet describing the gate and its
  four enforcement points, and the new test file names.
- Same file, line 195: fix the documented Slack/log tag `auth_source=…` — the
  code emits `source=%s` (`internal/scopetoken/middleware.go:243,352`). Drift
  found while working here, corrected here, per the repo's per-service rule.
- `apps-microservices/mcp-gateway-frontend/CLAUDE.md`: the new form control.

## 10. Acceptance

1. `go vet`, `go build`, `go test` clean in `mcp-gateway-service`;
   `npm run test` clean in `mcp-gateway-frontend`.
2. A server with `min_role=''` behaves exactly as before at all four points
   (regression: the existing consent and tools/list tests stay green untouched).
3. With a server at `min_role='admin'`: an admin OAuth2 session sees it on the
   consent screen and in `tools/list` and can call its tools; a `read-only`
   session sees it in neither and gets an MCP error on a direct `tools/call`.
4. A `mcp_…` scope token scoped to that server gets an MCP error on
   `tools/call` and does not see its tools in `tools/list`, regardless of the
   token owner's role.
5. A `client_credentials` grant is denied on the same server.
6. `POST /api/v1/servers` with `min_role: "wizard"` returns 400.
