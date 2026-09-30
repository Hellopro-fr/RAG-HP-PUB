package gateway

import (
	"context"
	"errors"
	"testing"
	"time"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

// countingTemplates is an in-memory templateRunnerLookup. A slug absent from
// rows returns an error, like gorm.ErrRecordNotFound from the real repo.
type countingTemplates struct {
	rows  map[string]*db.Template
	err   error
	calls int
}

func (f *countingTemplates) GetBySlugAny(slug string) (*db.Template, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	if t, ok := f.rows[slug]; ok {
		return t, nil
	}
	return nil, errors.New("record not found")
}

// countingServerSlugs is an in-memory serverTemplateSlugLookup. An id absent
// from slugs returns "" and no error, like the real repo.
type countingServerSlugs struct {
	slugs map[string]string
	err   error
	calls int
}

func (f *countingServerSlugs) TemplateSlugByID(id string) (string, error) {
	f.calls++
	if f.err != nil {
		return "", f.err
	}
	return f.slugs[id], nil
}

// countingUsers is an in-memory gatewayUserFinder. An email absent from rows
// returns (nil, nil), like the real repo.
type countingUsers struct {
	rows  map[string]*db.GatewayUser
	err   error
	calls int
}

func (f *countingUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.rows[email], nil
}

// countingGrants is an in-memory serverAuthorizer keyed server_id → email.
type countingGrants struct {
	grants map[string]map[string]bool
	calls  int
}

func (f *countingGrants) IsAuthorized(serverID, email string) bool {
	f.calls++
	return f.grants[serverID][email]
}

type neo4jAccessFakes struct {
	templates *countingTemplates
	servers   *countingServerSlugs
	users     *countingUsers
	grants    *countingGrants
}

// newNeo4jAccessFixture wires a policy where "srv-neo4j" is an instance of
// the "neo4j" template (runner neo4j), "srv-ga" an instance of "ga" (runner
// google) and "srv-plain" a regular server. admin@hp.fr is a gateway admin,
// alice@hp.fr holds a grant on srv-neo4j, carol@hp.fr a grant on srv-other.
func newNeo4jAccessFixture() (*Neo4jAccess, *neo4jAccessFakes) {
	f := &neo4jAccessFakes{
		templates: &countingTemplates{rows: map[string]*db.Template{
			"neo4j": {Slug: "neo4j", Runner: "neo4j"},
			"ga":    {Slug: "ga", Runner: "google"},
		}},
		servers: &countingServerSlugs{slugs: map[string]string{
			"srv-neo4j": "neo4j",
			"srv-ga":    "ga",
		}},
		users: &countingUsers{rows: map[string]*db.GatewayUser{
			"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin},
			"bob@hp.fr":   {Email: "bob@hp.fr", Role: "config-only"},
		}},
		grants: &countingGrants{grants: map[string]map[string]bool{
			"srv-neo4j": {"alice@hp.fr": true},
			"srv-other": {"carol@hp.fr": true},
		}},
	}
	return NewNeo4jAccess(f.templates, f.servers, f.users, f.grants), f
}

func TestNeo4jAccess_Restricted(t *testing.T) {
	cases := []struct {
		name    string
		backend *BackendServer
		want    bool
	}{
		{"neo4j runner via slug hint", &BackendServer{ID: "srv-x", TemplateSlug: "neo4j"}, true},
		{"google runner via slug hint", &BackendServer{ID: "srv-x", TemplateSlug: "ga"}, false},
		{"empty registry slug resolved from mcp_servers (neo4j)", &BackendServer{ID: "srv-neo4j"}, true},
		{"empty registry slug resolved from mcp_servers (google)", &BackendServer{ID: "srv-ga"}, false},
		{"regular server (no template_slug anywhere)", &BackendServer{ID: "srv-plain"}, false},
		{"missing template row fails closed", &BackendServer{ID: "srv-x", TemplateSlug: "ghost"}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, _ := newNeo4jAccessFixture()
			if got := a.Restricted(tc.backend); got != tc.want {
				t.Fatalf("Restricted(%+v) = %t, want %t", tc.backend, got, tc.want)
			}
		})
	}
}

