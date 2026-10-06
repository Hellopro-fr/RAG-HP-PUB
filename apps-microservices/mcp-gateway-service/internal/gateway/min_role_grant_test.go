package gateway

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/scopetoken"
)

// A server_authorizations grant satisfies the server's min_role: access is
// "role >= min_role OR grant on this server". Pinned here because the two
// were ANDed before, which made a grant useless on a gated server.

func TestGateOrGrantAllowsEmail(t *testing.T) {
	users := fakeUsers{"co@hellopro.fr": auth.RoleConfigOnly, "admin@hellopro.fr": auth.RoleAdmin}
	grants := &fakeServerAuth{grants: map[string]map[string]bool{"gated-1": {"co@hellopro.fr": true}}}

	cases := []struct {
		name, minRole, server, email string
		grants                       GrantChecker
		want                         bool
	}{
		{"grant lifts a config-only user past min_role admin", auth.RoleAdmin, "gated-1", "co@hellopro.fr", grants, true},
		{"admin passes without a grant", auth.RoleAdmin, "gated-1", "admin@hellopro.fr", grants, true},
		{"grant on another server does not count", auth.RoleAdmin, "gated-2", "co@hellopro.fr", grants, false},
		{"no grants wired keeps the role-only gate", auth.RoleAdmin, "gated-1", "co@hellopro.fr", nil, false},
		{"empty email never matches a grant", auth.RoleAdmin, "gated-1", "", grants, false},
		{"unknown min_role still allows a grant holder", "readonly", "gated-1", "co@hellopro.fr", grants, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := GateOrGrantAllowsEmail(c.minRole, c.server, c.email, users, c.grants); got != c.want {
				t.Fatalf("got %t, want %t", got, c.want)
			}
		})
	}
}

func TestFilterServersByGate_GrantShowsGatedServer(t *testing.T) {
	users := fakeUsers{"co@hellopro.fr": auth.RoleConfigOnly}
	grants := &fakeServerAuth{grants: map[string]map[string]bool{"gated-1": {"co@hellopro.fr": true}}}
	servers := []db.MCPServer{
		{ID: "pub-1"},
		{ID: "gated-1", MinRole: auth.RoleAdmin},
		{ID: "gated-2", MinRole: auth.RoleAdmin},
	}

	got := FilterServersByGate(servers, "co@hellopro.fr", users, grants)
	if len(got) != 2 || got[0].ID != "pub-1" || got[1].ID != "gated-1" {
		t.Fatalf("got %v, want [pub-1 gated-1]", got)
	}
}

func grantedGateGateway() *ScopedGateway {
	sg := newGateTestGateway(fakeUsers{"co@hellopro.fr": auth.RoleConfigOnly})
	sg.serverAuth = &fakeServerAuth{grants: map[string]map[string]bool{"gated-1": {"co@hellopro.fr": true}}}
	return sg
}

func TestToolsList_GrantShowsGatedBackend(t *testing.T) {
	sg := grantedGateGateway()
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "co@hellopro.fr")

	names := toolNames(t, sg.handleToolsList(ctx, &mcp.Request{ID: json.RawMessage(`1`)}))
	found := false
	for _, n := range names {
		if n == "gated_tool" {
			found = true
		}
	}
	if !found {
		t.Fatalf("grant holder does not see gated_tool in %v", names)
	}
}

func TestToolsCall_GrantPassesMinRoleGate(t *testing.T) {
	sg := grantedGateGateway()
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "co@hellopro.fr")
	req := &mcp.Request{ID: json.RawMessage(`1`), Params: json.RawMessage(`{"name":"gated_tool","arguments":{}}`)}

	resp := sg.handleToolsCall(ctx, req)
	// The test backend has no URL, so the forward itself fails; what matters
	// is that the refusal is not the min_role one.
	if resp.Error != nil && strings.Contains(resp.Error.Message, "requires the gateway role") {
		t.Fatalf("grant holder refused by the min_role gate: %q", resp.Error.Message)
	}
}

// Scope tokens carry no end-user email, so no grant can match: the gated
// backend stays hidden even when a grant exists for some email.
func TestToolsList_GrantDoesNotOpenScopeTokens(t *testing.T) {
	sg := grantedGateGateway()
	names := toolNames(t, sg.handleToolsList(context.Background(), &mcp.Request{ID: json.RawMessage(`1`)}))
	for _, n := range names {
		if n == "gated_tool" {
			t.Fatalf("email-less caller sees gated_tool in %v", names)
		}
	}
}
