package authserver

import (
	"errors"
	"reflect"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

// gateTemplates / gateServers / gateUsers / gateGrants are the in-memory
// collaborators of a real *gateway.Neo4jAccess used by the consent tests.
type gateTemplates struct{ rows map[string]*db.Template }

func (f gateTemplates) GetBySlugAny(slug string) (*db.Template, error) {
	if t, ok := f.rows[slug]; ok {
		return t, nil
	}
	return nil, errors.New("record not found")
}

type gateServers struct{ slugs, prefixes map[string]string }

func (f gateServers) AccessKeysByID(id string) (string, string, error) {
	return f.slugs[id], f.prefixes[id], nil
}

type gateUsers struct{ rows map[string]*db.GatewayUser }

func (f gateUsers) GetByEmail(email string) (*db.GatewayUser, error) { return f.rows[email], nil }

type gateGrants struct{ grants map[string]map[string]bool }

func (f gateGrants) IsAuthorized(serverID, email string) bool { return f.grants[serverID][email] }

// newGatePolicy: "srv-neo4j" is a Neo4j template instance, "srv-ga" a GA4
// instance (google runner), "srv-plain" a regular server. admin@hp.fr is a
// gateway admin, alice@hp.fr holds a grant on srv-neo4j.
func newGatePolicy() *gateway.Neo4jAccess {
	return gateway.NewNeo4jAccess(
		gateTemplates{rows: map[string]*db.Template{
			"neo4j": {Slug: "neo4j", Runner: "neo4j"},
			"ga":    {Slug: "ga", Runner: "google"},
		}},
		gateServers{slugs: map[string]string{"srv-neo4j": "neo4j", "srv-ga": "ga"}},
		gateUsers{rows: map[string]*db.GatewayUser{"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin, IsAllowed: true}}},
		gateGrants{grants: map[string]map[string]bool{"srv-neo4j": {"alice@hp.fr": true}}},
	)
}

func gateServerRows() []db.MCPServer {
	return []db.MCPServer{
		{ID: "srv-neo4j", Name: "Neo4j prod", TemplateSlug: "neo4j"},
		{ID: "srv-ga", Name: "GA4", TemplateSlug: "ga"},
		{ID: "srv-plain", Name: "Plain"},
	}
}

func serverIDs(servers []db.MCPServer) []string {
	out := make([]string, 0, len(servers))
	for _, s := range servers {
		out = append(out, s.ID)
	}
	return out
}

func TestVisibleServers_HidesNeo4jInstanceFromDeniedViewers(t *testing.T) {
	for _, email := range []string{"bob@hp.fr", "", "anonymous@client-1"} {
		got := serverIDs(visibleServers(gateServerRows(), newGatePolicy(), email))
		if want := []string{"srv-ga", "srv-plain"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("viewer %q: got %v, want %v", email, got, want)
		}
	}
}

func TestVisibleServers_ShowsNeo4jInstanceToAdminAndGrantee(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		got := serverIDs(visibleServers(gateServerRows(), newGatePolicy(), email))
		if want := []string{"srv-neo4j", "srv-ga", "srv-plain"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("viewer %q: got %v, want %v", email, got, want)
		}
	}
}

func TestVisibleServers_NilPolicyKeepsEveryServer(t *testing.T) {
	got := serverIDs(visibleServers(gateServerRows(), nil, "bob@hp.fr"))
	if want := []string{"srv-neo4j", "srv-ga", "srv-plain"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestFilterScopeForViewer_DropsHiddenServerAndItsTools(t *testing.T) {
	in := ConsentScope{
		ServerIDs: []string{"srv-neo4j", "srv-plain"},
		ServerTools: []ServerToolSelection{
			{ServerID: "srv-neo4j", ToolNames: []string{"read_neo4j_cypher"}},
			{ServerID: "srv-plain", ToolNames: []string{"echo"}},
		},
	}
	got := filterScopeForViewer(in, newGatePolicy(), "bob@hp.fr")
	want := ConsentScope{
		ServerIDs:   []string{"srv-plain"},
		ServerTools: []ServerToolSelection{{ServerID: "srv-plain", ToolNames: []string{"echo"}}},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %+v, want %+v", got, want)
	}

	if got := filterScopeForViewer(in, newGatePolicy(), "alice@hp.fr"); !reflect.DeepEqual(got, in) {
		t.Fatalf("grantee scope must be unchanged, got %+v", got)
	}
	if got := filterScopeForViewer(in, nil, "bob@hp.fr"); !reflect.DeepEqual(got, in) {
		t.Fatalf("nil policy must leave the scope unchanged, got %+v", got)
	}
}
