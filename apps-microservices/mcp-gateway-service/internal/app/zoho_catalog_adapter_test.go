package app

import (
	"context"
	"encoding/json"
	"testing"

	"gorm.io/driver/sqlite"
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

func TestZohoCatalogAdapter_UserRowWins(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)

	admin := &db.ZohoImport{ID: "admin-1", URL: "https://admin", IsAdmin: true, IsActive: true}
	if err := gdb.Create(admin).Error; err != nil {
		t.Fatalf("admin: %v", err)
	}
	user := &db.ZohoImport{URL: "https://alice", CreatedBy: "alice@hp.fr", IsActive: true}
	if err := repo.CreateUserImport(user); err != nil {
		t.Fatalf("user: %v", err)
	}

	if _, err := repo.ReplaceTools(admin.ID, []db.ZohoImportTool{
		{Name: "admin_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("admin tools: %v", err)
	}
	if _, err := repo.ReplaceTools(user.ID, []db.ZohoImportTool{
		{Name: "user_tool", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("user tools: %v", err)
	}

	a := &zohoCatalogAdapter{imports: repo}
	tools := a.ToolsForEmail(context.Background(), "alice@hp.fr")
	if len(tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(tools))
	}
	if tools[0].Name != "user_tool" {
		t.Fatalf("expected user_tool, got %q", tools[0].Name)
	}
}

func TestZohoCatalogAdapter_FallsBackToAdmin(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	repo := repository.NewZohoImportRepo(gdb)
	admin := &db.ZohoImport{ID: "admin-2", URL: "https://admin", IsAdmin: true, IsActive: true}
	if err := gdb.Create(admin).Error; err != nil {
		t.Fatalf("admin: %v", err)
	}
	if _, err := repo.ReplaceTools(admin.ID, []db.ZohoImportTool{
		{Name: "admin_only", InputSchema: json.RawMessage(`{}`)},
	}); err != nil {
		t.Fatalf("admin tools: %v", err)
	}

	a := &zohoCatalogAdapter{imports: repo}
	tools := a.ToolsForEmail(context.Background(), "stranger@hp.fr")
	if len(tools) != 1 || tools[0].Name != "admin_only" {
		t.Fatalf("expected admin_only fallback, got %+v", tools)
	}
}

func TestZohoCatalogAdapter_NoRowsReturnsEmpty(t *testing.T) {
	gdb := newZohoAdapterTestDB(t)
	a := &zohoCatalogAdapter{imports: repository.NewZohoImportRepo(gdb)}
	tools := a.ToolsForEmail(context.Background(), "alice@hp.fr")
	if len(tools) != 0 {
		t.Fatalf("expected empty, got %d", len(tools))
	}
}

func TestZohoCatalogAdapter_EmptyEmailNoOp(t *testing.T) {
	a := &zohoCatalogAdapter{}
	if got := a.ToolsForEmail(context.Background(), ""); got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}
