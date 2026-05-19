# Zoho Imports List View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a management view for `zoho_imports` under `/templates/zoho-crm` with Admin / Utilisateurs tabs, per-row actions (Edit, Toggle, Delete, Test) and four new REST endpoints backing them.

**Architecture:** Extend the existing `TemplateDetailView` with a Zoho branch. Backend adds list/patch/delete/test endpoints on `/api/v1/zoho-imports[/{id}[/test]]`. Frontend adds a Pinia store + API client + four small components composed into one `ZohoImportsSection`. Test endpoint server-side issues `POST tools/list` to the upstream Zoho URL with decrypted headers, returning latency + status.

**Tech Stack:** Go 1.24 + GORM v1.25 (backend), Vue 3 + TypeScript + Pinia (frontend), `net/http` (proxy), AES-256-GCM (existing).

**Spec:** `docs/superpowers/specs/2026-05-13-zoho-imports-list-view-design.md`.

---

## File Structure

```
apps-microservices/mcp-gateway-service/
├── internal/repository/
│   ├── zoho_import_repo.go            # +List, GetByID, Update, DeleteByID
│   └── zoho_import_repo_test.go       # +4 tests
├── internal/api/
│   ├── zoho_admin_dto.go              # +ZohoImportRowDTO, ZohoImportListResponse, ZohoImportUpdateRequest, ZohoImportTestResponse
│   ├── zoho_admin_handlers.go         # +list, getByID, patch, delete, test handlers
│   ├── zoho_admin_handlers_test.go    # +12 tests
│   └── handler.go                     # register 3 new routes + extend isAdminOnly
└── CLAUDE.md                          # +endpoint table rows

apps-microservices/mcp-gateway-frontend/
├── src/types/
│   └── zoho.ts                        # NEW: DTOs mirror
├── src/api/
│   └── zohoImports.ts                 # NEW: list/get/patch/delete/test/admin
├── src/stores/
│   └── zohoImports.ts                 # NEW: Pinia store
├── src/components/zoho/
│   ├── ZohoImportsSection.vue         # NEW: tab orchestrator
│   ├── ZohoAdminCard.vue              # NEW
│   ├── ZohoUserList.vue               # NEW
│   ├── ZohoImportEditModal.vue        # NEW
│   └── ZohoTestResultBadge.vue        # NEW
├── src/views/
│   ├── TemplatesView.vue              # MODIFY: drop Zoho redirect to GoogleSheetsImportView
│   └── TemplateDetailView.vue         # MODIFY: conditional Zoho branch
```

---

## Conventions

- Go: `go test ./internal/... -count=1` from `apps-microservices/mcp-gateway-service`.
- Frontend: `npm run type-check && npm run build` from `apps-microservices/mcp-gateway-frontend`.
- Commits: bilingual EN+FR, Conventional Commits, subject < 72 chars.
- Surgical edits only.

---

## Task 1: Backend repo — List, GetByID, Update, DeleteByID (TDD)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo_test.go`

The existing repo already has `CreateUserImport`, `UpdateOrCreateAdmin`, `GetAdmin`, `DeleteAdmin`, `FindUserImportByEmail`. Add four new methods.

- [ ] **Step 1: Append failing tests**

At the bottom of `zoho_import_repo_test.go`, append:

```go
func TestZohoImportRepo_List_PaginatesAndFilters(t *testing.T) {
	gormDB := newZohoImportTestDB(t)
	repo := NewZohoImportRepo(gormDB)

	// Seed: 1 admin + 3 users
	if _, err := repo.UpdateOrCreateAdmin(&db.ZohoImport{Name: "admin", URL: "https://admin"}); err != nil {
		t.Fatalf("seed admin: %v", err)
	}
	for i, e := range []string{"alice@hp.fr", "bob@hp.fr", "carol@hp.fr"} {
		if err := repo.CreateUserImport(&db.ZohoImport{
			Name: fmt.Sprintf("u%d", i), URL: "https://u", CreatedBy: e, TemplateSlug: "zoho-crm",
		}); err != nil {
			t.Fatalf("seed user %d: %v", i, err)
		}
	}

	// All rows, page 1 limit 10
	rows, total, err := repo.List(ZohoListFilter{}, 1, 10)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 4 || len(rows) != 4 {
		t.Fatalf("List all: total=%d len=%d, want 4/4", total, len(rows))
	}

	// Filter admin only
	adminBool := true
	rows, total, err = repo.List(ZohoListFilter{IsAdmin: &adminBool}, 1, 10)
	if err != nil {
		t.Fatalf("List admin: %v", err)
	}
	if total != 1 || !rows[0].IsAdmin {
		t.Fatalf("admin filter: total=%d row.IsAdmin=%v", total, rows[0].IsAdmin)
	}

	// Filter users only
	userBool := false
	_, total, err = repo.List(ZohoListFilter{IsAdmin: &userBool}, 1, 10)
	if err != nil {
		t.Fatalf("List users: %v", err)
	}
	if total != 3 {
		t.Fatalf("users filter: total=%d, want 3", total)
	}

	// Pagination: limit 2 page 2
	rows, total, err = repo.List(ZohoListFilter{}, 2, 2)
	if err != nil {
		t.Fatalf("List page2: %v", err)
	}
	if total != 4 || len(rows) != 2 {
		t.Fatalf("page 2: total=%d len=%d", total, len(rows))
	}

	// Search by created_by
	rows, total, err = repo.List(ZohoListFilter{Search: "alice"}, 1, 10)
	if err != nil {
		t.Fatalf("List search: %v", err)
	}
	if total != 1 || rows[0].CreatedBy != "alice@hp.fr" {
		t.Fatalf("search: total=%d row.CreatedBy=%q", total, rows[0].CreatedBy)
	}
}

func TestZohoImportRepo_GetByID(t *testing.T) {
	gormDB := newZohoImportTestDB(t)
	repo := NewZohoImportRepo(gormDB)

	in := &db.ZohoImport{Name: "x", URL: "https://x", CreatedBy: "alice@hp.fr", TemplateSlug: "zoho-crm"}
	if err := repo.CreateUserImport(in); err != nil {
		t.Fatalf("create: %v", err)
	}

	got, err := repo.GetByID(in.ID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if got == nil || got.URL != "https://x" {
		t.Fatalf("got = %+v", got)
	}

	missing, err := repo.GetByID("does-not-exist")
	if err != nil {
		t.Fatalf("GetByID missing: %v", err)
	}
	if missing != nil {
		t.Fatalf("expected nil, got %+v", missing)
	}
}

func TestZohoImportRepo_Update(t *testing.T) {
	gormDB := newZohoImportTestDB(t)
	repo := NewZohoImportRepo(gormDB)

	in := &db.ZohoImport{Name: "old", URL: "https://old", CreatedBy: "alice@hp.fr", TemplateSlug: "zoho-crm"}
	if err := repo.CreateUserImport(in); err != nil {
		t.Fatalf("create: %v", err)
	}

	// Update name + url, leave is_active alone
	newName := "new"
	newURL := "https://new"
	newHeaders := []byte{0xAA, 0xBB}
	patch := ZohoUpdatePatch{Name: &newName, URL: &newURL, AuthHeaders: &newHeaders}
	updated, err := repo.Update(in.ID, patch)
	if err != nil {
		t.Fatalf("Update: %v", err)
	}
	if updated.Name != "new" || updated.URL != "https://new" || !bytes.Equal(updated.AuthHeaders, newHeaders) {
		t.Fatalf("updated = %+v", updated)
	}

	// Toggle is_active off
	off := false
	updated, err = repo.Update(in.ID, ZohoUpdatePatch{IsActive: &off})
	if err != nil {
		t.Fatalf("toggle: %v", err)
	}
	if updated.IsActive {
		t.Fatalf("expected is_active=false")
	}

	// Clear auth_headers with explicit nil-slice patch
	empty := []byte{}
	updated, err = repo.Update(in.ID, ZohoUpdatePatch{AuthHeaders: &empty})
	if err != nil {
		t.Fatalf("clear: %v", err)
	}
	if len(updated.AuthHeaders) != 0 {
		t.Fatalf("expected empty auth_headers, got %v", updated.AuthHeaders)
	}

	// Update missing row → ErrZohoImportNotFound
	_, err = repo.Update("missing", ZohoUpdatePatch{Name: &newName})
	if !errors.Is(err, ErrZohoImportNotFound) {
		t.Fatalf("err = %v, want ErrZohoImportNotFound", err)
	}
}

func TestZohoImportRepo_DeleteByID(t *testing.T) {
	gormDB := newZohoImportTestDB(t)
	repo := NewZohoImportRepo(gormDB)

	in := &db.ZohoImport{Name: "x", URL: "https://x", CreatedBy: "alice@hp.fr", TemplateSlug: "zoho-crm"}
	if err := repo.CreateUserImport(in); err != nil {
		t.Fatalf("create: %v", err)
	}

	if err := repo.DeleteByID(in.ID); err != nil {
		t.Fatalf("DeleteByID: %v", err)
	}
	got, _ := repo.GetByID(in.ID)
	if got != nil {
		t.Fatalf("expected nil after delete, got %+v", got)
	}

	// Idempotent: deleting missing → ErrZohoImportNotFound
	if err := repo.DeleteByID("missing"); !errors.Is(err, ErrZohoImportNotFound) {
		t.Fatalf("err = %v, want ErrZohoImportNotFound", err)
	}
}
```

