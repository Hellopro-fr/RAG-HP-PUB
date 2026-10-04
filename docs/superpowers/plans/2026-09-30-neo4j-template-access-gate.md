# Neo4j Template Access Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Neo4j template instance visible and usable only by gateway admins and by users holding a `server_authorizations` row for that exact instance — on the scoped MCP gateway (`tools/*`, `resources/*`, `prompts/*`) and on the OAuth2 consent screens and consent submissions — while every other backend behaves exactly as today.

**Architecture:** A new policy object `gateway.Neo4jAccess` decides "restricted?" (the server's `mcp_servers.template_slug` names a template with `runner = "neo4j"`) and "allowed?" (end-user email present AND (`gateway_users.role = "admin"` OR grant on that server)). It is wired once in `app.go`, copied into every `ScopedGateway` through `Gateway.SetNeo4jAccess`, and handed to the `AuthServer` through `SetServerAccess` (as the `authserver.ServerAccessPolicy` interface). The scoped gateway drops denied backends from the allowed-ID set on the 3 list verbs and returns a JSON-RPC error on the 3 call verbs before anything is forwarded; the consent code filters the active-server list (HTML + JSON) and the submitted scope (HTML form POST + JSON POST). The template slug is resolved from `mcp_servers` by server id (`ServerRepo.TemplateSlugByID`, cached 60 s) because the in-memory registry does not reliably carry it.

**Tech Stack:** Go 1.24, `net/http`, GORM v1.25 (MySQL in production; `github.com/glebarez/sqlite` pure-Go SQLite in the new tests), Docker `golang:1.24-alpine` for every test run.

**Spec:** `docs/superpowers/specs/2026-09-30-neo4j-template-access-gate-design.md`

## Global Constraints

- Restricted backend ⇔ its `mcp_servers.template_slug` is non-empty **and** the template with that slug has `runner = "neo4j"` (inactive templates included — `TemplateRepo.GetBySlugAny`). No new column, no generic per-server flag.
- Allowed ⇔ the request carries an end-user email **and** (`gateway_users.role == "admin"` (`auth.RoleAdmin`) **or** `server_authorizations(server_id, email)` exists for that exact server).
- Callers without end-user email (`mcp_…` scope tokens, `client_credentials` grants) are **always denied** on restricted backends.
- Evaluation order (human decision, 2026-09-30): **email present and `gateway_users.role == "admin"` → allowed, before any template / slug lookup** — an admin keeps access during a DB outage and on an orphan `template_slug`. Only then the restriction check runs (callers without email skip the admin check and go straight to it).
- Fail-closed for non-admins: template / server-slug lookup errors, an unwired template lookup and a non-empty `template_slug` with no template row → the backend counts as restricted. A caller without email is then denied; a non-admin email is allowed only with a grant on that exact server (a grant is the defined key to a restricted server, so it still opens it); every other caller is denied. A `gateway_users` lookup error means "not admin".
- Unrestricted backends: behaviour unchanged (static `mcp-neo4j-service`, Google, Zoho, leexi, ringover, bdd, hellodata).
- A nil `*Neo4jAccess` allows everything; `app.go` always wires it when the DB is present.
- Caches: server id → template slug and template slug → is-Neo4j, TTL **60 s**, positive results only. Grants and roles are **never** cached (a revoked grant applies on the next request).
- Denied call verbs return JSON-RPC code `-32600` (`mcp.ErrInvalidRequest`) with the exact message `access denied: this server requires an admin role or a server authorization`; the call is never forwarded.
- Every denial on a call verb is logged with backend id, template slug and caller email (never credentials); omissions on list verbs are not logged per item.
- The per-instance `NEO4J_READ_ONLY` flag (database-level) is untouched. No frontend change.
- Worktree: `/tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate` (branch `features/neo4j-access-gate`). Every `git` command below uses `git -C` on it; every `go` command runs inside the container, whose `/src` is `apps-microservices/mcp-gateway-service`.
- Test container (no local Go). Create it **once**, only if `docker ps -a --filter name=gw-go-test-gate` lists nothing:
  `docker run -d --name gw-go-test-gate -v /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate/apps-microservices/mcp-gateway-service:/src -v gomodcache:/go/pkg/mod -v gobuildcache:/root/.cache/go-build -w /src golang:1.24-alpine sleep infinity`
  (if it exists but is stopped: `docker start gw-go-test-gate`). Every run is then `docker exec gw-go-test-gate go test ./internal/<pkg>/ -run '<names>' -v -count=1`. Never use `docker run` with a throw-away container.
- Baseline (before Task 1, once). The Alpine image has no cgo, so **86 pre-existing tests always fail** (`gorm.io/driver/sqlite` users in `internal/api`, `internal/authserver/authorize_test.go`, `internal/repository`). Record them and the gofmt state:
  `docker exec gw-go-test-gate sh -c "go test ./internal/... 2>&1 | grep -E '^\s*--- FAIL' | sed 's/ (.*//;s/^ *//' | sort" > /tmp/gate-baseline.fails` (expect 86 lines: `wc -l < /tmp/gate-baseline.fails`)
  `docker exec gw-go-test-gate gofmt -l ./internal > /tmp/gate-baseline.gofmt`
- Task check (end of every task — the "Run the package checks" step):
  `docker exec gw-go-test-gate sh -c "go test ./internal/... 2>&1 | grep -E '^\s*--- FAIL' | sed 's/ (.*//;s/^ *//' | sort" > /tmp/gate-after.fails && diff /tmp/gate-baseline.fails /tmp/gate-after.fails` → prints nothing;
  `docker exec gw-go-test-gate go vet ./internal/...` → prints nothing, exit 0;
  `docker exec gw-go-test-gate gofmt -l ./internal | diff /tmp/gate-baseline.gofmt -` → prints nothing.
- gofmt rule: 45 files under `internal/` are already listed by `gofmt -l` at baseline (among the files touched here: `internal/gateway/registry.go` (not edited), `internal/authserver/handler.go`, `internal/authserver/authorize_api.go`, `internal/repository/server_repo.go`). **Never** `gofmt -w` a file listed at baseline — edit those by hand, keeping the file's existing layout. New files must be gofmt-clean (`gofmt -w` on a new file is fine), and `scoped_gateway.go`, `gateway.go`, `authorize.go`, `app.go` must stay clean.
- The new tests never use `gorm.io/driver/sqlite` (cgo): SQLite-backed tests use `github.com/glebarez/sqlite` (already in `go.mod`, used by `internal/app/zoho_catalog_adapter_test.go`) with hand-written DDL — the production tags declare `datetime(3)`, which that driver does not scan back into `time.Time`, so `AutoMigrate` cannot be used.
- Commits: Conventional Commits, bilingual EN/FR body. Stage only the files listed in the task (explicit paths, never `git add -A` / `.`).
- A hook blocks the literal `--rm -v` in commands; `docker exec` never needs it.

## Review Focus

1. **Registry `TemplateSlug` is empty in production** — `Gateway.DiscoverAndRegister` only copies `TemplateSlug` from a previous registry entry, so a Neo4j instance discovered at boot (`loadServersFromDB`), right after creation (`template_handlers.go` auto-discover) or after a disable/enable has `BackendServer.TemplateSlug == ""`. A policy reading only that field fails **open**. Pinned by `TestNeo4jAccess_Restricted` case "empty registry slug resolved from mcp_servers (neo4j)" (Task 1) and by the Task 2 fixture, which registers `srv-neo4j` with an empty `TemplateSlug` (`TestScopedNeo4jGate_CallsDeniedAreNotForwarded`).
2. **A denied call still reaches the backend** — the check must run after the registry lookup / Zoho fallback and before `requestHeadersFor` / `transport.NewBackendClientWithEndpoint`, on all three call verbs. Pinned by `TestScopedNeo4jGate_CallsDeniedAreNotForwarded` (upstream hit counter must stay 0) and `TestScopedNeo4jGate_CallsServedForAdminAndGrantee` (Task 2).
3. **Admin-first order vs. fail-closed** — the admin check must come before the slug/template lookups (admin keeps access while they fail, with zero lookups) while non-admins and identity-less callers stay denied when a lookup fails. Pinned by `TestNeo4jAccess_AdminAllowedWhileLookupsFail`, `TestNeo4jAccess_NonAdminDeniedWhileLookupsFail` (bob and no-email sub-assertions, both lookup kinds), `TestNeo4jAccess_GranteeAllowedWhileLookupsFail` and `TestNeo4jAccess_UnrestrictedBackendSkipsUserAndGrantLookups` (Task 1).
   **Caching the wrong things** — caching grants/roles would delay revocation; caching a failed lookup would pin a server as restricted (or a template as unknown) for 60 s. Pinned by `TestNeo4jAccess_GrantRevocationTakesEffectImmediately`, `TestNeo4jAccess_DoesNotCacheLookupErrors`, `TestNeo4jAccess_CachesLookupsWithinTTL` (Task 1) and `TestScopedNeo4jGate_GrantRevocationAppliesOnNextRequest` (Task 2).
4. **Identity-less callers slipping through** — scope tokens / `client_credentials` (no email on ctx) on the MCP side, and the JSON consent API's `anonymous@<client_id>` fallback on the consent side. Pinned by `TestScopedNeo4jGate_ListsHideInstanceFromDeniedCallers` / `TestScopedNeo4jGate_CallsDeniedAreNotForwarded` sub-cases "no email" (Task 2) and `TestConsentJSONPost_DropsHiddenServerAndTools/anonymous_fallback` (Task 3).
5. **Hand-crafted consent submissions** — a POST naming a hidden server id (or a `tool_ids` entry `srv-neo4j:…`) must not be stored, on **both** submission endpoints (HTML form `POST /authorize` and JSON `POST /api/v1/oauth2/authorize/consent`). Pinned by `TestConsentHTMLPost_DropsHiddenServer`, `TestConsentHTMLPost_OnlyHiddenServersRejected` and `TestConsentJSONPost_DropsHiddenServerAndTools` (Task 3).

---

## Where the spec did not match the code (adapted here)

- **`BackendServer.TemplateSlug` is not a reliable source** (see Review Focus 1). The policy therefore takes a fourth collaborator, `serverTemplateSlugLookup` (`TemplateSlugByID(id) (string, error)`, a new `ServerRepo` method), and resolves the slug by server id whenever the registry's field is empty. `NewNeo4jAccess` is `NewNeo4jAccess(t templateRunnerLookup, s serverTemplateSlugLookup, u gatewayUserFinder, g serverAuthorizer)` instead of the spec's 3-argument form.
- **The consent screens work on `db.MCPServer` rows and a session email, not on `BackendServer` + ctx.** The policy gains `AllowsEmail(email, serverID, templateSlug string) bool` (the spec's `Allows(ctx, b)` delegates to it), and `internal/authserver` consumes it through a small `ServerAccessPolicy` interface set by `AuthServer.SetServerAccess`.
- **There are two consent submissions, not one:** the HTML form (`handleConsent`, `POST /authorize` with `action=consent`) and the Vue JSON API (`handleAuthorizeConsent`, `POST /api/v1/oauth2/authorize/consent`, which falls back to `anonymous@<client_id>` without a session). Both are filtered. Neither ever writes the OAuth2 client's server list: MCP routing uses `oauth2_client_servers` (admin-assigned `client.Servers`, read by `oauth2.CombinedMiddleware`), not the stored consent scope — so the consent filter is hygiene, and the scoped gateway (Task 2) is the enforcing layer.
- **`mcp_servers.template_slug` has no foreign key** (the `RESTRICT` FK is on `template_instances.template_slug`). A missing template row is therefore not limited to a corrupted DB: e.g. a Google-Sheets import row whose template was later removed from the catalog becomes restricted — denied to non-admins, allowed to admins (confirmed by the human, 2026-09-30).
- **Evaluation order amended by the human (2026-09-30):** the spec's `Allows` checks restriction first; the plan checks "email present → admin → allow" first so admins keep access while the template / slug lookup fails. Cost: one `gateway_users` lookup per (server, request) for callers with an email, uncached like the spec requires.
- The spec gives the error message but no JSON-RPC code; this plan uses `-32600` (`mcp.ErrInvalidRequest`).
- The unscoped `Gateway.Handle` (used by the transports only when no scope is on the context) is not gated; it is unreachable behind `oauth2.CombinedMiddleware`, which always sets the allowed-server set. Out of scope, as in the spec.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `internal/repository/server_repo.go` | Modify | `ServerRepo.TemplateSlugByID` — one-column lookup, `("", nil)` on missing row |
| `internal/repository/server_repo_template_slug_test.go` | Create | Pure-Go SQLite test of `TemplateSlugByID` |
| `internal/gateway/neo4j_access.go` | Create | `Neo4jAccess` policy: restricted detection, allow rule, 60 s caches, `Neo4jAccessDeniedMessage` |
| `internal/gateway/neo4j_access_test.go` | Create | Policy unit tests + counting fakes (`countingTemplates`, `countingServerSlugs`, `countingUsers`, `countingGrants`) |
| `internal/gateway/gateway.go` | Modify | `Gateway.neo4jAccess` field + `SetNeo4jAccess` |
| `internal/gateway/scoped_gateway.go` | Modify | Copy the gate into `ScopedGateway`; enforce on the 6 verbs; `ctx` on `handleResourcesList` / `handlePromptsList`; helpers `withoutDeniedNeo4j`, `neo4jDenied` |
| `internal/gateway/scoped_gateway_neo4j_access_test.go` | Create | 6-verb enforcement tests against an `httptest` upstream |
| `internal/authserver/server_access.go` | Create | `ServerAccessPolicy`, `AuthServer.SetServerAccess`, `visibleServers`, `filterScopeForViewer` |
| `internal/authserver/handler.go` | Modify | `AuthServer.serverAccess` field |
| `internal/authserver/authorize.go` | Modify | `renderConsent` list filter; `handleConsent` scope filter |
| `internal/authserver/authorize_api.go` | Modify | `buildServerList` list filter; `handleAuthorizeConsent` scope filter |
| `internal/authserver/server_access_test.go` | Create | Helper tests with a real `*gateway.Neo4jAccess` (fakes `gateTemplates`, `gateServers`, `gateUsers`, `gateGrants`) |
| `internal/authserver/consent_neo4j_test.go` | Create | Handler tests: HTML GET, JSON info, HTML POST, JSON POST on pure-Go SQLite |
| `internal/app/app.go` | Modify | Build one `Neo4jAccess`, wire it into the gateway and the auth server |
| `CLAUDE.md` (service) | Modify | Directory structure + "Neo4j template instance access gate" convention |

All paths below are relative to `apps-microservices/mcp-gateway-service/` unless they start with `/` or `docs/`.

---

### Task 0: Container and baseline

**Files:** none.

- [ ] **Step 1: Create or start the persistent container**

```bash
docker ps -a --filter name=gw-go-test-gate --format '{{.Names}} {{.Status}}'
```
Nothing printed → create it:
```bash
docker run -d --name gw-go-test-gate -v /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate/apps-microservices/mcp-gateway-service:/src -v gomodcache:/go/pkg/mod -v gobuildcache:/root/.cache/go-build -w /src golang:1.24-alpine sleep infinity
```
Listed as `Exited` → `docker start gw-go-test-gate`.

- [ ] **Step 2: Record the baselines**

```bash
docker exec gw-go-test-gate sh -c "go test ./internal/... 2>&1 | grep -E '^\s*--- FAIL' | sed 's/ (.*//;s/^ *//' | sort" > /tmp/gate-baseline.fails
wc -l < /tmp/gate-baseline.fails
docker exec gw-go-test-gate gofmt -l ./internal > /tmp/gate-baseline.gofmt
docker exec gw-go-test-gate go vet ./internal/...
```
Expected: `86`; `/tmp/gate-baseline.gofmt` lists 45 files (it includes `internal/authserver/handler.go`, `internal/authserver/authorize_api.go`, `internal/repository/server_repo.go`, `internal/gateway/registry.go`); `go vet` prints nothing. If the count is not 86, stop and report — the plan's "diff must be empty" checks assume this baseline.

---

### Task 1: `Neo4jAccess` policy and `ServerRepo.TemplateSlugByID`

**Files:**
- Create: `internal/gateway/neo4j_access.go`
- Create: `internal/gateway/neo4j_access_test.go`
- Create: `internal/repository/server_repo_template_slug_test.go`
- Modify: `internal/repository/server_repo.go` (hand edit — file is in the gofmt baseline)

**Interfaces:**
- Consumes (existing): `gatewayUserFinder` (`GetByEmail(email string) (*db.GatewayUser, error)`) and `serverAuthorizer` (`IsAuthorized(serverID, email string) bool`) from `internal/gateway/scoped_gateway.go`; `scopetoken.EndUserEmailFromContext(ctx context.Context) (string, bool)`; `auth.RoleAdmin`; `db.Template.Runner`; test helper `ctxWithEmail(email string) context.Context` from `internal/gateway/scoped_gateway_auto_self_test.go`.
- Produces:
  - `const Neo4jAccessDeniedMessage = "access denied: this server requires an admin role or a server authorization"`
  - `type templateRunnerLookup interface { GetBySlugAny(slug string) (*db.Template, error) }` — satisfied by `*repository.TemplateRepo`
  - `type serverTemplateSlugLookup interface { TemplateSlugByID(id string) (string, error) }` — satisfied by `*repository.ServerRepo`
  - `func NewNeo4jAccess(t templateRunnerLookup, s serverTemplateSlugLookup, u gatewayUserFinder, g serverAuthorizer) *Neo4jAccess`
  - `func (a *Neo4jAccess) Restricted(b *BackendServer) bool`
  - `func (a *Neo4jAccess) Allows(ctx context.Context, b *BackendServer) bool`
  - `func (a *Neo4jAccess) AllowsEmail(email, serverID, templateSlug string) bool`
  - `func (a *Neo4jAccess) DenialSlug(b *BackendServer) string`
  - `func (r *ServerRepo) TemplateSlugByID(id string) (string, error)`

- [ ] **Step 1: Write the failing repository test**

Create `internal/repository/server_repo_template_slug_test.go`:

```go
package repository

import (
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// Pure-Go SQLite (no cgo) so the test runs in the Alpine test container.
func newTemplateSlugTestRepo(t *testing.T) *ServerRepo {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	sqlDB, err := g.DB()
	if err != nil {
		t.Fatalf("sql db: %v", err)
	}
	sqlDB.SetMaxOpenConns(1)
	t.Cleanup(func() { _ = sqlDB.Close() })
	for _, stmt := range []string{
		`CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', template_slug TEXT NOT NULL DEFAULT '')`,
		`INSERT INTO mcp_servers (id, name, template_slug) VALUES ('srv-neo4j', 'Neo4j prod', 'neo4j'), ('srv-plain', 'Plain', '')`,
	} {
		if err := g.Exec(stmt).Error; err != nil {
			t.Fatalf("ddl: %v", err)
		}
	}
	return NewServerRepo(g, nil)
}

