package gateway

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// fakeUsers is an in-memory gatewayUserFinder: email -> role.
type fakeUsers map[string]string

func (f fakeUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	role, ok := f[email]
	if !ok {
		return nil, nil
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

// errUsers always fails, standing in for a DB outage.
type errUsers struct{}

func (errUsers) GetByEmail(string) (*db.GatewayUser, error) {
	return nil, errors.New("db down")
}

func TestGateAllowsEmail(t *testing.T) {
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
		"cfg@hellopro.fr":   auth.RoleConfigOnly,
	}

	cases := []struct {
		name    string
		minRole string
		email   string
		users   gatewayUserFinder
		want    bool
	}{
		{"public server, no email at all", "", "", users, true},
		{"public server, unknown email", "", "ghost@hellopro.fr", users, true},
		{"public server, nil repo", "", "", nil, true},
		{"gated admin, admin user", auth.RoleAdmin, "admin@hellopro.fr", users, true},
		{"gated admin, read-only user", auth.RoleAdmin, "ro@hellopro.fr", users, false},
		{"gated admin, config-only user", auth.RoleAdmin, "cfg@hellopro.fr", users, false},
		{"gated admin, unknown email", auth.RoleAdmin, "ghost@hellopro.fr", users, false},
		{"gated admin, empty email", auth.RoleAdmin, "", users, false},
		{"gated admin, nil repo", auth.RoleAdmin, "admin@hellopro.fr", nil, false},
		{"gated admin, repo error", auth.RoleAdmin, "admin@hellopro.fr", errUsers{}, false},
		{"gated read-only, admin user passes ladder", auth.RoleReadOnly, "admin@hellopro.fr", users, true},
		{"gated read-only, read-only user", auth.RoleReadOnly, "ro@hellopro.fr", users, true},
		{"gated read-only, config-only user", auth.RoleReadOnly, "cfg@hellopro.fr", users, false},
		{"gated config-only, config-only user", auth.RoleConfigOnly, "cfg@hellopro.fr", users, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := GateAllowsEmail(tc.minRole, tc.email, tc.users); got != tc.want {
				t.Fatalf("GateAllowsEmail(%q, %q) = %v, want %v", tc.minRole, tc.email, got, tc.want)
			}
		})
	}
}

func TestGateAllows_ContextForm(t *testing.T) {
	users := fakeUsers{"admin@hellopro.fr": auth.RoleAdmin}

	// No email on the context — this is what a scope token and a
	// client_credentials grant both look like. Gated servers must deny.
	bare := context.Background()
	if GateAllows(auth.RoleAdmin, bare, users) {
		t.Fatal("gated server allowed with no end-user email on context")
	}
	if !GateAllows("", bare, users) {
		t.Fatal("public server denied with no end-user email on context")
	}

	withAdmin := context.WithValue(bare, scopetoken.EndUserEmailContextKey, "admin@hellopro.fr")
	if !GateAllows(auth.RoleAdmin, withAdmin, users) {
		t.Fatal("gated server denied for an admin end user")
	}

	// An empty-string email on the context must not pass as an identity.
	withEmpty := context.WithValue(bare, scopetoken.EndUserEmailContextKey, "")
	if GateAllows(auth.RoleAdmin, withEmpty, users) {
		t.Fatal("gated server allowed with an empty email on context")
	}
}

func TestFilterServersByGate(t *testing.T) {
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
	}
	servers := []db.MCPServer{
		{ID: "pub-1", MinRole: ""},
		{ID: "gated-1", MinRole: auth.RoleAdmin},
		{ID: "pub-2", MinRole: ""},
	}

	ids := func(in []db.MCPServer) []string {
		out := make([]string, 0, len(in))
		for _, s := range in {
			out = append(out, s.ID)
		}
		return out
	}

	got := ids(FilterServersByGate(servers, "admin@hellopro.fr", users))
	if len(got) != 3 {
		t.Fatalf("admin sees %v, want all three", got)
	}

	got = ids(FilterServersByGate(servers, "ro@hellopro.fr", users))
	if len(got) != 2 || got[0] != "pub-1" || got[1] != "pub-2" {
		t.Fatalf("read-only sees %v, want [pub-1 pub-2]", got)
	}

	got = ids(FilterServersByGate(servers, "", users))
	if len(got) != 2 {
		t.Fatalf("anonymous sees %v, want the two public servers", got)
	}

	if out := FilterServersByGate(nil, "admin@hellopro.fr", users); len(out) != 0 {
		t.Fatalf("nil input produced %v", out)
	}

	allGated := []db.MCPServer{{ID: "g1", MinRole: auth.RoleAdmin}}
	if out := FilterServersByGate(allGated, "ro@hellopro.fr", users); len(out) != 0 {
		t.Fatalf("all-gated input produced %v for a read-only viewer", out)
	}
}

// TestScopeTokenPathLeavesEndUserEmailUnset pins the invariant GateAllows
// depends on: only the OAuth2 bearer path writes EndUserEmailContextKey. If a
// future feature starts attaching an owner email to scope-token requests,
// this test fails — and it must, because the gate would otherwise open for
// machine tokens without anyone noticing.
func TestScopeTokenPathLeavesEndUserEmailUnset(t *testing.T) {
	root := "../../internal/scopetoken"
	entries, err := os.ReadDir(root)
	if err != nil {
		t.Fatalf("read %s: %v", root, err)
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".go") || strings.HasSuffix(e.Name(), "_test.go") {
			continue
		}
		src, err := os.ReadFile(filepath.Join(root, e.Name()))
		if err != nil {
			t.Fatalf("read %s: %v", e.Name(), err)
		}
		if strings.Contains(string(src), "context.WithValue(ctx, EndUserEmailContextKey") {
			t.Fatalf("%s writes EndUserEmailContextKey: the scope-token path must never carry an end-user identity, or gateway.GateAllows silently stops excluding scope tokens", e.Name())
		}
	}
}
