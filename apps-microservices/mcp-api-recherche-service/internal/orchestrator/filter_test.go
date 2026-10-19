package orchestrator

import (
	"context"
	"testing"
	"time"
)

func TestBuildExclude(t *testing.T) {
	cache := NewSchemaCache(time.Hour)
	cache.Set("produits_3", map[string]string{
		"fournisseur": dtVarChar, "id_produit": dtInt64, "tags": dtArray,
	})
	fb := NewFilterBuilder(nil, cache)

	cases := []struct {
		name            string
		filtre, exclude map[string]any
		want            string
	}{
		{"string list", nil, map[string]any{"fournisseur": []any{"A", "B"}},
			"not (fournisseur in ['A', 'B'])"},
		{"numeric", nil, map[string]any{"id_produit": float64(42)},
			"not (id_produit == 42)"},
		{"array", nil, map[string]any{"tags": []any{"x"}},
			"not ((array_contains(tags, 'x')))"},
		{"with include", map[string]any{"id_produit": float64(1)}, map[string]any{"fournisseur": "A"},
			"id_produit == 1 and not (fournisseur == 'A')"},
		{"unknown field ignored", nil, map[string]any{"nope": "x"}, ""},
	}
	for _, c := range cases {
		got, _ := fb.Build(context.Background(), c.filtre, c.exclude, "produits_3")
		if got != c.want {
			t.Errorf("%s: got %q, want %q", c.name, got, c.want)
		}
	}
}