func TestServerRepo_TemplateSlugByID(t *testing.T) {
	repo := newTemplateSlugTestRepo(t)
	cases := map[string]string{
		"srv-neo4j":   "neo4j",
		"srv-plain":   "",
		"srv-missing": "",
	}
	for id, want := range cases {
		got, err := repo.TemplateSlugByID(id)
		if err != nil {
			t.Fatalf("TemplateSlugByID(%q): unexpected error %v", id, err)
		}
		if got != want {
			t.Fatalf("TemplateSlugByID(%q) = %q, want %q", id, got, want)
		}
	}
}

func TestServerRepo_TemplateSlugByIDPropagatesDBErrors(t *testing.T) {
	repo := newTemplateSlugTestRepo(t)
	if err := repo.db.Exec(`DROP TABLE mcp_servers`).Error; err != nil {
		t.Fatalf("drop: %v", err)
	}
	if _, err := repo.TemplateSlugByID("srv-neo4j"); err == nil {
		t.Fatal("a DB error must be returned, not swallowed as an empty slug")
	}
}
```

- [ ] **Step 2: Write the failing policy tests**

Create `internal/gateway/neo4j_access_test.go`:

```go
package gateway

import (
	"context"
	"errors"
	"testing"
	"time"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

// countingTemplates is an in-memory templateRunnerLookup. A slug absent from
// rows returns an error, like gorm.ErrRecordNotFound from the real repo.
type countingTemplates struct {
	rows  map[string]*db.Template
	err   error
	calls int
}

func (f *countingTemplates) GetBySlugAny(slug string) (*db.Template, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	if t, ok := f.rows[slug]; ok {
		return t, nil
	}
	return nil, errors.New("record not found")
}

// countingServerSlugs is an in-memory serverTemplateSlugLookup. An id absent
// from slugs returns "" and no error, like the real repo.
type countingServerSlugs struct {
	slugs map[string]string
	err   error
	calls int
}

func (f *countingServerSlugs) TemplateSlugByID(id string) (string, error) {
	f.calls++
	if f.err != nil {
		return "", f.err
	}
	return f.slugs[id], nil
}

// countingUsers is an in-memory gatewayUserFinder. An email absent from rows
// returns (nil, nil), like the real repo.
type countingUsers struct {
	rows  map[string]*db.GatewayUser
	err   error
	calls int
}

func (f *countingUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.rows[email], nil
}

// countingGrants is an in-memory serverAuthorizer keyed server_id → email.
type countingGrants struct {
	grants map[string]map[string]bool
	calls  int
}

func (f *countingGrants) IsAuthorized(serverID, email string) bool {
	f.calls++
	return f.grants[serverID][email]
}

type neo4jAccessFakes struct {
	templates *countingTemplates
	servers   *countingServerSlugs
	users     *countingUsers
	grants    *countingGrants
}

// newNeo4jAccessFixture wires a policy where "srv-neo4j" is an instance of
// the "neo4j" template (runner neo4j), "srv-ga" an instance of "ga" (runner
// google) and "srv-plain" a regular server. admin@hp.fr is a gateway admin,
// alice@hp.fr holds a grant on srv-neo4j, carol@hp.fr a grant on srv-other.
func newNeo4jAccessFixture() (*Neo4jAccess, *neo4jAccessFakes) {
	f := &neo4jAccessFakes{
		templates: &countingTemplates{rows: map[string]*db.Template{
			"neo4j": {Slug: "neo4j", Runner: "neo4j"},
			"ga":    {Slug: "ga", Runner: "google"},
		}},
		servers: &countingServerSlugs{slugs: map[string]string{
			"srv-neo4j": "neo4j",
			"srv-ga":    "ga",
		}},
		users: &countingUsers{rows: map[string]*db.GatewayUser{
			"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin},
			"bob@hp.fr":   {Email: "bob@hp.fr", Role: "config-only"},
		}},
		grants: &countingGrants{grants: map[string]map[string]bool{
			"srv-neo4j": {"alice@hp.fr": true},
			"srv-other": {"carol@hp.fr": true},
		}},
	}
	return NewNeo4jAccess(f.templates, f.servers, f.users, f.grants), f
}

func TestNeo4jAccess_Restricted(t *testing.T) {
	cases := []struct {
		name    string
		backend *BackendServer
		want    bool
	}{
		{"neo4j runner via slug hint", &BackendServer{ID: "srv-x", TemplateSlug: "neo4j"}, true},
		{"google runner via slug hint", &BackendServer{ID: "srv-x", TemplateSlug: "ga"}, false},
		{"empty registry slug resolved from mcp_servers (neo4j)", &BackendServer{ID: "srv-neo4j"}, true},
		{"empty registry slug resolved from mcp_servers (google)", &BackendServer{ID: "srv-ga"}, false},
		{"regular server (no template_slug anywhere)", &BackendServer{ID: "srv-plain"}, false},
		{"missing template row fails closed", &BackendServer{ID: "srv-x", TemplateSlug: "ghost"}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, _ := newNeo4jAccessFixture()
			if got := a.Restricted(tc.backend); got != tc.want {
				t.Fatalf("Restricted(%+v) = %t, want %t", tc.backend, got, tc.want)
			}
		})
	}
}

func TestNeo4jAccess_RestrictedFailsClosedOnLookupErrors(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.templates.err = errors.New("db down")
	if !a.Restricted(&BackendServer{ID: "srv-ga", TemplateSlug: "ga"}) {
		t.Fatal("template lookup error must count as restricted")
	}

	a, f = newNeo4jAccessFixture()
	f.servers.err = errors.New("db down")
	if !a.Restricted(&BackendServer{ID: "srv-plain"}) {
		t.Fatal("server template_slug lookup error must count as restricted")
	}

	unwired := NewNeo4jAccess(nil, nil, nil, nil)
	if !unwired.Restricted(&BackendServer{ID: "srv-x", TemplateSlug: "ga"}) {
		t.Fatal("unwired template lookup must count as restricted when a slug is present")
	}
	if unwired.Restricted(&BackendServer{ID: "srv-x"}) {
		t.Fatal("unwired policy must not restrict a backend with no slug")
	}
}

func TestNeo4jAccess_Allows(t *testing.T) {
	neo4j := &BackendServer{ID: "srv-neo4j"}
	cases := []struct {
		name  string
		email string
		want  bool
	}{
		{"gateway admin", "admin@hp.fr", true},
		{"grant on this server", "alice@hp.fr", true},
		{"grant on another server only", "carol@hp.fr", false},
		{"known non-admin without grant", "bob@hp.fr", false},
		{"unknown email without grant", "nobody@hp.fr", false},
		{"no end-user email (scope token / client_credentials)", "", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, _ := newNeo4jAccessFixture()
			ctx := context.Background()
			if tc.email != "" {
				ctx = ctxWithEmail(tc.email)
			}
			if got := a.Allows(ctx, neo4j); got != tc.want {
				t.Fatalf("Allows(%q) = %t, want %t", tc.email, got, tc.want)
			}
		})
	}
}

