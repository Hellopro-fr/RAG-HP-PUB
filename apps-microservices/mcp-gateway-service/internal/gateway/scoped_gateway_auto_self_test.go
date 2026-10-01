package gateway

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/ringoveradmin"
	"mcp-gateway/internal/scopetoken"
)

// fakeUserRepo lets the auto-self-override tests stub gateway_users lookups
// without touching GORM. Only GetByEmail is exercised.
type fakeUserRepo struct {
	rows map[string]*db.GatewayUser
}

func (f *fakeUserRepo) GetByEmail(email string) (*db.GatewayUser, error) {
	if u, ok := f.rows[email]; ok {
		return u, nil
	}
	return nil, errors.New("not found")
}

func leexiServerWithAlice(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/admin/users") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"uuid":"u-alice","email":"alice@example.com"}]}`))
	}))
}

func ringoverServerWithBob(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/admin/users") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"user_id":7,"email":"bob@example.com"}]}`))
	}))
}

func ctxWithEmail(email string) context.Context {
	return context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, email)
}

// 1. JWT carries email + Leexi user matches → override admin config (mode=users).
func TestInjectLeexiHeader_AutoSelfOverridesUsersMode(t *testing.T) {
	srv := leexiServerWithAlice(t)
	defer srv.Close()

	sg := &ScopedGateway{leexiAdmin: leexiadmin.NewClient(srv.URL, "tok")}
	ctx := ctxWithEmail("alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob", "u-charlie"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-alice" {
		t.Fatalf("expected u-alice, got %q", got)
	}
}

// 2. JWT email present, no Leexi match, end-user is NOT a gateway admin → deny.
func TestInjectLeexiHeader_NonAdminEmailMissingDeniesAll(t *testing.T) {
	srv := leexiServerWithAlice(t)
	defer srv.Close()

	sg := &ScopedGateway{
		leexiAdmin:   leexiadmin.NewClient(srv.URL, "tok"),
		gatewayUsers: &fakeUserRepo{}, // empty: ghost@ is not in gateway_users
	}
	ctx := ctxWithEmail("ghost@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "00000000-0000-0000-0000-000000000000" {
		t.Fatalf("expected deny-sentinel, got %q", got)
	}
}

// 3. JWT email present, no Leexi match, end-user IS a gateway admin → fall
// back to admin-configured filter (mode=users yields the admin's list).
func TestInjectLeexiHeader_AdminEmailMissingFallsBackToConfig(t *testing.T) {
	srv := leexiServerWithAlice(t)
	defer srv.Close()

	sg := &ScopedGateway{
		leexiAdmin: leexiadmin.NewClient(srv.URL, "tok"),
		gatewayUsers: &fakeUserRepo{rows: map[string]*db.GatewayUser{
			"sysadmin@example.com": {Email: "sysadmin@example.com", Role: auth.RoleAdmin},
		}},
	}
	ctx := ctxWithEmail("sysadmin@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob", "u-charlie"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob,u-charlie" {
		t.Fatalf("expected admin's list, got %q", got)
	}
}

// 4. No email (client_credentials grant) → use admin-configured filter as
// before, no auto-override applied.
func TestInjectLeexiHeader_NoEmailFallsThroughToConfig(t *testing.T) {
	sg := &ScopedGateway{}
	ctx := context.WithValue(context.Background(), scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob" {
		t.Fatalf("expected u-bob (admin-configured), got %q", got)
	}
}

// 5. Same matrix for Ringover — independent backend.
func TestInjectRingoverHeader_AutoSelfOverridesUsersMode(t *testing.T) {
	srv := ringoverServerWithBob(t)
	defer srv.Close()

	sg := &ScopedGateway{ringoverAdmin: ringoveradmin.NewClient(srv.URL, "tok")}
	ctx := ctxWithEmail("bob@example.com")
	ctx = context.WithValue(ctx, scopetoken.RingoverFilterContextKey, &scopetoken.RingoverFilterContext{
		Mode:           "users",
		AllowedUserIDs: []int{99},
	})
	headers := map[string]string{}
	sg.injectRingoverHeader(ctx, headers)
	if got := headers[RingoverAllowedUserIDsHeader]; got != "7" {
		t.Fatalf("expected 7, got %q", got)
	}
}

// 6. Per-backend independence: same user has Leexi but not Ringover, NOT
// gateway admin. Leexi gets override; Ringover denies.
func TestPerBackendIndependence_LeexiOverrideRingoverDeny(t *testing.T) {
	leexiSrv := leexiServerWithAlice(t)
	defer leexiSrv.Close()
	ringoverSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[]}`))
	}))
	defer ringoverSrv.Close()

	sg := &ScopedGateway{
		leexiAdmin:    leexiadmin.NewClient(leexiSrv.URL, "tok"),
		ringoverAdmin: ringoveradmin.NewClient(ringoverSrv.URL, "tok"),
		gatewayUsers:  &fakeUserRepo{},
	}
	ctx := ctxWithEmail("alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{Mode: "none"})
	ctx = context.WithValue(ctx, scopetoken.RingoverFilterContextKey, &scopetoken.RingoverFilterContext{Mode: "none"})

	leexiHeaders := map[string]string{}
	sg.injectLeexiHeader(ctx, leexiHeaders)
	if got := leexiHeaders[LeexiAllowedParticipantsHeader]; got != "u-alice" {
		t.Fatalf("Leexi: expected u-alice, got %q", got)
	}

	ringoverHeaders := map[string]string{}
	sg.injectRingoverHeader(ctx, ringoverHeaders)
	if got := ringoverHeaders[RingoverAllowedUserIDsHeader]; got != "0" {
		t.Fatalf("Ringover: expected deny-sentinel 0, got %q", got)
	}
}
