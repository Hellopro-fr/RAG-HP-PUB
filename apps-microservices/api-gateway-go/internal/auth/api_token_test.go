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

// newVerifier builds a verifier whose snapshot + admin key are fixed for the test.
func newVerifier(t *testing.T, snap AuthSnapshot, adminKey string) (*APITokenVerifier, *gorm.DB, *miniredis.Miniredis) {
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
		func() AuthSnapshot { return snap },
		adminKey,
	)
	return v, gdb, mr
}

func runReq(t *testing.T, mw gin.HandlerFunc, method, target, bearer, adminHeader string) *httptest.ResponseRecorder {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(mw)
	r.Any("/:service/*path", func(c *gin.Context) { c.Status(204) })
	req := httptest.NewRequest(method, target, nil)
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	if adminHeader != "" {
		req.Header.Set("X-Admin-Key", adminHeader)
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func TestVerifier_PolicyPublic_AllowsWithoutBearer(t *testing.T) {
	v, _, _ := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyPublic}}, "k")
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", "", "")
	require.Equal(t, 204, w.Code)
}

func TestVerifier_UnknownService_FailOpen(t *testing.T) {
	v, _, _ := newVerifier(t, AuthSnapshot{}, "k")
	w := runReq(t, v.Middleware(), "GET", "/ghost-service/x", "", "")
	require.Equal(t, 204, w.Code)
}

func TestVerifier_PublicPathBypass_AllowsWithoutBearer(t *testing.T) {
	snap := AuthSnapshot{"graphdlq-service": {Default: PolicyBearer, PublicPaths: map[string]struct{}{"/dlq/queues": {}}}}
	v, _, _ := newVerifier(t, snap, "k")
	w := runReq(t, v.Middleware(), "GET", "/graphdlq-service/dlq/queues", "", "")
	require.Equal(t, 204, w.Code)
}

func TestVerifier_PolicyBearer_RejectsMissingBearer(t *testing.T) {
	v, _, _ := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyBearer}}, "k")
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", "", "")
	require.Equal(t, http.StatusUnauthorized, w.Code)
	require.Equal(t, "Bearer", w.Header().Get("WWW-Authenticate"))
}

func TestVerifier_PolicyBearer_AcceptsRedisHit(t *testing.T) {
	snap := AuthSnapshot{"foo-service": {Default: PolicyBearer}}
	v, _, mr := newVerifier(t, snap, "k")
	tok := v.jwt.GenerateAccessToken("foo-service", 1)
	mr.Set("access_token:"+tok, `{"service":"foo-service","rtid":1}`)
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", tok, "")
	require.Equal(t, 204, w.Code)
}

func TestVerifier_PolicyBearer_FallsBackToDB(t *testing.T) {
	snap := AuthSnapshot{"foo-service": {Default: PolicyBearer}}
	v, gdb, _ := newVerifier(t, snap, "k")
	tok := v.jwt.GenerateAccessToken("foo-service", 1)
	exp := time.Now().Add(5 * time.Minute)
	require.NoError(t, gdb.Create(&dbpkg.InfoRefreshToken{ID: 1, NomService: "foo-service", Token: "r", EstActif: true, IPCreation: "test"}).Error)
	require.NoError(t, gdb.Create(&dbpkg.InfoAccessToken{IDRefreshToken: 1, Token: tok, DateExpiration: exp, EstActif: true}).Error)
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", tok, "")
	require.Equal(t, 204, w.Code)
}

func TestVerifier_PolicyBearer_RejectsRevoked(t *testing.T) {
	snap := AuthSnapshot{"foo-service": {Default: PolicyBearer}}
	v, gdb, _ := newVerifier(t, snap, "k")
	tok := v.jwt.GenerateAccessToken("foo-service", 1)
	exp := time.Now().Add(5 * time.Minute)
	rt := &dbpkg.InfoRefreshToken{ID: 1, NomService: "foo-service", Token: "r", EstActif: true, IPCreation: "test"}
	require.NoError(t, gdb.Create(rt).Error)
	require.NoError(t, gdb.Model(rt).Update("est_actif", false).Error)
	require.NoError(t, gdb.Create(&dbpkg.InfoAccessToken{IDRefreshToken: 1, Token: tok, DateExpiration: exp, EstActif: true}).Error)
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", tok, "")
	require.Equal(t, http.StatusUnauthorized, w.Code)
}

func TestVerifier_PolicyAdminKey_AllowsWithHeader(t *testing.T) {
	v, _, _ := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyAdminKey}}, "k123")
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", "", "k123")
	require.Equal(t, 204, w.Code)
}

func TestVerifier_PolicyAdminKey_RejectsWrongHeader(t *testing.T) {
	v, _, _ := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyAdminKey}}, "k123")
	w := runReq(t, v.Middleware(), "GET", "/foo-service/x", "", "wrong")
	require.Equal(t, http.StatusForbidden, w.Code)
}
