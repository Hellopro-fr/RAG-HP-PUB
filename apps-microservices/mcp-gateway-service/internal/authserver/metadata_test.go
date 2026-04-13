package authserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleMetadata(t *testing.T) {
	srv := &AuthServer{publicURL: "https://mcp.example.com"}
	req := httptest.NewRequest("GET", "/.well-known/oauth-authorization-server", nil)
	w := httptest.NewRecorder()
	srv.HandleMetadata(w, req)

	if w.Code != 200 {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var meta map[string]interface{}
	json.NewDecoder(w.Body).Decode(&meta)

	if meta["issuer"] != "https://mcp.example.com" {
		t.Fatalf("unexpected issuer: %v", meta["issuer"])
	}
	if meta["token_endpoint"] != "https://mcp.example.com/token" {
		t.Fatalf("unexpected token_endpoint: %v", meta["token_endpoint"])
	}
	if meta["authorization_endpoint"] != "https://mcp.example.com/authorize" {
		t.Fatalf("unexpected authorization_endpoint: %v", meta["authorization_endpoint"])
	}
	if meta["registration_endpoint"] != "https://mcp.example.com/register" {
		t.Fatalf("unexpected registration_endpoint: %v", meta["registration_endpoint"])
	}
}

func TestHandleMetadata_MethodNotAllowed(t *testing.T) {
	srv := &AuthServer{publicURL: "https://mcp.example.com"}
	req := httptest.NewRequest("POST", "/.well-known/oauth-authorization-server", nil)
	w := httptest.NewRecorder()
	srv.HandleMetadata(w, req)
	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}
