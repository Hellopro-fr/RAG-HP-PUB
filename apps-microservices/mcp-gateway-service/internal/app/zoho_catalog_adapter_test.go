package app

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

func newZohoAdapterTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := g.Exec(`
		CREATE TABLE zoho_imports (
			id            TEXT PRIMARY KEY,
			name          TEXT NOT NULL DEFAULT '',
			url           TEXT NOT NULL DEFAULT '',
			auth_headers  BLOB,
			created_by    TEXT NOT NULL DEFAULT '',
			is_admin      INTEGER NOT NULL DEFAULT 0,
			is_active     INTEGER NOT NULL DEFAULT 1,
			template_slug TEXT NOT NULL DEFAULT '',
			created_at    DATETIME,
			updated_at    DATETIME
		)
	`).Error; err != nil {
		t.Fatalf("zoho_imports: %v", err)
	}
	if err := g.Exec(`
		CREATE TABLE zoho_import_tools (
			id           INTEGER PRIMARY KEY AUTOINCREMENT,
			import_id    TEXT NOT NULL,
			name         TEXT NOT NULL,
			description  TEXT NOT NULL DEFAULT '',
			input_schema TEXT NOT NULL,
			created_at   DATETIME,
			updated_at   DATETIME,
			UNIQUE (import_id, name)
		)
	`).Error; err != nil {
		t.Fatalf("zoho_import_tools: %v", err)
	}
	return g
}

// fakeUserFinder satisfies the role-resolution dependency used by the
// adapter. Returns a *db.GatewayUser whose Role is the configured one
// for the given email; nil when the email is unknown.
type fakeUserFinder struct {
	byEmail map[string]string // email -> role
}

