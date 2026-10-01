//go:build integration

package repository

import "testing"

func TestUpsertOnLogin_FirstUserBecomesAdmin(t *testing.T) {
	g := setupTestDB(t)
	r := NewUserRepo(g, nil)

	u, err := r.UpsertOnLogin("alice@example.com", "Alice")
	if err != nil {
		t.Fatalf("UpsertOnLogin: %v", err)
	}
	if !u.IsAdmin {
		t.Fatalf("first user should be admin")
	}
}

func TestUpsertOnLogin_HonorsAdminEmailsList(t *testing.T) {
	g := setupTestDB(t)
	_, _ = NewUserRepo(g, nil).UpsertOnLogin("seed@example.com", "Seed")

	r := NewUserRepo(g, []string{"alice@example.com"})
	u, err := r.UpsertOnLogin("alice@example.com", "Alice")
	if err != nil {
		t.Fatalf("UpsertOnLogin: %v", err)
	}
	if !u.IsAdmin {
		t.Fatal("alice should be admin via env list")
	}
	other, _ := r.UpsertOnLogin("bob@example.com", "Bob")
	if other.IsAdmin {
		t.Fatal("bob should not be admin")
	}
}

func TestUpsertOnLogin_UpdatesLastLogin(t *testing.T) {
	g := setupTestDB(t)
	r := NewUserRepo(g, nil)

	u1, _ := r.UpsertOnLogin("alice@example.com", "Alice")
	first := u1.LastLoginAt
	u2, _ := r.UpsertOnLogin("alice@example.com", "Alice Updated")
	if u2.LastLoginAt == nil || (first != nil && !u2.LastLoginAt.After(*first)) {
		t.Fatal("LastLoginAt not bumped")
	}
	if u2.DisplayName != "Alice Updated" {
		t.Fatalf("DisplayName not updated: %q", u2.DisplayName)
	}
}
