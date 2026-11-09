//go:build integration

package repository

import (
	"errors"
	"testing"

	"account-service/internal/db"
)

func TestGroupRepo_Lifecycle(t *testing.T) {
	g := setupTestDB(t)
	users := NewUserRepo(g, nil)
	_, _ = users.UpsertOnLogin("alice@example.com", "Alice")
	_, _ = users.UpsertOnLogin("bob@example.com", "Bob")
	r := NewGroupRepo(g)

	cat, err := r.Create("Équipe catalogue", "Fiches produits", "admin@example.com")
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if _, err := r.Create("Équipe catalogue", "", "admin@example.com"); !errors.Is(err, db.ErrGroupNameTaken) {
		t.Fatalf("duplicate name: got %v", err)
	}

	if err := r.AddMember(cat.ID, "alice@example.com", "admin@example.com"); err != nil {
		t.Fatalf("AddMember: %v", err)
	}
	if err := r.AddMember(cat.ID, "alice@example.com", "admin@example.com"); err != nil {
		t.Fatalf("AddMember twice must be a no-op: %v", err)
	}
	if err := r.AddMember(cat.ID, "nobody@example.com", "admin@example.com"); !errors.Is(err, db.ErrUnknownUser) {
		t.Fatalf("unknown user: got %v", err)
	}
	if err := r.AddMember("00000000-0000-0000-0000-000000000000", "bob@example.com", "x"); !errors.Is(err, db.ErrGroupNotFound) {
		t.Fatalf("unknown group: got %v", err)
	}

	list, err := r.List()
	if err != nil || len(list) != 1 || list[0].MemberCount != 1 {
		t.Fatalf("List: %+v %v", list, err)
	}
	_, members, err := r.Get(cat.ID)
	if err != nil || len(members) != 1 || members[0].DisplayName != "Alice" || !members[0].IsAllowed {
		t.Fatalf("Get: %+v %v", members, err)
	}

	if _, err := r.Update(cat.ID, "Catalogue", "x"); err != nil {
		t.Fatalf("Update: %v", err)
	}
	users2, groups, memberships, err := r.Directory()
	if err != nil || len(users2) != 2 || len(groups) != 1 || len(memberships) != 1 || groups[0].Name != "Catalogue" {
		t.Fatalf("Directory: %d users %d groups %d members %v", len(users2), len(groups), len(memberships), err)
	}

	if err := r.RemoveMember(cat.ID, "alice@example.com"); err != nil {
		t.Fatalf("RemoveMember: %v", err)
	}
	if err := r.Delete(cat.ID); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	if err := r.Delete(cat.ID); !errors.Is(err, db.ErrGroupNotFound) {
		t.Fatalf("Delete twice: got %v", err)
	}
}
