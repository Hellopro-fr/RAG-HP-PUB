package api

import (
	"encoding/json"
	"testing"
)

// TestInstanceSheetImportRequestJSONRoundtrip verifies the DTO serializes
// its snake_case wire names. Also ensures optional overrides are omitted
// when unset (omitempty behaviour).
func TestInstanceSheetImportRequestJSONRoundtrip(t *testing.T) {
	req := InstanceSheetImportRequest{
		SpreadsheetID:     "ss-123",
		SheetName:         "Sheet1",
		TemplateSlug:      "ga",
		NameColumn:        "Name",
		CredentialsColumn: "Credentials",
		ExtraEnvColumns: map[string]string{
			"GOOGLE_ANALYTICS_PROPERTY_ID": "PropertyID",
		},
	}
	b, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if decoded["template_slug"] != "ga" {
		t.Fatalf("expected template_slug=ga, got %v", decoded["template_slug"])
	}
	if decoded["name_column"] != "Name" {
		t.Fatalf("expected name_column=Name, got %v", decoded["name_column"])
	}
	if decoded["credentials_column"] != "Credentials" {
		t.Fatalf("expected credentials_column=Credentials, got %v", decoded["credentials_column"])
	}
	// Optional overrides should be omitted when unset.
	if _, present := decoded["auto_discover"]; present {
		t.Fatal("auto_discover should be omitted when false")
	}
	if _, present := decoded["fixed_tags"]; present {
		t.Fatal("fixed_tags should be omitted when empty")
	}
}

// TestSheetImportResponseShape is a cheap sanity check that the shared response
// type exposes the fields the new endpoint reuses.
func TestSheetImportResponseShape(t *testing.T) {
	resp := SheetImportResponse{
		Total:    3,
		Imported: 1,
		Skipped:  1,
		Errors:   1,
		Results: []SheetImportResultEntry{
			{Row: 2, Name: "a", Status: "imported"},
			{Row: 3, Name: "b", Status: "skipped", Message: "duplicate"},
			{Row: 4, Name: "c", Status: "error", Message: "boom"},
		},
	}
	if resp.Total != len(resp.Results) {
		t.Fatalf("expected total=%d to match len(results)=%d", resp.Total, len(resp.Results))
	}
}
