// Tests for ServiceRepo are in repo_test.go (shared test setup).
package repository

import (
	"testing"

	"gorm.io/gorm"

	"api-catalog-service/internal/db"
)

func newServiceRepo(t *testing.T) (*ServiceRepo, *gorm.DB) {
	t.Helper()
	gdb := newDB(t)
	return NewServiceRepo(gdb), gdb
}

func TestServiceRepo_AuthPolicyDefault(t *testing.T) {
	repo, _ := newServiceRepo(t)
	row := &db.ServiceRow{ID: "auth-default", Name: "x-service", BaseURL: "http://x", Protocols: "[]", Source: "manual", Status: "active"}
	if err := repo.Create(row); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetByID("auth-default")
	if err != nil {
		t.Fatal(err)
	}
	if got.AuthPolicy != 1 { // PUBLIC
		t.Fatalf("default auth_policy = %d, want 1 (PUBLIC)", got.AuthPolicy)
	}
}

func TestServiceRepo_UpdateAuthPolicy(t *testing.T) {
	repo, _ := newServiceRepo(t)
	row := &db.ServiceRow{ID: "auth-update", Name: "y-service", BaseURL: "http://y", Protocols: "[]", Source: "manual", Status: "active"}
	_ = repo.Create(row)
	if err := repo.Update("auth-update", map[string]any{"auth_policy": 2, "public_paths": `["/health"]`}); err != nil {
		t.Fatal(err)
	}
	got, _ := repo.GetByID("auth-update")
	if got.AuthPolicy != 2 || got.PublicPaths != `["/health"]` {
		t.Fatalf("got policy=%d paths=%q; want 2 + /health JSON", got.AuthPolicy, got.PublicPaths)
	}
}

func TestServiceRepo_HasEndpointOverrides(t *testing.T) {
	repo, gdb := newServiceRepo(t)
	row := &db.ServiceRow{ID: "svc-h", Name: "h-service", BaseURL: "http://h", Protocols: "[]", Source: "manual", Status: "active"}
	_ = repo.Create(row)
	got, err := repo.HasEndpointOverrides("svc-h")
	if err != nil || got {
		t.Fatalf("empty endpoints: hasOverrides=%v err=%v; want false,nil", got, err)
	}
	p := 2
	_ = gdb.Create(&db.EndpointRow{ID: "ep1", ServiceID: "svc-h", Protocol: "rest", Path: "/", AuthPolicy: &p}).Error
	got, _ = repo.HasEndpointOverrides("svc-h")
	if !got {
		t.Fatal("with one override row: want true")
	}
}
