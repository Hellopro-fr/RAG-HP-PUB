package sso

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// Compile-only smoke test — full integration coverage lives in cmd/server e2e.
func TestNewHandlers(t *testing.T) {
	h := NewHandlers(nil, nil, nil, nil, false)
	if h == nil {
		t.Fatal("expected non-nil handlers")
	}
}

func TestParseJWTSubAndEmail(t *testing.T) {
	// {"sub":"user-123","email":"alice@example.com"}
	tok := "header." +
		"eyJzdWIiOiJ1c2VyLTEyMyIsImVtYWlsIjoiYWxpY2VAZXhhbXBsZS5jb20ifQ" +
		".sig"
	sub, email, name, err := ParseAccessTokenIdentity(tok)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if sub != "user-123" || email != "alice@example.com" {
		t.Fatalf("got sub=%q email=%q", sub, email)
	}
	_ = name
}

func newTestHandlersForLogin(t *testing.T) *Handlers {
	t.Helper()
	return NewHandlers(
		&Client{
			ClientID:         "test-client",
			AccountPublicURL: "https://account.test",
			RedirectURI:      "https://gw.test/sso/callback",
			Scope:            "openid profile email",
		},
		nil, nil, nil, false,
	).WithStateKey([]byte("hmac-secret-for-tests"))
}

func TestHandleLogin_StashesOAuth2Purpose(t *testing.T) {
	h := newTestHandlersForLogin(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/sso/login?return_to=%2Fauthorize%3Fclient_id%3Dx&purpose=oauth2", nil)
	h.handleLogin(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d", rec.Code)
	}

	cookies := rec.Result().Cookies()
	var pending string
	for _, c := range cookies {
		if c.Name == PendingCookieName {
			pending = c.Value
		}
	}
	if pending == "" {
		t.Fatal("pending cookie not set")
	}
	st, err := VerifyPendingState(h.stateKey, pending)
	if err != nil {
		t.Fatalf("VerifyPendingState: %v", err)
	}
	if st.Purpose != "oauth2" {
		t.Fatalf("expected Purpose=oauth2, got %q", st.Purpose)
	}
	if st.ReturnTo != "/authorize?client_id=x" {
		t.Fatalf("ReturnTo round-trip failed: %q", st.ReturnTo)
	}
}

func TestHandleLogin_DefaultsPurposeToEmpty(t *testing.T) {
	h := newTestHandlersForLogin(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/sso/login?return_to=%2F", nil)
	h.handleLogin(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d", rec.Code)
	}
	for _, c := range rec.Result().Cookies() {
		if c.Name != PendingCookieName {
			continue
		}
		st, err := VerifyPendingState(h.stateKey, c.Value)
		if err != nil {
			t.Fatalf("VerifyPendingState: %v", err)
		}
		if st.Purpose != "" {
			t.Fatalf("expected empty Purpose, got %q", st.Purpose)
		}
	}
}

func TestHandleLogin_RejectsUnknownPurpose(t *testing.T) {
	h := newTestHandlersForLogin(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/sso/login?return_to=%2F&purpose=admin-typo", nil)
	h.handleLogin(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for unknown purpose, got %d", rec.Code)
	}
}
