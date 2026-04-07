package authserver

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleAuthorize_MissingParams(t *testing.T) {
	srv := &AuthServer{publicURL: "https://mcp.example.com"}
	req := httptest.NewRequest("GET", "/authorize", nil)
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}
