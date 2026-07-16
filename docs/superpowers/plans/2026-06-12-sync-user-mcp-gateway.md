# Sync Account-Service Users to MCP Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin buttons (per-row + global) in the account-service admin/users UI that push users into the MCP gateway's `gateway_users` table with `role=config-only`, `is_allowed=false`, skipping users that already exist.

**Architecture:** Gateway exposes `POST /api/v1/internal/users/sync` gated by `X-Admin-Token` (same shared secret pair as `/internal/credentials`: account `INTERNAL_ADMIN_TOKEN` = gateway `ACCOUNT_INTERNAL_TOKEN`, both fed by `${ACCOUNT_INTERNAL_TOKEN}` in compose). Account backend proxies two new admin routes to it. Frontend adds buttons in `AdminUsersView.vue`. Spec: `docs/superpowers/specs/2026-06-12-sync-user-mcp-gateway-design.md`.

**Tech Stack:** Go 1.24 + GORM (both services, `net/http` stdlib mux), Vue 3 + TypeScript + Vitest (frontend). Gateway tests use `github.com/glebarez/sqlite` in-memory GORM with hand-rolled DDL (the `datetime(3)` MySQL types don't AutoMigrate on SQLite).

**Branch:** `features/sync-user-mcp-portal`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/mcp-gateway-service/internal/repository/user_repo.go` | Modify | Add `SyncUserInput` + `SyncUsers` (create-if-missing) |
| `apps-microservices/mcp-gateway-service/internal/repository/user_repo_test.go` | Create | SQLite tests for `SyncUsers` |
| `apps-microservices/mcp-gateway-service/internal/api/internal_handlers.go` | Modify | Add `handleUserSync` + DTOs |
| `apps-microservices/mcp-gateway-service/internal/api/internal_handlers_test.go` | Modify | Handler tests (auth, validation, create/skip) |
| `apps-microservices/mcp-gateway-service/internal/api/handler.go` | Modify | Mount `/api/v1/internal/users/sync` (after runner sync block, ~line 421) |
| `apps-microservices/mcp-gateway-service/internal/auth/middleware.go` | Modify | Add path to `publicExact` (line ~67) |
| `apps-microservices/account-service-backend/internal/config/config.go` | Modify | Add `MCPGatewayInternalURL` |
| `apps-microservices/account-service-backend/internal/config/config_test.go` | Create/Modify | Env-read test |
| `apps-microservices/account-service-backend/internal/gatewaysync/client.go` | Create | HTTP client for the gateway sync endpoint |
| `apps-microservices/account-service-backend/internal/gatewaysync/client_test.go` | Create | httptest-server client tests |
| `apps-microservices/account-service-backend/internal/repository/user_repo.go` | Modify | Add `ListAllowed` |
| `apps-microservices/account-service-backend/internal/api/admin_user_handlers.go` | Modify | `sync-mcp` op + bulk handler + `McpSyncer` interface |
| `apps-microservices/account-service-backend/internal/api/admin_user_handlers_test.go` | Modify | Tests for both routes |
| `apps-microservices/account-service-backend/internal/app/routes.go` | Modify | Register bulk route, pass `McpSync` dep |
| `apps-microservices/account-service-backend/internal/app/app.go` | Modify | Construct `gatewaysync.Client` when configured |
| `apps-microservices/account-service-frontend/src/api/users.ts` | Modify | `syncMcp`, `syncMcpAll`, `McpSyncResult` |
| `apps-microservices/account-service-frontend/src/api/users.spec.ts` | Create | Export checks (mirrors `services.spec.ts`) |
| `apps-microservices/account-service-frontend/src/views/AdminUsersView.vue` | Modify | Per-row + global buttons, info banner |
| `docker-compose.yml` | Modify | `MCP_GATEWAY_INTERNAL_URL` env on account-service-backend (~line 2559) |
| `apps-microservices/mcp-gateway-service/CLAUDE.md` | Modify | Document new internal endpoint |
| `apps-microservices/account-service-backend/CLAUDE.md` | Modify | Document new routes + env var |

---

### Task 1: Gateway — `UserRepo.SyncUsers`

**Files:**
- Test: `apps-microservices/mcp-gateway-service/internal/repository/user_repo_test.go` (create)
- Modify: `apps-microservices/mcp-gateway-service/internal/repository/user_repo.go`

- [ ] **Step 1: Write the failing test**

Create `internal/repository/user_repo_test.go`:

```go
package repository

import (
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/db"
)

// newUserTestDB hand-rolls the gateway_users DDL — AutoMigrate on the real
// GORM models isn't portable to SQLite (datetime(3)), mirroring the pattern
// in newInstructionTestDB.
func newUserTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE gateway_users (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			email         TEXT NOT NULL UNIQUE,
			display_name  TEXT NOT NULL DEFAULT '',
			role          TEXT NOT NULL DEFAULT 'config-only',
			is_allowed    INTEGER NOT NULL DEFAULT 0,
			login_count   INTEGER NOT NULL DEFAULT 0,
			last_login_at datetime,
			created_at    datetime,
			updated_at    datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return gdb
}

func TestSyncUsers_CreatesMissingWithConfigOnlyDefaults(t *testing.T) {
	repo := NewUserRepo(newUserTestDB(t), nil, nil)

	created, skipped, err := repo.SyncUsers([]SyncUserInput{
		{Email: "new@hellopro.fr", DisplayName: "New User"},
	})
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	if len(created) != 1 || created[0] != "new@hellopro.fr" {
		t.Fatalf("created = %v, want [new@hellopro.fr]", created)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped = %v, want empty", skipped)
	}

	u, err := repo.GetByEmail("new@hellopro.fr")
	if err != nil || u == nil {
		t.Fatalf("GetByEmail: u=%v err=%v", u, err)
	}
	if u.Role != "config-only" {
		t.Errorf("Role = %q, want config-only", u.Role)
	}
	if u.IsAllowed {
		t.Error("IsAllowed = true, want false")
	}
	if u.LoginCount != 0 {
		t.Errorf("LoginCount = %d, want 0", u.LoginCount)
	}
	if u.DisplayName != "New User" {
		t.Errorf("DisplayName = %q, want New User", u.DisplayName)
	}
}

func TestSyncUsers_SkipsExistingWithoutModifying(t *testing.T) {
	gdb := newUserTestDB(t)
	repo := NewUserRepo(gdb, nil, nil)

	// Pre-existing admin user — sync must NOT downgrade or touch it.
	pre := db.GatewayUser{Email: "admin@hellopro.fr", DisplayName: "Admin", Role: "admin", IsAllowed: true, LoginCount: 7}
	if err := gdb.Create(&pre).Error; err != nil {
		t.Fatalf("seed: %v", err)
	}

	created, skipped, err := repo.SyncUsers([]SyncUserInput{
		{Email: "admin@hellopro.fr", DisplayName: "Renamed"},
		{Email: "new@hellopro.fr", DisplayName: "New"},
	})
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	if len(created) != 1 || created[0] != "new@hellopro.fr" {
		t.Fatalf("created = %v, want [new@hellopro.fr]", created)
	}
	if len(skipped) != 1 || skipped[0] != "admin@hellopro.fr" {
		t.Fatalf("skipped = %v, want [admin@hellopro.fr]", skipped)
	}

	u, _ := repo.GetByEmail("admin@hellopro.fr")
	if u.Role != "admin" || !u.IsAllowed || u.DisplayName != "Admin" || u.LoginCount != 7 {
		t.Errorf("existing user modified: %+v", u)
	}
}

func TestSyncUsers_EmptyInputReturnsEmptySlices(t *testing.T) {
	repo := NewUserRepo(newUserTestDB(t), nil, nil)
	created, skipped, err := repo.SyncUsers(nil)
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	// Must be non-nil empty slices so the handler JSON-encodes [] not null.
	if created == nil || skipped == nil {
		t.Fatalf("created=%v skipped=%v, want non-nil empty slices", created, skipped)
	}
	if len(created) != 0 || len(skipped) != 0 {
		t.Fatalf("created=%v skipped=%v, want empty", created, skipped)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/repository/ -run TestSyncUsers -v`
Expected: FAIL to compile — `undefined: SyncUserInput`, `repo.SyncUsers undefined`

- [ ] **Step 3: Write minimal implementation**

Append to `internal/repository/user_repo.go`:

```go
// SyncUserInput is one user pushed from account-service via the internal
// sync endpoint.
type SyncUserInput struct {
	Email       string
	DisplayName string
}

// SyncUsers creates a gateway user for every input email that does not exist
// yet (role config-only, is_allowed=false) and skips existing ones untouched.
// Returns the emails created and skipped. Both slices are always non-nil so
// callers can JSON-encode them as [] rather than null.
func (r *UserRepo) SyncUsers(users []SyncUserInput) (created, skipped []string, err error) {
	created = []string{}
	skipped = []string{}
	for _, u := range users {
		existing, getErr := r.GetByEmail(u.Email)
		if getErr != nil {
			return nil, nil, getErr
		}
		if existing != nil {
			skipped = append(skipped, u.Email)
			continue
		}
		newUser := db.GatewayUser{
			Email:       u.Email,
			DisplayName: u.DisplayName,
			Role:        "config-only",
			IsAllowed:   false,
		}
		if createErr := r.db.Create(&newUser).Error; createErr != nil {
			// Unique-constraint race: the user logged in (UpsertOnLogin)
			// between our lookup and insert. Re-check and treat as skipped.
			if again, _ := r.GetByEmail(u.Email); again != nil {
				skipped = append(skipped, u.Email)
				continue
			}
			return nil, nil, createErr
		}
		created = append(created, u.Email)
	}
	return created, skipped, nil
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/repository/ -run TestSyncUsers -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/repository/user_repo.go apps-microservices/mcp-gateway-service/internal/repository/user_repo_test.go
git commit -m "feat(mcp-gateway): add UserRepo.SyncUsers create-if-missing

EN: Batch-create gateway users (role config-only, is_allowed=false),
skipping existing rows untouched; duplicate-key race treated as skip.

FR: Creation en lot des utilisateurs gateway (role config-only,
is_allowed=false), lignes existantes ignorees; course duplicate-key
traitee comme skip."
```

---

### Task 2: Gateway — `handleUserSync` handler

**Files:**
- Test: `apps-microservices/mcp-gateway-service/internal/api/internal_handlers_test.go` (modify)
- Modify: `apps-microservices/mcp-gateway-service/internal/api/internal_handlers.go`

- [ ] **Step 1: Write the failing tests**

Append to `internal/api/internal_handlers_test.go` (extend the existing imports — final import block shown):

```go
import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/config"
	"mcp-gateway/internal/repository"
)
```

```go
// newSyncTestHandler builds a Handler with a SQLite-backed UserRepo and the
// given AccountInternalToken. Same hand-rolled DDL as the repository tests.
func newSyncTestHandler(t *testing.T, token string) *Handler {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE gateway_users (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			email         TEXT NOT NULL UNIQUE,
			display_name  TEXT NOT NULL DEFAULT '',
			role          TEXT NOT NULL DEFAULT 'config-only',
			is_allowed    INTEGER NOT NULL DEFAULT 0,
			login_count   INTEGER NOT NULL DEFAULT 0,
			last_login_at datetime,
			created_at    datetime,
			updated_at    datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return &Handler{
		userRepo: repository.NewUserRepo(gdb, nil, nil),
		config:   &config.Config{AccountInternalToken: token},
	}
}

func postSync(h *Handler, token, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/internal/users/sync", strings.NewReader(body))
	if token != "" {
		req.Header.Set("X-Admin-Token", token)
	}
	rec := httptest.NewRecorder()
	h.handleUserSync(rec, req)
	return rec
}

func TestHandleUserSync_NilDeps_Returns503(t *testing.T) {
	h := &Handler{}
	rec := postSync(h, "tok", `{"users":[]}`)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("got %d, want 503", rec.Code)
	}
}

func TestHandleUserSync_GetReturns405(t *testing.T) {
	h := newSyncTestHandler(t, "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/internal/users/sync", nil)
	req.Header.Set("X-Admin-Token", "tok")
	rec := httptest.NewRecorder()
	h.handleUserSync(rec, req)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Errorf("got %d, want 405", rec.Code)
	}
	if got := rec.Header().Get("Allow"); got != "POST" {
		t.Errorf("Allow header = %q, want POST", got)
	}
}

func TestHandleUserSync_AuthFailures_Return401(t *testing.T) {
	cases := []struct {
		name, configured, presented string
	}{
		{"missing header", "tok", ""},
		{"wrong token", "tok", "wrong"},
		{"empty configured token", "", "anything"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			h := newSyncTestHandler(t, c.configured)
			rec := postSync(h, c.presented, `{"users":[]}`)
			if rec.Code != http.StatusUnauthorized {
				t.Errorf("got %d, want 401", rec.Code)
			}
		})
	}
}

func TestHandleUserSync_BadBody_Returns400(t *testing.T) {
	h := newSyncTestHandler(t, "tok")
	for _, body := range []string{`not json`, `{"users":[{"email":"  "}]}`} {
		rec := postSync(h, "tok", body)
		if rec.Code != http.StatusBadRequest {
			t.Errorf("body %q: got %d, want 400", body, rec.Code)
		}
	}
}

func TestHandleUserSync_CreatesAndSkips(t *testing.T) {
	h := newSyncTestHandler(t, "tok")

	// First call creates both users.
	rec := postSync(h, "tok", `{"users":[{"email":"A@Hellopro.fr","display_name":"A"},{"email":"b@hellopro.fr","display_name":"B"}]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Created []string `json:"created"`
		Skipped []string `json:"skipped"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// Email normalized: trimmed + lowercased.
	if len(out.Created) != 2 || out.Created[0] != "a@hellopro.fr" {
		t.Fatalf("created = %v, want [a@hellopro.fr b@hellopro.fr]", out.Created)
	}

	// Second call: both already exist -> skipped, created must encode as [].
	rec = postSync(h, "tok", `{"users":[{"email":"a@hellopro.fr","display_name":"A"}]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"created":[]`) {
		t.Errorf("created not encoded as []: %s", rec.Body.String())
	}
	out = struct {
		Created []string `json:"created"`
		Skipped []string `json:"skipped"`
	}{}
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if len(out.Skipped) != 1 || out.Skipped[0] != "a@hellopro.fr" {
		t.Errorf("skipped = %v, want [a@hellopro.fr]", out.Skipped)
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestHandleUserSync -v`
Expected: FAIL to compile — `h.handleUserSync undefined`

- [ ] **Step 3: Write the handler**

Append to `internal/api/internal_handlers.go` (add `"strings"` and `"mcp-gateway/internal/repository"` to its imports):

```go
type syncUserEntry struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

type syncUsersRequest struct {
	Users []syncUserEntry `json:"users"`
}

type syncUsersResponse struct {
	Created []string `json:"created"`
	Skipped []string `json:"skipped"`
}

// handleUserSync is called by account-service-backend to pre-provision its
// users as gateway users (role config-only, is_allowed=false). Existing
// users are skipped untouched.
// Auth: X-Admin-Token only (no JWT — machine-to-machine), validated against
// ACCOUNT_INTERNAL_TOKEN, the same shared secret the gateway presents to
// account-service /internal/credentials.
func (h *Handler) handleUserSync(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	if h.config == nil || h.userRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "user sync not configured"})
		return
	}
	expected := h.config.AccountInternalToken
	got := r.Header.Get("X-Admin-Token")
	if expected == "" || subtle.ConstantTimeCompare([]byte(got), []byte(expected)) != 1 {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}
	var req syncUsersRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}
	inputs := make([]repository.SyncUserInput, 0, len(req.Users))
	for _, u := range req.Users {
		email := strings.ToLower(strings.TrimSpace(u.Email))
		if email == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "entry with empty email"})
			return
		}
		inputs = append(inputs, repository.SyncUserInput{Email: email, DisplayName: u.DisplayName})
	}
	created, skipped, err := h.userRepo.SyncUsers(inputs)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, syncUsersResponse{Created: created, Skipped: skipped})
}
```

Note: `writeJSON` and `ErrorResponse` already exist in package `api` (used by `handleRunnerSync`). `subtle` is already imported in this file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestHandleUserSync -v`
Expected: PASS (5 tests). Also run the runner-sync tests to confirm no regression: `go test ./internal/api/ -run TestHandleRunnerSync -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/internal_handlers.go apps-microservices/mcp-gateway-service/internal/api/internal_handlers_test.go
git commit -m "feat(mcp-gateway): add internal user sync handler

EN: POST handler gated by X-Admin-Token (ACCOUNT_INTERNAL_TOKEN),
normalizes emails, delegates to UserRepo.SyncUsers, returns
created/skipped lists.

FR: Handler POST protege par X-Admin-Token (ACCOUNT_INTERNAL_TOKEN),
normalise les emails, delegue a UserRepo.SyncUsers, renvoie les listes
created/skipped."
```