func TestNeo4jAccess_AllowsDeniesOnUserLookupError(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.users.err = errors.New("db down")
	if a.Allows(ctxWithEmail("admin@hp.fr"), &BackendServer{ID: "srv-neo4j"}) {
		t.Fatal("user lookup error must deny an admin without a grant")
	}
}

func TestNeo4jAccess_AdminAllowedWhileLookupsFail(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.templates.err = errors.New("db down")
	f.servers.err = errors.New("db down")
	if !a.Allows(ctxWithEmail("admin@hp.fr"), &BackendServer{ID: "srv-neo4j"}) {
		t.Fatal("an admin must stay allowed while the slug/template lookups fail")
	}
	if !a.AllowsEmail("admin@hp.fr", "srv-x", "ghost") {
		t.Fatal("an admin must stay allowed on an orphan template_slug")
	}
	if f.servers.calls != 0 || f.templates.calls != 0 {
		t.Fatalf("the admin check must run before any lookup, got servers=%d templates=%d", f.servers.calls, f.templates.calls)
	}
}

func TestNeo4jAccess_NonAdminDeniedWhileLookupsFail(t *testing.T) {
	cases := []struct {
		name    string
		breakDB func(f *neo4jAccessFakes)
		backend *BackendServer // unrestricted whenever the DB answers
	}{
		{"template lookup fails", func(f *neo4jAccessFakes) { f.templates.err = errors.New("db down") }, &BackendServer{ID: "srv-ga", TemplateSlug: "ga"}},
		{"server slug lookup fails", func(f *neo4jAccessFakes) { f.servers.err = errors.New("db down") }, &BackendServer{ID: "srv-plain"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, f := newNeo4jAccessFixture()
			tc.breakDB(f)
			if a.Allows(ctxWithEmail("bob@hp.fr"), tc.backend) {
				t.Fatal("non-admin without grant must be denied while the lookup fails")
			}
			if a.Allows(context.Background(), tc.backend) {
				t.Fatal("caller without email must be denied while the lookup fails")
			}
		})
	}
}

func TestNeo4jAccess_GranteeAllowedWhileLookupsFail(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.servers.err = errors.New("db down")
	if !a.Allows(ctxWithEmail("alice@hp.fr"), &BackendServer{ID: "srv-neo4j"}) {
		t.Fatal("a failed lookup counts as restricted, so a grant on this exact server still opens it")
	}
}

func TestNeo4jAccess_AllowsDeniesWhenUsersAndGrantsUnwired(t *testing.T) {
	a := NewNeo4jAccess(&countingTemplates{rows: map[string]*db.Template{"neo4j": {Slug: "neo4j", Runner: "neo4j"}}}, nil, nil, nil)
	if a.Allows(ctxWithEmail("admin@hp.fr"), &BackendServer{ID: "srv-neo4j", TemplateSlug: "neo4j"}) {
		t.Fatal("unwired users/grants must deny a restricted backend")
	}
}

func TestNeo4jAccess_UnrestrictedBackendSkipsUserAndGrantLookups(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	for _, b := range []*BackendServer{{ID: "srv-plain"}, {ID: "srv-ga", TemplateSlug: "ga"}} {
		if !a.Allows(context.Background(), b) {
			t.Fatalf("unrestricted backend %s must be allowed without an email", b.ID)
		}
	}
	if f.users.calls != 0 || f.grants.calls != 0 {
		t.Fatalf("unrestricted backends must not hit users/grants, got users=%d grants=%d", f.users.calls, f.grants.calls)
	}
}

func TestNeo4jAccess_NilPolicyAllowsEverything(t *testing.T) {
	var a *Neo4jAccess
	b := &BackendServer{ID: "srv-neo4j", TemplateSlug: "neo4j"}
	if !a.Allows(context.Background(), b) || !a.AllowsEmail("", b.ID, b.TemplateSlug) {
		t.Fatal("nil *Neo4jAccess must allow everything")
	}
	if a.Restricted(b) {
		t.Fatal("nil *Neo4jAccess must restrict nothing")
	}
}

func TestNeo4jAccess_CachesLookupsWithinTTL(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	t0 := time.Date(2026, 9, 30, 12, 0, 0, 0, time.UTC)
	a.now = func() time.Time { return t0 }
	b := &BackendServer{ID: "srv-neo4j"}

	a.Restricted(b)
	a.Restricted(b)
	if f.servers.calls != 1 || f.templates.calls != 1 {
		t.Fatalf("within TTL: want 1 server + 1 template lookup, got servers=%d templates=%d", f.servers.calls, f.templates.calls)
	}

	a.now = func() time.Time { return t0.Add(neo4jAccessCacheTTL + time.Second) }
	a.Restricted(b)
	if f.servers.calls != 2 || f.templates.calls != 2 {
		t.Fatalf("after TTL: want 2 server + 2 template lookups, got servers=%d templates=%d", f.servers.calls, f.templates.calls)
	}
}

func TestNeo4jAccess_DoesNotCacheLookupErrors(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	b := &BackendServer{ID: "srv-ga", TemplateSlug: "ga"}
	f.templates.err = errors.New("db down")
	if !a.Restricted(b) {
		t.Fatal("lookup error must count as restricted")
	}
	f.templates.err = nil
	if a.Restricted(b) {
		t.Fatal("a failed lookup must not be cached — the next call must see runner=google")
	}
	if f.templates.calls != 2 {
		t.Fatalf("want 2 template lookups, got %d", f.templates.calls)
	}
}

func TestNeo4jAccess_GrantRevocationTakesEffectImmediately(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	b := &BackendServer{ID: "srv-neo4j"}
	ctx := ctxWithEmail("alice@hp.fr")
	if !a.Allows(ctx, b) {
		t.Fatal("alice must be allowed while her grant exists")
	}
	delete(f.grants.grants["srv-neo4j"], "alice@hp.fr")
	if a.Allows(ctx, b) {
		t.Fatal("grants must not be cached: revocation must apply on the next request")
	}
}