Add the missing imports at the top of the test file (after the existing imports):

```go
import (
	"bytes"
	"errors"
	"fmt"
)
```

- [ ] **Step 2: Run, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/repository/ -run TestZohoImportRepo -v
```

Expected: `undefined: ZohoListFilter`, `undefined: ZohoUpdatePatch`, `undefined: ErrZohoImportNotFound`, plus undefined method errors.

- [ ] **Step 3: Implement the new repo methods**

Append to `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo.go`:

```go
// ErrZohoImportNotFound is returned by Update and DeleteByID when the target
// row does not exist.
var ErrZohoImportNotFound = errors.New("zoho_import not found")

// ZohoListFilter narrows the List query. Each field is independently
// optional: nil filters are dropped at the SQL layer.
type ZohoListFilter struct {
	IsAdmin *bool   // nil = both
	Search  string  // matches name or created_by, case-insensitive substring
}

// ZohoUpdatePatch is the bag of optionally-set fields for Update. A nil pointer
// means "do not touch this column"; a non-nil pointer (even if pointing at an
// empty value) means "write this value, including clearing slices".
type ZohoUpdatePatch struct {
	Name        *string
	URL         *string
	AuthHeaders *[]byte
	IsActive    *bool
}

// List returns rows matching filter, paginated by page (1-indexed) and limit.
// Returns the total matching count alongside the page slice for UI pagination.
// limit is clamped to [1, 100]; page to >= 1.
func (r *ZohoImportRepo) List(filter ZohoListFilter, page, limit int) ([]db.ZohoImport, int64, error) {
	if page < 1 {
		page = 1
	}
	if limit < 1 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}

	tx := r.db.Model(&db.ZohoImport{})
	if filter.IsAdmin != nil {
		tx = tx.Where("is_admin = ?", *filter.IsAdmin)
	}
	if s := strings.TrimSpace(filter.Search); s != "" {
		like := "%" + strings.ToLower(s) + "%"
		tx = tx.Where("LOWER(name) LIKE ? OR LOWER(created_by) LIKE ?", like, like)
	}

	var total int64
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, fmt.Errorf("count: %w", err)
	}

	var rows []db.ZohoImport
	if err := tx.Order("created_at DESC").
		Limit(limit).
		Offset((page - 1) * limit).
		Find(&rows).Error; err != nil {
		return nil, 0, fmt.Errorf("find: %w", err)
	}
	return rows, total, nil
}

// GetByID returns (row, nil) when found, (nil, nil) when missing, or (nil, err)
// on DB error. Callers distinguish missing-row by the nil pointer.
func (r *ZohoImportRepo) GetByID(id string) (*db.ZohoImport, error) {
	var out db.ZohoImport
	err := r.db.Where("id = ?", id).First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// Update applies a patch to row id. Each non-nil patch field is written.
// Returns ErrZohoImportNotFound when id doesn't match.
func (r *ZohoImportRepo) Update(id string, patch ZohoUpdatePatch) (*db.ZohoImport, error) {
	row, err := r.GetByID(id)
	if err != nil {
		return nil, err
	}
	if row == nil {
		return nil, ErrZohoImportNotFound
	}
	if patch.Name != nil {
		row.Name = *patch.Name
	}
	if patch.URL != nil {
		row.URL = *patch.URL
	}
	if patch.AuthHeaders != nil {
		// Patching with an empty slice intentionally clears the blob.
		if len(*patch.AuthHeaders) == 0 {
			row.AuthHeaders = nil
		} else {
			row.AuthHeaders = *patch.AuthHeaders
		}
	}
	if patch.IsActive != nil {
		row.IsActive = *patch.IsActive
	}
	row.UpdatedAt = time.Now()
	if err := r.db.Save(row).Error; err != nil {
		return nil, fmt.Errorf("save: %w", err)
	}
	return row, nil
}

// DeleteByID removes row id. Returns ErrZohoImportNotFound when missing.
func (r *ZohoImportRepo) DeleteByID(id string) error {
	res := r.db.Where("id = ?", id).Delete(&db.ZohoImport{})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrZohoImportNotFound
	}
	return nil
}
```

Confirm `"strings"` is already imported (other repo methods use `strings.ToLower`); if not, add it.

- [ ] **Step 4: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/repository/ -run TestZohoImportRepo -v
```

Expected: all 9 tests PASS (5 from the prior plan + 4 new).

- [ ] **Step 5: Full backend suite green**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/repository/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): zoho_imports repo gains List, GetByID, Update, Delete

Adds paginated List with optional is_admin filter and case-insensitive
substring search on name/created_by. GetByID returns nil on miss.
Update applies a ZohoUpdatePatch (each nil pointer skips the field;
non-nil writes including clearing slices). DeleteByID returns
ErrZohoImportNotFound on miss.

EN: Étend le repo zoho_imports avec liste paginée, lookup par ID,
update partiel et suppression idempotente.
EOF
)"
```

---

## Task 2: Backend DTOs

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go`

- [ ] **Step 1: Append the new DTOs**

At the end of `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go`, append:

```go
// ZohoImportRowDTO is the wire shape of a zoho_imports row. auth_headers
// values are redacted to header key names; the encrypted blob is never
// exposed.
type ZohoImportRowDTO struct {
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	URL            string   `json:"url"`
	IsAdmin        bool     `json:"is_admin"`
	IsActive       bool     `json:"is_active"`
	CreatedBy      string   `json:"created_by"`
	TemplateSlug   string   `json:"template_slug"`
	AuthHeaderKeys []string `json:"auth_header_keys"`
	CreatedAt      string   `json:"created_at"`
	UpdatedAt      string   `json:"updated_at"`
}

// ZohoImportListResponse paginates List results.
type ZohoImportListResponse struct {
	Rows  []ZohoImportRowDTO `json:"rows"`
	Total int64              `json:"total"`
	Page  int                `json:"page"`
	Limit int                `json:"limit"`
}

// ZohoImportUpdateRequest is the body of PATCH /api/v1/zoho-imports/{id}.
// Every field is optional. A non-nil AuthHeaders pointer to an empty map
// clears the encrypted blob; omitting the field entirely leaves it alone.
type ZohoImportUpdateRequest struct {
	Name        *string            `json:"name,omitempty"`
	URL         *string            `json:"url,omitempty"`
	AuthHeaders *map[string]string `json:"auth_headers,omitempty"`
	IsActive    *bool              `json:"is_active,omitempty"`
}

// ZohoImportTestResponse is the result of POST /api/v1/zoho-imports/{id}/test.
type ZohoImportTestResponse struct {
	OK         bool   `json:"ok"`
	StatusCode int    `json:"status_code,omitempty"`
	LatencyMs  int64  `json:"latency_ms"`
	Error      string `json:"error,omitempty"`
}
```

- [ ] **Step 2: Build**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success.

- [ ] **Step 3: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): DTOs for zoho_imports list, update, test

Adds ZohoImportRowDTO (auth_headers redacted to key names),
ZohoImportListResponse (paginated wrapper), ZohoImportUpdateRequest
(every field optional; nil-pointer-to-empty-map clears blob),
ZohoImportTestResponse (ok + latency + optional status_code/error).

