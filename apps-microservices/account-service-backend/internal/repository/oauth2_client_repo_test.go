//go:build integration

package repository

import (
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestOAuth2ClientCRUD(t *testing.T) {
	g := setupTestDB(t)
	r := NewOAuth2ClientRepo(g)

	c := &db.OAuth2Client{
		ClientID:          "cli-1",
		ClientSecretEnc:   []byte("ciphertext"),
		Name:              "Test",
		TokenTTLSeconds:   60,
		RefreshTTLSeconds: 86400,
		IsActive:          true,
	}
	if err := r.Create(c); err != nil {
		t.Fatalf("Create: %v", err)
	}
	if c.ID == "" {
		t.Fatal("Create should set ID")
	}

	got, err := r.GetByClientID("cli-1")
	if err != nil {
		t.Fatalf("GetByClientID: %v", err)
	}
	if got.Name != "Test" {
		t.Errorf("Name=%q", got.Name)
	}

	if err := r.Update(c.ID, map[string]interface{}{"name": "Renamed"}); err != nil {
		t.Fatalf("Update: %v", err)
	}
	got, _ = r.GetByID(c.ID)
	if got.Name != "Renamed" {
		t.Fatalf("Update did not persist: %q", got.Name)
	}

	clients, total, err := r.List(10, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 1 || len(clients) != 1 {
		t.Fatalf("List total=%d len=%d", total, len(clients))
	}
}
