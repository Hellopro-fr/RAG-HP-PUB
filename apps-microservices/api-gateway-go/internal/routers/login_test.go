package routers

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"

	"api-gateway-go/internal/auth"
)

func newLoginRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(sessions.Sessions("session", cookie.NewStore([]byte("k"))))
	RegisterLogin(r, auth.NewJWT("s", "HS256", time.Minute))
	return r
}

func TestLoginRedirectsToAuthLoginWhenNoSession(t *testing.T) {
	r := newLoginRouter()
	req := httptest.NewRequest("GET", "/login", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusFound, w.Code)
	require.Equal(t, "/auth/login", w.Header().Get("Location"))
}

func TestLogoutClearsAndRedirects(t *testing.T) {
	r := newLoginRouter()
	req := httptest.NewRequest("GET", "/logout", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusSeeOther, w.Code)
	require.Equal(t, "/login", w.Header().Get("Location"))
}