---

### Task 3: Gateway — mount route + auth skip-list

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/handler.go` (after the runner sync block ending line ~421)
- Modify: `apps-microservices/mcp-gateway-service/internal/auth/middleware.go:60-68`

- [ ] **Step 1: Mount the route in `handler.go`**

Insert directly after the `/api/v1/internal/runner/sync` registration block (after its closing `})` at ~line 421):

```go
	// Account-service → gateway user sync. account-service-backend
	// authenticates with X-Admin-Token (shared ACCOUNT_INTERNAL_TOKEN);
	// the handler enforces it. Path is in the auth middleware's
	// publicExact list so JWT is bypassed.
	apiMux.HandleFunc("/api/v1/internal/users/sync", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleUserSync(w, r)
	})
```

- [ ] **Step 2: Add the path to `publicExact` in `internal/auth/middleware.go`**

```go
var publicExact = map[string]bool{
	"/login":  true,
	"/logout": true,
	"/health": true,
	// Internal machine-to-machine endpoints (X-Admin-Token enforced on handler).
	// Kept as exact match to avoid accidentally exempting any future
	// /api/v1/internal/* endpoint from JWT auth.
	"/api/v1/internal/runner/sync": true,
	"/api/v1/internal/users/sync":  true,
}
```

(The comment's "endpoint" becomes "endpoints" — singular no longer accurate.)

- [ ] **Step 3: Build + full gateway test run**

Run: `cd apps-microservices/mcp-gateway-service && go build ./... && go test ./...`
Expected: build OK, all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/handler.go apps-microservices/mcp-gateway-service/internal/auth/middleware.go
git commit -m "feat(mcp-gateway): mount /api/v1/internal/users/sync route

EN: Register the user sync endpoint and exempt it from JWT auth
(X-Admin-Token enforced in the handler, mirroring runner/sync).

FR: Enregistre l'endpoint de sync utilisateurs et l'exempte du JWT
(X-Admin-Token verifie dans le handler, comme runner/sync)."
```

