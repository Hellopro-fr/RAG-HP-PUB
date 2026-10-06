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
		`CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', template_slug TEXT NOT NULL DEFAULT '', tool_prefix TEXT NOT NULL DEFAULT '')`,
		`INSERT INTO mcp_servers (id, name, template_slug, tool_prefix) VALUES ('srv-neo4j', 'Neo4j prod', 'neo4j', ''), ('srv-plain', 'Plain', '', ''), ('srv-hd', 'HelloData', '', 'hellodata')`,
	} {
		if err := g.Exec(stmt).Error; err != nil {
			t.Fatalf("ddl: %v", err)
		}
	}
	return NewServerRepo(g, nil)
}

func TestServerRepo_AccessKeysByID(t *testing.T) {
	repo := newTemplateSlugTestRepo(t)
	cases := map[string][2]string{
		"srv-neo4j":   {"neo4j", ""},
		"srv-plain":   {"", ""},
		"srv-hd":      {"", "hellodata"},
		"srv-missing": {"", ""},
	}
	for id, want := range cases {
		slug, prefix, err := repo.AccessKeysByID(id)
		if err != nil {
			t.Fatalf("AccessKeysByID(%q): unexpected error %v", id, err)
		}
		if slug != want[0] || prefix != want[1] {
			t.Fatalf("AccessKeysByID(%q) = (%q, %q), want (%q, %q)", id, slug, prefix, want[0], want[1])
		}
	}
}

func TestServerRepo_AccessKeysByIDPropagatesDBErrors(t *testing.T) {
	repo := newTemplateSlugTestRepo(t)
	if err := repo.db.Exec(`DROP TABLE mcp_servers`).Error; err != nil {
		t.Fatalf("drop: %v", err)
	}
	if _, _, err := repo.AccessKeysByID("srv-neo4j"); err == nil {
		t.Fatal("a DB error must be returned, not swallowed as empty keys")
	}
}
