# mcp-gateway Server Authorizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only "Serveur Autorisation" feature: admins grant specific end-users full unfiltered access to specific MCP servers. When the bearer token's email is in the grant table for the targeted server, the gateway skips ALL filter header injection (Leexi participant scope, Ringover user-id scope, BDD allowed-tables) — the request reaches the backend with only the static auth headers and the backend treats it as unrestricted. Grants are per-(server_id, user_email).

**Architecture:** New `server_authorizations` table joining `mcp_servers.id` ↔ user email. New repository + admin REST CRUD. `ScopedGateway` gains a `serverAuthorizer` interface; `requestHeadersFor` adds a Step-0 check before the existing auto-self override / admin-config fallback. New Vue admin page wired from the sidebar with admin-role gating.

**Resolution order at `requestHeadersFor`:**
```
Step 0 (NEW): server_authorizations grant for (backend.ID, email)? → skip filter injection (full access)
Step 1: auto-self override (Leexi/Ringover/BDD-aware backend)? → inject user UUID/ID
Step 2: admin-configured filter (existing) → inject admin list or deny-sentinel
```

Applies to all per-user filter backends — Leexi, Ringover, BDD (and future Zoho when added).

**Tech Stack:** Go 1.24, GORM v1.25 (MySQL), Vue 3.5 + TypeScript 5.7 + Pinia. No new dependencies.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps-microservices/mcp-gateway-service/internal/db/models.go` | `ServerAuthorization` GORM model. |
| `apps-microservices/mcp-gateway-service/internal/db/mysql.go` | Add `ServerAuthorization{}` to `AutoMigrate` list. |
| `apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo.go` | `ServerAuthorizationRepo` w/ `IsAuthorized`, `Create`, `Delete`, `List`, `ListByServer`. |
| `apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo_test.go` | Repo tests against in-memory sqlite. |
| `apps-microservices/mcp-gateway-service/internal/api/server_authorization_dto.go` | Request/response DTOs. |
| `apps-microservices/mcp-gateway-service/internal/api/server_authorization_handlers.go` | REST handlers (admin-only). |
| `apps-microservices/mcp-gateway-service/internal/api/handler.go` | Register new routes. |
| `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go` | `serverAuthorizer` interface + field + Step-0 check in `requestHeadersFor`. |
| `apps-microservices/mcp-gateway-service/internal/gateway/gateway.go` | Field + `SetServerAuthorizer` setter. |
| `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_server_auth_test.go` | Tests for Step-0 bypass across Leexi/Ringover/BDD. |
| `apps-microservices/mcp-gateway-service/internal/app/app.go` | Wire repo into Gateway + into the API handler. |
| `apps-microservices/mcp-gateway-service/CLAUDE.md` | Document the feature. |
| `apps-microservices/mcp-gateway-frontend/src/types/server-authorization.ts` | Type defs. |
| `apps-microservices/mcp-gateway-frontend/src/api/server-authorizations.ts` | API client. |
| `apps-microservices/mcp-gateway-frontend/src/views/ServerAuthorizationsView.vue` | Admin page. |
| `apps-microservices/mcp-gateway-frontend/src/router/index.ts` | New route w/ admin gate. |
| `apps-microservices/mcp-gateway-frontend/src/components/layout/AppSidebar.vue` (or equivalent) | New nav entry. |

---

## Task 1: DB Model + Migration

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/db/models.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/db/mysql.go`

- [ ] **Step 1: Add the GORM model**

In `apps-microservices/mcp-gateway-service/internal/db/models.go`, append (placement: near other join-style tables like `OAuth2ClientServer`):

```go
// ServerAuthorization grants a specific end-user (by email) full unfiltered
// access to a specific MCP server. When a row exists for (server_id, email),
// the gateway skips all filter-header injection (Leexi/Ringover/BDD) on
// outbound requests targeting that server — the backend receives only the
// static auth headers and treats the call as unrestricted.
//
// Primary key is (server_id, email). Insert/delete is the admin-side API.
type ServerAuthorization struct {
	ServerID  string    `gorm:"type:char(36);primaryKey" json:"server_id"`
	Email     string    `gorm:"type:varchar(255);primaryKey" json:"email"`
	CreatedBy string    `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	CreatedAt time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
}

