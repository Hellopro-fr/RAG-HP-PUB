package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/scopetoken"
)

// fakeServerAuth implements serverAuthorizer in-memory for tests.
type fakeServerAuth struct {
	grants map[string]map[string]bool // server_id -> email -> true
}

func (f *fakeServerAuth) IsAuthorized(serverID, email string) bool {
	if f.grants == nil {
		return false
	}
	emails, ok := f.grants[serverID]
	if !ok {
		return false
	}
	return emails[email]
}

// 1. With a grant for (server_id, email) → headers contain ONLY the static
// auth headers, no Leexi participants header.
func TestRequestHeadersFor_ServerAuthBypassesLeexiInjection(t *testing.T) {
	leexiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatalf("unexpected leexi /admin/users hit (bypass should skip)")
	}))
	defer leexiSrv.Close()

	sg := &ScopedGateway{
		leexiAdmin: leexiadmin.NewClient(leexiSrv.URL, "tok"),
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-leexi": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-leexi",
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{"X-Static-Auth": "secret"},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")

	headers := sg.requestHeadersFor(ctx, backend)
	if _, present := headers[LeexiAllowedParticipantsHeader]; present {
		t.Fatalf("expected no Leexi header on bypass, got %v", headers)
	}
	if got := headers["X-Static-Auth"]; got != "secret" {
		t.Fatalf("static auth header missing or wrong: %q", got)
	}
}

// 2. No grant + admin-configured filter present → existing inject runs.
func TestRequestHeadersFor_NoGrantUsesExistingInjection(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{}, // empty grants
	}
	backend := &BackendServer{
		ID:          "srv-leexi",
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})

	// Without a Leexi admin client, tryAutoSelf returns ("", false) → falls
	// through to admin config. Filter resolves to u-bob (admin's list).
	headers := sg.requestHeadersFor(ctx, backend)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob" {
		t.Fatalf("expected u-bob, got %q", got)
	}
}

// 3. No email in ctx (client_credentials) → grant lookup returns false → falls
// through to existing path.
func TestRequestHeadersFor_NoEmailFallsThrough(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-leexi": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-leexi",
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})
	headers := sg.requestHeadersFor(ctx, backend)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob" {
		t.Fatalf("expected u-bob (no-email fall-through), got %q", got)
	}
}

// 4. Grant for ringover backend bypasses Ringover header injection too.
func TestRequestHeadersFor_ServerAuthBypassesRingover(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-ringover": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-ringover",
		ToolPrefix:  ringoverToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	headers := sg.requestHeadersFor(ctx, backend)
	if _, present := headers[RingoverAllowedUserIDsHeader]; present {
		t.Fatalf("expected no Ringover header on bypass, got %v", headers)
	}
}

// 5. Grant for BDD backend bypasses BDD header injection.
func TestRequestHeadersFor_ServerAuthBypassesBDD(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-bdd": {"alice@example.com": true},
		}},
	}
	backend := &BackendServer{
		ID:          "srv-bdd",
		ToolPrefix:  bddToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.BDDFilterContextKey, []string{"id-1"})
	headers := sg.requestHeadersFor(ctx, backend)
	if _, present := headers[BDDAllowedTablesHeader]; present {
		t.Fatalf("expected no BDD header on bypass, got %v", headers)
	}
}

// 6. Per-server granularity: grant for srv-1 does NOT bypass srv-2.
func TestRequestHeadersFor_GrantIsPerServer(t *testing.T) {
	leexiSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"uuid":"u-alice","email":"alice@example.com"}]}`))
	}))
	defer leexiSrv.Close()

	sg := &ScopedGateway{
		leexiAdmin: leexiadmin.NewClient(leexiSrv.URL, "tok"),
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-1": {"alice@example.com": true},
		}},
	}
	backendOther := &BackendServer{
		ID:          "srv-2", // not granted
		ToolPrefix:  leexiToolPrefix,
		AuthHeaders: map[string]string{},
	}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{Mode: "none"})

	headers := sg.requestHeadersFor(ctx, backendOther)
	// Auto-self override on srv-2 should still inject u-alice (no bypass).
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-alice" {
		t.Fatalf("srv-2 should auto-self-filter alice (not bypass), got %q", got)
	}
}
