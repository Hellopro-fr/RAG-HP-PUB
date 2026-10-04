package repository

import (
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// Pure-Go SQLite (no cgo) so the test runs in the Alpine test container.
func newTemplateSlugTestRepo(t *testing.T) *ServerRepo {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	sqlDB, err := g.DB()
	if err != nil {
		t.Fatalf("sql db: %v", err)
	}
	sqlDB.SetMaxOpenConns(1)
	t.Cleanup(func() { _ = sqlDB.Close() })
	for _, stmt := range []string{
		`CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', template_slug TEXT NOT NULL DEFAULT '')`,
		`INSERT INTO mcp_servers (id, name, template_slug) VALUES ('srv-neo4j', 'Neo4j prod', 'neo4j'), ('srv-plain', 'Plain', '')`,
	} {
		if err := g.Exec(stmt).Error; err != nil {
			t.Fatalf("ddl: %v", err)
		}
	}
	return NewServerRepo(g, nil)
}

func TestServerRepo_TemplateSlugByID(t *testing.T) {
	repo := newTemplateSlugTestRepo(t)
	cases := map[string]string{
		"srv-neo4j":   "neo4j",
		"srv-plain":   "",
		"srv-missing": "",
	}
	for id, want := range cases {
		got, err := repo.TemplateSlugByID(id)
		if err != nil {
			t.Fatalf("TemplateSlugByID(%q): unexpected error %v", id, err)
		}
		if got != want {
			t.Fatalf("TemplateSlugByID(%q) = %q, want %q", id, got, want)
		}
	}
}

func TestServerRepo_TemplateSlugByIDPropagatesDBErrors(t *testing.T) {
	repo := newTemplateSlugTestRepo(t)
	if err := repo.db.Exec(`DROP TABLE mcp_servers`).Error; err != nil {
		t.Fatalf("drop: %v", err)
	}
	if _, err := repo.TemplateSlugByID("srv-neo4j"); err == nil {
		t.Fatal("a DB error must be returned, not swallowed as an empty slug")
	}
}
