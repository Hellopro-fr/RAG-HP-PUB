package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/mcp-gateway/internal/db"
)

func TestHandleListTemplates_NilDeps_Returns503(t *testing.T) {
	h := &Handler{} // templateRepo and instanceRepo both nil
	req := httptest.NewRequest(http.MethodGet, "/api/v1/templates", nil)
	rec := httptest.NewRecorder()

	h.handleListTemplates(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
	var body ErrorResponse
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body.Error == "" {
		t.Fatal("expected non-empty error message")
	}
}

func TestHandleGetTemplate_NilDeps_Returns503(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/templates/google-sheets", nil)
	rec := httptest.NewRecorder()

	h.handleGetTemplate(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
}

func TestHandleListInstances_NilRepo_Returns503(t *testing.T) {
	h := &Handler{} // instanceRepo nil
	req := httptest.NewRequest(http.MethodGet, "/api/v1/template-instances", nil)
	rec := httptest.NewRecorder()

	h.handleListInstances(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
}

func TestHandleGetInstance_NilRepo_Returns503(t *testing.T) {
	h := &Handler{} // instanceRepo nil
	req := httptest.NewRequest(http.MethodGet, "/api/v1/template-instances/abc", nil)
	rec := httptest.NewRecorder()

	h.handleGetInstance(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", rec.Code)
	}
}

func TestToTemplateResponse_PreservesFields(t *testing.T) {
	tmpl := db.Template{
		Slug:         "google-sheets",
		Name:         "Google Sheets",
		Description:  "access sheets",
		Icon:         "sheets.png",
		StdioCommand: "npx",
		StdioArgs:    json.RawMessage(`["-y","@g/sheets"]`),
		ToolPrefix:   "sheets",
	}
	resp := toTemplateResponse(tmpl, 5)

	if resp.Slug != "google-sheets" {
		t.Fatalf("unexpected slug: %s", resp.Slug)
	}
	if resp.InstanceCount != 5 {
		t.Fatalf("unexpected count: %d", resp.InstanceCount)
	}
	if resp.StdioCommand != "npx" {
		t.Fatalf("unexpected command: %s", resp.StdioCommand)
	}
	if string(resp.StdioArgs) != `["-y","@g/sheets"]` {
		t.Fatalf("unexpected args: %s", resp.StdioArgs)
	}
}
