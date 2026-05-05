package gateway

import (
	"encoding/json"
	"testing"

	"mcp-gateway/internal/mcp"
)

func newTestTool(name string, active bool) mcp.Tool {
	return mcp.Tool{
		Name:        name,
		Description: "desc-" + name,
		InputSchema: json.RawMessage(`{"type":"object"}`),
		IsActive:    active,
	}
}

func TestMergedToolsFiltersInactive(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:   "srv1",
		Name: "Server1",
		Tools: []mcp.Tool{
			newTestTool("active_tool", true),
			newTestTool("inactive_tool", false),
		},
	})

	tools := reg.MergedTools()
	if len(tools) != 1 {
		t.Fatalf("expected 1 active tool, got %d", len(tools))
	}
	if tools[0].Name != "active_tool" {
		t.Errorf("expected active_tool, got %s", tools[0].Name)
	}
}

func TestMergedToolsWithPrefixFiltersInactive(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:         "srv1",
		Name:       "Server1",
		ToolPrefix: "zoho",
		Tools: []mcp.Tool{
			newTestTool("search", true),
			newTestTool("delete", false),
		},
	})

	tools := reg.MergedTools()
	if len(tools) != 1 {
		t.Fatalf("expected 1 active tool, got %d", len(tools))
	}
	if tools[0].Name != "zoho_search" {
		t.Errorf("expected zoho_search, got %s", tools[0].Name)
	}
}

func TestFindByToolSkipsInactive(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:   "srv1",
		Name: "Server1",
		Tools: []mcp.Tool{
			newTestTool("active_tool", true),
			newTestTool("inactive_tool", false),
		},
	})

	// Active tool should be found
	srv, origName := reg.FindByTool("active_tool")
	if srv == nil {
		t.Fatal("expected to find active_tool")
	}
	if origName != "active_tool" {
		t.Errorf("expected original name active_tool, got %s", origName)
	}

	// Inactive tool should NOT be found
	srv, _ = reg.FindByTool("inactive_tool")
	if srv != nil {
		t.Error("inactive_tool should not be found via FindByTool")
	}
}

func TestMergedToolsFilteredWithToolsFiltersInactive(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:   "srv1",
		Name: "Server1",
		Tools: []mcp.Tool{
			newTestTool("tool_a", true),
			newTestTool("tool_b", false),
			newTestTool("tool_c", true),
		},
	})

	allowed := map[string]bool{"srv1": true}

	// With no tool whitelist — should still filter inactive
	tools := reg.MergedToolsFilteredWithTools(allowed, nil)
	if len(tools) != 2 {
		t.Fatalf("expected 2 active tools, got %d", len(tools))
	}

	// With tool whitelist including inactive tool — should still filter it
	allowedTools := map[string]map[string]bool{
		"srv1": {"tool_a": true, "tool_b": true},
	}
	tools = reg.MergedToolsFilteredWithTools(allowed, allowedTools)
	if len(tools) != 1 {
		t.Fatalf("expected 1 tool (tool_a only, tool_b inactive), got %d", len(tools))
	}
	if tools[0].Name != "tool_a" {
		t.Errorf("expected tool_a, got %s", tools[0].Name)
	}
}

func TestSetToolActive(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:   "srv1",
		Name: "Server1",
		Tools: []mcp.Tool{
			newTestTool("my_tool", true),
		},
	})

	// Should be visible initially
	tools := reg.MergedTools()
	if len(tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(tools))
	}

	// Deactivate
	reg.SetToolActive("srv1", "my_tool", false)
	tools = reg.MergedTools()
	if len(tools) != 0 {
		t.Fatalf("expected 0 tools after deactivation, got %d", len(tools))
	}

	// Reactivate
	reg.SetToolActive("srv1", "my_tool", true)
	tools = reg.MergedTools()
	if len(tools) != 1 {
		t.Fatalf("expected 1 tool after reactivation, got %d", len(tools))
	}
}
