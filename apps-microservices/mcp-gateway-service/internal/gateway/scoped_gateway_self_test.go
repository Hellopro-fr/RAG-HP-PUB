package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/ringoveradmin"
	"mcp-gateway/internal/scopetoken"
)

// fakeLeexiServer returns one user matching alice@example.com.
func fakeLeexiServer(t *testing.T) *httptest.Server {
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

func fakeRingoverServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/admin/users") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"user_id":42,"email":"alice@example.com"}]}`))
	}))
}

func TestResolveLeexiParticipants_SelfMode_Success(t *testing.T) {
	srv := fakeLeexiServer(t)
	defer srv.Close()

	sg := &ScopedGateway{leexiAdmin: leexiadmin.NewClient(srv.URL, "tok")}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")

	got := sg.resolveLeexiParticipants(ctx, &scopetoken.LeexiFilterContext{Mode: "self"})
	if len(got) != 1 || got[0] != "u-alice" {
		t.Fatalf("expected [u-alice], got %v", got)
	}
}

func TestResolveLeexiParticipants_SelfMode_NoEmailFailsClosed(t *testing.T) {
	sg := &ScopedGateway{}
	got := sg.resolveLeexiParticipants(context.Background(), &scopetoken.LeexiFilterContext{Mode: "self"})
	if got != nil {
		t.Fatalf("expected nil for missing email, got %v", got)
	}
}

func TestResolveLeexiParticipants_SelfMode_UnknownEmailFailsClosed(t *testing.T) {
	srv := fakeLeexiServer(t)
	defer srv.Close()

	sg := &ScopedGateway{leexiAdmin: leexiadmin.NewClient(srv.URL, "tok")}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "ghost@example.com")

	got := sg.resolveLeexiParticipants(ctx, &scopetoken.LeexiFilterContext{Mode: "self"})
	if got != nil {
		t.Fatalf("expected nil for unknown email, got %v", got)
	}
}

func TestResolveRingoverAllowedUsers_SelfMode_Success(t *testing.T) {
	srv := fakeRingoverServer(t)
	defer srv.Close()

	sg := &ScopedGateway{ringoverAdmin: ringoveradmin.NewClient(srv.URL, "tok")}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.com")

	got := sg.resolveRingoverAllowedUsers(ctx, &scopetoken.RingoverFilterContext{Mode: "self"})
	if len(got) != 1 || got[0] != 42 {
		t.Fatalf("expected [42], got %v", got)
	}
}

func TestResolveRingoverAllowedUsers_SelfMode_NoEmailFailsClosed(t *testing.T) {
	sg := &ScopedGateway{}
	got := sg.resolveRingoverAllowedUsers(context.Background(), &scopetoken.RingoverFilterContext{Mode: "self"})
	if got != nil {
		t.Fatalf("expected nil for missing email, got %v", got)
	}
}

func TestResolveRingoverAllowedUsers_SelfMode_UnknownEmailFailsClosed(t *testing.T) {
	srv := fakeRingoverServer(t)
	defer srv.Close()

	sg := &ScopedGateway{ringoverAdmin: ringoveradmin.NewClient(srv.URL, "tok")}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "ghost@example.com")

	got := sg.resolveRingoverAllowedUsers(ctx, &scopetoken.RingoverFilterContext{Mode: "self"})
	if got != nil {
		t.Fatalf("expected nil for unknown email, got %v", got)
	}
}
