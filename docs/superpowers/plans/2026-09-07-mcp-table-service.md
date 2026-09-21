# mcp-table-service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new Go MCP server, `mcp-table-service`, that exposes 13 tools over the gateway's BDD used-tables registry, enforcing the calling user's gateway role through a new act-as path in the gateway.

**Architecture:** The service is a thin façade: every tool reads the end-user email forwarded by the gateway (`X-End-User-Email`), then calls the gateway's existing `/api/v1/bdd/*` REST routes with a shared secret plus `X-Act-As-Email`. A new branch in both gateway auth middlewares (JWT and SSO) accepts that pair only on `/api/v1/bdd/` paths and resolves the role from `gateway_users`, so the existing `isAdminOnly` / `isReadOnlyPlus` gate and every handler stay untouched. The gateway also forwards the end-user identity to backends whose tool prefix is `tables`.

**Tech Stack:** Go 1.24 standard library only (no third-party modules) for the service; Go 1.24 for the gateway changes; `httptest` for all tests; Docker multi-stage `golang:1.24-alpine` → `alpine:3.20`; docker-compose profile `mcp`.

**Spec:** `docs/superpowers/specs/2026-09-07-mcp-table-service-design.md`

## Global Constraints

- Service module path `github.com/hellopro/mcp-table`, directory `apps-microservices/mcp-table-service`, port `8597`, binary `/usr/local/bin/mcp-table`.
- Service has **no external Go dependencies**: `go.mod` contains only the module line and `go 1.24`.
- Gateway tool prefix for the backend: `tables`. Service-local tool names have no prefix.
- Exactly **13 tools**: `list_registered_tables`, `get_table_info`, `list_databases`, `list_catalog_tables`, `list_catalog_fields`, `add_tables`, `add_fields`, `update_table_info`, `update_fields`, `remove_fields`, `set_tables_active`, `delete_tables`, `sync_table_catalog`.
- Batch arrays are capped at **50** items (gateway bulk cap). `database_id` ∈ {1, 5, 10}.
- Shared secret: gateway env `TABLE_SERVICE_TOKEN`, service env `MCP_TABLE_GATEWAY_TOKEN`, `.env` key `MCP_TABLE_SERVICE_TOKEN`. Inbound and outbound header name: `X-Admin-Token`. Act-as header: `X-Act-As-Email`. Identity headers from gateway: `X-End-User-Email`, `X-End-User-Login`.
- Act-as is accepted **only** for paths starting with `/api/v1/bdd/`.
- Timeouts: 15 s per gateway call (`MCP_GATEWAY_TIMEOUT`), 10 s per refresh-catalog call, `add_tables` bounded at 120 s, at most 5 parallel refreshes.
- Error texts are the exact strings in spec §7 (copied into `internal/tools/errors.go` in Task 6).
- Status: `inactive` when `!is_active`; `draft` when `is_active && len(fields)==0`; `active` otherwise.
- Commit messages: Conventional Commits, subject in English, body with an `EN:` and a `FR:` line. Stage with explicit paths. The repo's PreToolUse secret scanner scans **all** untracked files whenever a command contains `git add`; if it blocks on unrelated untracked `.claude-crawl/` caches, stage with `git update-index --add <paths>` then `git commit` (the commit step still scans the staged content).
- Every task ends with `go vet ./... && go build ./... && go test ./...` green in the module it touched.
- Go formatting: `gofmt -l .` must print nothing before each commit.

---

## File Structure

### Gateway (`apps-microservices/mcp-gateway-service`) — modified

| File | Responsibility of the change |
|---|---|
| `internal/auth/actas.go` (new) | `ActAsEmail(r, token)` — the single decision "is this a valid act-as request", shared by both middlewares |
| `internal/auth/actas_test.go` (new) | unit tests of `ActAsEmail` and of the JWT middleware branch |
| `internal/auth/middleware.go` | `Config.TableServiceToken`; act-as branch in `Middleware` |
| `internal/sso/middleware.go` | `WithTableServiceToken`; act-as branch in `Handler` |
| `internal/sso/middleware_actas_test.go` (new) | act-as tests in SSO mode |
| `internal/config/config.go` | `TableServiceToken` from `TABLE_SERVICE_TOKEN` |
| `internal/app/app.go` | plumb the token into `auth.Config` and the SSO middleware |
| `internal/gateway/scoped_gateway.go` | `tablesToolPrefix`, `endUserIdentityHeaders`, `injectTablesIdentity`, two call sites in `requestHeadersFor` |
| `internal/gateway/scoped_gateway_tables_test.go` (new) | identity forwarding tests |
| `CLAUDE.md` | env var row + convention bullet |

### Service (`apps-microservices/mcp-table-service`) — new

| File | Responsibility |
|---|---|
| `go.mod` | module definition |
| `cmd/server/main.go` | boot, config validation, mux, admin-token middleware, graceful shutdown |
| `internal/config/config.go` | env loading |
| `internal/mcp/types.go` | JSON-RPC 2.0 + MCP types (copied from ringover, plus `ToolAnnotations`) |
| `internal/transport/sse.go`, `streamable_http.go` | MCP transports (copied from ringover) |
| `internal/transport/identity.go` | `X-Admin-Token` check middleware; `X-End-User-Email` → context |
| `internal/gateway/types.go` | DTOs mirroring the gateway's `bdd_dto.go` and catalog proxy |
| `internal/gateway/errors.go` | `APIError` |
| `internal/gateway/client.go` | `Client`, `Session` (act-as bound), one method per gateway route |
| `internal/tools/registry.go`, `handler.go` | tool registration/dispatch, MCP method handling (copied from ringover, `Deps` instead of `Clients`) |
| `internal/tools/args.go` | argument extraction helpers |
| `internal/tools/session.go` | `requireSession` (identity → `*gateway.Session`) |
| `internal/tools/errors.go` | gateway error → MCP error text |
| `internal/tools/resolve.go` | `resolveTable`, `findRegisteredByName`, `findCatalogTable`, `registeredByName` |
| `internal/tools/status.go` | status, missing checklist, summary/detail views |
| `internal/tools/relations.go` | relation rows ⇄ stored JSON shape |
| `internal/tools/read_tools.go` | `list_registered_tables`, `get_table_info` |
| `internal/tools/catalog_tools.go` | `list_databases`, `list_catalog_tables`, `list_catalog_fields` |
| `internal/tools/table_tools.go` | `add_tables`, `update_table_info`, `set_tables_active`, `delete_tables`, `sync_table_catalog` |
| `internal/tools/field_tools.go` | `add_fields`, `update_fields`, `remove_fields` |
| `Dockerfile`, `CLAUDE.md` | container + service doc |

### Repo root — modified

| File | Change |
|---|---|
| `docker-compose.yml` | new `mcp-table-service` block; `TABLE_SERVICE_TOKEN` on the gateway |
| `docs/superpowers/specs/2026-09-07-mcp-table-service-design.md` | addendum: act-as branch also lives in the SSO middleware |

---

## Task 1: Gateway act-as authentication branch

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/auth/actas.go`
- Create: `apps-microservices/mcp-gateway-service/internal/auth/actas_test.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/auth/middleware.go` (struct `Config` ~line 47; inside `Middleware` after the public-prefix loop ~line 111)
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/middleware.go` (struct `Middleware` ~line 30; `Handler` after the public-prefix loop ~line 116)
- Create: `apps-microservices/mcp-gateway-service/internal/sso/middleware_actas_test.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/config/config.go` (struct ~line 90; loader ~line 201)
- Modify: `apps-microservices/mcp-gateway-service/internal/app/app.go:82-92` (authCfg literal) and `~line 322` (`ssoMiddleware := sso.NewMiddleware(...)` chain)

**Interfaces:**
- Produces: `auth.ActAsEmail(r *http.Request, token string) (email string, ok bool)`; `auth.ActAsTokenHeader = "X-Admin-Token"`; `auth.ActAsEmailHeader = "X-Act-As-Email"`; `auth.Config.TableServiceToken string`; `(*sso.Middleware).WithTableServiceToken(tok string) *sso.Middleware`; `config.Config.TableServiceToken string`.
- Consumes: existing `auth.injectRole`, `sso.injectRole`, `sso.injectName`, `auth.ContextKeyUserEmail`, `auth.ContextKeyUserName`.

Why both middlewares: `app.go` `wrapAuthMiddleware` uses **either** `sso.Middleware.Handler` (when `SSO_ENABLED=true`, the production mode) **or** `auth.Middleware`. The branch must exist in both or the service would get 401 in production.

- [ ] **Step 1: Write the failing tests for the pure helper**

Create `internal/auth/actas_test.go`:

```go
package auth

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/db"
)

func TestActAsEmail(t *testing.T) {
	mk := func(path, tok, email string) *http.Request {
		r := httptest.NewRequest(http.MethodGet, path, nil)
		if tok != "" {
			r.Header.Set(ActAsTokenHeader, tok)
		}
		if email != "" {
			r.Header.Set(ActAsEmailHeader, email)
		}
		return r
	}
	cases := []struct {
		name      string
		req       *http.Request
		token     string
		wantEmail string
		wantOK    bool
	}{
		{"valid", mk("/api/v1/bdd/used/tables", "s3cret", " alice@hellopro.fr "), "s3cret", "alice@hellopro.fr", true},
		{"valid nested path", mk("/api/v1/bdd/catalog/databases", "s3cret", "alice@hellopro.fr"), "s3cret", "alice@hellopro.fr", true},
		{"wrong token", mk("/api/v1/bdd/used/tables", "nope", "alice@hellopro.fr"), "s3cret", "", false},
		{"missing token header", mk("/api/v1/bdd/used/tables", "", "alice@hellopro.fr"), "s3cret", "", false},
		{"missing email", mk("/api/v1/bdd/used/tables", "s3cret", ""), "s3cret", "", false},
		{"blank email", mk("/api/v1/bdd/used/tables", "s3cret", "   "), "s3cret", "", false},
		{"outside bdd prefix", mk("/api/v1/servers", "s3cret", "alice@hellopro.fr"), "s3cret", "", false},
		{"prefix lookalike", mk("/api/v1/bddx/used", "s3cret", "alice@hellopro.fr"), "s3cret", "", false},
		{"feature disabled (empty token)", mk("/api/v1/bdd/used/tables", "", "alice@hellopro.fr"), "", "", false},
		{"feature disabled, empty header equals empty token", mk("/api/v1/bdd/used/tables", "", "alice@hellopro.fr"), "", "", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, ok := ActAsEmail(c.req, c.token)
			if ok != c.wantOK || got != c.wantEmail {
				t.Fatalf("ActAsEmail = (%q, %v), want (%q, %v)", got, ok, c.wantEmail, c.wantOK)
			}
		})
	}
}

// fakeUsers implements UserRepo in memory: email -> role.
type fakeUsers map[string]string

func (f fakeUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	role, ok := f[email]
	if !ok {
		return nil, errors.New("not found")
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

// echoHandler writes the identity the middleware put on the context.
func echoHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]string{
			"email": UserEmailFromContext(r.Context()),
			"role":  UserRoleFromContext(r.Context()),
		})
	})
}

func actAsCfg(token string) Config {
	return Config{JWTSecret: "jwt-secret", JWTAlgo: "HS256", JWTAudience: "aud", Enabled: true, TableServiceToken: token}
}

func TestMiddleware_ActAs_InjectsEmailAndRole(t *testing.T) {
	h := Middleware(actAsCfg("s3cret"), fakeUsers{"alice@hellopro.fr": "admin"})(echoHandler())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	r.Header.Set(ActAsTokenHeader, "s3cret")
	r.Header.Set(ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, body=%s", w.Code, w.Body.String())
	}
	var got map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["email"] != "alice@hellopro.fr" || got["role"] != "admin" {
		t.Fatalf("identity = %v, want alice/admin", got)
	}
}

func TestMiddleware_ActAs_UnknownUserIsConfigOnly(t *testing.T) {
	h := Middleware(actAsCfg("s3cret"), fakeUsers{})(echoHandler())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	r.Header.Set(ActAsTokenHeader, "s3cret")
	r.Header.Set(ActAsEmailHeader, "ghost@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	var got map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["role"] != RoleConfigOnly {
		t.Fatalf("role = %q, want %q", got["role"], RoleConfigOnly)
	}
}

func TestMiddleware_ActAs_WrongTokenFallsThroughTo401(t *testing.T) {
	h := Middleware(actAsCfg("s3cret"), fakeUsers{"alice@hellopro.fr": "admin"})(echoHandler())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	r.Header.Set(ActAsTokenHeader, "wrong")
	r.Header.Set(ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", w.Code)
	}
}

func TestMiddleware_ActAs_IgnoredOutsideBDDPaths(t *testing.T) {
	h := Middleware(actAsCfg("s3cret"), fakeUsers{"alice@hellopro.fr": "admin"})(echoHandler())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/servers", nil)
	r.Header.Set(ActAsTokenHeader, "s3cret")
	r.Header.Set(ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 (act-as must not work outside /api/v1/bdd/)", w.Code)
	}
}

func TestMiddleware_ActAs_DisabledWhenTokenEmpty(t *testing.T) {
	h := Middleware(actAsCfg(""), fakeUsers{"alice@hellopro.fr": "admin"})(echoHandler())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	r.Header.Set(ActAsTokenHeader, "")
	r.Header.Set(ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 (branch disabled)", w.Code)
	}
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/auth/ -run 'TestActAsEmail|TestMiddleware_ActAs' 2>&1 | head -20`
Expected: compile errors `undefined: ActAsEmail`, `undefined: ActAsTokenHeader`, `unknown field TableServiceToken`.

- [ ] **Step 3: Create the helper**

Create `internal/auth/actas.go`:

```go
package auth

import (
	"crypto/subtle"
	"net/http"
	"strings"
)

// Act-as headers carried by mcp-table-service when it calls the BDD REST
// routes on behalf of an end user. The service authenticates itself with the
// shared secret in X-Admin-Token and names the impersonated user in
// X-Act-As-Email. The gateway then resolves that user's role exactly as it
// would for a browser session, so isAdminOnly / isReadOnlyPlus apply
// unchanged and every /api/v1/bdd handler keeps working on
// auth.UserEmailFromContext.
const (
	ActAsTokenHeader = "X-Admin-Token"
	ActAsEmailHeader = "X-Act-As-Email"

	// actAsPathPrefix bounds the act-as surface: the shared secret can only
	// impersonate a user on the BDD registry routes, never on /servers,
	// /tokens or any other admin API.
	actAsPathPrefix = "/api/v1/bdd/"
)

// ActAsEmail returns the impersonated email when r is a valid act-as request:
// the feature is enabled (token non-empty), the path is under /api/v1/bdd/,
// X-Admin-Token equals token (constant-time compare) and X-Act-As-Email is
// non-empty after trimming. ok=false in every other case — callers then fall
// through to their normal authentication, which ends in 401 for API paths.
func ActAsEmail(r *http.Request, token string) (email string, ok bool) {
	if token == "" || !strings.HasPrefix(r.URL.Path, actAsPathPrefix) {
		return "", false
	}
	got := r.Header.Get(ActAsTokenHeader)
	if got == "" || subtle.ConstantTimeCompare([]byte(got), []byte(token)) != 1 {
		return "", false
	}
	email = strings.TrimSpace(r.Header.Get(ActAsEmailHeader))
	if email == "" {
		return "", false
	}
	return email, true
}
```

- [ ] **Step 4: Add the config field and the branch to the JWT middleware**

In `internal/auth/middleware.go`, extend `Config` (after `FallbackEmail`):

```go
	// TableServiceToken enables the act-as branch used by mcp-table-service on
	// /api/v1/bdd/* (see actas.go). Empty = branch disabled.
	TableServiceToken string
```

In `Middleware`, right after the `for _, prefix := range publicPrefixes { ... }` loop and before the `// Try Authorization: Bearer header first` comment, insert:

```go
			// Act-as branch: mcp-table-service calling the BDD routes on behalf
			// of an end user. The role comes from gateway_users like any other
			// request; roleCheckMiddleware downstream is unchanged.
			if email, ok := ActAsEmail(r, cfg.TableServiceToken); ok {
				log.Printf("[auth] act-as email=%s path=%s", email, path)
				ctx := r.Context()
				ctx = context.WithValue(ctx, ContextKeyUserEmail, email)
				ctx = context.WithValue(ctx, ContextKeyUserName, email)
				ctx = injectRole(ctx, email, userRepo)
				next.ServeHTTP(w, r.WithContext(ctx))
				return
			}
```

- [ ] **Step 5: Run the auth tests**

Run: `go test ./internal/auth/ 2>&1 | tail -5`
Expected: `ok  mcp-gateway/internal/auth`

- [ ] **Step 6: Write the failing SSO-mode test**

Create `internal/sso/middleware_actas_test.go`:

```go
package sso

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

type fakeUsers map[string]string

func (f fakeUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	role, ok := f[email]
	if !ok {
		return nil, errors.New("not found")
	}
	return &db.GatewayUser{Email: email, Role: role, DisplayName: "Alice"}, nil
}

func echo() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]string{
			"email": auth.UserEmailFromContext(r.Context()),
			"role":  auth.UserRoleFromContext(r.Context()),
			"name":  auth.UserNameFromContext(r.Context()),
		})
	})
}

// A Middleware with non-nil client/repo so Handler is not the no-op sentinel.
// The act-as branch returns before any repo call, so zero-value structs are safe.
func actAsMiddleware(token string, users userRepoIface) *Middleware {
	return NewMiddleware(&Client{}, &repository.SSOSessionRepo{}, users, false).WithTableServiceToken(token)
}

func TestSSOHandler_ActAs_InjectsIdentity(t *testing.T) {
	h := actAsMiddleware("s3cret", fakeUsers{"alice@hellopro.fr": "read-only"}).Handler(echo())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	r.Header.Set(auth.ActAsTokenHeader, "s3cret")
	r.Header.Set(auth.ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", w.Code, w.Body.String())
	}
	var got map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["email"] != "alice@hellopro.fr" || got["role"] != "read-only" || got["name"] != "Alice" {
		t.Fatalf("identity = %v", got)
	}
}

func TestSSOHandler_ActAs_WrongTokenIs401(t *testing.T) {
	h := actAsMiddleware("s3cret", fakeUsers{}).Handler(echo())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	r.Header.Set(auth.ActAsTokenHeader, "wrong")
	r.Header.Set(auth.ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", w.Code)
	}
}

func TestSSOHandler_ActAs_IgnoredOutsideBDD(t *testing.T) {
	h := actAsMiddleware("s3cret", fakeUsers{"alice@hellopro.fr": "admin"}).Handler(echo())
	r := httptest.NewRequest(http.MethodGet, "/api/v1/tokens", nil)
	r.Header.Set(auth.ActAsTokenHeader, "s3cret")
	r.Header.Set(auth.ActAsEmailHeader, "alice@hellopro.fr")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", w.Code)
	}
}
```

- [ ] **Step 7: Run it to verify it fails**

Run: `go test ./internal/sso/ -run 'TestSSOHandler_ActAs' 2>&1 | head -5`
Expected: `undefined: (*Middleware).WithTableServiceToken` (or "has no field or method").

- [ ] **Step 8: Add the branch to the SSO middleware**

In `internal/sso/middleware.go`, add a field to `Middleware` (after `slack *SlackNotifier`):

```go
	// tableServiceToken enables the act-as branch for mcp-table-service on
	// /api/v1/bdd/* — same semantics as auth.Config.TableServiceToken.
	tableServiceToken string
```

Add the builder after `WithSlack`:

```go
// WithTableServiceToken enables the mcp-table-service act-as branch (see
// auth.ActAsEmail). Empty token = disabled.
func (m *Middleware) WithTableServiceToken(tok string) *Middleware {
	m.tableServiceToken = tok
	return m
}
```

In `Handler`, right after the `for _, prefix := range publicPrefixes { ... }` loop and before `sid, err := GetSessionID(r)`, insert:

```go
		// Act-as branch: mcp-table-service on behalf of an end user. Mirrors
		// auth.Middleware so the service works in both auth modes.
		if email, ok := auth.ActAsEmail(r, m.tableServiceToken); ok {
			log.Printf("[sso] act-as email=%s path=%s", email, path)
			ctx := r.Context()
			ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, email)
			ctx = injectName(ctx, m.users, email)
			ctx = injectRole(ctx, m.users, email)
			next.ServeHTTP(w, r.WithContext(ctx))
			return
		}
```

- [ ] **Step 9: Run the SSO tests**

Run: `go test ./internal/sso/ 2>&1 | tail -3`
Expected: `ok  mcp-gateway/internal/sso`

- [ ] **Step 10: Wire the config**

`internal/config/config.go` — in the `Config` struct, after `BDDPublicAPIToken string // BDD_PUBLIC_API_TOKEN`:

```go
	// TableServiceToken is the shared secret mcp-table-service presents as
	// X-Admin-Token (with X-Act-As-Email) when it calls /api/v1/bdd/* on
	// behalf of an end user. Must equal MCP_TABLE_GATEWAY_TOKEN on the
	// service side. Empty = act-as disabled.
	TableServiceToken string // TABLE_SERVICE_TOKEN
```

In `Load()`, after `BDDPublicAPIToken: os.Getenv("BDD_PUBLIC_API_TOKEN"),`:

```go
		TableServiceToken: os.Getenv("TABLE_SERVICE_TOKEN"),
```

`internal/app/app.go` — in the `authCfg := auth.Config{...}` literal (line ~82) add:

```go
		TableServiceToken: cfg.TableServiceToken,
```

In `buildSSO`, change the `ssoMiddleware := sso.NewMiddleware(...)` chain to:

```go
	ssoMiddleware := sso.NewMiddleware(ssoClient, ssoRepo, dbs.userRepo, cfg.SecureCookie).
		WithEncryptor(dbs.encryptor).
		WithSlack(ssoSlack).
		WithTableServiceToken(cfg.TableServiceToken)
```

- [ ] **Step 11: Verify the whole module**

Run: `gofmt -l . ; go vet ./... && go build ./... && go test ./... 2>&1 | tail -15`
Expected: gofmt prints nothing; all packages `ok` (pre-existing tests included).