---

### Task 4: Account backend — config `MCPGatewayInternalURL`

**Files:**
- Test: `apps-microservices/account-service-backend/internal/config/config_test.go` (create if absent, else append)
- Modify: `apps-microservices/account-service-backend/internal/config/config.go`

- [ ] **Step 1: Write the failing test**

In `internal/config/config_test.go` (if the file does not exist, create it with `package config` and these imports: `strings`, `testing`):

```go
func TestLoad_MCPGatewayInternalURL(t *testing.T) {
	t.Setenv("MYSQL_DSN", "u:p@tcp(h:3306)/db")
	t.Setenv("ENCRYPTION_KEY", strings.Repeat("a", 64))
	t.Setenv("JWT_SECRET", "s")
	t.Setenv("ACCOUNT_PUBLIC_URL", "http://x")
	t.Setenv("MCP_GATEWAY_INTERNAL_URL", "http://mcp-gateway-service:8592/")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Trailing slash trimmed.
	if cfg.MCPGatewayInternalURL != "http://mcp-gateway-service:8592" {
		t.Errorf("MCPGatewayInternalURL = %q", cfg.MCPGatewayInternalURL)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/account-service-backend && go test ./internal/config/ -run TestLoad_MCPGatewayInternalURL -v`
Expected: FAIL to compile — `cfg.MCPGatewayInternalURL undefined`

