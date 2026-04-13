package authserver

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleToken_MethodNotAllowed(t *testing.T) {
	srv := &AuthServer{}
	req := httptest.NewRequest("GET", "/token", nil)
	w := httptest.NewRecorder()
	srv.HandleToken(w, req)
	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

func TestHandleToken_MissingGrantType(t *testing.T) {
	srv := &AuthServer{}
	req := httptest.NewRequest("POST", "/token", nil)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	srv.HandleToken(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}