func (f *fakeUserFinder) GetByEmail(email string) (*db.GatewayUser, error) {
	if f == nil {
		return nil, nil
	}
	role, ok := f.byEmail[email]
	if !ok {
		return nil, nil
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

func TestZohoCatalogAdapter_StateForEmail_AdminWithRow(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)
	admin := &db.ZohoImport{ID: "admin-1", URL: "https://admin", IsAdmin: true, IsActive: true}
	if err := gdb.Create(admin).Error; err != nil {
		t.Fatalf("admin: %v", err)
	}
	if _, err := repo.ReplaceTools(admin.ID, []db.ZohoImportTool{
		{Name: "admin_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("admin tools: %v", err)
	}

	a := &zohoCatalogAdapter{
		imports: repo,
		users:   &fakeUserFinder{byEmail: map[string]string{"admin@hp.fr": "admin"}},
	}
	st := a.StateForEmail(context.Background(), "admin@hp.fr")

	if !st.Configured {
		t.Fatalf("admin with admin row must be Configured")
	}
	if len(st.Tools) != 1 || st.Tools[0].Name != "admin_tool" {
		t.Fatalf("want admin_tool, got %+v", st.Tools)
	}
}

func TestZohoCatalogAdapter_StateForEmail_AdminWithoutRow(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)

	a := &zohoCatalogAdapter{
		imports: repo,
		users:   &fakeUserFinder{byEmail: map[string]string{"admin@hp.fr": "admin"}},
	}
	st := a.StateForEmail(context.Background(), "admin@hp.fr")

	if st.Configured {
		t.Fatalf("admin without admin row must be Configured=false")
	}
	if len(st.Tools) != 0 {
		t.Fatalf("unconfigured state must carry no tools")
	}
}

func TestZohoCatalogAdapter_StateForEmail_NonAdminWithRow(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)

	admin := &db.ZohoImport{ID: "admin-1", URL: "https://admin", IsAdmin: true, IsActive: true}
	if err := gdb.Create(admin).Error; err != nil {
		t.Fatalf("admin: %v", err)
	}
	if _, err := repo.ReplaceTools(admin.ID, []db.ZohoImportTool{
		{Name: "admin_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("admin tools: %v", err)
	}
	user := &db.ZohoImport{URL: "https://alice", CreatedBy: "alice@hp.fr", IsActive: true}
	if err := repo.CreateUserImport(user); err != nil {
		t.Fatalf("user: %v", err)
	}
	if _, err := repo.ReplaceTools(user.ID, []db.ZohoImportTool{
		{Name: "alice_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("user tools: %v", err)
	}

	a := &zohoCatalogAdapter{
		imports: repo,
		users:   &fakeUserFinder{byEmail: map[string]string{"alice@hp.fr": "user"}},
	}
	st := a.StateForEmail(context.Background(), "alice@hp.fr")

	if !st.Configured {
		t.Fatalf("non-admin with user row must be Configured=true")
	}
	if len(st.Tools) != 1 || st.Tools[0].Name != "alice_tool" {
		t.Fatalf("want alice_tool, got %+v", st.Tools)
	}
}

func TestZohoCatalogAdapter_StateForEmail_NonAdminWithoutRow_NoAdminFallback(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)

	admin := &db.ZohoImport{ID: "admin-1", URL: "https://admin", IsAdmin: true, IsActive: true}
	if err := gdb.Create(admin).Error; err != nil {
		t.Fatalf("admin: %v", err)
	}
	if _, err := repo.ReplaceTools(admin.ID, []db.ZohoImportTool{
		{Name: "admin_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("admin tools: %v", err)
	}

	a := &zohoCatalogAdapter{
		imports: repo,
		users:   &fakeUserFinder{byEmail: map[string]string{"bob@hp.fr": "user"}},
	}
	st := a.StateForEmail(context.Background(), "bob@hp.fr")

	if st.Configured {
		t.Fatalf("non-admin without user row must NOT fall back to admin row (got Configured=true)")
	}
	if len(st.Tools) != 0 {
		t.Fatalf("non-admin without user row must NOT see admin tools (got %+v)", st.Tools)
	}
}

func TestZohoCatalogAdapter_StateForEmail_UnknownUserTreatedAsNonAdmin(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)

	admin := &db.ZohoImport{ID: "admin-1", URL: "https://admin", IsAdmin: true, IsActive: true}
	if err := gdb.Create(admin).Error; err != nil {
		t.Fatalf("admin: %v", err)
	}
	if _, err := repo.ReplaceTools(admin.ID, []db.ZohoImportTool{
		{Name: "admin_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("admin tools: %v", err)
	}

	a := &zohoCatalogAdapter{
		imports: repo,
		users:   &fakeUserFinder{}, // no users mapped
	}
	st := a.StateForEmail(context.Background(), "stranger@hp.fr")

	if st.Configured {
		t.Fatalf("unknown user must default to non-admin and NOT fall back to admin (got Configured=true)")
	}
}

func TestZohoCatalogAdapter_StateForEmail_EmptyEmail(t *testing.T) {
	a := &zohoCatalogAdapter{
		imports: repository.NewZohoImportRepo(newZohoAdapterTestDB(t)),
		users:   &fakeUserFinder{},
	}
	if st := a.StateForEmail(context.Background(), ""); st.Configured || len(st.Tools) > 0 {
		t.Fatalf("empty email must return zero state")
	}
}

func TestZohoCatalogAdapter_StateForEmail_RowExistsButNoTools(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)

	user := &db.ZohoImport{URL: "https://alice", CreatedBy: "alice@hp.fr", IsActive: true}
	if err := repo.CreateUserImport(user); err != nil {
		t.Fatalf("user: %v", err)
	}
	// No ReplaceTools call → no rows in zoho_import_tools.

	a := &zohoCatalogAdapter{
		imports: repo,
		users:   &fakeUserFinder{byEmail: map[string]string{"alice@hp.fr": "user"}},
	}
	st := a.StateForEmail(context.Background(), "alice@hp.fr")

	if st.Configured {
		t.Fatalf("row without tools must be Configured=false")
	}
}