- [ ] **Step 3: Implement**

In `internal/config/config.go`, add the field after `InternalAdminToken string` (line 33):

```go
	InternalAdminToken string
	// MCPGatewayInternalURL is the in-cluster base URL of mcp-gateway-service
	// (e.g. http://mcp-gateway-service:8592). Empty = MCP user sync disabled.
	MCPGatewayInternalURL string
```

And in `Load()`, after the `InternalAdminToken:` line (line 81):

```go
		InternalAdminToken:    os.Getenv("INTERNAL_ADMIN_TOKEN"),
		MCPGatewayInternalURL: strings.TrimRight(os.Getenv("MCP_GATEWAY_INTERNAL_URL"), "/"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/account-service-backend && go test ./internal/config/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/internal/config/
git commit -m "feat(account-service): add MCP_GATEWAY_INTERNAL_URL config

EN: New optional env for the in-cluster mcp-gateway base URL; empty
disables MCP user sync.

FR: Nouvelle variable optionnelle pour l'URL interne du mcp-gateway;
vide = sync MCP desactivee."
```

---

### Task 5: Account backend — `gatewaysync` client

**Files:**
- Create: `apps-microservices/account-service-backend/internal/gatewaysync/client.go`
- Test: `apps-microservices/account-service-backend/internal/gatewaysync/client_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/gatewaysync/client_test.go`:

```go
package gatewaysync

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSyncUsers_SendsTokenAndBody_ParsesResult(t *testing.T) {
	var gotToken string
	var gotBody struct {
		Users []SyncUser `json:"users"`
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/v1/internal/users/sync" {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		gotToken = r.Header.Get("X-Admin-Token")
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"created":["a@x"],"skipped":["b@x"]}`))
	}))
	defer srv.Close()

	c := New(srv.URL+"/", "secret") // trailing slash must be tolerated
	res, err := c.SyncUsers([]SyncUser{{Email: "a@x", DisplayName: "A"}, {Email: "b@x", DisplayName: "B"}})
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	if gotToken != "secret" {
		t.Errorf("X-Admin-Token = %q", gotToken)
	}
	if len(gotBody.Users) != 2 || gotBody.Users[0].Email != "a@x" {
		t.Errorf("body users = %+v", gotBody.Users)
	}
	if len(res.Created) != 1 || res.Created[0] != "a@x" || len(res.Skipped) != 1 || res.Skipped[0] != "b@x" {
		t.Errorf("result = %+v", res)
	}
}

