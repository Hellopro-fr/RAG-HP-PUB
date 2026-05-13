package routers

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func TestFavicon_ServesSVG(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	RegisterFavicon(r)

	for _, path := range []string{"/favicon.ico", "/favicon.svg"} {
		req := httptest.NewRequest("GET", path, nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		require.Equal(t, http.StatusOK, w.Code, "path=%s", path)
		require.Equal(t, "image/svg+xml", w.Header().Get("Content-Type"), "path=%s", path)
		require.Contains(t, w.Body.String(), "<svg", "path=%s", path)
	}
}
