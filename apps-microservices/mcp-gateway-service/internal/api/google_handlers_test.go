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

// TestResolveCreatedBy verifies the row-level created_by resolution rule
// shared between handleSheetImport and handleImportInstancesFromSheet.
//
// Contract:
//   - column header empty               -> fallback (connected user)
//   - column header set, header missing -> fallback (handler responsibility
//                                          to pre-flight when desired; the
//                                          resolver itself does not error)
//   - column header set, cell empty     -> fallback
//   - column header set, cell non-empty -> trimmed cell
func TestResolveCreatedBy(t *testing.T) {
	headers := []string{"Name", "Credentials", "Owner"}
	colIndex := map[string]int{}
	for i, h := range headers {
		colIndex[h] = i
	}

	cases := []struct {
		name     string
		column   string
		row      []string
		fallback string
		want     string
	}{
		{
			name:     "empty column -> fallback",
			column:   "",
			row:      []string{"srv-1", "{}", "ignored@example.com"},
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
		{
			name:     "header missing -> fallback",
			column:   "Doesnotexist",
			row:      []string{"srv-1", "{}", "ignored@example.com"},
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
		{
			name:     "cell empty -> fallback",
			column:   "Owner",
			row:      []string{"srv-1", "{}", "   "},
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
		{
			name:     "cell non-empty -> trimmed cell",
			column:   "Owner",
			row:      []string{"srv-1", "{}", "  alice@hellopro.fr  "},
			fallback: "me@hellopro.fr",
			want:     "alice@hellopro.fr",
		},
		{
			name:     "row shorter than colIndex -> fallback",
			column:   "Owner",
			row:      []string{"srv-1", "{}"}, // missing Owner cell
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := resolveCreatedBy(tc.column, tc.row, colIndex, tc.fallback)
			if got != tc.want {
				t.Fatalf("resolveCreatedBy(%q) = %q, want %q", tc.column, got, tc.want)
			}
		})
	}
}