func TestNeo4jAccess_RestrictedFailsClosedOnLookupErrors(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.templates.err = errors.New("db down")
	if !a.Restricted(&BackendServer{ID: "srv-ga", TemplateSlug: "ga"}) {
		t.Fatal("template lookup error must count as restricted")
	}

	a, f = newNeo4jAccessFixture()
	f.servers.err = errors.New("db down")
	if !a.Restricted(&BackendServer{ID: "srv-plain"}) {
		t.Fatal("server template_slug lookup error must count as restricted")
	}

	unwired := NewNeo4jAccess(nil, nil, nil, nil)
	if !unwired.Restricted(&BackendServer{ID: "srv-x", TemplateSlug: "ga"}) {
		t.Fatal("unwired template lookup must count as restricted when a slug is present")
	}
	if unwired.Restricted(&BackendServer{ID: "srv-x"}) {
		t.Fatal("unwired policy must not restrict a backend with no slug")
	}
}

func TestNeo4jAccess_Allows(t *testing.T) {
	neo4j := &BackendServer{ID: "srv-neo4j"}
	cases := []struct {
		name  string
		email string
		want  bool
	}{
		{"gateway admin", "admin@hp.fr", true},
		{"grant on this server", "alice@hp.fr", true},
		{"grant on another server only", "carol@hp.fr", false},
		{"known non-admin without grant", "bob@hp.fr", false},
		{"unknown email without grant", "nobody@hp.fr", false},
		{"no end-user email (scope token / client_credentials)", "", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, _ := newNeo4jAccessFixture()
			ctx := context.Background()
			if tc.email != "" {
				ctx = ctxWithEmail(tc.email)
			}
			if got := a.Allows(ctx, neo4j); got != tc.want {
				t.Fatalf("Allows(%q) = %t, want %t", tc.email, got, tc.want)
			}
		})
	}
}

func TestNeo4jAccess_AllowsDeniesOnUserLookupError(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.users.err = errors.New("db down")
	if a.Allows(ctxWithEmail("admin@hp.fr"), &BackendServer{ID: "srv-neo4j"}) {
		t.Fatal("user lookup error must deny an admin without a grant")
	}
}

func TestNeo4jAccess_AdminAllowedWhileLookupsFail(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.templates.err = errors.New("db down")
	f.servers.err = errors.New("db down")
	if !a.Allows(ctxWithEmail("admin@hp.fr"), &BackendServer{ID: "srv-neo4j"}) {
		t.Fatal("an admin must stay allowed while the slug/template lookups fail")
	}
	if !a.AllowsEmail("admin@hp.fr", "srv-x", "ghost") {
		t.Fatal("an admin must stay allowed on an orphan template_slug")
	}
	if f.servers.calls != 0 || f.templates.calls != 0 {
		t.Fatalf("the admin check must run before any lookup, got servers=%d templates=%d", f.servers.calls, f.templates.calls)
	}
}

func TestNeo4jAccess_NonAdminDeniedWhileLookupsFail(t *testing.T) {
	cases := []struct {
		name    string
		breakDB func(f *neo4jAccessFakes)
		backend *BackendServer // unrestricted whenever the DB answers
	}{
		{"template lookup fails", func(f *neo4jAccessFakes) { f.templates.err = errors.New("db down") }, &BackendServer{ID: "srv-ga", TemplateSlug: "ga"}},
		{"server slug lookup fails", func(f *neo4jAccessFakes) { f.servers.err = errors.New("db down") }, &BackendServer{ID: "srv-plain"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, f := newNeo4jAccessFixture()
			tc.breakDB(f)
			if a.Allows(ctxWithEmail("bob@hp.fr"), tc.backend) {
				t.Fatal("non-admin without grant must be denied while the lookup fails")
			}
			if a.Allows(context.Background(), tc.backend) {
				t.Fatal("caller without email must be denied while the lookup fails")
			}
		})
	}
}

func TestNeo4jAccess_GranteeAllowedWhileLookupsFail(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	f.servers.err = errors.New("db down")
	if !a.Allows(ctxWithEmail("alice@hp.fr"), &BackendServer{ID: "srv-neo4j"}) {
		t.Fatal("a failed lookup counts as restricted, so a grant on this exact server still opens it")
	}
}

