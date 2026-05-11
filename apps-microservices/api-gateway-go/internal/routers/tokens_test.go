package routers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
	cachepkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/cache"
	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
)

func newTokensRouter(t *testing.T) (*gin.Engine, *gorm.DB, *miniredis.Miniredis) {
	gin.SetMode(gin.TestMode)
	gdb, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, dbpkg.AutoMigrate(gdb))
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	r := gin.New()
	RegisterTokens(r, TokenDeps{
		DB:                       gdb,
		Cache:                    cachepkg.New(rdb),
		JWT:                      auth.NewJWT("s", "HS256", time.Minute),
		AdminKey:                 "K",
		AccessTokenExpireMinutes: 15,
	})
	return r, gdb, mr
}

func doJSON(r *gin.Engine, method, path string, body any, headers map[string]string) *httptest.ResponseRecorder {
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(method, path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func TestGenerateRequiresAdmin(t *testing.T) {
	r, _, _ := newTokensRouter(t)
	w := doJSON(r, "POST", "/auth/token/generate", map[string]any{"service_name": "x"}, nil)
	require.Equal(t, http.StatusForbidden, w.Code)
}

func TestGenerateCreatesRefreshAndAccess(t *testing.T) {
	r, gdb, _ := newTokensRouter(t)
	w := doJSON(r, "POST", "/auth/token/generate",
		map[string]any{"service_name": "svc"},
		map[string]string{"X-Admin-Key": "K"})
	require.Equal(t, 200, w.Code)
	var rt []dbpkg.InfoRefreshToken
	require.NoError(t, gdb.Find(&rt).Error)
	require.Len(t, rt, 1)
	var at []dbpkg.InfoAccessToken
	require.NoError(t, gdb.Find(&at).Error)
	require.Len(t, at, 1)
}

func TestRefreshRequiresValidRefreshToken(t *testing.T) {
	r, _, _ := newTokensRouter(t)
	w := doJSON(r, "POST", "/auth/token/refresh", map[string]any{"service_name": "x", "refresh_token": "bad"}, nil)
	require.Equal(t, http.StatusUnauthorized, w.Code)
}

func TestListRefreshTokensActiveOnly(t *testing.T) {
	r, gdb, _ := newTokensRouter(t)
	require.NoError(t, gdb.Create(&dbpkg.InfoRefreshToken{NomService: "svc", Token: "a", EstActif: true, IPCreation: "x"}).Error)
	rt := dbpkg.InfoRefreshToken{NomService: "svc", Token: "b", EstActif: true, IPCreation: "x"}
	require.NoError(t, gdb.Create(&rt).Error)
	require.NoError(t, gdb.Model(&rt).Update("est_actif", false).Error)

	req := httptest.NewRequest("GET", "/auth/token/refresh-tokens?service_name=svc&active_only=true", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	var resp map[string]any
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	require.EqualValues(t, 1, resp["total"])
}

func TestAllRefreshTokensRequiresAdmin(t *testing.T) {
	r, _, _ := newTokensRouter(t)
	req := httptest.NewRequest("GET", "/auth/token/all-refresh-tokens", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, http.StatusForbidden, w.Code)
}

func TestLogsPagination(t *testing.T) {
	r, gdb, _ := newTokensRouter(t)
	for i := 0; i < 3; i++ {
		require.NoError(t, gdb.Create(&dbpkg.ApiCallHistory{ServiceName: "x", Method: "GET", Path: "/p", StatusCode: 200, ClientIP: "1.1.1.1"}).Error)
	}
	req := httptest.NewRequest("GET", "/auth/logs?page=1&page_size=2", nil)
	req.Header.Set("X-Admin-Key", "K")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	var resp map[string]any
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	require.EqualValues(t, 3, resp["total"])
	items := resp["items"].([]any)
	require.Len(t, items, 2)
}
