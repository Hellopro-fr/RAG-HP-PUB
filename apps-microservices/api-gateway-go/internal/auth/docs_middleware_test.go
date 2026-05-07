package auth

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func newDocsRouter(j *JWT) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	store := cookie.NewStore([]byte("secret"))
	r.Use(sessions.Sessions("session", store))
	r.Use(DocsAuthMiddleware(j))
	r.GET("/docs", func(c *gin.Context) { c.String(200, "ok") })
	r.GET("/openapi.json", func(c *gin.Context) { c.String(200, "ok") })
	r.GET("/openapi-public.json", func(c *gin.Context) { c.String(200, "open") })
	r.GET("/login", func(c *gin.Context) { c.String(200, "login-page") })
	return r
}

func TestDocsRedirectsWhenNoSession(t *testing.T) {
	r := newDocsRouter(NewJWT("s", "HS256", time.Minute))
	req := httptest.NewRequest("GET", "/docs", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusFound, w.Code)
	require.Equal(t, "/login", w.Header().Get("Location"))
}

func TestDocsLetsThroughPublicSpec(t *testing.T) {
	r := newDocsRouter(NewJWT("s", "HS256", time.Minute))
	req := httptest.NewRequest("GET", "/openapi-public.json", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	require.Equal(t, "open", w.Body.String())
}