func (ServerAuthorization) TableName() string { return "server_authorizations" }
```

- [ ] **Step 2: Register in AutoMigrate**

Read `apps-microservices/mcp-gateway-service/internal/db/mysql.go`. Locate the `AutoMigrate` call (it lists every model). Add `&ServerAuthorization{}` next to the other join-table models (e.g. after `OAuth2ClientBDDTable{}`).

Use Edit. Match the existing pattern.

- [ ] **Step 3: Build to verify migration list compiles**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/internal/db/models.go \
        apps-microservices/mcp-gateway-service/internal/db/mysql.go
git commit -m "feat(mcp-gateway): add server_authorizations table"
```

---

## Task 2: Repository + Tests

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo.go`
- Create: `apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo_test.go`

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo_test.go`. Use the same SQLite-in-memory setup pattern existing repository tests already use (read e.g. `oauth2_repo_test.go` for the helper):

```go
package repository

import (
	"testing"

	"mcp-gateway/internal/db"
)

func TestServerAuthorizationRepo_CreateAndIsAuthorized(t *testing.T) {
	gormDB := setupTestDB(t) // existing helper from the repo test suite
	repo := NewServerAuthorizationRepo(gormDB)

	if err := repo.Create(&db.ServerAuthorization{
		ServerID:  "srv-1",
		Email:     "alice@example.com",
		CreatedBy: "admin@example.com",
	}); err != nil {
		t.Fatalf("Create: %v", err)
	}

	if !repo.IsAuthorized("srv-1", "alice@example.com") {
		t.Fatal("expected alice authorized for srv-1")
	}
	if repo.IsAuthorized("srv-1", "bob@example.com") {
		t.Fatal("expected bob NOT authorized")
	}
	if repo.IsAuthorized("srv-2", "alice@example.com") {
		t.Fatal("expected alice not authorized on different server")
	}
}

func TestServerAuthorizationRepo_DeleteRevokesAccess(t *testing.T) {
	gormDB := setupTestDB(t)
	repo := NewServerAuthorizationRepo(gormDB)

	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"})
	if err := repo.Delete("srv-1", "alice@example.com"); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	if repo.IsAuthorized("srv-1", "alice@example.com") {
		t.Fatal("expected access revoked after Delete")
	}
}

func TestServerAuthorizationRepo_ListByServer(t *testing.T) {
	gormDB := setupTestDB(t)
	repo := NewServerAuthorizationRepo(gormDB)

	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"})
	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "bob@example.com"})
	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-2", Email: "alice@example.com"})

	rows, err := repo.ListByServer("srv-1")
	if err != nil {
		t.Fatalf("ListByServer: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("expected 2 rows for srv-1, got %d", len(rows))
	}
}

func TestServerAuthorizationRepo_DuplicateInsertIgnored(t *testing.T) {
	gormDB := setupTestDB(t)
	repo := NewServerAuthorizationRepo(gormDB)

	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"})
	if err := repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"}); err != nil {
		// Duplicate insert should be a no-op or return a sentinel; either way
		// the row count must stay at 1. The test asserts the latter.
	}
	rows, _ := repo.ListByServer("srv-1")
	if len(rows) != 1 {
		t.Fatalf("expected 1 row after duplicate insert, got %d", len(rows))
	}
}
```

If `setupTestDB` does not exist, look at how existing repo tests build a `*gorm.DB` and copy that pattern. They likely use `gorm.io/driver/sqlite` w/ `:memory:`.

- [ ] **Step 2: Run to verify failure**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/repository/... -run ServerAuthorization -v 2>&1 | tail -25"
```
Expected: FAIL — `NewServerAuthorizationRepo` undefined.

- [ ] **Step 3: Implement the repository**

Create `apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo.go`:

```go
package repository

import (
	"errors"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"mcp-gateway/internal/db"
)

