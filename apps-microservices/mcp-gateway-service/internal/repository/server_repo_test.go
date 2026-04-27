package repository

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

func TestNewServerRepoNilEncryptor(t *testing.T) {
	// Verifies that creating a repo with nil encryptor doesn't panic
	repo := NewServerRepo(nil, nil)
	if repo == nil {
		t.Error("expected non-nil repo")
	}
}

func TestServerRepo_GetURL(t *testing.T) {
	gdb := newTemplateTestDB(t)
	repo := NewServerRepo(gdb, nil)

	id := uuid.New().String()
	if err := gdb.Exec(
		"INSERT INTO mcp_servers (id, name, url) VALUES (?, ?, ?)",
		id, "srv", "http://runner:15042",
	).Error; err != nil {
		t.Fatalf("seed: %v", err)
	}

	u, err := repo.GetURL(id)
	if err != nil {
		t.Fatalf("GetURL: %v", err)
	}
	if u != "http://runner:15042" {
		t.Errorf("got %q, want http://runner:15042", u)
	}

	// Missing row returns empty string + no error (Scan on zero rows is a no-op).
	// This mirrors how GORM's Select+Scan behaves for primitives — callers that
	// need a not-found signal should use GetByID.
	missing, err := repo.GetURL("does-not-exist")
	if err != nil {
		t.Errorf("unexpected error for missing row: %v", err)
	}
	if missing != "" {
		t.Errorf("missing row should return empty string, got %q", missing)
	}

	// Sanity check: the ErrRecordNotFound sentinel isn't what we get back.
	if errors.Is(err, gorm.ErrRecordNotFound) {
		t.Errorf("GetURL should not surface ErrRecordNotFound")
	}
}
