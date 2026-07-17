package scopetoken

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// preloadedCache builds a Cache with one entry so tests don't hit the DB.
func preloadedCache(t *testing.T, rawToken string, ct *CachedToken) *Cache {
	t.Helper()
	c := NewCache(60 * time.Second)
	c.Set(Hash(rawToken), ct)
	return c
}

func TestValidateAndBuildContext_AcceptsBothAuthSources(t *testing.T) {
	const raw = "mcp_helper_test_token_0000000000000000000000000000"
	ct := &CachedToken{
		ID:        "tok-1",
		Name:      "test",
		ServerIDs: map[string]bool{"srv-1": true},
		IsActive:  true,
	}

	tests := []struct {
		name       string
		authSource string
	}{
		{"x-mcp-scope-token source", "x-mcp-scope-token"},
		{"bearer source", "bearer"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cache := preloadedCache(t, raw, ct)

			req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
			rec := httptest.NewRecorder()

			ctx, ok := ValidateAndBuildContext(rec, req, raw, tt.authSource, cache, nil, nil, nil)
			if !ok {
				t.Fatalf("expected ok=true, status=%d", rec.Code)
			}
			got, _ := ctx.Value(AllowedServersContextKey).(map[string]bool)
			if !got["srv-1"] {
				t.Fatalf("expected srv-1 allowed, got %v", got)
			}
		})
	}
}

func TestValidateAndBuildContext_RejectsRevoked(t *testing.T) {
	const raw = "mcp_revoked_test_token_00000000000000000000000000000"
	cache := preloadedCache(t, raw, &CachedToken{
		ID:       "tok-2",
		IsActive: false,
	})

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	rec := httptest.NewRecorder()

	if _, ok := ValidateAndBuildContext(rec, req, raw, "bearer", cache, nil, nil, nil); ok {
		t.Fatal("expected ok=false for revoked token")
	}
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", rec.Code)
	}
	if rec.Header().Get("WWW-Authenticate") != "" {
		t.Fatal("scope path must not emit WWW-Authenticate")
	}
}
