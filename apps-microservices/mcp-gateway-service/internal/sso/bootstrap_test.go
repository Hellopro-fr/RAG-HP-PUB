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
		_, _ = w.Write([]byte(`{"client_id":"id-x","client_secret":"sec-y"}`))
	}))
	defer srv.Close()

	id, sec, err := FetchCredentialsFromAPI(context.Background(), "mcp-gateway", srv.URL, "tok")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if id != "id-x" || sec != "sec-y" {
		t.Fatalf("got %q / %q", id, sec)
	}
}

func TestFetchCredentialsFromAPI_NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))
	defer srv.Close()

	_, _, err := FetchCredentialsFromAPI(context.Background(), "missing", srv.URL, "tok")
	if err == nil {
		t.Fatal("expected error")
	}
}