EN: DTOs pour la liste paginée, la mise à jour partielle et le test
upstream du proxy Zoho.
EOF
)"
```

---

## Task 3: Backend list + getByID handlers (TDD)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/handler.go`

- [ ] **Step 1: Append failing tests**

At the bottom of `zoho_admin_handlers_test.go`, append:

```go
func TestZohoImports_List_RedactsAuthHeaders(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	// Seed via existing admin endpoint (encrypts auth_headers for us)
	body, _ := json.Marshal(ZohoAdminCreateRequest{
		Name:        "admin",
		URL:         "https://admin",
		AuthHeaders: map[string]string{"Authorization": "Bearer admin", "X-Custom": "v"},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("seed admin: %d", rec.Code)
	}

	req = httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports", nil)
	rec = httptest.NewRecorder()
	h.handleZohoImports(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list: %d body=%s", rec.Code, rec.Body.String())
	}
	var out ZohoImportListResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.Total != 1 || len(out.Rows) != 1 {
		t.Fatalf("total=%d len=%d", out.Total, len(out.Rows))
	}
	got := out.Rows[0]
	if got.URL != "https://admin" {
		t.Fatalf("URL = %q", got.URL)
	}
	// Auth header keys exposed; values must NOT appear in JSON.
	keys := got.AuthHeaderKeys
	if len(keys) != 2 {
		t.Fatalf("AuthHeaderKeys len = %d, want 2", len(keys))
	}
	raw := rec.Body.String()
	if strings.Contains(raw, "Bearer admin") {
		t.Fatalf("Bearer admin leaked: %s", raw)
	}
}

func TestZohoImports_List_FiltersIsAdmin(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	// Admin
	body, _ := json.Marshal(ZohoAdminCreateRequest{Name: "admin", URL: "https://admin"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	// User
	if err := h.zohoImportRepo.CreateUserImport(&db.ZohoImport{
		Name: "alice", URL: "https://alice", CreatedBy: "alice@hp.fr", TemplateSlug: "zoho-crm",
	}); err != nil {
		t.Fatalf("seed user: %v", err)
	}

	req = httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports?is_admin=true", nil)
	rec = httptest.NewRecorder()
	h.handleZohoImports(rec, req)
	var out ZohoImportListResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.Total != 1 || !out.Rows[0].IsAdmin {
		t.Fatalf("admin filter: total=%d row.IsAdmin=%v", out.Total, out.Rows[0].IsAdmin)
	}

	req = httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports?is_admin=false", nil)
	rec = httptest.NewRecorder()
	h.handleZohoImports(rec, req)
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.Total != 1 || out.Rows[0].IsAdmin {
		t.Fatalf("user filter: total=%d row.IsAdmin=%v", out.Total, out.Rows[0].IsAdmin)
	}
}

func TestZohoImports_GetByID_404(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/missing-id", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rec.Code)
	}
}
```

- [ ] **Step 2: Run, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run "TestZohoImports_(List|GetByID)" -v
```

Expected: `undefined: handleZohoImports`, `undefined: handleZohoImportByID`.

- [ ] **Step 3: Implement handlers**

Append to `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`:

```go
// handleZohoImports dispatches GET /api/v1/zoho-imports.
// Verb fan-out: PATCH/DELETE go to /api/v1/zoho-imports/{id} via
// handleZohoImportByID; this handler covers the collection path only.
func (h *Handler) handleZohoImports(w http.ResponseWriter, r *http.Request) {
	if h.zohoImportRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "zoho imports not configured"})
		return
	}
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}

	filter := repository.ZohoListFilter{Search: r.URL.Query().Get("search")}
	if isAdminParam := r.URL.Query().Get("is_admin"); isAdminParam != "" {
		val := isAdminParam == "true" || isAdminParam == "1"
		filter.IsAdmin = &val
	}
	page := parsePositiveInt(r.URL.Query().Get("page"), 1)
	limit := parsePositiveInt(r.URL.Query().Get("limit"), 20)

	rows, total, err := h.zohoImportRepo.List(filter, page, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	out := ZohoImportListResponse{
		Rows:  make([]ZohoImportRowDTO, 0, len(rows)),
		Total: total,
		Page:  page,
		Limit: limit,
	}
	for i := range rows {
		out.Rows = append(out.Rows, zohoImportToRowDTO(&rows[i], h))
	}
	writeJSON(w, http.StatusOK, out)
}

// handleZohoImportByID dispatches GET/PATCH/DELETE on /api/v1/zoho-imports/{id}
// and POST on /api/v1/zoho-imports/{id}/test (delegated to handleZohoImportTest).
func (h *Handler) handleZohoImportByID(w http.ResponseWriter, r *http.Request) {
	if h.zohoImportRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "zoho imports not configured"})
		return
	}

	id, rest := splitZohoImportPath(r.URL.Path)
	if id == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing zoho import id"})
		return
	}

	if rest == "test" {
		h.handleZohoImportTest(w, r, id)
		return
	}
	if rest != "" {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "unknown subroute"})
		return
	}

	switch r.Method {
	case http.MethodGet:
		row, err := h.zohoImportRepo.GetByID(id)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
			return
		}
		if row == nil {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			return
		}
		writeJSON(w, http.StatusOK, zohoImportToRowDTO(row, h))
	case http.MethodPatch:
		h.handleZohoImportPatch(w, r, id)
	case http.MethodDelete:
		h.handleZohoImportDelete(w, r, id)
	default:
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

// splitZohoImportPath parses "/api/v1/zoho-imports/{id}" or
// "/api/v1/zoho-imports/{id}/test" and returns (id, subroute).
// Returns ("", "") when the path doesn't match.
func splitZohoImportPath(p string) (string, string) {
	const prefix = "/api/v1/zoho-imports/"
	if !strings.HasPrefix(p, prefix) {
		return "", ""
	}
	rest := strings.TrimPrefix(p, prefix)
	parts := strings.SplitN(rest, "/", 2)
	if len(parts) == 1 {
		return parts[0], ""
	}
	return parts[0], parts[1]
}

// parsePositiveInt returns def when the input is empty, unparseable, or < 1.
func parsePositiveInt(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 {
		return def
	}
	return n
}

// zohoImportToRowDTO renders a row into the wire shape, decrypting auth_headers
// only to extract key names (values redacted).
func zohoImportToRowDTO(row *db.ZohoImport, h *Handler) ZohoImportRowDTO {
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
	return ZohoImportRowDTO{
		ID:             row.ID,
		Name:           row.Name,
		URL:            row.URL,
		IsAdmin:        row.IsAdmin,
		IsActive:       row.IsActive,
		CreatedBy:      row.CreatedBy,
		TemplateSlug:   row.TemplateSlug,
		AuthHeaderKeys: keys,
		CreatedAt:      row.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:      row.UpdatedAt.UTC().Format(time.RFC3339),
	}
}

// handleZohoImportPatch / handleZohoImportDelete / handleZohoImportTest are
// implemented in Tasks 4 and 5; declare stubs so the file compiles. Replace
// with real implementations in those tasks.
func (h *Handler) handleZohoImportPatch(w http.ResponseWriter, _ *http.Request, _ string) {
	writeJSON(w, http.StatusNotImplemented, ErrorResponse{Error: "patch not implemented yet"})
}
func (h *Handler) handleZohoImportDelete(w http.ResponseWriter, _ *http.Request, _ string) {
	writeJSON(w, http.StatusNotImplemented, ErrorResponse{Error: "delete not implemented yet"})
}
func (h *Handler) handleZohoImportTest(w http.ResponseWriter, _ *http.Request, _ string) {
	writeJSON(w, http.StatusNotImplemented, ErrorResponse{Error: "test not implemented yet"})
}
```

Add the missing imports if absent: `"strconv"`, `"strings"`. The `"github.com/hellopro/mcp-gateway/internal/repository"` import should already be present.

- [ ] **Step 4: Register the two new routes**

In `apps-microservices/mcp-gateway-service/internal/api/handler.go`, locate the existing `/api/v1/zoho-imports/admin` registration. Right next to it, register:

```go
		apiMux.HandleFunc("/api/v1/zoho-imports", h.handleZohoImports)
		apiMux.HandleFunc("/api/v1/zoho-imports/", h.handleZohoImportByID)
