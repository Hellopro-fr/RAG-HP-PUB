// Tests for EndpointRepo are in repo_test.go (shared test setup).
package repository

import (
	"errors"
	"testing"

	"gorm.io/gorm"

	"api-catalog-service/internal/db"
)

func newEndpointRepo(t *testing.T) (*EndpointRepo, *gorm.DB) {
	t.Helper()
	gdb := newDB(t)
	return NewEndpointRepo(gdb), gdb
}

func TestEndpointRepo_UpdateAuthPolicy_Set(t *testing.T) {
	repo, gdb := newEndpointRepo(t)
	_ = gdb.Create(&db.EndpointRow{ID: "ep-set", ServiceID: "svc", Protocol: "rest", Path: "/a"}).Error
	policy := 2
	if err := repo.UpdateAuthPolicy("ep-set", &policy); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetByID("ep-set")
	if err != nil || got.AuthPolicy == nil || *got.AuthPolicy != 2 {
		t.Fatalf("got=%+v err=%v; want policy=2", got, err)
	}
}

func TestEndpointRepo_UpdateAuthPolicy_Clear(t *testing.T) {
	repo, gdb := newEndpointRepo(t)
	policy := 3
	_ = gdb.Create(&db.EndpointRow{ID: "ep-clr", ServiceID: "svc", Protocol: "rest", Path: "/b", AuthPolicy: &policy}).Error
	if err := repo.UpdateAuthPolicy("ep-clr", nil); err != nil {
		t.Fatal(err)
	}
	got, _ := repo.GetByID("ep-clr")
	if got.AuthPolicy != nil {
		t.Fatalf("got policy=%d; want nil after clear", *got.AuthPolicy)
	}
}

func TestEndpointRepo_GetByID_NotFound(t *testing.T) {
	repo, _ := newEndpointRepo(t)
	if _, err := repo.GetByID("nope"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("got err=%v; want ErrNotFound", err)
	}
}