- [ ] **Step 12: Commit**

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/internal/auth/actas.go \
        apps-microservices/mcp-gateway-service/internal/auth/actas_test.go \
        apps-microservices/mcp-gateway-service/internal/auth/middleware.go \
        apps-microservices/mcp-gateway-service/internal/sso/middleware.go \
        apps-microservices/mcp-gateway-service/internal/sso/middleware_actas_test.go \
        apps-microservices/mcp-gateway-service/internal/config/config.go \
        apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway-service): act-as auth branch for mcp-table-service on /api/v1/bdd/*

EN: X-Admin-Token (TABLE_SERVICE_TOKEN) + X-Act-As-Email resolve the end user's gateway role on BDD routes, in both JWT and SSO middlewares; role gate and handlers unchanged.
FR: X-Admin-Token (TABLE_SERVICE_TOKEN) + X-Act-As-Email resolvent le role gateway de l'utilisateur final sur les routes BDD, dans les middlewares JWT et SSO ; gate de role et handlers inchanges."
```

Note: `app.go` already carries uncommitted, unrelated edits (backend metadata source). Commit only the hunks of this task with `git add -p apps-microservices/mcp-gateway-service/internal/app/app.go` if those edits are still present; otherwise `git add` the file.

---

## Task 2: Gateway forwards end-user identity to the `tables` backend

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go` (constants ~line 48; `requestHeadersFor` lines 406-447; `injectZohoIdentity` ~line 761)
- Create: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_tables_test.go`

**Interfaces:**
- Produces: `tablesToolPrefix = "tables"`; `endUserIdentityHeaders(ctx, headers) (email string, ok bool)`; `(*ScopedGateway).injectTablesIdentity(ctx, headers, backend)`.
- Consumes: `scopetoken.EndUserEmailFromContext`, `fakeServerAuth` (already defined in `scoped_gateway_server_auth_test.go`, same package).

- [ ] **Step 1: Write the failing tests**

Create `internal/gateway/scoped_gateway_tables_test.go`:

```go
package gateway

import (
	"context"
	"testing"

	"mcp-gateway/internal/scopetoken"
)

func tablesBackend() *BackendServer {
	return &BackendServer{
		ID:          "srv-tables",
		ToolPrefix:  tablesToolPrefix,
		AuthHeaders: map[string]string{"X-Admin-Token": "shared"},
	}
}

func TestRequestHeadersFor_TablesForwardsIdentity(t *testing.T) {
	sg := &ScopedGateway{}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@hellopro.fr")
	h := sg.requestHeadersFor(ctx, tablesBackend())
	if h["X-End-User-Email"] != "alice@hellopro.fr" || h["X-End-User-Login"] != "alice" {
		t.Fatalf("identity headers missing: %v", h)
	}
	if h["X-Admin-Token"] != "shared" {
		t.Fatalf("static auth header lost: %v", h)
	}
	if _, present := h[BDDAllowedTablesHeader]; present {
		t.Fatalf("no BDD allow-list header expected on tables backend: %v", h)
	}
}

func TestRequestHeadersFor_TablesNoIdentityWithoutEmail(t *testing.T) {
	sg := &ScopedGateway{}
	h := sg.requestHeadersFor(context.Background(), tablesBackend())
	if _, ok := h["X-End-User-Email"]; ok {
		t.Fatalf("unexpected identity header without end-user on ctx: %v", h)
	}
	if h["X-Admin-Token"] != "shared" {
		t.Fatalf("static auth header lost: %v", h)
	}
}

func TestRequestHeadersFor_TablesIdentitySurvivesServerAuthBypass(t *testing.T) {
	sg := &ScopedGateway{serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
		"srv-tables": {"alice@hellopro.fr": true},
	}}}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@hellopro.fr")
	h := sg.requestHeadersFor(ctx, tablesBackend())
	if h["X-End-User-Email"] != "alice@hellopro.fr" {
		t.Fatalf("identity must be forwarded inside the server-auth bypass: %v", h)
	}
}

func TestRequestHeadersFor_UnrelatedPrefixGetsNoIdentity(t *testing.T) {
	sg := &ScopedGateway{}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@hellopro.fr")
	b := &BackendServer{ID: "srv-other", ToolPrefix: "semrush", AuthHeaders: map[string]string{}}
	h := sg.requestHeadersFor(ctx, b)
	if _, ok := h["X-End-User-Email"]; ok {
		t.Fatalf("identity must not leak to unrelated backends: %v", h)
	}
}
```

If `BDDAllowedTablesHeader` is not the exported constant name in `scoped_gateway.go`, run `grep -n "X-BDD-Allowed-Tables" internal/gateway/scoped_gateway.go` and use the constant found there (or the literal `"X-BDD-Allowed-Tables"`).

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/gateway/ -run 'Tables' 2>&1 | head -5`
Expected: `undefined: tablesToolPrefix`.

- [ ] **Step 3: Implement**

In `scoped_gateway.go`, after the `bddToolPrefix` constant block, add:

```go
// tablesToolPrefix identifies the mcp-table-service backend. The gateway
// forwards the end-user identity (X-End-User-Email / X-End-User-Login) to it
// so the service can act on the user's behalf against /api/v1/bdd/*. No
// filter header is injected: the user's gateway role decides, not an
// allow-list.
const tablesToolPrefix = "tables"
```

Add the shared helper and the tables injector next to `injectZohoIdentity`:

```go
// endUserIdentityHeaders copies the end-user email (and its login part, the
// local part before '@') from ctx into headers. ok=false when no end-user is
// on context: discovery, health probe, or a client_credentials grant.
func endUserIdentityHeaders(ctx context.Context, headers map[string]string) (email string, ok bool) {
	email, ok = scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return "", false
	}
	headers["X-End-User-Email"] = email
	if at := strings.IndexByte(email, '@'); at > 0 {
		headers["X-End-User-Login"] = email[:at]
	}
	return email, true
}

// injectTablesIdentity forwards the end-user identity to mcp-table-service.
// Called from both the normal path and the server-authorization bypass of
// requestHeadersFor — the service fails closed without an identity.
func (sg *ScopedGateway) injectTablesIdentity(ctx context.Context, headers map[string]string, backend *BackendServer) {
	if email, ok := endUserIdentityHeaders(ctx, headers); ok {
		log.Printf("[scoped] tables injectHeaders backend=%s email=%s — forwarding identity", backend.ID, email)
		return
	}
	log.Printf("[scoped] tables injectHeaders backend=%s NO end_user_email in ctx — discovery/health probe or non-OAuth2 grant", backend.ID)
}
```

Rewrite the body of `injectZohoIdentity` to use the helper (behaviour unchanged, log lines kept):

```go
func (sg *ScopedGateway) injectZohoIdentity(ctx context.Context, headers map[string]string, backend *BackendServer) {
	// Identity headers for mcp-zoho-service. Independent of the X-Zoho-Allowed-User
	// filter feature: these are always injected on Zoho backends when an end-user
	// is on context, so the downstream router can pick the right per-user upstream.
	if email, ok := endUserIdentityHeaders(ctx, headers); ok {
		log.Printf("[scoped] zoho injectHeaders backend=%s tool_prefix=%s email=%s — forwarding identity", backend.ID, backend.ToolPrefix, email)
	} else {
		log.Printf("[scoped] zoho injectHeaders backend=%s tool_prefix=%s NO end_user_email in ctx — discovery/health probe or non-OAuth2 grant", backend.ID, backend.ToolPrefix)
	}
}
```

In `requestHeadersFor`, inside the Step 0 bypass block, after the Zoho `if` and before `return headers`:

```go
		if backend.ToolPrefix == tablesToolPrefix {
			sg.injectTablesIdentity(ctx, headers, backend)
		}
```

And in the `switch backend.ToolPrefix` add:

```go
		case tablesToolPrefix:
			sg.injectTablesIdentity(ctx, headers, backend)
```

- [ ] **Step 4: Run the gateway package tests**

Run: `gofmt -l . ; go vet ./... && go test ./internal/gateway/ 2>&1 | tail -3`
Expected: gofmt silent; `ok  mcp-gateway/internal/gateway` (Zoho tests still pass).

- [ ] **Step 5: Commit**

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go \
        apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_tables_test.go
git commit -m "feat(mcp-gateway-service): forward end-user identity to the tables backend

EN: Backends with tool_prefix 'tables' receive X-End-User-Email/-Login, also inside the server-authorization bypass; Zoho identity injection now shares the same helper.
FR: Les backends au tool_prefix 'tables' recoivent X-End-User-Email/-Login, y compris dans le bypass server-authorization ; l'injection d'identite Zoho partage desormais le meme helper."
```

Note: `scoped_gateway.go` may hold unrelated uncommitted hunks from the backend-metadata work; use `git add -p` to stage only this task's hunks if so.

---

## Task 3: Service scaffold — module, MCP types, transports, identity middleware, boot

**Files:**
- Create: `apps-microservices/mcp-table-service/go.mod`
- Create: `apps-microservices/mcp-table-service/internal/mcp/types.go`
- Create: `apps-microservices/mcp-table-service/internal/config/config.go`
- Create: `apps-microservices/mcp-table-service/internal/transport/sse.go`, `streamable_http.go` (copies), `identity.go`, `identity_test.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/registry.go`, `handler.go`
- Create: `apps-microservices/mcp-table-service/cmd/server/main.go`
- Create: `apps-microservices/mcp-table-service/Dockerfile`

**Interfaces:**
- Produces: `transport.EndUserEmailFromContext(ctx) (string, bool)`, `transport.WithEndUserEmail(ctx, email) context.Context`, `transport.AdminTokenMiddleware(expected string) func(http.Handler) http.Handler`, `tools.Deps{Gateway *gateway.Client}` (the `gateway` package arrives in Task 4 — until then `Deps` is declared with a placeholder-free empty struct and extended in Task 4), `tools.ToolHandler`, `(*tools.Registry).register(name, description, inputSchema string, handler ToolHandler, ann *mcp.ToolAnnotations)`, `tools.errorResult`, `tools.jsonResult`, `mcp.ToolAnnotations{ReadOnlyHint, DestructiveHint *bool}`.

- [ ] **Step 1: Create the module and copy the protocol files from ringover**

```bash
cd /home/hellopro/RAG-HP-PUB/apps-microservices
mkdir -p mcp-table-service/{cmd/server,internal/{config,mcp,transport,tools,gateway}}
printf 'module github.com/hellopro/mcp-table\n\ngo 1.24\n' > mcp-table-service/go.mod
for f in internal/mcp/types.go internal/transport/sse.go internal/transport/streamable_http.go; do
  sed 's#github.com/hellopro/mcp-ringover#github.com/hellopro/mcp-table#g' "mcp-ringover-service/$f" > "mcp-table-service/$f"
done
```

The two transport files call `enrichRequestContext(r)`; that function is provided by `identity.go` below (ringover's `scope.go` is deliberately **not** copied).

- [ ] **Step 2: Add tool annotations to the MCP types**

In `mcp-table-service/internal/mcp/types.go`, replace the `Tool` struct with:

```go
type Tool struct {
	Name        string           `json:"name"`
	Description string           `json:"description,omitempty"`
	InputSchema json.RawMessage  `json:"inputSchema"`
	Annotations *ToolAnnotations `json:"annotations,omitempty"`
}

// ToolAnnotations are the MCP 2025-03-26 behavioural hints. Only the two we
// use are modelled; pointers so "unset" is omitted from JSON.
type ToolAnnotations struct {
	ReadOnlyHint    *bool `json:"readOnlyHint,omitempty"`
	DestructiveHint *bool `json:"destructiveHint,omitempty"`
}
```

- [ ] **Step 3: Write the failing identity tests**

Create `internal/transport/identity_test.go`:

```go
package transport

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnrichRequestContext_Email(t *testing.T) {
	r := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	r.Header.Set(EndUserEmailHeader, "  alice@hellopro.fr ")
	email, ok := EndUserEmailFromContext(enrichRequestContext(r))
	if !ok || email != "alice@hellopro.fr" {
		t.Fatalf("got (%q,%v)", email, ok)
	}
}

func TestEnrichRequestContext_NoHeader(t *testing.T) {
	r := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	if _, ok := EndUserEmailFromContext(enrichRequestContext(r)); ok {
		t.Fatal("expected no identity")
	}
}

func TestAdminTokenMiddleware(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	h := AdminTokenMiddleware("s3cret")(next)

	cases := []struct {
		name string
		path string
		tok  string
		want int
	}{
		{"valid", "/mcp", "s3cret", 200},
		{"wrong", "/mcp", "nope", 401},
		{"missing", "/mcp", "", 401},
		{"health exempt", "/health", "", 200},
		{"sse needs token", "/sse", "", 401},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := httptest.NewRequest(http.MethodPost, c.path, nil)
			if c.tok != "" {
				r.Header.Set(AdminTokenHeader, c.tok)
			}
			w := httptest.NewRecorder()
			h.ServeHTTP(w, r)
			if w.Code != c.want {
				t.Fatalf("status = %d, want %d", w.Code, c.want)
			}
		})
	}
}

func TestAdminTokenMiddleware_EmptyExpectedRejectsAll(t *testing.T) {
	h := AdminTokenMiddleware("")(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(200) }))
	r := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	r.Header.Set(AdminTokenHeader, "")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", w.Code)
	}
}
```

- [ ] **Step 4: Run to verify failure**

Run: `cd mcp-table-service && go test ./internal/transport/ 2>&1 | head -5`
Expected: `undefined: enrichRequestContext`, `undefined: EndUserEmailHeader`, `undefined: AdminTokenMiddleware`.

- [ ] **Step 5: Implement identity.go**

```go
package transport

import (
	"context"
	"crypto/subtle"
	"net/http"
	"strings"
)

// Headers exchanged with the MCP gateway.
const (
	// AdminTokenHeader carries the shared secret the gateway sets as a static
	// auth header on this backend's mcp_servers row. Every MCP request must
	// present it; GET /health is exempt.
	AdminTokenHeader = "X-Admin-Token"
	// EndUserEmailHeader is injected by the gateway (tool_prefix "tables")
	// with the OAuth2 access token's email claim. Absent on discovery, health
	// probes and scope-token calls.
	EndUserEmailHeader = "X-End-User-Email"
)

type ctxKey int

const endUserEmailKey ctxKey = iota

// enrichRequestContext lifts X-End-User-Email into the request context. Both
// transports call it on every inbound JSON-RPC message.
func enrichRequestContext(r *http.Request) context.Context {
	email := strings.TrimSpace(r.Header.Get(EndUserEmailHeader))
	if email == "" {
		return r.Context()
	}
	return WithEndUserEmail(r.Context(), email)
}

// WithEndUserEmail returns ctx carrying email as the acting end user.
func WithEndUserEmail(ctx context.Context, email string) context.Context {
	return context.WithValue(ctx, endUserEmailKey, email)
}

// EndUserEmailFromContext returns the acting end user's email. ok=false when
// the gateway forwarded no identity.
func EndUserEmailFromContext(ctx context.Context) (string, bool) {
	v, ok := ctx.Value(endUserEmailKey).(string)
	return v, ok && v != ""
}

// AdminTokenMiddleware rejects every request whose X-Admin-Token does not
// match expected (constant-time). /health stays reachable for probes. An
// empty expected value rejects everything — main.go refuses to boot without
// a token, this is defence in depth.
func AdminTokenMiddleware(expected string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/health" {
				next.ServeHTTP(w, r)
				return
			}
			got := r.Header.Get(AdminTokenHeader)
			if expected == "" || got == "" || subtle.ConstantTimeCompare([]byte(got), []byte(expected)) != 1 {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_, _ = w.Write([]byte(`{"error":"invalid_admin_token"}`))
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
```

- [ ] **Step 6: Run the transport tests**

Run: `go test ./internal/transport/ 2>&1 | tail -3`
Expected: `ok  github.com/hellopro/mcp-table/internal/transport`

- [ ] **Step 7: Config**

Create `internal/config/config.go`:

```go
package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port    string
	Name    string
	Version string

	// GatewayURL is the in-cluster base URL of mcp-gateway-service
	// (e.g. http://mcp-gateway-service:8592). Required.
	GatewayURL string
	// GatewayToken is the shared secret: checked on inbound X-Admin-Token and
	// sent on outbound X-Admin-Token. Must equal TABLE_SERVICE_TOKEN on the
	// gateway. Required.
	GatewayToken string
	// GatewayTimeout bounds each REST call to the gateway.
	GatewayTimeout time.Duration
}

func Load() *Config {
	return &Config{
		Port:           getEnv("MCP_PORT", "8597"),
		Name:           getEnv("MCP_SERVICE_NAME", "mcp-table"),
		Version:        getEnv("MCP_SERVICE_VERSION", "0.1.0"),
		GatewayURL:     getEnv("MCP_GATEWAY_URL", ""),
		GatewayToken:   getEnv("MCP_TABLE_GATEWAY_TOKEN", ""),
		GatewayTimeout: time.Duration(getEnvInt("MCP_GATEWAY_TIMEOUT", 15)) * time.Second,
	}
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getEnvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}
```

- [ ] **Step 8: Tool registry and MCP handler**

Create `internal/tools/registry.go`:

```go
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/hellopro/mcp-table/internal/mcp"
)

// Deps holds what tool handlers need. Gateway is added in the gateway-client task.
type Deps struct{}

// ToolHandler processes one tools/call and returns the result.
type ToolHandler func(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error)

type registeredTool struct {
	definition mcp.Tool
	handler    ToolHandler
}

// Registry manages all MCP tools.
type Registry struct {
	tools  []registeredTool
	byName map[string]*registeredTool
	deps   *Deps
}

// NewRegistry creates a registry with every tool registered. Tools are added
// group by group in later tasks (read, catalog, table, field).
func NewRegistry(deps *Deps) *Registry {
	r := &Registry{byName: make(map[string]*registeredTool), deps: deps}
	return r
}

func boolPtr(b bool) *bool { return &b }

// readOnly / destructive are the two annotation presets used by the tools.
var (
	readOnly    = &mcp.ToolAnnotations{ReadOnlyHint: boolPtr(true)}
	destructive = &mcp.ToolAnnotations{DestructiveHint: boolPtr(true)}
)

func (r *Registry) register(name, description, inputSchema string, handler ToolHandler, ann *mcp.ToolAnnotations) {
	t := registeredTool{
		definition: mcp.Tool{
			Name:        name,
			Description: description,
			InputSchema: json.RawMessage(inputSchema),
			Annotations: ann,
		},
		handler: handler,
	}
	r.tools = append(r.tools, t)
	r.byName[name] = &r.tools[len(r.tools)-1]
}

// ListTools returns all registered tool definitions.
func (r *Registry) ListTools() []mcp.Tool {
	out := make([]mcp.Tool, len(r.tools))
	for i, t := range r.tools {
		out[i] = t.definition
	}
	return out
}

// CallTool dispatches a tool call to its handler.
func (r *Registry) CallTool(ctx context.Context, params *mcp.CallToolParams) *mcp.CallToolResult {
	t, found := r.byName[params.Name]
	if !found {
		return errorResult(fmt.Sprintf("unknown tool: %s", params.Name))
	}
	args := params.Arguments
	if args == nil {
		args = map[string]any{}
	}
	result, err := t.handler(ctx, r.deps, args)
	if err != nil {
		log.Printf("[tools] error in %s: %v", params.Name, err)
		return errorResult(fmt.Sprintf("tool execution failed: %v", err))
	}
	return result
}

func errorResult(msg string) *mcp.CallToolResult {
	return &mcp.CallToolResult{Content: []mcp.ContentBlock{{Type: "text", Text: msg}}, IsError: true}
}

func textResult(text string) *mcp.CallToolResult {
	return &mcp.CallToolResult{Content: []mcp.ContentBlock{{Type: "text", Text: text}}}
}

func jsonResult(v any) *mcp.CallToolResult {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return errorResult(fmt.Sprintf("failed to marshal result: %v", err))
	}
	return textResult(string(b))
}
```

Copy the handler from ringover unchanged apart from the import path:

```bash
sed 's#github.com/hellopro/mcp-ringover#github.com/hellopro/mcp-table#g' \
  ../mcp-ringover-service/internal/tools/handler.go > internal/tools/handler.go
```

Then in `handleToolsCall` of the copied `internal/tools/handler.go`, change the log line so the acting user is visible:

```go
	if email, ok := transport.EndUserEmailFromContext(ctx); ok {
		log.Printf("[handler] tools/call: %s user=%s", params.Name, email)
	} else {
		log.Printf("[handler] tools/call: %s user=<none>", params.Name)
	}
```

and add `"github.com/hellopro/mcp-table/internal/transport"` to its imports.

- [ ] **Step 9: main.go**

```go
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/hellopro/mcp-table/internal/config"
	"github.com/hellopro/mcp-table/internal/tools"
	"github.com/hellopro/mcp-table/internal/transport"
)

func main() {
	cfg := config.Load()
	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	if cfg.GatewayURL == "" {
		log.Fatal("[main] FATAL: MCP_GATEWAY_URL is required")
	}
	if cfg.GatewayToken == "" {
		log.Fatal("[main] FATAL: MCP_TABLE_GATEWAY_TOKEN is required (shared secret with the gateway)")
	}

	deps := &tools.Deps{}
	registry := tools.NewRegistry(deps)
	handler := tools.NewMCPHandler(cfg.Name, cfg.Version, registry)

	mux := http.NewServeMux()
	transport.NewSSEServer(handler).Register(mux)
	transport.NewStreamableHTTPServer(handler).Register(mux)

	httpServer := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           transport.AdminTokenMiddleware(cfg.GatewayToken)(mux),
		ReadTimeout:       15 * time.Second,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      0, // SSE streams need unlimited write time
		IdleTimeout:       60 * time.Second,
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[main] server error: %v", err)
		}
	}()
	log.Printf("[main] ready — SSE: http://0.0.0.0:%s/sse | HTTP: http://0.0.0.0:%s/mcp | gateway=%s", cfg.Port, cfg.Port, cfg.GatewayURL)

	<-stop
	log.Println("[main] shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(ctx); err != nil {
		log.Printf("[main] shutdown error: %v", err)
	}
	log.Println("[main] stopped")
}
```

Task 4 changes `deps := &tools.Deps{}` to pass the gateway client.

- [ ] **Step 10: Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1
FROM golang:1.24-alpine AS builder
WORKDIR /src
COPY go.mod ./
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/mcp-table ./cmd/server

FROM alpine:3.20
RUN apk add --no-cache ca-certificates curl && adduser -D -u 10001 mcptable
USER mcptable
COPY --from=builder /out/mcp-table /usr/local/bin/mcp-table
EXPOSE 8597
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8597/health || exit 1
ENTRYPOINT ["/usr/local/bin/mcp-table"]
```

- [ ] **Step 11: Build, vet, test; smoke the handshake**

Run:
```bash
gofmt -l . ; go vet ./... && go build ./... && go test ./... 2>&1 | tail -8
MCP_GATEWAY_URL=http://localhost:1 MCP_TABLE_GATEWAY_TOKEN=t MCP_PORT=18597 go run ./cmd/server &
sleep 1
curl -s http://localhost:18597/health
curl -s -X POST http://localhost:18597/mcp -H 'X-Admin-Token: t' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:18597/mcp -d '{}'
kill %1
```
Expected: gofmt silent, all `ok`/no test files; `{"status":"ok"}`; `{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}`; `401`.

- [ ] **Step 12: Commit**

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-table-service
git commit -m "feat(mcp-table-service): scaffold Go MCP server with identity middleware

EN: New stdlib-only service (port 8597): SSE + streamable HTTP transports, X-Admin-Token gate, X-End-User-Email lifted into context, empty tool registry, Dockerfile.
FR: Nouveau service stdlib (port 8597) : transports SSE + HTTP streamable, garde X-Admin-Token, X-End-User-Email place dans le contexte, registre d'outils vide, Dockerfile."
```

---

## Task 4: Gateway REST client (`internal/gateway`)

**Files:**
- Create: `apps-microservices/mcp-table-service/internal/gateway/types.go`
- Create: `apps-microservices/mcp-table-service/internal/gateway/errors.go`
- Create: `apps-microservices/mcp-table-service/internal/gateway/client.go`
- Create: `apps-microservices/mcp-table-service/internal/gateway/client_test.go`
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go` (`Deps`)
- Modify: `apps-microservices/mcp-table-service/cmd/server/main.go` (construct the client)

**Interfaces:**
- Produces: `gateway.New(baseURL, token string, timeout time.Duration) *Client`; `(*Client).As(email string) *Session`; `(*Session).Email() string`; the `Session` methods listed in Step 3; `gateway.APIError{Status int; Message string; Body []byte}`; `gateway.IsStatus(err error, status int) bool`; all DTO types in `types.go`; `tools.Deps{Gateway *gateway.Client}`.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing client tests**

Create `internal/gateway/client_test.go`:

```go
package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

type captured struct {
	method, path, query, token, actAs, ctype string
	body                                    []byte
}

func newServer(t *testing.T, status int, respBody string, cap *captured) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		*cap = captured{r.Method, r.URL.Path, r.URL.RawQuery, r.Header.Get("X-Admin-Token"), r.Header.Get("X-Act-As-Email"), r.Header.Get("Content-Type"), b}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(respBody))
	}))
}

func TestListUsedTables_HeadersQueryAndDecode(t *testing.T) {
	var cap captured
	srv := newServer(t, 200, `{"tables":[{"id":"t1","database_id":5,"table_name":"produits","is_active":true,"fields":[]}],"total":1,"page":2,"limit":50}`, &cap)
	defer srv.Close()
	s := New(srv.URL, "s3cret", 2*time.Second).As("alice@hellopro.fr")

	res, err := s.ListUsedTables(context.Background(), ListParams{DatabaseID: 5, Search: "prod", Page: 2, Limit: 50})
	if err != nil {
		t.Fatal(err)
	}
	if cap.method != "GET" || cap.path != "/api/v1/bdd/used/tables" {
		t.Fatalf("request = %s %s", cap.method, cap.path)
	}
	if cap.query != "database_id=5&limit=50&page=2&search=prod" {
		t.Fatalf("query = %q", cap.query)
	}
	if cap.token != "s3cret" || cap.actAs != "alice@hellopro.fr" {
		t.Fatalf("headers token=%q actas=%q", cap.token, cap.actAs)
	}
	if res.Total != 1 || res.Page != 2 || len(res.Tables) != 1 || res.Tables[0].TableName != "produits" {
		t.Fatalf("decoded = %+v", res)
	}
}

func TestAPIError_MessageFromEnvelope(t *testing.T) {
	var cap captured
	srv := newServer(t, 403, `{"error":"insufficient permissions"}`, &cap)
	defer srv.Close()
	s := New(srv.URL, "s3cret", 2*time.Second).As("bob@hellopro.fr")

	_, err := s.GetUsedTable(context.Background(), "t1")
	var ae *APIError
	if !errors.As(err, &ae) || ae.Status != 403 || ae.Message != "insufficient permissions" {
		t.Fatalf("err = %v", err)
	}
	if !IsStatus(err, 403) || IsStatus(err, 404) {
		t.Fatal("IsStatus mismatch")
	}
	if cap.path != "/api/v1/bdd/used/tables/t1" {
		t.Fatalf("path = %s", cap.path)
	}
}

func TestAPIError_FallbackToStatusText(t *testing.T) {
	var cap captured
	srv := newServer(t, 502, `<html>bad gateway</html>`, &cap)
	defer srv.Close()
	_, err := New(srv.URL, "s3cret", time.Second).As("a@b").ListDatabases(context.Background())
	var ae *APIError
	if !errors.As(err, &ae) || ae.Message != "Bad Gateway" {
		t.Fatalf("err = %v", err)
	}
}

func TestBulkCreate_AllFailed400IsAResult(t *testing.T) {
	var cap captured
	srv := newServer(t, 400, `{"created":[],"errors":[{"table_name":"dup","error":"table already registered for this database"}]}`, &cap)
	defer srv.Close()
	res, err := New(srv.URL, "s3cret", time.Second).As("a@b").BulkCreateUsedTables(context.Background(), BulkCreateRequest{DatabaseID: 1, Items: []BulkCreateItem{{TableName: "dup"}}})
	if err != nil {
		t.Fatalf("expected envelope, got err %v", err)
	}
	if len(res.Errors) != 1 || res.Errors[0].TableName != "dup" {
		t.Fatalf("res = %+v", res)
	}
	if cap.method != "POST" || cap.path != "/api/v1/bdd/used/tables/bulk" || cap.ctype != "application/json" {
		t.Fatalf("request = %s %s %s", cap.method, cap.path, cap.ctype)
	}
	var sent BulkCreateRequest
	_ = json.Unmarshal(cap.body, &sent)
	if sent.DatabaseID != 1 || len(sent.Items) != 1 {
		t.Fatalf("sent = %+v", sent)
	}
}

func TestBulkCreate_Plain400IsAnError(t *testing.T) {
	var cap captured
	srv := newServer(t, 400, `{"error":"database_id must be one of 1, 5, 10"}`, &cap)
	defer srv.Close()
	_, err := New(srv.URL, "s3cret", time.Second).As("a@b").BulkCreateUsedTables(context.Background(), BulkCreateRequest{DatabaseID: 7})
	if !IsStatus(err, 400) {
		t.Fatalf("err = %v", err)
	}
}

func TestBulkSetActiveAndDelete(t *testing.T) {
	var cap captured
	srv := newServer(t, 200, `{"affected":3}`, &cap)
	defer srv.Close()
	s := New(srv.URL, "s3cret", time.Second).As("a@b")

	n, err := s.BulkSetActive(context.Background(), []string{"a", "b", "c"}, false)
	if err != nil || n != 3 {
		t.Fatalf("n=%d err=%v", n, err)
	}
	if cap.method != "PATCH" || cap.path != "/api/v1/bdd/used/tables/bulk" || string(cap.body) != `{"ids":["a","b","c"],"is_active":false}`+"\n" && string(cap.body) != `{"ids":["a","b","c"],"is_active":false}` {
		t.Fatalf("request = %s %s body=%s", cap.method, cap.path, cap.body)
	}

	n, err = s.BulkDeleteUsedTables(context.Background(), []string{"a"})
	if err != nil || n != 3 || cap.method != "DELETE" {
		t.Fatalf("n=%d err=%v method=%s", n, err, cap.method)
	}
}

func TestDeleteField_204(t *testing.T) {
	var cap captured
	srv := newServer(t, 204, ``, &cap)
	defer srv.Close()
	if err := New(srv.URL, "s3cret", time.Second).As("a@b").DeleteField(context.Background(), "t1", "f1"); err != nil {
		t.Fatal(err)
	}
	if cap.method != "DELETE" || cap.path != "/api/v1/bdd/used/tables/t1/fields/f1" {
		t.Fatalf("request = %s %s", cap.method, cap.path)
	}
}

func TestCatalogFields_PathAndDecode(t *testing.T) {
	var cap captured
	srv := newServer(t, 200, `{"fields":[{"id":9,"table_id":42,"field_name":"id","field_type":"int(11)"}],"primary":"id"}`, &cap)
	defer srv.Close()
	res, err := New(srv.URL, "s3cret", time.Second).As("a@b").ListCatalogFields(context.Background(), 5, 42)
	if err != nil {
		t.Fatal(err)
	}
	if cap.path != "/api/v1/bdd/catalog/databases/5/tables/42/fields" {
		t.Fatalf("path = %s", cap.path)
	}
	if res.Primary != "id" || len(res.Fields) != 1 || res.Fields[0].FieldType != "int(11)" {
		t.Fatalf("res = %+v", res)
	}
}

func TestTimeoutIsNotAnAPIError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(300 * time.Millisecond)
		w.WriteHeader(200)
	}))
	defer srv.Close()
	_, err := New(srv.URL, "s3cret", 50*time.Millisecond).As("a@b").ListDatabases(context.Background())
	var ae *APIError
	if err == nil || errors.As(err, &ae) {
		t.Fatalf("expected transport error, got %v", err)
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/hellopro/RAG-HP-PUB/apps-microservices/mcp-table-service && go test ./internal/gateway/ 2>&1 | head -5`
Expected: `undefined: New`, `undefined: ListParams` …

- [ ] **Step 3: Implement types.go, errors.go, client.go**

`internal/gateway/types.go`:

```go
// Package gateway is the typed HTTP client for mcp-gateway-service's
// /api/v1/bdd routes. DTOs mirror internal/api/bdd_dto.go and the catalog
// proxy in the gateway; keep field names in sync when the gateway changes.
package gateway

import "encoding/json"

type UsedField struct {
	ID              string `json:"id"`
	UsedTableID     string `json:"used_table_id"`
	FieldName       string `json:"field_name"`
	FieldType       string `json:"field_type,omitempty"`
	Description     string `json:"description"`
	UpstreamFieldID int    `json:"upstream_field_id,omitempty"`
}

type UsedTable struct {
	ID              string          `json:"id"`
	DatabaseID      int             `json:"database_id"`
	TableName       string          `json:"table_name"`
	Description     string          `json:"description"`
	UpstreamTableID int             `json:"upstream_table_id,omitempty"`
	Rows            *int64          `json:"rows"`
	PrimaryKey      string          `json:"primary_key"`
	DefaultOrderBy  string          `json:"default_order_by"`
	Relations       json.RawMessage `json:"relations,omitempty"`
	Notes           string          `json:"notes"`
	IsActive        bool            `json:"is_active"`
	CreatedBy       string          `json:"created_by,omitempty"`
	CreatedAt       string          `json:"created_at,omitempty"`
	UpdatedAt       string          `json:"updated_at,omitempty"`
	Fields          []UsedField     `json:"fields"`
}

type UsedListResponse struct {
	Tables []UsedTable `json:"tables"`
	Total  int64       `json:"total"`
	Page   int         `json:"page"`
	Limit  int         `json:"limit"`
}

// ListParams are the query parameters of GET /used/tables. Zero values are omitted.
type ListParams struct {
	DatabaseID int
	Search     string
	Page       int
	Limit      int
}

type BulkCreateItem struct {
	TableName       string `json:"table_name"`
	Description     string `json:"description,omitempty"`
	UpstreamTableID int    `json:"upstream_table_id,omitempty"`
}

type BulkCreateRequest struct {
	DatabaseID int              `json:"database_id"`
	Items      []BulkCreateItem `json:"items"`
}

type BulkCreateError struct {
	TableName string `json:"table_name"`
	Error     string `json:"error"`
}

type BulkCreateResponse struct {
	Created []UsedTable       `json:"created"`
	Errors  []BulkCreateError `json:"errors,omitempty"`
}

// PatchUsedTableRequest is PATCH /used/tables/{id}; nil pointers are omitted.
type PatchUsedTableRequest struct {
	Description    *string         `json:"description,omitempty"`
	DefaultOrderBy *string         `json:"default_order_by,omitempty"`
	Relations      json.RawMessage `json:"relations,omitempty"`
	Notes          *string         `json:"notes,omitempty"`
	Rows           *int64          `json:"rows,omitempty"`
}

type AddFieldRequest struct {
	FieldName       string `json:"field_name"`
	FieldType       string `json:"field_type,omitempty"`
	Description     string `json:"description,omitempty"`
	UpstreamFieldID int    `json:"upstream_field_id,omitempty"`
}

type SyncFieldTypesResponse struct {
	Updated int `json:"updated"`
	Total   int `json:"total"`
}

type Database struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

type CatalogTable struct {
	ID          int    `json:"id"`
	DatabaseID  int    `json:"database_id"`
	TableName   string `json:"table_name"`
	Description string `json:"description,omitempty"`
	FieldCount  int    `json:"field_count,omitempty"`
}

type CatalogField struct {
	ID          int    `json:"id"`
	TableID     int    `json:"table_id"`
	FieldName   string `json:"field_name"`
	FieldType   string `json:"field_type,omitempty"`
	IsNullable  bool   `json:"is_nullable,omitempty"`
	Description string `json:"description,omitempty"`
}

type CatalogFieldsResponse struct {
	Fields  []CatalogField `json:"fields"`
	Primary string         `json:"primary,omitempty"`
}
```

`internal/gateway/errors.go`:

```go
package gateway

import (
	"errors"
	"fmt"
)

// APIError is a non-2xx answer from the gateway. Message is the gateway's
// {"error":"..."} text when present, else the HTTP status text. Body keeps the
// raw payload so callers can reinterpret a 400 that is actually a result
// envelope (bulk create answers 400 with its normal body when every row failed).
type APIError struct {
	Status  int
	Message string
	Body    []byte
}

func (e *APIError) Error() string { return fmt.Sprintf("gateway %d: %s", e.Status, e.Message) }

// IsStatus reports whether err is an *APIError carrying status.
func IsStatus(err error, status int) bool {
	var ae *APIError
	return errors.As(err, &ae) && ae.Status == status
}
```

`internal/gateway/client.go`:

```go
package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	adminTokenHeader = "X-Admin-Token"
	actAsEmailHeader = "X-Act-As-Email"
	apiPrefix        = "/api/v1/bdd"
	maxErrorBody     = 64 << 10
)

// Client talks to the gateway's /api/v1/bdd routes. Safe for concurrent use.
// Bind it to an end user with As before making calls.
type Client struct {
	base  string
	token string
	http  *http.Client
}

// New builds a client for baseURL (e.g. http://mcp-gateway-service:8592) that
// authenticates with token in X-Admin-Token. timeout bounds each call.
func New(baseURL, token string, timeout time.Duration) *Client {
	return &Client{
		base:  strings.TrimRight(baseURL, "/"),
		token: token,
		http:  &http.Client{Timeout: timeout},
	}
}

// Session is a Client acting for one end user. Every request carries
// X-Admin-Token (service identity) and X-Act-As-Email (user identity); the
// gateway resolves the user's role from gateway_users and applies its own
// admin / read-only gate.
type Session struct {
	c     *Client
	email string
}

// As binds the client to the acting end user.
func (c *Client) As(email string) *Session { return &Session{c: c, email: email} }

// Email returns the acting end user's email.
func (s *Session) Email() string { return s.email }

func (s *Session) do(ctx context.Context, method, path string, query url.Values, body, out any) error {
	u := s.c.base + apiPrefix + path
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encode request: %w", err)
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, u, rdr)
	if err != nil {
		return err
	}
	req.Header.Set(adminTokenHeader, s.c.token)
	req.Header.Set(actAsEmailHeader, s.email)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := s.c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, maxErrorBody))
		msg := http.StatusText(resp.StatusCode)
		var env struct {
			Error string `json:"error"`
		}
		if json.Unmarshal(raw, &env) == nil && env.Error != "" {
			msg = env.Error
		}
		return &APIError{Status: resp.StatusCode, Message: msg, Body: raw}
	}
	if out == nil || resp.StatusCode == http.StatusNoContent {
		return nil
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("decode gateway response: %w", err)
	}
	return nil
}

func tablePath(id string) string { return "/used/tables/" + url.PathEscape(id) }

// ── Registry ─────────────────────────────────────────────────────────────

func (s *Session) ListUsedTables(ctx context.Context, p ListParams) (*UsedListResponse, error) {
	q := url.Values{}
	if p.DatabaseID != 0 {
		q.Set("database_id", strconv.Itoa(p.DatabaseID))
	}
	if p.Search != "" {
		q.Set("search", p.Search)
	}
	if p.Page > 0 {
		q.Set("page", strconv.Itoa(p.Page))
	}
	if p.Limit > 0 {
		q.Set("limit", strconv.Itoa(p.Limit))
	}
	var out UsedListResponse
	if err := s.do(ctx, http.MethodGet, "/used/tables", q, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (s *Session) GetUsedTable(ctx context.Context, id string) (*UsedTable, error) {
	var out UsedTable
	if err := s.do(ctx, http.MethodGet, tablePath(id), nil, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// BulkCreateUsedTables registers tables. The gateway answers 201 (all
// created), 200 (mixed) or 400 with the SAME envelope when every row failed;
// that last case is returned as a result, not an error.
func (s *Session) BulkCreateUsedTables(ctx context.Context, req BulkCreateRequest) (*BulkCreateResponse, error) {
	var out BulkCreateResponse
	err := s.do(ctx, http.MethodPost, "/used/tables/bulk", nil, req, &out)
	if err != nil {
		var ae *APIError
		if errors.As(err, &ae) && ae.Status == http.StatusBadRequest {
			var env BulkCreateResponse
			if json.Unmarshal(ae.Body, &env) == nil && len(env.Errors) > 0 {
				return &env, nil
			}
		}
		return nil, err
	}
	return &out, nil
}

func (s *Session) PatchUsedTable(ctx context.Context, id string, req PatchUsedTableRequest) (*UsedTable, error) {
	var out UsedTable
	if err := s.do(ctx, http.MethodPatch, tablePath(id), nil, req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

type bulkIDsRequest struct {
	IDs      []string `json:"ids"`
	IsActive *bool    `json:"is_active,omitempty"`
}

type affectedResponse struct {
	Affected int64 `json:"affected"`
}

// BulkSetActive flips is_active on ids. Returns the number of rows affected.
func (s *Session) BulkSetActive(ctx context.Context, ids []string, active bool) (int64, error) {
	var out affectedResponse
	if err := s.do(ctx, http.MethodPatch, "/used/tables/bulk", nil, bulkIDsRequest{IDs: ids, IsActive: &active}, &out); err != nil {
		return 0, err
	}
	return out.Affected, nil
}

// BulkDeleteUsedTables removes ids (fields cascade). Returns rows affected.
func (s *Session) BulkDeleteUsedTables(ctx context.Context, ids []string) (int64, error) {
	var out affectedResponse
	if err := s.do(ctx, http.MethodDelete, "/used/tables/bulk", nil, bulkIDsRequest{IDs: ids}, &out); err != nil {
		return 0, err
	}
	return out.Affected, nil
}

// ── Fields ───────────────────────────────────────────────────────────────

func (s *Session) AddField(ctx context.Context, tableID string, req AddFieldRequest) (*UsedField, error) {
	var out UsedField
	if err := s.do(ctx, http.MethodPost, tablePath(tableID)+"/fields", nil, req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (s *Session) PatchFieldDescription(ctx context.Context, tableID, fieldID, description string) (*UsedField, error) {
	var out UsedField
	body := struct {
		Description string `json:"description"`
	}{description}
	if err := s.do(ctx, http.MethodPatch, tablePath(tableID)+"/fields/"+url.PathEscape(fieldID), nil, body, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (s *Session) DeleteField(ctx context.Context, tableID, fieldID string) error {
	return s.do(ctx, http.MethodDelete, tablePath(tableID)+"/fields/"+url.PathEscape(fieldID), nil, nil, nil)
}

// ── Catalog-backed maintenance ───────────────────────────────────────────

// RefreshCatalog pulls primary key + row count from the upstream catalog.
// Gateway: 422 when the table has no upstream link, 502/503 when the catalog is down.
func (s *Session) RefreshCatalog(ctx context.Context, tableID string) (*UsedTable, error) {
	var out UsedTable
	if err := s.do(ctx, http.MethodPost, tablePath(tableID)+"/refresh-catalog", nil, struct{}{}, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (s *Session) SyncFieldTypes(ctx context.Context, tableID string) (*SyncFieldTypesResponse, error) {
	var out SyncFieldTypesResponse
	if err := s.do(ctx, http.MethodPost, tablePath(tableID)+"/sync-field-types", nil, struct{}{}, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ── Catalog (read-only proxy, admin-only on the gateway) ─────────────────

func (s *Session) ListDatabases(ctx context.Context) ([]Database, error) {
	var out struct {
		Databases []Database `json:"databases"`
	}
	if err := s.do(ctx, http.MethodGet, "/catalog/databases", nil, nil, &out); err != nil {
		return nil, err
	}
	return out.Databases, nil
}

func (s *Session) ListCatalogTables(ctx context.Context, databaseID int, search string) ([]CatalogTable, error) {
	q := url.Values{}
	if search != "" {
		q.Set("search", search)
	}
	var out struct {
		Tables []CatalogTable `json:"tables"`
	}
	if err := s.do(ctx, http.MethodGet, "/catalog/databases/"+strconv.Itoa(databaseID)+"/tables", q, nil, &out); err != nil {
		return nil, err
	}
	return out.Tables, nil
}

func (s *Session) ListCatalogFields(ctx context.Context, databaseID, tableID int) (*CatalogFieldsResponse, error) {
	var out CatalogFieldsResponse
	if err := s.do(ctx, http.MethodGet, "/catalog/databases/"+strconv.Itoa(databaseID)+"/tables/"+strconv.Itoa(tableID)+"/fields", nil, nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}
```

- [ ] **Step 4: Run the client tests**

Run: `go test ./internal/gateway/ 2>&1 | tail -3`
Expected: `ok  github.com/hellopro/mcp-table/internal/gateway`

- [ ] **Step 5: Wire the client into Deps and main**

In `internal/tools/registry.go` replace `type Deps struct{}` (and its comment) with:

```go
// Deps holds what tool handlers need: the gateway client, bound per call to
// the acting end user via requireSession.
type Deps struct {
	Gateway *gateway.Client
}
```

and add `"github.com/hellopro/mcp-table/internal/gateway"` to its imports.

In `cmd/server/main.go`, replace `deps := &tools.Deps{}` with:

```go
	deps := &tools.Deps{Gateway: gateway.New(cfg.GatewayURL, cfg.GatewayToken, cfg.GatewayTimeout)}
```

and import `"github.com/hellopro/mcp-table/internal/gateway"`.

- [ ] **Step 6: Verify and commit**

Run: `gofmt -l . ; go vet ./... && go build ./... && go test ./... 2>&1 | tail -8`
Expected: gofmt silent, all `ok`.

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-table-service
git commit -m "feat(mcp-table-service): typed act-as client for the gateway BDD REST routes

EN: Session bound to the end user sends X-Admin-Token + X-Act-As-Email; one method per /api/v1/bdd route; APIError with envelope message; bulk-create 400 envelope returned as a result.
FR: Session liee a l'utilisateur final envoie X-Admin-Token + X-Act-As-Email ; une methode par route /api/v1/bdd ; APIError avec le message de l'enveloppe ; l'enveloppe 400 du bulk-create est renvoyee comme resultat."
```

---

## Task 5: Tool infrastructure — arguments, session, error mapping, resolution, status, relations

**Files:**
- Create: `apps-microservices/mcp-table-service/internal/tools/args.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/session.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/errors.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/resolve.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/status.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/relations.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/testutil_test.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/infra_test.go`

**Interfaces:**
- Produces (all package-private, used by every tool task):
  - `argString(args, key) string`, `argInt(args, key) (int, bool)`, `argBool(args, key) (bool, bool)`, `argStringList(args, key) ([]string, error)`, `argObjectList(args, key) ([]map[string]any, error)`, `argDatabaseID(args, required bool) (int, error)`, `checkBatch(key string, n int) error`, `maxBatch = 50`, `invalidArgs(err) *mcp.CallToolResult`
  - `requireSession(ctx, deps) (*gateway.Session, *mcp.CallToolResult)`
  - `errNoIdentity`, `roleAdmin`, `roleReadOnly`, `gatewayErrorText(err, action, role, notFound) string`, `gatewayError(...) *mcp.CallToolResult`
  - `resolveTable(ctx, sess, args) (*gateway.UsedTable, *mcp.CallToolResult)`, `findRegisteredByName(ctx, sess, databaseID, name) (*gateway.UsedTable, error)`, `registeredByName(ctx, sess, databaseID) (map[string]gateway.UsedTable, error)`, `findCatalogTable(ctx, sess, databaseID, name) (*gateway.CatalogTable, error)`
  - `StatusActive/StatusDraft/StatusInactive`, `tableStatus(t) string`, `missingChecklist(t) []string`, `tableSummary`, `summarize(t) tableSummary`, `tableDetail`, `detail(t) tableDetail`
  - `RelationRow{SelfCol, TargetTable, TargetCol}`, `parseRelations(raw) []RelationRow`, `serializeRelations(selfTable, rows) (json.RawMessage, error)`, `identRe`
  - test helpers: `newFakeGateway(t) *fakeGateway`, `(*fakeGateway).on(method, path, handler)`, `(*fakeGateway).json(status, v) http.HandlerFunc`, `(*fakeGateway).deps() *Deps`, `(*fakeGateway).calls(method, path) []recordedCall`, `userCtx(email) context.Context`, `resultText(res) string`, `decodeResult(t, res, out)`

- [ ] **Step 1: Write the test helpers**

Create `internal/tools/testutil_test.go`:

```go
package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
	"github.com/hellopro/mcp-table/internal/transport"
)

type recordedCall struct {
	Method, Path, Query, ActAs, Token string
	Body                              []byte
}

// fakeGateway serves canned handlers keyed by "METHOD /path" and records every call.
// Unregistered routes answer 418 so a wrong path shows up as an APIError in the test.
type fakeGateway struct {
	t      *testing.T
	srv    *httptest.Server
	mu     sync.Mutex
	rec    []recordedCall
	routes map[string]http.HandlerFunc
}

func newFakeGateway(t *testing.T) *fakeGateway {
	f := &fakeGateway{t: t, routes: map[string]http.HandlerFunc{}}
	f.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		f.mu.Lock()
		f.rec = append(f.rec, recordedCall{r.Method, r.URL.Path, r.URL.RawQuery, r.Header.Get("X-Act-As-Email"), r.Header.Get("X-Admin-Token"), body})
		f.mu.Unlock()
		r.Body = io.NopCloser(bytes.NewReader(body))
		if h, ok := f.routes[r.Method+" "+r.URL.Path]; ok {
			h(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTeapot)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "unexpected route " + r.Method + " " + r.URL.Path})
	}))
	t.Cleanup(f.srv.Close)
	return f
}

func (f *fakeGateway) on(method, path string, h http.HandlerFunc) { f.routes[method+" "+path] = h }

func (f *fakeGateway) json(status int, v any) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(v)
	}
}

func (f *fakeGateway) deps() *Deps {
	return &Deps{Gateway: gateway.New(f.srv.URL, "s3cret", 5*time.Second)}
}

func (f *fakeGateway) calls(method, path string) []recordedCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	var out []recordedCall
	for _, c := range f.rec {
		if c.Method == method && c.Path == path {
			out = append(out, c)
		}
	}
	return out
}

func userCtx(email string) context.Context {
	return transport.WithEndUserEmail(context.Background(), email)
}

func resultText(res *mcp.CallToolResult) string {
	if res == nil || len(res.Content) == 0 {
		return ""
	}
	return res.Content[0].Text
}

func decodeResult(t *testing.T, res *mcp.CallToolResult, out any) {
	t.Helper()
	if res.IsError {
		t.Fatalf("unexpected error result: %s", resultText(res))
	}
	if err := json.Unmarshal([]byte(resultText(res)), out); err != nil {
		t.Fatalf("result is not JSON: %v\n%s", err, resultText(res))
	}
}

func rowsPtr(n int64) *int64 { return &n }

// sampleTable is a registered table with one field, active → status "active".
func sampleTable() gateway.UsedTable {
	return gateway.UsedTable{
		ID: "t-1", DatabaseID: 5, TableName: "produits", Description: "Catalogue produits",
		UpstreamTableID: 42, Rows: rowsPtr(1200), PrimaryKey: "id", IsActive: true,
		Relations: json.RawMessage(`{"categories":"produits.categorie_id -> categories.id"}`),
		Fields: []gateway.UsedField{{ID: "f-1", UsedTableID: "t-1", FieldName: "id", FieldType: "int", Description: "PK"}},
	}
}
```

- [ ] **Step 2: Write the failing infra tests**

Create `internal/tools/infra_test.go`:

```go
package tools

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"testing"

	"github.com/hellopro/mcp-table/internal/gateway"
)

func TestArgInt(t *testing.T) {
	args := map[string]any{"a": float64(5), "b": "10", "c": 2.5, "d": "x"}
	if v, ok := argInt(args, "a"); !ok || v != 5 {
		t.Fatalf("a = %d %v", v, ok)
	}
	if v, ok := argInt(args, "b"); !ok || v != 10 {
		t.Fatalf("b = %d %v", v, ok)
	}
	if _, ok := argInt(args, "c"); ok {
		t.Fatal("2.5 must not be an int")
	}
	if _, ok := argInt(args, "d"); ok {
		t.Fatal("'x' must not be an int")
	}
	if _, ok := argInt(args, "missing"); ok {
		t.Fatal("missing must be !ok")
	}
}

func TestArgDatabaseID(t *testing.T) {
	if id, err := argDatabaseID(map[string]any{"database_id": float64(10)}, true); err != nil || id != 10 {
		t.Fatalf("id=%d err=%v", id, err)
	}
	if _, err := argDatabaseID(map[string]any{"database_id": float64(7)}, true); err == nil {
		t.Fatal("7 must be rejected")
	}
	if _, err := argDatabaseID(map[string]any{}, true); err == nil {
		t.Fatal("required must fail when absent")
	}
	if id, err := argDatabaseID(map[string]any{}, false); err != nil || id != 0 {
		t.Fatalf("optional absent → 0,nil got %d %v", id, err)
	}
}

func TestArgLists(t *testing.T) {
	args := map[string]any{"names": []any{" a ", "b"}, "bad": []any{"a", 3}, "objs": []any{map[string]any{"x": 1}}}
	got, err := argStringList(args, "names")
	if err != nil || len(got) != 2 || got[0] != "a" {
		t.Fatalf("got %v err %v", got, err)
	}
	if _, err := argStringList(args, "bad"); err == nil {
		t.Fatal("mixed list must fail")
	}
	if got, err := argStringList(args, "absent"); err != nil || got != nil {
		t.Fatalf("absent → nil,nil got %v %v", got, err)
	}
	objs, err := argObjectList(args, "objs")
	if err != nil || len(objs) != 1 {
		t.Fatalf("objs %v %v", objs, err)
	}
	if err := checkBatch("ids", 0); err == nil {
		t.Fatal("0 items must fail")
	}
	if err := checkBatch("ids", 51); err == nil {
		t.Fatal("51 items must fail")
	}
	if err := checkBatch("ids", 50); err != nil {
		t.Fatal(err)
	}
}

func TestTableStatusAndChecklist(t *testing.T) {
	tb := sampleTable()
	if tableStatus(&tb) != StatusActive {
		t.Fatalf("status = %s", tableStatus(&tb))
	}
	if m := missingChecklist(&tb); len(m) != 0 {
		t.Fatalf("complete table must have empty checklist, got %v", m)
	}
	tb.Fields = nil
	if tableStatus(&tb) != StatusDraft {
		t.Fatalf("status = %s", tableStatus(&tb))
	}
	tb.IsActive = false
	if tableStatus(&tb) != StatusInactive {
		t.Fatalf("status = %s", tableStatus(&tb))
	}
	empty := gateway.UsedTable{IsActive: true, Fields: []gateway.UsedField{{FieldName: "a"}, {FieldName: "b", Description: "ok"}}}
	got := strings.Join(missingChecklist(&empty), ",")
	want := "empty_description,fields_without_description:1,unknown_primary_key,unknown_rows"
	if got != want {
		t.Fatalf("checklist = %s, want %s", got, want)
	}
	bare := gateway.UsedTable{IsActive: true}
	if !strings.HasPrefix(strings.Join(missingChecklist(&bare), ","), "no_fields,") {
		t.Fatalf("checklist = %v", missingChecklist(&bare))
	}
}

func TestRelationsRoundTrip(t *testing.T) {
	rows := parseRelations(json.RawMessage(`{"categories":"produits.categorie_id -> categories.id","weird":"???"}`))
	if len(rows) != 2 || rows[0] != (RelationRow{"categorie_id", "categories", "id"}) || rows[1] != (RelationRow{"", "weird", ""}) {
		t.Fatalf("rows = %+v", rows)
	}
	if got := parseRelations(json.RawMessage(`[]`)); len(got) != 0 {
		t.Fatalf("[] → none, got %v", got)
	}
	if got := parseRelations(json.RawMessage(`null`)); len(got) != 0 {
		t.Fatalf("null → none, got %v", got)
	}
	if got := parseRelations(nil); len(got) != 0 {
		t.Fatalf("nil → none, got %v", got)
	}

	raw, err := serializeRelations("produits", []RelationRow{{"categorie_id", "categories", "id"}})
	if err != nil || string(raw) != `{"categories":"produits.categorie_id -> categories.id"}` {
		t.Fatalf("raw=%s err=%v", raw, err)
	}
	raw, err = serializeRelations("produits", nil)
	if err != nil || string(raw) != `[]` {
		t.Fatalf("empty → [] got %s %v", raw, err)
	}
	if _, err := serializeRelations("produits", []RelationRow{{"", "categories", "id"}}); err == nil {
		t.Fatal("empty self_col must fail")
	}
	if _, err := serializeRelations("produits", []RelationRow{{"a b", "categories", "id"}}); err == nil {
		t.Fatal("non-identifier must fail")
	}
}

func TestGatewayErrorText(t *testing.T) {
	api := func(status int, msg string) error { return &gateway.APIError{Status: status, Message: msg} }
	cases := []struct {
		err  error
		want string
	}{
		{api(403, "insufficient permissions"), "Your gateway role does not allow this action (add tables requires role admin). Ask a gateway admin."},
		{api(401, "not authenticated"), "The table service is not authorized on the gateway (shared secret mismatch)."},
		{api(404, "table not found"), "Table not found"},
		{api(409, "table already registered for this database"), "table already registered for this database"},
		{api(400, "database_id must be one of 1, 5, 10"), "database_id must be one of 1, 5, 10"},
		{api(422, "table has no upstream catalog link (upstream_table_id missing)"), "table has no upstream catalog link (upstream_table_id missing)"},
		{api(503, "BDD catalog not configured"), "Upstream BDD catalog unavailable: BDD catalog not configured"},
		{api(502, "upstream timeout"), "Upstream BDD catalog unavailable: upstream timeout"},
		{errors.New("dial tcp: connection refused"), "Gateway unreachable: dial tcp: connection refused"},
	}
	for _, c := range cases {
		if got := gatewayErrorText(c.err, "add tables", roleAdmin, "Table not found"); got != c.want {
			t.Errorf("%v → %q, want %q", c.err, got, c.want)
		}
	}
}

func TestRequireSession_NoIdentity(t *testing.T) {
	f := newFakeGateway(t)
	sess, res := requireSession(context.Background(), f.deps())
	if sess != nil || res == nil || !res.IsError || resultText(res) != errNoIdentity {
		t.Fatalf("sess=%v res=%v", sess, res)
	}
	sess, res = requireSession(userCtx("alice@hellopro.fr"), f.deps())
	if sess == nil || res != nil || sess.Email() != "alice@hellopro.fr" {
		t.Fatalf("sess=%v res=%v", sess, res)
	}
}

func TestResolveTable_ByIDAndByName(t *testing.T) {
	f := newFakeGateway(t)
	tb := sampleTable()
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, tb))
	f.on("GET", "/api/v1/bdd/used/tables", func(w http.ResponseWriter, r *http.Request) {
		// substring search returns a near-miss first, exact match second
		near := tb
		near.ID, near.TableName = "t-9", "produits_archive"
		f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{near, tb}, Total: 2, Page: 1, Limit: 100})(w, r)
	})
	sess := f.deps().Gateway.As("alice@hellopro.fr")

	got, res := resolveTable(context.Background(), sess, map[string]any{"table_id": "t-1"})
	if res != nil || got.ID != "t-1" {
		t.Fatalf("by id: %v %v", got, res)
	}
	got, res = resolveTable(context.Background(), sess, map[string]any{"database_id": float64(5), "table_name": "PRODUITS"})
	if res != nil || got.ID != "t-1" {
		t.Fatalf("by name: %v %v", got, res)
	}
	if q := f.calls("GET", "/api/v1/bdd/used/tables")[0].Query; !strings.Contains(q, "database_id=5") || !strings.Contains(q, "search=PRODUITS") {
		t.Fatalf("query = %s", q)
	}
	_, res = resolveTable(context.Background(), sess, map[string]any{})
	if res == nil || !res.IsError {
		t.Fatal("no address must be an error")
	}
	_, res = resolveTable(context.Background(), sess, map[string]any{"table_name": "nope"})
	if res == nil || !strings.Contains(resultText(res), `Table not found: "nope"`) {
		t.Fatalf("res = %v", res)
	}
}

func TestResolveTable_404(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/missing", f.json(404, map[string]string{"error": "table not found"}))
	_, res := resolveTable(context.Background(), f.deps().Gateway.As("a@b"), map[string]any{"table_id": "missing"})
	if res == nil || resultText(res) != "Table not found: missing" {
		t.Fatalf("res = %v", res)
	}
}

func TestFindCatalogTable_ExactMatchOnly(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{
		{ID: 41, DatabaseID: 5, TableName: "produits_archive"}, {ID: 42, DatabaseID: 5, TableName: "produits"},
	}}))
	sess := f.deps().Gateway.As("a@b")
	got, err := findCatalogTable(context.Background(), sess, 5, "Produits")
	if err != nil || got == nil || got.ID != 42 {
		t.Fatalf("got %v err %v", got, err)
	}
	got, err = findCatalogTable(context.Background(), sess, 5, "clients")
	if err != nil || got != nil {
		t.Fatalf("expected nil,nil got %v %v", got, err)
	}
}
```

- [ ] **Step 3: Run to verify failure**

Run: `go test ./internal/tools/ 2>&1 | head -5`
Expected: many `undefined:` errors.

- [ ] **Step 4: Implement args.go**

```go
package tools

import (
	"fmt"
	"math"
	"strings"

	"github.com/hellopro/mcp-table/internal/mcp"
)

// maxBatch mirrors the gateway's bulk cap (bddBulkMaxItems = 50).
const maxBatch = 50

var validDatabaseIDs = map[int]bool{1: true, 5: true, 10: true}

const databaseHint = "1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA"

// argString returns the trimmed string at key; "" when absent or not a string.
func argString(args map[string]any, key string) string {
	s, _ := args[key].(string)
	return strings.TrimSpace(s)
}

// argInt returns the integer at key. JSON numbers arrive as float64; integral
// strings are accepted too because some MCP clients stringify numbers.
func argInt(args map[string]any, key string) (int, bool) {
	switch v := args[key].(type) {
	case float64:
		if v != math.Trunc(v) {
			return 0, false
		}
		return int(v), true
	case int:
		return v, true
	case string:
		var n int
		if _, err := fmt.Sscanf(strings.TrimSpace(v), "%d", &n); err == nil {
			return n, true
		}
	}
	return 0, false
}

func argBool(args map[string]any, key string) (bool, bool) {
	b, ok := args[key].(bool)
	return b, ok
}

// argStringList returns the non-empty trimmed strings at key. Absent → nil, nil.
func argStringList(args map[string]any, key string) ([]string, error) {
	raw, present := args[key]
	if !present || raw == nil {
		return nil, nil
	}
	items, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("'%s' must be an array of strings", key)
	}
	out := make([]string, 0, len(items))
	for i, it := range items {
		s, ok := it.(string)
		if !ok || strings.TrimSpace(s) == "" {
			return nil, fmt.Errorf("'%s[%d]' must be a non-empty string", key, i)
		}
		out = append(out, strings.TrimSpace(s))
	}
	return out, nil
}

// argObjectList returns the objects at key. Absent → nil, nil.
func argObjectList(args map[string]any, key string) ([]map[string]any, error) {
	raw, present := args[key]
	if !present || raw == nil {
		return nil, nil
	}
	items, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("'%s' must be an array of objects", key)
	}
	out := make([]map[string]any, 0, len(items))
	for i, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("'%s[%d]' must be an object", key, i)
		}
		out = append(out, m)
	}
	return out, nil
}

// checkBatch enforces 1..maxBatch items for a batch argument.
func checkBatch(key string, n int) error {
	if n == 0 {
		return fmt.Errorf("'%s' must contain at least one item", key)
	}
	if n > maxBatch {
		return fmt.Errorf("'%s' has %d items, max %d per call", key, n, maxBatch)
	}
	return nil
}

// argDatabaseID validates database_id. required=false returns 0,nil when absent.
func argDatabaseID(args map[string]any, required bool) (int, error) {
	id, ok := argInt(args, "database_id")
	if !ok {
		if required {
			return 0, fmt.Errorf("'database_id' is required (%s)", databaseHint)
		}
		return 0, nil
	}
	if !validDatabaseIDs[id] {
		return 0, fmt.Errorf("'database_id' must be one of %s", databaseHint)
	}
	return id, nil
}

func invalidArgs(err error) *mcp.CallToolResult {
	return errorResult("invalid arguments: " + err.Error())
}
```

- [ ] **Step 5: Implement session.go and errors.go**

`internal/tools/session.go`:

```go
package tools

import (
	"context"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
	"github.com/hellopro/mcp-table/internal/transport"
)

// requireSession binds the gateway client to the acting end user. It returns
// an MCP error result when the gateway forwarded no identity: the service
// fails closed rather than acting anonymously.
func requireSession(ctx context.Context, deps *Deps) (*gateway.Session, *mcp.CallToolResult) {
	if deps == nil || deps.Gateway == nil {
		return nil, errorResult("gateway client is not configured")
	}
	email, ok := transport.EndUserEmailFromContext(ctx)
	if !ok {
		return nil, errorResult(errNoIdentity)
	}
	return deps.Gateway.As(email), nil
}
```

`internal/tools/errors.go`:

```go
package tools

import (
	"errors"
	"fmt"
	"log"
	"net/http"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// errNoIdentity is returned by every tool when the gateway forwarded no end-user.
const errNoIdentity = "No end-user identity. Connect through the gateway with an OAuth2 user login; scope tokens are not supported by this service."

// Minimum gateway roles, as named in gateway_users.role.
const (
	roleAdmin    = "admin"
	roleReadOnly = "read-only"
)

// gatewayErrorText maps a gateway client error to the user-facing text of the
// spec (§7). action names what was attempted ("add tables"), role is the
// minimum gateway role for it, notFound is the 404 text.
func gatewayErrorText(err error, action, role, notFound string) string {
	var ae *gateway.APIError
	if !errors.As(err, &ae) {
		return "Gateway unreachable: " + err.Error()
	}
	switch ae.Status {
	case http.StatusForbidden:
		return fmt.Sprintf("Your gateway role does not allow this action (%s requires role %s). Ask a gateway admin.", action, role)
	case http.StatusUnauthorized:
		log.Printf("[tools] CONFIGURATION ERROR: gateway rejected the service credentials (401) — TABLE_SERVICE_TOKEN and MCP_TABLE_GATEWAY_TOKEN must match")
		return "The table service is not authorized on the gateway (shared secret mismatch)."
	case http.StatusNotFound:
		return notFound
	case http.StatusBadGateway, http.StatusServiceUnavailable:
		return "Upstream BDD catalog unavailable: " + ae.Message
	default:
		return ae.Message
	}
}

func gatewayError(err error, action, role, notFound string) *mcp.CallToolResult {
	return errorResult(gatewayErrorText(err, action, role, notFound))
}
```

- [ ] **Step 6: Implement status.go and relations.go**

`internal/tools/status.go`:

```go
package tools

import (
	"fmt"
	"strings"

	"github.com/hellopro/mcp-table/internal/gateway"
)

// Computed table status. The DB flag alone is not enough: the "Tables BDD"
// page shows a flagged table with zero fields as "Brouillon" and the fields
// page requires at least one field to consider the table activated.
const (
	StatusActive   = "active"
	StatusDraft    = "draft"
	StatusInactive = "inactive"
)

func tableStatus(t *gateway.UsedTable) string {
	switch {
	case !t.IsActive:
		return StatusInactive
	case len(t.Fields) == 0:
		return StatusDraft
	default:
		return StatusActive
	}
}

// missingChecklist lists what is left to complete a table. Empty when complete.
func missingChecklist(t *gateway.UsedTable) []string {
	out := []string{}
	if len(t.Fields) == 0 {
		out = append(out, "no_fields")
	}
	if strings.TrimSpace(t.Description) == "" {
		out = append(out, "empty_description")
	}
	n := 0
	for _, f := range t.Fields {
		if strings.TrimSpace(f.Description) == "" {
			n++
		}
	}
	if n > 0 {
		out = append(out, fmt.Sprintf("fields_without_description:%d", n))
	}
	if t.PrimaryKey == "" {
		out = append(out, "unknown_primary_key")
	}
	if t.Rows == nil {
		out = append(out, "unknown_rows")
	}
	return out
}

// tableSummary is one row of list_registered_tables.
type tableSummary struct {
	ID          string `json:"id"`
	DatabaseID  int    `json:"database_id"`
	TableName   string `json:"table_name"`
	Description string `json:"description"`
	IsActive    bool   `json:"is_active"`
	Status      string `json:"status"`
	FieldCount  int    `json:"field_count"`
	PrimaryKey  string `json:"primary_key"`
	Rows        *int64 `json:"rows"`
	CreatedBy   string `json:"created_by,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

func summarize(t *gateway.UsedTable) tableSummary {
	return tableSummary{
		ID: t.ID, DatabaseID: t.DatabaseID, TableName: t.TableName, Description: t.Description,
		IsActive: t.IsActive, Status: tableStatus(t), FieldCount: len(t.Fields),
		PrimaryKey: t.PrimaryKey, Rows: t.Rows, CreatedBy: t.CreatedBy, UpdatedAt: t.UpdatedAt,
	}
}

// tableDetail is the full view returned by get_table_info and the write tools.
type tableDetail struct {
	gateway.UsedTable
	Status       string        `json:"status"`
	Missing      []string      `json:"missing"`
	RelationRows []RelationRow `json:"relation_rows"`
}

func detail(t *gateway.UsedTable) tableDetail {
	return tableDetail{UsedTable: *t, Status: tableStatus(t), Missing: missingChecklist(t), RelationRows: parseRelations(t.Relations)}
}
```

`internal/tools/relations.go`:

```go
package tools

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
)

// RelationRow is the editable form of one relation, as on the fields page.
type RelationRow struct {
	SelfCol     string `json:"self_col"`
	TargetTable string `json:"target_table"`
	TargetCol   string `json:"target_col"`
}

// Stored shape (gateway column bdd_used_tables.relations):
//   []                                              → no relation
//   {"<target>": "<self>.<col> -> <target>.<col>"}  → one entry per target table
var relationRe = regexp.MustCompile(`^\s*(\w+)\.(\w+)\s*->\s*(\w+)\.(\w+)\s*$`)

// identRe mirrors the gateway's identifier rule (bddIdentRe).
var identRe = regexp.MustCompile(`^[a-zA-Z0-9_]{1,128}$`)

// parseRelations decodes the stored column. null, [], nil and non-object
// payloads yield no rows. Values that do not match the pattern keep the
// target table with empty columns, like the fields page does.
func parseRelations(raw json.RawMessage) []RelationRow {
	out := []RelationRow{}
	if len(raw) == 0 {
		return out
	}
	var obj map[string]any
	if err := json.Unmarshal(raw, &obj); err != nil || obj == nil {
		return out
	}
	keys := make([]string, 0, len(obj))
	for k := range obj {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, target := range keys {
		expr, _ := obj[target].(string)
		if m := relationRe.FindStringSubmatch(expr); m != nil {
			out = append(out, RelationRow{SelfCol: m[2], TargetTable: m[3], TargetCol: m[4]})
		} else {
			out = append(out, RelationRow{TargetTable: target})
		}
	}
	return out
}

// serializeRelations encodes rows into the stored shape. Empty → "[]".
func serializeRelations(selfTable string, rows []RelationRow) (json.RawMessage, error) {
	if len(rows) == 0 {
		return json.RawMessage(`[]`), nil
	}
	obj := make(map[string]string, len(rows))
	for i, r := range rows {
		if !identRe.MatchString(r.SelfCol) || !identRe.MatchString(r.TargetTable) || !identRe.MatchString(r.TargetCol) {
			return nil, fmt.Errorf("relations[%d]: self_col, target_table and target_col must be identifiers matching ^[a-zA-Z0-9_]{1,128}$", i)
		}
		obj[r.TargetTable] = fmt.Sprintf("%s.%s -> %s.%s", selfTable, r.SelfCol, r.TargetTable, r.TargetCol)
	}
	b, err := json.Marshal(obj)
	if err != nil {
		return nil, err
	}
	return json.RawMessage(b), nil
}
```

- [ ] **Step 7: Implement resolve.go**

```go
package tools

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// Registry paging when the service must scan rows: the gateway caps limit at 100.
const (
	registryPageSize = 100
	maxRegistryPages = 50
)

// findRegisteredByName returns the registry row named tableName in
// databaseID (0 = any database), or nil,nil when none matches. The gateway
// search is a substring LIKE on name+description, so pages are walked until an
// exact case-insensitive name match or the total is exhausted.
func findRegisteredByName(ctx context.Context, sess *gateway.Session, databaseID int, tableName string) (*gateway.UsedTable, error) {
	want := strings.ToLower(tableName)
	for page := 1; page <= maxRegistryPages; page++ {
		res, err := sess.ListUsedTables(ctx, gateway.ListParams{DatabaseID: databaseID, Search: tableName, Page: page, Limit: registryPageSize})
		if err != nil {
			return nil, err
		}
		for i := range res.Tables {
			if strings.ToLower(res.Tables[i].TableName) == want {
				t := res.Tables[i]
				return &t, nil
			}
		}
		if len(res.Tables) == 0 || int64(page*registryPageSize) >= res.Total {
			break
		}
	}
	return nil, nil
}

// registeredByName maps lower(table_name) → row for every registered table of
// databaseID (0 = all). Used to flag catalog rows and validate relation targets.
func registeredByName(ctx context.Context, sess *gateway.Session, databaseID int) (map[string]gateway.UsedTable, error) {
	out := map[string]gateway.UsedTable{}
	for page := 1; page <= maxRegistryPages; page++ {
		res, err := sess.ListUsedTables(ctx, gateway.ListParams{DatabaseID: databaseID, Page: page, Limit: registryPageSize})
		if err != nil {
			return nil, err
		}
		for _, t := range res.Tables {
			out[strings.ToLower(t.TableName)] = t
		}
		if len(res.Tables) == 0 || int64(page*registryPageSize) >= res.Total {
			break
		}
	}
	return out, nil
}

// findCatalogTable returns the upstream catalog row named tableName in
// databaseID (exact, case-insensitive), or nil,nil.
func findCatalogTable(ctx context.Context, sess *gateway.Session, databaseID int, tableName string) (*gateway.CatalogTable, error) {
	rows, err := sess.ListCatalogTables(ctx, databaseID, tableName)
	if err != nil {
		return nil, err
	}
	want := strings.ToLower(tableName)
	for i := range rows {
		if strings.ToLower(rows[i].TableName) == want {
			r := rows[i]
			return &r, nil
		}
	}
	return nil, nil
}

// resolveTable finds the registry row addressed by args: table_id, or
// database_id + table_name (database_id optional: any database).
func resolveTable(ctx context.Context, sess *gateway.Session, args map[string]any) (*gateway.UsedTable, *mcp.CallToolResult) {
	if id := argString(args, "table_id"); id != "" {
		t, err := sess.GetUsedTable(ctx, id)
		if err != nil {
			return nil, gatewayError(err, "read table", roleReadOnly, "Table not found: "+id)
		}
		return t, nil
	}
	name := argString(args, "table_name")
	dbID, err := argDatabaseID(args, false)
	if err != nil {
		return nil, invalidArgs(err)
	}
	if name == "" {
		return nil, invalidArgs(errors.New("provide 'table_id', or 'database_id' + 'table_name'"))
	}
	t, err := findRegisteredByName(ctx, sess, dbID, name)
	if err != nil {
		return nil, gatewayError(err, "read table", roleReadOnly, "Table not found")
	}
	if t == nil {
		scope := ""
		if dbID != 0 {
			scope = fmt.Sprintf(" in database %d", dbID)
		}
		return nil, errorResult(fmt.Sprintf("Table not found: %q is not registered%s", name, scope))
	}
	return t, nil
}
```

- [ ] **Step 8: Run the infra tests**

Run: `gofmt -l . ; go vet ./... && go test ./internal/tools/ 2>&1 | tail -3`
Expected: gofmt silent; `ok  github.com/hellopro/mcp-table/internal/tools`

- [ ] **Step 9: Commit**

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-table-service/internal/tools
git commit -m "feat(mcp-table-service): tool infrastructure (args, session, error mapping, resolution, status, relations)

EN: Shared helpers for the 13 tools: argument parsing with the 50-item cap, identity-bound session, gateway error → MCP text mapping, table resolution by id or name, computed status + missing checklist, relations round-trip.
FR: Helpers partages des 13 outils : parsing d'arguments avec le plafond de 50, session liee a l'identite, mapping erreur gateway → texte MCP, resolution de table par id ou nom, statut calcule + checklist des manques, aller-retour des relations."
```

---

## Task 6: Read tools — `list_registered_tables`, `get_table_info`

**Files:**
- Create: `apps-microservices/mcp-table-service/internal/tools/read_tools.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/read_tools_test.go`
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go` (`NewRegistry` registrations)

**Interfaces:**
- Consumes: Task 5 helpers.
- Produces: `handleListRegisteredTables`, `handleGetTableInfo`; output shapes `{tables:[tableSummary], total, page, limit}` and `tableDetail`.

- [ ] **Step 1: Write the failing tests**

Create `internal/tools/read_tools_test.go`:

```go
package tools

import (
	"context"
	"net/http"
	"strings"
	"testing"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

func TestListRegisteredTables_SummariesAndQuery(t *testing.T) {
	f := newFakeGateway(t)
	draft := sampleTable()
	draft.ID, draft.TableName, draft.Fields = "t-2", "clients", nil
	f.on("GET", "/api/v1/bdd/used/tables", f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{sampleTable(), draft}, Total: 2, Page: 1, Limit: 20}))

	res := NewRegistry(f.deps()).CallTool(userCtx("alice@hellopro.fr"), &mcp.CallToolParams{
		Name: "list_registered_tables", Arguments: map[string]any{"database_id": float64(5), "search": "cl"},
	})
	var out struct {
		Tables []tableSummary `json:"tables"`
		Total  int64          `json:"total"`
	}
	decodeResult(t, res, &out)
	if out.Total != 2 || len(out.Tables) != 2 {
		t.Fatalf("out = %+v", out)
	}
	if out.Tables[0].Status != StatusActive || out.Tables[0].FieldCount != 1 || out.Tables[1].Status != StatusDraft {
		t.Fatalf("statuses = %+v", out.Tables)
	}
	c := f.calls("GET", "/api/v1/bdd/used/tables")[0]
	if c.ActAs != "alice@hellopro.fr" || c.Token != "s3cret" {
		t.Fatalf("headers = %+v", c)
	}
	if !strings.Contains(c.Query, "database_id=5") || !strings.Contains(c.Query, "search=cl") || !strings.Contains(c.Query, "limit=20") {
		t.Fatalf("query = %s", c.Query)
	}
}

func TestListRegisteredTables_ForbiddenAndNoIdentity(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables", f.json(403, map[string]string{"error": "insufficient permissions"}))
	reg := NewRegistry(f.deps())

	res := reg.CallTool(userCtx("cfg@hellopro.fr"), &mcp.CallToolParams{Name: "list_registered_tables"})
	if !res.IsError || !strings.Contains(resultText(res), "requires role read-only") {
		t.Fatalf("res = %s", resultText(res))
	}
	res = reg.CallTool(context.Background(), &mcp.CallToolParams{Name: "list_registered_tables"})
	if !res.IsError || resultText(res) != errNoIdentity {
		t.Fatalf("res = %s", resultText(res))
	}
	if n := len(f.calls("GET", "/api/v1/bdd/used/tables")); n != 1 {
		t.Fatalf("no-identity call must not reach the gateway; calls=%d", n)
	}
}

func TestListRegisteredTables_BadArgs(t *testing.T) {
	f := newFakeGateway(t)
	reg := NewRegistry(f.deps())
	for _, args := range []map[string]any{{"database_id": float64(3)}, {"page": float64(0)}, {"limit": float64(101)}} {
		res := reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "list_registered_tables", Arguments: args})
		if !res.IsError || !strings.HasPrefix(resultText(res), "invalid arguments:") {
			t.Fatalf("args %v → %s", args, resultText(res))
		}
	}
}

func TestGetTableInfo_DetailByName(t *testing.T) {
	f := newFakeGateway(t)
	tb := sampleTable()
	tb.Description = ""
	f.on("GET", "/api/v1/bdd/used/tables", f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{tb}, Total: 1, Page: 1, Limit: 100}))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "get_table_info", Arguments: map[string]any{"database_id": float64(5), "table_name": "produits"}})
	var out tableDetail
	decodeResult(t, res, &out)
	if out.ID != "t-1" || out.Status != StatusActive || strings.Join(out.Missing, ",") != "empty_description" {
		t.Fatalf("out = %+v", out)
	}
	if len(out.RelationRows) != 1 || out.RelationRows[0].TargetTable != "categories" {
		t.Fatalf("relation rows = %+v", out.RelationRows)
	}
}

func TestGetTableInfo_ByIDNotFound(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/nope", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(404)
		_, _ = w.Write([]byte(`{"error":"table not found"}`))
	})
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "get_table_info", Arguments: map[string]any{"table_id": "nope"}})
	if !res.IsError || resultText(res) != "Table not found: nope" {
		t.Fatalf("res = %s", resultText(res))
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/tools/ -run 'ListRegistered|GetTableInfo' 2>&1 | head -5`
Expected: tests fail with `unknown tool: list_registered_tables` (registry is empty).

- [ ] **Step 3: Implement read_tools.go**

```go
package tools

import (
	"context"
	"errors"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// ── list_registered_tables ───────────────────────────────────────────────

const listRegisteredTablesDescription = `List the Hellopro BDD tables registered in the MCP gateway registry (the "Tables BDD" admin page). Each row has a computed status: "active" (flag on and at least one exposed field), "draft" (flag on but no field yet — call add_fields to activate it), "inactive" (flag off). Paginated. Filter by database (1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA) and by a case-insensitive substring of the table name or description. Requires gateway role read-only or higher.`

const listRegisteredTablesInputSchema = `{
  "type": "object",
  "properties": {
    "database_id": {"type": "integer", "enum": [1, 5, 10], "description": "Restrict to one database: 1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA. Omit for all databases."},
    "search": {"type": "string", "description": "Case-insensitive substring matched on table_name or description."},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
  }
}`

type listRegisteredTablesResult struct {
	Tables []tableSummary `json:"tables"`
	Total  int64          `json:"total"`
	Page   int            `json:"page"`
	Limit  int            `json:"limit"`
}

func handleListRegisteredTables(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	dbID, err := argDatabaseID(args, false)
	if err != nil {
		return invalidArgs(err), nil
	}
	p := gateway.ListParams{DatabaseID: dbID, Search: argString(args, "search"), Page: 1, Limit: 20}
	if v, ok := argInt(args, "page"); ok {
		if v < 1 {
			return invalidArgs(errors.New("'page' must be >= 1")), nil
		}
		p.Page = v
	}
	if v, ok := argInt(args, "limit"); ok {
		if v < 1 || v > 100 {
			return invalidArgs(errors.New("'limit' must be between 1 and 100")), nil
		}
		p.Limit = v
	}
	res, err := sess.ListUsedTables(ctx, p)
	if err != nil {
		return gatewayError(err, "list registered tables", roleReadOnly, "Registry not found"), nil
	}
	out := listRegisteredTablesResult{Tables: make([]tableSummary, 0, len(res.Tables)), Total: res.Total, Page: res.Page, Limit: res.Limit}
	for i := range res.Tables {
		out.Tables = append(out.Tables, summarize(&res.Tables[i]))
	}
	return jsonResult(out), nil
}

// ── get_table_info ───────────────────────────────────────────────────────

const getTableInfoDescription = `Full detail of one registered table: description, notes, metadata (primary_key, rows, default_order_by, relations and their parsed relation_rows), the exposed fields with type and description, the computed status (active / draft / inactive) and a "missing" checklist — no_fields, empty_description, fields_without_description:N, unknown_primary_key, unknown_rows — telling what is left to complete the table. Address the table by table_id, or by table_name (optionally with database_id). Requires gateway role read-only or higher.`

const getTableInfoInputSchema = `{
  "type": "object",
  "properties": {
    "table_id": {"type": "string", "description": "Registry UUID (from list_registered_tables)."},
    "database_id": {"type": "integer", "enum": [1, 5, 10], "description": "With table_name: the database of the table (1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA)."},
    "table_name": {"type": "string", "description": "Exact table name (case-insensitive). Used when table_id is not given."}
  }
}`

func handleGetTableInfo(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	t, errRes := resolveTable(ctx, sess, args)
	if errRes != nil {
		return errRes, nil
	}
	return jsonResult(detail(t)), nil
}
```

In `registry.go` `NewRegistry`, after `r := &Registry{...}` add:

```go
	// ── Read (gateway role read-only or higher) ──────────────────────────
	r.register("list_registered_tables", listRegisteredTablesDescription, listRegisteredTablesInputSchema, handleListRegisteredTables, readOnly)
	r.register("get_table_info", getTableInfoDescription, getTableInfoInputSchema, handleGetTableInfo, readOnly)
```

- [ ] **Step 4: Run tests and commit**

Run: `gofmt -l . ; go vet ./... && go test ./... 2>&1 | tail -5`
Expected: all `ok`.

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-table-service/internal/tools
git commit -m "feat(mcp-table-service): list_registered_tables and get_table_info tools

EN: Read tools over the registry with computed status and missing checklist; role read-only enforced by the gateway, mapped to clear MCP errors.
FR: Outils de lecture sur le registre avec statut calcule et checklist des manques ; role read-only applique par le gateway, traduit en erreurs MCP claires."
```

---

## Task 7: Catalog tools — `list_databases`, `list_catalog_tables`, `list_catalog_fields`

**Files:**
- Create: `apps-microservices/mcp-table-service/internal/tools/catalog_tools.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/catalog_tools_test.go`
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go`

**Interfaces:**
- Consumes: Task 5 helpers (`findCatalogTable`, `registeredByName`, `findRegisteredByName`).
- Produces: `handleListDatabases`, `handleListCatalogTables`, `handleListCatalogFields`; `catalogTableRow`, `catalogFieldRow` output types.

- [ ] **Step 1: Write the failing tests**

Create `internal/tools/catalog_tools_test.go`:

```go
package tools

import (
	"strings"
	"testing"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

func TestListDatabases(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases", f.json(200, map[string]any{"databases": []gateway.Database{{ID: 1, Name: "Hellopro BO"}, {ID: 5, Name: "Hellopro Data"}}}))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "list_databases"})
	var out struct {
		Databases []gateway.Database `json:"databases"`
	}
	decodeResult(t, res, &out)
	if len(out.Databases) != 2 || out.Databases[1].Name != "Hellopro Data" {
		t.Fatalf("out = %+v", out)
	}
}

func TestListDatabases_AdminOnlyMessage(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases", f.json(403, map[string]string{"error": "insufficient permissions"}))
	res := NewRegistry(f.deps()).CallTool(userCtx("ro@b"), &mcp.CallToolParams{Name: "list_databases"})
	if !res.IsError || !strings.Contains(resultText(res), "requires role admin") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestListCatalogTables_FlagsRegistered(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{
		{ID: 42, DatabaseID: 5, TableName: "produits", FieldCount: 12},
		{ID: 43, DatabaseID: 5, TableName: "clients", FieldCount: 8},
	}}))
	f.on("GET", "/api/v1/bdd/used/tables", f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{sampleTable()}, Total: 1, Page: 1, Limit: 100}))

	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "list_catalog_tables", Arguments: map[string]any{"database_id": float64(5), "search": "s"}})
	var out struct {
		Tables []catalogTableRow `json:"tables"`
	}
	decodeResult(t, res, &out)
	if len(out.Tables) != 2 {
		t.Fatalf("out = %+v", out)
	}
	if !out.Tables[0].Registered || out.Tables[0].RegisteredTableID != "t-1" || out.Tables[0].RegisteredStatus != StatusActive {
		t.Fatalf("produits row = %+v", out.Tables[0])
	}
	if out.Tables[1].Registered || out.Tables[1].RegisteredTableID != "" {
		t.Fatalf("clients row = %+v", out.Tables[1])
	}
	if q := f.calls("GET", "/api/v1/bdd/catalog/databases/5/tables")[0].Query; q != "search=s" {
		t.Fatalf("catalog query = %s", q)
	}
	if q := f.calls("GET", "/api/v1/bdd/used/tables")[0].Query; !strings.Contains(q, "database_id=5") || !strings.Contains(q, "limit=100") {
		t.Fatalf("registry query = %s", q)
	}
}

func TestListCatalogTables_RequiresDatabase(t *testing.T) {
	f := newFakeGateway(t)
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "list_catalog_tables"})
	if !res.IsError || !strings.Contains(resultText(res), "'database_id' is required") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestListCatalogFields_ExposedFlag(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{{ID: 42, DatabaseID: 5, TableName: "produits"}}}))
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables/42/fields", f.json(200, gateway.CatalogFieldsResponse{Primary: "id", Fields: []gateway.CatalogField{
		{ID: 1, TableID: 42, FieldName: "id", FieldType: "int(11)"},
		{ID: 2, TableID: 42, FieldName: "libelle", FieldType: "varchar(255)", IsNullable: true},
	}}))
	f.on("GET", "/api/v1/bdd/used/tables", f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{sampleTable()}, Total: 1, Page: 1, Limit: 100}))

	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "list_catalog_fields", Arguments: map[string]any{"database_id": float64(5), "table_name": "produits"}})
	var out struct {
		TableName         string            `json:"table_name"`
		UpstreamTableID   int               `json:"upstream_table_id"`
		PrimaryKey        string            `json:"primary_key"`
		RegisteredTableID string            `json:"registered_table_id"`
		Fields            []catalogFieldRow `json:"fields"`
	}
	decodeResult(t, res, &out)
	if out.UpstreamTableID != 42 || out.PrimaryKey != "id" || out.RegisteredTableID != "t-1" || len(out.Fields) != 2 {
		t.Fatalf("out = %+v", out)
	}
	if !out.Fields[0].Exposed || out.Fields[1].Exposed || !out.Fields[1].IsNullable {
		t.Fatalf("fields = %+v", out.Fields)
	}
}

func TestListCatalogFields_UnknownTable(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/1/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{}}))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "list_catalog_fields", Arguments: map[string]any{"database_id": float64(1), "table_name": "ghost"}})
	if !res.IsError || resultText(res) != `Table "ghost" not found in the catalog of database 1` {
		t.Fatalf("res = %s", resultText(res))
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/tools/ -run 'Catalog|ListDatabases' 2>&1 | head -5`
Expected: `undefined: catalogTableRow` / `unknown tool`.

- [ ] **Step 3: Implement catalog_tools.go**

```go
package tools

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// ── list_databases ───────────────────────────────────────────────────────

const listDatabasesDescription = `List the Hellopro databases exposed by the upstream BDD catalog (expected: 1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA). Requires gateway role admin.`

const listDatabasesInputSchema = `{"type": "object", "properties": {}}`

func handleListDatabases(ctx context.Context, deps *Deps, _ map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	rows, err := sess.ListDatabases(ctx)
	if err != nil {
		return gatewayError(err, "browse the catalog", roleAdmin, "Catalog not found"), nil
	}
	return jsonResult(struct {
		Databases []gateway.Database `json:"databases"`
	}{rows}), nil
}

// ── list_catalog_tables ──────────────────────────────────────────────────

const listCatalogTablesDescription = `Browse the upstream BDD catalog of one database and see which tables are already registered in the gateway registry (registered = true, with registered_table_id and registered_status). Use it to find candidates for add_tables. Optional case-insensitive search on the table name. Requires gateway role admin.`

const listCatalogTablesInputSchema = `{
  "type": "object",
  "properties": {
    "database_id": {"type": "integer", "enum": [1, 5, 10], "description": "1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA."},
    "search": {"type": "string", "description": "Case-insensitive substring of the table name."}
  },
  "required": ["database_id"]
}`

type catalogTableRow struct {
	UpstreamTableID   int    `json:"upstream_table_id"`
	DatabaseID        int    `json:"database_id"`
	TableName         string `json:"table_name"`
	Description       string `json:"description,omitempty"`
	FieldCount        int    `json:"field_count,omitempty"`
	Registered        bool   `json:"registered"`
	RegisteredTableID string `json:"registered_table_id,omitempty"`
	RegisteredStatus  string `json:"registered_status,omitempty"`
}

func handleListCatalogTables(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	dbID, err := argDatabaseID(args, true)
	if err != nil {
		return invalidArgs(err), nil
	}
	rows, err := sess.ListCatalogTables(ctx, dbID, argString(args, "search"))
	if err != nil {
		return gatewayError(err, "browse the catalog", roleAdmin, "Catalog not found"), nil
	}
	registered, err := registeredByName(ctx, sess, dbID)
	if err != nil {
		return gatewayError(err, "list registered tables", roleReadOnly, "Registry not found"), nil
	}
	out := struct {
		DatabaseID int               `json:"database_id"`
		Tables     []catalogTableRow `json:"tables"`
	}{DatabaseID: dbID, Tables: make([]catalogTableRow, 0, len(rows))}
	for _, r := range rows {
		row := catalogTableRow{UpstreamTableID: r.ID, DatabaseID: dbID, TableName: r.TableName, Description: r.Description, FieldCount: r.FieldCount}
		if reg, ok := registered[strings.ToLower(r.TableName)]; ok {
			row.Registered, row.RegisteredTableID, row.RegisteredStatus = true, reg.ID, tableStatus(&reg)
		}
		out.Tables = append(out.Tables, row)
	}
	return jsonResult(out), nil
}

// ── list_catalog_fields ──────────────────────────────────────────────────

const listCatalogFieldsDescription = `List the columns of one upstream catalog table (name, type, nullable, description) plus its primary key, and flag which columns are already exposed in the gateway registry (exposed = true). Use it to choose fields for add_fields. Requires gateway role admin.`

const listCatalogFieldsInputSchema = `{
  "type": "object",
  "properties": {
    "database_id": {"type": "integer", "enum": [1, 5, 10], "description": "1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA."},
    "table_name": {"type": "string", "description": "Exact catalog table name (case-insensitive)."}
  },
  "required": ["database_id", "table_name"]
}`

type catalogFieldRow struct {
	UpstreamFieldID int    `json:"upstream_field_id"`
	FieldName       string `json:"field_name"`
	FieldType       string `json:"field_type,omitempty"`
	IsNullable      bool   `json:"is_nullable"`
	Description     string `json:"description,omitempty"`
	Exposed         bool   `json:"exposed"`
}

func handleListCatalogFields(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	dbID, err := argDatabaseID(args, true)
	if err != nil {
		return invalidArgs(err), nil
	}
	name := argString(args, "table_name")
	if name == "" {
		return invalidArgs(errors.New("'table_name' is required")), nil
	}
	cat, err := findCatalogTable(ctx, sess, dbID, name)
	if err != nil {
		return gatewayError(err, "browse the catalog", roleAdmin, "Catalog not found"), nil
	}
	if cat == nil {
		return errorResult(fmt.Sprintf("Table %q not found in the catalog of database %d", name, dbID)), nil
	}
	fields, err := sess.ListCatalogFields(ctx, dbID, cat.ID)
	if err != nil {
		return gatewayError(err, "browse the catalog", roleAdmin, "Catalog table not found"), nil
	}
	exposed := map[string]bool{}
	registeredID := ""
	if reg, err := findRegisteredByName(ctx, sess, dbID, name); err != nil {
		return gatewayError(err, "list registered tables", roleReadOnly, "Registry not found"), nil
	} else if reg != nil {
		registeredID = reg.ID
		for _, f := range reg.Fields {
			exposed[strings.ToLower(f.FieldName)] = true
		}
	}
	out := struct {
		DatabaseID        int               `json:"database_id"`
		TableName         string            `json:"table_name"`
		UpstreamTableID   int               `json:"upstream_table_id"`
		PrimaryKey        string            `json:"primary_key"`
		RegisteredTableID string            `json:"registered_table_id,omitempty"`
		Fields            []catalogFieldRow `json:"fields"`
	}{DatabaseID: dbID, TableName: cat.TableName, UpstreamTableID: cat.ID, PrimaryKey: fields.Primary, RegisteredTableID: registeredID, Fields: make([]catalogFieldRow, 0, len(fields.Fields))}
	for _, f := range fields.Fields {
		out.Fields = append(out.Fields, catalogFieldRow{
			UpstreamFieldID: f.ID, FieldName: f.FieldName, FieldType: f.FieldType, IsNullable: f.IsNullable,
			Description: f.Description, Exposed: exposed[strings.ToLower(f.FieldName)],
		})
	}
	return jsonResult(out), nil
}
```

In `registry.go` `NewRegistry`, after the read tools:

```go
	// ── Catalog (gateway role admin) ─────────────────────────────────────
	r.register("list_databases", listDatabasesDescription, listDatabasesInputSchema, handleListDatabases, readOnly)
	r.register("list_catalog_tables", listCatalogTablesDescription, listCatalogTablesInputSchema, handleListCatalogTables, readOnly)
	r.register("list_catalog_fields", listCatalogFieldsDescription, listCatalogFieldsInputSchema, handleListCatalogFields, readOnly)
```

(`readOnly` here is the MCP *side-effect* hint — these tools change nothing — not the gateway role.)

- [ ] **Step 4: Run tests and commit**

Run: `gofmt -l . ; go vet ./... && go test ./... 2>&1 | tail -5`
Expected: all `ok`.

```bash
cd /home/hellopro/RAG-HP-PUB
git add apps-microservices/mcp-table-service/internal/tools
git commit -m "feat(mcp-table-service): catalog browsing tools

EN: list_databases, list_catalog_tables (flags already-registered rows) and list_catalog_fields (flags exposed columns) over the gateway's read-only catalog proxy.
FR: list_databases, list_catalog_tables (signale les tables deja enregistrees) et list_catalog_fields (signale les colonnes exposees) via le proxy catalogue en lecture seule du gateway."
```

---

## Task 8: `add_tables`

**Files:**
- Create: `apps-microservices/mcp-table-service/internal/tools/table_tools.go` (this task adds `add_tables`; Tasks 10 and 11 append to the same file)
- Create: `apps-microservices/mcp-table-service/internal/tools/table_tools_test.go`
- Modify: `apps-microservices/mcp-table-service/internal/tools/errors.go` (`errorJSONResult`, `batchError`)
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go`

**Interfaces:**
- Consumes: Task 5 helpers, `gateway.Session.BulkCreateUsedTables`, `RefreshCatalog`.
- Produces: `batchError{Item, Error string}`, `errorJSONResult(v any) *mcp.CallToolResult`, `handleAddTables`, `addTablesResult{OK []addTablesItem; Errors []batchError; Note string}`, `addTablesItem{tableDetail; CatalogRefreshed bool}`; constants `addTablesDeadline = 120s`, `refreshTimeout = 10s`, `refreshParallel = 5`.

- [ ] **Step 1: Write the failing tests**

Create `internal/tools/table_tools_test.go`:

```go
package tools

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

func mustJSON(v any) string { b, _ := json.Marshal(v); return string(b) }

func TestAddTables_CreatesResolvesCatalogAndRefreshes(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Query().Get("search") {
		case "produits":
			f.json(200, map[string]any{"tables": []gateway.CatalogTable{{ID: 42, DatabaseID: 5, TableName: "produits"}}})(w, r)
		default:
			f.json(200, map[string]any{"tables": []gateway.CatalogTable{}})(w, r)
		}
	})
	created := gateway.UsedTable{ID: "t-new", DatabaseID: 5, TableName: "produits", UpstreamTableID: 42, IsActive: true, Fields: []gateway.UsedField{}}
	f.on("POST", "/api/v1/bdd/used/tables/bulk", f.json(201, gateway.BulkCreateResponse{Created: []gateway.UsedTable{created}}))
	refreshed := created
	refreshed.PrimaryKey, refreshed.Rows = "id", rowsPtr(99)
	var refreshCalls int32
	f.on("POST", "/api/v1/bdd/used/tables/t-new/refresh-catalog", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&refreshCalls, 1)
		f.json(200, refreshed)(w, r)
	})

	res := NewRegistry(f.deps()).CallTool(userCtx("admin@hellopro.fr"), &mcp.CallToolParams{Name: "add_tables", Arguments: map[string]any{
		"database_id": float64(5),
		"tables":      []any{map[string]any{"table_name": "produits", "description": "Catalogue"}, map[string]any{"table_name": "ghost"}},
	}})
	var out addTablesResult
	decodeResult(t, res, &out)
	if len(out.OK) != 1 || out.OK[0].ID != "t-new" || out.OK[0].Status != StatusDraft || !out.OK[0].CatalogRefreshed || out.OK[0].PrimaryKey != "id" {
		t.Fatalf("ok = %+v", out.OK)
	}
	if len(out.Errors) != 1 || out.Errors[0].Item != "ghost" || !strings.Contains(out.Errors[0].Error, "not found in the catalog") {
		t.Fatalf("errors = %+v", out.Errors)
	}
	if !strings.Contains(out.Note, "add_fields") {
		t.Fatalf("note = %s", out.Note)
	}
	var sent gateway.BulkCreateRequest
	_ = json.Unmarshal(f.calls("POST", "/api/v1/bdd/used/tables/bulk")[0].Body, &sent)
	if sent.DatabaseID != 5 || len(sent.Items) != 1 || sent.Items[0].UpstreamTableID != 42 || sent.Items[0].Description != "Catalogue" {
		t.Fatalf("sent = %+v", sent)
	}
	if atomic.LoadInt32(&refreshCalls) != 1 {
		t.Fatalf("refresh calls = %d", refreshCalls)
	}
}

func TestAddTables_RefreshDisabledAndBestEffort(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/1/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{{ID: 7, DatabaseID: 1, TableName: "clients"}}}))
	created := gateway.UsedTable{ID: "t-c", DatabaseID: 1, TableName: "clients", UpstreamTableID: 7, IsActive: true}
	f.on("POST", "/api/v1/bdd/used/tables/bulk", f.json(201, gateway.BulkCreateResponse{Created: []gateway.UsedTable{created}}))
	f.on("POST", "/api/v1/bdd/used/tables/t-c/refresh-catalog", f.json(502, map[string]string{"error": "upstream timeout"}))
	reg := NewRegistry(f.deps())

	res := reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_tables", Arguments: map[string]any{
		"database_id": float64(1), "tables": []any{map[string]any{"table_name": "clients"}}, "refresh_catalog": false,
	}})
	var out addTablesResult
	decodeResult(t, res, &out)
	if len(out.OK) != 1 || out.OK[0].CatalogRefreshed {
		t.Fatalf("ok = %+v", out.OK)
	}
	if n := len(f.calls("POST", "/api/v1/bdd/used/tables/t-c/refresh-catalog")); n != 0 {
		t.Fatalf("refresh must be skipped, calls=%d", n)
	}

	res = reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_tables", Arguments: map[string]any{
		"database_id": float64(1), "tables": []any{map[string]any{"table_name": "clients"}},
	}})
	decodeResult(t, res, &out)
	if len(out.OK) != 1 || out.OK[0].CatalogRefreshed {
		t.Fatalf("refresh failure must be best effort: %+v", out)
	}
}

func TestAddTables_AllFailedIsError(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{{ID: 42, DatabaseID: 5, TableName: "produits"}}}))
	f.on("POST", "/api/v1/bdd/used/tables/bulk", f.json(400, gateway.BulkCreateResponse{Created: []gateway.UsedTable{}, Errors: []gateway.BulkCreateError{{TableName: "produits", Error: "table already registered for this database"}}}))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_tables", Arguments: map[string]any{
		"database_id": float64(5), "tables": []any{map[string]any{"table_name": "produits"}},
	}})
	if !res.IsError {
		t.Fatal("all-failed batch must be an error result")
	}
	var out addTablesResult
	_ = json.Unmarshal([]byte(resultText(res)), &out)
	if len(out.Errors) != 1 || out.Errors[0].Error != "table already registered for this database" {
		t.Fatalf("out = %+v", out)
	}
}

func TestAddTables_ArgValidation(t *testing.T) {
	f := newFakeGateway(t)
	reg := NewRegistry(f.deps())
	cases := []map[string]any{
		{"tables": []any{map[string]any{"table_name": "x"}}},           // no database_id
		{"database_id": float64(5)},                                     // no tables
		{"database_id": float64(5), "tables": []any{map[string]any{}}}, // missing table_name
		{"database_id": float64(5), "tables": []any{"not-an-object"}},  // wrong shape
	}
	for _, args := range cases {
		res := reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_tables", Arguments: args})
		if !res.IsError || !strings.HasPrefix(resultText(res), "invalid arguments:") {
			t.Fatalf("args %v → %s", args, resultText(res))
		}
	}
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", f.json(200, map[string]any{"tables": []gateway.CatalogTable{}}))
	res := reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_tables", Arguments: map[string]any{
		"database_id": float64(5), "tables": []any{map[string]any{"table_name": "bad name"}},
	}})
	var out addTablesResult
	_ = json.Unmarshal([]byte(resultText(res)), &out)
	if !res.IsError || len(out.Errors) != 1 || !strings.Contains(out.Errors[0].Error, "must match") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestAddTables_ForbiddenForReadOnly(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables", f.json(403, map[string]string{"error": "insufficient permissions"}))
	res := NewRegistry(f.deps()).CallTool(userCtx("ro@b"), &mcp.CallToolParams{Name: "add_tables", Arguments: map[string]any{
		"database_id": float64(5), "tables": []any{map[string]any{"table_name": "produits"}},
	}})
	if !res.IsError || !strings.Contains(resultText(res), "requires role admin") {
		t.Fatalf("res = %s", resultText(res))
	}
}
```

(`io` and `mustJSON` are used by the tests appended in Tasks 10 and 11; if `go vet` flags `io` as unused at this point, remove the import now and re-add it in Task 11.)

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/hellopro/RAG-HP-PUB/apps-microservices/mcp-table-service && go test ./internal/tools/ -run AddTables 2>&1 | head -5`
Expected: `undefined: addTablesResult`.

- [ ] **Step 3: Add `batchError` and `errorJSONResult` to errors.go**

Append to `internal/tools/errors.go`:

```go
// batchError is one failed item of a batch tool. Item is the caller-facing
// identifier (table name, field name or table id).
type batchError struct {
	Item  string `json:"item"`
	Error string `json:"error"`
}

// errorJSONResult renders a structured batch outcome as an MCP error result.
// Used when no item of a batch succeeded: the caller still gets the per-item
// reasons, but isError tells the LLM the call achieved nothing.
func errorJSONResult(v any) *mcp.CallToolResult {
	res := jsonResult(v)
	res.IsError = true
	return res
}
```

- [ ] **Step 4: Implement `add_tables` in table_tools.go**

```go
package tools

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// ── add_tables ───────────────────────────────────────────────────────────

const (
	// addTablesDeadline bounds the whole add_tables call (spec §7).
	addTablesDeadline = 120 * time.Second
	// refreshTimeout bounds one refresh-catalog call: row counting can be
	// slow on very large tables, and the refresh is best effort.
	refreshTimeout = 10 * time.Second
	// refreshParallel caps concurrent refresh-catalog calls.
	refreshParallel = 5
)

const addTablesDescription = `Register upstream catalog tables of one database in the gateway registry (the "Ajouter" wizard of the Tables BDD page). Each table_name is resolved in the catalog (exact, case-insensitive) so the registry keeps the catalog link needed for field resolution and refreshes. After creation the primary key and row count are pulled from the catalog (best effort; see catalog_refreshed per table). IMPORTANT: new tables are drafts — no column is exposed until you call add_fields, which activates them; then complete them with update_table_info (description, notes, metadata). Requires gateway role admin.`

const addTablesInputSchema = `{
  "type": "object",
  "properties": {
    "database_id": {"type": "integer", "enum": [1, 5, 10], "description": "1 = Hellopro BO, 5 = Hellopro Data, 10 = Hellopro IA."},
    "tables": {
      "type": "array", "minItems": 1, "maxItems": 50,
      "items": {
        "type": "object",
        "properties": {
          "table_name": {"type": "string", "description": "Exact catalog table name."},
          "description": {"type": "string", "description": "Optional functional description used in the LLM doc."}
        },
        "required": ["table_name"]
      }
    },
    "refresh_catalog": {"type": "boolean", "default": true, "description": "Pull primary key and row count from the catalog after creation. Slow on huge tables; set false to skip and run sync_table_catalog later."}
  },
  "required": ["database_id", "tables"]
}`

const addTablesNote = "Newly added tables are drafts: call add_fields to expose columns (this activates them), then update_table_info for description, notes and metadata."

type addTablesItem struct {
	tableDetail
	CatalogRefreshed bool `json:"catalog_refreshed"`
}

type addTablesResult struct {
	OK     []addTablesItem `json:"ok"`
	Errors []batchError    `json:"errors"`
	Note   string          `json:"note"`
}

func handleAddTables(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	dbID, err := argDatabaseID(args, true)
	if err != nil {
		return invalidArgs(err), nil
	}
	items, err := argObjectList(args, "tables")
	if err != nil {
		return invalidArgs(err), nil
	}
	if err := checkBatch("tables", len(items)); err != nil {
		return invalidArgs(err), nil
	}
	refresh := true
	if v, ok := argBool(args, "refresh_catalog"); ok {
		refresh = v
	}
	ctx, cancel := context.WithTimeout(ctx, addTablesDeadline)
	defer cancel()

	out := addTablesResult{OK: []addTablesItem{}, Errors: []batchError{}, Note: addTablesNote}
	req := gateway.BulkCreateRequest{DatabaseID: dbID}
	seen := map[string]bool{}
	for i, it := range items {
		name := argString(it, "table_name")
		if name == "" {
			return invalidArgs(fmt.Errorf("'tables[%d].table_name' is required", i)), nil
		}
		if !identRe.MatchString(name) {
			out.Errors = append(out.Errors, batchError{name, "table_name must match ^[a-zA-Z0-9_]{1,128}$"})
			continue
		}
		key := strings.ToLower(name)
		if seen[key] {
			out.Errors = append(out.Errors, batchError{name, "duplicate in request"})
			continue
		}
		seen[key] = true
		cat, err := findCatalogTable(ctx, sess, dbID, name)
		if err != nil {
			return gatewayError(err, "browse the catalog", roleAdmin, "Catalog not found"), nil
		}
		if cat == nil {
			out.Errors = append(out.Errors, batchError{name, fmt.Sprintf("not found in the catalog of database %d", dbID)})
			continue
		}
		req.Items = append(req.Items, gateway.BulkCreateItem{TableName: cat.TableName, Description: argString(it, "description"), UpstreamTableID: cat.ID})
	}

	if len(req.Items) > 0 {
		res, err := sess.BulkCreateUsedTables(ctx, req)
		if err != nil {
			return gatewayError(err, "add tables", roleAdmin, "Registry not found"), nil
		}
		for _, e := range res.Errors {
			out.Errors = append(out.Errors, batchError{e.TableName, e.Error})
		}
		created := res.Created
		refreshed := make([]bool, len(created))
		if refresh && len(created) > 0 {
			refreshCreated(ctx, sess, created, refreshed)
		}
		for i := range created {
			out.OK = append(out.OK, addTablesItem{tableDetail: detail(&created[i]), CatalogRefreshed: refreshed[i]})
		}
	}
	if len(out.OK) == 0 {
		return errorJSONResult(out), nil
	}
	return jsonResult(out), nil
}

// refreshCreated pulls primary key + row count for each created table, at
// most refreshParallel at a time and refreshTimeout each. Best effort: a
// failure leaves refreshed[i] false and created[i] unchanged; a success
// replaces created[i] with the refreshed row.
func refreshCreated(ctx context.Context, sess *gateway.Session, created []gateway.UsedTable, refreshed []bool) {
	sem := make(chan struct{}, refreshParallel)
	var wg sync.WaitGroup
	for i := range created {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			rctx, cancel := context.WithTimeout(ctx, refreshTimeout)
			defer cancel()
			t, err := sess.RefreshCatalog(rctx, created[i].ID)
			if err != nil {
				log.Printf("[tools] add_tables: refresh-catalog for %s failed (best effort): %v", created[i].TableName, err)
				return
			}
			created[i] = *t
			refreshed[i] = true
		}(i)
	}
	wg.Wait()
}
```

The imports `errors` and `net/http` are used by the tools appended in Tasks 10 and 11. Go rejects unused imports, so at this step **omit them** from the import block and add them back in Task 10 (`errors`) and Task 11 (`net/http`).

In `registry.go` `NewRegistry`, after the catalog tools:

```go
	// ── Write (gateway role admin) ───────────────────────────────────────
	r.register("add_tables", addTablesDescription, addTablesInputSchema, handleAddTables, nil)
```

- [ ] **Step 5: Run tests and commit**

Run: `gofmt -l . ; go vet ./... && go test ./... 2>&1 | tail -5`
Expected: all `ok`.

Stage `apps-microservices/mcp-table-service/internal/tools` and commit with subject `feat(mcp-table-service): add_tables tool`, body:
- `EN: Resolves names in the catalog, bulk-creates registry rows, best-effort catalog refresh (5 parallel, 10s each, 120s overall); per-item errors; result states tables are drafts until fields are added.`
- `FR: Resout les noms dans le catalogue, cree les lignes en masse, rafraichissement catalogue best-effort (5 en parallele, 10 s chacun, 120 s au total) ; erreurs par element ; le resultat rappelle que les tables sont des brouillons jusqu'a l'ajout de champs.`

---

## Task 9: Field tools — `add_fields`, `update_fields`, `remove_fields`

**Files:**
- Create: `apps-microservices/mcp-table-service/internal/tools/field_tools.go`
- Create: `apps-microservices/mcp-table-service/internal/tools/field_tools_test.go`
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go`

**Interfaces:**
- Consumes: `resolveTable`, `batchError`, `errorJSONResult`, `gateway.Session.ListCatalogFields/AddField/PatchFieldDescription/DeleteField/GetUsedTable`.
- Produces: `fieldsResult{TableID, TableName string; OK []gateway.UsedField; Errors []batchError; StatusAfter string; Missing []string; Warning string}`, `statusAfter(ctx, sess, tableID) (string, []string)`, `tableAddressSchema` (JSON fragment reused by Task 10), `draftTable()` test helper, the three handlers.

- [ ] **Step 1: Write the failing tests**

Create `internal/tools/field_tools_test.go`:

```go
package tools

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// draftTable is sampleTable without fields → status "draft".
func draftTable() gateway.UsedTable {
	t := sampleTable()
	t.Fields = []gateway.UsedField{}
	return t
}

func catalogFieldsRoute(f *fakeGateway) {
	f.on("GET", "/api/v1/bdd/catalog/databases/5/tables/42/fields", f.json(200, gateway.CatalogFieldsResponse{Primary: "id", Fields: []gateway.CatalogField{
		{ID: 1, TableID: 42, FieldName: "id", FieldType: "int(11)"},
		{ID: 2, TableID: 42, FieldName: "libelle", FieldType: "varchar(255)"},
		{ID: 3, TableID: 42, FieldName: "statut", FieldType: "enum('a','b')"},
	}}))
}

func TestAddFields_ExplicitNamesActivateDraft(t *testing.T) {
	f := newFakeGateway(t)
	catalogFieldsRoute(f)
	after := sampleTable()
	after.Fields = []gateway.UsedField{{ID: "f-1", FieldName: "id"}, {ID: "f-2", FieldName: "libelle", Description: "Nom"}}
	getCalls := 0
	f.on("GET", "/api/v1/bdd/used/tables/t-1", func(w http.ResponseWriter, r *http.Request) {
		getCalls++
		if getCalls == 1 {
			f.json(200, draftTable())(w, r)
			return
		}
		f.json(200, after)(w, r)
	})
	f.on("POST", "/api/v1/bdd/used/tables/t-1/fields", func(w http.ResponseWriter, r *http.Request) {
		var req gateway.AddFieldRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		f.json(201, gateway.UsedField{ID: "f-" + req.FieldName, UsedTableID: "t-1", FieldName: req.FieldName, FieldType: req.FieldType, Description: req.Description, UpstreamFieldID: req.UpstreamFieldID})(w, r)
	})

	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_fields", Arguments: map[string]any{
		"table_id": "t-1",
		"fields":   []any{map[string]any{"field_name": "ID"}, map[string]any{"field_name": "libelle", "description": "Nom"}, map[string]any{"field_name": "ghost"}},
	}})
	var out fieldsResult
	decodeResult(t, res, &out)
	if len(out.OK) != 2 || out.OK[0].FieldName != "id" || out.OK[0].FieldType != "int(11)" || out.OK[0].UpstreamFieldID != 1 || out.OK[1].Description != "Nom" {
		t.Fatalf("ok = %+v", out.OK)
	}
	if len(out.Errors) != 1 || out.Errors[0].Item != "ghost" || !strings.Contains(out.Errors[0].Error, "not found in the catalog") {
		t.Fatalf("errors = %+v", out.Errors)
	}
	if out.StatusAfter != StatusActive {
		t.Fatalf("status_after = %s", out.StatusAfter)
	}
	if n := len(f.calls("POST", "/api/v1/bdd/used/tables/t-1/fields")); n != 2 {
		t.Fatalf("POST calls = %d", n)
	}
}

func TestAddFields_AllFieldsSkipsAlreadyExposed(t *testing.T) {
	f := newFakeGateway(t)
	catalogFieldsRoute(f)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, sampleTable())) // already exposes "id"
	f.on("POST", "/api/v1/bdd/used/tables/t-1/fields", func(w http.ResponseWriter, r *http.Request) {
		var req gateway.AddFieldRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		f.json(201, gateway.UsedField{ID: "f-" + req.FieldName, FieldName: req.FieldName, FieldType: req.FieldType})(w, r)
	})
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_fields", Arguments: map[string]any{"table_id": "t-1", "all_fields": true}})
	var out fieldsResult
	decodeResult(t, res, &out)
	if len(out.OK) != 2 || len(out.Errors) != 1 || out.Errors[0].Item != "id" || out.Errors[0].Error != "already exposed" {
		t.Fatalf("out = %+v", out)
	}
}

func TestAddFields_NoUpstreamLink(t *testing.T) {
	f := newFakeGateway(t)
	tb := draftTable()
	tb.UpstreamTableID = 0
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, tb))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_fields", Arguments: map[string]any{"table_id": "t-1", "all_fields": true}})
	if !res.IsError || !strings.Contains(resultText(res), "no upstream catalog link") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestAddFields_ForbiddenStopsBatch(t *testing.T) {
	f := newFakeGateway(t)
	catalogFieldsRoute(f)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, draftTable()))
	f.on("POST", "/api/v1/bdd/used/tables/t-1/fields", f.json(403, map[string]string{"error": "insufficient permissions"}))
	res := NewRegistry(f.deps()).CallTool(userCtx("ro@b"), &mcp.CallToolParams{Name: "add_fields", Arguments: map[string]any{"table_id": "t-1", "all_fields": true}})
	if !res.IsError || !strings.Contains(resultText(res), "requires role admin") {
		t.Fatalf("res = %s", resultText(res))
	}
	if n := len(f.calls("POST", "/api/v1/bdd/used/tables/t-1/fields")); n != 1 {
		t.Fatalf("a 403 must stop the batch after the first call, got %d", n)
	}
}

func TestAddFields_NeedsFieldsOrAll(t *testing.T) {
	f := newFakeGateway(t)
	catalogFieldsRoute(f)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, draftTable()))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "add_fields", Arguments: map[string]any{"table_id": "t-1"}})
	if !res.IsError || !strings.Contains(resultText(res), "all_fields") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestUpdateFields_PatchesByName(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, sampleTable()))
	f.on("PATCH", "/api/v1/bdd/used/tables/t-1/fields/f-1", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Description string `json:"description"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		f.json(200, gateway.UsedField{ID: "f-1", FieldName: "id", Description: body.Description})(w, r)
	})
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "update_fields", Arguments: map[string]any{
		"table_id": "t-1",
		"fields":   []any{map[string]any{"field_name": "id", "description": "Identifiant"}, map[string]any{"field_name": "nope", "description": "x"}},
	}})
	var out fieldsResult
	decodeResult(t, res, &out)
	if len(out.OK) != 1 || out.OK[0].Description != "Identifiant" || len(out.Errors) != 1 || out.Errors[0].Item != "nope" {
		t.Fatalf("out = %+v", out)
	}
}

func TestRemoveFields_LastFieldWarnsDraft(t *testing.T) {
	f := newFakeGateway(t)
	getCalls := 0
	f.on("GET", "/api/v1/bdd/used/tables/t-1", func(w http.ResponseWriter, r *http.Request) {
		getCalls++
		if getCalls == 1 {
			f.json(200, sampleTable())(w, r)
			return
		}
		f.json(200, draftTable())(w, r)
	})
	f.on("DELETE", "/api/v1/bdd/used/tables/t-1/fields/f-1", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(204) })
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "remove_fields", Arguments: map[string]any{"table_id": "t-1", "field_names": []any{"id", "ghost"}}})
	var out fieldsResult
	decodeResult(t, res, &out)
	if len(out.OK) != 1 || out.OK[0].FieldName != "id" || len(out.Errors) != 1 || out.StatusAfter != StatusDraft {
		t.Fatalf("out = %+v", out)
	}
	if !strings.Contains(out.Warning, "draft") {
		t.Fatalf("warning = %q", out.Warning)
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/tools/ -run 'AddFields|UpdateFields|RemoveFields' 2>&1 | head -5`
Expected: `undefined: fieldsResult`.

- [ ] **Step 3: Implement field_tools.go**

```go
package tools

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/hellopro/mcp-table/internal/gateway"
	"github.com/hellopro/mcp-table/internal/mcp"
)

// fieldsResult is the shared outcome of the three field tools.
type fieldsResult struct {
	TableID     string              `json:"table_id"`
	TableName   string              `json:"table_name"`
	OK          []gateway.UsedField `json:"ok"`
	Errors      []batchError        `json:"errors"`
	StatusAfter string              `json:"status_after,omitempty"`
	Missing     []string            `json:"missing,omitempty"`
	Warning     string              `json:"warning,omitempty"`
}

// statusAfter re-reads the table and returns its computed status and
// checklist. "unknown" when the re-read fails — the writes already happened.
func statusAfter(ctx context.Context, sess *gateway.Session, tableID string) (string, []string) {
	t, err := sess.GetUsedTable(ctx, tableID)
	if err != nil {
		return "unknown", nil
	}
	return tableStatus(t), missingChecklist(t)
}

// tableAddressSchema is the shared address fragment of every table-scoped tool.
const tableAddressSchema = `
    "table_id": {"type": "string", "description": "Registry UUID (from list_registered_tables)."},
    "database_id": {"type": "integer", "enum": [1, 5, 10], "description": "With table_name: the database of the table."},
    "table_name": {"type": "string", "description": "Exact registered table name, used when table_id is not given."}`

// isAuthError reports a 401/403: the whole batch stops, the caller cannot do
// anything about the remaining items.
func isAuthError(err error) bool {
	return gateway.IsStatus(err, http.StatusForbidden) || gateway.IsStatus(err, http.StatusUnauthorized)
}

// ── add_fields ───────────────────────────────────────────────────────────

const addFieldsDescription = `Expose columns of a registered table (the "Champs" section of the table configuration page). Field types and catalog ids are pulled from the upstream catalog automatically; give an optional description per field (used in the LLM doc), or set all_fields=true to expose every column (not subject to the 50-item cap). Adding the first field turns a draft table into an active one. Already exposed fields and names unknown to the catalog are reported in errors. Requires gateway role admin.`

const addFieldsInputSchema = `{
  "type": "object",
  "properties": {` + tableAddressSchema + `,
    "fields": {
      "type": "array", "maxItems": 50,
      "items": {"type": "object", "properties": {"field_name": {"type": "string"}, "description": {"type": "string"}}, "required": ["field_name"]}
    },
    "all_fields": {"type": "boolean", "default": false, "description": "Expose every catalog column. 'fields' may still carry descriptions for some of them."}
  }
}`

func handleAddFields(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	t, errRes := resolveTable(ctx, sess, args)
	if errRes != nil {
		return errRes, nil
	}
	if t.UpstreamTableID == 0 {
		return errorResult(fmt.Sprintf("Table %q has no upstream catalog link (upstream_table_id missing), so its fields cannot be resolved in the catalog. Remove it with delete_tables and re-add it with add_tables.", t.TableName)), nil
	}
	all, _ := argBool(args, "all_fields")
	items, err := argObjectList(args, "fields")
	if err != nil {
		return invalidArgs(err), nil
	}
	if !all {
		if err := checkBatch("fields", len(items)); err != nil {
			return invalidArgs(errors.New(err.Error() + ", or set all_fields=true")), nil
		}
	}
	cat, err := sess.ListCatalogFields(ctx, t.DatabaseID, t.UpstreamTableID)
	if err != nil {
		return gatewayError(err, "browse the catalog", roleAdmin, "Catalog table not found"), nil
	}
	byName := make(map[string]gateway.CatalogField, len(cat.Fields))
	for _, f := range cat.Fields {
		byName[strings.ToLower(f.FieldName)] = f
	}
	exposed := make(map[string]bool, len(t.Fields))
	for _, f := range t.Fields {
		exposed[strings.ToLower(f.FieldName)] = true
	}

	// Wanted list: explicit items, or every catalog column (descriptions
	// still taken from explicit items when present).
	type want struct{ name, desc string }
	descByName := map[string]string{}
	var wants []want
	for i, it := range items {
		name := argString(it, "field_name")
		if name == "" {
			return invalidArgs(fmt.Errorf("'fields[%d].field_name' is required", i)), nil
		}
		descByName[strings.ToLower(name)] = argString(it, "description")
		if !all {
			wants = append(wants, want{name, argString(it, "description")})
		}
	}
	if all {
		for _, f := range cat.Fields {
			wants = append(wants, want{f.FieldName, descByName[strings.ToLower(f.FieldName)]})
		}
	}
	if len(wants) == 0 {
		return invalidArgs(errors.New("'fields' must contain at least one item, or set all_fields=true")), nil
	}

	out := fieldsResult{TableID: t.ID, TableName: t.TableName, OK: []gateway.UsedField{}, Errors: []batchError{}}
	for _, w := range wants {
		key := strings.ToLower(w.name)
		cf, ok := byName[key]
		if !ok {
			out.Errors = append(out.Errors, batchError{w.name, "not found in the catalog for this table"})
			continue
		}
		if exposed[key] {
			out.Errors = append(out.Errors, batchError{w.name, "already exposed"})
			continue
		}
		created, err := sess.AddField(ctx, t.ID, gateway.AddFieldRequest{FieldName: cf.FieldName, FieldType: cf.FieldType, Description: w.desc, UpstreamFieldID: cf.ID})
		if err != nil {
			if isAuthError(err) {
				return gatewayError(err, "add fields", roleAdmin, "Table not found"), nil
			}
			out.Errors = append(out.Errors, batchError{w.name, gatewayErrorText(err, "add fields", roleAdmin, "Table not found")})
			continue
		}
		exposed[key] = true
		out.OK = append(out.OK, *created)
	}
	out.StatusAfter, out.Missing = statusAfter(ctx, sess, t.ID)
	if len(out.OK) == 0 {
		return errorJSONResult(out), nil
	}
	return jsonResult(out), nil
}

// ── update_fields ────────────────────────────────────────────────────────

const updateFieldsDescription = `Set the description of exposed fields of a registered table (used in the LLM doc). Batch of {field_name, description}; unknown names are reported in errors. Requires gateway role admin.`

const updateFieldsInputSchema = `{
  "type": "object",
  "properties": {` + tableAddressSchema + `,
    "fields": {
      "type": "array", "minItems": 1, "maxItems": 50,
      "items": {"type": "object", "properties": {"field_name": {"type": "string"}, "description": {"type": "string"}}, "required": ["field_name", "description"]}
    }
  },
  "required": ["fields"]
}`

func handleUpdateFields(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	t, errRes := resolveTable(ctx, sess, args)
	if errRes != nil {
		return errRes, nil
	}
	items, err := argObjectList(args, "fields")
	if err != nil {
		return invalidArgs(err), nil
	}
	if err := checkBatch("fields", len(items)); err != nil {
		return invalidArgs(err), nil
	}
	byName := make(map[string]gateway.UsedField, len(t.Fields))
	for _, f := range t.Fields {
		byName[strings.ToLower(f.FieldName)] = f
	}
	out := fieldsResult{TableID: t.ID, TableName: t.TableName, OK: []gateway.UsedField{}, Errors: []batchError{}}
	for i, it := range items {
		name := argString(it, "field_name")
		if name == "" {
			return invalidArgs(fmt.Errorf("'fields[%d].field_name' is required", i)), nil
		}
		desc, ok := it["description"].(string)
		if !ok {
			return invalidArgs(fmt.Errorf("'fields[%d].description' is required (string)", i)), nil
		}
		f, ok := byName[strings.ToLower(name)]
		if !ok {
			out.Errors = append(out.Errors, batchError{name, "not an exposed field of this table (see get_table_info)"})
			continue
		}
		updated, err := sess.PatchFieldDescription(ctx, t.ID, f.ID, desc)
		if err != nil {
			if isAuthError(err) {
				return gatewayError(err, "update fields", roleAdmin, "Field not found"), nil
			}
			out.Errors = append(out.Errors, batchError{name, gatewayErrorText(err, "update fields", roleAdmin, "Field not found")})
			continue
		}
		out.OK = append(out.OK, *updated)
	}
	out.StatusAfter, out.Missing = statusAfter(ctx, sess, t.ID)
	if len(out.OK) == 0 {
		return errorJSONResult(out), nil
	}
	return jsonResult(out), nil
}

// ── remove_fields ────────────────────────────────────────────────────────

const removeFieldsDescription = `Stop exposing fields of a registered table (batch of field names). Removing the last field turns the table back into a draft (flag still on, but no column exposed) — the result then carries a warning. Requires gateway role admin.`

const removeFieldsInputSchema = `{
  "type": "object",
  "properties": {` + tableAddressSchema + `,
    "field_names": {"type": "array", "minItems": 1, "maxItems": 50, "items": {"type": "string"}}
  },
  "required": ["field_names"]
}`

func handleRemoveFields(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	t, errRes := resolveTable(ctx, sess, args)
	if errRes != nil {
		return errRes, nil
	}
	names, err := argStringList(args, "field_names")
	if err != nil {
		return invalidArgs(err), nil
	}
	if err := checkBatch("field_names", len(names)); err != nil {
		return invalidArgs(err), nil
	}
	byName := make(map[string]gateway.UsedField, len(t.Fields))
	for _, f := range t.Fields {
		byName[strings.ToLower(f.FieldName)] = f
	}
	out := fieldsResult{TableID: t.ID, TableName: t.TableName, OK: []gateway.UsedField{}, Errors: []batchError{}}
	for _, name := range names {
		f, ok := byName[strings.ToLower(name)]
		if !ok {
			out.Errors = append(out.Errors, batchError{name, "not an exposed field of this table (see get_table_info)"})
			continue
		}
		if err := sess.DeleteField(ctx, t.ID, f.ID); err != nil {
			if isAuthError(err) {
				return gatewayError(err, "remove fields", roleAdmin, "Field not found"), nil
			}
			out.Errors = append(out.Errors, batchError{name, gatewayErrorText(err, "remove fields", roleAdmin, "Field not found")})
			continue
		}
		out.OK = append(out.OK, f)
	}
	out.StatusAfter, out.Missing = statusAfter(ctx, sess, t.ID)
	if out.StatusAfter == StatusDraft {
		out.Warning = "table is now a draft (0 exposed fields): it is flagged active but exposes no column until add_fields is called"
	}
	if len(out.OK) == 0 {
		return errorJSONResult(out), nil
	}
	return jsonResult(out), nil
}
```

In `registry.go` `NewRegistry`, after `add_tables`:

```go
	r.register("add_fields", addFieldsDescription, addFieldsInputSchema, handleAddFields, nil)
	r.register("update_fields", updateFieldsDescription, updateFieldsInputSchema, handleUpdateFields, nil)
	r.register("remove_fields", removeFieldsDescription, removeFieldsInputSchema, handleRemoveFields, nil)
```

- [ ] **Step 4: Run tests and commit**

Run: `gofmt -l . ; go vet ./... && go test ./... 2>&1 | tail -5`
Expected: all `ok`.

Stage `apps-microservices/mcp-table-service/internal/tools` and commit with subject `feat(mcp-table-service): add_fields, update_fields and remove_fields tools`, body:
- `EN: Field exposure resolved from the catalog (type + upstream id), per-field descriptions, all_fields mode, status_after and draft warning when the last field is removed.`
- `FR: Exposition de champs resolue depuis le catalogue (type + id amont), descriptions par champ, mode all_fields, status_after et avertissement brouillon quand le dernier champ est retire.`

---

## Task 10: `update_table_info` and `sync_table_catalog`

**Files:**
- Modify: `apps-microservices/mcp-table-service/internal/tools/table_tools.go` (append; add `errors` to imports)
- Modify: `apps-microservices/mcp-table-service/internal/tools/table_tools_test.go` (append)
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go`

**Interfaces:**
- Consumes: `resolveTable`, `registeredByName`, `serializeRelations`, `detail`, `tableAddressSchema`, `draftTable()` (test), `gateway.Session.PatchUsedTable/RefreshCatalog/SyncFieldTypes`.
- Produces: `handleUpdateTableInfo`, `handleSyncTableCatalog`, `syncResult`, `optionalString(args, key) (*string, error)`.

- [ ] **Step 1: Append the failing tests to table_tools_test.go**

```go
func TestUpdateTableInfo_PatchesDescriptionNotesRows(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, sampleTable()))
	f.on("PATCH", "/api/v1/bdd/used/tables/t-1", func(w http.ResponseWriter, r *http.Request) {
		var req gateway.PatchUsedTableRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		if req.Description == nil || *req.Description != "Produits vendus" || req.Notes == nil || *req.Notes != "N" || req.Rows == nil || *req.Rows != 12 || req.DefaultOrderBy != nil || req.Relations != nil {
			t.Errorf("patch body = %s", mustJSON(req))
		}
		tb := sampleTable()
		tb.Description, tb.Notes, tb.Rows = "Produits vendus", "N", rowsPtr(12)
		f.json(200, tb)(w, r)
	})
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "update_table_info", Arguments: map[string]any{
		"table_id": "t-1", "description": "Produits vendus", "notes": "N", "rows": float64(12),
	}})
	var out tableDetail
	decodeResult(t, res, &out)
	if out.Description != "Produits vendus" || out.Status != StatusActive || len(out.Missing) != 0 {
		t.Fatalf("out = %+v", out)
	}
}

func TestUpdateTableInfo_RelationsValidatedAndSerialized(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, sampleTable()))
	categories := sampleTable()
	categories.ID, categories.TableName = "t-cat", "categories"
	emptyTarget := draftTable()
	emptyTarget.ID, emptyTarget.TableName = "t-e", "fournisseurs"
	f.on("GET", "/api/v1/bdd/used/tables", f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{sampleTable(), categories, emptyTarget}, Total: 3, Page: 1, Limit: 100}))
	var patched json.RawMessage
	f.on("PATCH", "/api/v1/bdd/used/tables/t-1", func(w http.ResponseWriter, r *http.Request) {
		var req gateway.PatchUsedTableRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		patched = req.Relations
		tb := sampleTable()
		tb.Relations = req.Relations
		f.json(200, tb)(w, r)
	})
	reg := NewRegistry(f.deps())
	call := func(rel any) *mcp.CallToolResult {
		return reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "update_table_info", Arguments: map[string]any{"table_id": "t-1", "relations": rel}})
	}

	res := call([]any{map[string]any{"self_col": "categorie_id", "target_table": "categories", "target_col": "id"}})
	if res.IsError || string(patched) != `{"categories":"produits.categorie_id -> categories.id"}` {
		t.Fatalf("res=%s patched=%s", resultText(res), patched)
	}
	res = call([]any{})
	if res.IsError || string(patched) != `[]` {
		t.Fatalf("clear: res=%s patched=%s", resultText(res), patched)
	}
	res = call([]any{map[string]any{"self_col": "x", "target_table": "unknown", "target_col": "id"}})
	if !res.IsError || !strings.Contains(resultText(res), `"unknown" is not registered`) {
		t.Fatalf("res = %s", resultText(res))
	}
	res = call([]any{map[string]any{"self_col": "x", "target_table": "fournisseurs", "target_col": "id"}})
	if !res.IsError || !strings.Contains(resultText(res), "no exposed field") {
		t.Fatalf("res = %s", resultText(res))
	}
	res = call([]any{map[string]any{"self_col": "x", "target_table": "produits", "target_col": "id"}})
	if !res.IsError || !strings.Contains(resultText(res), "itself") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestUpdateTableInfo_ArgValidation(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, sampleTable()))
	reg := NewRegistry(f.deps())
	res := reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "update_table_info", Arguments: map[string]any{"table_id": "t-1"}})
	if !res.IsError || !strings.Contains(resultText(res), "at least one of") {
		t.Fatalf("res = %s", resultText(res))
	}
	res = reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "update_table_info", Arguments: map[string]any{"table_id": "t-1", "rows": float64(-1)}})
	if !res.IsError || !strings.Contains(resultText(res), "'rows'") {
		t.Fatalf("res = %s", resultText(res))
	}
	res = reg.CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "update_table_info", Arguments: map[string]any{"table_id": "t-1", "description": float64(3)}})
	if !res.IsError || !strings.Contains(resultText(res), "'description'") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestSyncTableCatalog(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables", f.json(200, gateway.UsedListResponse{Tables: []gateway.UsedTable{sampleTable()}, Total: 1, Page: 1, Limit: 100}))
	refreshed := sampleTable()
	refreshed.PrimaryKey, refreshed.Rows = "id", rowsPtr(4242)
	f.on("POST", "/api/v1/bdd/used/tables/t-1/refresh-catalog", f.json(200, refreshed))
	f.on("POST", "/api/v1/bdd/used/tables/t-1/sync-field-types", f.json(200, gateway.SyncFieldTypesResponse{Updated: 1, Total: 1}))
	// table_name without database_id goes through the list endpoint.
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "sync_table_catalog", Arguments: map[string]any{"table_name": "produits"}})
	var out syncResult
	decodeResult(t, res, &out)
	if out.PrimaryKey != "id" || out.Rows == nil || *out.Rows != 4242 || out.FieldTypesUpdated != 1 || out.TotalFields != 1 {
		t.Fatalf("out = %+v", out)
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/tools/ -run 'UpdateTableInfo|SyncTableCatalog' 2>&1 | head -5`
Expected: `undefined: syncResult`.

- [ ] **Step 3: Append the two tools to table_tools.go** (and add `"errors"` to its imports)

```go
// ── update_table_info ────────────────────────────────────────────────────

const updateTableInfoDescription = `Complete a registered table's documentation and metadata (the "Description de la table" and "Metadonnees" sections of the table configuration page): description (functional description used in the LLM doc), notes, default_order_by, rows (manual row count) and relations. Relations are given as rows {self_col, target_table, target_col}; the list REPLACES the stored relations (pass [] to clear). Every target_table must be a registered table with at least one exposed field, and cannot be the table itself. At least one attribute is required. Returns the updated table with status and missing checklist. Requires gateway role admin.`

const updateTableInfoInputSchema = `{
  "type": "object",
  "properties": {` + tableAddressSchema + `,
    "description": {"type": "string", "description": "Functional description used in the LLM doc."},
    "notes": {"type": "string", "description": "Free notes for the LLM (caveats, business rules)."},
    "default_order_by": {"type": "string", "description": "Default ORDER BY hint, e.g. 'date_creation DESC'."},
    "rows": {"type": "integer", "minimum": 0, "description": "Manual row count (use sync_table_catalog to fetch it from the catalog instead)."},
    "relations": {
      "type": "array",
      "items": {"type": "object", "properties": {"self_col": {"type": "string"}, "target_table": {"type": "string"}, "target_col": {"type": "string"}}, "required": ["self_col", "target_table", "target_col"]},
      "description": "Foreign-key style links to other registered tables. Replaces the stored list."
    }
  }
}`

// optionalString returns the string at key, nil when absent, error when not a string.
func optionalString(args map[string]any, key string) (*string, error) {
	v, present := args[key]
	if !present {
		return nil, nil
	}
	s, ok := v.(string)
	if !ok {
		return nil, fmt.Errorf("'%s' must be a string", key)
	}
	return &s, nil
}

func handleUpdateTableInfo(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	t, errRes := resolveTable(ctx, sess, args)
	if errRes != nil {
		return errRes, nil
	}
	var req gateway.PatchUsedTableRequest
	touched := 0
	var err error
	if req.Description, err = optionalString(args, "description"); err != nil {
		return invalidArgs(err), nil
	} else if req.Description != nil {
		touched++
	}
	if req.Notes, err = optionalString(args, "notes"); err != nil {
		return invalidArgs(err), nil
	} else if req.Notes != nil {
		touched++
	}
	if req.DefaultOrderBy, err = optionalString(args, "default_order_by"); err != nil {
		return invalidArgs(err), nil
	} else if req.DefaultOrderBy != nil {
		touched++
	}
	if _, present := args["rows"]; present {
		n, ok := argInt(args, "rows")
		if !ok || n < 0 {
			return invalidArgs(errors.New("'rows' must be an integer >= 0")), nil
		}
		r := int64(n)
		req.Rows = &r
		touched++
	}
	if _, present := args["relations"]; present {
		items, err := argObjectList(args, "relations")
		if err != nil {
			return invalidArgs(err), nil
		}
		relRows := make([]RelationRow, 0, len(items))
		for _, it := range items {
			relRows = append(relRows, RelationRow{SelfCol: argString(it, "self_col"), TargetTable: argString(it, "target_table"), TargetCol: argString(it, "target_col")})
		}
		if len(relRows) > 0 {
			registered, err := registeredByName(ctx, sess, 0)
			if err != nil {
				return gatewayError(err, "list registered tables", roleReadOnly, "Registry not found"), nil
			}
			for i, r := range relRows {
				key := strings.ToLower(r.TargetTable)
				if key == strings.ToLower(t.TableName) {
					return errorResult(fmt.Sprintf("relations[%d]: a table cannot be related to itself", i)), nil
				}
				reg, ok := registered[key]
				if !ok {
					return errorResult(fmt.Sprintf("relations[%d]: target table %q is not registered (see list_registered_tables)", i, r.TargetTable)), nil
				}
				if len(reg.Fields) == 0 {
					return errorResult(fmt.Sprintf("relations[%d]: target table %q has no exposed field yet (call add_fields on it first)", i, r.TargetTable)), nil
				}
			}
		}
		raw, err := serializeRelations(t.TableName, relRows)
		if err != nil {
			return invalidArgs(err), nil
		}
		req.Relations = raw
		touched++
	}
	if touched == 0 {
		return invalidArgs(errors.New("provide at least one of description, notes, default_order_by, rows, relations")), nil
	}
	updated, err := sess.PatchUsedTable(ctx, t.ID, req)
	if err != nil {
		return gatewayError(err, "update table info", roleAdmin, "Table not found"), nil
	}
	return jsonResult(detail(updated)), nil
}

// ── sync_table_catalog ───────────────────────────────────────────────────

const syncTableCatalogDescription = `Re-synchronise a registered table with the upstream catalog: refresh its primary key and row count ("Re-synchroniser depuis le catalogue"), then update the types of its exposed fields ("Synchroniser les types de champs"). Use it when the catalog changed or when get_table_info reports unknown_primary_key / unknown_rows. Requires gateway role admin.`

const syncTableCatalogInputSchema = `{
  "type": "object",
  "properties": {` + tableAddressSchema + `
  }
}`

type syncResult struct {
	TableID           string   `json:"table_id"`
	TableName         string   `json:"table_name"`
	PrimaryKey        string   `json:"primary_key"`
	Rows              *int64   `json:"rows"`
	FieldTypesUpdated int      `json:"field_types_updated"`
	TotalFields       int      `json:"total_fields"`
	Status            string   `json:"status"`
	Missing           []string `json:"missing"`
}

func handleSyncTableCatalog(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	t, errRes := resolveTable(ctx, sess, args)
	if errRes != nil {
		return errRes, nil
	}
	refreshed, err := sess.RefreshCatalog(ctx, t.ID)
	if err != nil {
		return gatewayError(err, "sync table with catalog", roleAdmin, "Table not found"), nil
	}
	sync, err := sess.SyncFieldTypes(ctx, t.ID)
	if err != nil {
		return gatewayError(err, "sync field types", roleAdmin, "Table not found"), nil
	}
	return jsonResult(syncResult{
		TableID: refreshed.ID, TableName: refreshed.TableName, PrimaryKey: refreshed.PrimaryKey, Rows: refreshed.Rows,
		FieldTypesUpdated: sync.Updated, TotalFields: sync.Total,
		Status: tableStatus(refreshed), Missing: missingChecklist(refreshed),
	}), nil
}
```

In `registry.go` `NewRegistry`, after the field tools:

```go
	r.register("update_table_info", updateTableInfoDescription, updateTableInfoInputSchema, handleUpdateTableInfo, nil)
	r.register("sync_table_catalog", syncTableCatalogDescription, syncTableCatalogInputSchema, handleSyncTableCatalog, nil)
```

- [ ] **Step 4: Run tests and commit**

Run: `gofmt -l . ; go vet ./... && go test ./... 2>&1 | tail -5`
Expected: all `ok`.

Stage `apps-microservices/mcp-table-service/internal/tools` and commit with subject `feat(mcp-table-service): update_table_info and sync_table_catalog tools`, body:
- `EN: Description, notes, default order by, rows and relations (validated against registered tables with fields, serialized to the stored shape); catalog re-sync of primary key, rows and field types.`
- `FR: Description, notes, tri par defaut, lignes et relations (validees contre les tables enregistrees avec champs, serialisees au format stocke) ; resynchro catalogue de la cle primaire, des lignes et des types de champs.`

---

## Task 11: `set_tables_active`, `delete_tables`, and the 13-tool contract test

**Files:**
- Modify: `apps-microservices/mcp-table-service/internal/tools/table_tools.go` (append; add `net/http` to imports)
- Modify: `apps-microservices/mcp-table-service/internal/tools/table_tools_test.go` (append)
- Create: `apps-microservices/mcp-table-service/internal/tools/registry_test.go`
- Modify: `apps-microservices/mcp-table-service/internal/tools/registry.go`

**Interfaces:**
- Consumes: `gateway.Session.GetUsedTable/BulkSetActive/BulkDeleteUsedTables`, `destructive` annotation preset.
- Produces: `handleSetTablesActive`, `handleDeleteTables`, `activeResult`, `deleteResult`.

- [ ] **Step 1: Append the failing tests to table_tools_test.go**

```go
func TestSetTablesActive_RefusesZeroFieldTables(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/t-1", f.json(200, sampleTable()))
	f.on("GET", "/api/v1/bdd/used/tables/t-d", func(w http.ResponseWriter, r *http.Request) {
		d := draftTable()
		d.ID, d.TableName, d.IsActive = "t-d", "brouillon", false
		f.json(200, d)(w, r)
	})
	f.on("GET", "/api/v1/bdd/used/tables/t-x", f.json(404, map[string]string{"error": "table not found"}))
	f.on("PATCH", "/api/v1/bdd/used/tables/bulk", func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if !strings.Contains(string(body), `"ids":["t-1"]`) || !strings.Contains(string(body), `"is_active":true`) {
			t.Errorf("bulk body = %s", body)
		}
		f.json(200, map[string]int{"affected": 1})(w, r)
	})
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "set_tables_active", Arguments: map[string]any{"table_ids": []any{"t-1", "t-d", "t-x"}, "active": true}})
	var out activeResult
	decodeResult(t, res, &out)
	if out.Affected != 1 || out.Requested != 3 || len(out.Errors) != 2 {
		t.Fatalf("out = %+v", out)
	}
	if !strings.Contains(out.Errors[0].Error, "no exposed field") || out.Errors[1].Error != "Table not found" {
		t.Fatalf("errors = %+v", out.Errors)
	}
}

func TestSetTablesActive_DeactivateNeedsNoCheck(t *testing.T) {
	f := newFakeGateway(t)
	f.on("PATCH", "/api/v1/bdd/used/tables/bulk", f.json(200, map[string]int{"affected": 2}))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "set_tables_active", Arguments: map[string]any{"table_ids": []any{"a", "b"}, "active": false}})
	var out activeResult
	decodeResult(t, res, &out)
	if out.Affected != 2 || len(out.Errors) != 0 || out.Active {
		t.Fatalf("out = %+v", out)
	}
	if n := len(f.calls("GET", "/api/v1/bdd/used/tables/a")); n != 0 {
		t.Fatalf("deactivation must not read tables, got %d GETs", n)
	}
}

func TestSetTablesActive_AllRefusedIsError(t *testing.T) {
	f := newFakeGateway(t)
	f.on("GET", "/api/v1/bdd/used/tables/t-d", f.json(200, draftTable()))
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "set_tables_active", Arguments: map[string]any{"table_ids": []any{"t-d"}, "active": true}})
	if !res.IsError {
		t.Fatal("expected error result when nothing was activated")
	}
	if n := len(f.calls("PATCH", "/api/v1/bdd/used/tables/bulk")); n != 0 {
		t.Fatalf("no PATCH expected, got %d", n)
	}
	res = NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "set_tables_active", Arguments: map[string]any{"table_ids": []any{"t-d"}}})
	if !res.IsError || !strings.Contains(resultText(res), "'active'") {
		t.Fatalf("res = %s", resultText(res))
	}
}

func TestDeleteTables(t *testing.T) {
	f := newFakeGateway(t)
	f.on("DELETE", "/api/v1/bdd/used/tables/bulk", func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if !strings.Contains(string(body), `"ids":["t-1","t-2"]`) {
			t.Errorf("body = %s", body)
		}
		f.json(200, map[string]int{"affected": 1})(w, r)
	})
	res := NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "delete_tables", Arguments: map[string]any{"table_ids": []any{"t-1", "t-2"}}})
	var out deleteResult
	decodeResult(t, res, &out)
	if out.Affected != 1 || out.Requested != 2 || !strings.Contains(out.Note, "not found") {
		t.Fatalf("out = %+v", out)
	}
	res = NewRegistry(f.deps()).CallTool(userCtx("a@b"), &mcp.CallToolParams{Name: "delete_tables", Arguments: map[string]any{"table_ids": []any{}}})
	if !res.IsError || !strings.HasPrefix(resultText(res), "invalid arguments:") {
		t.Fatalf("res = %s", resultText(res))
	}
}
```

- [ ] **Step 2: Write the registry contract test**

Create `internal/tools/registry_test.go`:

```go
package tools

import (
	"context"
	"encoding/json"
	"sort"
	"strings"
	"testing"

	"github.com/hellopro/mcp-table/internal/mcp"
)

var expectedTools = []string{
	"list_registered_tables", "get_table_info",
	"list_databases", "list_catalog_tables", "list_catalog_fields",
	"add_tables", "add_fields", "update_table_info", "update_fields", "remove_fields",
	"set_tables_active", "delete_tables", "sync_table_catalog",
}

func TestRegistry_ExposesExactlyThe13Tools(t *testing.T) {
	tools := NewRegistry(&Deps{}).ListTools()
	got := make([]string, 0, len(tools))
	for _, tl := range tools {
		got = append(got, tl.Name)
		var schema map[string]any
		if err := json.Unmarshal(tl.InputSchema, &schema); err != nil || schema["type"] != "object" {
			t.Errorf("%s: inputSchema is not a JSON object schema: %v", tl.Name, err)
		}
		if !strings.Contains(tl.Description, "Requires gateway role") {
			t.Errorf("%s: description must state the required gateway role", tl.Name)
		}
	}
	want := append([]string(nil), expectedTools...)
	sort.Strings(got)
	sort.Strings(want)
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("tools = %v\nwant  %v", got, want)
	}
	if len(got) != 13 {
		t.Fatalf("len = %d", len(got))
	}
}

func TestRegistry_Annotations(t *testing.T) {
	byName := map[string]mcp.Tool{}
	for _, tl := range NewRegistry(&Deps{}).ListTools() {
		byName[tl.Name] = tl
	}
	if a := byName["delete_tables"].Annotations; a == nil || a.DestructiveHint == nil || !*a.DestructiveHint {
		t.Fatal("delete_tables must carry destructiveHint=true")
	}
	for _, n := range []string{"list_registered_tables", "get_table_info", "list_databases", "list_catalog_tables", "list_catalog_fields"} {
		if a := byName[n].Annotations; a == nil || a.ReadOnlyHint == nil || !*a.ReadOnlyHint {
			t.Errorf("%s must carry readOnlyHint=true", n)
		}
	}
}

func TestMCPHandler_ToolsListWorksWithoutIdentity(t *testing.T) {
	h := NewMCPHandler("mcp-table", "0.1.0", NewRegistry(&Deps{}))
	resp := h.Handle(context.Background(), &mcp.Request{JSONRPC: "2.0", ID: json.RawMessage(`1`), Method: "tools/list"})
	var res mcp.ListToolsResult
	if err := json.Unmarshal(resp.Result, &res); err != nil || len(res.Tools) != 13 {
		t.Fatalf("tools/list = %s err=%v", resp.Result, err)
	}
	resp = h.Handle(context.Background(), &mcp.Request{JSONRPC: "2.0", ID: json.RawMessage(`2`), Method: "tools/call", Params: json.RawMessage(`{"name":"nope"}`)})
	var call mcp.CallToolResult
	_ = json.Unmarshal(resp.Result, &call)
	if !call.IsError || !strings.Contains(call.Content[0].Text, "unknown tool") {
		t.Fatalf("call = %+v", call)
	}
}
```

- [ ] **Step 3: Run to verify failure**

Run: `go test ./internal/tools/ -run 'SetTablesActive|DeleteTables|Registry|MCPHandler' 2>&1 | head -5`
Expected: `undefined: activeResult`, `undefined: deleteResult`.

- [ ] **Step 4: Append the two tools to table_tools.go** (and add `"net/http"` to its imports)

```go
// ── set_tables_active ────────────────────────────────────────────────────

const setTablesActiveDescription = `Activate or deactivate registered tables (the "Activer" / "Desactiver" bulk actions of the Tables BDD page). Deactivated tables are hidden from the MCP BDD runner. Activation is refused for tables with no exposed field — call add_fields first; such tables are reported in errors while the others are still activated. Requires gateway role admin.`

const setTablesActiveInputSchema = `{
  "type": "object",
  "properties": {
    "table_ids": {"type": "array", "minItems": 1, "maxItems": 50, "items": {"type": "string"}, "description": "Registry UUIDs (from list_registered_tables)."},
    "active": {"type": "boolean", "description": "true to activate, false to deactivate."}
  },
  "required": ["table_ids", "active"]
}`

type activeResult struct {
	Active    bool         `json:"active"`
	Requested int          `json:"requested"`
	Affected  int64        `json:"affected"`
	Errors    []batchError `json:"errors"`
}

func handleSetTablesActive(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	ids, err := argStringList(args, "table_ids")
	if err != nil {
		return invalidArgs(err), nil
	}
	if err := checkBatch("table_ids", len(ids)); err != nil {
		return invalidArgs(err), nil
	}
	active, ok := argBool(args, "active")
	if !ok {
		return invalidArgs(errors.New("'active' (true|false) is required")), nil
	}
	action := "deactivate tables"
	if active {
		action = "activate tables"
	}
	out := activeResult{Active: active, Requested: len(ids), Errors: []batchError{}}
	targets := ids
	if active {
		// Activation rule: a table without exposed field must stay a draft.
		targets = make([]string, 0, len(ids))
		for _, id := range ids {
			t, err := sess.GetUsedTable(ctx, id)
			if err != nil {
				if gateway.IsStatus(err, http.StatusNotFound) {
					out.Errors = append(out.Errors, batchError{id, "Table not found"})
					continue
				}
				return gatewayError(err, action, roleAdmin, "Table not found"), nil
			}
			if len(t.Fields) == 0 {
				out.Errors = append(out.Errors, batchError{id, fmt.Sprintf("cannot activate %q: table has no exposed field (call add_fields first)", t.TableName)})
				continue
			}
			targets = append(targets, id)
		}
	}
	if len(targets) == 0 {
		return errorJSONResult(out), nil
	}
	n, err := sess.BulkSetActive(ctx, targets, active)
	if err != nil {
		return gatewayError(err, action, roleAdmin, "Table not found"), nil
	}
	out.Affected = n
	return jsonResult(out), nil
}

// ── delete_tables ────────────────────────────────────────────────────────

const deleteTablesDescription = `Permanently remove registered tables from the gateway registry together with their exposed fields and descriptions (the "Supprimer" action of the Tables BDD page). This never touches the underlying MySQL tables, only the registry. Irreversible — prefer set_tables_active with active=false to hide a table temporarily. Requires gateway role admin.`

const deleteTablesInputSchema = `{
  "type": "object",
  "properties": {
    "table_ids": {"type": "array", "minItems": 1, "maxItems": 50, "items": {"type": "string"}, "description": "Registry UUIDs (from list_registered_tables)."}
  },
  "required": ["table_ids"]
}`

type deleteResult struct {
	Requested int    `json:"requested"`
	Affected  int64  `json:"affected"`
	Note      string `json:"note,omitempty"`
}

func handleDeleteTables(ctx context.Context, deps *Deps, args map[string]any) (*mcp.CallToolResult, error) {
	sess, errRes := requireSession(ctx, deps)
	if errRes != nil {
		return errRes, nil
	}
	ids, err := argStringList(args, "table_ids")
	if err != nil {
		return invalidArgs(err), nil
	}
	if err := checkBatch("table_ids", len(ids)); err != nil {
		return invalidArgs(err), nil
	}
	n, err := sess.BulkDeleteUsedTables(ctx, ids)
	if err != nil {
		return gatewayError(err, "delete tables", roleAdmin, "Table not found"), nil
	}
	out := deleteResult{Requested: len(ids), Affected: n}
	if n < int64(len(ids)) {
		out.Note = fmt.Sprintf("%d id(s) were not found in the registry", int64(len(ids))-n)
	}
	return jsonResult(out), nil
}
```

In `registry.go` `NewRegistry`, after `sync_table_catalog`:

```go
	r.register("set_tables_active", setTablesActiveDescription, setTablesActiveInputSchema, handleSetTablesActive, nil)
	r.register("delete_tables", deleteTablesDescription, deleteTablesInputSchema, handleDeleteTables, destructive)
```

- [ ] **Step 5: Run the whole module and commit**

Run: `gofmt -l . ; go vet ./... && go build ./... && go test ./... 2>&1 | tail -6`
Expected: gofmt silent; every package `ok`; `TestRegistry_ExposesExactlyThe13Tools` passes.

Stage `apps-microservices/mcp-table-service/internal/tools` and commit with subject `feat(mcp-table-service): set_tables_active and delete_tables tools; 13-tool contract test`, body:
- `EN: Activation refused for zero-field tables (per-table errors, others still activated), deactivation unguarded, destructive delete with not-found note; registry test pins the 13 tool names, schemas and annotations.`
- `FR: Activation refusee pour les tables sans champ (erreurs par table, les autres activees), desactivation sans garde, suppression destructive avec note des ids introuvables ; le test de registre fige les 13 noms, schemas et annotations.`

---

## Task 12: Deployment and documentation

**Files:**
- Modify: `docker-compose.yml` (gateway env block: after the `ZOHO_ADMIN_TOKEN` line; new service block after the `mcp-zoho-service` block, before `# ── MCP Gateway Frontend`)
- Create: `apps-microservices/mcp-table-service/CLAUDE.md`
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md` (Environment Variables table after the `BDD_CATALOG_TOKEN` row; Conventions list after the **BDD scope filter** bullet)
- Modify: `docs/superpowers/specs/2026-09-07-mcp-table-service-design.md` (addendum)

- [ ] **Step 1: docker-compose — gateway env**

In the `mcp-gateway-service` block, after `- ZOHO_ADMIN_TOKEN=${ZOHO_GATEWAY_TOKEN}` add:

```yaml
      # mcp-table-service act-as secret: X-Admin-Token + X-Act-As-Email on /api/v1/bdd/*.
      # Must equal MCP_TABLE_GATEWAY_TOKEN on the service side. Empty = act-as disabled.
      - TABLE_SERVICE_TOKEN=${MCP_TABLE_SERVICE_TOKEN}
```

- [ ] **Step 2: docker-compose — service block**

Insert after the `mcp-zoho-service` block (after its `logging: *logging_defaults` line) and before `  # ── MCP Gateway Frontend`:

```yaml
  # ── MCP Table Service ──────────────────────────────────────────────────
  # MCP tools over the gateway's BDD used-tables registry. Thin façade: every
  # tool calls the gateway REST API on behalf of the end user (X-Act-As-Email);
  # the gateway enforces the user's role. Register it in the gateway Servers UI
  # with url http://mcp-table-service:8597/mcp, tool_prefix "tables" and the
  # auth header X-Admin-Token=${MCP_TABLE_SERVICE_TOKEN}.
  mcp-table-service:
    build:
      context: ./apps-microservices/mcp-table-service
      dockerfile: Dockerfile
    container_name: mcp-table-service
    profiles: [ "mcp" ]
    restart: unless-stopped
    ports:
      - "8597:8597"
    environment:
      - MCP_PORT=8597
      - MCP_SERVICE_NAME=mcp-table
      - MCP_GATEWAY_URL=http://mcp-gateway-service:8592
      - MCP_TABLE_GATEWAY_TOKEN=${MCP_TABLE_SERVICE_TOKEN}
      - MCP_GATEWAY_TIMEOUT=15
    depends_on:
      - mcp-gateway-service
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8597/health" ]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - services-net
    logging: *logging_defaults

```

- [ ] **Step 3: Validate the compose file**

Run: `cd /home/hellopro/RAG-HP-PUB && MCP_TABLE_SERVICE_TOKEN=x docker compose --profile mcp config 2>/dev/null | grep -A3 "^  mcp-table-service:" | head -6; docker compose --profile mcp config -q; echo exit=$?`
Expected: the service block is printed with `container_name: mcp-table-service`, and `exit=0` (warnings about other unset variables are fine).

- [ ] **Step 4: Service CLAUDE.md**

Create `apps-microservices/mcp-table-service/CLAUDE.md` with this content:

````markdown
# mcp-table-service

MCP server exposing the gateway's **BDD used-tables registry** (the "Tables BDD" admin pages) as 13 tools, with the calling user's gateway role as the only privilege model.

## Tech Stack

- Go 1.24, standard library only (no external modules)
- MCP v2025-03-26 (JSON-RPC 2.0 over SSE + Streamable HTTP)
- Talks to `mcp-gateway-service` REST (`/api/v1/bdd/*`) — never to MySQL or the upstream catalog directly
- Docker multi-stage `golang:1.24-alpine` → `alpine:3.20`, non-root, port **8597**

## Run

```bash
cd apps-microservices/mcp-table-service
MCP_GATEWAY_URL=http://localhost:8592 MCP_TABLE_GATEWAY_TOKEN=<secret> go run ./cmd/server
go vet ./... && go test ./...

# Docker (from repo root)
docker compose --profile mcp build mcp-table-service
docker compose --profile mcp up mcp-table-service
```

## Folder Structure

```
cmd/server/main.go            # boot (refuses to start without gateway URL + token), mux, shutdown
internal/config/config.go     # env loading
internal/mcp/types.go         # JSON-RPC / MCP types + ToolAnnotations
internal/transport/
  sse.go, streamable_http.go  # transports
  identity.go                 # X-Admin-Token gate (health exempt); X-End-User-Email → context
internal/gateway/
  client.go, types.go, errors.go  # typed act-as client: Session = Client bound to one end user
internal/tools/
  registry.go, handler.go     # registration + dispatch
  args.go, session.go, errors.go, resolve.go, status.go, relations.go   # shared helpers
  read_tools.go, catalog_tools.go, table_tools.go, field_tools.go       # the 13 tools
```

## Tools

Gateway tool prefix `tables` → clients see `tables_<name>`.

| Tool | Gateway role | Wraps |
|---|---|---|
| `list_registered_tables` | read-only | `GET /bdd/used/tables` |
| `get_table_info` | read-only | `GET /bdd/used/tables/{id}` (+ list search for name lookup) |
| `list_databases` | admin | `GET /bdd/catalog/databases` |
| `list_catalog_tables` | admin | catalog tables + registry (flags `registered`) |
| `list_catalog_fields` | admin | catalog fields + registry (flags `exposed`) |
| `add_tables` | admin | catalog lookup → `POST /bdd/used/tables/bulk` → best-effort `refresh-catalog` |
| `add_fields` | admin | catalog fields → `POST /bdd/used/tables/{id}/fields` per field |
| `update_table_info` | admin | `PATCH /bdd/used/tables/{id}` (description, notes, default_order_by, rows, relations) |
| `update_fields` | admin | `PATCH /bdd/used/tables/{id}/fields/{fid}` per field |
| `remove_fields` | admin | `DELETE /bdd/used/tables/{id}/fields/{fid}` per field |
| `set_tables_active` | admin | `PATCH /bdd/used/tables/bulk` (activation refused for zero-field tables) |
| `delete_tables` | admin | `DELETE /bdd/used/tables/bulk` |
| `sync_table_catalog` | admin | `refresh-catalog` + `sync-field-types` |

Computed `status`: `inactive` (flag off), `draft` (flag on, 0 fields), `active`. A table is only exposed with columns once it has fields: **`add_fields` is the activation step**, and `set_tables_active(true)` refuses zero-field tables.

Batch tools return `{ok, errors}`, capped at 50 items (`all_fields` excepted), `isError` only when nothing succeeded.

## Privilege flow

1. Gateway forwards the OAuth2 user's email as `X-End-User-Email` (tool prefix `tables`), plus the static `X-Admin-Token` from the `mcp_servers` row.
2. This service checks `X-Admin-Token == MCP_TABLE_GATEWAY_TOKEN`; `tools/call` without an end-user email fails closed (scope tokens are not supported). `initialize` / `tools/list` need no identity.
3. Each tool calls the gateway with `X-Admin-Token` + `X-Act-As-Email`; the gateway's act-as branch (`internal/auth/actas.go`, only on `/api/v1/bdd/*`, present in both JWT and SSO middlewares) resolves the role from `gateway_users` and applies its normal admin / read-only gate. `created_by` is the real user.
4. Gateway 403 → "Your gateway role does not allow this action…"; 401 → shared secret mismatch (configuration error, logged).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_PORT` | `8597` | Listen port |
| `MCP_SERVICE_NAME` | `mcp-table` | MCP serverInfo name |
| `MCP_SERVICE_VERSION` | `0.1.0` | MCP serverInfo version |
| `MCP_GATEWAY_URL` | — (required) | e.g. `http://mcp-gateway-service:8592` |
| `MCP_TABLE_GATEWAY_TOKEN` | — (required) | Shared secret, inbound and outbound `X-Admin-Token`. Must equal gateway `TABLE_SERVICE_TOKEN`. `.env` key: `MCP_TABLE_SERVICE_TOKEN`. |
| `MCP_GATEWAY_TIMEOUT` | `15` | Seconds per gateway call (refresh-catalog uses 10 s, add_tables is bounded at 120 s) |

## Gateway registration (admin, Servers UI)

URL `http://mcp-table-service:8597/mcp`, tool prefix `tables`, auth header `X-Admin-Token: <MCP_TABLE_SERVICE_TOKEN>`. Discovery yields the 13 tools; `tools/list` is served from the gateway's cached catalog (no per-role hiding — enforcement happens at call time).

## Boundaries

- No MySQL, no upstream catalog access, no state: everything goes through the gateway REST API.
- No registry-wide `_meta` editing, no export/import, no moving tables between databases.
````

- [ ] **Step 5: Gateway CLAUDE.md**

In the Environment Variables table, after the `BDD_CATALOG_TOKEN` row, add:

```markdown
| `TABLE_SERVICE_TOKEN` | — | Shared secret `mcp-table-service` presents as `X-Admin-Token` together with `X-Act-As-Email` on `/api/v1/bdd/*`. Enables the act-as branch in both auth middlewares; empty = disabled. Must equal `MCP_TABLE_GATEWAY_TOKEN` on the service (`.env`: `MCP_TABLE_SERVICE_TOKEN`). |
```

In Conventions, after the **BDD scope filter** bullet, add:

```markdown
- **Act-as for mcp-table-service** (`internal/auth/actas.go`): when `TABLE_SERVICE_TOKEN` is set, a request on a `/api/v1/bdd/*` path carrying `X-Admin-Token` equal to it (constant-time compare) and a non-empty `X-Act-As-Email` is authenticated as that email, with the role resolved from `gateway_users` (unknown → `config-only`). The branch exists in `auth.Middleware` **and** `sso.Middleware.Handler` (production runs SSO mode); `roleCheckMiddleware` / `isAdminOnly` and every BDD handler are unchanged, so the MCP tools obey exactly the UI's rules and `created_by` is the real user. The gateway forwards `X-End-User-Email` / `X-End-User-Login` to backends whose `ToolPrefix == "tables"` (also inside the server-authorization bypass, like Zoho); no filter header is injected for that prefix. Tests: `internal/auth/actas_test.go`, `internal/sso/middleware_actas_test.go`, `internal/gateway/scoped_gateway_tables_test.go`.
```

- [ ] **Step 6: Spec addendum**

Append to `docs/superpowers/specs/2026-09-07-mcp-table-service-design.md`:

```markdown

## 13. Addendum (implementation plan, 2026-09-07)

- §5.2 said the act-as branch lives in `internal/auth/middleware.go`. `app.go` `wrapAuthMiddleware` uses **either** that middleware **or** `sso.Middleware.Handler` when `SSO_ENABLED=true` (the production mode), so the check is implemented once as `auth.ActAsEmail` and called from both middlewares. `sso.Middleware` gains `WithTableServiceToken`.
- `add_fields` accepts `all_fields: true`, which is not subject to the 50-item cap (each column is its own gateway call).
- Batch results are `isError` only when no item succeeded, and then still carry the per-item reasons.
```

- [ ] **Step 7: Commit**

Stage `docker-compose.yml`, `apps-microservices/mcp-table-service/CLAUDE.md`, `apps-microservices/mcp-gateway-service/CLAUDE.md`, `docs/superpowers/specs/2026-09-07-mcp-table-service-design.md` and commit with subject `chore(mcp-table-service): compose service, gateway TABLE_SERVICE_TOKEN, docs`, body:
- `EN: docker-compose block for mcp-table-service (profile mcp, port 8597), TABLE_SERVICE_TOKEN on the gateway, service CLAUDE.md, gateway CLAUDE.md act-as convention, spec addendum (SSO middleware).`
- `FR: Bloc docker-compose pour mcp-table-service (profil mcp, port 8597), TABLE_SERVICE_TOKEN sur le gateway, CLAUDE.md du service, convention act-as dans le CLAUDE.md du gateway, addendum de spec (middleware SSO).`

Note: `apps-microservices/mcp-gateway-service/CLAUDE.md` already carries an unrelated uncommitted hunk (backend metadata bullet); stage only this task's hunks with the interactive patch mode if it is still present.

---

## Acceptance mapping (spec §12 → tasks)

| Spec acceptance | Where it is proven |
|---|---|
| 1. `go vet`, `go build`, `go test` clean in both modules | Last step of every task; Tasks 1–2 (gateway), 3–11 (service) |
| 2. `tools/list` returns exactly the 13 names | Task 11 `TestRegistry_ExposesExactlyThe13Tools`, `TestMCPHandler_ToolsListWorksWithoutIdentity` |
| 3. read-only user: list OK, add_tables role error; admin: add_tables → add_fields → `status: "active"`; zero-field activation refused | Task 6 `TestListRegisteredTables_*`, Task 8 `TestAddTables_ForbiddenForReadOnly`, Task 9 `TestAddFields_ExplicitNamesActivateDraft`, Task 11 `TestSetTablesActive_RefusesZeroFieldTables` |
| 4. `docker compose --profile mcp config` validates | Task 12 Step 3 |
| 5. Both CLAUDE.md mention the env vars | Task 12 Steps 4–5 |

End-to-end smoke (manual, after deploy — needs the gateway DB and OAuth2, not automatable here): register the backend in the Servers UI, connect with an OAuth2 client as a read-only user and as an admin, run `tables_list_registered_tables`, `tables_add_tables`, `tables_add_fields`, `tables_get_table_info`; check `created_by` on the new row and the "Active" badge in `/bdd-tables`.
