package repository

import (
	"bytes"
	"errors"
	"fmt"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"mcp-gateway/internal/db"
)

// newZohoImportTestDB opens an in-memory SQLite and creates the zoho_imports
// table using narrow DDL that is portable to SQLite (no datetime(3)).
func newZohoImportTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE zoho_imports (
			id            TEXT PRIMARY KEY,
			name          TEXT NOT NULL DEFAULT '',
			url           TEXT NOT NULL DEFAULT '',
			auth_headers  BLOB,
			created_by    TEXT NOT NULL DEFAULT '',
			is_admin      INTEGER NOT NULL DEFAULT 0,
			is_active     INTEGER NOT NULL DEFAULT 1,
			template_slug TEXT NOT NULL DEFAULT '',
			created_at    datetime,
			updated_at    datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return gdb
}

func TestZohoImportRepo_CreateUserImport(t *testing.T) {
	gormDB := newZohoImportTestDB(t)
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
	gormDB := newZohoImportTestDB(t)
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
	gormDB := newZohoImportTestDB(t)
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
	gormDB := newZohoImportTestDB(t)
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
	gormDB := newZohoImportTestDB(t)
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

func TestZohoImportRepo_List_PaginatesAndFilters(t *testing.T) {
	gormDB := newZohoImportTestDB(t)
	repo := NewZohoImportRepo(gormDB)

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

	rows, total, err := repo.List(ZohoListFilter{}, 1, 10)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 4 || len(rows) != 4 {
		t.Fatalf("List all: total=%d len=%d, want 4/4", total, len(rows))
	}

	adminBool := true
	rows, total, err = repo.List(ZohoListFilter{IsAdmin: &adminBool}, 1, 10)
	if err != nil {
		t.Fatalf("List admin: %v", err)
	}
	if total != 1 || !rows[0].IsAdmin {
		t.Fatalf("admin filter: total=%d row.IsAdmin=%v", total, rows[0].IsAdmin)
	}

	userBool := false
	_, total, err = repo.List(ZohoListFilter{IsAdmin: &userBool}, 1, 10)
	if err != nil {
		t.Fatalf("List users: %v", err)
	}
	if total != 3 {
		t.Fatalf("users filter: total=%d, want 3", total)
	}

	rows, total, err = repo.List(ZohoListFilter{}, 2, 2)
	if err != nil {
		t.Fatalf("List page2: %v", err)
	}
	if total != 4 || len(rows) != 2 {
		t.Fatalf("page 2: total=%d len=%d", total, len(rows))
	}

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

	off := false
	updated, err = repo.Update(in.ID, ZohoUpdatePatch{IsActive: &off})
	if err != nil {
		t.Fatalf("toggle: %v", err)
	}
	if updated.IsActive {
		t.Fatalf("expected is_active=false")
	}

	empty := []byte{}
	updated, err = repo.Update(in.ID, ZohoUpdatePatch{AuthHeaders: &empty})
	if err != nil {
		t.Fatalf("clear: %v", err)
	}
	if len(updated.AuthHeaders) != 0 {
		t.Fatalf("expected empty auth_headers, got %v", updated.AuthHeaders)
	}

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

	if err := repo.DeleteByID("missing"); !errors.Is(err, ErrZohoImportNotFound) {
		t.Fatalf("err = %v, want ErrZohoImportNotFound", err)
	}
}