func TestSyncUsers_Non200_ReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
	}))
	defer srv.Close()

	c := New(srv.URL, "bad")
	if _, err := c.SyncUsers([]SyncUser{{Email: "a@x"}}); err == nil {
		t.Fatal("want error on HTTP 401, got nil")
	}
}

func TestSyncUsers_ConnectionRefused_ReturnsError(t *testing.T) {
	c := New("http://127.0.0.1:1", "tok")
	if _, err := c.SyncUsers([]SyncUser{{Email: "a@x"}}); err == nil {
		t.Fatal("want connection error, got nil")
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/account-service-backend && go test ./internal/gatewaysync/ -v`
Expected: FAIL to compile — package does not exist yet (`client.go` missing)

- [ ] **Step 3: Implement the client**

Create `internal/gatewaysync/client.go`:

```go
// Package gatewaysync pushes account-service users to the MCP gateway's
// internal user sync endpoint so they are pre-provisioned as gateway users
// with the config-only role. Counterpart of the gateway's handleUserSync.
package gatewaysync

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// SyncUser is one user in the sync batch. Field names mirror the gateway's
// syncUserEntry contract.
type SyncUser struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

// Result mirrors the gateway's syncUsersResponse.
type Result struct {
	Created []string `json:"created"`
	Skipped []string `json:"skipped"`
}

type Client struct {
	baseURL string
	token   string
	cli     *http.Client
}

// New returns a client for the gateway at baseURL authenticating with the
// shared internal admin token (sent as X-Admin-Token).
func New(baseURL, token string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		cli:     &http.Client{Timeout: 5 * time.Second},
	}
}

// SyncUsers POSTs the batch to the gateway and returns its created/skipped
// outcome. Any non-200 response is an error carrying the status and a body
// excerpt.
func (c *Client) SyncUsers(users []SyncUser) (*Result, error) {
	body, err := json.Marshal(map[string][]SyncUser{"users": users})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequest(http.MethodPost, c.baseURL+"/api/v1/internal/users/sync", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-Token", c.token)

	resp, err := c.cli.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return nil, fmt.Errorf("gateway sync: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(b)))
	}
	var out Result
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/account-service-backend && go test ./internal/gatewaysync/ -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/internal/gatewaysync/
git commit -m "feat(account-service): add gatewaysync client for MCP user sync

EN: HTTP client posting user batches to the gateway internal sync
endpoint with X-Admin-Token, 5s timeout, typed created/skipped result.

FR: Client HTTP envoyant les lots d'utilisateurs a l'endpoint interne
du gateway avec X-Admin-Token, timeout 5s, resultat created/skipped."
```

---

### Task 6: Account backend — admin routes (single + bulk) and wiring

**Files:**
- Test: `apps-microservices/account-service-backend/internal/api/admin_user_handlers_test.go` (modify)
- Modify: `apps-microservices/account-service-backend/internal/api/admin_user_handlers.go`
- Modify: `apps-microservices/account-service-backend/internal/repository/user_repo.go`
- Modify: `apps-microservices/account-service-backend/internal/app/routes.go`
- Modify: `apps-microservices/account-service-backend/internal/app/app.go`

- [ ] **Step 1: Write the failing tests**

In `internal/api/admin_user_handlers_test.go`:

(a) Add `ListAllowed` to the existing `fakeUserAdminRepo` (the interface gains a method, so the fake must implement it or every existing test breaks):

```go
func (f *fakeUserAdminRepo) ListAllowed() ([]db.User, error) {
	out := []db.User{}
	for _, u := range f.users {
		if u.IsAllowed {
			out = append(out, u)
		}
	}
	return out, nil
}
```

(b) Add a fake syncer and the new tests (add `"account-service/internal/gatewaysync"` to the test file imports):

```go
type fakeMcpSync struct {
	got  []gatewaysync.SyncUser
	res  *gatewaysync.Result
	err  error
}

func (f *fakeMcpSync) SyncUsers(users []gatewaysync.SyncUser) (*gatewaysync.Result, error) {
	f.got = users
	if f.err != nil {
		return nil, f.err
	}
	return f.res, nil
}

func TestAdminUsers_SyncMcp_SingleUser(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x", DisplayName: "Alice", IsAllowed: false}}}
	sync := &fakeMcpSync{res: &gatewaysync.Result{Created: []string{"alice@x"}, Skipped: []string{}}}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/sync-mcp", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	// Per-row sync works even for a blocked user (explicit admin intent).
	if len(sync.got) != 1 || sync.got[0].Email != "alice@x" || sync.got[0].DisplayName != "Alice" {
		t.Fatalf("synced = %+v", sync.got)
	}
	var res gatewaysync.Result
	_ = json.Unmarshal(w.Body.Bytes(), &res)
	if len(res.Created) != 1 || res.Created[0] != "alice@x" {
		t.Errorf("created = %v", res.Created)
	}
}

func TestAdminUsers_SyncMcp_UnknownUser404(t *testing.T) {
	repo := &fakeUserAdminRepo{}
	sync := &fakeMcpSync{res: &gatewaysync.Result{}}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/ghost@x/sync-mcp", nil)
	r.SetPathValue("email", "ghost@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusNotFound {
		t.Fatalf("Code=%d, want 404", w.Code)
	}
	if sync.got != nil {
		t.Error("gateway must not be called for unknown user")
	}
}

func TestAdminUsers_SyncMcp_Unconfigured503(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: nil})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/sync-mcp", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("Code=%d, want 503", w.Code)
	}
}

