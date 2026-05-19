package auth

import (
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

	cachepkg "api-gateway-go/internal/cache"
	dbpkg "api-gateway-go/internal/db"
)

func setupAuthDeps(t *testing.T) (*APITokenVerifier, *gorm.DB, *miniredis.Miniredis) {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	require.NoError(t, dbpkg.AutoMigrate(gdb))

	mr, err := miniredis.Run()
	require.NoError(t, err)
	t.Cleanup(mr.Close)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})

	v := NewAPITokenVerifier(
		NewJWT("s", "HS256", time.Minute),
		gdb,
		cachepkg.New(rdb),
		map[string][]string{"graphdlq-service": {"dlq/queues"}},
	)
	return v, gdb, mr
}

func runReq(t *testing.T, h gin.HandlerFunc, mw gin.HandlerFunc, method, target, bearer string) *httptest.ResponseRecorder {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(mw)
	r.Any("/:service/*path", h)
	req := httptest.NewRequest(method, target, nil)
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func TestVerifierBypassesNonGraphdlq(t *testing.T) {
	v, _, _ := setupAuthDeps(t)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/dlq-service/anything", "")
	require.Equal(t, 204, w.Code)
}

func TestVerifierAllowsExcludedRoute(t *testing.T) {
	v, _, _ := setupAuthDeps(t)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/queues", "")
	require.Equal(t, 204, w.Code)
}

func TestVerifierRejectsMissingBearer(t *testing.T) {
	v, _, _ := setupAuthDeps(t)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/peek", "")
	require.Equal(t, http.StatusUnauthorized, w.Code)
	require.Equal(t, "Bearer", w.Header().Get("WWW-Authenticate"))
}

func TestVerifierAcceptsRedisHit(t *testing.T) {
	v, _, mr := setupAuthDeps(t)
	tok := v.jwt.GenerateAccessToken("graphdlq-service", 1)
	mr.Set("access_token:"+tok, `{"service":"graphdlq-service","rtid":1}`)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/peek", tok)
	require.Equal(t, 204, w.Code)
}

func TestVerifierFallsBackToDB(t *testing.T) {
	v, gdb, _ := setupAuthDeps(t)
	tok := v.jwt.GenerateAccessToken("graphdlq-service", 1)
	exp := time.Now().Add(5 * time.Minute)
	require.NoError(t, gdb.Create(&dbpkg.InfoRefreshToken{ID: 1, NomService: "graphdlq-service", Token: "r", EstActif: true, IPCreation: "test"}).Error)
	require.NoError(t, gdb.Create(&dbpkg.InfoAccessToken{IDRefreshToken: 1, Token: tok, DateExpiration: exp, EstActif: true}).Error)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/peek", tok)
	require.Equal(t, 204, w.Code)
}

func TestVerifierRejectsRevoked(t *testing.T) {
	v, gdb, _ := setupAuthDeps(t)
	tok := v.jwt.GenerateAccessToken("graphdlq-service", 1)
	exp := time.Now().Add(5 * time.Minute)
	// Create with EstActif=true first (GORM skips zero booleans with default:true tag),
	// then revoke explicitly via Update to set est_actif=false.
	rt := &dbpkg.InfoRefreshToken{ID: 1, NomService: "graphdlq-service", Token: "r", EstActif: true, IPCreation: "test"}
	require.NoError(t, gdb.Create(rt).Error)
	require.NoError(t, gdb.Model(rt).Update("est_actif", false).Error)
	require.NoError(t, gdb.Create(&dbpkg.InfoAccessToken{IDRefreshToken: 1, Token: tok, DateExpiration: exp, EstActif: true}).Error)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/peek", tok)
	require.Equal(t, http.StatusUnauthorized, w.Code)
}
