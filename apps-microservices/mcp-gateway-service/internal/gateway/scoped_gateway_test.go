package gateway

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/hellopro/mcp-gateway/internal/mcp"
	"github.com/hellopro/mcp-gateway/internal/scopetoken"
)

func newScopedGatewayForTest(t *testing.T) *ScopedGateway {
	t.Helper()
	reg := NewRegistry()
	gw := New("hellopro-mcp-gateway", "0.1.0", reg)
	return NewScopedGateway(gw, map[string]bool{}, nil, nil)
}

func initializeName(t *testing.T, resp *mcp.Response) string {
	t.Helper()
	if resp == nil || resp.Error != nil {
		t.Fatalf("unexpected error response: %+v", resp)
	}
	raw, err := json.Marshal(resp.Result)
	if err != nil {
		t.Fatalf("marshal result: %v", err)
	}
	var out mcp.InitializeResult
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("unmarshal result: %v", err)
	}
	return out.ServerInfo.Name
}

func TestHandleInitializeUsesScopeNameFromContext(t *testing.T) {
	sg := newScopedGatewayForTest(t)
	ctx := context.WithValue(context.Background(), scopetoken.ScopeNameContextKey, "leexi-readonly")

	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(ctx, req)

	if got := initializeName(t, resp); got != "leexi-readonly" {
		t.Errorf("expected serverInfo.name=leexi-readonly, got %q", got)
	}
}

func TestHandleInitializeFallsBackToStaticName(t *testing.T) {
	sg := newScopedGatewayForTest(t)
	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(context.Background(), req)

	if got := initializeName(t, resp); got != "hellopro-mcp-gateway" {
		t.Errorf("expected static name fallback, got %q", got)
	}
}

func TestHandleInitializeIgnoresEmptyScopeName(t *testing.T) {
	sg := newScopedGatewayForTest(t)
	ctx := context.WithValue(context.Background(), scopetoken.ScopeNameContextKey, "")
	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(ctx, req)

	if got := initializeName(t, resp); got != "hellopro-mcp-gateway" {
		t.Errorf("expected static name when ctx value empty, got %q", got)
	}
}

// initializeInstructions extracts the `instructions` field for easy assertion.
func initializeInstructions(t *testing.T, resp *mcp.Response) string {
	t.Helper()
	raw, _ := json.Marshal(resp.Result)
	var out mcp.InitializeResult
	_ = json.Unmarshal(raw, &out)
	return out.Instructions
}

func TestHandleInitializeEmitsComposedInstructions(t *testing.T) {
	reg := NewRegistry()
	gw := New("gw", "1.0", reg)
	sg := NewScopedGateway(gw, map[string]bool{}, nil, []InstructionView{
		{ID: "1", Title: "Prefer search", Body: "Use search_* before list_*."},
		{ID: "2", Title: "Batch", Body: "Batch in groups of 5."},
	})

	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(context.Background(), req)

	got := initializeInstructions(t, resp)
	want := "## Prefer search\nUse search_* before list_*.\n\n## Batch\nBatch in groups of 5."
	if got != want {
		t.Errorf("instructions mismatch\n got=%q\nwant=%q", got, want)
	}
}

func TestHandleInitializeEmptyInstructionsOmitsField(t *testing.T) {
	sg := newScopedGatewayForTest(t)
	req := &mcp.Request{ID: json.RawMessage(`1`), Method: "initialize"}
	resp := sg.Handle(context.Background(), req)

	// When no instructions are attached, the JSON should omit the field
	// entirely thanks to `omitempty`.
	raw, _ := json.Marshal(resp.Result)
	if got := string(raw); got == "" || contains(got, `"instructions"`) {
		t.Errorf("instructions field should be omitted when empty, got %s", got)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
