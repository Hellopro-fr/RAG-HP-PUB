package repository

import (
	"testing"

	"github.com/glebarez/sqlite"
	"mcp-gateway/internal/db"
	"gorm.io/gorm"
)

func newServerAuthTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE server_authorizations (
			server_id  TEXT NOT NULL,
			email      TEXT NOT NULL,
			created_by TEXT NOT NULL DEFAULT '',
			created_at datetime,
			PRIMARY KEY (server_id, email)
		);
	`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return gdb
}

func TestServerAuthorizationRepo_CreateAndIsAuthorized(t *testing.T) {
	repo := NewServerAuthorizationRepo(newServerAuthTestDB(t))

	if err := repo.Create(&db.ServerAuthorization{
		ServerID:  "srv-1",
		Email:     "alice@example.com",
		CreatedBy: "admin@example.com",
	}); err != nil {
		t.Fatalf("Create: %v", err)
	}

	if !repo.IsAuthorized("srv-1", "alice@example.com") {
		t.Fatal("expected alice authorized for srv-1")
	}
	if repo.IsAuthorized("srv-1", "bob@example.com") {
		t.Fatal("expected bob NOT authorized")
	}
	if repo.IsAuthorized("srv-2", "alice@example.com") {
		t.Fatal("expected alice not authorized on different server")
	}
}

func TestServerAuthorizationRepo_DeleteRevokesAccess(t *testing.T) {
	repo := NewServerAuthorizationRepo(newServerAuthTestDB(t))

	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"})
	if err := repo.Delete("srv-1", "alice@example.com"); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	if repo.IsAuthorized("srv-1", "alice@example.com") {
		t.Fatal("expected access revoked after Delete")
	}
}

func TestServerAuthorizationRepo_ListByServer(t *testing.T) {
	repo := NewServerAuthorizationRepo(newServerAuthTestDB(t))

	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"})
	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "bob@example.com"})
	_ = repo.Create(&db.ServerAuthorization{ServerID: "srv-2", Email: "alice@example.com"})

	rows, err := repo.ListByServer("srv-1")
	if err != nil {
		t.Fatalf("ListByServer: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("expected 2 rows for srv-1, got %d", len(rows))
	}
}

func TestServerAuthorizationRepo_DuplicateInsertIgnored(t *testing.T) {
	repo := NewServerAuthorizationRepo(newServerAuthTestDB(t))

	if err := repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"}); err != nil {
		t.Fatalf("first Create: %v", err)
	}
	if err := repo.Create(&db.ServerAuthorization{ServerID: "srv-1", Email: "alice@example.com"}); err != nil {
		t.Fatalf("duplicate Create returned err: %v (expected silent no-op)", err)
	}
	rows, _ := repo.ListByServer("srv-1")
	if len(rows) != 1 {
		t.Fatalf("expected 1 row after duplicate insert, got %d", len(rows))
	}
}

func TestServerAuthorizationRepo_IsAuthorizedRejectsEmpty(t *testing.T) {
	repo := NewServerAuthorizationRepo(newServerAuthTestDB(t))
	if repo.IsAuthorized("", "alice@example.com") {
		t.Fatal("empty server_id must not authorize")
	}
	if repo.IsAuthorized("srv-1", "") {
		t.Fatal("empty email must not authorize")
	}
}