```

The trailing-slash variant catches `/api/v1/zoho-imports/{id}` and `/api/v1/zoho-imports/{id}/test`. The `/admin` route still wins because Go's mux matches the more specific pattern first.

Also extend `isAdminOnly` so the new paths require admin: add the prefix to whichever data structure controls admin paths (the existing check for `/api/v1/zoho-imports/admin` is the model — match the same prefix `/api/v1/zoho-imports`).

- [ ] **Step 5: Run, verify list/getByID PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run "TestZohoImports_(List|GetByID)" -v
```

Expected: all 3 sub-tests PASS.

- [ ] **Step 6: Full backend suite green**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go \
  apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go \
  apps-microservices/mcp-gateway-service/internal/api/handler.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): GET /api/v1/zoho-imports list + GET by id

Paginated list with optional ?is_admin and ?search filters. Per-row
GET resolves by id. Both endpoints redact auth_headers values to key
names. PATCH/DELETE/test are stubbed and return 501 — real
implementations land in follow-up commits.

EN: Endpoints REST GET liste paginée et GET par ID pour zoho_imports.
EOF
)"
```

---

## Task 4: Backend PATCH + DELETE handlers (TDD)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`

- [ ] **Step 1: Append failing tests**

```go
func TestZohoImports_Patch_UpdatesFields(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	in := &db.ZohoImport{Name: "old", URL: "https://old", CreatedBy: "alice@hp.fr", TemplateSlug: "zoho-crm"}
	if err := h.zohoImportRepo.CreateUserImport(in); err != nil {
		t.Fatalf("seed: %v", err)
	}

	body, _ := json.Marshal(map[string]any{
		"name":         "new",
		"url":          "https://new",
		"auth_headers": map[string]string{"Authorization": "Bearer x"},
		"is_active":    false,
	})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/zoho-imports/"+in.ID, bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}
	var out ZohoImportRowDTO
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.Name != "new" || out.URL != "https://new" || out.IsActive {
		t.Fatalf("DTO = %+v", out)
	}
	if len(out.AuthHeaderKeys) != 1 || out.AuthHeaderKeys[0] != "Authorization" {
		t.Fatalf("AuthHeaderKeys = %+v", out.AuthHeaderKeys)
	}
}

func TestZohoImports_Patch_ClearsAuthHeaders(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	in := &db.ZohoImport{
		Name: "x", URL: "https://x", CreatedBy: "alice@hp.fr", TemplateSlug: "zoho-crm",
		AuthHeaders: []byte{0xAA},
	}
	if err := h.zohoImportRepo.CreateUserImport(in); err != nil {
		t.Fatalf("seed: %v", err)
	}

	body, _ := json.Marshal(map[string]any{"auth_headers": map[string]string{}})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/zoho-imports/"+in.ID, bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	got, _ := h.zohoImportRepo.GetByID(in.ID)
	if len(got.AuthHeaders) != 0 {
		t.Fatalf("expected cleared auth_headers, got %v", got.AuthHeaders)
	}
}

func TestZohoImports_Patch_EmptyBody400(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	in := &db.ZohoImport{Name: "x", URL: "https://x", CreatedBy: "a@hp.fr", TemplateSlug: "zoho-crm"}
	_ = h.zohoImportRepo.CreateUserImport(in)

	req := httptest.NewRequest(http.MethodPatch, "/api/v1/zoho-imports/"+in.ID, bytes.NewReader([]byte("{}")))
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}

func TestZohoImports_Patch_404(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	body, _ := json.Marshal(map[string]any{"name": "x"})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/zoho-imports/missing-id", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d", rec.Code)
	}
}

func TestZohoImports_Delete_UserRow(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	in := &db.ZohoImport{Name: "x", URL: "https://x", CreatedBy: "a@hp.fr", TemplateSlug: "zoho-crm"}
	if err := h.zohoImportRepo.CreateUserImport(in); err != nil {
		t.Fatalf("seed: %v", err)
	}

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/zoho-imports/"+in.ID, nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d", rec.Code)
	}
	got, _ := h.zohoImportRepo.GetByID(in.ID)
	if got != nil {
		t.Fatalf("expected nil, got %+v", got)
	}
}

func TestZohoImports_Delete_AdminRow400(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	body, _ := json.Marshal(ZohoAdminCreateRequest{Name: "admin", URL: "https://admin"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("seed admin: %d", rec.Code)
	}
	var seeded ZohoAdminResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &seeded)

	req = httptest.NewRequest(http.MethodDelete, "/api/v1/zoho-imports/"+seeded.ID, nil)
	rec = httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "/api/v1/zoho-imports/admin") {
		t.Fatalf("expected redirect message in body, got %s", rec.Body.String())
	}
}
```

- [ ] **Step 2: Run, verify the stubbed handlers return 501 (tests fail)**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run "TestZohoImports_(Patch|Delete)" -v
```

Expected: all six tests fail (501 vs expected status).

- [ ] **Step 3: Replace the stub Patch + Delete handlers**

In `zoho_admin_handlers.go`, replace the two stubs with real implementations:

```go
func (h *Handler) handleZohoImportPatch(w http.ResponseWriter, r *http.Request, id string) {
	var req ZohoImportUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.Name == nil && req.URL == nil && req.AuthHeaders == nil && req.IsActive == nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "no fields to update"})
		return
	}

	patch := repository.ZohoUpdatePatch{
		Name:     req.Name,
		URL:      req.URL,
		IsActive: req.IsActive,
	}
	if req.AuthHeaders != nil {
		var encrypted []byte
		if len(*req.AuthHeaders) > 0 {
			raw, err := json.Marshal(*req.AuthHeaders)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encode auth_headers: " + err.Error()})
				return
			}
			if h.encryptor != nil {
				encrypted, err = h.encryptor.Encrypt(raw)
				if err != nil {
					writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encrypt: " + err.Error()})
					return
				}
			} else {
				encrypted = raw
			}
		} else {
			encrypted = []byte{}
		}
		patch.AuthHeaders = &encrypted
	}

	row, err := h.zohoImportRepo.Update(id, patch)
	if err != nil {
		if errors.Is(err, repository.ErrZohoImportNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, zohoImportToRowDTO(row, h))
}

func (h *Handler) handleZohoImportDelete(w http.ResponseWriter, r *http.Request, id string) {
	// Block deletes against the admin singleton — operators use /admin for that.
	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}
	if row.IsAdmin {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "use /api/v1/zoho-imports/admin to delete the admin row"})
		return
	}

	if err := h.zohoImportRepo.DeleteByID(id); err != nil {
		if errors.Is(err, repository.ErrZohoImportNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
```

Ensure `"errors"` is imported in this file.

- [ ] **Step 4: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run "TestZohoImports_(Patch|Delete)" -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Full backend suite green**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/api/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): PATCH + DELETE on zoho_imports/{id}

PATCH applies a partial update to one row: nil pointers skip fields,
non-nil writes are applied. auth_headers={} clears the encrypted blob.
DELETE removes a per-user row (204). DELETE on the admin singleton
returns 400 with a redirect to /api/v1/zoho-imports/admin.

EN: Endpoints REST PATCH et DELETE sur les lignes individuelles de
zoho_imports avec garde anti-suppression du singleton admin.
EOF
)"
```

---

## Task 5: Backend test endpoint (TDD)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`

- [ ] **Step 1: Append failing tests**

```go
func TestZohoImports_Test_Success(t *testing.T) {
	hits := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","result":{"tools":[]},"id":1}`))
	}))
	defer upstream.Close()

	h := newTestZohoAdminHandler(t)
	in := &db.ZohoImport{
		Name: "x", URL: upstream.URL, CreatedBy: "alice@hp.fr",
		TemplateSlug: "zoho-crm",
	}
	if err := h.zohoImportRepo.CreateUserImport(in); err != nil {
		t.Fatalf("seed: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/"+in.ID+"/test", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}
	var out ZohoImportTestResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if !out.OK {
		t.Fatalf("ok = false, body=%s", rec.Body.String())
	}
	if out.StatusCode != 200 {
		t.Fatalf("status_code = %d", out.StatusCode)
	}
	if out.LatencyMs <= 0 {
		t.Fatalf("latency_ms = %d, want > 0", out.LatencyMs)
	}
	if hits != 1 {
		t.Fatalf("upstream hits = %d", hits)
	}
}

