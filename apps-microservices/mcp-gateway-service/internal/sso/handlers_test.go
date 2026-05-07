package sso

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
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

// fakeAccountServer answers /token with a canned authorization_code response.
// The access token is a minimal HS256 JWT carrying sub/email/name claims so
// ParseAccessTokenIdentity returns the expected identity without crypto setup.
func fakeAccountServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/token") {
			http.NotFound(w, r)
			return
		}
		hdr := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
		body := base64.RawURLEncoding.EncodeToString([]byte(
			fmt.Sprintf(`{"sub":"u-1","email":"alice@example.com","name":"Alice","exp":%d}`, time.Now().Add(time.Hour).Unix()),
		))
		toSign := hdr + "." + body
		mac := hmac.New(sha256.New, []byte("upstream-jwt-secret"))
		mac.Write([]byte(toSign))
		sig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
		jwt := toSign + "." + sig

		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"access_token":%q,"refresh_token":"r-1","token_type":"Bearer","expires_in":3600}`, jwt)
	}))
}

func TestHandleCallback_OAuth2PurposeWritesAuthSession(t *testing.T) {
	srv := fakeAccountServer(t)
	defer srv.Close()

	authJWTSecret := "auth-session-secret"
	stateSecret := []byte("hmac-secret-for-tests")

	h := NewHandlers(&Client{
		ClientID:           "c1",
		ClientSecret:       "s1",
		AccountPublicURL:   srv.URL,
		AccountInternalURL: srv.URL,
		RedirectURI:        srv.URL + "/sso/callback",
		Scope:              "openid email",
	}, nil, nil, nil, false).
		WithStateKey(stateSecret).
		WithAuthSession(authJWTSecret)

	pending := PendingState{
		Verifier: "verifier-xyz",
		State:    "state-abc",
		ReturnTo: "/authorize?response_type=code&client_id=mcp-x",
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
		Purpose:  "oauth2",
	}
	tok, err := SignPendingState(stateSecret, pending)
	if err != nil {
		t.Fatalf("SignPendingState: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/sso/callback?code=auth-code-1&state=state-abc", nil)
	req.AddCookie(&http.Cookie{Name: PendingCookieName, Value: tok})
	rec := httptest.NewRecorder()
	h.handleCallback(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d (body: %s)", rec.Code, rec.Body.String())
	}
	if got := rec.Header().Get("Location"); got != "/authorize?response_type=code&client_id=mcp-x" {
		t.Fatalf("unexpected redirect: %q", got)
	}

	var sawAuth, sawSession bool
	for _, c := range rec.Result().Cookies() {
		if c.Name == "mcp_session" {
			sawAuth = true
		}
		if c.Name == CookieName {
			sawSession = true
		}
	}
	if !sawAuth {
		t.Fatal("expected mcp_session cookie to be set on OAuth2 path")
	}
	if sawSession {
		t.Fatal("did not expect gw_session cookie on OAuth2 path")
	}
}
