package gateway

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/mcp"
)

func toolsFromResponse(t *testing.T, resp *mcp.Response) []mcp.Tool {
	t.Helper()
	if resp == nil || resp.Error != nil {
		t.Fatalf("unexpected error response: %+v", resp)
	}
	raw, err := json.Marshal(resp.Result)
	if err != nil {
		t.Fatalf("marshal result: %v", err)
	}
	var out mcp.ListToolsResult
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("unmarshal result: %v", err)
	}
	return out.Tools
}

func decorationFixture() ([]mcp.Tool, []InstructionView, map[string]string) {
	tools := []mcp.Tool{
		{Name: "ga4_run_report", Description: "Run a GA4 report."},
		{Name: "leexi_search_calls", Description: "Search Leexi calls."},
	}
	instructions := []InstructionView{
		{ID: "g1", Title: "Golden rule", Body: "Always explain tool choice.", Kind: db.LLMInstructionRowKindGeneral},
		{ID: "p1", Title: "GA4 category filter", Body: "Read category5 via cURL first.", Kind: db.LLMInstructionRowKindPerServer, ServerIDs: []string{"srv-ga"}},
	}
	index := map[string]string{
		"ga4_run_report":     "srv-ga",
		"leexi_search_calls": "srv-leexi",
	}
	return tools, instructions, index
}

func TestDecorateTools_GeneralAppliesToAllPerServerOnlyToOwner(t *testing.T) {
	tools, instructions, index := decorationFixture()
	got := DecorateToolsWithInstructions(tools, instructions, index, "test-scope")

	// GA4 tool: general + per-server blocks.
	if !strings.Contains(got[0].Description, "Always explain tool choice.") {
		t.Errorf("ga4 tool should carry the general row: %q", got[0].Description)
	}
	if !strings.Contains(got[0].Description, "Read category5 via cURL first.") {
		t.Errorf("ga4 tool should carry its per-server row: %q", got[0].Description)
	}
	// Leexi tool: general only.
	if !strings.Contains(got[1].Description, "Always explain tool choice.") {
		t.Errorf("leexi tool should carry the general row: %q", got[1].Description)
	}
	if strings.Contains(got[1].Description, "Read category5") {
		t.Errorf("leexi tool must NOT carry the GA4 per-server row: %q", got[1].Description)
	}
	// Original description must survive as prefix.
	if !strings.HasPrefix(got[0].Description, "Run a GA4 report.") {
		t.Errorf("original description must be preserved as prefix: %q", got[0].Description)
	}
}

func TestDecorateTools_EmptyKindTreatedAsGeneral(t *testing.T) {
	tools := []mcp.Tool{{Name: "t1", Description: "d1"}}
	instructions := []InstructionView{{ID: "1", Title: "Rule", Body: "Apply everywhere."}}
	got := DecorateToolsWithInstructions(tools, instructions, map[string]string{}, "s")
	if !strings.Contains(got[0].Description, "Apply everywhere.") {
		t.Errorf("empty Kind should render as general: %q", got[0].Description)
	}
}

func TestDecorateTools_UnknownToolGetsGeneralOnly(t *testing.T) {
	tools := []mcp.Tool{{Name: "zoho_live_tool", Description: "live"}}
	instructions := []InstructionView{
		{ID: "g1", Title: "G", Body: "general body", Kind: db.LLMInstructionRowKindGeneral},
		{ID: "p1", Title: "P", Body: "per-server body", Kind: db.LLMInstructionRowKindPerServer, ServerIDs: []string{"srv-x"}},
	}
	// Tool absent from the index → only general rows.
	got := DecorateToolsWithInstructions(tools, instructions, map[string]string{}, "s")
	if !strings.Contains(got[0].Description, "general body") {
		t.Errorf("unknown tool should still get general rows: %q", got[0].Description)
	}
	if strings.Contains(got[0].Description, "per-server body") {
		t.Errorf("unknown tool must not get per-server rows: %q", got[0].Description)
	}
}

func TestDecorateTools_NoMatchingRowsLeavesDescriptionUntouched(t *testing.T) {
	tools := []mcp.Tool{{Name: "t1", Description: "original"}}
	instructions := []InstructionView{
		{ID: "p1", Title: "P", Body: "other server", Kind: db.LLMInstructionRowKindPerServer, ServerIDs: []string{"srv-other"}},
	}
	got := DecorateToolsWithInstructions(tools, instructions, map[string]string{"t1": "srv-mine"}, "s")
	if got[0].Description != "original" {
		t.Errorf("description must stay untouched when nothing matches: %q", got[0].Description)
	}
}

