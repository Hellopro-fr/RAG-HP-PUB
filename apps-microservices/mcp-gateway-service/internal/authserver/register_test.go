package authserver

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleRegister_MethodNotAllowed(t *testing.T) {
	srv := &AuthServer{}
	req := httptest.NewRequest("GET", "/register", nil)
	w := httptest.NewRecorder()
	srv.HandleRegister(w, req)
	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}
