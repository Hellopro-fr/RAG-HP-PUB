package repository

import (
	"encoding/json"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// newTestDB opens an in-memory SQLite and creates a minimal `templates` table
// that matches the fields exercised by TemplateRepo. We avoid AutoMigrate on
// db.Template because its MySQL-specific `datetime(3)` column type is not
// recognised by SQLite drivers for time.Time scan conversion.
func newTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE templates (
			slug                TEXT PRIMARY KEY,
			name                TEXT NOT NULL,
			description         TEXT,
			icon                TEXT NOT NULL DEFAULT '',
			stdio_command       TEXT NOT NULL,
			stdio_args          TEXT,
			default_env         TEXT,
			required_extra_env  TEXT,
			tool_prefix         TEXT NOT NULL DEFAULT '',
			tags                TEXT,
			is_active           INTEGER NOT NULL DEFAULT 1,
			created_at          datetime,
			updated_at          datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return gdb
}

func TestTemplateRepo_ListActive(t *testing.T) {
	gdb := newTestDB(t)
	gdb.Create(&db.Template{Slug: "ga", Name: "GA4", StdioCommand: "analytics-mcp", IsActive: true, Tags: json.RawMessage(`["google"]`)})
	gdb.Create(&db.Template{Slug: "gsc", Name: "GSC", StdioCommand: "mcp-gsc", IsActive: true})
	// Bool zero-value + gorm `default:true` tag makes GORM substitute the default on
	// Create, so we bypass GORM for the inactive row to actually store is_active=0.
	if err := gdb.Exec(
		"INSERT INTO templates (slug, name, stdio_command, is_active) VALUES (?, ?, ?, 0)",
		"old", "Old", "x",
	).Error; err != nil {
		t.Fatalf("insert inactive: %v", err)
	}

	repo := NewTemplateRepo(gdb)
	out, err := repo.ListActive()
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 2 {
		t.Errorf("want 2, got %d", len(out))
	}
}

func TestTemplateRepo_GetBySlug_NotFound(t *testing.T) {
	gdb := newTestDB(t)
	repo := NewTemplateRepo(gdb)
	_, err := repo.GetBySlug("nope")
	if err == nil {
		t.Fatal("want error")
	}
}