// ServerAuthorizationRepo is the CRUD layer for the server_authorizations
// table. Enforces (server_id, email) uniqueness on insert; idempotent inserts
// silently coalesce so the admin UI can re-grant without checking first.
type ServerAuthorizationRepo struct {
	db *gorm.DB
}

func NewServerAuthorizationRepo(d *gorm.DB) *ServerAuthorizationRepo {
	return &ServerAuthorizationRepo{db: d}
}

// IsAuthorized reports whether the given email is granted full access on the
// given server. Repo errors short-circuit to false (fail-closed).
func (r *ServerAuthorizationRepo) IsAuthorized(serverID, email string) bool {
	if serverID == "" || email == "" {
		return false
	}
	var row db.ServerAuthorization
	err := r.db.Where("server_id = ? AND email = ?", serverID, email).First(&row).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return false
		}
		return false
	}
	return true
}

// Create inserts a grant. Duplicate (server_id, email) pairs are silently
// ignored via ON CONFLICT DO NOTHING (MySQL: ON DUPLICATE KEY UPDATE
// no-op).
func (r *ServerAuthorizationRepo) Create(row *db.ServerAuthorization) error {
	return r.db.Clauses(clause.OnConflict{DoNothing: true}).Create(row).Error
}

// Delete removes a grant. Missing rows are not an error.
func (r *ServerAuthorizationRepo) Delete(serverID, email string) error {
	return r.db.Where("server_id = ? AND email = ?", serverID, email).
		Delete(&db.ServerAuthorization{}).Error
}

// ListByServer returns every grant for the given server, ordered by
// created_at DESC (newest first).
func (r *ServerAuthorizationRepo) ListByServer(serverID string) ([]db.ServerAuthorization, error) {
	var rows []db.ServerAuthorization
	err := r.db.Where("server_id = ?", serverID).
		Order("created_at DESC").
		Find(&rows).Error
	return rows, err
}

// List returns every grant across every server, ordered by created_at DESC.
// Used by the admin UI overview page.
func (r *ServerAuthorizationRepo) List() ([]db.ServerAuthorization, error) {
	var rows []db.ServerAuthorization
	err := r.db.Order("created_at DESC").Find(&rows).Error
	return rows, err
}
```

- [ ] **Step 4: Run tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/repository/... -run ServerAuthorization -v 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
```
Expected: all 4 new tests PASS, full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo.go \
        apps-microservices/mcp-gateway-service/internal/repository/server_authorization_repo_test.go
git commit -m "feat(mcp-gateway): add ServerAuthorizationRepo CRUD"
```

---

## Task 3: API DTOs + Handlers

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/api/server_authorization_dto.go`
- Create: `apps-microservices/mcp-gateway-service/internal/api/server_authorization_handlers.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/handler.go`

- [ ] **Step 1: Define DTOs**

Create `apps-microservices/mcp-gateway-service/internal/api/server_authorization_dto.go`:

```go
package api

// CreateServerAuthorizationRequest is the body for POST /api/v1/server-authorizations.
type CreateServerAuthorizationRequest struct {
	ServerID string `json:"server_id"`
	Email    string `json:"email"`
}

// ServerAuthorizationResponse is the wire shape returned by GET / POST.
type ServerAuthorizationResponse struct {
	ServerID  string `json:"server_id"`
	Email     string `json:"email"`
	CreatedBy string `json:"created_by,omitempty"`
	CreatedAt string `json:"created_at"`
}
```

- [ ] **Step 2: Implement handlers**

Create `apps-microservices/mcp-gateway-service/internal/api/server_authorization_handlers.go`:

