# Per-server `min_role` Access Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `min_role` column to `mcp_servers` so a registered MCP backend can be restricted to gateway users at or above a given role — hidden on the OAuth2 consent screen and unreachable through `tools/list` / `tools/call` for everyone else, including all scope tokens and `client_credentials` grants.

**Architecture:** One fail-closed predicate (`GateAllowsEmail`) in `internal/gateway`, reached through two thin wrappers: a context-based one for the MCP runtime (where "has an end-user email on the context" is also what excludes scope tokens) and an email-based one for the consent screen (where the viewer's email is a function parameter, not context). Four call sites consume it: the two consent-list builders and the two `ScopedGateway` MCP handlers. The registry gains a `MinRole` field echoed from the DB row, following the existing `TemplateSlug` / `CreatedBy` / `Tags` precedent.

**Tech Stack:** Go 1.24 (stdlib `net/http`, GORM v1.25, MySQL) for `mcp-gateway-service`; Vue 3 + TypeScript + Vitest + Tailwind for `mcp-gateway-frontend`.

**Spec:** `docs/superpowers/specs/2026-09-16-mcp-server-min-role-gate-design.md`

## Global Constraints

- Accepted `min_role` values, exactly: `""` (public), `"config-only"`, `"read-only"`, `"admin"`. Any other string is rejected with HTTP 400 on write — never coerced to public.
- Column default is `''`, so **every existing server keeps today's behaviour**. No data migration sets `min_role` on any existing row.
- The predicate is **fail-closed**: nil repository, missing email, unknown email, repository error, and role-below-threshold all deny.
- `internal/api/handler.go` `isAdminOnly` / `isReadOnlyPlus` are **not** modified. This gate covers the MCP surface only; the browser admin REST API keeps its current role model.
- Granularity is the **server**, never the tool.
- Go formatting: `gofmt -l .` must print nothing before each commit.
- Every Go task ends with `go vet ./... && go build ./... && go test ./...` green in `apps-microservices/mcp-gateway-service`.
- Frontend tasks end with `npm run test` green in `apps-microservices/mcp-gateway-frontend`.
- Commit messages: Conventional Commits, English subject, body carrying an `EN:` line and an `FR:` line. Stage with explicit paths.
- The repo's PreToolUse secret scanner scans all untracked files whenever a command contains `git add`. If it blocks on unrelated untracked caches, stage with `git update-index --add <paths>` then `git commit`.

---

## File Structure

**`apps-microservices/mcp-gateway-service`**

| File | Responsibility |
|---|---|
| `internal/db/models.go` | `MCPServer.MinRole` column (modify) |
| `init-db/init-mcp-gateway-db.sql` | matching DDL (modify) |
| `internal/api/dto.go` | `min_role` on create / update / response DTOs (modify) |
| `internal/api/server_handlers.go` | validate + persist `min_role` (modify) |
| `internal/gateway/access_gate.go` | **new** — `GateAllowsEmail`, `GateAllows`, `FilterServersByGate`, `gatewayUserRole` |
| `internal/gateway/access_gate_test.go` | **new** — predicate + filter unit tests |
| `internal/gateway/registry.go` | `BackendServer.MinRole` + `SetMinRole` (modify) |
| `internal/gateway/gateway.go` | preserve `MinRole` across rediscovery (modify) |
| `internal/app/app.go` | populate `MinRole` from the DB row; wire `UserRepo` into `AuthServer` (modify) |
| `internal/gateway/scoped_gateway.go` | `gatedOutIDs`, enforcement in `handleToolsList` / `handleToolsCall`; `isGatewayAdmin` → `gatewayUserRole` (modify) |
| `internal/gateway/scoped_gateway_gate_test.go` | **new** — runtime enforcement tests |
| `internal/authserver/handler.go` | `userRepo` field + config (modify) |
| `internal/authserver/authorize.go` | filter in `renderConsent` (modify) |
| `internal/authserver/authorize_api.go` | filter in `buildServerList` (modify) |
| `internal/authserver/consent_gate_test.go` | **new** — consent filtering tests |

**`apps-microservices/mcp-gateway-frontend`**

| File | Responsibility |
|---|---|
| `src/types/server.ts` | `min_role` on `Server` / `CreateServerRequest` (modify) |
| `src/views/ServerFormView.vue` | admin-only "Niveau d'accès requis" select (modify) |
| `src/components/servers/ServerCard.vue` | gate badge (modify) |
| `src/views/ServerFormView.spec.ts` | **new** — select visibility by role |

---

## Task 1: `min_role` column, DTO and REST round-trip

**Files:**
- Modify: `internal/db/models.go` (`MCPServer`)
- Modify: `init-db/init-mcp-gateway-db.sql`
- Modify: `internal/api/dto.go`
- Modify: `internal/api/server_handlers.go`
- Test: `internal/api/min_role_dto_test.go` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `db.MCPServer.MinRole string`; `api.ValidMinRole(s string) bool`; JSON field `min_role` on `CreateServerRequest`, `UpdateServerRequest` (`*string`), `ServerResponse`.

- [ ] **Step 1: Write the failing test**

Create `internal/api/min_role_dto_test.go`:

```go
package api

import "testing"

func TestValidMinRole(t *testing.T) {
	valid := []string{"", "config-only", "read-only", "admin"}
	for _, v := range valid {
		if !ValidMinRole(v) {
			t.Fatalf("ValidMinRole(%q) = false, want true", v)
		}
	}
	invalid := []string{"wizard", "Admin", "ADMIN", "readonly", "read_only", " admin", "admin "}
	for _, v := range invalid {
		if ValidMinRole(v) {
			t.Fatalf("ValidMinRole(%q) = true, want false", v)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestValidMinRole`
Expected: FAIL — `undefined: ValidMinRole`

- [ ] **Step 3: Add the validator**

Append to `internal/api/dto.go`:

```go
// ValidMinRole reports whether s is an accepted mcp_servers.min_role value.
// Empty means "public". Comparison is exact: an unknown or differently-cased
// string must be rejected, never coerced to public.
func ValidMinRole(s string) bool {
	switch s {
	case "", auth.RoleConfigOnly, auth.RoleReadOnly, auth.RoleAdmin:
		return true
	default:
		return false
	}
}
```

Add `"mcp-gateway/internal/auth"` to that file's imports if absent.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestValidMinRole`
Expected: PASS

- [ ] **Step 5: Add the column to the model**

In `internal/db/models.go`, inside `type MCPServer struct`, directly after the `Icon` field:

```go
	// MinRole is the minimum gateway_users.role required to see this server
	// on the OAuth2 consent screen and to reach its tools over MCP. Empty
	// means public — the value every pre-existing server carries.
	MinRole string `gorm:"type:varchar(20);not null;default:''" json:"min_role"`
```

- [ ] **Step 6: Add the matching DDL**

In `init-db/init-mcp-gateway-db.sql`, in the `mcp_servers` `CREATE TABLE`, after the `icon` column:

```sql
  min_role VARCHAR(20) NOT NULL DEFAULT '',
```

- [ ] **Step 7: Add the DTO fields**

In `internal/api/dto.go`:

- `CreateServerRequest`, after `ToolPrefix`:
  ```go
  	MinRole             string            `json:"min_role,omitempty"`
  ```
- `UpdateServerRequest`, after `ToolPrefix`:
  ```go
  	MinRole             *string           `json:"min_role,omitempty"`
  ```
- `ServerResponse`, after `ToolPrefix`:
  ```go
  	MinRole             string            `json:"min_role"`
  ```

- [ ] **Step 8: Wire validation and persistence**

In `internal/api/server_handlers.go`:

- In the create handler, after the existing `ToolPrefix` validation and before the row is built:
  ```go
  	if !ValidMinRole(req.MinRole) {
  		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "min_role must be one of: \"\", config-only, read-only, admin"})
  		return
  	}
  ```
  and set `MinRole: req.MinRole` on the `db.MCPServer` literal.
- In the update handler, alongside the other `*string` fields:
  ```go
  	if req.MinRole != nil {
  		if !ValidMinRole(*req.MinRole) {
  			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "min_role must be one of: \"\", config-only, read-only, admin"})
  			return
  		}
  		srv.MinRole = *req.MinRole
  	}
  ```
- In the function that builds `ServerResponse` from a `db.MCPServer`, add `MinRole: srv.MinRole`.

- [ ] **Step 9: Run the full service test suite**

Run: `cd apps-microservices/mcp-gateway-service && gofmt -l . && go vet ./... && go build ./... && go test ./...`
Expected: no gofmt output, all PASS

- [ ] **Step 10: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/db/models.go \
        apps-microservices/mcp-gateway-service/init-db/init-mcp-gateway-db.sql \
        apps-microservices/mcp-gateway-service/internal/api/dto.go \
        apps-microservices/mcp-gateway-service/internal/api/server_handlers.go \
        apps-microservices/mcp-gateway-service/internal/api/min_role_dto_test.go
git commit -m "feat(mcp-gateway-service): add min_role column to mcp_servers

EN: mcp_servers.min_role (default '' = public) with strict validation on the
server create/update REST routes and exposure on the server response DTO.
FR: mcp_servers.min_role (defaut '' = public) avec validation stricte sur les
routes REST de creation/modification et exposition dans le DTO de reponse."
```

---

## Task 2: The fail-closed predicate

**Files:**
- Create: `internal/gateway/access_gate.go`
- Create: `internal/gateway/access_gate_test.go`
- Modify: `internal/gateway/scoped_gateway.go:547` (`isGatewayAdmin`)

**Interfaces:**
- Consumes: `gatewayUserFinder` (`internal/gateway/scoped_gateway.go:23`), `auth.RoleLevelFor`, `scopetoken.EndUserEmailFromContext`, `db.MCPServer`, `db.GatewayUser`.
- Produces:
  - `func GateAllowsEmail(minRole, email string, users gatewayUserFinder) bool`
  - `func GateAllows(minRole string, ctx context.Context, users gatewayUserFinder) bool`
  - `func FilterServersByGate(servers []db.MCPServer, email string, users gatewayUserFinder) []db.MCPServer`
  - `func gatewayUserRole(users gatewayUserFinder, email string) (string, bool)`

> **Refinement of spec §5.2.** The spec sketched a single context-based
> predicate. The consent screen does not have the viewer on a context — it
> receives `userEmail string` as a parameter (`renderConsent`,
> `buildServerList`). So the core predicate takes an email, and the
> context-based form is a thin wrapper whose *only* extra job is extracting
> the email — which is exactly what makes it reject scope tokens and
> `client_credentials`. Same semantics, two entry points, one implementation.

- [ ] **Step 1: Write the failing test**

Create `internal/gateway/access_gate_test.go`:

```go
package gateway

import (
	"context"
	"errors"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// fakeUsers is an in-memory gatewayUserFinder: email -> role.
type fakeUsers map[string]string

func (f fakeUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	role, ok := f[email]
	if !ok {
		return nil, nil
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

// errUsers always fails, standing in for a DB outage.
type errUsers struct{}

func (errUsers) GetByEmail(string) (*db.GatewayUser, error) {
	return nil, errors.New("db down")
}

func TestGateAllowsEmail(t *testing.T) {
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
		"cfg@hellopro.fr":   auth.RoleConfigOnly,
	}

	cases := []struct {
		name    string
		minRole string
		email   string
		users   gatewayUserFinder
		want    bool
	}{
		{"public server, no email at all", "", "", users, true},
		{"public server, unknown email", "", "ghost@hellopro.fr", users, true},
		{"public server, nil repo", "", "", nil, true},
		{"gated admin, admin user", auth.RoleAdmin, "admin@hellopro.fr", users, true},
		{"gated admin, read-only user", auth.RoleAdmin, "ro@hellopro.fr", users, false},
		{"gated admin, config-only user", auth.RoleAdmin, "cfg@hellopro.fr", users, false},
		{"gated admin, unknown email", auth.RoleAdmin, "ghost@hellopro.fr", users, false},
		{"gated admin, empty email", auth.RoleAdmin, "", users, false},
		{"gated admin, nil repo", auth.RoleAdmin, "admin@hellopro.fr", nil, false},
		{"gated admin, repo error", auth.RoleAdmin, "admin@hellopro.fr", errUsers{}, false},
		{"gated read-only, admin user passes ladder", auth.RoleReadOnly, "admin@hellopro.fr", users, true},
		{"gated read-only, read-only user", auth.RoleReadOnly, "ro@hellopro.fr", users, true},
		{"gated read-only, config-only user", auth.RoleReadOnly, "cfg@hellopro.fr", users, false},
		{"gated config-only, config-only user", auth.RoleConfigOnly, "cfg@hellopro.fr", users, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := GateAllowsEmail(tc.minRole, tc.email, tc.users); got != tc.want {
				t.Fatalf("GateAllowsEmail(%q, %q) = %v, want %v", tc.minRole, tc.email, got, tc.want)
			}
		})
	}
}

func TestGateAllows_ContextForm(t *testing.T) {
	users := fakeUsers{"admin@hellopro.fr": auth.RoleAdmin}

	// No email on the context — this is what a scope token and a
	// client_credentials grant both look like. Gated servers must deny.
	bare := context.Background()
	if GateAllows(auth.RoleAdmin, bare, users) {
		t.Fatal("gated server allowed with no end-user email on context")
	}
	if !GateAllows("", bare, users) {
		t.Fatal("public server denied with no end-user email on context")
	}

	withAdmin := context.WithValue(bare, scopetoken.EndUserEmailContextKey, "admin@hellopro.fr")
	if !GateAllows(auth.RoleAdmin, withAdmin, users) {
		t.Fatal("gated server denied for an admin end user")
	}

	// An empty-string email on the context must not pass as an identity.
	withEmpty := context.WithValue(bare, scopetoken.EndUserEmailContextKey, "")
	if GateAllows(auth.RoleAdmin, withEmpty, users) {
		t.Fatal("gated server allowed with an empty email on context")
	}
}

func TestFilterServersByGate(t *testing.T) {
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
	}
	servers := []db.MCPServer{
		{ID: "pub-1", MinRole: ""},
		{ID: "gated-1", MinRole: auth.RoleAdmin},
		{ID: "pub-2", MinRole: ""},
	}

	ids := func(in []db.MCPServer) []string {
		out := make([]string, 0, len(in))
		for _, s := range in {
			out = append(out, s.ID)
		}
		return out
	}

	got := ids(FilterServersByGate(servers, "admin@hellopro.fr", users))
	if len(got) != 3 {
		t.Fatalf("admin sees %v, want all three", got)
	}

	got = ids(FilterServersByGate(servers, "ro@hellopro.fr", users))
	if len(got) != 2 || got[0] != "pub-1" || got[1] != "pub-2" {
		t.Fatalf("read-only sees %v, want [pub-1 pub-2]", got)
	}

	got = ids(FilterServersByGate(servers, "", users))
	if len(got) != 2 {
		t.Fatalf("anonymous sees %v, want the two public servers", got)
	}

	if out := FilterServersByGate(nil, "admin@hellopro.fr", users); len(out) != 0 {
		t.Fatalf("nil input produced %v", out)
	}

	allGated := []db.MCPServer{{ID: "g1", MinRole: auth.RoleAdmin}}
	if out := FilterServersByGate(allGated, "ro@hellopro.fr", users); len(out) != 0 {
		t.Fatalf("all-gated input produced %v for a read-only viewer", out)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run 'TestGate|TestFilterServers'`
Expected: FAIL — `undefined: GateAllowsEmail`

- [ ] **Step 3: Write the implementation**

Create `internal/gateway/access_gate.go`:

```go
package gateway

import (
	"context"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// gatewayUserRole resolves email to its gateway_users role.
//
// The bool reports whether the lookup produced a usable answer: false covers
// an unwired repository, a repository error, and an email with no row. It is
// deliberately distinct from "role is low" so callers can fail closed on
// uncertainty rather than treating an outage as a valid low-privilege answer.
func gatewayUserRole(users gatewayUserFinder, email string) (string, bool) {
	if users == nil || email == "" {
		return "", false
	}
	u, err := users.GetByEmail(email)
	if err != nil || u == nil {
		return "", false
	}
	return u.Role, true
}

// GateAllowsEmail reports whether the gateway user identified by email may
// see and reach a server whose mcp_servers.min_role is minRole.
//
// Fail-closed: an empty minRole is the only path that allows without a
// successful role resolution. Everything uncertain — no repository, no email,
// unknown email, repository error — denies.
func GateAllowsEmail(minRole, email string, users gatewayUserFinder) bool {
	if minRole == "" {
		return true // public: the value every pre-existing server carries
	}
	role, ok := gatewayUserRole(users, email)
	if !ok {
		return false
	}
	return auth.RoleLevelFor(role) >= auth.RoleLevelFor(minRole)
}

// GateAllows is the MCP-runtime form of GateAllowsEmail. It reads the
// end-user email from ctx, which is set in exactly one place —
// internal/oauth2/middleware.go, on the OAuth2 bearer path, and only when the
// access token carries a non-empty email claim.
//
// That single fact is what makes this function reject `mcp_…` scope tokens
// and client_credentials grants on a gated server: neither ever puts an email
// on the context. The invariant is pinned by
// TestScopeTokenPathLeavesEndUserEmailUnset — if that test ever fails, this
// gate has silently opened.
func GateAllows(minRole string, ctx context.Context, users gatewayUserFinder) bool {
	if minRole == "" {
		return true
	}
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return false
	}
	return GateAllowsEmail(minRole, email, users)
}

// FilterServersByGate returns the subset of servers that email may see.
// Pure: no receiver, no I/O beyond the injected finder, so the consent-screen
// call sites stay unit-testable without any AuthServer plumbing — the same
// discipline as applyZohoUserState.
func FilterServersByGate(servers []db.MCPServer, email string, users gatewayUserFinder) []db.MCPServer {
	out := make([]db.MCPServer, 0, len(servers))
	for _, s := range servers {
		if GateAllowsEmail(s.MinRole, email, users) {
			out = append(out, s)
		}
	}
	return out
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run 'TestGate|TestFilterServers' -v`
Expected: PASS

- [ ] **Step 5: Refactor `isGatewayAdmin` onto the shared lookup**

Replace the body of `isGatewayAdmin` in `internal/gateway/scoped_gateway.go` (currently at `:547`) with:

```go
// isGatewayAdmin returns true when the email belongs to a gateway_users row
// with Role=admin. Returns false when the repo isn't configured, the row is
// missing, or the role is anything else.
//
// Note the asymmetry with the access gate: here false means "not an admin, so
// fall through to the admin-configured filter" — permissive by design for the
// Leexi/Ringover auto-self override. GateAllowsEmail treats the same
// uncertainty as a denial. Both share gatewayUserRole; only the reading of a
// failed lookup differs.
func (sg *ScopedGateway) isGatewayAdmin(email string) bool {
	role, ok := gatewayUserRole(sg.gatewayUsers, email)
	return ok && role == auth.RoleAdmin
}
```

- [ ] **Step 6: Prove the refactor changed nothing**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run 'AutoSelf|Leexi|Ringover' -v`
Expected: PASS — every pre-existing auto-self test still green

- [ ] **Step 7: Pin the scope-token invariant**

Append to `internal/gateway/access_gate_test.go`:

```go
// TestScopeTokenPathLeavesEndUserEmailUnset pins the invariant GateAllows
// depends on: only the OAuth2 bearer path writes EndUserEmailContextKey. If a
// future feature starts attaching an owner email to scope-token requests,
// this test fails — and it must, because the gate would otherwise open for
// machine tokens without anyone noticing.
func TestScopeTokenPathLeavesEndUserEmailUnset(t *testing.T) {
	root := "../../internal/scopetoken"
	entries, err := os.ReadDir(root)
	if err != nil {
		t.Fatalf("read %s: %v", root, err)
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".go") || strings.HasSuffix(e.Name(), "_test.go") {
			continue
		}
		src, err := os.ReadFile(filepath.Join(root, e.Name()))
		if err != nil {
			t.Fatalf("read %s: %v", e.Name(), err)
		}
		if strings.Contains(string(src), "context.WithValue(ctx, EndUserEmailContextKey") {
			t.Fatalf("%s writes EndUserEmailContextKey: the scope-token path must never carry an end-user identity, or gateway.GateAllows silently stops excluding scope tokens", e.Name())
		}
	}
}
```

Add `"os"`, `"path/filepath"` and `"strings"` to that file's imports.

- [ ] **Step 8: Run it**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestScopeTokenPath -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/access_gate.go \
        apps-microservices/mcp-gateway-service/internal/gateway/access_gate_test.go \
        apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go
git commit -m "feat(mcp-gateway-service): add fail-closed min_role access predicate

EN: GateAllowsEmail / GateAllows / FilterServersByGate deny on nil repo,
missing or unknown email and repo error; isGatewayAdmin now shares the same
lookup; a regression test pins that the scope-token path carries no identity.
FR: GateAllowsEmail / GateAllows / FilterServersByGate refusent en cas de repo
absent, email manquant ou inconnu et erreur de repo ; isGatewayAdmin partage
desormais la meme resolution ; un test de regression fige l'absence d'identite
sur le chemin scope-token."
```

---

## Task 3: Carry `MinRole` onto the in-memory registry

**Files:**
- Modify: `internal/gateway/registry.go` (`BackendServer`, new `SetMinRole`)
- Modify: `internal/gateway/gateway.go:164-178` (rediscovery preservation)
- Modify: `internal/app/app.go` (`registerFromDBCache`)
- Modify: `internal/api/server_handlers.go` (push edits into the registry)
- Test: `internal/gateway/registry_min_role_test.go` (create)

**Interfaces:**
- Consumes: `db.MCPServer.MinRole` (Task 1).
- Produces: `BackendServer.MinRole string`; `func (r *Registry) SetMinRole(id, minRole string)`.

> **Why this task exists.** `handleToolsList` and `handleToolsCall` work with
> `*BackendServer` from the in-memory registry, not with `db.MCPServer`. The
> gate is unenforceable at runtime until `MinRole` reaches that struct. The
> health checker re-discovers backends on a 30 s loop and rebuilds
> `BackendServer` from the upstream `initialize` result, which knows nothing
> about `min_role` — so without the preservation block below, **the gate would
> silently fall open within 30 seconds of boot.** That is the single most
> dangerous failure mode in this plan, and Step 1 tests for it directly.

- [ ] **Step 1: Write the failing test**

Create `internal/gateway/registry_min_role_test.go`:

```go
package gateway

import (
	"testing"

	"mcp-gateway/internal/auth"
)

func TestRegistry_SetMinRole(t *testing.T) {
	r := NewRegistry()
	r.Register(&BackendServer{ID: "srv-1"})

	r.SetMinRole("srv-1", auth.RoleAdmin)
	if got := r.FindByID("srv-1").MinRole; got != auth.RoleAdmin {
		t.Fatalf("MinRole = %q, want %q", got, auth.RoleAdmin)
	}

	r.SetMinRole("srv-1", "")
	if got := r.FindByID("srv-1").MinRole; got != "" {
		t.Fatalf("MinRole = %q, want empty after ungating", got)
	}

	// Must not panic for an unknown id.
	r.SetMinRole("nope", auth.RoleAdmin)
}

// TestRegistry_MinRoleSurvivesRediscovery guards the highest-consequence
// regression in this feature: the health checker rebuilds BackendServer from
// the upstream initialize result every 30 s. If MinRole is not carried over,
// a gated server silently becomes public shortly after boot.
func TestRegistry_MinRoleSurvivesRediscovery(t *testing.T) {
	r := NewRegistry()
	r.Register(&BackendServer{ID: "srv-1", MinRole: auth.RoleAdmin, Name: "old"})

	// Simulate what registerBackend builds from a fresh initialize result:
	// a struct that knows nothing about min_role.
	fresh := &BackendServer{ID: "srv-1", Name: "new"}
	if prev := r.FindByID("srv-1"); prev != nil && fresh.MinRole == "" {
		fresh.MinRole = prev.MinRole
	}
	r.Register(fresh)

	if got := r.FindByID("srv-1").MinRole; got != auth.RoleAdmin {
		t.Fatalf("MinRole = %q after rediscovery, want %q — the gate fell open", got, auth.RoleAdmin)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestRegistry_MinRole`
Expected: FAIL — `unknown field MinRole` / `r.SetMinRole undefined`

- [ ] **Step 3: Add the field and the setter**

In `internal/gateway/registry.go`, in `type BackendServer struct`, after the `CreatedBy` field:

```go
	// MinRole echoes mcp_servers.min_role. Empty means public. Read by the
	// access gate to decide whether this backend is visible and reachable
	// for the caller behind the current request.
	MinRole string
```

And after `SetTags`:

```go
// SetMinRole updates the access gate level for a registered backend server.
// Used by the PUT /servers/{id} handler so a min_role edit takes effect
// without waiting for a re-discovery cycle.
func (r *Registry) SetMinRole(id, minRole string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if s, ok := r.servers[id]; ok {
		s.MinRole = minRole
		log.Printf("[registry] SetMinRole id=%s min_role=%q", id, minRole)
	} else {
		log.Printf("[registry] SetMinRole id=%s min_role=%q — backend NOT in registry", id, minRole)
	}
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestRegistry_MinRole -v`
Expected: PASS

- [ ] **Step 5: Preserve across rediscovery**

In `internal/gateway/gateway.go`, inside the existing `if prev := g.registry.FindByID(id); prev != nil {` block, after the `ToolPrefix` clause:

```go
		if srv.MinRole == "" {
			srv.MinRole = prev.MinRole
		}
```

Update that block's leading comment to name the field:

```go
	// Preserve metadata that lives on the registry but wasn't fetched from
	// the upstream init result: TemplateSlug, CreatedBy, Tags, ToolPrefix,
	// MinRole. Health-checker re-discovery would otherwise wipe them every
	// probe cycle — for MinRole that would silently un-gate the backend.
```

- [ ] **Step 6: Populate from the DB cache**

In `internal/app/app.go`, in `registerFromDBCache`, in the `&gateway.BackendServer{...}` literal, after `CreatedBy: srv.CreatedBy,`:

```go
		MinRole:       srv.MinRole,
```

- [ ] **Step 7: Push edits from the update handler**

In `internal/api/server_handlers.go`, in the update handler, next to the existing `SetToolPrefix` / `SetTags` registry calls, add:

```go
	if h.registry != nil {
		h.registry.SetMinRole(srv.ID, srv.MinRole)
	}
```

Match the surrounding nil-guard style; if the neighbouring calls use a different receiver name for the registry, use that one.

- [ ] **Step 8: Run the full service suite**

Run: `cd apps-microservices/mcp-gateway-service && gofmt -l . && go vet ./... && go build ./... && go test ./...`
Expected: no gofmt output, all PASS

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/registry.go \
        apps-microservices/mcp-gateway-service/internal/gateway/registry_min_role_test.go \
        apps-microservices/mcp-gateway-service/internal/gateway/gateway.go \
        apps-microservices/mcp-gateway-service/internal/app/app.go \
        apps-microservices/mcp-gateway-service/internal/api/server_handlers.go
git commit -m "feat(mcp-gateway-service): carry min_role onto the backend registry

EN: BackendServer.MinRole populated from the DB cache, preserved across
health-checker re-discovery and updated live by PUT /servers/{id}.
FR: BackendServer.MinRole alimente depuis le cache DB, conserve lors de la
re-decouverte par le health-checker et mis a jour a chaud par PUT /servers/{id}."
```

---

## Task 4: Runtime enforcement — `tools/list` and `tools/call`

**Files:**
- Modify: `internal/gateway/scoped_gateway.go` (`handleToolsList:195`, `handleToolsCall:348`, new `gatedOutIDs`)
- Test: `internal/gateway/scoped_gateway_gate_test.go` (create)

**Interfaces:**
- Consumes: `GateAllows` (Task 2), `BackendServer.MinRole` (Task 3), `Registry.All`, `Registry.FindByID`, `sg.allowedIDs`.
- Produces: `func (sg *ScopedGateway) gatedOutIDs(ctx context.Context) map[string]bool`.

> `tools/list` omission alone is not a gate. A client can call a tool name it
> learned from an earlier, more privileged `tools/list`, from the docs pages,
> or from a colleague. Both handlers must enforce.

- [ ] **Step 1: Write the failing test**

Create `internal/gateway/scoped_gateway_gate_test.go`:

```go
package gateway

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/scopetoken"
)

// newGateTestGateway builds a ScopedGateway over one public and one
// admin-gated backend, both in scope.
func newGateTestGateway(users gatewayUserFinder) *ScopedGateway {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:    "pub-1",
		Name:  "Public",
		Tools: []mcp.Tool{{Name: "pub_tool", IsActive: true}},
	})
	reg.Register(&BackendServer{
		ID:      "gated-1",
		Name:    "Gated",
		MinRole: auth.RoleAdmin,
		Tools:   []mcp.Tool{{Name: "gated_tool", IsActive: true}},
	})
	return &ScopedGateway{
		registry:     reg,
		allowedIDs:   map[string]bool{"pub-1": true, "gated-1": true},
		gatewayUsers: users,
	}
}

func toolNames(t *testing.T, resp *mcp.Response) []string {
	t.Helper()
	if resp.Error != nil {
		t.Fatalf("tools/list returned an error: %v", resp.Error)
	}
	// mcp.Response.Result is json.RawMessage (internal/mcp/types.go:17),
	// so it unmarshals directly — no intermediate Marshal.
	var out mcp.ListToolsResult
	if err := json.Unmarshal(resp.Result, &out); err != nil {
		t.Fatalf("unmarshal result: %v", err)
	}
	names := make([]string, 0, len(out.Tools))
	for _, tl := range out.Tools {
		names = append(names, tl.Name)
	}
	return names
}

func TestToolsList_OmitsGatedBackendForNonAdmin(t *testing.T) {
	users := fakeUsers{"ro@hellopro.fr": auth.RoleReadOnly}
	sg := newGateTestGateway(users)

	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "ro@hellopro.fr")
	names := toolNames(t, sg.handleToolsList(ctx, &mcp.Request{ID: json.RawMessage(`1`)}))

	for _, n := range names {
		if n == "gated_tool" {
			t.Fatalf("read-only user sees gated_tool in %v", names)
		}
	}
	found := false
	for _, n := range names {
		if n == "pub_tool" {
			found = true
		}
	}
	if !found {
		t.Fatalf("public tool missing from %v", names)
	}
}

func TestToolsList_KeepsGatedBackendForAdmin(t *testing.T) {
	users := fakeUsers{"admin@hellopro.fr": auth.RoleAdmin}
	sg := newGateTestGateway(users)

	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "admin@hellopro.fr")
	names := toolNames(t, sg.handleToolsList(ctx, &mcp.Request{ID: json.RawMessage(`1`)}))

	found := false
	for _, n := range names {
		if n == "gated_tool" {
			found = true
		}
	}
	if !found {
		t.Fatalf("admin does not see gated_tool in %v", names)
	}
}

// A scope token puts no email on the context: the gated backend must vanish.
func TestToolsList_OmitsGatedBackendForScopeToken(t *testing.T) {
	sg := newGateTestGateway(fakeUsers{"admin@hellopro.fr": auth.RoleAdmin})

	names := toolNames(t, sg.handleToolsList(context.Background(), &mcp.Request{ID: json.RawMessage(`1`)}))
	for _, n := range names {
		if n == "gated_tool" {
			t.Fatalf("scope token sees gated_tool in %v", names)
		}
	}
}

func TestToolsCall_DeniesGatedBackendForNonAdmin(t *testing.T) {
	users := fakeUsers{"ro@hellopro.fr": auth.RoleReadOnly}
	sg := newGateTestGateway(users)

	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "ro@hellopro.fr")
	req := &mcp.Request{
		ID:     json.RawMessage(`1`),
		Params: json.RawMessage(`{"name":"gated_tool","arguments":{}}`),
	}
	resp := sg.handleToolsCall(ctx, req)

	if resp.Error == nil {
		t.Fatal("expected an MCP error for a gated backend, got success")
	}
	if !strings.Contains(strings.ToLower(resp.Error.Message), "not allowed") {
		t.Fatalf("error message = %q, want it to say the call is not allowed", resp.Error.Message)
	}
}

func TestToolsCall_DeniesGatedBackendForScopeToken(t *testing.T) {
	sg := newGateTestGateway(fakeUsers{"admin@hellopro.fr": auth.RoleAdmin})

	req := &mcp.Request{
		ID:     json.RawMessage(`1`),
		Params: json.RawMessage(`{"name":"gated_tool","arguments":{}}`),
	}
	if resp := sg.handleToolsCall(context.Background(), req); resp.Error == nil {
		t.Fatal("scope token reached a gated backend")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run 'TestToolsList_|TestToolsCall_Denies'`
Expected: FAIL — gated tools present, calls succeed

- [ ] **Step 3: Add the scope helper**

In `internal/gateway/scoped_gateway.go`, next to `nonZohoAllowedIDs`:

```go
// gatedOutIDs returns the subset of sg.allowedIDs whose backend carries a
// min_role the caller behind ctx does not meet. Modelled on
// nonZohoAllowedIDs: the scope is narrowed per request rather than at cache
// build time, because the answer depends on who is asking.
func (sg *ScopedGateway) gatedOutIDs(ctx context.Context) map[string]bool {
	out := make(map[string]bool)
	for _, s := range sg.registry.All() {
		if !sg.allowedIDs[s.ID] || s.MinRole == "" {
			continue
		}
		if !GateAllows(s.MinRole, ctx, sg.gatewayUsers) {
			out[s.ID] = true
		}
	}
	return out
}

// allowedIDsMinusGated returns sg.allowedIDs without the gated-out backends.
// Returns sg.allowedIDs itself when nothing is gated, so the overwhelmingly
// common all-public case allocates nothing.
func (sg *ScopedGateway) allowedIDsMinusGated(ctx context.Context) map[string]bool {
	gated := sg.gatedOutIDs(ctx)
	if len(gated) == 0 {
		return sg.allowedIDs
	}
	out := make(map[string]bool, len(sg.allowedIDs))
	for id, ok := range sg.allowedIDs {
		if ok && !gated[id] {
			out[id] = true
		}
	}
	return out
}
```

- [ ] **Step 4: Enforce in `handleToolsList`**

At the very top of `handleToolsList`, before the existing `email, hasEmail := ...` line, insert:

```go
	// Narrow the scope to backends this caller may reach before any of the
	// Zoho branching below reads sg.allowedIDs.
	allowedIDs := sg.allowedIDsMinusGated(ctx)
```

Then replace every use of `sg.allowedIDs` **inside this function** with `allowedIDs`, and pass it to the two helpers that take the scope:

- `sg.registry.MergedToolsFilteredWithTools(sg.allowedIDs, sg.allowedTools)` → `sg.registry.MergedToolsFilteredWithTools(allowedIDs, sg.allowedTools)`
- `sg.nonZohoAllowedIDs(zohoBackends)` is derived from `sg.allowedIDs` internally; change its signature to take the scope explicitly:

```go
func (sg *ScopedGateway) nonZohoAllowedIDs(allowedIDs map[string]bool, zohoBackends []*BackendServer) map[string]bool {
```

updating its body to range over the `allowedIDs` parameter instead of `sg.allowedIDs`, and update both call sites in `handleToolsList` to `sg.nonZohoAllowedIDs(allowedIDs, zohoBackends)`.

- [ ] **Step 5: Enforce in `handleToolsCall`**

In `handleToolsCall`, immediately after the `if backend == nil { return errorResp(...) }` block that closes the lookup (i.e. once `backend` is known non-nil) and **before** `headers := sg.requestHeadersFor(ctx, backend)`:

```go
	if !GateAllows(backend.MinRole, ctx, sg.gatewayUsers) {
		email, _ := scopetoken.EndUserEmailFromContext(ctx)
		log.Printf("[scoped] tools/call DENIED name=%s backend=%s min_role=%q email=%q — caller does not meet the server's required role", params.Name, backend.ID, backend.MinRole, email)
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("tool %q is not allowed: this server requires the gateway role %q", params.Name, backend.MinRole))
	}
```

- [ ] **Step 6: Run the gate tests**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run 'TestToolsList_|TestToolsCall_Denies' -v`
Expected: PASS

- [ ] **Step 7: Prove no Zoho regression**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -v`
Expected: PASS — every pre-existing Zoho `tools/list` and `tools/call` test still green

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go \
        apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_gate_test.go
git commit -m "feat(mcp-gateway-service): enforce min_role on tools/list and tools/call

EN: Gated backends are omitted from tools/list and refused on tools/call for
callers below the required role, including every scope token and
client_credentials grant; denials are logged with email, server and min_role.
FR: Les backends proteges sont retires de tools/list et refuses sur tools/call
pour les appelants sous le role requis, y compris tout scope token et octroi
client_credentials ; les refus sont journalises avec email, serveur et min_role."
```

---

## Task 5: Consent-screen filtering, both code paths

**Files:**
- Modify: `internal/authserver/handler.go` (`AuthServer`, `AuthServerConfig`, `NewAuthServer`)
- Modify: `internal/authserver/authorize.go:244` (`renderConsent`)
- Modify: `internal/authserver/authorize_api.go:428` (`buildServerList`)
- Modify: `internal/app/app.go:415-429` (wire the user repo)
- Test: `internal/authserver/consent_gate_test.go` (create)

**Interfaces:**
- Consumes: `gateway.FilterServersByGate` (Task 2), `db.MCPServer.MinRole` (Task 1), `repository.UserRepo.GetByEmail`.
- Produces: `authserver.gatewayUserFinder` interface; `AuthServerConfig.UserRepo`.

> **Why one seam covers both branches.** `renderConsent` and `buildServerList`
> each start from the same `s.serverRepo.ListActive()` and then split into a
> "pre-configured scope" branch (admin-assigned `client.Servers`) and a "show
> every active server" branch. The pre-configured branch resolves ids through
> `serverMap`, which is built from that same slice. Filtering the slice
> immediately after `ListActive()` therefore covers both branches: an
> admin-assigned gated server simply **drops out** of `serverMap` for a
> non-admin viewer, so the consent flow renders without it instead of
> erroring. Do not filter anywhere else.

- [ ] **Step 1: Write the failing test**

Create `internal/authserver/consent_gate_test.go`:

```go
package authserver

import (
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

type fakeUsers map[string]string

func (f fakeUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	role, ok := f[email]
	if !ok {
		return nil, nil
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

// TestConsentFilterSeam proves the property both consent builders rely on:
// filtering the ListActive() slice removes a gated server from the map the
// pre-configured-scope branch resolves through, so that branch needs no
// filtering of its own.
func TestConsentFilterSeam(t *testing.T) {
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
	}
	servers := []db.MCPServer{
		{ID: "pub-1", Name: "Public"},
		{ID: "gated-1", Name: "Gated", MinRole: auth.RoleAdmin},
	}

	buildMap := func(email string) map[string]db.MCPServer {
		filtered := gateway.FilterServersByGate(servers, email, users)
		m := make(map[string]db.MCPServer, len(filtered))
		for _, s := range filtered {
			m[s.ID] = s
		}
		return m
	}

	adminMap := buildMap("admin@hellopro.fr")
	if _, ok := adminMap["gated-1"]; !ok {
		t.Fatal("admin lost the gated server from serverMap")
	}

	roMap := buildMap("ro@hellopro.fr")
	if _, ok := roMap["gated-1"]; ok {
		t.Fatal("read-only viewer kept the gated server in serverMap")
	}
	if _, ok := roMap["pub-1"]; !ok {
		t.Fatal("read-only viewer lost the public server")
	}

	// An anonymous viewer (empty email) must see only public servers.
	anonMap := buildMap("")
	if _, ok := anonMap["gated-1"]; ok {
		t.Fatal("anonymous viewer kept the gated server")
	}
	if len(anonMap) != 1 {
		t.Fatalf("anonymous viewer sees %d servers, want 1", len(anonMap))
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -run TestConsentFilterSeam`
Expected: FAIL — `undefined: gateway.FilterServersByGate` if Task 2 is not merged, otherwise `unknown field MinRole` if Task 1 is not merged. Both are prerequisites.

- [ ] **Step 3: Add the user-finder plumbing**

In `internal/authserver/handler.go`, above `type AuthServer struct`:

```go
// gatewayUserFinder is the slice of *repository.UserRepo the consent screen
// needs to resolve a viewer's role. An interface keeps authserver tests free
// of GORM. nil disables the access gate — see the note on AuthServer.userRepo.
type gatewayUserFinder interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}
```

Add `"mcp-gateway/internal/db"` to the imports if absent.

In `type AuthServer struct`, after `serverRepo`:

```go
	// userRepo (optional) resolves a consent viewer's gateway role so
	// servers carrying a min_role can be hidden from viewers below it.
	// When nil, gateway.FilterServersByGate denies every gated server —
	// fail-closed: an unwired repo hides gated servers rather than
	// exposing them.
	userRepo gatewayUserFinder
```

In `type AuthServerConfig struct`, after `ServerRepo`:

```go
	UserRepo       gatewayUserFinder // optional, enables the min_role consent gate
```

In `NewAuthServer`, after `serverRepo: cfg.ServerRepo,`:

```go
		userRepo:       cfg.UserRepo,
```

- [ ] **Step 4: Filter in the HTML path**

In `internal/authserver/authorize.go`, in `renderConsent`, replace:

```go
	servers, _ := s.serverRepo.ListActive()
```

with:

```go
	servers, _ := s.serverRepo.ListActive()
	// Drop servers this viewer's gateway role does not reach. Filtering here,
	// before serverMap is built, covers both the pre-configured-scope branch
	// and the show-all branch below.
	servers = gateway.FilterServersByGate(servers, userEmail, s.userRepo)
```

`internal/gateway` is already imported in this file (`gateway.ZohoServerState`).

- [ ] **Step 5: Filter in the JSON path**

In `internal/authserver/authorize_api.go`, in `buildServerList`, replace:

```go
	servers, _ := s.serverRepo.ListActive()
```

with:

```go
	servers, _ := s.serverRepo.ListActive()
	// Same gate as renderConsent — see the note there on why this one seam
	// covers both branches.
	servers = gateway.FilterServersByGate(servers, userEmail, s.userRepo)
```

Add `"mcp-gateway/internal/gateway"` to that file's imports if absent.

- [ ] **Step 6: Wire the repo at boot**

In `internal/app/app.go`, in the `authserver.AuthServerConfig{...}` literal, after `ServerRepo: dbs.repo,`:

```go
		UserRepo:       dbs.userRepo,
```

- [ ] **Step 7: Run the tests**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -v`
Expected: PASS — the new seam test plus every pre-existing authorize/consent test

- [ ] **Step 8: Run the full service suite**

Run: `cd apps-microservices/mcp-gateway-service && gofmt -l . && go vet ./... && go build ./... && go test ./...`
Expected: no gofmt output, all PASS

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/authserver/handler.go \
        apps-microservices/mcp-gateway-service/internal/authserver/authorize.go \
        apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go \
        apps-microservices/mcp-gateway-service/internal/authserver/consent_gate_test.go \
        apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway-service): hide min_role servers on the consent screen

EN: renderConsent and buildServerList filter the active-server list by the
viewer's gateway role right after ListActive, covering both the
pre-configured-scope and show-all branches; nil user repo fails closed.
FR: renderConsent et buildServerList filtrent la liste des serveurs actifs
selon le role du visiteur juste apres ListActive, ce qui couvre la branche a
scope pre-configure et la branche complete ; un repo utilisateur absent
refuse par defaut."
```

---

## Task 6: Admin UI — access-level select and badge

**Files:**
- Modify: `src/types/server.ts`
- Modify: `src/views/ServerFormView.vue`
- Modify: `src/components/servers/ServerCard.vue`
- Test: `src/views/ServerFormView.spec.ts` (create)

**Interfaces:**
- Consumes: `min_role` on the server REST DTOs (Task 1); `useAuthStore().isAdmin` (`src/stores/auth.ts:28`).
- Produces: `Server.min_role`, `CreateServerRequest.min_role`, form state `form.min_role`.

- [ ] **Step 1: Add the types**

In `src/types/server.ts`, in `interface Server`, after `tool_prefix: string`:

```ts
  /** Minimum gateway role required to see and reach this server over MCP.
   *  Empty string means public. */
  min_role: string
```

In `interface CreateServerRequest`, after `tool_prefix?: string`:

```ts
  min_role?: string
```

(`UpdateServerRequest` extends `Partial<CreateServerRequest>`, so it inherits the field.)

- [ ] **Step 2: Write the failing test**

Create `src/views/ServerFormView.spec.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { MIN_ROLE_OPTIONS, minRoleLabel } from './ServerFormView.vue'

describe('min_role options', () => {
  it('offers public plus the three gateway roles, public first', () => {
    expect(MIN_ROLE_OPTIONS.map((o) => o.value)).toEqual([
      '',
      'config-only',
      'read-only',
      'admin',
    ])
  })

  it('labels the empty value as public rather than leaving it blank', () => {
    expect(minRoleLabel('')).toBe('Public')
  })

  it('labels a gated value with its role', () => {
    expect(minRoleLabel('admin')).toBe('Admin')
  })

  it('falls back to the raw value for an unknown role', () => {
    expect(minRoleLabel('wizard')).toBe('wizard')
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-frontend && npm run test -- ServerFormView`
Expected: FAIL — `MIN_ROLE_OPTIONS` is not exported

- [ ] **Step 4: Export the options from the view**

In `src/views/ServerFormView.vue`, add a plain `<script lang="ts">` block **above** the existing `<script setup lang="ts">` block (a component may carry both; the non-setup block is where named exports live):

```vue
<script lang="ts">
export const MIN_ROLE_OPTIONS = [
  { value: '', label: 'Public' },
  { value: 'config-only', label: 'Config-only' },
  { value: 'read-only', label: 'Read-only' },
  { value: 'admin', label: 'Admin' },
] as const

export function minRoleLabel(value: string): string {
  return MIN_ROLE_OPTIONS.find((o) => o.value === value)?.label ?? value
}
</script>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps-microservices/mcp-gateway-frontend && npm run test -- ServerFormView`
Expected: PASS

- [ ] **Step 6: Add the select to the form**

In `src/views/ServerFormView.vue`, in the template, directly after the existing "Préfixe d'outils" `FormField` block:

```vue
          <FormField
            v-if="auth.isAdmin"
            label="Niveau d'accès requis"
            hint="Public = visible par tous. Sinon le serveur est masqué sur l'écran de consentement OAuth2 et ses outils sont refusés aux rôles inférieurs, ainsi qu'à tous les scope tokens."
          >
            <template #default="{ id }">
              <BaseSelect :id="id" v-model="form.min_role">
                <option v-for="opt in MIN_ROLE_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </BaseSelect>
            </template>
          </FormField>
```

In the `<script setup>` block:

- import the auth store next to the other imports:
  ```ts
  import { useAuthStore } from '@/stores/auth'
  ```
- instantiate it next to the other store/refs declarations:
  ```ts
  const auth = useAuthStore()
  ```
- add `min_role: string` to the form's type declaration (next to `tool_prefix: string`, around line 326)
- add `min_role: '',` to the reactive form initialiser (next to `tool_prefix: '',`, around line 337)
- populate on edit, next to the existing `form.tool_prefix = server.tool_prefix || ''` (around line 383):
  ```ts
  form.min_role = server.min_role || ''
  ```
- send on submit, next to `tool_prefix: form.tool_prefix || undefined,` (around line 463):
  ```ts
  min_role: form.min_role,
  ```

  Send `form.min_role` unconditionally, **not** `|| undefined`: clearing the gate back to Public must transmit `""`, and `omitempty` on the Go create DTO plus the `*string` update DTO both treat a present empty string as "public".

- [ ] **Step 7: Add the badge**

`ServerCard.vue` does **not** use the `Badge` component — it renders inline `<span>` pills with Tailwind classes. Match that, directly after the `v-if="server.tags?.length"` tag block:

```vue
          <span
            v-if="server.min_role"
            class="text-xs bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 px-2 py-0.5 rounded-full font-medium shrink-0"
            :title="'Accès restreint : rôle ' + server.min_role + ' minimum'"
          >
            <i class="pi pi-lock mr-1" />{{ minRoleLabel(server.min_role) }}
          </span>
```

Import the helper alongside the component's other imports:

```ts
import { minRoleLabel } from '@/views/ServerFormView.vue'
```

- [ ] **Step 8: Run the frontend suite**

Run: `cd apps-microservices/mcp-gateway-frontend && npm run test && npx vue-tsc --noEmit -p tsconfig.app.json`
Expected: all PASS, no type errors

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/types/server.ts \
        apps-microservices/mcp-gateway-frontend/src/views/ServerFormView.vue \
        apps-microservices/mcp-gateway-frontend/src/views/ServerFormView.spec.ts \
        apps-microservices/mcp-gateway-frontend/src/components/servers/ServerCard.vue
git commit -m "feat(mcp-gateway-frontend): add required access level to the server form

EN: Admin-only 'Niveau d'acces requis' select on the server create/edit form
and a badge on the server card when a server is gated.
FR: Selecteur 'Niveau d'acces requis' reserve aux admins sur le formulaire de
creation/modification de serveur, et badge sur la carte serveur quand un
serveur est protege."
```

---

## Task 7: Documentation and the `auth_source` drift fix

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`
- Modify: `apps-microservices/mcp-gateway-frontend/CLAUDE.md`

**Interfaces:**
- Consumes: everything shipped in Tasks 1–6.
- Produces: no code.

- [ ] **Step 1: Document the column**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`, in the Database table, change the `mcp_servers` row to:

```
| `mcp_servers` | Backend servers (name, URL, health, capabilities, `min_role` access gate) |
```

- [ ] **Step 2: Document the gate**

In the same file, add to the `## Conventions` list, directly after the "Server-level full-access grants (admin)" bullet:

```markdown
- **Per-server access gate (`mcp_servers.min_role`)**: empty (the default, and the value every pre-existing server carries) means public. Set to `config-only` / `read-only` / `admin` to require at least that `gateway_users.role`. Enforced at four points by one fail-closed predicate (`gateway.GateAllowsEmail`, `internal/gateway/access_gate.go`): `renderConsent` and `buildServerList` drop the server from the OAuth2 consent screen, `handleToolsList` omits its tools, `handleToolsCall` returns an MCP error. A gated server is unreachable for **every** `mcp_…` scope token and **every** `client_credentials` grant, because both arrive without an end-user email on the context — the single condition that also excludes them. An unwired user repository denies rather than allows. Granularity is the server, never the tool; `isAdminOnly` / `isReadOnlyPlus` on the browser REST API are untouched. Editable from the Servers form ("Niveau d'accès requis", admin-only). Tests: `internal/gateway/access_gate_test.go`, `internal/gateway/registry_min_role_test.go`, `internal/gateway/scoped_gateway_gate_test.go`, `internal/authserver/consent_gate_test.go`, `internal/api/min_role_dto_test.go`.
```

- [ ] **Step 3: Fix the documented log tag**

In the same file, line 195 currently reads:

```
Scope-token accepts and rejects log an `auth_source=x-mcp-scope-token|bearer` tag; Slack `UnauthorizedEvent` reasons carry the same tag.
```

The code emits `source=%s`, not `auth_source=` (`internal/scopetoken/middleware.go:243` and `:352`). Replace with:

```
Scope-token accepts and rejects log a `source=x-mcp-scope-token|bearer` tag; Slack `UnauthorizedEvent` reasons carry the same tag.
```

- [ ] **Step 4: Document the frontend control**

In `apps-microservices/mcp-gateway-frontend/CLAUDE.md`, add to the server-form description:

```markdown
- The server form carries a "Niveau d'accès requis" select (`min_role`), rendered only for `admin` sessions. Public is the default; any other value hides the server from lower-role users on the OAuth2 consent screen and blocks its tools. Gated servers show a badge on the server card.
```

- [ ] **Step 5: Verify both claims against the code**

Run:
```bash
cd apps-microservices/mcp-gateway-service && grep -n 'source=%s' internal/scopetoken/middleware.go && grep -rn 'auth_source' . | grep -v CLAUDE.md
```
Expected: the two `source=%s` lines print; the second grep prints nothing (no remaining `auth_source` anywhere in code).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-gateway-service/CLAUDE.md \
        apps-microservices/mcp-gateway-frontend/CLAUDE.md
git commit -m "docs(mcp-gateway): document the min_role access gate

EN: Describe the four enforcement points, the scope-token and
client_credentials exclusion and the admin form control; fix the documented
scope-token log tag, which is source= and not auth_source=.
FR: Decrit les quatre points d'application, l'exclusion des scope tokens et des
octrois client_credentials et le controle admin du formulaire ; corrige le tag
de log scope-token documente, qui est source= et non auth_source=."
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| §5.1 Schema | Task 1 Steps 5–6 |
| §5.2 Predicate, fail-closed branches | Task 2 Steps 1–4 |
| §5.2 `isGatewayAdmin` → `gatewayUserRole` refactor | Task 2 Steps 5–6 |
| §5.2 scope-token invariant pinned by test | Task 2 Steps 7–8 |
| §5.3 point 1 — `renderConsent` | Task 5 Step 4 |
| §5.3 point 2 — `buildServerList` | Task 5 Step 5 |
| §5.3 point 3 — `handleToolsList` | Task 4 Step 4 |
| §5.3 point 4 — `handleToolsCall` | Task 4 Step 5 |
| §5.3 denial logging at point 4 only | Task 4 Step 5 |
| §5.4 Frontend select + badge | Task 6 Steps 6–7 |
| §7 Testing — all groups | Tasks 1–6, each Step 1 |
| §9 Documentation + `auth_source` drift | Task 7 |
| §10.1 build/test clean | every task's penultimate step |
| §10.2 public servers unchanged | Task 2 `TestGateAllowsEmail` public cases; Task 4 Step 7 regression run |
| §10.3 admin sees / read-only does not | Tasks 4 and 5 Step 1 |
| §10.4 scope token denied | Task 4 `TestToolsList_OmitsGatedBackendForScopeToken`, `TestToolsCall_DeniesGatedBackendForScopeToken` |
| §10.5 client_credentials denied | Same tests — a `client_credentials` grant reaches the gateway with no `email` claim, so `oauth2/middleware.go:245` never sets the context key and the request is byte-identical to the scope-token case at this layer |
| §10.6 invalid `min_role` → 400 | Task 1 Steps 1 and 8 |

**Gap found and closed during review:** the spec's §5 sketched only the
context-based predicate, but the consent screen has the viewer's email as a
function parameter rather than on a context. Task 2 splits the predicate into
`GateAllowsEmail` (core) and `GateAllows` (context wrapper) and documents the
split inline. No spec requirement is left unimplemented.

**Second gap found and closed:** the spec did not mention the registry at all,
yet `handleToolsList` / `handleToolsCall` operate on `BackendServer`, and the
30-second health-checker re-discovery rebuilds that struct from the upstream
`initialize` result. Without Task 3 the gate would fall open shortly after
boot. Task 3 exists solely to close that, and `TestRegistry_MinRoleSurvivesRediscovery`
tests for it by name.

**2. Placeholder scan** — no `TBD`, no `TODO`, no "add appropriate error
handling", no "similar to Task N". Every code step carries the literal code.

Two claims in the first draft were verified against the code and found wrong;
both are corrected above rather than left for the implementer to discover:

- `mcp.Response.Result` is `json.RawMessage` (`internal/mcp/types.go:17`), not
  `any`. The Task 4 test helper now unmarshals it directly.
- `ServerCard.vue` does not import `Badge` — it renders inline Tailwind
  `<span>` pills. Task 6 Step 7 now matches that pattern instead of
  introducing a component the file has never used.

One step still carries a conditional instruction ("if the neighbouring calls
use a different receiver name for the registry…") because it depends on a
local naming detail the implementer will see on screen; it names the exact
fallback rule rather than leaving the choice open.

**3. Type consistency**

| Symbol | Defined | Used |
|---|---|---|
| `db.MCPServer.MinRole` | Task 1 Step 5 | Tasks 2, 3, 5 |
| `api.ValidMinRole` | Task 1 Step 3 | Task 1 Step 8 |
| `gatewayUserFinder` (gateway) | pre-existing, `scoped_gateway.go:23` | Task 2 |
| `gatewayUserFinder` (authserver) | Task 5 Step 3 | Task 5 Steps 4–6 |
| `gatewayUserRole` | Task 2 Step 3 | Task 2 Steps 3 and 5 |
| `GateAllowsEmail` | Task 2 Step 3 | Tasks 2, 5 |
| `GateAllows` | Task 2 Step 3 | Task 4 Steps 3 and 5 |
| `FilterServersByGate` | Task 2 Step 3 | Task 5 Steps 4–5 |
| `BackendServer.MinRole` | Task 3 Step 3 | Tasks 3, 4 |
| `Registry.SetMinRole` | Task 3 Step 3 | Task 3 Step 7 |
| `gatedOutIDs` / `allowedIDsMinusGated` | Task 4 Step 3 | Task 4 Step 4 |
| `MIN_ROLE_OPTIONS` / `minRoleLabel` | Task 6 Step 4 | Task 6 Steps 6–7 |

`fakeUsers` is declared twice — once in `package gateway` (Task 2) and once in
`package authserver` (Task 5). Different packages, no collision. The gateway
package already has no `fakeUsers` symbol; if a future merge introduces one,
rename the Task 2 copy to `fakeGatewayUsers`.

**Signature change to watch:** Task 4 Step 4 changes
`nonZohoAllowedIDs(zohoBackends)` to `nonZohoAllowedIDs(allowedIDs, zohoBackends)`.
Both call sites are inside `handleToolsList` and are updated in the same step.
`internal/gateway/scoped_gateway_test.go` may call it directly — if `go build`
reports an arity error there, pass `sg.allowedIDs` as the new first argument to
preserve the existing expectation.

## Task Dependencies

```
Task 1 (column + DTO)
  ├─→ Task 2 (predicate) ──→ Task 4 (runtime)   ← needs Task 3
  │                      └─→ Task 5 (consent)
  └─→ Task 3 (registry) ──→ Task 4
Tasks 1 + 6 (frontend) — Task 6 needs only Task 1's DTO
Task 7 (docs) — last, needs 1–6
```

Order 1 → 2 → 3 → 4 → 5 → 6 → 7 satisfies every edge.
