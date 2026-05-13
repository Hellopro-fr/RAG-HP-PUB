package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

// newZohoAdminTestDB builds an in-memory SQLite DB with the ZohoImport table.
// The gateway's MySQL-typed columns (`datetime(3)`) are not portable to SQLite;
// the table is created via hand-rolled DDL that mirrors the column set.
func newZohoAdminTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gormDB, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := gormDB.Exec(`
		CREATE TABLE zoho_imports (
			id            TEXT PRIMARY KEY,
			name          TEXT NOT NULL DEFAULT '',
			url           TEXT NOT NULL,
			auth_headers  BLOB,
			created_by    TEXT NOT NULL DEFAULT '',
			is_admin      INTEGER NOT NULL DEFAULT 0,
			is_active     INTEGER NOT NULL DEFAULT 1,
			template_slug TEXT NOT NULL DEFAULT '',
			created_at    DATETIME NOT NULL,
			updated_at    DATETIME NOT NULL
		)
	`).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return gormDB
}

func newTestZohoAdminHandler(t *testing.T) *Handler {
	t.Helper()
	gormDB := newZohoAdminTestDB(t)
	enc, err := crypto.NewEncryptor("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	if err != nil {
		t.Fatalf("crypto: %v", err)
	}
	h := &Handler{}
	h.encryptor = enc
	h.SetZohoImportRepo(repository.NewZohoImportRepo(gormDB))
	return h
}

func TestZohoAdmin_PostCreatesThenUpdates(t *testing.T) {
	h := newTestZohoAdminHandler(t)

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

	_ = db.ZohoImport{} // touch import so it doesn't go unused
}

func TestZohoAdmin_GetReturnsAdminOr404(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/admin", nil)
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("GET before create: status = %d, want 404", rec.Code)
	}

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

func TestZohoImports_List_RedactsAuthHeaders(t *testing.T) {
	h := newTestZohoAdminHandler(t)

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
	if len(got.AuthHeaderKeys) != 2 {
		t.Fatalf("AuthHeaderKeys len = %d, want 2", len(got.AuthHeaderKeys))
	}
	raw := rec.Body.String()
	if strings.Contains(raw, "Bearer admin") {
		t.Fatalf("Bearer admin leaked: %s", raw)
	}
}

func TestZohoImports_List_FiltersIsAdmin(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	body, _ := json.Marshal(ZohoAdminCreateRequest{Name: "admin", URL: "https://admin"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/admin", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoAdmin(rec, req)
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