func TestZohoImports_Test_UpstreamError(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer upstream.Close()

	h := newTestZohoAdminHandler(t)
	in := &db.ZohoImport{Name: "x", URL: upstream.URL, CreatedBy: "a@hp.fr", TemplateSlug: "zoho-crm"}
	if err := h.zohoImportRepo.CreateUserImport(in); err != nil {
		t.Fatalf("seed: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/"+in.ID+"/test", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d (should still be 200 with envelope)", rec.Code)
	}
	var out ZohoImportTestResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.OK || out.StatusCode != 502 {
		t.Fatalf("DTO = %+v, want ok=false status=502", out)
	}
}

func TestZohoImports_Test_404(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/missing/test", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rec.Code)
	}
}
```

- [ ] **Step 2: Replace the stub `handleZohoImportTest`**

In `zoho_admin_handlers.go`, replace the stub with:

```go
func (h *Handler) handleZohoImportTest(w http.ResponseWriter, r *http.Request, id string) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}

	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}

	// Decrypt headers (best-effort; missing key → empty headers).
	headers := map[string]string{}
	if len(row.AuthHeaders) > 0 && h.encryptor != nil {
		if pt, derr := h.encryptor.Decrypt(row.AuthHeaders); derr == nil {
			_ = json.Unmarshal(pt, &headers)
		}
	}

	const probeBody = `{"jsonrpc":"2.0","method":"tools/list","id":1}`
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	req, rerr := http.NewRequestWithContext(ctx, http.MethodPost, row.URL, strings.NewReader(probeBody))
	if rerr != nil {
		writeJSON(w, http.StatusOK, ZohoImportTestResponse{OK: false, Error: rerr.Error()})
		return
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	log.Printf("[zoho-imports] test row id=%s by admin", row.ID)

	start := time.Now()
	resp, perr := http.DefaultClient.Do(req)
	latency := time.Since(start).Milliseconds()
	out := ZohoImportTestResponse{LatencyMs: latency}
	if perr != nil {
		out.OK = false
		if errors.Is(perr, context.DeadlineExceeded) {
			out.Error = "timeout"
		} else {
			out.Error = perr.Error()
		}
		writeJSON(w, http.StatusOK, out)
		return
	}
	defer resp.Body.Close()

	out.StatusCode = resp.StatusCode
	out.OK = resp.StatusCode >= 200 && resp.StatusCode < 400
	writeJSON(w, http.StatusOK, out)
}
```

Add the missing imports: `"context"`, `"log"`, `"net/http"`, `"time"`, `"strings"` (most already present from prior tasks).

- [ ] **Step 3: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/api/ -run "TestZohoImports_Test" -v
```

Expected: all 3 tests PASS.

- [ ] **Step 4: Full backend suite green**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/api/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): POST /api/v1/zoho-imports/{id}/test probe endpoint

Server-side issues POST tools/list to the row's upstream URL with
decrypted headers and a 10s timeout. Returns {ok, status_code,
latency_ms, error?}. ok=true when 2xx/3xx. Logs row id + caller email,
never the URL or decrypted headers.

EN: Endpoint REST POST de test qui sonde le serveur Zoho amont d'une
ligne et retourne latence + statut.
EOF
)"
```

---

## Task 6: Frontend types + API client + Pinia store

**Files (all new):**
- Create: `apps-microservices/mcp-gateway-frontend/src/types/zoho.ts`
- Create: `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts`
- Create: `apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.ts`

- [ ] **Step 1: Write the types**

Create `apps-microservices/mcp-gateway-frontend/src/types/zoho.ts`:

```ts
export interface ZohoImportRow {
  id: string
  name: string
  url: string
  is_admin: boolean
  is_active: boolean
  created_by: string
  template_slug: string
  auth_header_keys: string[]
  created_at: string
  updated_at: string
}

export interface ZohoImportListResponse {
  rows: ZohoImportRow[]
  total: number
  page: number
  limit: number
}

export interface ZohoImportUpdateRequest {
  name?: string
  url?: string
  /** Replace the encrypted blob. Pass an empty object to clear. */
  auth_headers?: Record<string, string>
  is_active?: boolean
}

export interface ZohoImportTestResponse {
  ok: boolean
  status_code?: number
  latency_ms: number
  error?: string
}

/** Body of POST /api/v1/zoho-imports/admin. */
export interface ZohoAdminUpsertRequest {
  name: string
  url: string
  auth_headers?: Record<string, string>
}
```

- [ ] **Step 2: Write the API client**

Create `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts`:

```ts
import { api } from './client'
import type {
  ZohoImportRow,
  ZohoImportListResponse,
  ZohoImportUpdateRequest,
  ZohoImportTestResponse,
  ZohoAdminUpsertRequest,
} from '@/types/zoho'

const BASE = '/api/v1/zoho-imports'

export interface ListParams {
  isAdmin?: boolean
  search?: string
  page?: number
  limit?: number
}

export const zohoImportsApi = {
  list(params: ListParams = {}): Promise<ZohoImportListResponse> {
    const qs: Record<string, string> = {}
    if (params.isAdmin !== undefined) qs.is_admin = String(params.isAdmin)
    if (params.search) qs.search = params.search
    if (params.page) qs.page = String(params.page)
    if (params.limit) qs.limit = String(params.limit)
    return api.get<ZohoImportListResponse>(BASE, qs)
  },

  getByID(id: string): Promise<ZohoImportRow> {
    return api.get<ZohoImportRow>(`${BASE}/${encodeURIComponent(id)}`)
  },

  patch(id: string, patch: ZohoImportUpdateRequest): Promise<ZohoImportRow> {
    return api.patch<ZohoImportRow>(`${BASE}/${encodeURIComponent(id)}`, patch)
  },

  remove(id: string): Promise<void> {
    return api.del<void>(`${BASE}/${encodeURIComponent(id)}`)
  },

  test(id: string): Promise<ZohoImportTestResponse> {
    return api.post<ZohoImportTestResponse>(`${BASE}/${encodeURIComponent(id)}/test`, {})
  },

  getAdmin(): Promise<ZohoImportRow | null> {
    return api.get<ZohoImportRow>(`${BASE}/admin`).catch((e) => {
      // 404 → no admin configured
      if (typeof e === 'object' && e !== null && 'status' in e && (e as { status: number }).status === 404) {
        return null as unknown as ZohoImportRow
      }
      throw e
    })
  },

  upsertAdmin(payload: ZohoAdminUpsertRequest): Promise<ZohoImportRow> {
    return api.post<ZohoImportRow>(`${BASE}/admin`, payload)
  },

  deleteAdmin(): Promise<void> {
    return api.del<void>(`${BASE}/admin`)
  },
}
```

If `api.patch` doesn't exist on your client wrapper, add it (mirror `api.post`). Inspect `src/api/client.ts` first:

```bash
grep -n "patch\|post\|del" /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend/src/api/client.ts | head -20
```

If `patch` is missing, append a thin wrapper that uses `method: 'PATCH'`.

- [ ] **Step 3: Write the Pinia store**

Create `apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.ts`:

```ts
import { defineStore } from 'pinia'
import { zohoImportsApi } from '@/api/zohoImports'
import type {
  ZohoImportRow,
  ZohoImportUpdateRequest,
  ZohoImportTestResponse,
  ZohoAdminUpsertRequest,
} from '@/types/zoho'

interface State {
  admin: ZohoImportRow | null
  users: ZohoImportRow[]
  usersTotal: number
  usersPage: number
  usersLimit: number
  usersSearch: string
  isLoading: boolean
  error: string | null
}

