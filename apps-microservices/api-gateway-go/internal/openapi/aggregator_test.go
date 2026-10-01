package openapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func mkUpstream(spec map[string]any) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(spec)
	}))
}

func TestMergeNoCollision(t *testing.T) {
	a := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "a"},
		"paths": map[string]any{"/x": map[string]any{
			"get": map[string]any{"operationId": "get_x", "responses": map[string]any{"200": map[string]any{"description": "ok"}}},
		}},
		"components": map[string]any{"schemas": map[string]any{"Foo": map[string]any{"type": "object"}}},
	})
	defer a.Close()
	b := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "b"},
		"paths": map[string]any{"/y": map[string]any{
			"get": map[string]any{"operationId": "get_y", "responses": map[string]any{"200": map[string]any{"description": "ok"}}},
		}},
		"components": map[string]any{"schemas": map[string]any{"Bar": map[string]any{"type": "object"}}},
	})
	defer b.Close()

	out, err := Aggregate(context.Background(), AggregateInput{
		Base: map[string]any{
			"openapi": "3.0.0", "info": map[string]any{"title": "Hellopro"},
			"paths":      map[string]any{},
			"components": map[string]any{"schemas": map[string]any{}},
		},
		Services: map[string]string{
			"/svc-a-service": a.URL,
			"/svc-b-service": b.URL,
		},
	})
	require.NoError(t, err)
	paths := out["paths"].(map[string]any)
	_, hasA := paths["/svc-a-service/x"]
	_, hasB := paths["/svc-b-service/y"]
	require.True(t, hasA)
	require.True(t, hasB)
}

func TestMergeCollisionPrefixesSchema(t *testing.T) {
	a := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "a"},
		"paths": map[string]any{"/x": map[string]any{
			"get": map[string]any{"operationId": "get_x",
				"responses": map[string]any{"200": map[string]any{"content": map[string]any{
					"application/json": map[string]any{"schema": map[string]any{"$ref": "#/components/schemas/Foo"}},
				}}},
			},
		}},
		"components": map[string]any{"schemas": map[string]any{"Foo": map[string]any{"type": "object"}}},
	})
	defer a.Close()
	b := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "b"},
		"paths": map[string]any{"/y": map[string]any{
			"get": map[string]any{"operationId": "get_y",
				"responses": map[string]any{"200": map[string]any{"content": map[string]any{
					"application/json": map[string]any{"schema": map[string]any{"$ref": "#/components/schemas/Foo"}},
				}}},
			},
		}},
		"components": map[string]any{"schemas": map[string]any{"Foo": map[string]any{"type": "string"}}},
	})
	defer b.Close()

	out, err := Aggregate(context.Background(), AggregateInput{
		Base: map[string]any{"openapi": "3.0.0", "info": map[string]any{"title": "h"}, "paths": map[string]any{}, "components": map[string]any{"schemas": map[string]any{}}},
		Services: map[string]string{
			"/svc-a-service": a.URL,
			"/svc-b-service": b.URL,
		},
	})
	require.NoError(t, err)

	schemas := out["components"].(map[string]any)["schemas"].(map[string]any)
	_, ok1 := schemas["SvcAFoo"]
	_, ok2 := schemas["SvcBFoo"]
	require.True(t, ok1, "expected SvcAFoo schema")
	require.True(t, ok2, "expected SvcBFoo schema")
}