func TestDecorateTools_SuffixCappedPerTool(t *testing.T) {
	tools := []mcp.Tool{{Name: "t1", Description: "original"}}
	instructions := []InstructionView{
		{ID: "g1", Title: "Big", Body: strings.Repeat("x", 3*maxToolInstructionBytes), Kind: db.LLMInstructionRowKindGeneral},
	}
	got := DecorateToolsWithInstructions(tools, instructions, map[string]string{}, "s")
	suffixLen := len(got[0].Description) - len("original")
	if suffixLen > maxToolInstructionBytes {
		t.Errorf("appended suffix exceeds cap: %d > %d", suffixLen, maxToolInstructionBytes)
	}
	if !strings.HasSuffix(got[0].Description, truncationMarker) {
		t.Errorf("truncated suffix should end with the truncation marker: %q", got[0].Description[len(got[0].Description)-40:])
	}
}

func TestToolServerIndex(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:         "srv-ga",
		Name:       "GA",
		ToolPrefix: "ga4",
		Tools: []mcp.Tool{
			{Name: "run_report", IsActive: true},
			{Name: "old_tool", IsActive: false},
		},
	})
	reg.Register(&BackendServer{
		ID:    "srv-hidden",
		Name:  "Hidden",
		Tools: []mcp.Tool{{Name: "secret", IsActive: true}},
	})

	idx := reg.ToolServerIndex(map[string]bool{"srv-ga": true})
	if got := idx["ga4_run_report"]; got != "srv-ga" {
		t.Errorf("expected ga4_run_report → srv-ga, got %q", got)
	}
	if _, ok := idx["ga4_old_tool"]; ok {
		t.Error("inactive tool must not be indexed")
	}
	if _, ok := idx["secret"]; ok {
		t.Error("tool from non-allowed server must not be indexed")
	}
}

// ── ScopedGateway end-to-end behavior of the injection flag ─────────────────

func newInjectionGatewayForTest(t *testing.T) *ScopedGateway {
	t.Helper()
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:         "srv-ga",
		Name:       "GA",
		ToolPrefix: "ga4",
		Tools:      []mcp.Tool{{Name: "run_report", Description: "Run a report.", IsActive: true}},
	})
	gw := New("gw", "1.0", reg)
	return NewScopedGateway(gw, map[string]bool{"srv-ga": true}, nil, []InstructionView{
		{ID: "g1", Title: "Golden rule", Body: "Always explain tool choice.", Kind: db.LLMInstructionRowKindGeneral},
	})
}

func TestInjectionMode_OmitsInitializeInstructions(t *testing.T) {
	sg := newInjectionGatewayForTest(t)
	sg.SetInjectInstructionsIntoTools(true)

	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(context.Background(), req)
	if got := initializeInstructions(t, resp); got != "" {
		t.Errorf("initialize must omit instructions in injection mode, got %q", got)
	}
}

func TestInjectionMode_DefaultKeepsInitializeInstructions(t *testing.T) {
	sg := newInjectionGatewayForTest(t)

	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(context.Background(), req)
	if got := initializeInstructions(t, resp); !strings.Contains(got, "Always explain tool choice.") {
		t.Errorf("default mode must keep initialize instructions, got %q", got)
	}
}

func TestInjectionMode_DecoratesToolsList(t *testing.T) {
	sg := newInjectionGatewayForTest(t)
	sg.SetInjectInstructionsIntoTools(true)

	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "tools/list"}
	resp := sg.Handle(context.Background(), req)
	tools := toolsFromResponse(t, resp)
	if len(tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(tools))
	}
	if !strings.Contains(tools[0].Description, "Always explain tool choice.") {
		t.Errorf("tool description should carry the instruction: %q", tools[0].Description)
	}
}

func TestInjectionMode_DefaultLeavesToolsListUntouched(t *testing.T) {
	sg := newInjectionGatewayForTest(t)

	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "tools/list"}
	resp := sg.Handle(context.Background(), req)
	tools := toolsFromResponse(t, resp)
	if len(tools) != 1 {
		t.Fatalf("expected 1 tool, got %d", len(tools))
	}
	if tools[0].Description != "Run a report." {
		t.Errorf("default mode must not touch tool descriptions: %q", tools[0].Description)
	}
}
