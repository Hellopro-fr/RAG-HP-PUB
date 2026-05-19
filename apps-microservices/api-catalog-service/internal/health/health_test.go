package health

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHandler_Healthz(t *testing.T) {
	rr := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/healthz", nil)
	Handler().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("code = %d", rr.Code)
	}
	body, _ := io.ReadAll(rr.Body)
	if !strings.HasPrefix(string(body), "ok") {
		t.Fatalf("body = %q", body)
	}
}
