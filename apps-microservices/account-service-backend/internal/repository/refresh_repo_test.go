//go:build integration

package repository

import (
	"testing"
	"time"

	"github.com/google/uuid"
	"account-service/internal/db"
)

func newRefresh(sid, hash string) *db.OAuth2RefreshToken {
	return &db.OAuth2RefreshToken{
		ID:        uuid.New().String(),
		TokenHash: hash,
		SID:       sid,
		ClientID:  "cli-1",
		UserEmail: "alice@example.com",
		ExpiresAt: time.Now().Add(24 * time.Hour),
	}
}

func TestRefreshRotateChain(t *testing.T) {
	g := setupTestDB(t)
	r := NewRefreshRepo(g)
	old := newRefresh("sid-A", "h1")
	if err := r.Create(old); err != nil {
		t.Fatalf("Create: %v", err)
	}
	rotated, err := r.Rotate("h1", "h2")
	if err != nil {
		t.Fatalf("Rotate: %v", err)
	}
	if rotated.SID != "sid-A" {
		t.Errorf("SID drift on rotate")
	}
	got, err := r.FindByHash("h1")
	if err != nil {
		t.Fatalf("FindByHash: %v", err)
	}
	if !got.Revoked {
		t.Fatal("old row not revoked after rotate")
	}
}

func TestRefreshReuseDetectionRevokesChain(t *testing.T) {
	g := setupTestDB(t)
	r := NewRefreshRepo(g)
	first := newRefresh("sid-B", "ha")
	if err := r.Create(first); err != nil {
		t.Fatalf("Create: %v", err)
	}
	if _, err := r.Rotate("ha", "hb"); err != nil {
		t.Fatalf("Rotate1: %v", err)
	}
	if _, err := r.Rotate("ha", "hc"); err == nil {
		t.Fatal("expected reuse to fail")
	}
	rows, err := r.ListBySID("sid-B")
	if err != nil {
		t.Fatalf("ListBySID: %v", err)
	}
	for _, x := range rows {
		if !x.Revoked {
			t.Fatalf("row %s should be revoked after reuse detection", x.ID)
		}
	}
}

func TestRefreshRevokeAllForUser(t *testing.T) {
	g := setupTestDB(t)
	r := NewRefreshRepo(g)
	_ = r.Create(newRefresh("s1", "h1"))
	_ = r.Create(newRefresh("s2", "h2"))
	if err := r.RevokeAllForUser("alice@example.com", "admin_revoke"); err != nil {
		t.Fatalf("RevokeAllForUser: %v", err)
	}
	rows, _ := r.ListByUser("alice@example.com")
	for _, x := range rows {
		if !x.Revoked {
			t.Fatalf("row %s not revoked", x.ID)
		}
	}
}