func TestAdminUsers_SyncMcp_GatewayError502(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	sync := &fakeMcpSync{err: errors.New("connection refused")}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/sync-mcp", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusBadGateway {
		t.Fatalf("Code=%d, want 502", w.Code)
	}
}

func TestAdminUsersSyncAll_FiltersAllowedOnly(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{
		{Email: "ok@x", DisplayName: "OK", IsAllowed: true},
		{Email: "blocked@x", DisplayName: "Blocked", IsAllowed: false},
	}}
	sync := &fakeMcpSync{res: &gatewaysync.Result{Created: []string{"ok@x"}, Skipped: []string{}}}
	h := NewAdminUserMcpSyncAllHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/sync-mcp", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	if len(sync.got) != 1 || sync.got[0].Email != "ok@x" {
		t.Fatalf("synced = %+v, want only ok@x", sync.got)
	}
}

func TestAdminUsersSyncAll_NoAllowedUsers_SkipsGatewayCall(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "blocked@x", IsAllowed: false}}}
	sync := &fakeMcpSync{res: &gatewaysync.Result{}}
	h := NewAdminUserMcpSyncAllHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/sync-mcp", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	if sync.got != nil {
		t.Error("gateway must not be called with an empty batch")
	}
	if !strings.Contains(w.Body.String(), `"created":[]`) {
		t.Errorf("body = %s, want empty created/skipped", w.Body.String())
	}
}
```

Add `"strings"` to the test imports for the last assertion.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/account-service-backend && go test ./internal/api/ -run 'TestAdminUsers' -v`
Expected: FAIL to compile — `AdminUserDeps` has no field `McpSync`, `NewAdminUserMcpSyncAllHandler` undefined, `UserAdminRepo` missing `ListAllowed` (interface check)

- [ ] **Step 3: Implement handler changes**

In `internal/api/admin_user_handlers.go` — add `"account-service/internal/gatewaysync"` to imports, then:

(a) Extend `UserAdminRepo` and add the syncer interface + deps field:

```go
type UserAdminRepo interface {
	List(limit, offset int) ([]db.User, int64, error)
	ListAllowed() ([]db.User, error)
	FindByEmail(email string) (*db.User, error)
	SetAdmin(email string, admin bool) error
	SetAllowed(email string, ok bool) error
}

// McpSyncer pushes users to the MCP gateway. Nil when
// MCP_GATEWAY_INTERNAL_URL is unset (sync routes return 503).
type McpSyncer interface {
	SyncUsers(users []gatewaysync.SyncUser) (*gatewaysync.Result, error)
}

type AdminUserDeps struct {
	Repo        UserAdminRepo
	RevokeAll   RevokeAll
	Broadcaster LogoutBroadcaster
	McpSync     McpSyncer
}
```

(b) Add the `sync-mcp` op inside the existing `switch op` in `NewAdminUserHandler` (before `default:`). Unlike the other ops it returns early because its response body is the gateway result, not `{"status":"ok"}`:

```go
			case "sync-mcp":
				if d.McpSync == nil {
					writeJSONErr(w, http.StatusServiceUnavailable, "mcp_sync_unconfigured", "MCP gateway sync not configured")
					return
				}
				u, err := d.Repo.FindByEmail(email)
				if err != nil {
					writeJSONErr(w, http.StatusNotFound, "not_found", "unknown user")
					return
				}
				res, err := d.McpSync.SyncUsers([]gatewaysync.SyncUser{{Email: u.Email, DisplayName: u.DisplayName}})
				if err != nil {
					writeJSONErr(w, http.StatusBadGateway, "mcp_sync_failed", "mcp gateway sync failed: "+err.Error())
					return
				}
				_ = json.NewEncoder(w).Encode(res)
				return
```

(c) Append the bulk handler at the end of the file:

```go
// NewAdminUserMcpSyncAllHandler handles POST /api/v1/admin/users/sync-mcp:
// pushes every is_allowed account user to the MCP gateway. The gateway
// creates missing users (config-only) and reports existing ones as skipped.
func NewAdminUserMcpSyncAllHandler(d AdminUserDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if d.McpSync == nil {
			writeJSONErr(w, http.StatusServiceUnavailable, "mcp_sync_unconfigured", "MCP gateway sync not configured")
			return
		}
		users, err := d.Repo.ListAllowed()
		if err != nil {
			writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
			return
		}
		w.Header().Set("Content-Type", "application/json")
		if len(users) == 0 {
			_ = json.NewEncoder(w).Encode(&gatewaysync.Result{Created: []string{}, Skipped: []string{}})
			return
		}
		batch := make([]gatewaysync.SyncUser, 0, len(users))
		for _, u := range users {
			batch = append(batch, gatewaysync.SyncUser{Email: u.Email, DisplayName: u.DisplayName})
		}
		res, err := d.McpSync.SyncUsers(batch)
		if err != nil {
			writeJSONErr(w, http.StatusBadGateway, "mcp_sync_failed", "mcp gateway sync failed: "+err.Error())
			return
		}
		_ = json.NewEncoder(w).Encode(res)
	})
}
```

(d) In `internal/repository/user_repo.go`, add after `List` (line ~77):

```go
// ListAllowed returns every user with is_allowed=true, newest first.
// Used by the bulk MCP sync (blocked users are not pushed to the gateway).
func (r *UserRepo) ListAllowed() ([]db.User, error) {
	var users []db.User
	if err := r.g.Where("is_allowed = ?", true).Order("created_at DESC").Find(&users).Error; err != nil {
		return nil, err
	}
	return users, nil
}
```

- [ ] **Step 4: Run handler tests**

Run: `cd apps-microservices/account-service-backend && go test ./internal/api/ -run 'TestAdminUsers' -v`
Expected: PASS (all — including the pre-existing promote/demote/block/unblock/revoke tests)