```go
package api

import (
	"encoding/json"
	"net/http"
	"strings"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

// ServerAuthorizationHandler owns the /api/v1/server-authorizations routes.
// Admin-only — wired with auth.RequireAdmin in the route registration.
type ServerAuthorizationHandler struct {
	repo       *repository.ServerAuthorizationRepo
	serverRepo *repository.ServerRepo // for existence validation on Create
}

func NewServerAuthorizationHandler(repo *repository.ServerAuthorizationRepo, serverRepo *repository.ServerRepo) *ServerAuthorizationHandler {
	return &ServerAuthorizationHandler{repo: repo, serverRepo: serverRepo}
}

// Register mounts the routes on mux. Caller wraps with auth.RequireAdmin.
func (h *ServerAuthorizationHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc("/api/v1/server-authorizations", h.handleCollection)
	mux.HandleFunc("/api/v1/server-authorizations/", h.handleItem)
}

func (h *ServerAuthorizationHandler) handleCollection(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.list(w, r)
	case http.MethodPost:
		h.create(w, r)
	default:
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleItem handles DELETE /api/v1/server-authorizations/{server_id}/{email}.
// Path is /server-authorizations/{server_id}/{email-url-encoded}.
func (h *ServerAuthorizationHandler) handleItem(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		w.Header().Set("Allow", "DELETE")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	rest := strings.TrimPrefix(r.URL.Path, "/api/v1/server-authorizations/")
	parts := strings.SplitN(rest, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		http.Error(w, "expected /server-authorizations/{server_id}/{email}", http.StatusBadRequest)
		return
	}
	if err := h.repo.Delete(parts[0], parts[1]); err != nil {
		http.Error(w, "delete failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *ServerAuthorizationHandler) list(w http.ResponseWriter, r *http.Request) {
	serverID := r.URL.Query().Get("server_id")
	var rows []db.ServerAuthorization
	var err error
	if serverID != "" {
		rows, err = h.repo.ListByServer(serverID)
	} else {
		rows, err = h.repo.List()
	}
	if err != nil {
		http.Error(w, "list failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	resp := make([]ServerAuthorizationResponse, 0, len(rows))
	for _, r := range rows {
		resp = append(resp, ServerAuthorizationResponse{
			ServerID:  r.ServerID,
			Email:     r.Email,
			CreatedBy: r.CreatedBy,
			CreatedAt: r.CreatedAt.Format("2006-01-02T15:04:05Z07:00"),
		})
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ServerAuthorizationHandler) create(w http.ResponseWriter, r *http.Request) {
	var req CreateServerAuthorizationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON: "+err.Error(), http.StatusBadRequest)
		return
	}
	req.ServerID = strings.TrimSpace(req.ServerID)
	req.Email = strings.TrimSpace(req.Email)
	if req.ServerID == "" || req.Email == "" {
		http.Error(w, "server_id and email are required", http.StatusBadRequest)
		return
	}

	// Validate server exists.
	if _, err := h.serverRepo.GetByID(req.ServerID); err != nil {
		http.Error(w, "unknown server_id", http.StatusBadRequest)
		return
	}

	createdBy := ""
	if email, ok := auth.EmailFromContext(r.Context()); ok {
		createdBy = email
	}

	row := &db.ServerAuthorization{
		ServerID:  req.ServerID,
		Email:     req.Email,
		CreatedBy: createdBy,
	}
	if err := h.repo.Create(row); err != nil {
		http.Error(w, "create failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusCreated, ServerAuthorizationResponse{
		ServerID:  row.ServerID,
		Email:     row.Email,
		CreatedBy: row.CreatedBy,
		CreatedAt: row.CreatedAt.Format("2006-01-02T15:04:05Z07:00"),
	})
}
```

If the helpers `writeJSON` and `auth.EmailFromContext` don't exist with these exact names, find the existing equivalents in the codebase (`grep -rn "func writeJSON\|EmailFromContext"`) and adapt the calls.

- [ ] **Step 3: Register routes**

Read `apps-microservices/mcp-gateway-service/internal/api/handler.go`. Locate where existing admin handlers are wired (look for other `Register(mux)` or `auth.RequireAdmin` patterns).

Add a new constructor field on the API handler struct + a Register call wrapped in `auth.RequireAdmin`. Mirror the pattern existing admin routes use. Read 30 lines around the wiring to see the actual conventions (some routes are mounted directly on the mux; others via middleware-wrapped sub-handlers).

