package oauth2

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"mcp-gateway/internal/scopetoken"
)

// TestCombinedMiddleware_StashesEndUserEmail asserts that a valid Bearer JWT
// carrying an email claim is propagated to the request context under
// scopetoken.EndUserEmailContextKey so the ScopedGateway can resolve "self"
// mode filters.
func TestCombinedMiddleware_StashesEndUserEmail(t *testing.T) {
	secret := "test-secret"
	clientID := "client-z"
	email := "carol@example.com"

	tok, _, err := IssueAccessToken(secret, clientID, email, 60)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}

	cache := NewCache(time.Hour)
	cache.Set(clientID, &CachedClient{
		ID:        clientID,
		Name:      "test",
		ServerIDs: map[string]bool{"srv-1": true},
		IsActive:  true,
	})

	var captured string
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if v, ok := scopetoken.EndUserEmailFromContext(r.Context()); ok {
			captured = v
		}
		w.WriteHeader(http.StatusOK)
	})

	mw := CombinedMiddleware(cache, nil, nil, nil, nil, secret, "", nil)
	h := mw(next)

	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if captured != email {
		t.Fatalf("expected captured email %q, got %q", email, captured)
	}
}

// TestCombinedMiddleware_NoEmailWhenAbsent ensures that a client_credentials
// grant (empty email claim) does NOT leak a stale value into the context.
func TestCombinedMiddleware_NoEmailWhenAbsent(t *testing.T) {
	secret := "test-secret"
	clientID := "client-cc"

	tok, _, _ := IssueAccessToken(secret, clientID, "", 60)
	cache := NewCache(time.Hour)
	cache.Set(clientID, &CachedClient{
		ID:        clientID,
		Name:      "cc",
		ServerIDs: map[string]bool{"srv-1": true},
		IsActive:  true,
	})

	var present bool
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, present = scopetoken.EndUserEmailFromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	})

	mw := CombinedMiddleware(cache, nil, nil, nil, nil, secret, "", nil)
	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	rec := httptest.NewRecorder()
	mw(next).ServeHTTP(rec, req)

	if present {
		t.Fatal("expected no end-user email in context for client_credentials grant")
	}
}
