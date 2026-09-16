package gateway

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/scopetoken"
)

// newGateTestGateway builds a ScopedGateway over one public and one
// admin-gated backend, both in scope.
func newGateTestGateway(users gatewayUserFinder) *ScopedGateway {
	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:    "pub-1",
		Name:  "Public",
		Tools: []mcp.Tool{{Name: "pub_tool", IsActive: true}},
	})
	reg.Register(&BackendServer{
		ID:      "gated-1",
		Name:    "Gated",
		MinRole: auth.RoleAdmin,
		Tools:   []mcp.Tool{{Name: "gated_tool", IsActive: true}},
	})
	return &ScopedGateway{
		registry:     reg,
		allowedIDs:   map[string]bool{"pub-1": true, "gated-1": true},
		gatewayUsers: users,
	}
}

func toolNames(t *testing.T, resp *mcp.Response) []string {
	t.Helper()
	if resp.Error != nil {
		t.Fatalf("tools/list returned an error: %v", resp.Error)
	}
	// mcp.Response.Result is json.RawMessage (internal/mcp/types.go:17),
	// so it unmarshals directly — no intermediate Marshal.
	var out mcp.ListToolsResult
	if err := json.Unmarshal(resp.Result, &out); err != nil {
		t.Fatalf("unmarshal result: %v", err)
	}
	names := make([]string, 0, len(out.Tools))
	for _, tl := range out.Tools {
		names = append(names, tl.Name)
	}
	return names
}

func TestToolsList_OmitsGatedBackendForNonAdmin(t *testing.T) {
	users := fakeUsers{"ro@hellopro.fr": auth.RoleReadOnly}
	sg := newGateTestGateway(users)

	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "ro@hellopro.fr")
	names := toolNames(t, sg.handleToolsList(ctx, &mcp.Request{ID: json.RawMessage(`1`)}))

	for _, n := range names {
		if n == "gated_tool" {
			t.Fatalf("read-only user sees gated_tool in %v", names)
		}
	}
	found := false
	for _, n := range names {
		if n == "pub_tool" {
			found = true
		}
	}
	if !found {
		t.Fatalf("public tool missing from %v", names)
	}
}

func TestToolsList_KeepsGatedBackendForAdmin(t *testing.T) {
	users := fakeUsers{"admin@hellopro.fr": auth.RoleAdmin}
	sg := newGateTestGateway(users)

	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "admin@hellopro.fr")
	names := toolNames(t, sg.handleToolsList(ctx, &mcp.Request{ID: json.RawMessage(`1`)}))

	found := false
	for _, n := range names {
		if n == "gated_tool" {
			found = true
		}
	}
	if !found {
		t.Fatalf("admin does not see gated_tool in %v", names)
	}
}

// A scope token puts no email on the context: the gated backend must vanish.
func TestToolsList_OmitsGatedBackendForScopeToken(t *testing.T) {
	sg := newGateTestGateway(fakeUsers{"admin@hellopro.fr": auth.RoleAdmin})

	names := toolNames(t, sg.handleToolsList(context.Background(), &mcp.Request{ID: json.RawMessage(`1`)}))
	for _, n := range names {
		if n == "gated_tool" {
			t.Fatalf("scope token sees gated_tool in %v", names)
		}
	}
}

func TestToolsCall_DeniesGatedBackendForNonAdmin(t *testing.T) {
	users := fakeUsers{"ro@hellopro.fr": auth.RoleReadOnly}
	sg := newGateTestGateway(users)

	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "ro@hellopro.fr")
	req := &mcp.Request{
		ID:     json.RawMessage(`1`),
		Params: json.RawMessage(`{"name":"gated_tool","arguments":{}}`),
	}
	resp := sg.handleToolsCall(ctx, req)

	if resp.Error == nil {
		t.Fatal("expected an MCP error for a gated backend, got success")
	}
	if !strings.Contains(strings.ToLower(resp.Error.Message), "not allowed") {
		t.Fatalf("error message = %q, want it to say the call is not allowed", resp.Error.Message)
	}
}

func TestToolsCall_DeniesGatedBackendForScopeToken(t *testing.T) {
	sg := newGateTestGateway(fakeUsers{"admin@hellopro.fr": auth.RoleAdmin})

	req := &mcp.Request{
		ID:     json.RawMessage(`1`),
		Params: json.RawMessage(`{"name":"gated_tool","arguments":{}}`),
	}
	resp := sg.handleToolsCall(context.Background(), req)

	if resp.Error == nil {
		t.Fatal("scope token reached a gated backend")
	}
	// Assert on the message, not just non-nil: the test backend has no
	// MessageURL, so a missing gate would still fall through to
	// requestHeadersFor -> transport.NewBackendClientWithEndpoint("", ...)
	// -> client.CallTool, which fails on the empty endpoint and returns a
	// non-nil error for an entirely unrelated (transport) reason. Checking
	// the message is what pins this test to the gate specifically.
	if !strings.Contains(strings.ToLower(resp.Error.Message), "not allowed") {
		t.Fatalf("error message = %q, want it to say the call is not allowed", resp.Error.Message)
	}
}
