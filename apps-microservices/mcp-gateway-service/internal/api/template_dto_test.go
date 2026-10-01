package api

import (
	"encoding/json"
	"testing"
	"time"
)

func TestTemplateDTOStructs(t *testing.T) {
	// Validates DTO struct fields are correctly defined.
	tr := TemplateResponse{
		Slug:          "google-sheets",
		Name:          "Google Sheets",
		ToolPrefix:    "sheets",
		InstanceCount: 3,
	}
	if tr.Slug != "google-sheets" {
		t.Fatal("unexpected slug")
	}
	if tr.InstanceCount != 3 {
		t.Fatal("unexpected instance count")
	}

	port := 15000
	ir := TemplateInstanceResponse{
		ID:           "inst-1",
		TemplateSlug: "google-sheets",
		Name:         "my-sheets",
		RunnerPort:   &port,
		RunnerStatus: "running",
		MCPServerID:  "srv-1",
		CreatedAt:    time.Now(),
	}
	if ir.RunnerPort == nil || *ir.RunnerPort != 15000 {
		t.Fatal("unexpected runner port")
	}
	if ir.RunnerStatus != "running" {
		t.Fatal("unexpected runner status")
	}

	req := CreateInstanceRequest{
		TemplateSlug: "google-sheets",
		Name:         "my-sheets",
		ExtraEnv:     map[string]string{"KEY": "value"},
	}
	if req.ExtraEnv["KEY"] != "value" {
		t.Fatal("unexpected extra env")
	}
}

func TestTemplateResponseJSONRoundtrip(t *testing.T) {
	// Ensure json.RawMessage fields serialize as JSON (not base64-encoded bytes).
	tr := TemplateResponse{
		Slug:      "t",
		Name:      "T",
		StdioArgs: json.RawMessage(`["--flag"]`),
		Tags:      json.RawMessage(`["a","b"]`),
	}
	b, err := json.Marshal(tr)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	args, ok := decoded["stdio_args"].([]any)
	if !ok || len(args) != 1 || args[0] != "--flag" {
		t.Fatalf("stdio_args not serialized as JSON array: %v", decoded["stdio_args"])
	}
}