func TestNeo4jAccess_DenialSlugResolvesEmptyRegistrySlug(t *testing.T) {
	a, _ := newNeo4jAccessFixture()
	if got := a.DenialSlug(&BackendServer{ID: "srv-neo4j"}); got != "neo4j" {
		t.Fatalf("DenialSlug = %q, want neo4j", got)
	}
}
```

- [ ] **Step 3: Run them to verify they fail**

```bash
docker exec gw-go-test-gate go test ./internal/repository/ -run 'TestServerRepo_TemplateSlugByID' -v -count=1
docker exec gw-go-test-gate go test ./internal/gateway/ -run 'TestNeo4jAccess' -v -count=1
```
Expected: both `FAIL … [build failed]` — `repo.TemplateSlugByID undefined (type *ServerRepo has no field or method TemplateSlugByID)` and `undefined: NewNeo4jAccess` / `undefined: Neo4jAccess` / `undefined: neo4jAccessCacheTTL`.

- [ ] **Step 4: Add `ServerRepo.TemplateSlugByID`**

In `internal/repository/server_repo.go`, insert immediately **before** the existing lines

```go
// Delete removes a server and all its associations (CASCADE).
func (r *ServerRepo) Delete(id string) error {
```

the following block (tabs for indentation, one blank line after it):

```go
// TemplateSlugByID returns just the template_slug column of one server.
// A missing row yields ("", nil): env-var backends and deleted servers are
// not template instances. Used by gateway.Neo4jAccess, which cannot rely on
// the in-memory registry's BackendServer.TemplateSlug.
func (r *ServerRepo) TemplateSlugByID(id string) (string, error) {
	var slugs []string
	err := r.db.Model(&db.MCPServer{}).Where("id = ?", id).Limit(1).Pluck("template_slug", &slugs).Error
	if err != nil {
		return "", err
	}
	if len(slugs) == 0 {
		return "", nil
	}
	return slugs[0], nil
}
```

Do not run `gofmt -w` on this file.

- [ ] **Step 5: Create the policy**

Create `internal/gateway/neo4j_access.go`:

```go
package gateway

import (
	"context"
	"log"
	"sync"
	"time"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// neo4jRunner is the templates.runner value of Neo4j templates. Mirrors
// api.RunnerNeo4j — duplicated because internal/api imports this package.
const neo4jRunner = "neo4j"

// neo4jAccessCacheTTL bounds both policy caches (server id → template slug,
// template slug → is-Neo4j). Grants and roles are never cached.
const neo4jAccessCacheTTL = 60 * time.Second

// Neo4jAccessDeniedMessage is the JSON-RPC error message returned when a
// caller without an admin role or a server authorization targets a Neo4j
// template instance.
const Neo4jAccessDeniedMessage = "access denied: this server requires an admin role or a server authorization"

// templateRunnerLookup is the slice of *repository.TemplateRepo the policy
// needs. GetBySlugAny includes inactive templates.
type templateRunnerLookup interface {
	GetBySlugAny(slug string) (*db.Template, error)
}

// serverTemplateSlugLookup is the slice of *repository.ServerRepo the policy
// needs. It returns "" and a nil error when no mcp_servers row has that id.
// Needed because the in-memory registry does not reliably carry
// BackendServer.TemplateSlug: DiscoverAndRegister only copies it from a
// previous registry entry, so a backend discovered successfully at boot or
// right after instance creation has TemplateSlug == "".
type serverTemplateSlugLookup interface {
	TemplateSlugByID(id string) (string, error)
}

type cachedString struct {
	value   string
	expires time.Time
}

type cachedBool struct {
	value   bool
	expires time.Time
}

// Neo4jAccess decides service-level access to Neo4j template instances: a
// backend is restricted when its mcp_servers.template_slug names a template
// whose runner is "neo4j"; a restricted backend is reachable only by gateway
// admins and by holders of a server_authorizations row for that exact
// server. A nil *Neo4jAccess allows everything.
type Neo4jAccess struct {
	templates templateRunnerLookup
	servers   serverTemplateSlugLookup
	users     gatewayUserFinder
	grants    serverAuthorizer
	now       func() time.Time

	mu          sync.Mutex
	serverSlugs map[string]cachedString
	slugIsNeo4j map[string]cachedBool
}

// NewNeo4jAccess builds the policy. Any argument may be nil: a nil templates
// lookup makes every templated backend restricted (fail-closed), nil users
// or grants deny every restricted backend, and a nil servers lookup limits
// detection to BackendServer.TemplateSlug.
func NewNeo4jAccess(t templateRunnerLookup, s serverTemplateSlugLookup, u gatewayUserFinder, g serverAuthorizer) *Neo4jAccess {
	return &Neo4jAccess{
		templates:   t,
		servers:     s,
		users:       u,
		grants:      g,
		now:         time.Now,
		serverSlugs: make(map[string]cachedString),
		slugIsNeo4j: make(map[string]cachedBool),
	}
}

// Restricted reports whether b is a Neo4j template instance. Lookup errors
// and a missing template row count as restricted (fail-closed).
func (a *Neo4jAccess) Restricted(b *BackendServer) bool {
	if a == nil || b == nil {
		return false
	}
	return a.restricted(b.ID, b.TemplateSlug)
}

// Allows reports whether the request's end user (the OAuth2 email claim on
// ctx) may reach b. Non-restricted backends are always allowed.
func (a *Neo4jAccess) Allows(ctx context.Context, b *BackendServer) bool {
	if a == nil || b == nil {
		return true
	}
	email, _ := scopetoken.EndUserEmailFromContext(ctx)
	return a.AllowsEmail(email, b.ID, b.TemplateSlug)
}

// AllowsEmail is Allows for callers that hold the viewer's email directly
// (the OAuth2 consent screens). templateSlug is the server's
// mcp_servers.template_slug when known; "" makes the policy resolve it from
// serverID.
//
// Order matters: a gateway admin is allowed before any template lookup, so
// an admin keeps access even while the slug / template lookup fails. Every
// other caller then goes through the restriction check, where a failed
// lookup counts as restricted: callers without email are denied, other
// emails pass only with a grant on this exact server.
func (a *Neo4jAccess) AllowsEmail(email, serverID, templateSlug string) bool {
	if a == nil {
		return true
	}
	if email != "" && a.isAdmin(email) {
		return true
	}
	if !a.restricted(serverID, templateSlug) {
		return true
	}
	if email == "" {
		return false
	}
	if a.grants == nil {
		return false
	}
	return a.grants.IsAuthorized(serverID, email)
}

// DenialSlug returns the template slug to log for a denied call on b.
func (a *Neo4jAccess) DenialSlug(b *BackendServer) string {
	if a == nil || b == nil {
		return ""
	}
	if b.TemplateSlug != "" {
		return b.TemplateSlug
	}
	slug, _ := a.serverSlug(b.ID)
	return slug
}

func (a *Neo4jAccess) restricted(serverID, slugHint string) bool {
	slug := slugHint
	if slug == "" {
		var ok bool
		slug, ok = a.serverSlug(serverID)
		if !ok {
			return true
		}
	}
	if slug == "" {
		return false
	}
	return a.isNeo4jSlug(slug)
}

// serverSlug resolves a server's template slug. ok == false means the lookup
// failed; the caller must then treat the server as restricted.
func (a *Neo4jAccess) serverSlug(serverID string) (slug string, ok bool) {
	if a.servers == nil || serverID == "" {
		return "", true
	}
	now := a.now()
	a.mu.Lock()
	if e, hit := a.serverSlugs[serverID]; hit && now.Before(e.expires) {
		a.mu.Unlock()
		return e.value, true
	}
	a.mu.Unlock()

	slug, err := a.servers.TemplateSlugByID(serverID)
	if err != nil {
		log.Printf("[neo4j-access] template_slug lookup failed for server %s: %v — treating as restricted", serverID, err)
		return "", false
	}
	a.mu.Lock()
	a.serverSlugs[serverID] = cachedString{value: slug, expires: now.Add(neo4jAccessCacheTTL)}
	a.mu.Unlock()
	return slug, true
}

// isNeo4jSlug reports whether the template with this slug runs on the Neo4j
// runner. Unwired lookup, lookup error and missing row all return true.
func (a *Neo4jAccess) isNeo4jSlug(slug string) bool {
	if a.templates == nil {
		return true
	}
	now := a.now()
	a.mu.Lock()
	if e, hit := a.slugIsNeo4j[slug]; hit && now.Before(e.expires) {
		a.mu.Unlock()
		return e.value
	}
	a.mu.Unlock()

	tpl, err := a.templates.GetBySlugAny(slug)
	if err != nil || tpl == nil {
		log.Printf("[neo4j-access] template lookup failed for slug %q: %v — treating as restricted", slug, err)
		return true
	}
	isNeo4j := tpl.Runner == neo4jRunner
	a.mu.Lock()
	a.slugIsNeo4j[slug] = cachedBool{value: isNeo4j, expires: now.Add(neo4jAccessCacheTTL)}
	a.mu.Unlock()
	return isNeo4j
}

func (a *Neo4jAccess) isAdmin(email string) bool {
	if a.users == nil {
		return false
	}
	user, err := a.users.GetByEmail(email)
	if err != nil {
		log.Printf("[neo4j-access] gateway_users lookup failed for %s: %v — not treated as admin", email, err)
		return false
	}
	return user != nil && user.Role == auth.RoleAdmin
}
```

- [ ] **Step 6: Run the new tests to verify they pass**

```bash
docker exec gw-go-test-gate go test ./internal/repository/ -run 'TestServerRepo_TemplateSlugByID' -v -count=1
docker exec gw-go-test-gate go test ./internal/gateway/ -run 'TestNeo4jAccess' -v -count=1
```
Expected: `--- PASS: TestServerRepo_TemplateSlugByID`, `--- PASS: TestServerRepo_TemplateSlugByIDPropagatesDBErrors`, every `TestNeo4jAccess_*` (and sub-test) `PASS`, both packages `ok`. Log lines `[neo4j-access] … treating as restricted` / `… not treated as admin` are expected output of the error-path tests.

- [ ] **Step 7: Run the package checks**

Run the three "Task check" commands from Global Constraints. Expected: all three print nothing.

- [ ] **Step 8: Commit**

```bash
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate add \
  apps-microservices/mcp-gateway-service/internal/gateway/neo4j_access.go \
  apps-microservices/mcp-gateway-service/internal/gateway/neo4j_access_test.go \
  apps-microservices/mcp-gateway-service/internal/repository/server_repo.go \
  apps-microservices/mcp-gateway-service/internal/repository/server_repo_template_slug_test.go
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate commit \
  -m "feat(mcp-gateway-service): add the Neo4j template instance access policy" \
  -m "EN: Neo4jAccess decides whether a backend is a Neo4j template instance (template runner = neo4j, slug resolved from mcp_servers because the registry copy is empty after discovery) and whether the caller may reach it (email AND (admin role OR server authorization)). Fail-closed on lookup errors; 60 s caches for slugs only, never for grants or roles. Adds ServerRepo.TemplateSlugByID." \
  -m "FR : Neo4jAccess détermine si un backend est une instance du template Neo4j (runner = neo4j, slug relu dans mcp_servers car la copie du registre est vide après découverte) et si l'appelant peut l'atteindre (email ET (rôle admin OU autorisation serveur)). Refus en cas d'erreur de lecture ; caches de 60 s pour les slugs uniquement, jamais pour les droits ni les rôles. Ajoute ServerRepo.TemplateSlugByID."
```

---

### Task 2: Enforce the gate on the scoped gateway (6 verbs)

**Files:**
- Modify: `internal/gateway/gateway.go`
- Modify: `internal/gateway/scoped_gateway.go`
- Create: `internal/gateway/scoped_gateway_neo4j_access_test.go`

**Interfaces:**
- Consumes: Task 1's `NewNeo4jAccess`, `(*Neo4jAccess).Allows`, `(*Neo4jAccess).DenialSlug`, `Neo4jAccessDeniedMessage`, test fakes `countingTemplates` / `countingServerSlugs` / `countingUsers` / `countingGrants`; existing `Registry.FindByID(id string) *BackendServer`, `errorResp(id json.RawMessage, code int, message string) *mcp.Response`, `mcp.ErrInvalidRequest`, test helper `ctxWithEmail`.
- Produces:
  - `func (g *Gateway) SetNeo4jAccess(a *Neo4jAccess)`
  - `ScopedGateway.neo4jAccess *Neo4jAccess` (copied by `NewScopedGateway`)
  - `func (sg *ScopedGateway) handleResourcesList(ctx context.Context, req *mcp.Request) *mcp.Response` (was `(req)`)
  - `func (sg *ScopedGateway) handlePromptsList(ctx context.Context, req *mcp.Request) *mcp.Response` (was `(req)`)
  - `func (sg *ScopedGateway) withoutDeniedNeo4j(ctx context.Context, ids map[string]bool) map[string]bool`
  - `func (sg *ScopedGateway) neo4jDenied(ctx context.Context, id json.RawMessage, backend *BackendServer, verb string) *mcp.Response`

The only callers of `handleResourcesList` / `handlePromptsList` are the two `case` lines in `ScopedGateway.Handle`; no existing test calls them directly (verified with `grep -rn "handleResourcesList\|handlePromptsList" internal/`).

- [ ] **Step 1: Write the failing tests**

Create `internal/gateway/scoped_gateway_neo4j_access_test.go`:

```go
package gateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/mcp"
)

// neo4jGateFixture is a scoped gateway over two backends sharing one stub
// MCP upstream: "srv-neo4j" (a Neo4j template instance whose registry entry
// has an EMPTY TemplateSlug, exactly like a backend discovered at boot) and
// "srv-plain" (a regular server). hits counts every request that reached the
// upstream.
type neo4jGateFixture struct {
	gw     *Gateway
	sg     *ScopedGateway
	grants *countingGrants
	hits   *int32
}

func newNeo4jGateFixture(t *testing.T, wireGate bool) *neo4jGateFixture {
	t.Helper()
	var hits int32
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{}}`))
	}))
	t.Cleanup(upstream.Close)

	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:         "srv-neo4j",
		MessageURL: upstream.URL,
		ToolPrefix: "neo4jprod",
		Tools:      []mcp.Tool{{Name: "read_neo4j_cypher", IsActive: true}},
		Resources:  []mcp.Resource{{URI: "neo4j://schema", Name: "schema"}},
		Prompts:    []mcp.Prompt{{Name: "neo4j_prompt"}},
	})
	reg.Register(&BackendServer{
		ID:         "srv-plain",
		MessageURL: upstream.URL,
		Tools:      []mcp.Tool{{Name: "echo", IsActive: true}},
		Resources:  []mcp.Resource{{URI: "plain://doc", Name: "doc"}},
		Prompts:    []mcp.Prompt{{Name: "plain_prompt"}},
	})
	gw := New("gw", "1.0", reg)
	grants := &countingGrants{grants: map[string]map[string]bool{
		"srv-neo4j": {"alice@hp.fr": true},
	}}
	if wireGate {
		gw.SetNeo4jAccess(NewNeo4jAccess(
			&countingTemplates{rows: map[string]*db.Template{"neo4j": {Slug: "neo4j", Runner: "neo4j"}}},
			&countingServerSlugs{slugs: map[string]string{"srv-neo4j": "neo4j"}},
			&countingUsers{rows: map[string]*db.GatewayUser{"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin}}},
			grants,
		))
	}
	sg := NewScopedGateway(gw, map[string]bool{"srv-neo4j": true, "srv-plain": true}, nil, nil)
	return &neo4jGateFixture{gw: gw, sg: sg, grants: grants, hits: &hits}
}

func (f *neo4jGateFixture) call(t *testing.T, ctx context.Context, method string, params any) *mcp.Response {
	t.Helper()
	req := &mcp.Request{JSONRPC: "2.0", ID: json.RawMessage(`1`), Method: method}
	if params != nil {
		raw, err := json.Marshal(params)
		if err != nil {
			t.Fatalf("marshal params: %v", err)
		}
		req.Params = raw
	}
	return f.sg.Handle(ctx, req)
}

// listedNames returns the names (tools, prompts) or URIs (resources) of a
// list response.
func listedNames(t *testing.T, resp *mcp.Response) map[string]bool {
	t.Helper()
	if resp == nil || resp.Error != nil {
		t.Fatalf("unexpected error response: %+v", resp)
	}
	var out struct {
		Tools     []mcp.Tool     `json:"tools"`
		Resources []mcp.Resource `json:"resources"`
		Prompts   []mcp.Prompt   `json:"prompts"`
	}
	if err := json.Unmarshal(resp.Result, &out); err != nil {
		t.Fatalf("unmarshal list result: %v", err)
	}
	names := make(map[string]bool)
	for _, x := range out.Tools {
		names[x.Name] = true
	}
	for _, x := range out.Resources {
		names[x.URI] = true
	}
	for _, x := range out.Prompts {
		names[x.Name] = true
	}
	return names
}

var neo4jGateListCases = []struct {
	method     string
	restricted string
	plain      string
}{
	{"tools/list", "neo4jprod_read_neo4j_cypher", "echo"},
	{"resources/list", "neo4j://schema", "plain://doc"},
	{"prompts/list", "neo4j_prompt", "plain_prompt"},
}

var neo4jGateCallCases = []struct {
	method     string
	restricted any
	plain      any
}{
	{"tools/call", mcp.CallToolParams{Name: "neo4jprod_read_neo4j_cypher"}, mcp.CallToolParams{Name: "echo"}},
	{"resources/read", mcp.ReadResourceParams{URI: "neo4j://schema"}, mcp.ReadResourceParams{URI: "plain://doc"}},
	{"prompts/get", mcp.GetPromptParams{Name: "neo4j_prompt"}, mcp.GetPromptParams{Name: "plain_prompt"}},
}

func TestScopedNeo4jGate_ListsHideInstanceFromDeniedCallers(t *testing.T) {
	callers := map[string]context.Context{
		"non-granted user": ctxWithEmail("bob@hp.fr"),
		"no email":         context.Background(),
	}
	for who, ctx := range callers {
		for _, tc := range neo4jGateListCases {
			t.Run(who+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				names := listedNames(t, f.call(t, ctx, tc.method, nil))
				if names[tc.restricted] {
					t.Fatalf("%s leaked %q to %s", tc.method, tc.restricted, who)
				}
				if !names[tc.plain] {
					t.Fatalf("%s must still list unrestricted %q, got %v", tc.method, tc.plain, names)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_ListsShowInstanceToAdminAndGrantee(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		for _, tc := range neo4jGateListCases {
			t.Run(email+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				names := listedNames(t, f.call(t, ctxWithEmail(email), tc.method, nil))
				if !names[tc.restricted] || !names[tc.plain] {
					t.Fatalf("%s for %s must list %q and %q, got %v", tc.method, email, tc.restricted, tc.plain, names)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_CallsDeniedAreNotForwarded(t *testing.T) {
	callers := map[string]context.Context{
		"non-granted user": ctxWithEmail("bob@hp.fr"),
		"no email":         context.Background(),
	}
	for who, ctx := range callers {
		for _, tc := range neo4jGateCallCases {
			t.Run(who+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				resp := f.call(t, ctx, tc.method, tc.restricted)
				if resp.Error == nil || resp.Error.Message != Neo4jAccessDeniedMessage {
					t.Fatalf("%s: want access-denied error, got %+v", tc.method, resp)
				}
				if got := atomic.LoadInt32(f.hits); got != 0 {
					t.Fatalf("%s: denied call reached the upstream %d time(s)", tc.method, got)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_CallsServedForAdminAndGrantee(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		for _, tc := range neo4jGateCallCases {
			t.Run(email+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				resp := f.call(t, ctxWithEmail(email), tc.method, tc.restricted)
				if resp.Error != nil {
					t.Fatalf("%s for %s: unexpected error %+v", tc.method, email, resp.Error)
				}
				if got := atomic.LoadInt32(f.hits); got != 1 {
					t.Fatalf("%s for %s: want 1 upstream hit, got %d", tc.method, email, got)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_UnrestrictedBackendUnaffected(t *testing.T) {
	for _, tc := range neo4jGateCallCases {
		t.Run(tc.method, func(t *testing.T) {
			f := newNeo4jGateFixture(t, true)
			resp := f.call(t, ctxWithEmail("bob@hp.fr"), tc.method, tc.plain)
			if resp.Error != nil {
				t.Fatalf("%s on unrestricted backend: unexpected error %+v", tc.method, resp.Error)
			}
			if got := atomic.LoadInt32(f.hits); got != 1 {
				t.Fatalf("%s on unrestricted backend: want 1 upstream hit, got %d", tc.method, got)
			}
		})
	}
}

func TestScopedNeo4jGate_NilGateKeepsLegacyBehaviour(t *testing.T) {
	f := newNeo4jGateFixture(t, false)
	names := listedNames(t, f.call(t, ctxWithEmail("bob@hp.fr"), "tools/list", nil))
	if !names["neo4jprod_read_neo4j_cypher"] {
		t.Fatalf("without a wired gate every allowed backend stays visible, got %v", names)
	}
	resp := f.call(t, ctxWithEmail("bob@hp.fr"), "tools/call", mcp.CallToolParams{Name: "neo4jprod_read_neo4j_cypher"})
	if resp.Error != nil {
		t.Fatalf("without a wired gate the call must be forwarded, got %+v", resp.Error)
	}
}

func TestScopedNeo4jGate_GrantRevocationAppliesOnNextRequest(t *testing.T) {
	f := newNeo4jGateFixture(t, true)
	ctx := ctxWithEmail("alice@hp.fr")
	if !listedNames(t, f.call(t, ctx, "tools/list", nil))["neo4jprod_read_neo4j_cypher"] {
		t.Fatal("alice must see the instance while her grant exists")
	}
	delete(f.grants.grants["srv-neo4j"], "alice@hp.fr")
	if listedNames(t, f.call(t, ctx, "tools/list", nil))["neo4jprod_read_neo4j_cypher"] {
		t.Fatal("revoked grant must hide the instance on the next request")
	}
	resp := f.call(t, ctx, "tools/call", mcp.CallToolParams{Name: "neo4jprod_read_neo4j_cypher"})
	if resp.Error == nil || resp.Error.Message != Neo4jAccessDeniedMessage {
		t.Fatalf("revoked grant must deny the call, got %+v", resp)
	}
}

func TestNewScopedGateway_CopiesNeo4jAccess(t *testing.T) {
	gw := New("gw", "1.0", NewRegistry())
	a := NewNeo4jAccess(nil, nil, nil, nil)
	gw.SetNeo4jAccess(a)
	if sg := NewScopedGateway(gw, nil, nil, nil); sg.neo4jAccess != a {
		t.Fatal("NewScopedGateway must copy the gateway's Neo4jAccess")
	}
}
```

- [ ] **Step 2: Run them to verify they fail**

```bash
docker exec gw-go-test-gate go test ./internal/gateway/ -run 'TestScopedNeo4jGate|TestNewScopedGateway_CopiesNeo4jAccess' -v -count=1
```
Expected: `FAIL … [build failed]` — `gw.SetNeo4jAccess undefined (type *Gateway has no field or method SetNeo4jAccess)` and `sg.neo4jAccess undefined (type *ScopedGateway has no field or method neo4jAccess)`.

- [ ] **Step 3: Add the gate to `Gateway`**

In `internal/gateway/gateway.go`, replace

```go
	zohoCatalog   ZohoUserCatalog       // optional; nil marks all Zoho backends unconfigured
}
```

with

```go
	zohoCatalog   ZohoUserCatalog       // optional; nil marks all Zoho backends unconfigured
	neo4jAccess   *Neo4jAccess          // optional; nil disables the Neo4j template instance gate
}
```

and insert immediately before the line `// SetBDDResolver attaches the BDD used-table resolver consumed by`:

```go
// SetNeo4jAccess registers the service-level gate for Neo4j template
// instances, copied into every ScopedGateway. Pass nil to disable it (every
// backend then behaves as before the gate existed).
func (g *Gateway) SetNeo4jAccess(a *Neo4jAccess) {
	g.neo4jAccess = a
}

```

- [ ] **Step 4: Copy the gate into `ScopedGateway`**

In `internal/gateway/scoped_gateway.go`, replace

```go
	// nil falls back to the legacy behavior (live-fetch + admin fallback).
	zohoCatalog ZohoUserCatalog
}
```

with

```go
	// nil falls back to the legacy behavior (live-fetch + admin fallback).
	zohoCatalog ZohoUserCatalog
	// neo4jAccess (optional) hides Neo4j template instances from callers
	// that are neither gateway admins nor holders of a server_authorizations
	// grant on that instance. nil allows everything.
	neo4jAccess *Neo4jAccess
}
```

and in `NewScopedGateway` replace

```go
		zohoCatalog:   gw.zohoCatalog,
	}
```

with

```go
		zohoCatalog:   gw.zohoCatalog,
		neo4jAccess:   gw.neo4jAccess,
	}
```

- [ ] **Step 5: Pass `ctx` to the two list handlers**

In `ScopedGateway.Handle`, replace `		return sg.handleResourcesList(req)` with `		return sg.handleResourcesList(ctx, req)` and `		return sg.handlePromptsList(req)` with `		return sg.handlePromptsList(ctx, req)`.

Replace

```go
func (sg *ScopedGateway) handleResourcesList(req *mcp.Request) *mcp.Response {
	resources := sg.registry.MergedResourcesFiltered(sg.allowedIDs)
```

with

```go
func (sg *ScopedGateway) handleResourcesList(ctx context.Context, req *mcp.Request) *mcp.Response {
	resources := sg.registry.MergedResourcesFiltered(sg.withoutDeniedNeo4j(ctx, sg.allowedIDs))
```

and

```go
func (sg *ScopedGateway) handlePromptsList(req *mcp.Request) *mcp.Response {
	prompts := sg.registry.MergedPromptsFiltered(sg.allowedIDs)
```

with

```go
func (sg *ScopedGateway) handlePromptsList(ctx context.Context, req *mcp.Request) *mcp.Response {
	prompts := sg.registry.MergedPromptsFiltered(sg.withoutDeniedNeo4j(ctx, sg.allowedIDs))
```

- [ ] **Step 6: Filter the three registry merges of `handleToolsList`**

In `handleToolsList` make exactly these three replacements (the Zoho live-fetch path is untouched — Zoho backends are never Neo4j instances):

```go
		tools := sg.registry.MergedToolsFilteredWithTools(sg.allowedIDs, sg.allowedTools)
		return sg.toolsListResp(req.ID, tools, nil)
```
→
```go
		tools := sg.registry.MergedToolsFilteredWithTools(sg.withoutDeniedNeo4j(ctx, sg.allowedIDs), sg.allowedTools)
		return sg.toolsListResp(req.ID, tools, nil)
```

```go
			tools := sg.registry.MergedToolsFilteredWithTools(sg.nonZohoAllowedIDs(zohoBackends), sg.allowedTools)
			return sg.toolsListResp(req.ID, tools, nil)
```
→
```go
			tools := sg.registry.MergedToolsFilteredWithTools(sg.withoutDeniedNeo4j(ctx, sg.nonZohoAllowedIDs(zohoBackends)), sg.allowedTools)
			return sg.toolsListResp(req.ID, tools, nil)
```

```go
	tools := sg.registry.MergedToolsFilteredWithTools(sg.nonZohoAllowedIDs(zohoBackends), sg.allowedTools)
	// Live-fetched Zoho tools are absent from the registry index — record
```
→
```go
	tools := sg.registry.MergedToolsFilteredWithTools(sg.withoutDeniedNeo4j(ctx, sg.nonZohoAllowedIDs(zohoBackends)), sg.allowedTools)
	// Live-fetched Zoho tools are absent from the registry index — record
```

- [ ] **Step 7: Deny the three call verbs before forwarding**

In `handleToolsCall`, insert immediately before the line `	// Compute per-request backend headers, starting from the static auth` (i.e. after the registry lookup and the Zoho fallback, before `requestHeadersFor`):

```go
	if denied := sg.neo4jDenied(ctx, req.ID, backend, "tools/call"); denied != nil {
		return denied
	}

```

In `handleResourcesRead`, replace

```go
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown resource: %s", params.URI))
	}
```

with

```go
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown resource: %s", params.URI))
	}
	if denied := sg.neo4jDenied(ctx, req.ID, backend, "resources/read"); denied != nil {
		return denied
	}
```

In `handlePromptsGet`, replace

```go
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown prompt: %s", params.Name))
	}
```

with

```go
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown prompt: %s", params.Name))
	}
	if denied := sg.neo4jDenied(ctx, req.ID, backend, "prompts/get"); denied != nil {
		return denied
	}
```

- [ ] **Step 8: Add the two helpers**

Append to the end of `internal/gateway/scoped_gateway.go` (after `handlePromptsGet`, separated by one blank line):

```go
// withoutDeniedNeo4j returns ids minus every registered backend the
// request's caller may not reach under the Neo4j template instance gate.
// With no gate wired it returns ids unchanged. Omissions are not logged —
// listing verbs would log one line per hidden backend on every call.
func (sg *ScopedGateway) withoutDeniedNeo4j(ctx context.Context, ids map[string]bool) map[string]bool {
	if sg.neo4jAccess == nil {
		return ids
	}
	out := make(map[string]bool, len(ids))
	for id, ok := range ids {
		if !ok {
			continue
		}
		if b := sg.registry.FindByID(id); b != nil && !sg.neo4jAccess.Allows(ctx, b) {
			continue
		}
		out[id] = true
	}
	return out
}

// neo4jDenied returns the access-denied JSON-RPC error when backend is a
// Neo4j template instance the caller may not reach, nil otherwise. Every
// denial is logged with the backend id, template slug and caller email.
func (sg *ScopedGateway) neo4jDenied(ctx context.Context, id json.RawMessage, backend *BackendServer, verb string) *mcp.Response {
	if sg.neo4jAccess.Allows(ctx, backend) {
		return nil
	}
	email, _ := scopetoken.EndUserEmailFromContext(ctx)
	log.Printf("[neo4j-access] %s denied backend=%s template_slug=%q email=%q", verb, backend.ID, sg.neo4jAccess.DenialSlug(backend), email)
	return errorResp(id, mcp.ErrInvalidRequest, Neo4jAccessDeniedMessage)
}
```

(`sg.neo4jAccess.Allows` is safe on a nil `*Neo4jAccess` — it returns true.)

- [ ] **Step 9: Run the new tests to verify they pass**

```bash
docker exec gw-go-test-gate go test ./internal/gateway/ -run 'TestScopedNeo4jGate|TestNewScopedGateway_CopiesNeo4jAccess|TestNeo4jAccess' -v -count=1
```
Expected: every test and sub-test `PASS`, `ok  mcp-gateway/internal/gateway`. `[neo4j-access] tools/call denied backend=srv-neo4j template_slug="neo4j" email="bob@hp.fr"` lines are expected.

- [ ] **Step 10: Run the package checks**

Run the three "Task check" commands from Global Constraints. Expected: all three print nothing (the whole `internal/gateway` package, including the pre-existing scoped-gateway tests, must still pass).

- [ ] **Step 11: Commit**

```bash
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate add \
  apps-microservices/mcp-gateway-service/internal/gateway/gateway.go \
  apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go \
  apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_neo4j_access_test.go
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate commit \
  -m "feat(mcp-gateway-service): enforce the Neo4j access gate on the scoped gateway" \
  -m "EN: tools/list, resources/list and prompts/list omit Neo4j template instances the caller may not reach; tools/call, resources/read and prompts/get return 'access denied: this server requires an admin role or a server authorization' without forwarding, and log the denial. The two list handlers now take the request context." \
  -m "FR : tools/list, resources/list et prompts/list masquent les instances du template Neo4j que l'appelant ne peut pas atteindre ; tools/call, resources/read et prompts/get renvoient 'access denied: this server requires an admin role or a server authorization' sans transmettre l'appel, et journalisent le refus. Les deux handlers de liste reçoivent désormais le contexte de la requête."
```

---

### Task 3: Consent screens and consent submissions

**Files:**
- Create: `internal/authserver/server_access.go`
- Modify: `internal/authserver/handler.go` (hand edit — gofmt baseline)
- Modify: `internal/authserver/authorize.go`
- Modify: `internal/authserver/authorize_api.go` (hand edit — gofmt baseline)
- Create: `internal/authserver/server_access_test.go`
- Create: `internal/authserver/consent_neo4j_test.go`

**Interfaces:**
- Consumes: Task 1's `gateway.NewNeo4jAccess` and `(*gateway.Neo4jAccess).AllowsEmail(email, serverID, templateSlug string) bool`; existing `ConsentScope`, `ServerToolSelection`, `ParseConsentScope(j string) (*ConsentScope, error)`, `authorizeInfoResponse`, `authorizeConsentRequest`, `(*AuthServer).mintAuthSession(w http.ResponseWriter, email, displayName string) error`, `(*AuthServer).HandleAuthorize`, `handleAuthorizeInfo`, `handleAuthorizeConsent`, `auth.SignJWT(secret string, claims auth.Claims) (string, error)`.
- Produces:
  - `type ServerAccessPolicy interface { AllowsEmail(email, serverID, templateSlug string) bool }`
  - `func (s *AuthServer) SetServerAccess(p ServerAccessPolicy)`
  - `AuthServer.serverAccess ServerAccessPolicy`
  - `func visibleServers(servers []db.MCPServer, policy ServerAccessPolicy, email string) []db.MCPServer`
  - `func filterScopeForViewer(scope ConsentScope, policy ServerAccessPolicy, email string) ConsentScope`

Viewer identity (unchanged code paths): `renderConsent` receives `userEmail` (the `mcp_session` email, or the SSO-bridged one); `buildServerList` receives `userEmail` from the session cookie or the `Authorization: Bearer` JWT; `handleConsent` uses `session.Email`; `handleAuthorizeConsent` uses `userEmail` (session, Bearer, or the `anonymous@<client_id>` fallback). Filtering the `ListActive()` result once hides the server in both the pre-configured and the dynamic branch (the pre-configured branch looks servers up in `serverMap` and `continue`s on a miss).

- [ ] **Step 1: Write the failing helper tests**

Create `internal/authserver/server_access_test.go`:

```go
package authserver

import (
	"errors"
	"reflect"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

// gateTemplates / gateServers / gateUsers / gateGrants are the in-memory
// collaborators of a real *gateway.Neo4jAccess used by the consent tests.
type gateTemplates struct{ rows map[string]*db.Template }

func (f gateTemplates) GetBySlugAny(slug string) (*db.Template, error) {
	if t, ok := f.rows[slug]; ok {
		return t, nil
	}
	return nil, errors.New("record not found")
}

type gateServers struct{ slugs map[string]string }

func (f gateServers) TemplateSlugByID(id string) (string, error) { return f.slugs[id], nil }

type gateUsers struct{ rows map[string]*db.GatewayUser }

func (f gateUsers) GetByEmail(email string) (*db.GatewayUser, error) { return f.rows[email], nil }

type gateGrants struct{ grants map[string]map[string]bool }

func (f gateGrants) IsAuthorized(serverID, email string) bool { return f.grants[serverID][email] }

// newGatePolicy: "srv-neo4j" is a Neo4j template instance, "srv-ga" a GA4
// instance (google runner), "srv-plain" a regular server. admin@hp.fr is a
// gateway admin, alice@hp.fr holds a grant on srv-neo4j.
func newGatePolicy() *gateway.Neo4jAccess {
	return gateway.NewNeo4jAccess(
		gateTemplates{rows: map[string]*db.Template{
			"neo4j": {Slug: "neo4j", Runner: "neo4j"},
			"ga":    {Slug: "ga", Runner: "google"},
		}},
		gateServers{slugs: map[string]string{"srv-neo4j": "neo4j", "srv-ga": "ga"}},
		gateUsers{rows: map[string]*db.GatewayUser{"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin}}},
		gateGrants{grants: map[string]map[string]bool{"srv-neo4j": {"alice@hp.fr": true}}},
	)
}

func gateServerRows() []db.MCPServer {
	return []db.MCPServer{
		{ID: "srv-neo4j", Name: "Neo4j prod", TemplateSlug: "neo4j"},
		{ID: "srv-ga", Name: "GA4", TemplateSlug: "ga"},
		{ID: "srv-plain", Name: "Plain"},
	}
}

func serverIDs(servers []db.MCPServer) []string {
	out := make([]string, 0, len(servers))
	for _, s := range servers {
		out = append(out, s.ID)
	}
	return out
}

func TestVisibleServers_HidesNeo4jInstanceFromDeniedViewers(t *testing.T) {
	for _, email := range []string{"bob@hp.fr", "", "anonymous@client-1"} {
		got := serverIDs(visibleServers(gateServerRows(), newGatePolicy(), email))
		if want := []string{"srv-ga", "srv-plain"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("viewer %q: got %v, want %v", email, got, want)
		}
	}
}

func TestVisibleServers_ShowsNeo4jInstanceToAdminAndGrantee(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		got := serverIDs(visibleServers(gateServerRows(), newGatePolicy(), email))
		if want := []string{"srv-neo4j", "srv-ga", "srv-plain"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("viewer %q: got %v, want %v", email, got, want)
		}
	}
}

func TestVisibleServers_NilPolicyKeepsEveryServer(t *testing.T) {
	got := serverIDs(visibleServers(gateServerRows(), nil, "bob@hp.fr"))
	if want := []string{"srv-neo4j", "srv-ga", "srv-plain"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestFilterScopeForViewer_DropsHiddenServerAndItsTools(t *testing.T) {
	in := ConsentScope{
		ServerIDs: []string{"srv-neo4j", "srv-plain"},
		ServerTools: []ServerToolSelection{
			{ServerID: "srv-neo4j", ToolNames: []string{"read_neo4j_cypher"}},
			{ServerID: "srv-plain", ToolNames: []string{"echo"}},
		},
	}
	got := filterScopeForViewer(in, newGatePolicy(), "bob@hp.fr")
	want := ConsentScope{
		ServerIDs:   []string{"srv-plain"},
		ServerTools: []ServerToolSelection{{ServerID: "srv-plain", ToolNames: []string{"echo"}}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %+v, want %+v", got, want)
	}

	if got := filterScopeForViewer(in, newGatePolicy(), "alice@hp.fr"); !reflect.DeepEqual(got, in) {
		t.Fatalf("grantee scope must be unchanged, got %+v", got)
	}
	if got := filterScopeForViewer(in, nil, "bob@hp.fr"); !reflect.DeepEqual(got, in) {
		t.Fatalf("nil policy must leave the scope unchanged, got %+v", got)
	}
}
```

- [ ] **Step 2: Write the failing handler tests**

Create `internal/authserver/consent_neo4j_test.go`:

```go
package authserver

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

const gateJWTSecret = "gate-test-secret"

// gateConsentDDL is the minimal schema the consent handlers touch. Hand
// written because the production GORM tags declare datetime(3), which the
// pure-Go SQLite driver does not parse back into time.Time.
var gateConsentDDL = []string{
	`CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
		tool_prefix TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT '', template_slug TEXT NOT NULL DEFAULT '',
		is_active INTEGER NOT NULL DEFAULT 1)`,
	`CREATE TABLE server_tools (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, name TEXT NOT NULL,
		description TEXT NOT NULL DEFAULT '', input_schema BLOB NOT NULL, is_active INTEGER NOT NULL DEFAULT 1)`,
	`CREATE TABLE server_resources (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, uri TEXT NOT NULL, name TEXT NOT NULL DEFAULT '')`,
	`CREATE TABLE server_prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, name TEXT NOT NULL)`,
	`CREATE TABLE prompt_arguments (id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id INTEGER NOT NULL, name TEXT NOT NULL)`,
	`CREATE TABLE server_tags (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, tag TEXT NOT NULL)`,
	`CREATE TABLE oauth2_clients (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', redirect_uris TEXT,
		is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL DEFAULT '')`,
	`CREATE TABLE oauth2_client_servers (client_id TEXT NOT NULL, server_id TEXT NOT NULL)`,
	`CREATE TABLE oauth2_client_tools (client_id TEXT NOT NULL, server_id TEXT NOT NULL, tool_name TEXT NOT NULL)`,
	`CREATE TABLE oauth2_client_instructions (client_id TEXT NOT NULL, instruction_id TEXT NOT NULL)`,
	`CREATE TABLE oauth2_client_bdd_tables (client_id TEXT NOT NULL, used_table_id TEXT NOT NULL)`,
	`CREATE TABLE oauth2_consents (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_email TEXT NOT NULL,
		scope TEXT, created_at DATETIME, updated_at DATETIME, UNIQUE (client_id, user_email))`,
	`CREATE TABLE oauth2_authorization_codes (code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_email TEXT NOT NULL,
		redirect_uri TEXT NOT NULL, code_challenge TEXT NOT NULL, scope TEXT, expires_at DATETIME NOT NULL,
		used_at DATETIME, created_at DATETIME)`,
	`INSERT INTO mcp_servers (id, name, url, template_slug) VALUES
		('srv-neo4j', 'Neo4j prod', 'http://neo4j.invalid', 'neo4j'),
		('srv-ga', 'GA4', 'http://ga.invalid', 'ga'),
		('srv-plain', 'Plain', 'http://plain.invalid', '')`,
	`INSERT INTO server_tools (server_id, name, input_schema) VALUES
		('srv-neo4j', 'read_neo4j_cypher', CAST('{}' AS BLOB)),
		('srv-ga', 'run_report', CAST('{}' AS BLOB)),
		('srv-plain', 'echo', CAST('{}' AS BLOB))`,
	`INSERT INTO oauth2_clients (id, name, redirect_uris, created_by) VALUES
		('client-gate', 'gate-client', '["https://client.example.com/callback"]', 'admin@hp.fr')`,
}

// newGateConsentServer builds an AuthServer on a pure-Go in-memory SQLite
// (github.com/glebarez/sqlite: no cgo, so it runs in the Alpine test
// container) seeded with three active servers — a Neo4j instance, a GA4
// instance and a regular server — and one dynamic OAuth2 client (no
// admin-assigned servers). It returns the server, client ID, redirect URI
// and DB handle.
func newGateConsentServer(t *testing.T) (*AuthServer, string, string, *gorm.DB) {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	sqlDB, err := g.DB()
	if err != nil {
		t.Fatalf("sql db: %v", err)
	}
	sqlDB.SetMaxOpenConns(1) // one connection = one in-memory database
	t.Cleanup(func() { _ = sqlDB.Close() })
	for _, stmt := range gateConsentDDL {
		if err := g.Exec(stmt).Error; err != nil {
			t.Fatalf("ddl: %v\n%s", err, stmt)
		}
	}
	s := &AuthServer{
		oauth2Repo:   repository.NewOAuth2Repo(g, nil),
		authCodeRepo: repository.NewAuthCodeRepo(g),
		consentRepo:  repository.NewConsentRepo(g),
		refreshRepo:  repository.NewRefreshRepo(g),
		serverRepo:   repository.NewServerRepo(g, nil),
		jwtSecret:    gateJWTSecret,
		publicURL:    "https://mcp.example.com",
	}
	s.SetServerAccess(newGatePolicy())
	return s, "client-gate", "https://client.example.com/callback", g
}

// sessionCookies returns the mcp_session cookie for email.
func sessionCookies(t *testing.T, s *AuthServer, email string) []*http.Cookie {
	t.Helper()
	rec := httptest.NewRecorder()
	if err := s.mintAuthSession(rec, email, ""); err != nil {
		t.Fatalf("mint session: %v", err)
	}
	return rec.Result().Cookies()
}

func bearerFor(t *testing.T, email string) string {
	t.Helper()
	tok, err := auth.SignJWT(gateJWTSecret, auth.Claims{Email: email, Exp: time.Now().Add(time.Hour).Unix(), Iat: time.Now().Unix()})
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return "Bearer " + tok
}

func authorizeQuery(clientID, redirectURI string) url.Values {
	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")
	return q
}

func storedConsentScope(t *testing.T, g *gorm.DB, clientID, email string) *ConsentScope {
	t.Helper()
	var row db.OAuth2Consent
	if err := g.Where("client_id = ? AND user_email = ?", clientID, email).First(&row).Error; err != nil {
		return nil
	}
	scope, err := ParseConsentScope(row.Scope)
	if err != nil {
		t.Fatalf("parse stored scope: %v", err)
	}
	return scope
}

func TestConsentHTML_HidesNeo4jInstanceFromNonGrantedViewer(t *testing.T) {
	cases := []struct {
		email     string
		wantNeo4j bool
	}{
		{"bob@hp.fr", false},
		{"admin@hp.fr", true},
		{"alice@hp.fr", true},
	}
	for _, tc := range cases {
		t.Run(tc.email, func(t *testing.T) {
			s, clientID, redirectURI, _ := newGateConsentServer(t)
			req := httptest.NewRequest(http.MethodGet, "/authorize?"+authorizeQuery(clientID, redirectURI).Encode(), nil)
			for _, c := range sessionCookies(t, s, tc.email) {
				req.AddCookie(c)
			}
			rec := httptest.NewRecorder()
			s.HandleAuthorize(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("want 200 consent screen, got %d: %s", rec.Code, rec.Body.String())
			}
			body := rec.Body.String()
			if got := strings.Contains(body, `value="srv-neo4j"`); got != tc.wantNeo4j {
				t.Fatalf("%s: srv-neo4j listed=%t, want %t", tc.email, got, tc.wantNeo4j)
			}
			if !strings.Contains(body, `value="srv-plain"`) || !strings.Contains(body, `value="srv-ga"`) {
				t.Fatalf("%s: unrestricted servers must stay listed", tc.email)
			}
		})
	}
}

func TestConsentJSON_HidesNeo4jInstanceFromNonGrantedViewer(t *testing.T) {
	cases := []struct {
		email string
		want  []string
	}{
		{"bob@hp.fr", []string{"srv-ga", "srv-plain"}},
		{"admin@hp.fr", []string{"srv-ga", "srv-neo4j", "srv-plain"}},
		{"alice@hp.fr", []string{"srv-ga", "srv-neo4j", "srv-plain"}},
	}
	for _, tc := range cases {
		t.Run(tc.email, func(t *testing.T) {
			s, clientID, redirectURI, _ := newGateConsentServer(t)
			q := url.Values{}
			q.Set("client_id", clientID)
			q.Set("redirect_uri", redirectURI)
			req := httptest.NewRequest(http.MethodGet, "/api/v1/oauth2/authorize/info?"+q.Encode(), nil)
			req.Header.Set("Authorization", bearerFor(t, tc.email))
			rec := httptest.NewRecorder()
			s.handleAuthorizeInfo(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("want 200, got %d: %s", rec.Code, rec.Body.String())
			}
			var resp authorizeInfoResponse
			if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
				t.Fatalf("decode: %v", err)
			}
			var got []string
			for _, srv := range resp.Servers {
				got = append(got, srv.ID)
			}
			sort.Strings(got)
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("%s: got %v, want %v", tc.email, got, tc.want)
			}
		})
	}
}

func TestConsentHTMLPost_DropsHiddenServer(t *testing.T) {
	s, clientID, redirectURI, g := newGateConsentServer(t)
	form := authorizeQuery(clientID, redirectURI)
	form.Set("action", "consent")
	form.Set("approved", "true")
	form.Set("csrf_token", "csrf-1")
	form["server_ids"] = []string{"srv-neo4j", "srv-plain"}
	req := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.AddCookie(&http.Cookie{Name: "oauth2_csrf", Value: "csrf-1"})
	for _, c := range sessionCookies(t, s, "bob@hp.fr") {
		req.AddCookie(c)
	}
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)
	if rec.Code != http.StatusFound {
		t.Fatalf("want 302 to redirect_uri, got %d: %s", rec.Code, rec.Body.String())
	}
	scope := storedConsentScope(t, g, clientID, "bob@hp.fr")
	if scope == nil || !reflect.DeepEqual(scope.ServerIDs, []string{"srv-plain"}) {
		t.Fatalf("stored consent must keep only srv-plain, got %+v", scope)
	}
}

func TestConsentHTMLPost_OnlyHiddenServersRejected(t *testing.T) {
	s, clientID, redirectURI, g := newGateConsentServer(t)
	form := authorizeQuery(clientID, redirectURI)
	form.Set("action", "consent")
	form.Set("approved", "true")
	form.Set("csrf_token", "csrf-1")
	form["server_ids"] = []string{"srv-neo4j"}
	req := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.AddCookie(&http.Cookie{Name: "oauth2_csrf", Value: "csrf-1"})
	for _, c := range sessionCookies(t, s, "bob@hp.fr") {
		req.AddCookie(c)
	}
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400 when every selected server is hidden, got %d", rec.Code)
	}
	if scope := storedConsentScope(t, g, clientID, "bob@hp.fr"); scope != nil {
		t.Fatalf("nothing must be stored, got %+v", scope)
	}
}

func TestConsentJSONPost_DropsHiddenServerAndTools(t *testing.T) {
	cases := []struct {
		name      string
		auth      string
		userEmail string
	}{
		{"non-granted user", "bob@hp.fr", "bob@hp.fr"},
		{"anonymous fallback", "", "anonymous@client-gate"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s, clientID, redirectURI, g := newGateConsentServer(t)
			body, _ := json.Marshal(authorizeConsentRequest{
				ClientID:            clientID,
				RedirectURI:         redirectURI,
				CodeChallenge:       "abc",
				CodeChallengeMethod: "S256",
				State:               "xyz",
				ServerIDs:           []string{"srv-neo4j", "srv-plain"},
				ToolIDs:             []string{"srv-neo4j:read_neo4j_cypher", "srv-plain:echo"},
			})
			req := httptest.NewRequest(http.MethodPost, "/api/v1/oauth2/authorize/consent", bytes.NewReader(body))
			if tc.auth != "" {
				req.Header.Set("Authorization", bearerFor(t, tc.auth))
			}
			rec := httptest.NewRecorder()
			s.handleAuthorizeConsent(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("want 200, got %d: %s", rec.Code, rec.Body.String())
			}
			scope := storedConsentScope(t, g, clientID, tc.userEmail)
			want := &ConsentScope{
				ServerIDs:   []string{"srv-plain"},
				ServerTools: []ServerToolSelection{{ServerID: "srv-plain", ToolNames: []string{"echo"}}},
			}
			if !reflect.DeepEqual(scope, want) {
				t.Fatalf("stored scope: got %+v, want %+v", scope, want)
			}
		})
	}
}

func TestConsentJSONPost_GranteeKeepsNeo4jInstance(t *testing.T) {
	s, clientID, redirectURI, g := newGateConsentServer(t)
	body, _ := json.Marshal(authorizeConsentRequest{
		ClientID:            clientID,
		RedirectURI:         redirectURI,
		CodeChallenge:       "abc",
		CodeChallengeMethod: "S256",
		ServerIDs:           []string{"srv-neo4j", "srv-plain"},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/oauth2/authorize/consent", bytes.NewReader(body))
	req.Header.Set("Authorization", bearerFor(t, "alice@hp.fr"))
	rec := httptest.NewRecorder()
	s.handleAuthorizeConsent(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", rec.Code, rec.Body.String())
	}
	scope := storedConsentScope(t, g, clientID, "alice@hp.fr")
	if scope == nil || !reflect.DeepEqual(scope.ServerIDs, []string{"srv-neo4j", "srv-plain"}) {
		t.Fatalf("grantee must keep both servers, got %+v", scope)
	}
}
```