- [ ] **Step 4: Build**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/server_authorization_dto.go \
        apps-microservices/mcp-gateway-service/internal/api/server_authorization_handlers.go \
        apps-microservices/mcp-gateway-service/internal/api/handler.go
git commit -m "feat(mcp-gateway): add server-authorizations admin REST API"
```

---

## Task 4: `serverAuthorizer` Interface + Step-0 Bypass in `requestHeadersFor`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/gateway.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`

The pre-injection check applies to ALL backends (Leexi/Ringover/BDD/future Zoho). One central check in `requestHeadersFor` — no per-backend duplication.

- [ ] **Step 1: Define the interface**

In `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`, near the existing `gatewayUserFinder` interface, add:

```go
// serverAuthorizer abstracts repository.ServerAuthorizationRepo. Defining as
// an interface keeps tests in the gateway package free of GORM. nil disables
// Step-0 bypass — the gateway falls through to auto-self override + admin
// config like before.
type serverAuthorizer interface {
	IsAuthorized(serverID, email string) bool
}
```

- [ ] **Step 2: Add fields and setter**

In `gateway.go`, add a `serverAuthorizer` field next to `gatewayUsers`:

```go
serverAuth serverAuthorizer
```

Add the setter mirroring `SetGatewayUserFinder`:

```go
// SetServerAuthorizer registers the per-server full-access grant repository
// consulted by the Step-0 bypass in requestHeadersFor. Pass
// *repository.ServerAuthorizationRepo at boot.
func (g *Gateway) SetServerAuthorizer(s serverAuthorizer) {
	g.serverAuth = s
}
```

In `scoped_gateway.go`, add the matching field on `ScopedGateway` and propagate in `NewScopedGateway`:

```go
serverAuth serverAuthorizer  // copy from gw.serverAuth
```

```go
serverAuth: gw.serverAuth,
```

- [ ] **Step 3: Add Step-0 to `requestHeadersFor`**

Locate `requestHeadersFor` in `scoped_gateway.go` (around line 171). Replace its body:

```go
func (sg *ScopedGateway) requestHeadersFor(ctx context.Context, backend *BackendServer) map[string]string {
	headers := make(map[string]string, len(backend.AuthHeaders)+1)
	for k, v := range backend.AuthHeaders {
		headers[k] = v
	}

	// Step 0 — server-level full-access grant. When the end-user is granted
	// unfiltered access on this specific server, skip every filter header
	// and let the backend treat the call as unrestricted. Per-server (matched
	// by backend.ID) and per-email (from EndUserEmailContextKey).
	if sg.isServerAuthorized(ctx, backend.ID) {
		log.Printf("[scoped] server-authorization bypass for backend %s", backend.ID)
		return headers
	}

	switch backend.ToolPrefix {
	case leexiToolPrefix:
		sg.injectLeexiHeader(ctx, headers)
	case ringoverToolPrefix:
		sg.injectRingoverHeader(ctx, headers)
	case bddToolPrefix:
		sg.injectBDDHeader(ctx, headers)
	}
	return headers
}

// isServerAuthorized returns true when the request's end-user has an explicit
// full-access grant for this server. Returns false when:
//   - serverAuthorizer is not configured (boot-time choice)
//   - no email in context (client_credentials grant — there's no user to
//     match a grant against)
//   - email is in context but no row in server_authorizations
func (sg *ScopedGateway) isServerAuthorized(ctx context.Context, serverID string) bool {
	if sg.serverAuth == nil {
		return false
	}
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return false
	}
	return sg.serverAuth.IsAuthorized(serverID, email)
}
```

(The exact field name used by `BackendServer` for the server UUID may be `ID`, `ServerID`, etc. Read `internal/gateway/registry.go` to confirm. Adapt the call.)

- [ ] **Step 4: Build**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./... 2>&1"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/gateway.go \
        apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go
git commit -m "feat(mcp-gateway): server-authorization bypass at requestHeadersFor"
```

---

## Task 5: Tests for Step-0 Bypass

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_server_auth_test.go`

- [ ] **Step 1: Write the tests**

