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
