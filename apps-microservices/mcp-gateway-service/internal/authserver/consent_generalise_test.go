package authserver

import (
	"context"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

// The hellodata rule "admin OR server_authorizations grant" is not tied to
// hellodata: since min_role is satisfied by a grant (#855), setting
// min_role=admin on ANY server gives it exactly that rule. These tests pin it
// on a generic server — no hellodata tool_prefix, no template — named after
// mcp-normalize-unite, the service that prompted the check.

type fakeGrants map[string]map[string]bool // server_id -> email -> granted

func (f fakeGrants) IsAuthorized(serverID, email string) bool { return f[serverID][email] }

func listIDs(list []authorizeServerDTO) map[string]bool {
	out := make(map[string]bool, len(list))
	for _, s := range list {
		out[s.ID] = true
	}
	return out
}

func generiqueServer(minRole string) *AuthServer {
	s := &AuthServer{
		serverRepo: fakeServerLister{
			{ID: "pub-1", Name: "Public"},
			{ID: "normalize-1", Name: "mcp-normalize-unite", MinRole: minRole},
		},
		userRepo: fakeUsers{
			"admin@hellopro.fr":   auth.RoleAdmin,
			"granted@hellopro.fr": auth.RoleConfigOnly,
			"co@hellopro.fr":      auth.RoleConfigOnly,
		},
	}
	s.SetGrantChecker(fakeGrants{"normalize-1": {"granted@hellopro.fr": true}})
	return s
}

func TestConsentGeneralise_MinRoleAdminIsAdminOrGrant(t *testing.T) {
	s := generiqueServer(auth.RoleAdmin)
	client := &db.OAuth2Client{ID: "c"} // show-all branch
	ctx := context.Background()

	for email, want := range map[string]bool{
		"admin@hellopro.fr":   true,  // admin, no grant
		"granted@hellopro.fr": true,  // config-only + grant
		"co@hellopro.fr":      false, // config-only, no grant
		"":                    false, // no identity
	} {
		got := listIDs(s.buildServerList(ctx, client, email))["normalize-1"]
		if got != want {
			t.Errorf("%q sees normalize-1 = %t, want %t", email, got, want)
		}
	}
}

func TestConsentGeneralise_PublicServerSeenByEveryone(t *testing.T) {
	s := generiqueServer("")
	client := &db.OAuth2Client{ID: "c"}
	for _, email := range []string{"admin@hellopro.fr", "co@hellopro.fr"} {
		if !listIDs(s.buildServerList(context.Background(), client, email))["normalize-1"] {
			t.Errorf("%q should see a public server", email)
		}
	}
}

// A grant on another server never opens this one.
func TestConsentGeneralise_GrantIsPerServer(t *testing.T) {
	s := generiqueServer(auth.RoleAdmin)
	s.SetGrantChecker(fakeGrants{"pub-1": {"co@hellopro.fr": true}})
	if listIDs(s.buildServerList(context.Background(), &db.OAuth2Client{ID: "c"}, "co@hellopro.fr"))["normalize-1"] {
		t.Fatal("a grant on pub-1 must not open normalize-1")
	}
}

// The two ways an ADMIN loses a server on the consent page, unrelated to
// role: the client has a fixed server list that omits it, or min_role holds a
// value that is not a role (fail-closed, admins included).
func TestConsentAdminHidden_ClientFixedListOmitsServer(t *testing.T) {
	s := generiqueServer("")
	client := &db.OAuth2Client{ID: "c2", Servers: []db.OAuth2ClientServer{{ClientID: "c2", ServerID: "pub-1"}}}
	got := listIDs(s.buildServerList(context.Background(), client, "admin@hellopro.fr"))
	if got["normalize-1"] {
		t.Fatal("expected: a client with a fixed list hides servers outside it, even from an admin")
	}
	if !got["pub-1"] {
		t.Fatal("the listed server must still be shown")
	}
}

func TestConsentAdminHidden_UnrecognisedMinRole(t *testing.T) {
	s := generiqueServer("readonly") // not a role: the real one is read-only
	if listIDs(s.buildServerList(context.Background(), &db.OAuth2Client{ID: "c"}, "admin@hellopro.fr"))["normalize-1"] {
		t.Fatal("expected: an unrecognised min_role hides the server from everyone without a grant, admins included")
	}
	// A grant still opens it (#855: role OR grant).
	if !listIDs(s.buildServerList(context.Background(), &db.OAuth2Client{ID: "c"}, "granted@hellopro.fr"))["normalize-1"] {
		t.Fatal("a grant holder should still see it")
	}
}
