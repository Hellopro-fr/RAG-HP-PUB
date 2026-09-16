package gateway

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// endUserEmailContextKeyWritePattern matches a context.WithValue(...) call
// whose second argument is EndUserEmailContextKey, regardless of what the
// first argument (the parent context) is named or shaped — ctx, parent,
// reqCtx, c, r.Context(), req.Context(), etc. A plain substring match on
// "context.WithValue(ctx, EndUserEmailContextKey" would miss every one of
// those spellings.
//
// Known gap: the first-argument class is [^,]+, which stops at the first
// top-level comma. That's fine for r.Context()/req.Context() (no comma
// inside), but a first argument that itself contains a comma — e.g.
// context.WithValue(foo(a, b), EndUserEmailContextKey, e) — is NOT matched.
// No call site in this codebase does that today; if one ever does, this
// pattern silently misses it, so treat this comment as the limit of what
// TestScopeTokenPathLeavesEndUserEmailUnset actually proves, not a general
// "handles any expression" guarantee.
var endUserEmailContextKeyWritePattern = regexp.MustCompile(`context\.WithValue\(\s*[^,]+\s*,\s*EndUserEmailContextKey\b`)

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

// TestEndUserEmailContextKeyPattern proves endUserEmailContextKeyWritePattern
// can actually fail: each case here encodes a spelling that previously
// slipped through an earlier, weaker version of this check. Without this
// control, TestScopeTokenPathLeavesEndUserEmailUnset would be re-shipping
// the same unfalsifiable guarantee in fancier form.
//
// History: round 1 hardcoded the substring "context.WithValue(ctx,
// EndUserEmailContextKey", missing any other parent-context name. Round 2's
// replacement, `[^,)]+`, still excluded ')' from the first argument, so it
// missed the r.Context() / req.Context() idiom — arguably the MORE common
// spelling in HTTP-handler code, and the exact kind of code this test exists
// to police. The current pattern uses `[^,]+` instead, which tolerates the
// closing paren of a no-arg method call.
func TestEndUserEmailContextKeyPattern(t *testing.T) {
	positives := []string{
		`return context.WithValue(ctx, EndUserEmailContextKey, email)`,
		`return context.WithValue(parent, EndUserEmailContextKey, email)`,
		`return context.WithValue(r.Context(), EndUserEmailContextKey, e)`,
		`return context.WithValue(req.Context(), EndUserEmailContextKey, e)`,
	}
	for _, src := range positives {
		if !endUserEmailContextKeyWritePattern.MatchString(src) {
			t.Fatalf("pattern did not match known-positive write: %s", src)
		}
	}

	negative := `return context.WithValue(ctx, ScopeNameContextKey, name)`
	if endUserEmailContextKeyWritePattern.MatchString(negative) {
		t.Fatal("pattern matched an unrelated context.WithValue call")
	}

	// Known, documented gap (see the pattern's doc comment): a first
	// argument containing a top-level comma is not matched. Pinned here so
	// a future tightening of the pattern is a deliberate choice, not an
	// unnoticed behavior change.
	knownGap := `return context.WithValue(foo(a, b), EndUserEmailContextKey, e)`
	if endUserEmailContextKeyWritePattern.MatchString(knownGap) {
		t.Fatal("pattern unexpectedly matched a first argument with a top-level comma — update the doc comment, this is no longer a known gap")
	}
}

// TestScopeTokenPathLeavesEndUserEmailUnset pins the invariant GateAllows
// depends on: no file in package scopetoken (other than its own tests) writes
// EndUserEmailContextKey via context.WithValue, under any parent-context
// variable name.
//
// Scope: this only guards package scopetoken against growing such a write.
// It does NOT and cannot observe the one legitimate write, in
// internal/oauth2/middleware.go:245 — that file is outside this package by
// design, since only the OAuth2 bearer path is supposed to carry an end-user
// identity. If a future feature starts attaching an owner email to
// scope-token requests from inside package scopetoken, this test fails, and
// it must: gateway.GateAllows would otherwise silently stop excluding
// scope tokens and client_credentials grants from gated servers.
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
		if endUserEmailContextKeyWritePattern.Match(src) {
			t.Fatalf("%s writes EndUserEmailContextKey: the scope-token path must never carry an end-user identity, or gateway.GateAllows silently stops excluding scope tokens", e.Name())
		}
	}
}
