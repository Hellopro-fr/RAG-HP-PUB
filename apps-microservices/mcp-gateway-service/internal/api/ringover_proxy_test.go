package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleRingoverUsers_DisabledReturns503(t *testing.T) {
	h := &Handler{} // ringoverAdmin unset → disabled
	rr := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/api/v1/ringover/users", nil)
	h.handleRingoverUsers(rr, r)
	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", rr.Code)
	}
}

func TestHandleRingoverUsers_MethodNotAllowed(t *testing.T) {
	h := &Handler{}
	rr := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodPost, "/api/v1/ringover/users", nil)
	h.handleRingoverUsers(rr, r)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405, got %d", rr.Code)
	}
}

func TestHandleRingoverTeams_DisabledReturns503(t *testing.T) {
	h := &Handler{}
	rr := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/api/v1/ringover/teams", nil)
	h.handleRingoverTeams(rr, r)
	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503, got %d", rr.Code)
	}
}
