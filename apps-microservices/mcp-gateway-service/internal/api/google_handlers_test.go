package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestHandleImportInstancesFromSheet_NilDeps_Returns503 ensures the handler
// fails fast when the templates feature is not wired. No Google client, no
// repos — just the empty Handler.
func TestHandleImportInstancesFromSheet_NilDeps_Returns503(t *testing.T) {
	h := &Handler{} // all deps nil

	body, _ := json.Marshal(InstanceSheetImportRequest{
		SpreadsheetID:     "ss",
		SheetName:         "Sheet1",
		TemplateSlug:      "ga",
		NameColumn:        "Name",
		CredentialsColumn: "Credentials",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/google/sheets/import-instances", bytes.NewReader(body))
	rec := httptest.NewRecorder()

	h.handleImportInstancesFromSheet(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d (body=%s)", rec.Code, rec.Body.String())
	}
}
