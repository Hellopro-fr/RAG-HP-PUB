//go:build integration

package repository

import (
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestAuditInsertAndList(t *testing.T) {
	g := setupTestDB(t)
	r := NewAuditRepo(g)

	for i := 0; i < 5; i++ {
		_ = r.Insert(&db.AuditLog{Event: "login", ActorEmail: "a@x"})
	}
	rows, total, err := r.List(map[string]interface{}{"event": "login"}, 3, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 5 {
		t.Errorf("total=%d", total)
	}
	if len(rows) != 3 {
		t.Errorf("len=%d", len(rows))
	}
}
