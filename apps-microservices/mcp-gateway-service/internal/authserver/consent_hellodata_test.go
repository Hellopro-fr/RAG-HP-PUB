package authserver

import (
	"reflect"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

// newHellodataGatePolicy : "srv-hd" est le backend hellodata, reconnu par
// son tool_prefix lu en base (le consentement ne tient que l'id).
// admin@hp.fr est admin, alice@hp.fr a un grant sur srv-hd, carol@hp.fr un
// grant sur srv-plain seulement.
func newHellodataGatePolicy() *gateway.Neo4jAccess {
	return gateway.NewNeo4jAccess(
		gateTemplates{rows: map[string]*db.Template{}},
		gateServers{prefixes: map[string]string{"srv-hd": "hellodata"}},
		gateUsers{rows: map[string]*db.GatewayUser{
			"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin, IsAllowed: true},
			"bob@hp.fr":   {Email: "bob@hp.fr", Role: "readonly", IsAllowed: true},
		}},
		gateGrants{grants: map[string]map[string]bool{
			"srv-hd":    {"alice@hp.fr": true},
			"srv-plain": {"carol@hp.fr": true},
		}},
	)
}

// Le tool_prefix des lignes est volontairement laisse vide : la politique
// doit le relire par l'id, comme pour une soumission de consentement.
func hellodataServerRows() []db.MCPServer {
	return []db.MCPServer{
		{ID: "srv-hd", Name: "HelloData"},
		{ID: "srv-plain", Name: "Plain"},
	}
}

func TestConsent_HellodataMasqueSansGrant(t *testing.T) {
	for _, email := range []string{"bob@hp.fr", "carol@hp.fr", ""} {
		got := serverIDs(visibleServers(hellodataServerRows(), newHellodataGatePolicy(), email))
		if want := []string{"srv-plain"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("viewer %q: got %v, want %v", email, got, want)
		}
	}
}

func TestConsent_HellodataVisiblePourAdminEtGrant(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		got := serverIDs(visibleServers(hellodataServerRows(), newHellodataGatePolicy(), email))
		if want := []string{"srv-hd", "srv-plain"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("viewer %q: got %v, want %v", email, got, want)
		}
	}
}

// Une soumission forgee (scope pre-configure ou requete faite a la main) ne
// peut pas stocker hellodata pour un lecteur sans grant.
func TestConsent_HellodataRetireDuScopeSoumis(t *testing.T) {
	in := ConsentScope{
		ServerIDs: []string{"srv-hd", "srv-plain"},
		ServerTools: []ServerToolSelection{
			{ServerID: "srv-hd", ToolNames: []string{"compter"}},
		},
	}
	got := filterScopeForViewer(in, newHellodataGatePolicy(), "bob@hp.fr")
	if want := (ConsentScope{ServerIDs: []string{"srv-plain"}}); !reflect.DeepEqual(got, want) {
		t.Fatalf("got %+v, want %+v", got, want)
	}
	if got := filterScopeForViewer(in, newHellodataGatePolicy(), "alice@hp.fr"); !reflect.DeepEqual(got, in) {
		t.Fatalf("le scope du titulaire du grant doit rester intact, got %+v", got)
	}
}
