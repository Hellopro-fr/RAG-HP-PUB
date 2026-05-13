# `zoho_imports` Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move per-user and admin Zoho routing data out of `mcp_servers` into a dedicated `zoho_imports` table; rewire the sheet-import handler to dispatch Zoho rows there; expose REST endpoints to manage the singleton admin row; swap the service's queries to the new table.

**Architecture:** Gateway owns the schema (GORM AutoMigrate). Gateway sheet-import handler dispatches Zoho-prefixed templates to `zoho_imports` instead of `mcp_servers`. Admin row is a singleton (`is_admin=1`) managed via `POST/GET/DELETE /api/v1/zoho-imports/admin`. `mcp_servers` keeps one Zoho stub row pointing at the service; `server_authorizations` on that stub continues to identify admin emails. `mcp-zoho-service` swaps its DB queries to read `zoho_imports`.

**Tech Stack:** Go 1.24 (both services), GORM v1.25 (gateway), `database/sql` + go-sql-driver/mysql (service), AES-256-GCM via `crypto/aes`+`crypto/cipher`, `net/http`.

**Spec:** `docs/superpowers/specs/2026-05-13-zoho-imports-table-design.md`.

---

## File Structure

**Gateway side:**

```
apps-microservices/mcp-gateway-service/
├── internal/db/
│   ├── models.go                      # +ZohoImport struct
│   └── mysql.go                       # +AutoMigrate entry
├── internal/repository/
│   ├── zoho_import_repo.go            # NEW: CRUD + admin singleton helpers
│   └── zoho_import_repo_test.go       # NEW: 5 tests
├── internal/api/
│   ├── zoho_admin_dto.go              # NEW: request/response shapes
│   ├── zoho_admin_handlers.go         # NEW: POST/GET/DELETE /api/v1/zoho-imports/admin
│   ├── zoho_admin_handlers_test.go    # NEW: 4 tests
│   ├── google_handlers.go             # +detectZohoTemplate + dispatch in handleImportInstancesFromSheet
│   ├── google_handlers_test.go        # +2 tests (zoho slug routes to zoho_imports; non-zoho path unchanged)
│   ├── handler.go                     # +register the 3 admin routes
│   └── handler_struct.go              # +ZohoImportRepo field on Handler (if Handler struct lives elsewhere, find the right file)
└── CLAUDE.md                          # +zoho_imports table + rollout
```

**Service side:**

```
apps-microservices/mcp-zoho-service/
├── internal/db/
│   ├── models.go                      # rename ServerRow → ImportRow (semantic move; same fields)
│   └── queries.go                     # swap FindAdminZohoServer/FindUserZohoImport to zoho_imports
├── internal/config/
│   └── config.go                      # +required env ZOHO_STUB_SERVER_ID
├── internal/routing/
│   ├── resolver.go                    # new sentinel ErrNoAdminZohoConfigured + admin-gate via stub server ID
│   └── resolver_test.go               # +new test for admin-grant + missing admin row
└── CLAUDE.md                          # update env table + resolution rules + rollout note
```

**Infra:**

```
docker-compose.yml                      # +ZOHO_STUB_SERVER_ID on both service blocks (default empty)
```

---

## Conventions

- **Go test runner**: `go test ./internal/... -count=1` from the respective service directory.
- **Build**: `go build ./...` from the same directory.
- **Commits**: bilingual EN+FR Conventional Commits, subject < 72 chars.
- **TDD where signalled**: test first, run, see fail, then implement, run, see pass, then commit.
- **Surgical edits**: don't reformat unrelated lines.

---

## Task 1: Gateway — `ZohoImport` GORM model + AutoMigrate

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/db/models.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/db/mysql.go`

- [ ] **Step 1: Add the struct**

At the end of `apps-microservices/mcp-gateway-service/internal/db/models.go`, append:

```go
// ZohoImport stores per-user and admin Zoho upstream URLs used by
// mcp-zoho-service for per-call routing. Rows are written by the gateway
// (sheet-import handler + admin REST endpoint) and read by the service.
//
// At most one row may have is_admin=1 AND is_active=1 (enforced by the
// repo layer). Admin rows MUST have empty created_by.
type ZohoImport struct {
	ID            string    `gorm:"type:char(36);primaryKey" json:"id"`
	Name          string    `gorm:"type:varchar(255);not null;default:''" json:"name"`
	URL           string    `gorm:"type:varchar(2048);not null" json:"url"`
	AuthHeaders   []byte    `gorm:"type:blob" json:"-"`
	CreatedBy     string    `gorm:"type:varchar(255);not null;default:'';index:idx_zoho_created_by" json:"created_by"`
	IsAdmin       bool      `gorm:"not null;default:false;index:idx_zoho_admin_active,priority:1" json:"is_admin"`
	IsActive      bool      `gorm:"not null;default:true;index:idx_zoho_admin_active,priority:2;index:idx_zoho_active" json:"is_active"`
	TemplateSlug  string    `gorm:"type:varchar(64);not null;default:''" json:"template_slug"`
	CreatedAt     time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt     time.Time `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

// TableName binds ZohoImport to the zoho_imports table.
func (ZohoImport) TableName() string { return "zoho_imports" }
```

Confirm `"time"` is already imported in this file (it is, used by other models).

- [ ] **Step 2: Register with AutoMigrate**

In `apps-microservices/mcp-gateway-service/internal/db/mysql.go`, find the `db.AutoMigrate(` block (around line 30). Add `&ZohoImport{}` to the list, anywhere after `&ServerAuthorization{}`. Suggested placement (insert one new line):

```go
		&ServerAuthorization{},
		&ZohoImport{},
		&SSOSession{},
```

- [ ] **Step 3: Build + tests**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./... && go test ./internal/... -count=1
```

Expected: PASS. The schema add is additive; no tests should regress.

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/db/models.go apps-microservices/mcp-gateway-service/internal/db/mysql.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): add zoho_imports GORM model + auto-migrate

New ZohoImport struct backs the per-user and admin Zoho routing rows
read by mcp-zoho-service. Composite index (is_admin, is_active) speeds
the admin singleton lookup; idx_zoho_created_by speeds per-user lookup.

EN: Ajoute le modèle GORM ZohoImport et son auto-migration; backe le
routage par utilisateur et admin du service mcp-zoho-service.
EOF
)"
```

---

## Task 2: Gateway — `zoho_import_repo` CRUD (TDD)

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo.go`
- Create: `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo_test.go`

The repo encapsulates the singleton-admin invariant + the constraint that admin rows must have empty `created_by`.

- [ ] **Step 1: Write the failing tests**

Create `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo_test.go`:

```go
package repository

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/db"
)