- [ ] **Step 5: Wire routes and app**

In `internal/app/routes.go`:

(a) Add field to `routeDeps` (after `catalogAudit api.CatalogAuditFn`):

```go
	mcpSync      api.McpSyncer
```

(b) Pass the dep and register the bulk route. The `adminUserDeps` literal (line ~121) becomes:

```go
	adminUserDeps := api.AdminUserDeps{
		Repo:        r.User,
		RevokeAll:   r.Refresh,
		Broadcaster: userBroadcastAdapter{clients: r.OAuth2, refresh: r.Refresh, bc: d.broadcaster},
		McpSync:     d.mcpSync,
	}
	mux.Handle("GET /api/v1/admin/users", requireAdmin(api.NewAdminUserHandler(adminUserDeps)))
	// Literal segment — Go 1.22 mux prefers it over the {email}/{op} wildcard.
	mux.Handle("POST /api/v1/admin/users/sync-mcp", requireAdmin(api.NewAdminUserMcpSyncAllHandler(adminUserDeps)))
	mux.Handle("POST /api/v1/admin/users/{email}/{op}", requireAdmin(api.NewAdminUserHandler(adminUserDeps)))
```

In `internal/app/app.go` — add `"account-service/internal/gatewaysync"` to imports, construct the client right after the catalog-client block (after line ~87), mirroring its nil-when-unconfigured pattern:

```go
	// MCP gateway user sync — nil when MCP_GATEWAY_INTERNAL_URL is unset so
	// the sync routes return 503 instead of dialing nowhere.
	var mcpSync api.McpSyncer
	if cfg.MCPGatewayInternalURL != "" {
		mcpSync = gatewaysync.New(cfg.MCPGatewayInternalURL, cfg.InternalAdminToken)
	}
```

And add `mcpSync: mcpSync,` to the `routeDeps{...}` literal (line ~90).

- [ ] **Step 6: Build + full backend test run**

Run: `cd apps-microservices/account-service-backend && go build ./... && go test ./...`
Expected: build OK, all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/account-service-backend/internal/api/ apps-microservices/account-service-backend/internal/repository/user_repo.go apps-microservices/account-service-backend/internal/app/
git commit -m "feat(account-service): add sync-mcp admin routes (single + bulk)

EN: POST /api/v1/admin/users/{email}/sync-mcp and
POST /api/v1/admin/users/sync-mcp (is_allowed users only) proxy to the
gateway via gatewaysync; 503 unconfigured, 502 on gateway failure.

FR: POST /api/v1/admin/users/{email}/sync-mcp et
POST /api/v1/admin/users/sync-mcp (utilisateurs autorises uniquement)
relayes au gateway via gatewaysync; 503 si non configure, 502 si echec."
```

---

### Task 7: Frontend — API functions

**Files:**
- Test: `apps-microservices/account-service-frontend/src/api/users.spec.ts` (create)
- Modify: `apps-microservices/account-service-frontend/src/api/users.ts`

- [ ] **Step 1: Write the failing test**

Create `src/api/users.spec.ts` (mirrors `services.spec.ts`):

```typescript
import { describe, it, expect } from 'vitest'
import * as usersApi from './users'

