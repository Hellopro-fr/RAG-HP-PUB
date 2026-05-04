package authserver

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestParseAuthorizeParams_Required(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet,
		"/authorize?response_type=code&client_id=x&redirect_uri=https://x/cb&code_challenge=c&code_challenge_method=S256&state=s",
		nil)
	p, err := parseAuthorizeParams(r)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if p.ClientID != "x" || p.RedirectURI != "https://x/cb" || p.CodeChallenge != "c" {
		t.Fatalf("got %+v", p)
	}
}

func TestParseAuthorizeParams_RejectsNonCode(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=token&client_id=x&redirect_uri=https://x&code_challenge=c&code_challenge_method=S256", nil)
	if _, err := parseAuthorizeParams(r); err == nil {
		t.Fatal("expected error")
	}
}

func TestParseAuthorizeParams_RejectsPlainPKCE(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=code&client_id=x&redirect_uri=https://x&code_challenge=c&code_challenge_method=plain", nil)
	if _, err := parseAuthorizeParams(r); err == nil {
		t.Fatal("expected error")
	}
}

func TestIsRegisteredRedirectURI(t *testing.T) {
	uris := `["https://a/cb","https://b/cb"]`
	c := &db.OAuth2Client{RedirectURIs: &uris}
	if !isRegisteredRedirectURI(c, "https://b/cb") {
		t.Fatal("expected match")
	}
	if isRegisteredRedirectURI(c, "https://evil/cb") {
		t.Fatal("expected no match")
	}
}
