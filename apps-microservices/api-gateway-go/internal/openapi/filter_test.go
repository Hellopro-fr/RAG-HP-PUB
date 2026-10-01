package openapi

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestFilterPublicSpec(t *testing.T) {
	in := map[string]any{
		"info": map[string]any{"description": "A\n<!-- ADMIN_SECTION -->\nB"},
		"paths": map[string]any{
			"/p1": map[string]any{
				"get": map[string]any{"security": []any{map[string]any{"AdminCle": []any{}}}},
			},
			"/p2": map[string]any{
				"get": map[string]any{"summary": "ok"},
			},
		},
		"components": map[string]any{
			"securitySchemes": map[string]any{
				"AdminCle":     map[string]any{},
				"Bearer Token": map[string]any{},
			},
		},
	}
	out := Filter(in)
	paths := out["paths"].(map[string]any)
	_, ok := paths["/p1"]
	require.False(t, ok, "admin-only path should be removed")
	_, ok = paths["/p2"]
	require.True(t, ok)
	schemes := out["components"].(map[string]any)["securitySchemes"].(map[string]any)
	_, hasAdmin := schemes["AdminCle"]
	require.False(t, hasAdmin)
	desc := out["info"].(map[string]any)["description"].(string)
	require.Equal(t, "A", desc)
}