```go
package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/scopetoken"
)

// fakeServerAuth implements serverAuthorizer in-memory.
type fakeServerAuth struct {
	grants map[string]map[string]bool // server_id -> email -> true
}

func (f *fakeServerAuth) IsAuthorized(serverID, email string) bool {
	if f.grants == nil {
		return false
	}
	emails, ok := f.grants[serverID]
	if !ok {
		return false
	}
	return emails[email]
}

// 1. With a grant for (server_id, email) → headers contain ONLY the static
// auth headers, no Leexi participants header.
func TestRequestHeadersFor_ServerAuthBypassesLeexiInjection(t *testing.T) {
	leexiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Should never be called when bypass active. Fail the test if it is.
		t.Fatalf("unexpected leexi /admin/users hit (bypass should skip)")
	}))
	defer leexiSrv.Close()

	sg := &ScopedGateway{
		leexiAdmin: leexiadmin.NewClient(leexiSrv.URL, "tok"),
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-leexi": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-leexi",
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{"X-Static-Auth": "secret"},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")

	headers := sg.requestHeadersFor(ctx, backend)
	if _, present := headers[LeexiAllowedParticipantsHeader]; present {
		t.Fatalf("expected no Leexi header on bypass, got %v", headers)
	}
	if got := headers["X-Static-Auth"]; got != "secret" {
		t.Fatalf("static auth header missing or wrong: %q", got)
	}
}

// 2. No grant + admin-configured filter present → existing inject runs.
func TestRequestHeadersFor_NoGrantUsesExistingInjection(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{}, // empty grants
	}
	backend := &BackendServer{
		ID:          "srv-leexi",
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})

	// Without a Leexi admin client, tryAutoSelf returns ("", false) → falls
	// through to admin config. Filter resolves to u-bob (admin's list).
	headers := sg.requestHeadersFor(ctx, backend)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob" {
		t.Fatalf("expected u-bob, got %q", got)
	}
}

// 3. No email in ctx (client_credentials) → grant lookup returns false → falls
// through to existing path.
func TestRequestHeadersFor_NoEmailFallsThrough(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-leexi": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-leexi",
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})
	headers := sg.requestHeadersFor(ctx, backend)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob" {
		t.Fatalf("expected u-bob (no-email fall-through), got %q", got)
	}
}

// 4. Grant for ringover backend bypasses Ringover header injection too.
func TestRequestHeadersFor_ServerAuthBypassesRingover(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-ringover": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-ringover",
		ToolPrefix:  ringoverToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	headers := sg.requestHeadersFor(ctx, backend)
	if _, present := headers[RingoverAllowedUserIDsHeader]; present {
		t.Fatalf("expected no Ringover header on bypass, got %v", headers)
	}
}

// 5. Grant for BDD backend bypasses BDD header injection.
func TestRequestHeadersFor_ServerAuthBypassesBDD(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-bdd": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-bdd",
		ToolPrefix:  bddToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.BDDFilterContextKey, []string{"id-1"})
	headers := sg.requestHeadersFor(ctx, backend)
	if _, present := headers[BDDAllowedTablesHeader]; present {
		t.Fatalf("expected no BDD header on bypass, got %v", headers)
	}
}

// 6. Per-server granularity: grant for srv-1 does NOT bypass srv-2.
func TestRequestHeadersFor_GrantIsPerServer(t *testing.T) {
	leexiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"uuid":"u-alice","email":"alice@example.com"}]}`))
	}))
	defer leexiSrv.Close()

	sg := &ScopedGateway{
		leexiAdmin: leexiadmin.NewClient(leexiSrv.URL, "tok"),
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-1": {"alice@example.com": true},
		}},
	}
	backendOther := &BackendServer{
		ID:          "srv-2", // not granted
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{Mode: "none"})

	headers := sg.requestHeadersFor(ctx, backendOther)
	// Auto-self override on srv-2 should still inject u-alice (no bypass).
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-alice" {
		t.Fatalf("srv-2 should auto-self-filter alice (not bypass), got %q", got)
	}
	// Replace strings.HasSuffix usage to ensure import is used.
	_ = strings.HasSuffix
}
```

Drop the `strings.HasSuffix` placeholder line if not needed — depends on whether your imports already include `strings` for other reasons.

- [ ] **Step 2: Run tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/gateway/... -v 2>&1 | tail -60"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```
Expected: 6 new tests PASS, all existing tests still PASS.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_server_auth_test.go
git commit -m "test(mcp-gateway): cover server-authorization bypass across backends"
```

---

## Task 6: Wire Repo at Boot

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/app/app.go`

