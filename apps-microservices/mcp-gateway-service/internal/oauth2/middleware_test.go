package oauth2

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"mcp-gateway/internal/scopetoken"
)

// noopHandler is the downstream of CombinedMiddleware in tests — confirms
// the request reached the protected handler.
func noopHandler(t *testing.T, expectAllowed string) http.Handler {
	t.Helper()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got, _ := r.Context().Value(scopetoken.AllowedServersContextKey).(map[string]bool)
		if !got[expectAllowed] {
			t.Errorf("downstream: expected %q allowed, got %v", expectAllowed, got)
		}
		w.WriteHeader(http.StatusOK)
	})
}

// seedScopeCache puts a valid, active scope token into the scopetoken cache.
func seedScopeCache(t *testing.T, rawToken string, allowedServer string) *scopetoken.Cache {
	t.Helper()
	c := scopetoken.NewCache(time.Minute)
	c.Set(scopetoken.Hash(rawToken), &scopetoken.CachedToken{
		ID:        "tok-test",
		Name:      "test",
		ServerIDs: map[string]bool{allowedServer: true},
		IsActive:  true,
	})
	return c
}

// seedOAuth2Cache puts a valid OAuth2 client + a freshly issued JWT into
// the oauth2 cache. Returns the access token string.
func seedOAuth2Cache(t *testing.T, jwtSecret, allowedServer string) (string, *Cache) {
	t.Helper()
	jwt, _, err := IssueAccessToken(jwtSecret, "client-test", "", 3600)
	if err != nil {
		t.Fatalf("issue jwt: %v", err)
	}
	c := NewCache(time.Minute)
	c.Set("client-test", &CachedClient{
		ID:        "client-test",
		Name:      "test client",
		ServerIDs: map[string]bool{allowedServer: true},
		IsActive:  true,
	})
	return jwt, c
}

func TestCombinedMiddleware_BearerScopeTokenAccepted(t *testing.T) {
	const raw = "mcp_combined_test_valid_0000000000000000000000000000"
	scopeCache := seedScopeCache(t, raw, "srv-1")
	mw := CombinedMiddleware(NewCache(time.Minute), nil, scopeCache, nil, nil, "secret", "https://gw.example", nil)

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	req.Header.Set("Authorization", "Bearer "+raw)
	rec := httptest.NewRecorder()

	mw(noopHandler(t, "srv-1")).ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestCombinedMiddleware_BearerScopeTokenRevoked(t *testing.T) {
	const raw = "mcp_combined_test_revoked_00000000000000000000000000"
	c := scopetoken.NewCache(time.Minute)
	c.Set(scopetoken.Hash(raw), &scopetoken.CachedToken{ID: "tok", IsActive: false})
	mw := CombinedMiddleware(NewCache(time.Minute), nil, c, nil, nil, "secret", "https://gw.example", nil)

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	req.Header.Set("Authorization", "Bearer "+raw)
	rec := httptest.NewRecorder()

	mw(http.NotFoundHandler()).ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", rec.Code)
	}
	if rec.Header().Get("WWW-Authenticate") != "" {
		t.Fatal("scope path must not emit WWW-Authenticate")
	}
}

func TestCombinedMiddleware_BearerJWTPathUnchanged(t *testing.T) {
	const secret = "test-jwt-secret"
	jwt, oauthCache := seedOAuth2Cache(t, secret, "srv-2")
	mw := CombinedMiddleware(oauthCache, nil, scopetoken.NewCache(time.Minute), nil, nil, secret, "https://gw.example", nil)

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	req.Header.Set("Authorization", "Bearer "+jwt)
	rec := httptest.NewRecorder()

	mw(noopHandler(t, "srv-2")).ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestCombinedMiddleware_XScopeTokenWinsOverBearer(t *testing.T) {
	const rawScope = "mcp_combined_test_winner_000000000000000000000000000"
	scopeCache := seedScopeCache(t, rawScope, "srv-scope")
	mw := CombinedMiddleware(NewCache(time.Minute), nil, scopeCache, nil, nil, "secret", "https://gw.example", nil)

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	req.Header.Set("X-MCP-Scope-Token", rawScope)
	req.Header.Set("Authorization", "Bearer "+rawScope+"DIFFERENT") // garbage; must be ignored
	rec := httptest.NewRecorder()

	mw(noopHandler(t, "srv-scope")).ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestCombinedMiddleware_BearerGarbageFallsIntoJWTPath(t *testing.T) {
	mw := CombinedMiddleware(NewCache(time.Minute), nil, scopetoken.NewCache(time.Minute), nil, nil, "secret", "https://gw.example", nil)

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	req.Header.Set("Authorization", "Bearer foobar") // not mcp_, not JWT
	rec := httptest.NewRecorder()

	mw(http.NotFoundHandler()).ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	if rec.Header().Get("WWW-Authenticate") == "" {
		t.Fatal("JWT path must emit WWW-Authenticate")
	}
}

func TestCombinedMiddleware_NoAuthHeaders(t *testing.T) {
	mw := CombinedMiddleware(NewCache(time.Minute), nil, scopetoken.NewCache(time.Minute), nil, nil, "secret", "https://gw.example", nil)

	req := httptest.NewRequest(http.MethodGet, "/mcp", nil)
	rec := httptest.NewRecorder()

	mw(http.NotFoundHandler()).ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	if rec.Header().Get("WWW-Authenticate") == "" {
		t.Fatal("missing-auth path must emit WWW-Authenticate")
	}
}