- [ ] **Step 3: Run them to verify they fail**

```bash
docker exec gw-go-test-gate go test ./internal/authserver/ -run 'TestVisibleServers|TestFilterScopeForViewer|TestConsentHTML|TestConsentJSON' -v -count=1
```
Expected: `FAIL … [build failed]` — `undefined: visibleServers`, `undefined: filterScopeForViewer`, `s.SetServerAccess undefined (type *AuthServer has no field or method SetServerAccess)`.

- [ ] **Step 4: Create the policy seam and helpers**

Create `internal/authserver/server_access.go`:

```go
package authserver

import (
	"log"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

// ServerAccessPolicy decides whether a consent-screen viewer may see (and
// consent to) a server. templateSlug is the server's
// mcp_servers.template_slug when known, "" to let the policy resolve it.
// *gateway.Neo4jAccess satisfies it.
type ServerAccessPolicy interface {
	AllowsEmail(email, serverID, templateSlug string) bool
}

var _ ServerAccessPolicy = (*gateway.Neo4jAccess)(nil)

// SetServerAccess wires the service-level access policy applied to the
// consent screens (HTML + JSON) and to the consent submissions. nil (the
// default) shows every active server, as before the policy existed.
func (s *AuthServer) SetServerAccess(p ServerAccessPolicy) {
	s.serverAccess = p
}

// visibleServers returns the servers the viewer may see, preserving order.
func visibleServers(servers []db.MCPServer, policy ServerAccessPolicy, email string) []db.MCPServer {
	if policy == nil {
		return servers
	}
	out := make([]db.MCPServer, 0, len(servers))
	for _, srv := range servers {
		if policy.AllowsEmail(email, srv.ID, srv.TemplateSlug) {
			out = append(out, srv)
		}
	}
	return out
}

// filterScopeForViewer drops from a consent scope every server — and every
// per-server tool selection — the viewer may not see, so a hand-crafted
// submission can never store a hidden server.
func filterScopeForViewer(scope ConsentScope, policy ServerAccessPolicy, email string) ConsentScope {
	if policy == nil {
		return scope
	}
	var out ConsentScope
	for _, id := range scope.ServerIDs {
		if policy.AllowsEmail(email, id, "") {
			out.ServerIDs = append(out.ServerIDs, id)
		} else {
			log.Printf("[authserver] consent: dropped server %s not visible to %q", id, email)
		}
	}
	for _, sel := range scope.ServerTools {
		if policy.AllowsEmail(email, sel.ServerID, "") {
			out.ServerTools = append(out.ServerTools, sel)
		}
	}
	return out
}
```