func TestZohoImportRepo_CreateUserImport(t *testing.T) {
	gormDB := newSQLiteTestDB(t)
	if err := gormDB.AutoMigrate(&db.ZohoImport{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	repo := NewZohoImportRepo(gormDB)

	in := &db.ZohoImport{
		ID:           uuid.New().String(),
		Name:         "alice's zoho",
		URL:          "https://mcp.zoho.eu/alice",
		AuthHeaders:  []byte{0xAA, 0xBB},
		CreatedBy:    "alice@hp.fr",
		TemplateSlug: "zoho-crm",
		IsAdmin:      false,
		IsActive:     true,
	}
	if err := repo.CreateUserImport(in); err != nil {
		t.Fatalf("CreateUserImport: %v", err)
	}

	got, err := repo.FindUserImportByEmail("alice@hp.fr")
	if err != nil {
		t.Fatalf("FindUserImportByEmail: %v", err)
	}
	if got.URL != in.URL {
		t.Fatalf("URL = %q, want %q", got.URL, in.URL)
	}
}

func TestZohoImportRepo_UpdateOrCreateAdmin_FirstCreates(t *testing.T) {
	gormDB := newSQLiteTestDB(t)
	if err := gormDB.AutoMigrate(&db.ZohoImport{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	repo := NewZohoImportRepo(gormDB)

	in := &db.ZohoImport{
		Name:        "Zoho admin",
		URL:         "https://mcp.zoho.eu/admin",
		AuthHeaders: []byte{0x01},
	}
	out, err := repo.UpdateOrCreateAdmin(in)
	if err != nil {
		t.Fatalf("UpdateOrCreateAdmin: %v", err)
	}
	if out.ID == "" || !out.IsAdmin {
		t.Fatalf("unexpected out: %+v", out)
	}
	if out.CreatedBy != "" {
		t.Fatalf("admin row must have empty created_by; got %q", out.CreatedBy)
	}
}

func TestZohoImportRepo_UpdateOrCreateAdmin_SecondUpdates(t *testing.T) {
	gormDB := newSQLiteTestDB(t)
	if err := gormDB.AutoMigrate(&db.ZohoImport{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	repo := NewZohoImportRepo(gormDB)

	first, _ := repo.UpdateOrCreateAdmin(&db.ZohoImport{Name: "v1", URL: "https://zoho/v1", AuthHeaders: []byte{1}})
	second, err := repo.UpdateOrCreateAdmin(&db.ZohoImport{Name: "v2", URL: "https://zoho/v2", AuthHeaders: []byte{2}})
	if err != nil {
		t.Fatalf("second UpdateOrCreateAdmin: %v", err)
	}
	if second.ID != first.ID {
		t.Fatalf("admin row ID changed: %q -> %q", first.ID, second.ID)
	}
	if second.URL != "https://zoho/v2" {
		t.Fatalf("URL not updated: %q", second.URL)
	}
}

func TestZohoImportRepo_UpdateOrCreateAdmin_RejectsCreatedBy(t *testing.T) {
	gormDB := newSQLiteTestDB(t)
	if err := gormDB.AutoMigrate(&db.ZohoImport{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	repo := NewZohoImportRepo(gormDB)

	_, err := repo.UpdateOrCreateAdmin(&db.ZohoImport{
		Name:      "bad",
		URL:       "https://zoho",
		CreatedBy: "alice@hp.fr",
	})
	if !errors.Is(err, ErrAdminCreatedByMustBeEmpty) {
		t.Fatalf("err = %v, want ErrAdminCreatedByMustBeEmpty", err)
	}
}

func TestZohoImportRepo_DeleteAdmin(t *testing.T) {
	gormDB := newSQLiteTestDB(t)
	if err := gormDB.AutoMigrate(&db.ZohoImport{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	repo := NewZohoImportRepo(gormDB)

	_, _ = repo.UpdateOrCreateAdmin(&db.ZohoImport{Name: "a", URL: "https://zoho", AuthHeaders: []byte{1}})
	if err := repo.DeleteAdmin(); err != nil {
		t.Fatalf("DeleteAdmin: %v", err)
	}
	got, err := repo.GetAdmin()
	if err != nil {
		t.Fatalf("GetAdmin: %v", err)
	}
	if got != nil {
		t.Fatalf("expected nil after delete, got %+v", got)
	}
}
```

`newSQLiteTestDB(t)` is the existing helper used by other repo tests in this directory (search for it; reuse). If the helper is named differently, mirror what the neighbouring `token_repo_test.go` or `oauth2_repo_test.go` files use.

- [ ] **Step 2: Run, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/repository/ -run TestZohoImportRepo -v
```

Expected: `undefined: NewZohoImportRepo` and similar.

- [ ] **Step 3: Implement the repo**

Create `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo.go`:

```go
package repository

import (
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// ErrAdminCreatedByMustBeEmpty is returned by UpdateOrCreateAdmin when the
// caller supplies a non-empty CreatedBy on the admin row.
var ErrAdminCreatedByMustBeEmpty = errors.New("admin zoho import must have empty created_by")

// ZohoImportRepo provides CRUD for the zoho_imports table.
type ZohoImportRepo struct {
	db *gorm.DB
}

// NewZohoImportRepo returns a repo bound to db.
func NewZohoImportRepo(db *gorm.DB) *ZohoImportRepo {
	return &ZohoImportRepo{db: db}
}

// CreateUserImport inserts a per-user row. ID is generated when empty.
// IsAdmin is forced to false to keep the singleton invariant.
func (r *ZohoImportRepo) CreateUserImport(z *db.ZohoImport) error {
	if z.ID == "" {
		z.ID = uuid.New().String()
	}
	z.IsAdmin = false
	if z.CreatedAt.IsZero() {
		z.CreatedAt = time.Now()
	}
	z.UpdatedAt = time.Now()
	return r.db.Create(z).Error
}

// UpdateOrCreateAdmin upserts the singleton admin row. CreatedBy must be
// empty (returns ErrAdminCreatedByMustBeEmpty otherwise). Returns the
// stored row with ID + IsAdmin populated.
func (r *ZohoImportRepo) UpdateOrCreateAdmin(z *db.ZohoImport) (*db.ZohoImport, error) {
	if z.CreatedBy != "" {
		return nil, ErrAdminCreatedByMustBeEmpty
	}

	existing, err := r.GetAdmin()
	if err != nil {
		return nil, err
	}
	if existing == nil {
		z.ID = uuid.New().String()
		z.IsAdmin = true
		z.IsActive = true
		z.CreatedAt = time.Now()
		z.UpdatedAt = time.Now()
		if err := r.db.Create(z).Error; err != nil {
			return nil, fmt.Errorf("create admin: %w", err)
		}
		return z, nil
	}

	existing.Name = z.Name
	existing.URL = z.URL
	existing.AuthHeaders = z.AuthHeaders
	existing.IsActive = true
	existing.UpdatedAt = time.Now()
	if err := r.db.Save(existing).Error; err != nil {
		return nil, fmt.Errorf("update admin: %w", err)
	}
	return existing, nil
}

// GetAdmin returns the oldest active admin row, or (nil, nil) when none exists.
func (r *ZohoImportRepo) GetAdmin() (*db.ZohoImport, error) {
	var out db.ZohoImport
	err := r.db.Where("is_admin = ? AND is_active = ?", true, true).Order("created_at ASC").First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// DeleteAdmin removes the singleton admin row. No-op when none exists.
func (r *ZohoImportRepo) DeleteAdmin() error {
	return r.db.Where("is_admin = ?", true).Delete(&db.ZohoImport{}).Error
}

// FindUserImportByEmail returns the oldest active per-user import whose
// created_by matches email by exact equality (case-insensitive). Used by
// tests only — the service queries directly via raw SQL.
func (r *ZohoImportRepo) FindUserImportByEmail(email string) (*db.ZohoImport, error) {
	var out db.ZohoImport
	err := r.db.
		Where("is_admin = ? AND is_active = ? AND LOWER(created_by) = LOWER(?)", false, true, email).
		Order("created_at ASC").
		First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}
```

- [ ] **Step 4: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/repository/ -run TestZohoImportRepo -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/repository/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): zoho_imports repo with singleton-admin upsert

CreateUserImport inserts per-user rows (forces is_admin=false).
UpdateOrCreateAdmin upserts the singleton (rejects non-empty
created_by). GetAdmin returns oldest active row or nil. DeleteAdmin
clears the singleton. FindUserImportByEmail used by handler tests.

EN: Repository CRUD pour zoho_imports avec upsert singleton du compte
admin et garde-fou created_by vide.
EOF
)"
```

---

## Task 3: Gateway — Admin REST endpoints (POST/GET/DELETE)

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go`
- Create: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`
- Create: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/handler.go`
- Modify: the file declaring `Handler` struct (search to find it — likely `internal/api/handler.go` itself)

- [ ] **Step 1: Add `ZohoImportRepo` field on Handler**

Search for the `Handler` struct declaration:

```bash
grep -n "type Handler struct" apps-microservices/mcp-gateway-service/internal/api/*.go
```

Open that file and add a new field after the existing repo fields (placement next to `templateRepo` is good):

```go
	zohoImportRepo *repository.ZohoImportRepo
```

Add a setter mirroring the existing setters in the same file:

```go
// SetZohoImportRepo injects the ZohoImportRepo used by the admin REST handlers
// and the sheet-import dispatch.
func (h *Handler) SetZohoImportRepo(repo *repository.ZohoImportRepo) {
	h.zohoImportRepo = repo
}
```

Boot wiring (search for where other repo setters are called — typically `internal/app/app.go`):

```bash
grep -n "SetTemplateRepo\|SetInstanceRepo\|SetGoogleTokenRepo" apps-microservices/mcp-gateway-service/internal/app/app.go
```

At that call site, add:

```go
	h.SetZohoImportRepo(repository.NewZohoImportRepo(database))
```

- [ ] **Step 2: Write DTOs**

Create `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go`:

```go
package api

// ZohoAdminCreateRequest is the body of POST /api/v1/zoho-imports/admin.
type ZohoAdminCreateRequest struct {
	Name        string            `json:"name"`
	URL         string            `json:"url"`
	AuthHeaders map[string]string `json:"auth_headers,omitempty"`
}

// ZohoAdminResponse is returned by GET and POST. AuthHeaderKeys lists the
// header names present (values are redacted; same pattern as mcp_servers GET).
type ZohoAdminResponse struct {
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	URL            string   `json:"url"`
	IsActive       bool     `json:"is_active"`
	AuthHeaderKeys []string `json:"auth_header_keys"`
	CreatedAt      string   `json:"created_at"`
	UpdatedAt      string   `json:"updated_at"`
}
```

- [ ] **Step 3: Write the handler tests**

Create `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`:

```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// newTestZohoAdminHandler returns a Handler primed with an in-memory SQLite
// DB and a fixed encryption key. Mirrors patterns used by other api/*_test.go
// helpers in this directory.
func newTestZohoAdminHandler(t *testing.T) *Handler {
	t.Helper()
	gormDB := newSQLiteAPITestDB(t)
	enc, err := crypto.NewEncryptor("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	if err != nil {
		t.Fatalf("crypto: %v", err)
	}
	h := &Handler{encryptor: enc}
	h.SetZohoImportRepo(repository.NewZohoImportRepo(gormDB))
	return h
}

func TestZohoAdmin_PostCreatesThenUpdates(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	// First POST → 201
	body, _ := json.Marshal(ZohoAdminCreateRequest{
		Name:        "Zoho CRM",
		URL:         "https://mcp.zoho.eu/v1",
		AuthHeaders: map[string]string{"Authorization": "Bearer v1"},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("first POST status = %d, want 201 (body=%s)", rec.Code, rec.Body.String())
	}
	var first ZohoAdminResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &first)
	if first.URL != "https://mcp.zoho.eu/v1" {
		t.Fatalf("URL = %q", first.URL)
	}

	// Second POST → 200 + same ID
	body, _ = json.Marshal(ZohoAdminCreateRequest{
		Name:        "Zoho CRM",
		URL:         "https://mcp.zoho.eu/v2",
		AuthHeaders: map[string]string{"Authorization": "Bearer v2"},
	})
	req = httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec = httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("second POST status = %d, want 200", rec.Code)
	}
	var second ZohoAdminResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &second)
	if second.ID != first.ID {
		t.Fatalf("ID changed: %q -> %q", first.ID, second.ID)
	}
	if second.URL != "https://mcp.zoho.eu/v2" {
		t.Fatalf("URL = %q", second.URL)
	}
}

func TestZohoAdmin_GetReturnsAdminOr404(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	// Before create → 404
	req := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/admin", nil)
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("GET before create: status = %d, want 404", rec.Code)
	}

	// Create then GET
	body, _ := json.Marshal(ZohoAdminCreateRequest{Name: "Z", URL: "https://zoho", AuthHeaders: map[string]string{"X-Auth": "k"}})
	req = httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec = httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create: %d body=%s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/admin", nil)
	rec = httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("GET: %d", rec.Code)
	}
	var got ZohoAdminResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &got)
	if len(got.AuthHeaderKeys) != 1 || got.AuthHeaderKeys[0] != "X-Auth" {
		t.Fatalf("AuthHeaderKeys = %+v, want [X-Auth]", got.AuthHeaderKeys)
	}
}

func TestZohoAdmin_DeleteClears(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	body, _ := json.Marshal(ZohoAdminCreateRequest{Name: "Z", URL: "https://zoho", AuthHeaders: map[string]string{"X-Auth": "k"}})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create: %d", rec.Code)
	}

	req = httptest.NewRequest(http.MethodDelete, "/api/v1/zoho-imports/admin", nil)
	rec = httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("DELETE: %d", rec.Code)
	}

	req = httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/admin", nil)
	rec = httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("GET after delete: %d, want 404", rec.Code)
	}
}

func TestZohoAdmin_RejectsBadJSON(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader([]byte("not json")))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}
```

`newSQLiteAPITestDB(t)` is the helper used by other api/*_test.go files in this directory. Search for it (`grep -n "newSQLite" apps-microservices/mcp-gateway-service/internal/api/*_test.go`) and reuse the exact name in use.

- [ ] **Step 4: Run, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestZohoAdmin -v
```

Expected: `undefined: handleZohoAdmin`.

- [ ] **Step 5: Implement the handler**

Create `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`:

```go
package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// handleZohoAdmin dispatches the three verbs on /api/v1/zoho-imports/admin.
// All three verbs are admin-gated by the existing isAdminOnly middleware
// (configured in handler.go to match the path prefix).
func (h *Handler) handleZohoAdmin(w http.ResponseWriter, r *http.Request) {
	if h.zohoImportRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "zoho imports not configured"})
		return
	}
	switch r.Method {
	case http.MethodGet:
		h.handleZohoAdminGet(w, r)
	case http.MethodPost:
		h.handleZohoAdminPost(w, r)
	case http.MethodDelete:
		h.handleZohoAdminDelete(w, r)
	default:
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

func (h *Handler) handleZohoAdminGet(w http.ResponseWriter, r *http.Request) {
	row, err := h.zohoImportRepo.GetAdmin()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "no admin zoho row configured"})
		return
	}
	writeJSON(w, http.StatusOK, zohoAdminToResponse(row, h))
}

func (h *Handler) handleZohoAdminPost(w http.ResponseWriter, r *http.Request) {
	var req ZohoAdminCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.URL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "url is required"})
		return
	}

	// Encrypt auth_headers (if any).
	var encrypted []byte
	if len(req.AuthHeaders) > 0 {
		raw, err := json.Marshal(req.AuthHeaders)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encode auth_headers: " + err.Error()})
			return
		}
		if h.encryptor != nil {
			encrypted, err = h.encryptor.Encrypt(raw)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encrypt auth_headers: " + err.Error()})
				return
			}
		} else {
			encrypted = raw
		}
	}

	// Detect first-time create vs update for status code.
	existing, err := h.zohoImportRepo.GetAdmin()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	in := &db.ZohoImport{
		Name:        req.Name,
		URL:         req.URL,
		AuthHeaders: encrypted,
	}
	row, err := h.zohoImportRepo.UpdateOrCreateAdmin(in)
	if err != nil {
		if errors.Is(err, repository.ErrAdminCreatedByMustBeEmpty) {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	status := http.StatusCreated
	if existing != nil {
		status = http.StatusOK
	}
	writeJSON(w, status, zohoAdminToResponse(row, h))
}

func (h *Handler) handleZohoAdminDelete(w http.ResponseWriter, r *http.Request) {
	if err := h.zohoImportRepo.DeleteAdmin(); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// zohoAdminToResponse renders a row into the wire shape, decrypting
// auth_headers only to extract key names (values stay redacted).
func zohoAdminToResponse(row *db.ZohoImport, h *Handler) ZohoAdminResponse {
	keys := make([]string, 0)
	if len(row.AuthHeaders) > 0 && h.encryptor != nil {
		if pt, err := h.encryptor.Decrypt(row.AuthHeaders); err == nil {
			var m map[string]string
			if json.Unmarshal(pt, &m) == nil {
				for k := range m {
					keys = append(keys, k)
				}
			}
		}
	}
	return ZohoAdminResponse{
		ID:             row.ID,
		Name:           row.Name,
		URL:            row.URL,
		IsActive:       row.IsActive,
		AuthHeaderKeys: keys,
		CreatedAt:      row.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:      row.UpdatedAt.UTC().Format(time.RFC3339),
	}
}

// _ marks an unused import path to silence the linter when strings becomes
// unused in this file. Remove if strings is consumed (currently it isn't).
var _ = strings.TrimSpace
```

If `strings` ends up unused after final read, delete the import line + the `var _` line.

- [ ] **Step 6: Register the route**

In `apps-microservices/mcp-gateway-service/internal/api/handler.go`, locate the route registration block (around line 124 where `/api/v1/tokens` is registered). After the LLM-instructions routes (around line 130), add:

```go
		apiMux.HandleFunc("/api/v1/zoho-imports/admin", h.handleZohoAdmin)
```

Also extend `isAdminOnly` (around line 557) — find the slice/switch of admin paths and add `"/api/v1/zoho-imports/admin"` to it so the existing admin gate intercepts.

- [ ] **Step 7: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestZohoAdmin -v
```

Expected: all 4 tests PASS.

- [ ] **Step 8: Run full backend suite**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go \
  apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go \
  apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go \
  apps-microservices/mcp-gateway-service/internal/api/handler.go \
  apps-microservices/mcp-gateway-service/internal/app/app.go
# Add the handler-struct file if it lives elsewhere:
# git add apps-microservices/mcp-gateway-service/internal/api/<handler-struct-file>.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): admin REST for zoho_imports singleton

POST /api/v1/zoho-imports/admin upserts the singleton admin row,
returning 201 on first create and 200 on subsequent updates. GET
returns the row with redacted auth header values (keys only). DELETE
clears the singleton. Admin-gated via the existing isAdminOnly path
match. AuthHeaders are encrypted with the gateway's ENCRYPTION_KEY.

EN: API admin pour gérer le singleton du compte Zoho dans la table
zoho_imports.
EOF
)"
```

---

## Task 4: Gateway — Sheet-import dispatch (Zoho → `zoho_imports`)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go`

- [ ] **Step 1: Add `detectZohoTemplate` helper + dispatch in `handleImportInstancesFromSheet`**

In `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go`, locate the row-creation loop inside `handleImportInstancesFromSheet` (search for `createInstanceFromSpec`). Just before that call, insert a dispatch that writes to `zoho_imports` when the template is a Zoho slug. Add the helper near the bottom of the file.

Add the helper:

```go
// detectZohoTemplate returns true when the template's slug is the Zoho
// catalog row (matches ^zoho(-.*)?$). The detection is anchored on the
// catalog slug, not on imported sheet content, so a future non-Zoho
// template can't accidentally route through the zoho_imports table.
func detectZohoTemplate(slug string) bool {
	return slug == "zoho" || strings.HasPrefix(slug, "zoho-")
}
```

Locate the per-row block in `handleImportInstancesFromSheet` (around line 541, where `h.createInstanceFromSpec(...)` is called). Just before that call site, dispatch:

```go
		if detectZohoTemplate(tpl.Slug) {
			zohoRow := &db.ZohoImport{
				Name:         instName,
				URL:          rowURL,                         // from sheet, see note below
				AuthHeaders:  encryptedAuthHeaders,           // already encrypted via h.encryptor.Encrypt
				CreatedBy:    rowCreatedBy,
				TemplateSlug: tpl.Slug,
				IsAdmin:      false,
				IsActive:     true,
			}
			if cerr := h.zohoImportRepo.CreateUserImport(zohoRow); cerr != nil {
				result.Status = "error"
				result.Message = cerr.Error()
				resp.Results = append(resp.Results, result)
				resp.Errors++
				continue
			}
			result.Status = "imported"
			resp.Results = append(resp.Results, result)
			resp.Imported++
			continue
		}
```

Notes:
- `rowURL` is the upstream Zoho URL extracted from the sheet — the `handleImportInstancesFromSheet` flow already reads a `url` column for the http_batch case. Reuse that local variable name (read the function's existing variables before editing).
- `encryptedAuthHeaders` is the encrypted JSON of the sheet's `auth_headers` column (the existing code path already encrypts auth headers before insert; reuse the same intermediate). If the existing function uses `credBytes` for Zoho's credentials, follow whichever shape matches the sheet's mapping.
- The non-Zoho branch (existing `createInstanceFromSpec` call) stays untouched.

If the existing handler does not extract `rowURL` or `encryptedAuthHeaders` for the http_batch path, swap to whichever locals it does build. The point is: write the same fields to `zoho_imports` that would otherwise have gone into `mcp_servers`.

- [ ] **Step 2: Add unit tests for the helper**

In `apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go`, append:

```go
func TestDetectZohoTemplate(t *testing.T) {
	cases := []struct {
		slug string
		want bool
	}{
		{"zoho", true},
		{"zoho-crm", true},
		{"zoho-mail", true},
		{"zohoesque", false}, // no dash after "zoho"
		{"ga", false},
		{"gsc", false},
		{"", false},
		{"zoho-", true}, // empty suffix still has the dash
	}
	for _, tc := range cases {
		t.Run(tc.slug, func(t *testing.T) {
			if got := detectZohoTemplate(tc.slug); got != tc.want {
				t.Fatalf("detectZohoTemplate(%q) = %v, want %v", tc.slug, got, tc.want)
			}
		})
	}
}
```

- [ ] **Step 3: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run "TestDetectZohoTemplate|TestImportInstances" -v
```

Expected: all PASS. The integration sheet-import tests (full happy path) are heavy and may stay covered by the existing test set; we just add the dispatch helper test here.

- [ ] **Step 4: Run full backend suite**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/api/google_handlers.go apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): dispatch Zoho sheet imports to zoho_imports table

Sheet-import handler now detects Zoho-prefixed templates by their
catalog slug (^zoho(-.*)?$) and writes the imported row to the new
zoho_imports table instead of mcp_servers. Non-Zoho templates remain
on the existing path.

EN: Le handler d'import sheet bascule les templates Zoho vers la
nouvelle table zoho_imports.
EOF
)"
```

---

## Task 5: Service — Model + queries swap to `zoho_imports`

**Files:**
- Modify: `apps-microservices/mcp-zoho-service/internal/db/models.go`
- Modify: `apps-microservices/mcp-zoho-service/internal/db/queries.go`

- [ ] **Step 1: Rename + extend `models.go`**

Replace `apps-microservices/mcp-zoho-service/internal/db/models.go` content:

```go
// Package db carries the read-side row shapes that match the columns
// queries.go selects. These are NOT the gateway's full GORM models —
// only the subset the resolver needs.
package db

// ImportRow is the narrow view of a zoho_imports row used by the resolver.
type ImportRow struct {
	ID          string
	URL         string
	AuthHeaders []byte
	CreatedBy   string
	IsAdmin     bool
}
```

Note: `ServerRow` is renamed to `ImportRow`. The resolver in Task 7 picks up the new name.

- [ ] **Step 2: Swap the queries**

Replace `apps-microservices/mcp-zoho-service/internal/db/queries.go` content:

```go
package db

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
)

// Queries wraps a *sql.DB with the prepared statements the resolver needs.
type Queries struct {
	db *sql.DB
}

// NewQueries returns a Queries primed with the given DB handle.
func NewQueries(db *sql.DB) *Queries {
	return &Queries{db: db}
}

// FindAdminZohoImport returns the singleton admin row from zoho_imports.
// Returns sql.ErrNoRows when no admin row is configured.
func (q *Queries) FindAdminZohoImport(ctx context.Context) (*ImportRow, error) {
	const query = `
		SELECT id, url, auth_headers, created_by, is_admin
		FROM zoho_imports
		WHERE is_admin = 1 AND is_active = 1
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query)
	out := &ImportRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy, &out.IsAdmin); err != nil {
		return nil, err
	}
	return out, nil
}

// IsAdminGranted returns true when a server_authorizations row grants
// full access on stubServerID for the given email (case-insensitive).
// stubServerID is the UUID of the mcp_servers row whose tool_prefix='zoho'
// and url points at this service (configured via ZOHO_STUB_SERVER_ID).
func (q *Queries) IsAdminGranted(ctx context.Context, stubServerID, email string) (bool, error) {
	if stubServerID == "" || email == "" {
		return false, nil
	}
	const query = `
		SELECT 1
		FROM server_authorizations
		WHERE mcp_server_id = ?
		  AND LOWER(email) = LOWER(?)
		LIMIT 1
	`
	var dummy int
	err := q.db.QueryRowContext(ctx, query, stubServerID, email).Scan(&dummy)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("server_authorizations: %w", err)
	}
	return true, nil
}

// FindUserZohoImport returns the oldest active per-user zoho_imports row
// whose created_by matches by exact email or by login-portion.
// Returns sql.ErrNoRows when nothing matches.
func (q *Queries) FindUserZohoImport(ctx context.Context, email, login string) (*ImportRow, error) {
	emailLower := strings.ToLower(email)
	loginLower := strings.ToLower(login)
	if emailLower == "" && loginLower == "" {
		return nil, sql.ErrNoRows
	}

	const query = `
		SELECT id, url, auth_headers, created_by, is_admin
		FROM zoho_imports
		WHERE is_admin = 0 AND is_active = 1
		  AND (
		        LOWER(created_by) = ?
		     OR (? <> '' AND LOWER(created_by) LIKE CONCAT(?, '@%'))
		  )
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query, emailLower, loginLower, loginLower)
	out := &ImportRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy, &out.IsAdmin); err != nil {
		return nil, err
	}
	return out, nil
}
```

- [ ] **Step 3: Update existing smoke test**

In `apps-microservices/mcp-zoho-service/internal/db/queries_test.go`, replace the body with:

```go
package db

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"

	_ "github.com/go-sql-driver/mysql"
)

// TestQueries_Smoke is an integration smoke test against a live MySQL
// instance carrying the gateway schema. Skipped when MYSQL_TEST_DSN is
// unset so `go test` stays green on dev laptops without MySQL.
func TestQueries_Smoke(t *testing.T) {
	dsn := os.Getenv("MYSQL_TEST_DSN")
	if dsn == "" {
		t.Skip("MYSQL_TEST_DSN unset; skipping integration smoke")
	}
	conn, err := Open(dsn)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer conn.Close()

	ctx := context.Background()
	q := NewQueries(conn)

	if _, err := q.FindAdminZohoImport(ctx); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("FindAdminZohoImport: %v", err)
	}
	if _, err := q.FindUserZohoImport(ctx, "alice@hp.fr", "alice"); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("FindUserZohoImport: %v", err)
	}
	if _, err := q.IsAdminGranted(ctx, "any-stub-id", "alice@hp.fr"); err != nil {
		t.Fatalf("IsAdminGranted: %v", err)
	}
}
```

- [ ] **Step 4: Build (resolver will be temporarily broken until Task 7)**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./internal/db/...
```

Expected: success. Whole-service build will FAIL until Task 7 because resolver references the old query names. That's expected — Tasks 5–7 land together for the service side.

- [ ] **Step 5: Do NOT commit yet**

This task leaves the service in a half-state. Stage the changes but defer commit until Task 7. Run:

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/db/models.go apps-microservices/mcp-zoho-service/internal/db/queries.go apps-microservices/mcp-zoho-service/internal/db/queries_test.go
```

(No commit. The commit lands at the end of Task 7 once the resolver is updated to match.)

---

## Task 6: Service — Config requires `ZOHO_STUB_SERVER_ID`

**Files:**
- Modify: `apps-microservices/mcp-zoho-service/internal/config/config.go`

- [ ] **Step 1: Add the field + validation**

In `apps-microservices/mcp-zoho-service/internal/config/config.go`, add `StubServerID string` to the `Config` struct (placement: right after `SelfURL`):

```go
	StubServerID    string
```

In `Load()`, read the env and validate:

```go
		StubServerID:    os.Getenv("ZOHO_STUB_SERVER_ID"),
```

After the existing required-field checks (where `SelfURL == ""` returns an error), add:

```go
	if c.StubServerID == "" {
		return nil, fmt.Errorf("ZOHO_STUB_SERVER_ID is required (UUID of the gateway's mcp_servers stub row whose URL points at this service)")
	}
```

- [ ] **Step 2: Build**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./internal/config/...
```

Expected: success. Full service build will succeed at the end of Task 7.

- [ ] **Step 3: Stage**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/config/config.go
```

No commit yet.

---

## Task 7: Service — Resolver rewire (new sentinel + new queries)

**Files:**
- Modify: `apps-microservices/mcp-zoho-service/internal/routing/resolver.go`
- Modify: `apps-microservices/mcp-zoho-service/internal/routing/resolver_test.go`
- Modify: `apps-microservices/mcp-zoho-service/cmd/server/main.go`
- Modify: `apps-microservices/mcp-zoho-service/internal/transport/handler.go`

- [ ] **Step 1: Update `resolver.go`**

Replace `apps-microservices/mcp-zoho-service/internal/routing/resolver.go` content:

```go
package routing

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	"mcp-zoho-service/internal/db"
)

// Sentinel errors surfaced as JSON-RPC envelopes by the transport layer.
var (
	ErrNoZohoConfigured      = errors.New("no_zoho_configured")
	ErrNoAdminZohoConfigured = errors.New("no_admin_zoho_configured")
	ErrMisconfigured         = errors.New("misconfigured")
	ErrInvalidIdentity       = errors.New("invalid_identity")
)

// QueryRunner is the narrow contract resolver needs from the DB layer.
type QueryRunner interface {
	FindAdminZohoImport(ctx context.Context) (*db.ImportRow, error)
	IsAdminGranted(ctx context.Context, stubServerID, email string) (bool, error)
	FindUserZohoImport(ctx context.Context, email, login string) (*db.ImportRow, error)
}

// Decryptor unwraps an encrypted blob (zoho_imports.auth_headers).
type Decryptor interface {
	Decrypt([]byte) ([]byte, error)
}

// Resolver maps a caller's identity to an upstream Zoho URL.
type Resolver struct {
	q             QueryRunner
	dec           Decryptor
	cache         *cache
	stubServerID  string
}

// NewResolver wires the dependencies.
func NewResolver(q QueryRunner, dec Decryptor, ttl time.Duration, stubServerID string) *Resolver {
	return &Resolver{q: q, dec: dec, cache: newCache(ttl), stubServerID: stubServerID}
}

// Resolve returns the upstream URL and decrypted headers for the caller, or
// one of the sentinel errors above. The cache is consulted first.
func (r *Resolver) Resolve(ctx context.Context, email, login string) (*Resolution, error) {
	if email == "" && login == "" {
		return nil, ErrInvalidIdentity
	}
	key := lower(email)
	if v, ok := r.cache.get(key); ok {
		return v, nil
	}

	// Admin gate: is this email granted full access on the gateway's stub row?
	granted, err := r.q.IsAdminGranted(ctx, r.stubServerID, email)
	if err != nil {
		return nil, fmt.Errorf("server_authorizations lookup: %w", err)
	}
	if granted {
		adminRow, aerr := r.q.FindAdminZohoImport(ctx)
		if aerr != nil {
			if errors.Is(aerr, sql.ErrNoRows) {
				return nil, ErrNoAdminZohoConfigured
			}
			return nil, fmt.Errorf("find admin row: %w", aerr)
		}
		res, berr := r.buildResolution(adminRow)
		if berr != nil {
			return nil, berr
		}
		r.cache.set(key, res)
		return res, nil
	}

	// User lookup.
	userRow, err := r.q.FindUserZohoImport(ctx, email, login)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNoZohoConfigured
		}
		return nil, fmt.Errorf("find user row: %w", err)
	}

	// Defensive Go-side match (the SQL already filtered).
	if !matchesUserEmail(userRow.CreatedBy, email, login) {
		log.Printf("[resolver] WARN: SQL match for %s did not pass Go-side matchesUserEmail (created_by=%q)", email, userRow.CreatedBy)
		return nil, ErrNoZohoConfigured
	}

	res, err := r.buildResolution(userRow)
	if err != nil {
		return nil, err
	}
	r.cache.set(key, res)
	return res, nil
}

func (r *Resolver) buildResolution(row *db.ImportRow) (*Resolution, error) {
	headers := map[string]string{}
	if len(row.AuthHeaders) > 0 {
		pt, err := r.dec.Decrypt(row.AuthHeaders)
		if err != nil {
			return nil, fmt.Errorf("decrypt auth_headers for row %s: %w", row.ID, err)
		}
		if err := json.Unmarshal(pt, &headers); err != nil {
			return nil, fmt.Errorf("decode auth_headers for row %s: %w", row.ID, err)
		}
	}
	return &Resolution{UpstreamURL: row.URL, Headers: headers}, nil
}

// lower is strings.ToLower wrapped so resolver_test.go can reuse it.
func lower(s string) string { return strings.ToLower(s) }
```

Note: `selfURL` is removed from `Resolver`. `stubServerID` replaces it. The `FindAdminZohoServer` query name is gone — service now uses `FindAdminZohoImport`. `ErrMisconfigured` stays for legacy paths but is unused on the happy paths. (Leave it defined; the transport layer may still reference it.)

- [ ] **Step 2: Update `resolver_test.go`**

Replace `apps-microservices/mcp-zoho-service/internal/routing/resolver_test.go` content:

```go
package routing

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"mcp-zoho-service/internal/db"
)

type stubRunner struct {
	adminRow      *db.ImportRow
	adminErr      error
	importRow     *db.ImportRow
	importErr     error
	grants        map[string]map[string]bool // stubID → email(lower) → granted
	adminCalls    int
	grantCalls    int
	importCalls   int
}

func (s *stubRunner) FindAdminZohoImport(_ context.Context) (*db.ImportRow, error) {
	s.adminCalls++
	if s.adminErr != nil {
		return nil, s.adminErr
	}
	if s.adminRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.adminRow, nil
}

func (s *stubRunner) IsAdminGranted(_ context.Context, stubID, email string) (bool, error) {
	s.grantCalls++
	g, ok := s.grants[stubID]
	if !ok {
		return false, nil
	}
	return g[lower(email)], nil
}

func (s *stubRunner) FindUserZohoImport(_ context.Context, _, _ string) (*db.ImportRow, error) {
	s.importCalls++
	if s.importErr != nil {
		return nil, s.importErr
	}
	if s.importRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.importRow, nil
}

type fakeDecryptor struct{}

func (fakeDecryptor) Decrypt(b []byte) ([]byte, error) { return b, nil }

const testStubID = "stub-uuid-1234"

func TestResolver_AdminGranted(t *testing.T) {
	sr := &stubRunner{
		adminRow: &db.ImportRow{ID: "admin-1", URL: "http://admin-zoho/mcp", AuthHeaders: []byte(`{"Authorization":"Bearer admin"}`), IsAdmin: true},
		grants:   map[string]map[string]bool{testStubID: {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://admin-zoho/mcp" {
		t.Fatalf("upstream = %q", got.UpstreamURL)
	}
	if got.Headers["Authorization"] != "Bearer admin" {
		t.Fatalf("Authorization = %q", got.Headers["Authorization"])
	}
}

func TestResolver_AdminGrantedButNoAdminRow(t *testing.T) {
	sr := &stubRunner{
		grants: map[string]map[string]bool{testStubID: {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	_, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if !errors.Is(err, ErrNoAdminZohoConfigured) {
		t.Fatalf("err = %v, want ErrNoAdminZohoConfigured", err)
	}
}

func TestResolver_UserImport(t *testing.T) {
	sr := &stubRunner{
		grants:    map[string]map[string]bool{},
		importRow: &db.ImportRow{ID: "user-1", URL: "http://alice-zoho/mcp", CreatedBy: "alice@hp.fr"},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://alice-zoho/mcp" {
		t.Fatalf("upstream = %q", got.UpstreamURL)
	}
}

func TestResolver_NoMatch(t *testing.T) {
	sr := &stubRunner{importErr: sql.ErrNoRows}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	_, err := r.Resolve(context.Background(), "charlie@hp.fr", "charlie")
	if !errors.Is(err, ErrNoZohoConfigured) {
		t.Fatalf("err = %v, want ErrNoZohoConfigured", err)
	}
}

func TestResolver_EmptyEmail(t *testing.T) {
	sr := &stubRunner{}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	_, err := r.Resolve(context.Background(), "", "")
	if !errors.Is(err, ErrInvalidIdentity) {
		t.Fatalf("err = %v, want ErrInvalidIdentity", err)
	}
}

func TestResolver_CacheHit(t *testing.T) {
	sr := &stubRunner{
		adminRow: &db.ImportRow{ID: "admin-1", URL: "http://admin/mcp"},
		grants:   map[string]map[string]bool{testStubID: {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("first: %v", err)
	}
	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("second: %v", err)
	}
	if sr.adminCalls > 1 || sr.grantCalls > 1 {
		t.Fatalf("cache miss on second call: admin=%d grant=%d", sr.adminCalls, sr.grantCalls)
	}
}
```

- [ ] **Step 3: Update `main.go` to pass StubServerID**

In `apps-microservices/mcp-zoho-service/cmd/server/main.go`, find the `routing.NewResolver` call. Change the last argument from `cfg.SelfURL` to `cfg.StubServerID`:

```go
	resolver := routing.NewResolver(queries, dec, cfg.CacheTTL, cfg.StubServerID)
```

- [ ] **Step 4: Update transport handler error mapping**

In `apps-microservices/mcp-zoho-service/internal/transport/handler.go`, locate `writeResolverError`. Add a case for the new sentinel `ErrNoAdminZohoConfigured` BEFORE the generic `ErrNoZohoConfigured` case:

```go
	case errors.Is(err, routing.ErrNoAdminZohoConfigured):
		body := mcperr.WriteRPCError(rawID(id), mcperr.CodeNoZohoConfigured, "no admin Zoho server configured", map[string]string{
			"end_user_email": email,
			"category":       "no_admin_zoho_configured",
		})
		writeJSONRPC(w, body)
```

Keep the existing `ErrNoZohoConfigured` case below it for the per-user no-match path.

- [ ] **Step 5: Build the whole service**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./...
```

Expected: success. All Task 5/6/7 changes integrate cleanly.

- [ ] **Step 6: Run all service tests**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./... -count=1
```

Expected: PASS. Existing handler tests should still pass — `stubRunner` in `handler_test.go` was built for the previous `ServerRow` shape; it needs the same rename. Update it:

In `apps-microservices/mcp-zoho-service/internal/transport/handler_test.go`, replace every `*db.ServerRow` with `*db.ImportRow` and every `FindAdminZohoServer` method signature with `FindAdminZohoImport(_ context.Context) (*db.ImportRow, error)`. The `stubRunner` in `handler_test.go` must satisfy the new `routing.QueryRunner` interface (3 methods, where `FindAdminZohoImport` takes only `context.Context`).

If the existing `handler_test.go` `stubRunner` had a `FindAdminZohoServer(ctx, selfURL string)` signature, replace with `FindAdminZohoImport(ctx context.Context)` — drop the second arg. Adjust any test setups that pass a `selfURL` argument; remove that arg. The `newServerWith(t, runner stubRunner)` helper sets `routing.NewResolver(runner, fakeDec{}, time.Minute, "stub-id")` — replace the `"http://self/mcp"` string with a stub server ID like `"stub-id"`.

- [ ] **Step 7: Stage + single commit covering Tasks 5–7**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-zoho-service/internal/db/ \
  apps-microservices/mcp-zoho-service/internal/config/ \
  apps-microservices/mcp-zoho-service/internal/routing/ \
  apps-microservices/mcp-zoho-service/internal/transport/handler.go \
  apps-microservices/mcp-zoho-service/internal/transport/handler_test.go \
  apps-microservices/mcp-zoho-service/cmd/server/main.go
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): swap routing to zoho_imports table

Service queries the new zoho_imports table instead of mcp_servers.
IsAdminGranted now reads server_authorizations against the gateway's
stub server ID (required env ZOHO_STUB_SERVER_ID). New sentinel
ErrNoAdminZohoConfigured surfaces when an admin-granted caller has
no admin row available (JSON-RPC -32001 with category
"no_admin_zoho_configured"). ImportRow replaces ServerRow.

EN: Bascule du routage de mcp-zoho-service vers la table zoho_imports;
nouvel ID stub côté config et nouveau sentinel d'erreur pour les admins
sans ligne configurée.
EOF
)"
```

---

## Task 8: Compose + env wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example` (if present in the repo; skip otherwise)

- [ ] **Step 1: Add `ZOHO_STUB_SERVER_ID` to the service block**

In `docker-compose.yml`, find the `mcp-zoho-service:` block (search for `mcp-zoho-service:`). Add a new env entry under `environment:`, alongside `ZOHO_SELF_URL`:

```yaml
      - ZOHO_STUB_SERVER_ID=${ZOHO_STUB_SERVER_ID}
```

- [ ] **Step 2: Document in `.env.example` if it exists**

```bash
ls /home/sandratra/RAG-HP-PUB/.env.example 2>/dev/null
```

If the file exists, append:

```
# Captured from the gateway after step 4 of the zoho_imports rollout
# (SELECT id FROM mcp_servers WHERE tool_prefix='zoho' AND template_slug='').
ZOHO_STUB_SERVER_ID=
```

If `.env.example` doesn't exist, skip this step — the env var will live in operator runbooks only.

- [ ] **Step 3: Validate**

```bash
cd /home/sandratra/RAG-HP-PUB && docker compose config -q
```

Expected: no error output (the env var is empty in dev; that's fine for compose parse but service boot will fail until the operator fills it).

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add docker-compose.yml
# Add .env.example if you touched it:
# git add .env.example
git commit -m "$(cat <<'EOF'
chore(infra): wire ZOHO_STUB_SERVER_ID into mcp-zoho-service compose

Service now requires ZOHO_STUB_SERVER_ID (UUID of the gateway's
mcp_servers row whose URL points at this service). Boot fails fast
when empty; operator fills it after registering the stub row.

EN: Ajoute la variable ZOHO_STUB_SERVER_ID au bloc compose du service
mcp-zoho-service.
EOF
)"
```

---

## Task 9: CLAUDE.md updates + rollout runbook

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`
- Modify: `apps-microservices/mcp-zoho-service/CLAUDE.md`

- [ ] **Step 1: Gateway CLAUDE.md — add `zoho_imports` to the Database section**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`, locate the database table list. Add a new row:

```markdown
| `zoho_imports` | Per-user (and admin singleton) Zoho upstream URLs consumed by mcp-zoho-service for routing |
```

In the same file, find the Conventions bullet referencing the Zoho filter / `X-Zoho-Allowed-User`. Append a sentence:

```
The per-user Zoho upstream URLs now live in the dedicated `zoho_imports` table (managed by the sheet-import handler and the admin endpoint `POST /api/v1/zoho-imports/admin`); `mcp_servers` keeps only the stub row pointing at `mcp-zoho-service`.
```

Locate the Environment Variables table. The two new variables that ALREADY landed in a prior commit (`ZOHO_INTERNAL_URL` + `ZOHO_ADMIN_TOKEN`) should already be listed. Add a new row:

```
| `ZOHO_STUB_SERVER_ID` | — | UUID of the gateway's `mcp_servers` row whose URL points at `mcp-zoho-service`. Captured by the operator and pasted into `.env`; required by the service to gate admin grants. |
```

In the API endpoints section, add a row for the new admin REST:

```markdown
- `GET/POST/DELETE /api/v1/zoho-imports/admin` — manage the singleton admin Zoho row consumed by `mcp-zoho-service`. POST upserts (201 on create, 200 on update); GET returns the row with `auth_headers` keys redacted; DELETE clears.
```

- [ ] **Step 2: Service CLAUDE.md — update Environment table + resolution rules**

In `apps-microservices/mcp-zoho-service/CLAUDE.md`:

(a) The Environment table currently lists `ZOHO_SELF_URL`. Add a new required row:

```
| `ZOHO_STUB_SERVER_ID` | — | UUID of the gateway's `mcp_servers` stub row (the one whose URL points at this service). Required at boot; used by `IsAdminGranted` against `server_authorizations`. |
```

(b) Update the "Resolution rules" section. Replace it with:

```markdown
## Resolution rules

1. Read `X-End-User-Email` + `X-End-User-Login` from request headers.
2. Check `server_authorizations` for the gateway's stub server (UUID in `ZOHO_STUB_SERVER_ID`) + caller email. Granted?
3. Granted → `SELECT … FROM zoho_imports WHERE is_admin = 1 AND is_active = 1 LIMIT 1`. Hit → admin row's URL + decrypted headers. Miss → JSON-RPC `-32001` `no_admin_zoho_configured`.
4. Not granted → `SELECT … FROM zoho_imports WHERE is_admin = 0 AND is_active = 1 AND matches(created_by, email, login) ORDER BY created_at ASC LIMIT 1`. Hit → user row. Miss → JSON-RPC `-32001` `no_zoho_configured`.

Matching tries exact-email (case-insensitive) first, then login-portion (local-part before `@`).
```

(c) Add a "Rollout" section at the end documenting the 6-step rollout (paste the rollout block from the spec verbatim — see `docs/superpowers/specs/2026-05-13-zoho-imports-table-design.md` § "Operational rollout").

- [ ] **Step 3: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-service/CLAUDE.md \
  apps-microservices/mcp-zoho-service/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document zoho_imports table and rollout

Gateway CLAUDE.md gains a row in the Database section, the admin REST
endpoint, the ZOHO_STUB_SERVER_ID env var, and a sentence under the
Zoho convention bullet. Service CLAUDE.md replaces the old resolution
rules with the new zoho_imports SELECT path, adds the new env, and
includes the 6-step operator rollout.

EN: Met à jour les CLAUDE.md du gateway et du service mcp-zoho-service
pour documenter la nouvelle table zoho_imports et son déploiement.
EOF
)"
```

---

## Task 10: Final verification + push (USER OK GATED)

- [ ] **Step 1: Full backend build + tests (both services)**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./... && go test ./... -count=1
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./... && go test ./... -count=1
```

Expected: both green.

- [ ] **Step 2: Compose validation**

```bash
cd /home/sandratra/RAG-HP-PUB && docker compose config -q
```

Expected: no error.

- [ ] **Step 3: Confirm spec coverage**

Re-read `docs/superpowers/specs/2026-05-13-zoho-imports-table-design.md`. Walk through the Validation rules table and the Tests section — confirm each item maps to a task.

| Spec item | Task |
|---|---|
| Schema (zoho_imports columns + indexes) | Task 1 |
| Admin singleton repo | Task 2 |
| Admin REST endpoints (POST/GET/DELETE) | Task 3 |
| Sheet-import dispatch | Task 4 |
| Service queries on new table | Task 5 |
| `ZOHO_STUB_SERVER_ID` required env | Task 6 |
| New sentinel `ErrNoAdminZohoConfigured` + resolver swap | Task 7 |
| Compose env wiring | Task 8 |
| CLAUDE.md updates + rollout | Task 9 |

- [ ] **Step 4: STOP — do NOT push**

Push + PR are gated behind explicit user confirmation. Report status as ready-to-push.

If the user approves:

```bash
cd /home/sandratra/RAG-HP-PUB && git push -u origin features/poc
gh pr create --title "feat: zoho_imports table + per-user routing rewire" --body "$(cat <<'EOF'
## Summary
- New `zoho_imports` table backs per-user and admin Zoho upstream routing.
- Sheet-import handler dispatches Zoho-prefixed templates (`^zoho(-.*)?$` slug match) to the new table instead of `mcp_servers`.
- Admin REST: `POST/GET/DELETE /api/v1/zoho-imports/admin` manages the singleton admin row.
- Service swaps its queries to `zoho_imports` and requires `ZOHO_STUB_SERVER_ID` (the UUID of the gateway's stub mcp_servers row) to gate admin grants.
- `mcp_servers` keeps only the stub Zoho row (URL points at `mcp-zoho-service`).

Spec: `docs/superpowers/specs/2026-05-13-zoho-imports-table-design.md`
Plan: `docs/superpowers/plans/2026-05-13-zoho-imports-table.md`

## Rollout (operator action required after merge)
1. Deploy (AutoMigrate creates the table).
2. SQL: `DELETE FROM mcp_servers WHERE LOWER(tool_prefix) LIKE 'zoho%' AND template_slug <> '';`
3. Register the admin Zoho via `POST /api/v1/zoho-imports/admin`.
4. Capture the stub row UUID into `.env` as `ZOHO_STUB_SERVER_ID`; restart `mcp-zoho-service`.
5. Re-run the `/templates` sheet-import for per-user Zoho rows.
6. Smoke-test end-user routing.

## Test plan
- [x] `go test ./...` in `mcp-gateway-service` (new repo + handler + helper tests)
- [x] `go test ./...` in `mcp-zoho-service` (resolver + new sentinel test)
- [x] `docker compose config -q`
- [x] Manual: admin grant + admin row → routes to admin URL
- [x] Manual: admin grant + no admin row → JSON-RPC -32001 `no_admin_zoho_configured`
- [x] Manual: per-user import → routes to user URL
- [x] Manual: no match → JSON-RPC -32001 `no_zoho_configured`
EOF
)"
```

---

## Self-review

1. **Spec coverage**
   - Schema with all columns + indexes → Task 1. ✓
   - Singleton-admin constraint enforced in repo + admin endpoint → Tasks 2 + 3. ✓
   - Sheet-import dispatch by slug → Task 4. ✓
   - Service queries swap → Task 5. ✓
   - `ZOHO_STUB_SERVER_ID` required env + fail-fast boot → Task 6. ✓
   - Resolver swap + new sentinel → Task 7. ✓
   - Compose wiring → Task 8. ✓
   - CLAUDE.md updates including 6-step rollout → Task 9. ✓
   - Wipe SQL documented in rollout (Task 9 + PR body Task 10). ✓
   - JSON-RPC error categories (`no_admin_zoho_configured`, `no_zoho_configured`, `upstream_error`, `upstream_timeout`) → Task 7 (sentinels) + existing handler error mapping. ✓

2. **Placeholder scan**
   - No TODO/TBD/"fill in details" lines.
   - One spot reads "search to find it" — Task 3 Step 1, the Handler struct file. Acceptable because the search command is concrete (`grep -n "type Handler struct"`) and the action is clear. Not a placeholder.

3. **Type consistency**
   - `db.ZohoImport` (gateway GORM) vs `db.ImportRow` (service narrow projection): two distinct types in two distinct modules — intentional. Spec mentions both. ✓
   - `routing.QueryRunner` methods consistent across Tasks 5, 7. ✓
   - `routing.NewResolver(q, dec, ttl, stubServerID)` signature consistent across Tasks 7 + the existing handler tests after rename. ✓
   - Error sentinels (`ErrNoZohoConfigured`, `ErrNoAdminZohoConfigured`, `ErrMisconfigured`, `ErrInvalidIdentity`) all defined in Task 7 and consumed in Task 7's transport update. ✓
   - HTTP status codes: 201 on first POST, 200 on update, 204 on DELETE, 404 on missing GET — consistent across handler + tests. ✓
   - JSON-RPC error code `-32001` (`CodeNoZohoConfigured`) used for both no-admin-row and no-user-row cases; differentiated by the `category` field in `data`. ✓

No gaps found.