export const useZohoImportsStore = defineStore('zohoImports', {
  state: (): State => ({
    admin: null,
    users: [],
    usersTotal: 0,
    usersPage: 1,
    usersLimit: 20,
    usersSearch: '',
    isLoading: false,
    error: null,
  }),
  actions: {
    async fetchAdmin() {
      try {
        this.admin = await zohoImportsApi.getAdmin()
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : 'Erreur de chargement'
      }
    },
    async fetchUsers(params: { page?: number; search?: string } = {}) {
      this.isLoading = true
      this.error = null
      try {
        const page = params.page ?? this.usersPage
        const search = params.search ?? this.usersSearch
        const out = await zohoImportsApi.list({ isAdmin: false, page, search, limit: this.usersLimit })
        this.users = out.rows
        this.usersTotal = out.total
        this.usersPage = out.page
        this.usersLimit = out.limit
        this.usersSearch = search
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : 'Erreur de chargement'
      } finally {
        this.isLoading = false
      }
    },
    async upsertAdmin(payload: ZohoAdminUpsertRequest) {
      this.admin = await zohoImportsApi.upsertAdmin(payload)
    },
    async deleteAdmin() {
      await zohoImportsApi.deleteAdmin()
      this.admin = null
    },
    async updateRow(id: string, patch: ZohoImportUpdateRequest) {
      const row = await zohoImportsApi.patch(id, patch)
      if (row.is_admin) {
        this.admin = row
      } else {
        await this.fetchUsers()
      }
      return row
    },
    async deleteRow(id: string) {
      await zohoImportsApi.remove(id)
      await this.fetchUsers()
    },
    async testRow(id: string): Promise<ZohoImportTestResponse> {
      return zohoImportsApi.test(id)
    },
    async toggleActive(id: string, active: boolean) {
      return this.updateRow(id, { is_active: active })
    },
  },
})
```

- [ ] **Step 4: Typecheck + build**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend && npm run type-check && npm run build
```

Expected: success.

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-frontend/src/types/zoho.ts apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.ts
# Add client.ts if you extended it:
# git add apps-microservices/mcp-gateway-frontend/src/api/client.ts
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): TS types + API client + Pinia store for zoho_imports

Mirrors the new REST surface (list, get, patch, delete, test, admin
upsert/delete). Store keeps admin singleton + paginated users list +
search; refetches users on every mutation.

EN: Types TypeScript, client REST et store Pinia pour la gestion des
imports Zoho.
EOF
)"
```

---

## Task 7: Frontend view + components

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/views/TemplatesView.vue`
- Modify: `apps-microservices/mcp-gateway-frontend/src/views/TemplateDetailView.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportsSection.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoAdminCard.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoUserList.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportEditModal.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoTestResultBadge.vue`

This task introduces a lot of UI. We ship the structural shell here; visual polish is iterative.

- [ ] **Step 1: Update `TemplatesView.vue` routing**

In `templateTarget`, change:

```ts
function templateTarget(template: Template): RouteLocationRaw {
  if (template.kind === 'http_batch') {
    return { name: 'google-sheets-import', query: { from: 'templates', template_slug: template.slug } }
  }
  return { name: 'template-detail', params: { slug: template.slug } }
}
```

to:

```ts
function isZohoSlug(slug: string): boolean {
  return slug === 'zoho' || slug.startsWith('zoho-')
}

function templateTarget(template: Template): RouteLocationRaw {
  if (template.kind === 'http_batch' && !isZohoSlug(template.slug)) {
    return { name: 'google-sheets-import', query: { from: 'templates', template_slug: template.slug } }
  }
  return { name: 'template-detail', params: { slug: template.slug } }
}
```

- [ ] **Step 2: Create `ZohoTestResultBadge.vue`**

```vue
<template>
  <span
    v-if="result"
    :class="[
      'inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 font-medium',
      result.ok
        ? 'bg-success-50 text-success-700 dark:bg-success-500/15 dark:text-success-400'
        : 'bg-error-50 text-error-700 dark:bg-error-500/15 dark:text-error-400',
    ]"
  >
    <i :class="result.ok ? 'pi pi-check-circle' : 'pi pi-times-circle'" />
    <template v-if="result.ok">
      {{ result.status_code ?? '?' }} · {{ result.latency_ms }}ms
    </template>
    <template v-else>
      {{ result.error || result.status_code }} · {{ result.latency_ms }}ms
    </template>
  </span>
</template>

<script setup lang="ts">
import type { ZohoImportTestResponse } from '@/types/zoho'
defineProps<{ result: ZohoImportTestResponse | null }>()
</script>
```

- [ ] **Step 3: Create `ZohoImportEditModal.vue`**

```vue
<template>
  <Dialog :open="open" @update:open="(v) => $emit('update:open', v)">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
      </DialogHeader>
      <form class="space-y-3 mt-2" @submit.prevent="onSubmit">
        <div>
          <label class="block text-xs font-medium mb-1">Nom</label>
          <input v-model="form.name" type="text" class="w-full h-9 text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200" />
        </div>
        <div>
          <label class="block text-xs font-medium mb-1">URL upstream</label>
          <input v-model="form.url" type="url" required class="w-full h-9 text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200" />
        </div>
        <div>
          <label class="block text-xs font-medium mb-1">
            Auth headers (JSON)
            <span class="text-gray-400">— laissez vide pour ne pas modifier</span>
          </label>
          <textarea v-model="form.authHeadersJSON" rows="4" placeholder='{"Authorization":"Bearer ..."}' class="w-full text-xs font-mono rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200"></textarea>
          <p v-if="parseError" class="text-xs text-error-500 mt-1">{{ parseError }}</p>
        </div>
        <div class="flex gap-2 justify-end pt-2">
          <button type="button" class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600" @click="$emit('update:open', false)">Annuler</button>
          <button type="submit" :disabled="submitting" class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600 disabled:opacity-50">{{ submitting ? '...' : 'Enregistrer' }}</button>
        </div>
      </form>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, watch, reactive } from 'vue'
import Dialog from '@/components/ui/Dialog.vue'
import DialogContent from '@/components/ui/DialogContent.vue'
import DialogHeader from '@/components/ui/DialogHeader.vue'
import DialogTitle from '@/components/ui/DialogTitle.vue'
import type { ZohoImportRow, ZohoImportUpdateRequest } from '@/types/zoho'

const props = defineProps<{
  open: boolean
  row: ZohoImportRow | null
  title: string
}>()
const emit = defineEmits<{
  'update:open': [v: boolean]
  submit: [patch: ZohoImportUpdateRequest]
}>()

const form = reactive({
  name: '',
  url: '',
  authHeadersJSON: '',
})
const parseError = ref('')
const submitting = ref(false)

watch(() => props.row, (r) => {
  form.name = r?.name ?? ''
  form.url = r?.url ?? ''
  form.authHeadersJSON = ''
  parseError.value = ''
}, { immediate: true })

function onSubmit() {
  parseError.value = ''
  const patch: ZohoImportUpdateRequest = {}
  if (props.row && form.name !== props.row.name) patch.name = form.name
  if (props.row && form.url !== props.row.url) patch.url = form.url
  if (form.authHeadersJSON.trim()) {
    try {
      const parsed = JSON.parse(form.authHeadersJSON)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        patch.auth_headers = parsed
      } else {
        parseError.value = 'Doit être un objet JSON {"clé":"valeur"}.'
        return
      }
    } catch (e) {
      parseError.value = 'JSON invalide.'
      return
    }
  }
  submitting.value = true
  emit('submit', patch)
  submitting.value = false
}
</script>
```

Note: this file imports `@/components/ui/Dialog.vue` etc. If those components don't exist in this codebase under that path, replace with whatever shared Dialog/Modal primitive the project uses (search with `grep -rn "DialogContent\|ConfirmDialog\|Modal" apps-microservices/mcp-gateway-frontend/src/components/`). The existing `ConfirmDialog.vue` and `RotateCredentialsModal.vue` from the templates feature are good references.

- [ ] **Step 4: Create `ZohoAdminCard.vue`**

