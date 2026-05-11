package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestHandleListServerAuthorizations_NoRepo verifies the 503 fallback when the
// repo is not wired, so the route stays mountable in deployments that do not
// enable the feature yet.
func TestHandleListServerAuthorizations_NoRepo(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/server-authorizations", nil)
	rec := httptest.NewRecorder()
	h.handleListServerAuthorizations(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", rec.Code)
	}
}

// TestHandleCreateServerAuthorization_NoRepo verifies the 503 fallback on POST.
func TestHandleCreateServerAuthorization_NoRepo(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodPost, "/api/v1/server-authorizations",
		strings.NewReader(`{"server_id":"s","email":"e@x"}`))
	rec := httptest.NewRecorder()
	h.handleCreateServerAuthorization(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", rec.Code)
	}
}

// TestHandleDeleteServerAuthorization_NoRepo verifies the 503 fallback on DELETE.
func TestHandleDeleteServerAuthorization_NoRepo(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodDelete,
		"/api/v1/server-authorizations/srv-1/alice@example.com", nil)
	rec := httptest.NewRecorder()
	h.handleDeleteServerAuthorization(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", rec.Code)
	}
}