- [ ] **Step 5: Add the field to `AuthServer`**

In `internal/authserver/handler.go` (hand edit, no `gofmt -w`), replace

```go
	zohoFetcher ZohoStateForUser
	// docsURL is the absolute URL surfaced in the "Non configurés"
```

with

```go
	zohoFetcher ZohoStateForUser
	// serverAccess (optional) hides servers the viewer may not reach (Neo4j
	// template instances without admin role or grant) from both consent
	// screens and drops them from consent submissions. nil shows everything.
	serverAccess ServerAccessPolicy
	// docsURL is the absolute URL surfaced in the "Non configurés"
```

`AuthServerConfig` / `NewAuthServer` are not changed — the policy is set through `SetServerAccess`, like the other optional collaborators set after construction.

- [ ] **Step 6: Run the tests with the seam in place but the handlers untouched**

```bash
docker exec gw-go-test-gate go test ./internal/authserver/ -run 'TestVisibleServers|TestFilterScopeForViewer|TestConsentHTML|TestConsentJSON' -v -count=1
```
Expected: it now compiles; the four `TestVisibleServers_*` / `TestFilterScopeForViewer_*` tests PASS, and `TestConsentHTML_HidesNeo4jInstanceFromNonGrantedViewer`, `TestConsentJSON_HidesNeo4jInstanceFromNonGrantedViewer`, `TestConsentHTMLPost_DropsHiddenServer`, `TestConsentHTMLPost_OnlyHiddenServersRejected`, `TestConsentJSONPost_DropsHiddenServerAndTools` FAIL (the handlers do not call the helpers yet). `TestConsentJSONPost_GranteeKeepsNeo4jInstance` passes (regression guard).

