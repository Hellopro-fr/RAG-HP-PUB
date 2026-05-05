package sso

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestClientBuildAuthorizeURL(t *testing.T) {
	c := &Client{
		ClientID:         "mcp-gateway",
		AccountPublicURL: "https://account.example.com",
		RedirectURI:      "https://gw.example.com/sso/callback",
		Scope:            "openid profile email",
	}
	u, err := c.BuildAuthorizeURL("ch-abc", "state-xyz")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	parsed, err := url.Parse(u)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if parsed.Host != "account.example.com" {
		t.Fatalf("host: %s", parsed.Host)
	}
	if parsed.Path != "/authorize" {
		t.Fatalf("path: %s", parsed.Path)
	}
	q := parsed.Query()
	if q.Get("client_id") != "mcp-gateway" {
		t.Fatal("missing client_id")
	}
	if q.Get("code_challenge") != "ch-abc" {
		t.Fatal("missing challenge")
	}
	if q.Get("code_challenge_method") != "S256" {
		t.Fatal("missing method")
	}
	if q.Get("state") != "state-xyz" {
		t.Fatal("missing state")
	}
	if q.Get("response_type") != "code" {
		t.Fatal("missing response_type")
	}
}

func TestExchangeCode(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/token" {
			http.Error(w, "wrong path", 404)
			return
		}
		if err := r.ParseForm(); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		if r.PostForm.Get("grant_type") != "authorization_code" {
			http.Error(w, "wrong grant", 400)
			return
		}
		if r.PostForm.Get("code") != "auth-code-1" {
			http.Error(w, "wrong code", 400)
			return
		}
		if r.PostForm.Get("client_id") != "mcp-gateway" {
			http.Error(w, "wrong client", 400)
			return
		}
		if r.PostForm.Get("client_secret") != "secret" {
			http.Error(w, "wrong secret", 400)
			return
		}
		if r.PostForm.Get("code_verifier") == "" {
			http.Error(w, "missing verifier", 400)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(TokenResponse{
			AccessToken:  "access-1",
			RefreshToken: "refresh-1",
			TokenType:    "Bearer",
			ExpiresIn:    3600,
			Scope:        "openid",
		})
	}))
	defer srv.Close()

	c := &Client{
		ClientID:           "mcp-gateway",
		ClientSecret:       "secret",
		AccountInternalURL: srv.URL,
		HTTP:               srv.Client(),
	}
	tok, err := c.ExchangeCode(context.Background(), "auth-code-1", "verifier-x", "https://gw/sso/callback")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if tok.AccessToken != "access-1" {
		t.Fatalf("access: %q", tok.AccessToken)
	}
}

func TestExchangeCodeError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
		_, _ = w.Write([]byte(`{"error":"invalid_grant"}`))
	}))
	defer srv.Close()

	c := &Client{
		ClientID:           "mcp-gateway",
		ClientSecret:       "secret",
		AccountInternalURL: srv.URL,
		HTTP:               srv.Client(),
	}
	_, err := c.ExchangeCode(context.Background(), "x", "v", "r")
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "invalid_grant") {
		t.Fatalf("err message: %v", err)
	}
}