- [ ] **Step 1: Build the repo + wire into Gateway and API handler**

Locate the section where other repos are built (e.g. near `tokenRepo := repository.NewTokenRepo(...)`). Add:

```go
serverAuthRepo := repository.NewServerAuthorizationRepo(dbStack.database)
gw.SetServerAuthorizer(serverAuthRepo)
log.Println("[main] server_authorizations wired into Gateway for full-access bypass")
```

(Wrapped in the existing `if dbStack.repo != nil && dbStack.database != nil` block.)

In `registerRESTAndOAuthServer` (or wherever the API handler is built — `grep -n "api.NewHandler" apps-microservices/mcp-gateway-service/internal/app/app.go`), pass the new `serverAuthRepo` to `api.NewServerAuthorizationHandler` and register its routes.

The exact wiring depends on how the API handler is currently constructed — read 50 lines around the construction site before editing.

- [ ] **Step 2: Build + test**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway): wire ServerAuthorizationRepo + admin handler at boot"
```

---

## Task 7: Vue Admin Page

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/types/server-authorization.ts`
- Create: `apps-microservices/mcp-gateway-frontend/src/api/server-authorizations.ts`
- Create: `apps-microservices/mcp-gateway-frontend/src/views/ServerAuthorizationsView.vue`
- Modify: `apps-microservices/mcp-gateway-frontend/src/router/index.ts`
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/layout/AppSidebar.vue` (or wherever the sidebar nav lives — `grep -rn "router-link\|nav.*item\|sidebar" apps-microservices/mcp-gateway-frontend/src/components/layout/`)

- [ ] **Step 1: Type defs**

Create `apps-microservices/mcp-gateway-frontend/src/types/server-authorization.ts`:

```ts
export interface ServerAuthorization {
  server_id: string
  email: string
  created_by?: string
  created_at: string
}

export interface CreateServerAuthorizationRequest {
  server_id: string
  email: string
}
```

- [ ] **Step 2: API client**

Create `apps-microservices/mcp-gateway-frontend/src/api/server-authorizations.ts`. Match the pattern of an existing API module like `src/api/oauth2.ts`:

```ts
import { client } from './client'
import type { ServerAuthorization, CreateServerAuthorizationRequest } from '@/types/server-authorization'

export const serverAuthorizationsApi = {
  list(serverID?: string): Promise<ServerAuthorization[]> {
    const q = serverID ? `?server_id=${encodeURIComponent(serverID)}` : ''
    return client.get(`/api/v1/server-authorizations${q}`)
  },
  create(req: CreateServerAuthorizationRequest): Promise<ServerAuthorization> {
    return client.post('/api/v1/server-authorizations', req)
  },
  delete(serverID: string, email: string): Promise<void> {
    return client.delete(`/api/v1/server-authorizations/${encodeURIComponent(serverID)}/${encodeURIComponent(email)}`)
  },
}
```

(Exact `client` API depends on the project's fetch wrapper — read `src/api/client.ts` to confirm method signatures.)

- [ ] **Step 3: View component**

Create `apps-microservices/mcp-gateway-frontend/src/views/ServerAuthorizationsView.vue`. Match the styling and structure of an existing admin page (e.g. `BDDTablesView.vue` or `OAuth2View.vue`). Render:
- A server picker (load `/api/v1/servers` to populate options).
- A table of grants for the selected server: email | created_by | created_at | delete-button.
- An "Add grant" form: email input + submit.
- Filter / "all servers" view as a fallback.

Keep it minimal — copy the table + form patterns from `OAuth2View.vue` if it has them.

- [ ] **Step 4: Route**

In `apps-microservices/mcp-gateway-frontend/src/router/index.ts`, add:

```ts
{
  path: '/server-authorizations',
  name: 'server-authorizations',
  component: () => import('@/views/ServerAuthorizationsView.vue'),
  meta: { minRole: 'admin' },
}
```

(`minRole` matches the existing route-guard convention — confirm by reading other admin routes in the same file.)

- [ ] **Step 5: Sidebar nav entry**

Locate the sidebar component. Add a new nav item linking to `/server-authorizations` titled "Serveur Autorisation". Gate visibility on `auth.isAdmin` (or whatever the SPA's role check is — look at how other admin-only items hide for non-admins).

- [ ] **Step 6: Smoke check**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend
npx vue-tsc --noEmit 2>&1 | tail -15
npm run lint 2>&1 | tail -10
```
Expected: zero new type errors, zero new lint errors on the new files.

