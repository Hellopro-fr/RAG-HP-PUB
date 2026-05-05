package sso

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestFetchCredentialsFromAPI(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Admin-Token") != "tok" {
			http.Error(w, "unauth", http.StatusUnauthorized)
			return
		}
		if r.URL.Path != "/internal/credentials/mcp-gateway" {
			http.Error(w, "wrong path", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"client_id":"id-x","client_secret":"sec-y","redirect_uris":["https://gw/sso/callback"]}`))
	}))
	defer srv.Close()

	creds, err := FetchCredentialsFromAPI(context.Background(), "mcp-gateway", srv.URL, "tok")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if creds.ClientID != "id-x" || creds.ClientSecret != "sec-y" {
		t.Fatalf("got %q / %q", creds.ClientID, creds.ClientSecret)
	}
	if len(creds.RedirectURIs) != 1 || creds.RedirectURIs[0] != "https://gw/sso/callback" {
		t.Fatalf("redirect_uris: %v", creds.RedirectURIs)
	}
}

func TestFetchCredentialsFromAPI_NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))
	defer srv.Close()

	_, err := FetchCredentialsFromAPI(context.Background(), "missing", srv.URL, "tok")
	if err == nil {
		t.Fatal("expected error")
	}
}
