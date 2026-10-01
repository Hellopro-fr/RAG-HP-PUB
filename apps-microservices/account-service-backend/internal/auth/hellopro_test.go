package auth

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAuthenticateHellopro_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		if r.FormValue("login") != "alice" || r.FormValue("password") != "p" {
			http.Error(w, "bad", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
	defer srv.Close()

	resp, err := AuthenticateHellopro(srv.URL, "alice", "p")
	if err != nil {
		t.Fatalf("AuthenticateHellopro: %v", err)
	}
	if !resp.Success {
		t.Fatal("Success=false")
	}
	if resp.Email != "alice@example.com" {
		t.Errorf("Email=%q", resp.Email)
	}
}

func TestAuthenticateHellopro_RejectsHTTPRemote(t *testing.T) {
	if _, err := AuthenticateHellopro("http://attacker.example/login", "x", "y"); err == nil {
		t.Fatal("expected scheme error")
	}
}

func TestAuthenticateHellopro_AllowsLocalhostHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":false}`))
	}))
	defer srv.Close()
	if !strings.HasPrefix(srv.URL, "http://127.0.0.1") {
		t.Skipf("test server URL %q not localhost", srv.URL)
	}
	resp, err := AuthenticateHellopro(srv.URL, "x", "y")
	if err != nil {
		t.Fatalf("expected no error for localhost, got %v", err)
	}
	if resp.Success {
		t.Fatal("Success=true")
	}
}
