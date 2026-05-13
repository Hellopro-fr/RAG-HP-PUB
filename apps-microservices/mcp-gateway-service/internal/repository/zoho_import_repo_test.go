package repository

import (
	"errors"
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
