package repository

import (
	"encoding/json"
	"errors"
	"testing"

	"mcp-gateway/internal/db"
)

func TestTemplateRepo_Create(t *testing.T) {
	gdb := newTemplateTestDB(t)
	repo := NewTemplateRepo(gdb)

	active := &db.Template{
		Slug: "a", Name: "A", StdioCommand: "x", Kind: "stdio", Runner: "neo4j",
		StdioArgs: json.RawMessage(`[]`), IsActive: true,
	}
	if err := repo.Create(active); err != nil {
		t.Fatalf("Create active: %v", err)
	}
	got, err := repo.GetBySlug("a")
	if err != nil || got.Runner != "neo4j" {
		t.Fatalf("GetBySlug = %+v err=%v", got, err)
	}

	// GORM substitutes the `default:true` tag for a false bool: the inactive
	// row must still be stored as is_active=0.
	inactive := &db.Template{Slug: "b", Name: "B", StdioCommand: "x", Kind: "stdio", Runner: "google", IsActive: false}
	if err := repo.Create(inactive); err != nil {
		t.Fatalf("Create inactive: %v", err)
	}
	any, err := repo.GetBySlugAny("b")
	if err != nil {
		t.Fatalf("GetBySlugAny: %v", err)
	}
	if any.IsActive {
		t.Error("inactive template was stored as active")
	}

	for _, slug := range []string{"a", "b"} {
		dup := &db.Template{Slug: slug, Name: "Dup", StdioCommand: "x", IsActive: true}
		if err := repo.Create(dup); !errors.Is(err, ErrTemplateExists) {
			t.Errorf("duplicate %s: want ErrTemplateExists, got %v", slug, err)
		}
	}
}
