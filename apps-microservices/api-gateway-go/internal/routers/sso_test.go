package routers

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/sso"
)

func newSSORouter(t *testing.T, accountBase string) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(sessions.Sessions("session", cookie.NewStore([]byte("k"))))
	resolver := sso.NewResolver(sso.ResolverConfig{ServiceName: "api-gateway", AccountBaseURL: accountBase})
	t.Setenv("ACCOUNT_CLIENT_ID", "cid")
	t.Setenv("ACCOUNT_CLIENT_SECRET", "csec")
	RegisterSSO(r, SSODeps{
		Resolver:        resolver,
		AccountBaseURL:  accountBase,
		AccountPubURL:   accountBase,
		AccountRedirect: "http://gw/auth/callback",
		SecureCookie:    false,
	})
	return r
}

func TestAuthLoginRedirects(t *testing.T) {
	r := newSSORouter(t, "http://acct")
	req := httptest.NewRequest("GET", "/auth/login", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusFound, w.Code)
	loc := w.Header().Get("Location")
	require.Contains(t, loc, "http://acct/authorize")
	parsed, err := url.Parse(loc)
	require.NoError(t, err)
	q := parsed.Query()
	require.Equal(t, "code", q.Get("response_type"))
	require.Equal(t, "cid", q.Get("client_id"))
	require.Equal(t, "S256", q.Get("code_challenge_method"))
	require.NotEmpty(t, q.Get("state"))
	require.NotEmpty(t, q.Get("code_challenge"))
	// Set-Cookie is a multi-value header; join all values before asserting.
	cookies := strings.Join(w.Header().Values("Set-Cookie"), " ")
	require.Contains(t, cookies, "auth_verifier=")
	require.Contains(t, cookies, "auth_state=")
}