func TestNeo4jAccess_AllowsDeniesWhenUsersAndGrantsUnwired(t *testing.T) {
	a := NewNeo4jAccess(&countingTemplates{rows: map[string]*db.Template{"neo4j": {Slug: "neo4j", Runner: "neo4j"}}}, nil, nil, nil)
	if a.Allows(ctxWithEmail("admin@hp.fr"), &BackendServer{ID: "srv-neo4j", TemplateSlug: "neo4j"}) {
		t.Fatal("unwired users/grants must deny a restricted backend")
	}
}

func TestNeo4jAccess_UnrestrictedBackendSkipsUserAndGrantLookups(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	for _, b := range []*BackendServer{{ID: "srv-plain"}, {ID: "srv-ga", TemplateSlug: "ga"}} {
		if !a.Allows(context.Background(), b) {
			t.Fatalf("unrestricted backend %s must be allowed without an email", b.ID)
		}
	}
	if f.users.calls != 0 || f.grants.calls != 0 {
		t.Fatalf("unrestricted backends must not hit users/grants, got users=%d grants=%d", f.users.calls, f.grants.calls)
	}
}

func TestNeo4jAccess_NilPolicyAllowsEverything(t *testing.T) {
	var a *Neo4jAccess
	b := &BackendServer{ID: "srv-neo4j", TemplateSlug: "neo4j"}
	if !a.Allows(context.Background(), b) || !a.AllowsEmail("", b.ID, b.TemplateSlug) {
		t.Fatal("nil *Neo4jAccess must allow everything")
	}
	if a.Restricted(b) {
		t.Fatal("nil *Neo4jAccess must restrict nothing")
	}
}

func TestNeo4jAccess_CachesLookupsWithinTTL(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	t0 := time.Date(2026, 9, 30, 12, 0, 0, 0, time.UTC)
	a.now = func() time.Time { return t0 }
	b := &BackendServer{ID: "srv-neo4j"}

	a.Restricted(b)
	a.Restricted(b)
	if f.servers.calls != 1 || f.templates.calls != 1 {
		t.Fatalf("within TTL: want 1 server + 1 template lookup, got servers=%d templates=%d", f.servers.calls, f.templates.calls)
	}

	a.now = func() time.Time { return t0.Add(neo4jAccessCacheTTL + time.Second) }
	a.Restricted(b)
	if f.servers.calls != 2 || f.templates.calls != 2 {
		t.Fatalf("after TTL: want 2 server + 2 template lookups, got servers=%d templates=%d", f.servers.calls, f.templates.calls)
	}
}

func TestNeo4jAccess_DoesNotCacheLookupErrors(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	b := &BackendServer{ID: "srv-ga", TemplateSlug: "ga"}
	f.templates.err = errors.New("db down")
	if !a.Restricted(b) {
		t.Fatal("lookup error must count as restricted")
	}
	f.templates.err = nil
	if a.Restricted(b) {
		t.Fatal("a failed lookup must not be cached — the next call must see runner=google")
	}
	if f.templates.calls != 2 {
		t.Fatalf("want 2 template lookups, got %d", f.templates.calls)
	}
}

func TestNeo4jAccess_GrantRevocationTakesEffectImmediately(t *testing.T) {
	a, f := newNeo4jAccessFixture()
	b := &BackendServer{ID: "srv-neo4j"}
	ctx := ctxWithEmail("alice@hp.fr")
	if !a.Allows(ctx, b) {
		t.Fatal("alice must be allowed while her grant exists")
	}
	delete(f.grants.grants["srv-neo4j"], "alice@hp.fr")
	if a.Allows(ctx, b) {
		t.Fatal("grants must not be cached: revocation must apply on the next request")
	}
}

func TestNeo4jAccess_DenialSlugResolvesEmptyRegistrySlug(t *testing.T) {
	a, _ := newNeo4jAccessFixture()
	if got := a.DenialSlug(&BackendServer{ID: "srv-neo4j"}); got != "neo4j" {
		t.Fatalf("DenialSlug = %q, want neo4j", got)
	}
}