```vue
<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5">
    <div v-if="admin" class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ admin.name || 'Compte admin Zoho' }}</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate" :title="admin.url">{{ admin.url }}</p>
        <div class="text-xs text-gray-500 dark:text-gray-400 mt-2 flex gap-3">
          <span>Actif : <strong>{{ admin.is_active ? 'oui' : 'non' }}</strong></span>
          <span>Headers : {{ admin.auth_header_keys.join(', ') || 'aucun' }}</span>
        </div>
      </div>
      <div class="flex gap-2 shrink-0">
        <button class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600" @click="$emit('test')">Tester</button>
        <button class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600" @click="$emit('edit')">Modifier</button>
        <button class="text-xs px-2 py-1 rounded-md border border-error-300 dark:border-error-700 text-error-600" @click="$emit('delete')">Supprimer</button>
      </div>
    </div>
    <ZohoTestResultBadge v-if="testResult" :result="testResult" />
    <div v-if="!admin" class="text-center py-6 text-gray-500 dark:text-gray-400">
      <p class="text-sm mb-3">Aucun compte admin configuré.</p>
      <button class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600" @click="$emit('create')">Configurer le compte admin</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import ZohoTestResultBadge from './ZohoTestResultBadge.vue'
import type { ZohoImportRow, ZohoImportTestResponse } from '@/types/zoho'
defineProps<{
  admin: ZohoImportRow | null
  testResult: ZohoImportTestResponse | null
}>()
defineEmits<{
  edit: []
  test: []
  delete: []
  create: []
}>()
</script>
```

- [ ] **Step 5: Create `ZohoUserList.vue`**

```vue
<template>
  <div>
    <div class="flex items-center gap-3 mb-3">
      <input v-model="searchLocal" type="text" placeholder="Filtrer par email ou nom…" class="h-9 flex-1 max-w-sm text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200" @input="onSearch" />
      <span class="text-xs text-gray-500 dark:text-gray-400">{{ total }} ligne(s)</span>
    </div>
    <div v-if="rows.length === 0" class="text-center py-12 text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-900 rounded-lg border border-dashed border-gray-200 dark:border-gray-800">
      <p class="text-sm">Aucun import utilisateur.</p>
    </div>
    <table v-else class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500 dark:text-gray-400">
          <th class="py-2">Créateur</th>
          <th>Nom</th>
          <th>URL</th>
          <th>Actif</th>
          <th>Headers</th>
          <th class="text-right">Actions</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
        <tr v-for="r in rows" :key="r.id" class="text-sm">
          <td class="py-2 font-mono text-xs">{{ r.created_by }}</td>
          <td>{{ r.name }}</td>
          <td class="font-mono text-xs truncate max-w-[280px]" :title="r.url">{{ r.url }}</td>
          <td>{{ r.is_active ? 'oui' : 'non' }}</td>
          <td class="text-xs">{{ r.auth_header_keys.join(', ') }}</td>
          <td class="text-right">
            <div class="flex justify-end items-center gap-2">
              <ZohoTestResultBadge :result="testResults[r.id] ?? null" />
              <button class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600" @click="$emit('test', r)">Tester</button>
              <button class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600" @click="$emit('toggle', r)">{{ r.is_active ? 'Désactiver' : 'Activer' }}</button>
              <button class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600" @click="$emit('edit', r)">Modifier</button>
              <button class="text-xs px-2 py-1 rounded-md border border-error-300 dark:border-error-700 text-error-600" @click="$emit('delete', r)">Supprimer</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="totalPages > 1" class="flex justify-center items-center gap-2 mt-4 text-sm">
      <button class="px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 disabled:opacity-40" :disabled="page <= 1" @click="$emit('page', page - 1)">Précédent</button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button class="px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 disabled:opacity-40" :disabled="page >= totalPages" @click="$emit('page', page + 1)">Suivant</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import ZohoTestResultBadge from './ZohoTestResultBadge.vue'
import type { ZohoImportRow, ZohoImportTestResponse } from '@/types/zoho'

const props = defineProps<{
  rows: ZohoImportRow[]
  total: number
  page: number
  limit: number
  search: string
  testResults: Record<string, ZohoImportTestResponse>
}>()
defineEmits<{
  search: [v: string]
  page: [n: number]
  edit: [r: ZohoImportRow]
  delete: [r: ZohoImportRow]
  toggle: [r: ZohoImportRow]
  test: [r: ZohoImportRow]
}>()

const searchLocal = ref(props.search)
watch(() => props.search, (v) => { searchLocal.value = v })

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.limit)))

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => emit('search', searchLocal.value), 250)
}
</script>
```

- [ ] **Step 6: Create `ZohoImportsSection.vue`**

```vue
<template>
  <div>
    <div class="flex items-center gap-3 mb-4">
      <button class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600" @click="goToImport">
        Importer depuis Sheets
      </button>
    </div>

    <div class="border-b border-gray-200 dark:border-gray-800 mb-4">
      <nav class="flex gap-4">
        <button :class="tabBtn(activeTab === 'admin')" @click="activeTab = 'admin'">
          Admin ({{ store.admin ? 1 : 0 }})
        </button>
        <button :class="tabBtn(activeTab === 'users')" @click="activeTab = 'users'">
          Utilisateurs ({{ store.usersTotal }})
        </button>
      </nav>
    </div>

    <ZohoAdminCard
      v-if="activeTab === 'admin'"
      :admin="store.admin"
      :test-result="adminTestResult"
      @create="openAdminEdit(true)"
      @edit="openAdminEdit(false)"
      @test="onTestAdmin"
      @delete="onDeleteAdmin"
    />

    <ZohoUserList
      v-else
      :rows="store.users"
      :total="store.usersTotal"
      :page="store.usersPage"
      :limit="store.usersLimit"
      :search="store.usersSearch"
      :test-results="userTestResults"
      @search="onSearchUsers"
      @page="(n) => store.fetchUsers({ page: n })"
      @edit="openUserEdit"
      @delete="onDeleteUser"
      @toggle="onToggleUser"
      @test="onTestUser"
    />

    <ZohoImportEditModal
      :open="editOpen"
      :row="editRow"
      :title="editIsCreate ? 'Configurer le compte admin' : (editRow?.is_admin ? 'Modifier le compte admin' : 'Modifier l\\'import')"
      @update:open="editOpen = $event"
      @submit="onEditSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useZohoImportsStore } from '@/stores/zohoImports'
import { zohoImportsApi } from '@/api/zohoImports'
import ZohoAdminCard from './ZohoAdminCard.vue'
import ZohoUserList from './ZohoUserList.vue'
import ZohoImportEditModal from './ZohoImportEditModal.vue'
import type { ZohoImportRow, ZohoImportTestResponse, ZohoImportUpdateRequest } from '@/types/zoho'

const props = defineProps<{ templateSlug: string }>()

const router = useRouter()
const store = useZohoImportsStore()

const activeTab = ref<'admin' | 'users'>('admin')
const editOpen = ref(false)
const editRow = ref<ZohoImportRow | null>(null)
const editIsCreate = ref(false)
const adminTestResult = ref<ZohoImportTestResponse | null>(null)
const userTestResults = ref<Record<string, ZohoImportTestResponse>>({})

onMounted(() => {
  store.fetchAdmin()
  store.fetchUsers()
})

function tabBtn(active: boolean) {
  return [
    'pb-2 -mb-px text-sm font-medium border-b-2',
    active ? 'border-brand-500 text-brand-500' : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200',
  ]
}

function goToImport() {
  router.push({ name: 'google-sheets-import', query: { from: 'templates', template_slug: props.templateSlug } })
}

function openAdminEdit(isCreate: boolean) {
  editRow.value = store.admin
  editIsCreate.value = isCreate
  editOpen.value = true
}

function openUserEdit(r: ZohoImportRow) {
  editRow.value = r
  editIsCreate.value = false
  editOpen.value = true
}

async function onEditSubmit(patch: ZohoImportUpdateRequest) {
  if (editIsCreate.value) {
    // First admin creation — convert patch into upsert payload.
    await store.upsertAdmin({
      name: patch.name ?? 'Compte admin Zoho',
      url: patch.url ?? '',
      auth_headers: patch.auth_headers,
    })
  } else if (editRow.value) {
    await store.updateRow(editRow.value.id, patch)
  }
  editOpen.value = false
}

async function onDeleteAdmin() {
  if (!confirm('Supprimer le compte admin Zoho ?')) return
  await store.deleteAdmin()
}

async function onDeleteUser(r: ZohoImportRow) {
  if (!confirm(`Supprimer l'import de ${r.created_by} ?`)) return
  await store.deleteRow(r.id)
}

async function onToggleUser(r: ZohoImportRow) {
  await store.toggleActive(r.id, !r.is_active)
}

async function onTestAdmin() {
  if (!store.admin) return
  adminTestResult.value = await store.testRow(store.admin.id)
}

async function onTestUser(r: ZohoImportRow) {
  const res = await store.testRow(r.id)
  userTestResults.value = { ...userTestResults.value, [r.id]: res }
}

