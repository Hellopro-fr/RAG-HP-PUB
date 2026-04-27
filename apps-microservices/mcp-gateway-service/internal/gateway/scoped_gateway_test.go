package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"sort"
	"testing"

	"github.com/hellopro/mcp-gateway/internal/db"
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

// ── BDD header injection tests ──────────────────────────────────────────

// stubBDDResolver lets a test enumerate which IDs to honour and which to
// pretend are gone. Anything not present in `tables` triggers a not-found.
type stubBDDResolver struct {
	tables map[string]*db.BDDUsedTable
}

func (s *stubBDDResolver) GetTable(_ context.Context, id string) (*db.BDDUsedTable, error) {
	t, ok := s.tables[id]
	if !ok {
		return nil, errors.New("not found")
	}
	return t, nil
}

// scopedGWWithResolver wires a ScopedGateway with a registry-backed BDD
// backend (ToolPrefix=bdd) plus a resolver. ToolPrefix-only path: the
// header injection logic doesn't touch tools/list, only outbound headers.
func scopedGWWithResolver(t *testing.T, resolver BDDTableResolver) (*ScopedGateway, *BackendServer) {
	t.Helper()
	reg := NewRegistry()
	gw := New("hellopro-mcp-gateway", "0.1.0", reg)
	gw.SetBDDResolver(resolver)
	backend := &BackendServer{ID: "bdd-srv", ToolPrefix: bddToolPrefix}
	return NewScopedGateway(gw, map[string]bool{"bdd-srv": true}, nil, nil), backend
}

func parseBDDHeader(t *testing.T, header string) []bddTablePair {
	t.Helper()
	var got []bddTablePair
	if err := json.Unmarshal([]byte(header), &got); err != nil {
		t.Fatalf("unmarshal bdd header %q: %v", header, err)
	}
	return got
}

func TestRequestHeadersFor_BDDFilterAbsent(t *testing.T) {
	sg, backend := scopedGWWithResolver(t, &stubBDDResolver{})
	headers := sg.requestHeadersFor(context.Background(), backend)
	if _, ok := headers[BDDAllowedTablesHeader]; ok {
		t.Errorf("expected no BDD header when filter absent, got %q", headers[BDDAllowedTablesHeader])
	}
}

func TestRequestHeadersFor_BDDFilterTwoIDsResolveCleanly(t *testing.T) {
	resolver := &stubBDDResolver{tables: map[string]*db.BDDUsedTable{
		"id-1": {DatabaseID: 1, Name: "products"},
		"id-2": {DatabaseID: 5, Name: "leads"},
	}}
	sg, backend := scopedGWWithResolver(t, resolver)
	ctx := context.WithValue(context.Background(), scopetoken.BDDFilterContextKey, []string{"id-1", "id-2"})

	headers := sg.requestHeadersFor(ctx, backend)
	raw, ok := headers[BDDAllowedTablesHeader]
	if !ok {
		t.Fatalf("expected BDD header to be present")
	}
	got := parseBDDHeader(t, raw)
	sort.Slice(got, func(i, j int) bool { return got[i].DatabaseID < got[j].DatabaseID })
	if len(got) != 2 {
		t.Fatalf("expected 2 entries, got %d (%+v)", len(got), got)
	}
	if got[0].DatabaseID != 1 || got[0].TableName != "products" {
		t.Errorf("unexpected entry[0]: %+v", got[0])
	}
	if got[1].DatabaseID != 5 || got[1].TableName != "leads" {
		t.Errorf("unexpected entry[1]: %+v", got[1])
	}
}

func TestRequestHeadersFor_BDDFilterAllRowsDeletedFailsClosed(t *testing.T) {
	// Resolver returns not-found for every requested ID — simulates the
	// case where the registry rows were deleted between cache load and
	// the request. Header MUST be set to "[]" so the backend denies all.
	resolver := &stubBDDResolver{tables: map[string]*db.BDDUsedTable{}}
	sg, backend := scopedGWWithResolver(t, resolver)
	ctx := context.WithValue(context.Background(), scopetoken.BDDFilterContextKey, []string{"ghost-1", "ghost-2"})

	headers := sg.requestHeadersFor(ctx, backend)
	raw, ok := headers[BDDAllowedTablesHeader]
	if !ok {
		t.Fatalf("expected BDD header even when all IDs are gone (fail-closed)")
	}
	if raw != "[]" {
		t.Errorf("expected empty JSON array, got %q", raw)
	}
}

func TestRequestHeadersFor_BDDFilterIgnoredForNonBDDBackend(t *testing.T) {
	resolver := &stubBDDResolver{tables: map[string]*db.BDDUsedTable{
		"id-1": {DatabaseID: 1, Name: "products"},
	}}
	sg, _ := scopedGWWithResolver(t, resolver)
	// Override the backend's prefix to something else — the injector must
	// skip every backend that isn't BDD-tagged.
	other := &BackendServer{ID: "other", ToolPrefix: "ringover"}
	ctx := context.WithValue(context.Background(), scopetoken.BDDFilterContextKey, []string{"id-1"})

	headers := sg.requestHeadersFor(ctx, other)
	if _, ok := headers[BDDAllowedTablesHeader]; ok {
		t.Errorf("expected no BDD header on non-BDD backend, got %q", headers[BDDAllowedTablesHeader])
	}
}