describe('users api', () => {
  it('exports the admin user actions', () => {
    expect(typeof usersApi.list).toBe('function')
    expect(typeof usersApi.promote).toBe('function')
    expect(typeof usersApi.demote).toBe('function')
    expect(typeof usersApi.block).toBe('function')
    expect(typeof usersApi.unblock).toBe('function')
    expect(typeof usersApi.revoke).toBe('function')
  })

  it('exports the MCP sync actions', () => {
    expect(typeof usersApi.syncMcp).toBe('function')
    expect(typeof usersApi.syncMcpAll).toBe('function')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/account-service-frontend && npx vitest run src/api/users.spec.ts`
Expected: FAIL — `syncMcp` / `syncMcpAll` are undefined (first `it` passes)

- [ ] **Step 3: Implement**

Append to `src/api/users.ts` (after `revoke`, line 41):

```typescript
export interface McpSyncResult {
  created: string[]
  skipped: string[]
}

export function syncMcp(email: string) {
  return api<McpSyncResult>(`/api/v1/admin/users/${encodeURIComponent(email)}/sync-mcp`, { method: 'POST' })
}
export function syncMcpAll() {
  return api<McpSyncResult>('/api/v1/admin/users/sync-mcp', { method: 'POST' })
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/account-service-frontend && npx vitest run src/api/users.spec.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-frontend/src/api/users.ts apps-microservices/account-service-frontend/src/api/users.spec.ts
git commit -m "feat(account-frontend): add syncMcp/syncMcpAll API functions

EN: Typed wrappers for the new sync-mcp admin routes returning
created/skipped lists.

FR: Wrappers types pour les nouvelles routes admin sync-mcp renvoyant
les listes created/skipped."
```

---

### Task 8: Frontend — AdminUsersView buttons

**Files:**
- Modify: `apps-microservices/account-service-frontend/src/views/AdminUsersView.vue`

(View has no existing spec file; behavior is covered by the API spec from Task 7 plus the type-check build. Keep the view diff surgical.)

- [ ] **Step 1: Add the sync state + handlers in `<script setup>`**

After the `error` ref (line 28), add an info ref:

```typescript
const error = ref('')
const info = ref('')
```

After the existing `action()` function (line 51), add:

```typescript
async function runSync(fn: () => Promise<usersApi.McpSyncResult>, confirmText: string) {
  if (!confirm(confirmText)) return
  error.value = ''
  info.value = ''
  try {
    const r = await fn()
    info.value = `MCP sync : ${r.created.length} créé(s), ${r.skipped.length} déjà présent(s)`
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}
```

(No `load()` after sync — account-service rows are unchanged by it.)

- [ ] **Step 2: Add the per-row button**

Update the lucide import (line 5):

```typescript
import { ChevronUp, ChevronDown, Lock, Unlock, KeyRound, Users, CloudUpload } from 'lucide-vue-next'
```

In the `actions` column cell, before the final "Voir les sessions" button push (line 120), add:

```typescript
      buttons.push(
        iconButton(CloudUpload, 'Sync vers MCP gateway', 'hover:text-blue-600', () =>
          runSync(() => usersApi.syncMcp(u.email), `Sync ${u.email} vers MCP gateway ?`),
        ),
      )
```

- [ ] **Step 3: Add the global button + info banner in the template**

Replace the template header block (lines 132-134):

```html
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-semibold">Utilisateurs</h1>
      <button
        type="button"
        class="px-3 py-2 text-sm rounded-md bg-brand-500 text-white hover:bg-brand-600"
        @click="runSync(usersApi.syncMcpAll, 'Sync tous les utilisateurs autorisés vers MCP gateway ?')"
      >
        Sync MCP
      </button>
    </div>
    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>
    <div v-if="info" class="mb-4 p-3 bg-green-50 text-green-700 rounded">{{ info }}</div>
```

(The rest of the template — loading + DataTable — is unchanged.)

- [ ] **Step 4: Type-check, lint, full frontend test run**

Run: `cd apps-microservices/account-service-frontend && npx vue-tsc --noEmit -p tsconfig.app.json && npx vitest run`
Expected: no type errors, all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-frontend/src/views/AdminUsersView.vue
git commit -m "feat(account-frontend): MCP sync buttons on admin users view

EN: Per-row CloudUpload button + global 'Sync MCP' button with confirm
dialogs and a created/skipped result banner.

FR: Bouton CloudUpload par ligne + bouton global 'Sync MCP' avec
confirmations et bandeau de resultat created/skipped."
```

---

### Task 9: Deployment + docs

**Files:**
- Modify: `docker-compose.yml:2558-2559`
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`
- Modify: `apps-microservices/account-service-backend/CLAUDE.md`

- [ ] **Step 1: Compose env**

In `docker-compose.yml`, in the `account-service-backend` `environment:` block, insert after `INTERNAL_ADMIN_TOKEN: ${ACCOUNT_INTERNAL_TOKEN}` (line 2558):

```yaml
      INTERNAL_ADMIN_TOKEN: ${ACCOUNT_INTERNAL_TOKEN}
      # MCP gateway user sync (reverse direction of ACCOUNT_INTERNAL_TOKEN:
      # the backend pushes users to the gateway with the same shared secret)
      MCP_GATEWAY_INTERNAL_URL: ${MCP_GATEWAY_INTERNAL_URL:-http://mcp-gateway-service:8592}
```

- [ ] **Step 2: Gateway CLAUDE.md**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`, under the "### Runner Sync (internal, shared-secret auth via `X-Admin-Token`)" section, add:

```markdown
- `POST /api/v1/internal/users/sync` — account-service-backend pushes its users; gateway creates missing `gateway_users` (role `config-only`, `is_allowed=false`) and returns `{created, skipped}`. Token: `ACCOUNT_INTERNAL_TOKEN`.
```

- [ ] **Step 3: Account backend CLAUDE.md**

In `apps-microservices/account-service-backend/CLAUDE.md`, document in the routes/env sections (match the file's existing structure):

```markdown
- `POST /api/v1/admin/users/{email}/sync-mcp` — push one user to the MCP gateway (`config-only`, skip-existing). Admin only.
- `POST /api/v1/admin/users/sync-mcp` — push all `is_allowed` users. Admin only. Both return `{created, skipped}`; 503 when `MCP_GATEWAY_INTERNAL_URL` unset, 502 on gateway failure.
```

And the env var:

```markdown
| `MCP_GATEWAY_INTERNAL_URL` | — | In-cluster mcp-gateway base URL (e.g. `http://mcp-gateway-service:8592`). Empty = MCP user sync disabled. Auth reuses `INTERNAL_ADMIN_TOKEN`. |
```

- [ ] **Step 4: Final verification — all three components**

```bash
cd apps-microservices/mcp-gateway-service && go build ./... && go test ./...
cd ../account-service-backend && go build ./... && go test ./...
cd ../account-service-frontend && npx vue-tsc --noEmit -p tsconfig.app.json && npx vitest run
```

Expected: everything green.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml apps-microservices/mcp-gateway-service/CLAUDE.md apps-microservices/account-service-backend/CLAUDE.md
git commit -m "chore(compose,docs): wire MCP_GATEWAY_INTERNAL_URL + document sync

EN: Compose env for account-service-backend and CLAUDE.md docs for the
new user sync endpoint and admin routes.

FR: Variable compose pour account-service-backend et docs CLAUDE.md
pour le nouvel endpoint de sync et les routes admin."
```

---

## Notes for the Implementer

- **No new secret:** the gateway validates `X-Admin-Token` against its existing `ACCOUNT_INTERNAL_TOKEN` config (already populated in compose from `${ACCOUNT_INTERNAL_TOKEN}`, the same value as the backend's `INTERNAL_ADMIN_TOKEN`).
- **Local constraint:** unit tests only (remote-only infra). Do not attempt to start either service against MySQL.
- **Existing tests must stay green:** Task 6 widens the `UserAdminRepo` interface — the fake gets `ListAllowed` in the same step, before the interface change compiles.
- **`writeJSON` / `ErrorResponse` / `writeJSONErr`** already exist in their respective `api` packages — do not redefine them.
- **Auto-format hook:** Python-only; Go files are untouched. Run `gofmt` mentally — match existing style.