function onSearchUsers(s: string) {
  store.fetchUsers({ page: 1, search: s })
}
</script>
```

- [ ] **Step 7: Wire `TemplateDetailView.vue`**

In `apps-microservices/mcp-gateway-frontend/src/views/TemplateDetailView.vue`, add at the top of the script block:

```ts
import ZohoImportsSection from '@/components/zoho/ZohoImportsSection.vue'

function isZohoSlug(slug: string): boolean {
  return slug === 'zoho' || slug.startsWith('zoho-')
}

const isZohoTemplate = computed(() => template.value !== null && isZohoSlug(template.value.slug))
```

(`template` is already a `ref` in the existing script; `computed` is already imported.)

Then in the template body, locate the existing `<!-- Instances section -->` block and wrap the stdio-specific content in a `v-else`:

```vue
      <ZohoImportsSection v-if="isZohoTemplate" :template-slug="template.slug" />

      <!-- Instances section (stdio only) -->
      <section v-else>
        … existing stdio block …
      </section>
```

The `<!-- Required env -->` block above and the delete/rotate/logs modals below are stdio-only — wrap them with `v-if="!isZohoTemplate"` if they assume `instances` etc.

- [ ] **Step 8: Typecheck + build**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend && npm run type-check && npm run build
```

Expected: success.

- [ ] **Step 9: Smoke test (manual)**

1. Visit `/templates`, click the Zoho card. Confirm the URL routes to `/templates/zoho-crm` (not `/servers/import-google`).
2. Confirm the new view loads with two tabs.
3. Click "Configurer le compte admin" → modal opens → fill URL → save → admin tab shows the card.
4. Click "Tester" → green badge appears with latency.
5. Switch to "Utilisateurs" tab → existing imports listed; search box narrows.
6. Click "Modifier" on a row → modal opens with name+url pre-filled.
7. Click "Désactiver" → row toggles.
8. Click "Supprimer" → confirm → row vanishes.
9. Click "Importer depuis Sheets" → opens existing wizard with `template_slug=zoho-crm`.

- [ ] **Step 10: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-frontend/src/views/TemplatesView.vue \
  apps-microservices/mcp-gateway-frontend/src/views/TemplateDetailView.vue \
  apps-microservices/mcp-gateway-frontend/src/components/zoho/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): Zoho imports management view

TemplateDetailView gains a Zoho branch (slug starts with 'zoho'):
two tabs (Admin / Utilisateurs) backed by the new zohoImports store.
Per-row actions: Tester, Modifier, (Dés)activer, Supprimer. Admin
singleton has a dedicated card with the same actions. An "Importer
depuis Sheets" button opens the existing wizard. TemplatesView no
longer redirects Zoho cards directly to the wizard.

EN: Vue de gestion des imports Zoho avec onglets Admin / Utilisateurs,
actions par ligne et bouton d'import.
EOF
)"
```

---

## Task 8: CLAUDE.md + final verification + PR

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Document the new endpoints**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`, locate the Zoho Imports Admin subsection added in the prior plan. Right after the existing `GET/POST/DELETE /api/v1/zoho-imports/admin` bullet, add:

```markdown
- `GET /api/v1/zoho-imports` — paginated list of all Zoho rows (admin + users). Query params: `is_admin=true|false`, `search=<substring on name or created_by>`, `page=N`, `limit=M` (default 1/20, max 100). `auth_headers` are redacted to header key names.
- `GET /api/v1/zoho-imports/{id}` — fetch one row (same DTO shape as list items).
- `PATCH /api/v1/zoho-imports/{id}` — partial update. Body fields all optional: `name`, `url`, `auth_headers` (replaces blob; `{}` clears it), `is_active`. Empty body → 400. `is_admin` and `created_by` are not editable here.
- `DELETE /api/v1/zoho-imports/{id}` — hard delete a per-user row (204). Returns 400 when the target is the singleton admin row (use `/api/v1/zoho-imports/admin` for that).
- `POST /api/v1/zoho-imports/{id}/test` — server-side `POST tools/list` probe against the row's upstream URL with decrypted headers, 10s timeout. Returns `{ok, status_code?, latency_ms, error?}`. Logs only the row ID + caller email (never the URL or headers).
```

- [ ] **Step 2: Run both services' tests one last time**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./... && go test ./... -count=1
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend && npm run type-check && npm run build
```

Expected: all green.

- [ ] **Step 3: Confirm spec coverage**

| Spec item | Task |
|---|---|
| Repo additions (List/GetByID/Update/DeleteByID) | Task 1 |
| DTOs | Task 2 |
| GET list + GET by id | Task 3 |
| PATCH | Task 4 |
| DELETE (with admin-row redirect) | Task 4 |
| Test endpoint | Task 5 |
| Frontend types/API/store | Task 6 |
| TemplatesView routing change | Task 7 |
| TemplateDetailView Zoho branch | Task 7 |
| Admin card + user list + edit modal + test badge | Task 7 |
| CLAUDE.md updates | Task 8 |

- [ ] **Step 4: Commit docs**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(mcp-gateway): document zoho_imports list + per-row endpoints

Lists the five new REST endpoints (GET list, GET by id, PATCH,
DELETE, POST test) in the gateway CLAUDE.md API section.

EN: Documente les cinq nouveaux endpoints REST de gestion des
imports Zoho dans le CLAUDE.md du gateway.
EOF
)"
```

- [ ] **Step 5: STOP — do NOT push**

Push + PR are gated behind explicit user confirmation. Report status as ready-to-push. When the user approves:

```bash
cd /home/sandratra/RAG-HP-PUB && git push -u origin features/poc
gh pr create --title "feat: zoho_imports list view + per-row admin actions" --body "$(cat <<'EOF'
## Summary
- Backend: paginated `GET /api/v1/zoho-imports` + per-row `GET/PATCH/DELETE/{id}` + `POST {id}/test` probe.
- Frontend: `TemplateDetailView` Zoho branch with Admin / Utilisateurs tabs, edit modal, test badge.
- Routing: `/templates` Zoho cards now route to the detail view (not the import wizard).
- All actions are admin-gated by the existing `isAdminOnly` middleware.

Spec: `docs/superpowers/specs/2026-05-13-zoho-imports-list-view-design.md`
Plan: `docs/superpowers/plans/2026-05-13-zoho-imports-list-view.md`

## Test plan
- [x] `go test ./...` in `mcp-gateway-service` (4 repo + 12 handler tests)
- [x] `npm run type-check && npm run build` in `mcp-gateway-frontend`
- [x] Manual: open `/templates/zoho-crm`, run edit/test/toggle/delete cycle.
EOF
)"
```

---

## Self-review

1. **Spec coverage**
   - Every spec section maps to a task per the table in Task 8 Step 3. ✓
   - Tests numbered in the spec (12 backend + frontend smoke) covered across Tasks 1–5 + Task 7 manual smoke.
   - DELETE-on-admin redirect → Task 4.
   - Auth_headers cleared by `{}` semantics → Task 4 test 2.
   - Test endpoint logs only row id + caller email → Task 5 (`log.Printf("[zoho-imports] test row id=%s by admin", row.ID)`).

2. **Placeholder scan**
   - No TODO/TBD/"fill in details".
   - Step 7 Task 7 references `@/components/ui/Dialog.vue` etc. Spec-equivalent: existing `ConfirmDialog.vue` + `RotateCredentialsModal.vue` are the codebase conventions; the implementer is instructed to swap to the project's actual primitive (line included).
   - The CLAUDE.md "Step 1" describes the exact insert point and content — concrete enough.

3. **Type consistency**
   - `ZohoImportRow` shape consistent across types.ts, store, components. ✓
   - `ZohoImportUpdateRequest` mirrors the backend DTO exactly (4 optional fields). ✓
   - `ZohoListFilter`/`ZohoUpdatePatch` Go types consistent across Task 1 (definition) and Tasks 3+4 (consumption). ✓
   - `parsePositiveInt` referenced in handler — defined in same file (Task 3). ✓
   - Routes: collection `/api/v1/zoho-imports` vs item `/api/v1/zoho-imports/` (trailing slash for `/{id}` matching) — both registered in Task 3 Step 4.

No gaps found.
