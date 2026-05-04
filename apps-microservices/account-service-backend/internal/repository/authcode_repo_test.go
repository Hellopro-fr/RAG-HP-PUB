//go:build integration

package repository

import (
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

func TestAuthCodeSingleUse(t *testing.T) {
	g := setupTestDB(t)
	r := NewAuthCodeRepo(g)

	code := &db.OAuth2AuthorizationCode{
		CodeHash:      "hash-1",
		ClientID:      "cli-1",
		UserEmail:     "alice@example.com",
		RedirectURI:   "https://x/cb",
		CodeChallenge: "challenge",
		ExpiresAt:     time.Now().Add(10 * time.Minute),
	}
	if err := r.Create(code); err != nil {
		t.Fatalf("Create: %v", err)
	}
	got, err := r.ConsumeUnused("hash-1")
	if err != nil {
		t.Fatalf("ConsumeUnused: %v", err)
	}
	if got.UserEmail != "alice@example.com" {
		t.Fatal("wrong row")
	}
	if _, err := r.ConsumeUnused("hash-1"); err == nil {
		t.Fatal("second ConsumeUnused should fail")
	}
}

func TestPurgeExpired(t *testing.T) {
	g := setupTestDB(t)
	r := NewAuthCodeRepo(g)
	_ = r.Create(&db.OAuth2AuthorizationCode{
		CodeHash:    "old",
		ClientID:    "c",
		UserEmail:   "x@y",
		RedirectURI: "https://x",
		ExpiresAt:   time.Now().Add(-1 * time.Hour),
	})
	n, err := r.PurgeExpired()
	if err != nil {
		t.Fatalf("PurgeExpired: %v", err)
	}
	if n != 1 {
		t.Errorf("purged=%d want 1", n)
	}
}
