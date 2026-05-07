package sso

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestResolveCredentialsFromServiceEnv(t *testing.T) {
	t.Setenv("ACCOUNT_CLIENT_ID_API_GATEWAY", "id1")
	t.Setenv("ACCOUNT_CLIENT_SECRET_API_GATEWAY", "secret1")

	r := NewResolver(ResolverConfig{ServiceName: "api-gateway", AccountBaseURL: "http://x"})
	c, err := r.Resolve(context.Background())
	require.NoError(t, err)
	require.Equal(t, "id1", c.ClientID)
	require.Equal(t, "secret1", c.ClientSecret)
}

func TestResolveCredentialsFallbackToGeneric(t *testing.T) {
	t.Setenv("ACCOUNT_CLIENT_ID", "g")
	t.Setenv("ACCOUNT_CLIENT_SECRET", "gs")

	r := NewResolver(ResolverConfig{ServiceName: "api-gateway", AccountBaseURL: "http://x"})
	c, err := r.Resolve(context.Background())
	require.NoError(t, err)
	require.Equal(t, "g", c.ClientID)
	require.Equal(t, "gs", c.ClientSecret)
}

func TestResolveCredentialsHTTPFallback(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/internal/credentials/api-gateway", r.URL.Path)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"client_id":     "from-api",
			"client_secret": "from-api-secret",
			"redirect_uris": []string{"http://cb"},
		})
	}))
	defer srv.Close()

	r := NewResolver(ResolverConfig{ServiceName: "api-gateway", AccountBaseURL: srv.URL})
	c, err := r.Resolve(context.Background())
	require.NoError(t, err)
	require.Equal(t, "from-api", c.ClientID)
	require.Equal(t, "from-api-secret", c.ClientSecret)
	require.Equal(t, []string{"http://cb"}, c.RedirectURIs)
}
