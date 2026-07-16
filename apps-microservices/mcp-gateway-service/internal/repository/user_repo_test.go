package repository

import (
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/db"
)

// newUserTestDB hand-rolls the gateway_users DDL — AutoMigrate on the real
// GORM models isn't portable to SQLite (datetime(3)), mirroring the pattern
// in newInstructionTestDB.
func newUserTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE gateway_users (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			email         TEXT NOT NULL UNIQUE,
			display_name  TEXT NOT NULL DEFAULT '',
			role          TEXT NOT NULL DEFAULT 'config-only',
			is_allowed    INTEGER NOT NULL DEFAULT 0,
			login_count   INTEGER NOT NULL DEFAULT 0,
			last_login_at datetime,
			created_at    datetime,
			updated_at    datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return gdb
}

func TestSyncUsers_CreatesMissingWithConfigOnlyDefaults(t *testing.T) {
	repo := NewUserRepo(newUserTestDB(t), nil, nil)

	created, skipped, err := repo.SyncUsers([]SyncUserInput{
		{Email: "new@hellopro.fr", DisplayName: "New User"},
	})
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	if len(created) != 1 || created[0] != "new@hellopro.fr" {
		t.Fatalf("created = %v, want [new@hellopro.fr]", created)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped = %v, want empty", skipped)
	}

	u, err := repo.GetByEmail("new@hellopro.fr")
	if err != nil || u == nil {
		t.Fatalf("GetByEmail: u=%v err=%v", u, err)
	}
	if u.Role != "config-only" {
		t.Errorf("Role = %q, want config-only", u.Role)
	}
	if u.IsAllowed {
		t.Error("IsAllowed = true, want false")
	}
	if u.LoginCount != 0 {
		t.Errorf("LoginCount = %d, want 0", u.LoginCount)
	}
	if u.DisplayName != "New User" {
		t.Errorf("DisplayName = %q, want New User", u.DisplayName)
	}
}

func TestSyncUsers_SkipsExistingWithoutModifying(t *testing.T) {
	gdb := newUserTestDB(t)
	repo := NewUserRepo(gdb, nil, nil)

	// Pre-existing admin user — sync must NOT downgrade or touch it.
	pre := db.GatewayUser{Email: "admin@hellopro.fr", DisplayName: "Admin", Role: "admin", IsAllowed: true, LoginCount: 7}
	if err := gdb.Create(&pre).Error; err != nil {
		t.Fatalf("seed: %v", err)
	}

	created, skipped, err := repo.SyncUsers([]SyncUserInput{
		{Email: "admin@hellopro.fr", DisplayName: "Renamed"},
		{Email: "new@hellopro.fr", DisplayName: "New"},
	})
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	if len(created) != 1 || created[0] != "new@hellopro.fr" {
		t.Fatalf("created = %v, want [new@hellopro.fr]", created)
	}
	if len(skipped) != 1 || skipped[0] != "admin@hellopro.fr" {
		t.Fatalf("skipped = %v, want [admin@hellopro.fr]", skipped)
	}

	u, _ := repo.GetByEmail("admin@hellopro.fr")
	if u.Role != "admin" || !u.IsAllowed || u.DisplayName != "Admin" || u.LoginCount != 7 {
		t.Errorf("existing user modified: %+v", u)
	}
}

func TestSyncUsers_EmptyInputReturnsEmptySlices(t *testing.T) {
	repo := NewUserRepo(newUserTestDB(t), nil, nil)
	created, skipped, err := repo.SyncUsers(nil)
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	// Must be non-nil empty slices so the handler JSON-encodes [] not null.
	if created == nil || skipped == nil {
		t.Fatalf("created=%v skipped=%v, want non-nil empty slices", created, skipped)
	}
	if len(created) != 0 || len(skipped) != 0 {
		t.Fatalf("created=%v skipped=%v, want empty", created, skipped)
	}
}
