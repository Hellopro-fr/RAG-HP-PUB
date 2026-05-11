package routers

import (
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func TestDocsRendersSwaggerUI(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(sessions.Sessions("session", cookie.NewStore([]byte("k"))))
	RegisterDocs(r, DocsDeps{
		BaseSpec:    map[string]any{"openapi": "3.1.0", "info": map[string]any{"title": "x"}, "paths": map[string]any{}, "components": map[string]any{}},
		ServiceMap:  map[string]string{},
		AdminEmails: map[string]struct{}{},
		AdminKey:    "K",
	})
	req := httptest.NewRequest("GET", "/docs", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	require.Contains(t, w.Body.String(), "swagger-ui")
	require.True(t, strings.Contains(w.Body.String(), "/openapi-public.json") || strings.Contains(w.Body.String(), "/openapi.json"))
}