- [ ] **Step 7: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB
git add apps-microservices/mcp-gateway-frontend/src/types/server-authorization.ts \
        apps-microservices/mcp-gateway-frontend/src/api/server-authorizations.ts \
        apps-microservices/mcp-gateway-frontend/src/views/ServerAuthorizationsView.vue \
        apps-microservices/mcp-gateway-frontend/src/router/index.ts \
        apps-microservices/mcp-gateway-frontend/src/components/layout/
git commit -m "feat(mcp-gateway-frontend): add Serveur Autorisation admin page"
```

---

## Task 8: Document the Feature

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Add a new bullet immediately above the auto-self override bullet**

```markdown
- **Server-level full-access grants (admin)**: the `server_authorizations` table joins (`mcp_servers.id`, `email`). When a request's bearer-token email has a row for the targeted backend, the gateway skips ALL filter-header injection (Leexi, Ringover, BDD, future Zoho) — the backend receives only the static auth headers and treats the call as unrestricted. Grants are managed via the admin-only `/api/v1/server-authorizations` REST endpoints and the "Serveur Autorisation" Vue admin page. Per-server granularity (a grant on `srv-1` does not affect `srv-2`). Client-credentials grants (no email) never match a row → grant table is irrelevant to non-human flows.
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "docs(mcp-gateway): document server_authorizations full-access grants"
```

---

## Task 9: Final Verification

- [ ] **Step 1: Full Go suite**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```

- [ ] **Step 2: Frontend type-check + lint**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend
npx vue-tsc --noEmit 2>&1 | tail -10
npm run lint 2>&1 | tail -10
```

- [ ] **Step 3: Manual smoke (optional, requires staging)**

1. Log in to the Vue admin UI as an admin user. "Serveur Autorisation" appears in the sidebar.
2. Pick a server (e.g. an mcp-leexi-service backend). Add `alice@example.com` as a grant.
3. Have alice OAuth2 into a connector that targets that server.
4. Watch the gateway logs: `[scoped] server-authorization bypass for backend <id>`.
5. Confirm the outbound MCP request to the backend has NO `X-Leexi-Allowed-Participants` header.
6. Add a grant on a different server (`srv-2`); confirm the request to the original `srv-1` still bypasses; the request to `srv-2` ALSO bypasses; a request to a third ungranted server runs auto-self override.
7. Delete the grant from the UI; alice's next request hits auto-self override again.

---

## Out of Scope (Explicit YAGNI)

- Bulk grant UI (CSV import). One-at-a-time form is enough for the initial cut.
- Audit log of grant create/delete actions (already covered by the gateway's audit middleware on every admin REST call).
- Caching `IsAuthorized` in-memory. The query is a single-row indexed lookup against a small table; premature optimization.
- Wildcard grants (`email = "*"` for full-access-for-everyone-on-this-server). Adds a third resolution mode that could surprise future readers; if needed later, model as a separate feature flag on the `mcp_servers` row, not as a magic email value.
- Per-tool grants. Grants are server-level; locking a single tool to one user is admin-config territory.
- Frontend confirm dialog on delete. Match the existing UI conventions; if other admin pages already confirm, do likewise; otherwise plain delete is fine.