- [ ] **Step 7: Filter the HTML consent screen and the HTML submission**

In `internal/authserver/authorize.go`, `renderConsent`: replace

```go
	servers, _ := s.serverRepo.ListActive()

	// Build server lookup for name resolution + identify Zoho-tagged servers
```

with

```go
	servers, _ := s.serverRepo.ListActive()
	servers = visibleServers(servers, s.serverAccess, userEmail)

	// Build server lookup for name resolution + identify Zoho-tagged servers
```

In `handleConsent`: replace

```go
		scope.ServerIDs = serverIDs
	}

	s.consentRepo.Upsert(&db.OAuth2Consent{
```

with

```go
		scope.ServerIDs = serverIDs
	}
	scope = filterScopeForViewer(scope, s.serverAccess, session.Email)
	if len(client.Servers) == 0 && len(scope.ServerIDs) == 0 {
		http.Error(w, "select at least one server", http.StatusBadRequest)
		return
	}

	s.consentRepo.Upsert(&db.OAuth2Consent{
```

(For a client with admin-assigned servers an emptied scope is still stored: routing uses `client.Servers`, and the scoped gateway enforces the gate.)

- [ ] **Step 8: Filter the JSON consent API and the JSON submission**

In `internal/authserver/authorize_api.go` (hand edit, no `gofmt -w`), `buildServerList`: replace

```go
	servers, _ := s.serverRepo.ListActive()
	serverMap := make(map[string]db.MCPServer, len(servers))
```

with

