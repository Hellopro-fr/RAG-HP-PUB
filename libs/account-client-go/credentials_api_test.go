package accountclient

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetCredentialsFromAPI_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Admin-Token") != "secret" {
			http.Error(w, "unauth", http.StatusUnauthorized)
			return
		}
		if r.URL.Path != "/internal/credentials/api-gateway" {
			http.Error(w, "wrong path", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"client_id":"id-1","client_secret":"sec-1"}`))
	}))
	defer srv.Close()

	id, sec, err := GetCredentialsFromAPI(context.Background(), "api-gateway", srv.URL, "secret")
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if id != "id-1" || sec != "sec-1" {
		t.Errorf("got=%q,%q", id, sec)
	}
}

func TestGetCredentialsFromAPI_MissingArgs(t *testing.T) {
	if _, _, err := GetCredentialsFromAPI(context.Background(), "", "https://x", "tok"); err == nil {
		t.Fatal("expected error for empty service")
	}
	if _, _, err := GetCredentialsFromAPI(context.Background(), "x", "", "tok"); err == nil {
		t.Fatal("expected error for empty base url")
	}
	if _, _, err := GetCredentialsFromAPI(context.Background(), "x", "https://x", ""); err == nil {
		t.Fatal("expected error for empty token")
	}
}

func TestGetCredentialsFromAPI_404(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"not_found"}`, http.StatusNotFound)
	}))
	defer srv.Close()
	_, _, err := GetCredentialsFromAPI(context.Background(), "nope", srv.URL, "secret")
	if err == nil {
		t.Fatal("expected error")
	}
}
