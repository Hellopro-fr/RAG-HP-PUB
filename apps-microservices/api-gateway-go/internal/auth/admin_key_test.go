package auth

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func newRouter(handler gin.HandlerFunc, h gin.HandlerFunc) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(handler)
	r.GET("/x", h)
	return r
}

func TestRequireAdminKeyOK(t *testing.T) {
	r := newRouter(RequireAdminKey("KEY"), func(c *gin.Context) { c.Status(204) })
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("X-Admin-Key", "KEY")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 204, w.Code)
}

func TestRequireAdminKeyMissing(t *testing.T) {
	r := newRouter(RequireAdminKey("KEY"), func(c *gin.Context) { c.Status(204) })
	req := httptest.NewRequest("GET", "/x", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusForbidden, w.Code)
}

func TestRequireAdminKeyMismatch(t *testing.T) {
	r := newRouter(RequireAdminKey("KEY"), func(c *gin.Context) { c.Status(204) })
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("X-Admin-Key", "wrong")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusForbidden, w.Code)
}