```go
	servers, _ := s.serverRepo.ListActive()
	servers = visibleServers(servers, s.serverAccess, userEmail)
	serverMap := make(map[string]db.MCPServer, len(servers))
```

In `handleAuthorizeConsent`: replace

```go
	// Save consent
	s.consentRepo.Upsert(&db.OAuth2Consent{
```

with

```go
	scope = filterScopeForViewer(scope, s.serverAccess, userEmail)
	if len(client.Servers) == 0 && len(scope.ServerIDs) == 0 {
		writeJSONError(w, http.StatusBadRequest, "select at least one server")
		return
	}

	// Save consent
	s.consentRepo.Upsert(&db.OAuth2Consent{
```

- [ ] **Step 9: Run the new tests to verify they pass**

```bash
docker exec gw-go-test-gate go test ./internal/authserver/ -run 'TestVisibleServers|TestFilterScopeForViewer|TestConsentHTML|TestConsentJSON' -v -count=1
```
Expected: all 10 tests (and sub-tests) `PASS`, `ok  mcp-gateway/internal/authserver`. `[authserver] consent: dropped server srv-neo4j not visible to "bob@hp.fr"` lines are expected.

- [ ] **Step 10: Run the package checks**

Run the three "Task check" commands from Global Constraints. Expected: all three print nothing (`internal/authserver` still fails only on the baseline `authorize_test.go` cgo tests, which are in `/tmp/gate-baseline.fails`).

- [ ] **Step 11: Commit**

```bash
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate add \
  apps-microservices/mcp-gateway-service/internal/authserver/server_access.go \
  apps-microservices/mcp-gateway-service/internal/authserver/handler.go \
  apps-microservices/mcp-gateway-service/internal/authserver/authorize.go \
  apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go \
  apps-microservices/mcp-gateway-service/internal/authserver/server_access_test.go \
  apps-microservices/mcp-gateway-service/internal/authserver/consent_neo4j_test.go
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate commit \
  -m "feat(mcp-gateway-service): hide gated Neo4j instances on the OAuth2 consent screens" \
  -m "EN: renderConsent (HTML) and buildServerList (JSON) no longer list a Neo4j template instance the viewer may not reach, and both consent submissions (form POST /authorize and POST /api/v1/oauth2/authorize/consent) drop such a server and its tool selections before storing the consent. The policy is injected with AuthServer.SetServerAccess." \
  -m "FR : renderConsent (HTML) et buildServerList (JSON) n'affichent plus une instance du template Neo4j inaccessible au visiteur, et les deux soumissions de consentement (formulaire POST /authorize et POST /api/v1/oauth2/authorize/consent) retirent ce serveur et ses outils avant d'enregistrer le consentement. La politique est injectée via AuthServer.SetServerAccess."
```

---

### Task 4: Wire the gate in `app.go` and document it

**Files:**
- Modify: `internal/app/app.go`
- Modify: `CLAUDE.md` (the service's, `apps-microservices/mcp-gateway-service/CLAUDE.md`)

**Interfaces:**
- Consumes: `gateway.NewNeo4jAccess(t, s, u, g)`, `(*gateway.Gateway).SetNeo4jAccess`, `(*authserver.AuthServer).SetServerAccess`; the locals already present in `registerRESTAndOAuthServer`: `templateRepo *repository.TemplateRepo`, `dbs.repo *repository.ServerRepo`, `dbs.userRepo *repository.UserRepo`, `serverAuthRepo *repository.ServerAuthorizationRepo`, `authSrv *authserver.AuthServer`. The four repos satisfy `templateRunnerLookup`, `serverTemplateSlugLookup`, `gatewayUserFinder`, `serverAuthorizer` — the build is the check. `registerRESTAndOAuthServer` only runs when `dbStack.repo != nil && dbStack.database != nil`, so none of them is nil there.
- Produces: no new API.

- [ ] **Step 1: Wire the gate into the gateway**

In `internal/app/app.go`, `registerRESTAndOAuthServer`, replace

```go
	gw.SetServerAuthorizer(serverAuthRepo)
	log.Println("[main] server_authorizations wired into Gateway for full-access bypass")

```

with

```go
	gw.SetServerAuthorizer(serverAuthRepo)
	log.Println("[main] server_authorizations wired into Gateway for full-access bypass")

	// Service-level gate on Neo4j template instances: only gateway admins and
	// holders of a server_authorizations grant on the instance may see or call
	// it. Shared by the scoped gateway and the OAuth2 consent screens.
	neo4jAccess := gateway.NewNeo4jAccess(templateRepo, dbs.repo, dbs.userRepo, serverAuthRepo)
	gw.SetNeo4jAccess(neo4jAccess)
	log.Println("[main] neo4j access gate wired (admin role or server authorization required on Neo4j template instances)")

```

- [ ] **Step 2: Wire the gate into the auth server**

In the same function replace

```go
	authSrv.Register(mux)
	authSrv.RegisterAPI(mux)
```

with

```go
	authSrv.SetServerAccess(neo4jAccess)
	authSrv.Register(mux)
	authSrv.RegisterAPI(mux)
```

- [ ] **Step 3: Verify the wiring compiles and is present exactly once each**

```bash
docker exec gw-go-test-gate go build ./...
grep -n "SetNeo4jAccess(neo4jAccess)\|SetServerAccess(neo4jAccess)" /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate/apps-microservices/mcp-gateway-service/internal/app/app.go
```
Expected: the build prints nothing; `grep` prints exactly two lines (`gw.SetNeo4jAccess(neo4jAccess)` and `authSrv.SetServerAccess(neo4jAccess)`).

- [ ] **Step 4: Document the gate in the service CLAUDE.md**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`:

(a) Replace the line

```
    scoped_gateway.go        # Scope-token filtered gateway view
```

with

```
    scoped_gateway.go        # Scope-token filtered gateway view
    neo4j_access.go          # Service-level gate on Neo4j template instances (admin OR grant)
```

(b) Replace the line

```
    consent.go               # Consent scope helpers, CSRF token generation
```

with

```
    consent.go               # Consent scope helpers, CSRF token generation
    server_access.go         # Consent-screen server visibility (Neo4j access gate)
```

(c) In `## Conventions`, find the bullet that starts with `- **Server-level full-access grants (admin)**` and ends with `Resolution order at \`requestHeadersFor\`: Step 0 server-authorization grant → Step 1 auto-self override → Step 2 admin-configured filter.` Insert this new bullet on the line right after it:

```
- **Neo4j template instance access gate**: a backend whose `mcp_servers.template_slug` names a template with `runner = "neo4j"` (inactive templates included) is visible and callable only by gateway admins (`gateway_users.role = "admin"`) and by emails holding a `server_authorizations` row for that exact instance — for Neo4j instances a grant therefore *opens* access, on top of its "unfiltered" meaning for filtered backends. Everybody else, including every caller without an end-user email (`mcp_…` scope tokens, `client_credentials`), gets the instance omitted from `tools/list` / `resources/list` / `prompts/list` and a JSON-RPC `-32600` `access denied: this server requires an admin role or a server authorization` on `tools/call` / `resources/read` / `prompts/get` (never forwarded, logged with backend id, template slug and email). The OAuth2 consent screens (`renderConsent`, `buildServerList`) hide the instance, and both consent submissions (`POST /authorize`, `POST /api/v1/oauth2/authorize/consent`) drop it from the stored scope. Fail-closed: template / server / user lookup errors and a `template_slug` with no template row deny. The slug is read from `mcp_servers` by id (`ServerRepo.TemplateSlugByID`) because the registry's `BackendServer.TemplateSlug` is empty after a successful discovery. Caches (60 s): server id → slug, slug → is-Neo4j; roles and grants are read on every request, so revoking a grant applies on the next request. Unrelated to the per-instance `NEO4J_READ_ONLY` flag (database-level) and to the static `mcp-neo4j-service` (no `template_slug`, unaffected). Implementation: `gateway.Neo4jAccess`, wired in `internal/app/app.go` into `Gateway.SetNeo4jAccess` and `AuthServer.SetServerAccess`.
```

(d) Replace the line

```
- Unit tests in `internal/authserver/*_test.go`, `internal/oauth2/*_test.go`, `internal/repository/*_test.go`, `internal/db/mysql_test.go`.
```

with

```
- Unit tests in `internal/authserver/*_test.go`, `internal/oauth2/*_test.go`, `internal/repository/*_test.go`, `internal/db/mysql_test.go`, `internal/gateway/*_test.go`. Tests using `gorm.io/driver/sqlite` need cgo; new SQLite-backed tests use the pure-Go `github.com/glebarez/sqlite` with hand-written DDL (see `internal/authserver/consent_neo4j_test.go`) so they also run in `golang:1.24-alpine`.
```

- [ ] **Step 5: Run the package checks**

Run the three "Task check" commands from Global Constraints. Expected: all three print nothing.

- [ ] **Step 6: Run every new test together**

```bash
docker exec gw-go-test-gate go test ./internal/gateway/ -run 'TestNeo4jAccess|TestScopedNeo4jGate|TestNewScopedGateway_CopiesNeo4jAccess' -v -count=1
docker exec gw-go-test-gate go test ./internal/authserver/ -run 'TestVisibleServers|TestFilterScopeForViewer|TestConsentHTML|TestConsentJSON' -v -count=1
docker exec gw-go-test-gate go test ./internal/repository/ -run 'TestServerRepo_TemplateSlugByID' -v -count=1
```
Expected: all `PASS`, three `ok` lines.

- [ ] **Step 7: Commit**

```bash
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate add \
  apps-microservices/mcp-gateway-service/internal/app/app.go \
  apps-microservices/mcp-gateway-service/CLAUDE.md
git -C /tmp/claude-1000/-home-hellopro-RAG-HP-PUB/b95a2012-f9f4-4dc3-8341-330b444633c1/scratchpad/wt-neo4j-gate commit \
  -m "feat(mcp-gateway-service): wire the Neo4j access gate and document it" \
  -m "EN: app.go builds one Neo4jAccess from TemplateRepo, ServerRepo, UserRepo and ServerAuthorizationRepo and hands it to the gateway (scoped MCP verbs) and to the OAuth2 auth server (consent screens and submissions). The service CLAUDE.md documents the rule, its fail-closed cases and caches." \
  -m "FR : app.go construit un Neo4jAccess à partir de TemplateRepo, ServerRepo, UserRepo et ServerAuthorizationRepo et le transmet à la passerelle (verbes MCP filtrés) et au serveur d'autorisation OAuth2 (écrans et soumissions de consentement). Le CLAUDE.md du service documente la règle, ses cas de refus par défaut et ses caches."
```

---

## Self-review against the spec

| Spec item | Where |
|---|---|
| G1 restricted = template runner `neo4j` (covers future Neo4j templates), no new column | Task 1 `isNeo4jSlug`; `TestNeo4jAccess_Restricted` |
| G2 admin OR grant on this server, email required | Task 1 `AllowsEmail`; `TestNeo4jAccess_Allows` |
| G3 no email → denied | `TestNeo4jAccess_Allows/no_end-user_email…`, Task 2 "no email" sub-tests |
| G4 fail-closed (lookup errors, unwired repos, missing template row) for non-admins; admins always allowed (human decision) | `TestNeo4jAccess_RestrictedFailsClosedOnLookupErrors`, `…DeniesOnUserLookupError`, `…DeniesWhenUsersAndGrantsUnwired`, `Restricted/missing_template_row…`, `…AdminAllowedWhileLookupsFail`, `…NonAdminDeniedWhileLookupsFail`, `…GranteeAllowedWhileLookupsFail` |
| G5 unrestricted unchanged | `TestNeo4jAccess_UnrestrictedBackendSkipsUserAndGrantLookups`, `TestScopedNeo4jGate_UnrestrictedBackendUnaffected`, `TestScopedNeo4jGate_NilGateKeepsLegacyBehaviour`, baseline diff |
| G6 grant on A never opens B | `TestNeo4jAccess_Allows/grant_on_another_server_only` |
| nil `*Neo4jAccess` allows everything | `TestNeo4jAccess_NilPolicyAllowsEverything`, `TestScopedNeo4jGate_NilGateKeepsLegacyBehaviour`, `TestVisibleServers_NilPolicyKeepsEveryServer` |
| 60 s slug cache, grants/roles uncached | `TestNeo4jAccess_CachesLookupsWithinTTL`, `…GrantRevocationTakesEffectImmediately`, `TestScopedNeo4jGate_GrantRevocationAppliesOnNextRequest` |
| 6 verbs (list omitted / call denied, not forwarded) + ctx on the 2 list handlers | Task 2 |
| Denials logged on call verbs only | Task 2 `neo4jDenied` (list path has no log) |
| Consent HTML + JSON lists, consent submission filtering | Task 3 |
| Wiring via setters in `app.go` | Task 4 |
| G8 no frontend change | no file under `mcp-gateway-frontend` touched |

