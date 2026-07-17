package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHandleRunnerSync_NilDeps_Returns503(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodPost, "/api/v1/internal/runner/sync", nil)
	rec := httptest.NewRecorder()
	h.handleRunnerSync(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("got %d", rec.Code)
	}
}

func TestHandleRunnerSync_GetReturns405(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/internal/runner/sync", nil)
	rec := httptest.NewRecorder()
	h.handleRunnerSync(rec, req)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Errorf("got %d, want 405", rec.Code)
	}
	if got := rec.Header().Get("Allow"); got != "POST" {
		t.Errorf("Allow header = %q, want POST", got)
	}
}
