package mcp

import (
	"encoding/json"
	"testing"
)

func TestToolIsActiveNotSerialized(t *testing.T) {
	tool := Tool{
		Name:        "test_tool",
		Description: "A test tool",
		InputSchema: json.RawMessage(`{"type":"object"}`),
		IsActive:    true,
	}

	b, err := json.Marshal(tool)
	if err != nil {
		t.Fatalf("failed to marshal tool: %v", err)
	}

	// IsActive must NOT appear in JSON output (json:"-")
	var raw map[string]interface{}
	if err := json.Unmarshal(b, &raw); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}
	if _, found := raw["is_active"]; found {
		t.Error("IsActive should not be serialized in JSON (MCP protocol)")
	}
	if _, found := raw["IsActive"]; found {
		t.Error("IsActive should not be serialized in JSON (MCP protocol)")
	}
}
