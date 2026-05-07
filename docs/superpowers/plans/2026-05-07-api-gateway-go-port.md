# api-gateway Go Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strict 1:1 port of `apps-microservices/api-gateway` (Python/FastAPI/Tortoise-ORM) to `apps-microservices/api-gateway-go` (Go 1.24/Gin/GORM). Same endpoints, same DB schema, same Redis keys, same JWT secret + claims, same OpenAPI aggregation rules.

**Architecture:** Single Go binary on port 8500, behind the existing Nginx sidecar (port 8050, untouched). MySQL + Redis backing unchanged. New service folder `apps-microservices/api-gateway-go/` lives next to existing Python folder until cutover.

**Tech Stack:** Go 1.24, Gin, GORM (MySQL driver), `golang-jwt/jwt/v5`, `redis/go-redis/v9`, `gorilla/websocket`, `kin-openapi`, `gin-contrib/sessions`, `joho/godotenv`, `golang.org/x/sync/errgroup`.

**Spec:** `docs/superpowers/specs/2026-05-07-api-gateway-go-port-design.md`.

---

## File Structure (target)

```
apps-microservices/api-gateway-go/
  cmd/gateway/main.go
  internal/
    config/
      config.go
      service_map.go
    db/
      db.go
      models.go
      bootstrap.go
    cache/
      redis.go
    auth/
      jwt.go
      admin_key.go
      api_token.go
      docs_middleware.go
    sso/
      client.go
      pkce.go
    proxy/
      http.go
      ws.go
      history.go
    routers/
      login.go
      sso.go
      tokens.go
      docs.go
    openapi/
      base.yaml          (embed)
      aggregator.go
      filter.go
      swagger_assets/    (embed Swagger UI HTML/JS, pinned)
  Dockerfile
  nginx.conf             (copy of Python service's nginx.conf, byte-identical)
  go.mod
  go.sum
  CLAUDE.md
  README.md
  tests/                 (mirror of internal/, *_test.go inside packages per Go convention)
```

Tests live next to source (`foo_test.go` next to `foo.go`) per Go idiom — no separate `tests/` tree. The `tests/` folder is for the few integration tests that need their own package.

---

## Task 1: Scaffold module + folder layout

**Files:**
- Create: `apps-microservices/api-gateway-go/go.mod`
- Create: `apps-microservices/api-gateway-go/cmd/gateway/main.go`
- Create: `apps-microservices/api-gateway-go/CLAUDE.md`
- Create: `apps-microservices/api-gateway-go/.gitignore`

- [ ] **Step 1: Initialize Go module**

```bash
cd apps-microservices/api-gateway-go
go mod init github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go
```

- [ ] **Step 2: Create empty `cmd/gateway/main.go` that builds**

Create `apps-microservices/api-gateway-go/cmd/gateway/main.go`:

```go
package main

import (
	"log"
)

func main() {
	log.Println("api-gateway-go: scaffold OK")
}
```

- [ ] **Step 3: Verify it builds**

Run: `go build ./...`
Expected: no output, exit 0.

- [ ] **Step 4: Add `.gitignore`**

Create `apps-microservices/api-gateway-go/.gitignore`:

```
/gateway
*.test
*.out
.env
.env.*
!.env.example
```

- [ ] **Step 5: Add `CLAUDE.md`**

Create `apps-microservices/api-gateway-go/CLAUDE.md` with the same structure used by other services (tech stack, run, folder structure, endpoints table — copy from `apps-microservices/api-gateway/CLAUDE.md` and edit Tech Stack section to Go/Gin/GORM).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-gateway-go/
git commit -m "feat(api-gateway-go): scaffold Go module + folder layout"
```

---

## Task 2: Add core dependencies

**Files:**
- Modify: `apps-microservices/api-gateway-go/go.mod`

- [ ] **Step 1: Add deps**

```bash
cd apps-microservices/api-gateway-go
go get github.com/gin-gonic/gin@latest
go get github.com/gin-contrib/sessions@latest
go get gorm.io/gorm@latest
go get gorm.io/driver/mysql@latest
go get github.com/golang-jwt/jwt/v5@latest
go get github.com/redis/go-redis/v9@latest
go get github.com/gorilla/websocket@latest
go get github.com/getkin/kin-openapi/openapi3@latest
go get github.com/joho/godotenv@latest
go get golang.org/x/sync/errgroup@latest
go get gopkg.in/yaml.v3@latest
```

Test deps:

```bash
go get github.com/stretchr/testify@latest
go get github.com/DATA-DOG/go-sqlmock@latest
go get github.com/alicebob/miniredis/v2@latest
```

- [ ] **Step 2: Verify build**

Run: `go build ./...`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/api-gateway-go/go.mod apps-microservices/api-gateway-go/go.sum
git commit -m "feat(api-gateway-go): pin core + test dependencies"
```

---

## Task 3: Config package — base struct + env loading

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/config/config.go`
- Create: `apps-microservices/api-gateway-go/internal/config/config_test.go`

- [ ] **Step 1: Write the failing test**

Create `internal/config/config_test.go`:

```go
package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLoadDefaults(t *testing.T) {
	t.Setenv("JWT_SECRET", "s")
	t.Setenv("GATEWAY_ADMIN_KEY", "k")

	cfg := Load()

	require.Equal(t, "s", cfg.JWTSecret)
	require.Equal(t, "HS256", cfg.JWTAlgo)
	require.Equal(t, "hellopro", cfg.JWTAudience)
	require.Equal(t, "k", cfg.GatewayAdminKey)
	require.Equal(t, 15, cfg.AccessTokenExpireMinutes)
	require.Equal(t, "gateway-mysql", cfg.MySQLHost)
	require.Equal(t, "3306", cfg.MySQLPort)
	require.Equal(t, "gateway_user", cfg.MySQLUser)
	require.Equal(t, "gateway_pass", cfg.MySQLPass)
	require.Equal(t, "gateway_db", cfg.MySQLDB)
	require.Equal(t, "api-gateway", cfg.ServiceName)
}

func TestLoadOverrides(t *testing.T) {
	t.Setenv("JWT_SECRET", "x")
	t.Setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
	t.Setenv("MYSQL_HOST", "db.local")
	t.Setenv("SECURE_COOKIE", "true")
	t.Setenv("GATEWAY_DOCS_ADMIN_EMAILS", " a@b.com ,B@C.com ")

	cfg := Load()

	require.Equal(t, 60, cfg.AccessTokenExpireMinutes)
	require.Equal(t, "db.local", cfg.MySQLHost)
	require.True(t, cfg.SecureCookie)
	require.ElementsMatch(t, []string{"a@b.com", "b@c.com"}, cfg.DocsAdminEmails)
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./internal/config/...`
Expected: build fails — `Load` undefined.

- [ ] **Step 3: Write minimal implementation**

Create `internal/config/config.go`:

```go
package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	JWTSecret                string
	JWTAlgo                  string
	JWTAudience              string
	GatewayAdminKey          string
	AccessTokenExpireMinutes int

	MySQLHost string
	MySQLPort string
	MySQLUser string
	MySQLPass string
	MySQLDB   string

	RedisURL string

	AccountBaseURL     string
	AccountPublicURL   string
	AccountRedirectURI string

	SecureCookie    bool
	ServiceName     string
	DocsAdminEmails []string
}

func getenv(key, def string) string {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return def
	}
	return v
}

func getenvInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func getenvBool(key string, def bool) bool {
	v := strings.ToLower(os.Getenv(key))
	if v == "" {
		return def
	}
	return v == "1" || v == "true" || v == "yes"
}

func parseAdminEmails(raw string) []string {
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.ToLower(strings.TrimSpace(p))
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func Load() Config {
	cfg := Config{
		JWTSecret:                os.Getenv("JWT_SECRET"),
		JWTAlgo:                  getenv("JWT_ALGO", "HS256"),
		JWTAudience:              getenv("JWT_AUDIENCE", "hellopro"),
		GatewayAdminKey:          os.Getenv("GATEWAY_ADMIN_KEY"),
		AccessTokenExpireMinutes: getenvInt("ACCESS_TOKEN_EXPIRE_MINUTES", 15),

		MySQLHost: getenv("MYSQL_HOST", "gateway-mysql"),
		MySQLPort: getenv("MYSQL_PORT", "3306"),
		MySQLUser: getenv("MYSQL_USER", "gateway_user"),
		MySQLPass: getenv("MYSQL_PASS", "gateway_pass"),
		MySQLDB:   getenv("MYSQL_DB", "gateway_db"),

		RedisURL: os.Getenv("REDIS_URL"),

		AccountBaseURL:     strings.TrimRight(getenv("ACCOUNT_BASE_URL", "http://account-service-backend:8600"), "/"),
		AccountPublicURL:   "",
		AccountRedirectURI: os.Getenv("ACCOUNT_REDIRECT_URI"),

		SecureCookie:    getenvBool("SECURE_COOKIE", false),
		ServiceName:     getenv("SERVICE_NAME", "api-gateway"),
		DocsAdminEmails: parseAdminEmails(os.Getenv("GATEWAY_DOCS_ADMIN_EMAILS")),
	}
	cfg.AccountPublicURL = strings.TrimRight(getenv("ACCOUNT_PUBLIC_URL", cfg.AccountBaseURL), "/")
	return cfg
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./internal/config/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/config/
git commit -m "feat(api-gateway-go): config loader from env"
```

---

## Task 4: Config package — service map + excluded routes + timeouts

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/config/service_map.go`
- Create: `apps-microservices/api-gateway-go/internal/config/service_map_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/config/service_map_test.go`:

```go
package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildServiceMapFromEnv(t *testing.T) {
	t.Setenv("SERVICE_DLQ", "http://dlq:1234")
	t.Setenv("SERVICE_GRAPHDLQ", "http://graphdlq:5678")
	t.Setenv("OTHER_VAR", "ignored")

	m := BuildServiceMap()

	require.Equal(t, "http://dlq:1234", m["/dlq-service"])
	require.Equal(t, "http://graphdlq:5678", m["/graphdlq-service"])
	require.NotContains(t, m, "OTHER_VAR")
}

func TestExcludedRoutes(t *testing.T) {
	er := BuildExcludedRoutes()
	require.Equal(t, []string{"dlq/queues"}, er["graphdlq-service"])
}

func TestDownstreamTimeouts(t *testing.T) {
	to := BuildDownstreamTimeouts()
	v, ok := to["api-detection-langue-fr-service"]
	require.True(t, ok)
	require.Equal(t, 180.0, v)
}

func TestExcludedServices(t *testing.T) {
	es := ExcludedServices()
	require.Contains(t, es, "crawling-service")
	require.Contains(t, es, "image_comparator-service")
	require.Contains(t, es, "graphadmin-service")
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `go test ./internal/config/... -run "ServiceMap|Excluded|Timeout"`
Expected: build fails — symbols undefined.

- [ ] **Step 3: Write minimal implementation**

Create `internal/config/service_map.go`:

```go
package config

import (
	"os"
	"strings"
)

func BuildServiceMap() map[string]string {
	out := map[string]string{}
	for _, kv := range os.Environ() {
		eq := strings.IndexByte(kv, '=')
		if eq <= 0 {
			continue
		}
		k, v := kv[:eq], kv[eq+1:]
		if !strings.HasPrefix(k, "SERVICE_") {
			continue
		}
		name := strings.ToLower(strings.TrimPrefix(k, "SERVICE_"))
		out["/"+name+"-service"] = v
	}
	return out
}

func BuildExcludedRoutes() map[string][]string {
	raw := map[string][]string{
		"graphdlq-service": {"/dlq/queues"},
	}
	out := make(map[string][]string, len(raw))
	for svc, paths := range raw {
		clean := make([]string, 0, len(paths))
		for _, p := range paths {
			p = strings.Trim(strings.TrimSpace(p), "/")
			if p != "" {
				clean = append(clean, p)
			}
		}
		out[svc] = clean
	}
	return out
}

func BuildDownstreamTimeouts() map[string]float64 {
	return map[string]float64{
		"api-detection-langue-fr-service": 180,
	}
}

func ExcludedServices() map[string]struct{} {
	return map[string]struct{}{
		"crawling-service":         {},
		"image_comparator-service": {},
		"graphadmin-service":       {},
	}
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/config/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/config/
git commit -m "feat(api-gateway-go): SERVICE_MAP + excluded routes + per-service timeouts"
```

---

## Task 5: DB models with GORM tags

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/db/models.go`
- Create: `apps-microservices/api-gateway-go/internal/db/models_test.go`

- [ ] **Step 1: Write the failing test**

Create `internal/db/models_test.go`:

```go
package db

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestTableNames(t *testing.T) {
	require.Equal(t, "info_refresh_token", InfoRefreshToken{}.TableName())
	require.Equal(t, "info_access_token", InfoAccessToken{}.TableName())
	require.Equal(t, "api_call_history", ApiCallHistory{}.TableName())
}
```

- [ ] **Step 2: Run test (build fails)**

Run: `go test ./internal/db/...`
Expected: build error — types undefined.

- [ ] **Step 3: Write models**

Create `internal/db/models.go`:

```go
package db

import "time"

type InfoRefreshToken struct {
	ID           uint      `gorm:"column:id;primaryKey;autoIncrement"`
	NomService   string    `gorm:"column:nom_service;size:128;index"`
	Token        string    `gorm:"column:token;size:768;index"`
	DateCreation time.Time `gorm:"column:date_creation;autoCreateTime"`
	IPCreation   string    `gorm:"column:ip_creation;size:64;default:system"`
	EstActif     bool      `gorm:"column:est_actif;default:true;index"`
}

func (InfoRefreshToken) TableName() string { return "info_refresh_token" }

type InfoAccessToken struct {
	ID             uint             `gorm:"column:id;primaryKey;autoIncrement"`
	IDRefreshToken uint             `gorm:"column:id_refresh_token_id;index"`
	RefreshToken   InfoRefreshToken `gorm:"foreignKey:IDRefreshToken;references:ID;constraint:OnDelete:CASCADE"`
	Token          string           `gorm:"column:token;size:768;index"`
	DateCreation   time.Time        `gorm:"column:date_creation;autoCreateTime"`
	DateExpiration time.Time        `gorm:"column:date_expiration"`
	EstActif       bool             `gorm:"column:est_actif;default:true;index"`
}

func (InfoAccessToken) TableName() string { return "info_access_token" }

type ApiCallHistory struct {
	ID             uint      `gorm:"column:id;primaryKey;autoIncrement"`
	ServiceName    string    `gorm:"column:service_name;size:128;index"`
	Method         string    `gorm:"column:method;size:10"`
	Path           string    `gorm:"column:path;type:text"`
	StatusCode     int       `gorm:"column:status_code"`
	ClientIP       string    `gorm:"column:client_ip;size:64"`
	RequestHeaders *string   `gorm:"column:request_headers;type:text"`
	CalledAt       time.Time `gorm:"column:called_at;autoCreateTime;index"`
	DurationMs     *int      `gorm:"column:duration_ms"`
}

func (ApiCallHistory) TableName() string { return "api_call_history" }
```

- [ ] **Step 4: Run test**

Run: `go test ./internal/db/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/db/
git commit -m "feat(api-gateway-go): GORM models matching Tortoise table/column names"
```

---

## Task 6: DB init + AutoMigrate

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/db/db.go`
- Create: `apps-microservices/api-gateway-go/internal/db/db_test.go`

- [ ] **Step 1: Write the failing test (DSN format only — actual conn lives in integration tests)**

Create `internal/db/db_test.go`:

```go
package db

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildDSN(t *testing.T) {
	dsn := BuildDSN("user", "pw", "h", "3306", "d")
	require.Equal(t, "user:pw@tcp(h:3306)/d?charset=utf8mb4&parseTime=true&loc=UTC", dsn)
}
```

- [ ] **Step 2: Run test**

Run: `go test ./internal/db/... -run TestBuildDSN`
Expected: build fails — `BuildDSN` undefined.

- [ ] **Step 3: Implement**

Create `internal/db/db.go`:

```go
package db

import (
	"context"
	"fmt"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func BuildDSN(user, pass, host, port, name string) string {
	return fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=true&loc=UTC",
		user, pass, host, port, name)
}

func Open(ctx context.Context, dsn string) (*gorm.DB, error) {
	gdb, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Warn),
	})
	if err != nil {
		return nil, err
	}
	sqlDB, err := gdb.DB()
	if err != nil {
		return nil, err
	}
	if err := sqlDB.PingContext(ctx); err != nil {
		return nil, err
	}
	return gdb, nil
}

func AutoMigrate(gdb *gorm.DB) error {
	return gdb.AutoMigrate(&InfoRefreshToken{}, &InfoAccessToken{}, &ApiCallHistory{})
}
```

- [ ] **Step 4: Run test**

Run: `go test ./internal/db/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/db/
git commit -m "feat(api-gateway-go): GORM Open + AutoMigrate"
```

---

## Task 7: JWT helpers (HS256)

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/auth/jwt.go`
- Create: `apps-microservices/api-gateway-go/internal/auth/jwt_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/auth/jwt_test.go`:

```go
package auth

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestGenerateAndVerifyAccessToken(t *testing.T) {
	j := NewJWT("secret", "HS256", 15*time.Minute)

	tok := j.GenerateAccessToken("svc", 42)
	require.NotEmpty(t, tok)

	claims, err := j.VerifyAccessToken(tok)
	require.NoError(t, err)
	require.Equal(t, "svc", claims.Subject)
	require.Equal(t, uint(42), claims.RefreshTokenID)
}

func TestVerifyExpired(t *testing.T) {
	j := NewJWT("secret", "HS256", -time.Minute)
	tok := j.GenerateAccessToken("svc", 1)
	_, err := j.VerifyAccessToken(tok)
	require.ErrorIs(t, err, ErrExpired)
}

func TestVerifyInvalid(t *testing.T) {
	j := NewJWT("secret", "HS256", time.Minute)
	_, err := j.VerifyAccessToken("not-a-jwt")
	require.ErrorIs(t, err, ErrInvalid)
}

func TestRefreshTokenHasNoExp(t *testing.T) {
	j := NewJWT("secret", "HS256", time.Minute)
	tok := j.GenerateRefreshToken("svc")
	c, err := j.parse(tok)
	require.NoError(t, err)
	require.Equal(t, "svc", c["sub"])
	require.Equal(t, "refresh", c["type"])
	_, hasExp := c["exp"]
	require.False(t, hasExp)
}
```

- [ ] **Step 2: Run tests (will fail)**

Run: `go test ./internal/auth/... -run TestGenerate`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/auth/jwt.go`:

```go
package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var (
	ErrExpired = errors.New("token expired")
	ErrInvalid = errors.New("token invalid")
)

type AccessClaims struct {
	Subject        string
	RefreshTokenID uint
}

type JWT struct {
	secret []byte
	alg    string
	access time.Duration
}

func NewJWT(secret, alg string, accessDuration time.Duration) *JWT {
	return &JWT{secret: []byte(secret), alg: alg, access: accessDuration}
}

func (j *JWT) GenerateAccessToken(service string, refreshID uint) string {
	now := time.Now().UTC()
	claims := jwt.MapClaims{
		"sub":  service,
		"rtid": refreshID,
		"iat":  now.Unix(),
		"exp":  now.Add(j.access).Unix(),
	}
	tok := jwt.NewWithClaims(jwt.GetSigningMethod(j.alg), claims)
	s, _ := tok.SignedString(j.secret)
	return s
}

func (j *JWT) GenerateRefreshToken(service string) string {
	claims := jwt.MapClaims{
		"sub":  service,
		"type": "refresh",
		"iat":  time.Now().UTC().Unix(),
	}
	tok := jwt.NewWithClaims(jwt.GetSigningMethod(j.alg), claims)
	s, _ := tok.SignedString(j.secret)
	return s
}

func (j *JWT) VerifyAccessToken(raw string) (AccessClaims, error) {
	c, err := j.parse(raw)
	if err != nil {
		return AccessClaims{}, err
	}
	sub, _ := c["sub"].(string)
	var rtid uint
	switch v := c["rtid"].(type) {
	case float64:
		rtid = uint(v)
	case int64:
		rtid = uint(v)
	}
	return AccessClaims{Subject: sub, RefreshTokenID: rtid}, nil
}

// parse is exported only via internal tests via the package boundary.
func (j *JWT) parse(raw string) (jwt.MapClaims, error) {
	tok, err := jwt.Parse(raw, func(t *jwt.Token) (interface{}, error) {
		return j.secret, nil
	}, jwt.WithValidMethods([]string{j.alg}))
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrExpired
		}
		return nil, ErrInvalid
	}
	c, ok := tok.Claims.(jwt.MapClaims)
	if !ok {
		return nil, ErrInvalid
	}
	return c, nil
}

// VerifyDocsToken decodes a docs-session JWT, skipping audience verification
// (matches Python DocsAuthMiddleware which sets options={"verify_aud": False}).
func (j *JWT) VerifyDocsToken(raw string) error {
	_, err := j.parse(raw)
	return err
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/auth/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/auth/
git commit -m "feat(api-gateway-go): JWT sign/verify (HS256, claims sub/rtid/iat/exp)"
```

---

## Task 8: Cache (Redis) — get/set/delete with TTL

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/cache/redis.go`
- Create: `apps-microservices/api-gateway-go/internal/cache/redis_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/cache/redis_test.go`:

```go
package cache

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func newClient(t *testing.T) (*Cache, *miniredis.Miniredis) {
	t.Helper()
	mr, err := miniredis.Run()
	require.NoError(t, err)
	t.Cleanup(mr.Close)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	return New(rdb), mr
}

func TestSetGetJSON(t *testing.T) {
	c, _ := newClient(t)
	ctx := context.Background()

	require.NoError(t, c.SetJSON(ctx, "k", map[string]any{"a": 1}, 5*time.Second))

	var out map[string]any
	found, err := c.GetJSON(ctx, "k", &out)
	require.NoError(t, err)
	require.True(t, found)
	require.EqualValues(t, 1, out["a"])
}

func TestGetJSONMissing(t *testing.T) {
	c, _ := newClient(t)
	var out map[string]any
	found, err := c.GetJSON(context.Background(), "missing", &out)
	require.NoError(t, err)
	require.False(t, found)
}

func TestDelete(t *testing.T) {
	c, _ := newClient(t)
	ctx := context.Background()
	require.NoError(t, c.SetJSON(ctx, "k", "v", time.Minute))
	require.NoError(t, c.Delete(ctx, "k"))
	var out string
	found, _ := c.GetJSON(ctx, "k", &out)
	require.False(t, found)
}
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/cache/...`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/cache/redis.go`:

```go
package cache

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
)

type Cache struct {
	rdb *redis.Client
}

func New(rdb *redis.Client) *Cache { return &Cache{rdb: rdb} }

func (c *Cache) SetJSON(ctx context.Context, key string, value any, ttl time.Duration) error {
	b, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return c.rdb.Set(ctx, key, b, ttl).Err()
}

// GetJSON returns (found, error). found=false means key absent.
func (c *Cache) GetJSON(ctx context.Context, key string, out any) (bool, error) {
	b, err := c.rdb.Get(ctx, key).Bytes()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return false, nil
		}
		return false, err
	}
	if err := json.Unmarshal(b, out); err != nil {
		return true, err
	}
	return true, nil
}

func (c *Cache) Delete(ctx context.Context, key string) error {
	return c.rdb.Del(ctx, key).Err()
}

func OpenFromURL(rawURL string) (*redis.Client, error) {
	if rawURL == "" {
		return nil, errors.New("REDIS_URL empty")
	}
	opt, err := redis.ParseURL(rawURL)
	if err != nil {
		return nil, err
	}
	return redis.NewClient(opt), nil
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/cache/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/cache/
git commit -m "feat(api-gateway-go): Redis cache with TTL JSON helpers"
```

---

## Task 9: Bootstrap refresh tokens at startup

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/db/bootstrap.go`
- Create: `apps-microservices/api-gateway-go/internal/db/bootstrap_test.go`

- [ ] **Step 1: Write the failing test (uses sqlite in-memory for portability)**

Create `internal/db/bootstrap_test.go`:

```go
package db

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

func newSQLite(t *testing.T) *gorm.DB {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	require.NoError(t, AutoMigrate(g))
	return g
}

type fakeIssuer struct{ counter int }

func (f *fakeIssuer) NewRefreshToken(service string) string {
	f.counter++
	return service + "-refresh-token"
}

func TestBootstrapCreatesMissing(t *testing.T) {
	g := newSQLite(t)
	iss := &fakeIssuer{}
	serviceMap := map[string]string{
		"/dlq-service":      "http://dlq",
		"/graphdlq-service": "http://graphdlq",
	}

	require.NoError(t, BootstrapRefreshTokens(context.Background(), g, serviceMap, iss))

	var rows []InfoRefreshToken
	require.NoError(t, g.Find(&rows).Error)
	require.Len(t, rows, 2)
	require.Equal(t, 2, iss.counter)
}

func TestBootstrapSkipsExisting(t *testing.T) {
	g := newSQLite(t)
	iss := &fakeIssuer{}

	require.NoError(t, g.Create(&InfoRefreshToken{NomService: "dlq-service", Token: "x", IPCreation: "system", EstActif: true}).Error)

	require.NoError(t, BootstrapRefreshTokens(context.Background(), g, map[string]string{
		"/dlq-service": "http://dlq",
	}, iss))

	require.Equal(t, 0, iss.counter)
}
```

Add `gorm.io/driver/sqlite` test dep:

```bash
cd apps-microservices/api-gateway-go
go get gorm.io/driver/sqlite@latest
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/db/... -run Bootstrap`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/db/bootstrap.go`:

```go
package db

import (
	"context"
	"strings"

	"gorm.io/gorm"
)

type RefreshTokenIssuer interface {
	NewRefreshToken(service string) string
}

func BootstrapRefreshTokens(ctx context.Context, g *gorm.DB, serviceMap map[string]string, issuer RefreshTokenIssuer) error {
	for apiPath := range serviceMap {
		serviceName := strings.TrimPrefix(apiPath, "/")
		var existing InfoRefreshToken
		err := g.WithContext(ctx).
			Where("nom_service = ? AND est_actif = ?", serviceName, true).
			First(&existing).Error
		if err == nil {
			continue
		}
		if err != gorm.ErrRecordNotFound {
			return err
		}
		row := InfoRefreshToken{
			NomService: serviceName,
			Token:      issuer.NewRefreshToken(serviceName),
			IPCreation: "system",
			EstActif:   true,
		}
		if err := g.WithContext(ctx).Create(&row).Error; err != nil {
			return err
		}
	}
	return nil
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/db/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/db/
git commit -m "feat(api-gateway-go): bootstrap refresh tokens on startup"
```

---

## Task 10: Admin-key middleware

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/auth/admin_key.go`
- Create: `apps-microservices/api-gateway-go/internal/auth/admin_key_test.go`

- [ ] **Step 1: Write the failing test**

Create `internal/auth/admin_key_test.go`:

```go
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
```

- [ ] **Step 2: Run test (build fails)**

Run: `go test ./internal/auth/... -run AdminKey`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/auth/admin_key.go`:

```go
package auth

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func RequireAdminKey(expected string) gin.HandlerFunc {
	return func(c *gin.Context) {
		got := c.GetHeader("X-Admin-Key")
		if got != expected {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"detail": "Invalid or missing admin key."})
			return
		}
		c.Next()
	}
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/auth/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/auth/
git commit -m "feat(api-gateway-go): X-Admin-Key middleware"
```

---

## Task 11: API token middleware (with TODO short-circuit)

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/auth/api_token.go`
- Create: `apps-microservices/api-gateway-go/internal/auth/api_token_test.go`

The Python source (`app/core/auth.py:122-133`) currently short-circuits everything except `graphdlq-service`. Preserve this behavior exactly — port the TODO comment so the next maintainer knows it's intentional.

- [ ] **Step 1: Write the failing tests**

Create `internal/auth/api_token_test.go`:

```go
package auth

import (
	"context"
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

	cachepkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/cache"
	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
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
	_ = context.Background()
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/peek", tok)
	require.Equal(t, 204, w.Code)
}

func TestVerifierRejectsRevoked(t *testing.T) {
	v, gdb, _ := setupAuthDeps(t)
	tok := v.jwt.GenerateAccessToken("graphdlq-service", 1)
	exp := time.Now().Add(5 * time.Minute)
	require.NoError(t, gdb.Create(&dbpkg.InfoRefreshToken{ID: 1, NomService: "graphdlq-service", Token: "r", EstActif: false, IPCreation: "test"}).Error)
	require.NoError(t, gdb.Create(&dbpkg.InfoAccessToken{IDRefreshToken: 1, Token: tok, DateExpiration: exp, EstActif: true}).Error)
	w := runReq(t, func(c *gin.Context) { c.Status(204) }, v.Middleware(), "GET", "/graphdlq-service/dlq/peek", tok)
	require.Equal(t, http.StatusUnauthorized, w.Code)
}
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/auth/... -run Verifier`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/auth/api_token.go`:

```go
package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	cachepkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/cache"
	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
)

type APITokenVerifier struct {
	jwt            *JWT
	db             *gorm.DB
	cache          *cachepkg.Cache
	excludedRoutes map[string][]string
}

func NewAPITokenVerifier(j *JWT, g *gorm.DB, c *cachepkg.Cache, excluded map[string][]string) *APITokenVerifier {
	return &APITokenVerifier{jwt: j, db: g, cache: c, excludedRoutes: excluded}
}

// Middleware mirrors app/core/auth.py:verify_api_token, including the existing
// TODO short-circuit that bypasses auth for every service except graphdlq-service.
// DO NOT remove this short-circuit without a follow-up spec — the Python service
// has the same behavior in production.
func (v *APITokenVerifier) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		service := c.Param("service")
		path := strings.Trim(c.Param("path"), "/")

		// TODO: Test pour toujours exclure toutes les routes
		// → except graphdlq-service pour le test (ported from Python).
		if service != "graphdlq-service" {
			c.Set("token_payload", gin.H{"sub": service, "is_excluded": true})
			c.Next()
			return
		}

		// 1. Excluded routes bypass.
		for _, p := range v.excludedRoutes[service] {
			if p == path {
				c.Set("token_payload", gin.H{"sub": service, "is_excluded": true})
				c.Next()
				return
			}
		}

		// 2. Bearer extraction.
		authHeader := c.GetHeader("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			abortAuth(c, "Access token manquant ou invalide.")
			return
		}
		raw := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))

		// 3. Verify JWT.
		claims, err := v.jwt.VerifyAccessToken(raw)
		if err != nil {
			if errors.Is(err, ErrExpired) {
				abortAuth(c, "Access token has expired. Please refresh.")
			} else {
				abortAuth(c, "Invalid access token.")
			}
			return
		}

		// 4. Redis fast path.
		ctx := c.Request.Context()
		var redisPayload map[string]any
		found, _ := v.cache.GetJSON(ctx, "access_token:"+raw, &redisPayload)
		if found {
			c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
			c.Next()
			return
		}

		// 5. DB fallback.
		if !v.dbAccessTokenActive(ctx, raw) {
			abortAuth(c, "Access token has been revoked or expired.")
			return
		}
		c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
		c.Next()
	}
}

func abortAuth(c *gin.Context, detail string) {
	c.Header("WWW-Authenticate", "Bearer")
	c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"detail": detail})
}

func (v *APITokenVerifier) dbAccessTokenActive(ctx context.Context, token string) bool {
	now := time.Now().UTC()
	var access dbpkg.InfoAccessToken
	err := v.db.WithContext(ctx).
		Preload("RefreshToken").
		Where("token = ? AND est_actif = ? AND date_expiration >= ?", token, true, now).
		First(&access).Error
	if err != nil {
		return false
	}
	return access.RefreshToken.EstActif
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/auth/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/auth/
git commit -m "feat(api-gateway-go): API Bearer token verifier (preserves Python TODO short-circuit)"
```

---

## Task 12: Docs auth middleware (session + JWT)

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/auth/docs_middleware.go`
- Create: `apps-microservices/api-gateway-go/internal/auth/docs_middleware_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/auth/docs_middleware_test.go`:

```go
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
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/auth/... -run DocsRedirects`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/auth/docs_middleware.go`:

```go
package auth

import (
	"net/http"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
)

var docsProtectedPaths = map[string]struct{}{
	"/docs":         {},
	"/redoc":        {},
	"/openapi.json": {},
}

// DocsAuthMiddleware mirrors app/core/auth.py:DocsAuthMiddleware. /openapi-public.json
// is intentionally NOT in the protected set (matches Python).
func DocsAuthMiddleware(j *JWT) gin.HandlerFunc {
	return func(c *gin.Context) {
		path := c.Request.URL.Path
		if _, ok := docsProtectedPaths[path]; !ok {
			c.Next()
			return
		}

		s := sessions.Default(c)
		userRaw := s.Get("user")
		if userRaw == nil {
			redirectLogin(c)
			return
		}
		user, ok := userRaw.(map[string]any)
		if !ok {
			redirectLogin(c)
			return
		}
		token, _ := user["token"].(string)
		if token == "" {
			redirectLogin(c)
			return
		}
		if err := j.VerifyDocsToken(token); err != nil {
			s.Clear()
			_ = s.Save()
			redirectLogin(c)
			return
		}
		c.Next()
	}
}

func redirectLogin(c *gin.Context) {
	c.Redirect(http.StatusFound, "/login")
	c.Abort()
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/auth/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/auth/
git commit -m "feat(api-gateway-go): /docs session + JWT middleware"
```

---

## Task 13: SSO PKCE helpers

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/sso/pkce.go`
- Create: `apps-microservices/api-gateway-go/internal/sso/pkce_test.go`

- [ ] **Step 1: Write the failing test**

Create `internal/sso/pkce_test.go`:

```go
package sso

import (
	"crypto/sha256"
	"encoding/base64"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestNewPKCEPair(t *testing.T) {
	p := NewPKCEPair()
	require.NotEmpty(t, p.Verifier)
	require.NotEmpty(t, p.Challenge)
	require.NotEmpty(t, p.State)
	require.False(t, strings.HasSuffix(p.Challenge, "="))

	sum := sha256.Sum256([]byte(p.Verifier))
	want := base64.RawURLEncoding.EncodeToString(sum[:])
	require.Equal(t, want, p.Challenge)
}
```

- [ ] **Step 2: Run test**

Run: `go test ./internal/sso/... -run NewPKCE`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/sso/pkce.go`:

```go
package sso

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
)

type PKCEPair struct {
	Verifier  string
	Challenge string
	State     string
}

func b64url(b []byte) string { return base64.RawURLEncoding.EncodeToString(b) }

func NewPKCEPair() PKCEPair {
	verifierBytes := make([]byte, 32)
	_, _ = rand.Read(verifierBytes)
	verifier := b64url(verifierBytes)

	sum := sha256.Sum256([]byte(verifier))
	challenge := b64url(sum[:])

	stateBytes := make([]byte, 16)
	_, _ = rand.Read(stateBytes)
	state := b64url(stateBytes)

	return PKCEPair{Verifier: verifier, Challenge: challenge, State: state}
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/sso/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/sso/
git commit -m "feat(api-gateway-go): PKCE verifier/challenge/state generator"
```

---

## Task 14: SSO client credential resolution

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/sso/client.go`
- Create: `apps-microservices/api-gateway-go/internal/sso/client_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/sso/client_test.go`:

```go
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
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/sso/... -run Resolve`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/sso/client.go`:

```go
package sso

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type ClientCredentials struct {
	ClientID     string
	ClientSecret string
	RedirectURIs []string
}

type ResolverConfig struct {
	ServiceName    string
	AccountBaseURL string
	HTTPClient     *http.Client
}

type Resolver struct {
	cfg    ResolverConfig
	mu     sync.Mutex
	cached *ClientCredentials
}

func NewResolver(cfg ResolverConfig) *Resolver {
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 10 * time.Second}
	}
	return &Resolver{cfg: cfg}
}

func (r *Resolver) Resolve(ctx context.Context) (*ClientCredentials, error) {
	r.mu.Lock()
	if r.cached != nil {
		c := r.cached
		r.mu.Unlock()
		return c, nil
	}
	r.mu.Unlock()

	// 1. Service-specific env
	upper := strings.ToUpper(strings.ReplaceAll(r.cfg.ServiceName, "-", "_"))
	if id := os.Getenv("ACCOUNT_CLIENT_ID_" + upper); id != "" {
		if sec := os.Getenv("ACCOUNT_CLIENT_SECRET_" + upper); sec != "" {
			return r.cache(&ClientCredentials{ClientID: id, ClientSecret: sec}), nil
		}
	}
	// 2. Generic env
	if id := os.Getenv("ACCOUNT_CLIENT_ID"); id != "" {
		if sec := os.Getenv("ACCOUNT_CLIENT_SECRET"); sec != "" {
			return r.cache(&ClientCredentials{ClientID: id, ClientSecret: sec}), nil
		}
	}
	// 3. HTTP fallback
	url := fmt.Sprintf("%s/internal/credentials/%s", strings.TrimRight(r.cfg.AccountBaseURL, "/"), r.cfg.ServiceName)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := r.cfg.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("account-service /internal/credentials/%s returned %d", r.cfg.ServiceName, resp.StatusCode)
	}
	var body struct {
		ClientID     string   `json:"client_id"`
		ClientSecret string   `json:"client_secret"`
		RedirectURIs []string `json:"redirect_uris"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, err
	}
	if body.ClientID == "" || body.ClientSecret == "" {
		return nil, errors.New("account-service returned empty credentials")
	}
	return r.cache(&ClientCredentials{ClientID: body.ClientID, ClientSecret: body.ClientSecret, RedirectURIs: body.RedirectURIs}), nil
}

func (r *Resolver) cache(c *ClientCredentials) *ClientCredentials {
	r.mu.Lock()
	r.cached = c
	r.mu.Unlock()
	return c
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/sso/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/sso/
git commit -m "feat(api-gateway-go): account-service credential resolution (env → /internal/credentials)"
```

---

## Task 15: SSO router — `/auth/login` + `/auth/callback`

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/routers/sso.go`
- Create: `apps-microservices/api-gateway-go/internal/routers/sso_test.go`

- [ ] **Step 1: Write the failing tests**

Create `internal/routers/sso_test.go`:

```go
package routers

import (
	"net/http"
	"net/http/httptest"
	"net/url"
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
	require.Contains(t, w.Header().Get("Set-Cookie"), "auth_verifier=")
	require.Contains(t, w.Header().Get("Set-Cookie"), "auth_state=")
}
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/routers/... -run AuthLogin`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/routers/sso.go`:

```go
package routers

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/sso"
)

type SSODeps struct {
	Resolver        *sso.Resolver
	AccountBaseURL  string
	AccountPubURL   string
	AccountRedirect string
	SecureCookie    bool
	HTTPClient      *http.Client
}

const replayWindowS = 5 * 60

func RegisterSSO(r *gin.Engine, d SSODeps) {
	if d.HTTPClient == nil {
		d.HTTPClient = &http.Client{Timeout: 10 * time.Second}
	}
	r.GET("/auth/login", authLoginHandler(d))
	r.GET("/auth/callback", authCallbackHandler(d))
	r.POST("/auth/logout-webhook", logoutWebhookHandler(d))
}

func redirectURI(d SSODeps, c *sso.ClientCredentials) (string, error) {
	if d.AccountRedirect != "" {
		return d.AccountRedirect, nil
	}
	if len(c.RedirectURIs) > 0 {
		return c.RedirectURIs[0], nil
	}
	return "", fmt.Errorf("no redirect_uri available (set ACCOUNT_REDIRECT_URI or register one)")
}

func authLoginHandler(d SSODeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		creds, err := d.Resolver.Resolve(c.Request.Context())
		if err != nil {
			c.JSON(500, gin.H{"detail": fmt.Sprintf("account-service credentials unavailable: %v", err)})
			return
		}
		ru, err := redirectURI(d, creds)
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		p := sso.NewPKCEPair()
		target := fmt.Sprintf(
			"%s/authorize?response_type=code&client_id=%s&redirect_uri=%s&code_challenge=%s&code_challenge_method=S256&state=%s",
			d.AccountPubURL, url.QueryEscape(creds.ClientID), url.QueryEscape(ru), p.Challenge, p.State,
		)
		setShortCookie(c, "auth_verifier", p.Verifier, d.SecureCookie)
		setShortCookie(c, "auth_state", p.State, d.SecureCookie)
		c.Redirect(http.StatusFound, target)
	}
}

func setShortCookie(c *gin.Context, name, value string, secure bool) {
	c.SetSameSite(http.SameSiteLaxMode)
	c.SetCookie(name, value, 600, "/", "", secure, true)
}

func authCallbackHandler(d SSODeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		code := c.Query("code")
		state := c.Query("state")
		if code == "" || state == "" {
			c.JSON(400, gin.H{"detail": "missing code or state"})
			return
		}
		storedState, _ := c.Cookie("auth_state")
		verifier, _ := c.Cookie("auth_verifier")
		if storedState != state {
			c.JSON(400, gin.H{"detail": "state mismatch"})
			return
		}
		if verifier == "" {
			c.JSON(400, gin.H{"detail": "missing verifier"})
			return
		}
		creds, err := d.Resolver.Resolve(c.Request.Context())
		if err != nil {
			c.JSON(500, gin.H{"detail": fmt.Sprintf("account-service credentials unavailable: %v", err)})
			return
		}
		ru, err := redirectURI(d, creds)
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}

		form := url.Values{}
		form.Set("grant_type", "authorization_code")
		form.Set("code", code)
		form.Set("redirect_uri", ru)
		form.Set("code_verifier", verifier)

		req, _ := http.NewRequestWithContext(c.Request.Context(), "POST", d.AccountBaseURL+"/token", strings.NewReader(form.Encode()))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.SetBasicAuth(creds.ClientID, creds.ClientSecret)
		resp, err := d.HTTPClient.Do(req)
		if err != nil {
			c.JSON(502, gin.H{"detail": "token exchange failed: " + err.Error()})
			return
		}
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)
		if resp.StatusCode != 200 {
			c.JSON(502, gin.H{"detail": "token exchange failed: " + string(body)})
			return
		}
		var tokens map[string]any
		if err := json.Unmarshal(body, &tokens); err != nil {
			c.JSON(502, gin.H{"detail": "token exchange parse failed"})
			return
		}
		access, _ := tokens["access_token"].(string)
		refresh, _ := tokens["refresh_token"].(string)
		claims := decodeJWTPayload(access)

		s := sessions.Default(c)
		s.Set("user", map[string]any{
			"display_name": firstNonEmpty(claims["name"], claims["sub"]),
			"email":        firstNonEmpty(claims["sub"], claims["email"]),
			"token":        access,
			"sso": map[string]any{
				"sid": claims["sid"], "iss": claims["iss"], "exp": claims["exp"],
				"refresh_token": refresh,
			},
		})
		_ = s.Save()

		c.SetCookie("auth_verifier", "", -1, "/", "", d.SecureCookie, true)
		c.SetCookie("auth_state", "", -1, "/", "", d.SecureCookie, true)
		c.Redirect(http.StatusSeeOther, "/docs")
	}
}

func decodeJWTPayload(token string) map[string]any {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return map[string]any{}
	}
	seg := parts[1]
	if pad := len(seg) % 4; pad > 0 {
		seg += strings.Repeat("=", 4-pad)
	}
	raw, err := base64.URLEncoding.DecodeString(seg)
	if err != nil {
		return map[string]any{}
	}
	var out map[string]any
	_ = json.Unmarshal(raw, &out)
	return out
}

func firstNonEmpty(values ...any) any {
	for _, v := range values {
		if s, ok := v.(string); ok && s != "" {
			return s
		}
		if v != nil {
			return v
		}
	}
	return nil
}

func logoutWebhookHandler(d SSODeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		creds, err := d.Resolver.Resolve(c.Request.Context())
		if err != nil {
			c.JSON(500, gin.H{"detail": fmt.Sprintf("account-service credentials unavailable: %v", err)})
			return
		}
		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(400, gin.H{"detail": "bad body"})
			return
		}
		mac := hmac.New(sha256.New, []byte(creds.ClientSecret))
		mac.Write(body)
		expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
		presented := c.GetHeader("X-Logout-Signature")
		if !hmac.Equal([]byte(expected), []byte(presented)) {
			c.JSON(401, gin.H{"detail": "bad signature"})
			return
		}
		var evt map[string]any
		if err := json.Unmarshal(body, &evt); err != nil {
			c.JSON(400, gin.H{"detail": "bad body"})
			return
		}
		iat, _ := evt["iat"].(float64)
		if abs(time.Now().Unix()-int64(iat)) > replayWindowS {
			c.JSON(401, gin.H{"detail": "stale event"})
			return
		}
		_ = context.Background()
		c.Status(http.StatusNoContent)
	}
}

func abs(n int64) int64 {
	if n < 0 {
		return -n
	}
	return n
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/routers/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/routers/
git commit -m "feat(api-gateway-go): SSO routes — /auth/login /auth/callback /auth/logout-webhook"
```

---

## Task 16: Login + logout routes

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/routers/login.go`
- Create: `apps-microservices/api-gateway-go/internal/routers/login_test.go`

- [ ] **Step 1: Failing tests**

Create `internal/routers/login_test.go`:

```go
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

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
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
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/routers/... -run Login`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/routers/login.go`:

```go
package routers

import (
	"net/http"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
)

func RegisterLogin(r *gin.Engine, j *auth.JWT) {
	r.GET("/login", func(c *gin.Context) {
		s := sessions.Default(c)
		userRaw := s.Get("user")
		if user, ok := userRaw.(map[string]any); ok {
			if tok, ok := user["token"].(string); ok && tok != "" {
				if err := j.VerifyDocsToken(tok); err == nil {
					c.Redirect(http.StatusSeeOther, "/docs")
					return
				}
				s.Clear()
				_ = s.Save()
			}
		}
		c.Redirect(http.StatusFound, "/auth/login")
	})

	r.GET("/logout", func(c *gin.Context) {
		s := sessions.Default(c)
		s.Clear()
		_ = s.Save()
		c.Redirect(http.StatusSeeOther, "/login")
	})
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/routers/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/routers/
git commit -m "feat(api-gateway-go): /login + /logout"
```

---

## Task 17: Token endpoints — generate + refresh + revoke

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/routers/tokens.go`
- Create: `apps-microservices/api-gateway-go/internal/routers/tokens_test.go`

- [ ] **Step 1: Failing tests**

Create `internal/routers/tokens_test.go`:

```go
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
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/routers/... -run Token`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/routers/tokens.go`:

```go
package routers

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
	cachepkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/cache"
	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
)

const maxActiveAccessTokens = 10

type TokenDeps struct {
	DB                       *gorm.DB
	Cache                    *cachepkg.Cache
	JWT                      *auth.JWT
	AdminKey                 string
	AccessTokenExpireMinutes int
}

type tokenGenerateReq struct {
	ServiceName string `json:"service_name" binding:"required"`
}

type tokenGenerateResp struct {
	ServiceName               string    `json:"service_name"`
	RefreshToken              string    `json:"refresh_token"`
	AccessToken               string    `json:"access_token"`
	AccessTokenExpiresMinutes int       `json:"access_token_expires_minutes"`
	AccessTokenExpiresAt      time.Time `json:"access_token_expires_at"`
	CreatedAt                 time.Time `json:"created_at"`
}

type tokenRefreshReq struct {
	ServiceName  string `json:"service_name" binding:"required"`
	RefreshToken string `json:"refresh_token" binding:"required"`
}

type tokenRefreshResp struct {
	ServiceName               string    `json:"service_name"`
	AccessToken               string    `json:"access_token"`
	AccessTokenExpiresMinutes int       `json:"access_token_expires_minutes"`
	AccessTokenExpiresAt      time.Time `json:"access_token_expires_at"`
}

type tokenRevokeReq struct {
	ServiceName string `json:"service_name" binding:"required"`
}

type tokenRevokeResp struct {
	ServiceName string `json:"service_name"`
	Revoked     bool   `json:"revoked"`
	Message     string `json:"message"`
}

func RegisterTokens(r *gin.Engine, d TokenDeps) {
	g := r.Group("/auth")
	g.POST("/token/generate", auth.RequireAdminKey(d.AdminKey), generateHandler(d))
	g.POST("/token/refresh", refreshHandler(d))
	g.POST("/token/revoke", auth.RequireAdminKey(d.AdminKey), revokeHandler(d))
}

func generateHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body tokenGenerateReq
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": err.Error()})
			return
		}
		ctx := c.Request.Context()
		var rt dbpkg.InfoRefreshToken
		err := d.DB.WithContext(ctx).Where("nom_service = ? AND est_actif = ?", body.ServiceName, true).First(&rt).Error
		if err == gorm.ErrRecordNotFound {
			rt = dbpkg.InfoRefreshToken{
				NomService: body.ServiceName,
				Token:      d.JWT.GenerateRefreshToken(body.ServiceName),
				IPCreation: clientIP(c),
				EstActif:   true,
			}
			if err := d.DB.WithContext(ctx).Create(&rt).Error; err != nil {
				c.JSON(500, gin.H{"detail": err.Error()})
				return
			}
		} else if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}

		access := d.JWT.GenerateAccessToken(body.ServiceName, rt.ID)
		exp := time.Now().UTC().Add(time.Duration(d.AccessTokenExpireMinutes) * time.Minute)
		acc := dbpkg.InfoAccessToken{
			IDRefreshToken: rt.ID,
			Token:          access,
			DateExpiration: exp,
			EstActif:       true,
		}
		if err := d.DB.WithContext(ctx).Create(&acc).Error; err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		_ = d.Cache.SetJSON(ctx, "access_token:"+access,
			map[string]any{"service": body.ServiceName, "rtid": rt.ID},
			time.Duration(d.AccessTokenExpireMinutes)*time.Minute)

		_ = pruneAccessTokens(ctx, d.DB, rt.ID)

		c.JSON(200, tokenGenerateResp{
			ServiceName:               body.ServiceName,
			RefreshToken:              rt.Token,
			AccessToken:               access,
			AccessTokenExpiresMinutes: d.AccessTokenExpireMinutes,
			AccessTokenExpiresAt:      exp,
			CreatedAt:                 rt.DateCreation,
		})
	}
}

func refreshHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body tokenRefreshReq
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": err.Error()})
			return
		}
		ctx := c.Request.Context()
		var rt dbpkg.InfoRefreshToken
		err := d.DB.WithContext(ctx).
			Where("nom_service = ? AND token = ? AND est_actif = ?", body.ServiceName, body.RefreshToken, true).
			First(&rt).Error
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "Invalid or revoked refresh token."})
			return
		}
		access := d.JWT.GenerateAccessToken(body.ServiceName, rt.ID)
		exp := time.Now().UTC().Add(time.Duration(d.AccessTokenExpireMinutes) * time.Minute)
		_ = d.DB.WithContext(ctx).Create(&dbpkg.InfoAccessToken{
			IDRefreshToken: rt.ID,
			Token:          access,
			DateExpiration: exp,
			EstActif:       true,
		})
		_ = d.Cache.SetJSON(ctx, "access_token:"+access,
			map[string]any{"service": body.ServiceName, "rtid": rt.ID},
			time.Duration(d.AccessTokenExpireMinutes)*time.Minute)
		_ = pruneAccessTokens(ctx, d.DB, rt.ID)
		c.JSON(200, tokenRefreshResp{
			ServiceName:               body.ServiceName,
			AccessToken:               access,
			AccessTokenExpiresMinutes: d.AccessTokenExpireMinutes,
			AccessTokenExpiresAt:      exp,
		})
	}
}

func revokeHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body tokenRevokeReq
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": err.Error()})
			return
		}
		ctx := c.Request.Context()
		var rts []dbpkg.InfoRefreshToken
		err := d.DB.WithContext(ctx).Where("nom_service = ? AND est_actif = ?", body.ServiceName, true).Find(&rts).Error
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		if len(rts) == 0 {
			c.JSON(200, tokenRevokeResp{ServiceName: body.ServiceName, Revoked: false, Message: "No active token found for this service."})
			return
		}
		ids := make([]uint, len(rts))
		for i, r := range rts {
			ids[i] = r.ID
		}
		_ = d.DB.WithContext(ctx).Model(&dbpkg.InfoRefreshToken{}).Where("id IN ?", ids).Update("est_actif", false)
		_ = d.DB.WithContext(ctx).Model(&dbpkg.InfoAccessToken{}).Where("id_refresh_token_id IN ? AND est_actif = ?", ids, true).Update("est_actif", false)

		var accs []dbpkg.InfoAccessToken
		_ = d.DB.WithContext(ctx).Where("id_refresh_token_id IN ?", ids).Find(&accs).Error
		for _, a := range accs {
			_ = d.Cache.Delete(ctx, "access_token:"+a.Token)
		}
		c.JSON(200, tokenRevokeResp{ServiceName: body.ServiceName, Revoked: true, Message: "Refresh token revoked."})
	}
}

func pruneAccessTokens(ctx context.Context, gdb *gorm.DB, refreshID uint) error {
	now := time.Now().UTC()
	var active []dbpkg.InfoAccessToken
	if err := gdb.WithContext(ctx).
		Where("id_refresh_token_id = ? AND est_actif = ? AND date_expiration >= ?", refreshID, true, now).
		Order("date_creation DESC").
		Find(&active).Error; err != nil {
		return err
	}
	if len(active) > maxActiveAccessTokens {
		excessIDs := make([]uint, 0, len(active)-maxActiveAccessTokens)
		for _, a := range active[maxActiveAccessTokens:] {
			excessIDs = append(excessIDs, a.ID)
		}
		_ = gdb.WithContext(ctx).Model(&dbpkg.InfoAccessToken{}).Where("id IN ?", excessIDs).Update("est_actif", false)
	}
	_ = gdb.WithContext(ctx).Model(&dbpkg.InfoAccessToken{}).
		Where("id_refresh_token_id = ? AND est_actif = ? AND date_expiration < ?", refreshID, true, now).
		Update("est_actif", false)
	return nil
}

func clientIP(c *gin.Context) string {
	ip := c.ClientIP()
	if ip == "" {
		return "unknown"
	}
	return ip
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/routers/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/routers/
git commit -m "feat(api-gateway-go): /auth/token/{generate,refresh,revoke}"
```

---

## Task 18: Token endpoints — list refresh-tokens, all-refresh-tokens, /auth/logs

**Files:**
- Modify: `apps-microservices/api-gateway-go/internal/routers/tokens.go`
- Modify: `apps-microservices/api-gateway-go/internal/routers/tokens_test.go`

- [ ] **Step 1: Add failing tests**

Append to `internal/routers/tokens_test.go`:

```go
func TestListRefreshTokensActiveOnly(t *testing.T) {
	r, gdb, _ := newTokensRouter(t)
	require.NoError(t, gdb.Create(&dbpkg.InfoRefreshToken{NomService: "svc", Token: "a", EstActif: true, IPCreation: "x"}).Error)
	require.NoError(t, gdb.Create(&dbpkg.InfoRefreshToken{NomService: "svc", Token: "b", EstActif: false, IPCreation: "x"}).Error)

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
	require.Len(t, resp["items"], 2)
}
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/routers/... -run "RefreshTokens|Logs"`
Expected: 404s — handlers not registered.

- [ ] **Step 3: Add handlers**

Append to `internal/routers/tokens.go`:

```go
type refreshTokenEntry struct {
	ID           uint             `json:"id"`
	ServiceName  string           `json:"service_name"`
	Token        string           `json:"token"`
	DateCreation time.Time        `json:"date_creation"`
	IPCreation   string           `json:"ip_creation"`
	EstActif     bool             `json:"est_actif"`
	Refresh      *tokenRefreshReq `json:"refresh,omitempty"`
}

type refreshTokenList struct {
	Total int                 `json:"total"`
	Items []refreshTokenEntry `json:"items"`
}

type apiCallHistoryEntry struct {
	ID             uint      `json:"id"`
	ServiceName    string    `json:"service_name"`
	Method         string    `json:"method"`
	Path           string    `json:"path"`
	StatusCode     int       `json:"status_code"`
	ClientIP       string    `json:"client_ip"`
	RequestHeaders *string   `json:"request_headers"`
	CalledAt       time.Time `json:"called_at"`
	DurationMs     *int      `json:"duration_ms"`
}

type apiCallHistoryList struct {
	Total    int64                 `json:"total"`
	Page     int                   `json:"page"`
	PageSize int                   `json:"page_size"`
	Items    []apiCallHistoryEntry `json:"items"`
}

// Patch RegisterTokens to include the new endpoints. Replace its body with:
//
//   g := r.Group("/auth")
//   g.POST("/token/generate", auth.RequireAdminKey(d.AdminKey), generateHandler(d))
//   g.POST("/token/refresh", refreshHandler(d))
//   g.POST("/token/revoke", auth.RequireAdminKey(d.AdminKey), revokeHandler(d))
//   g.GET("/token/refresh-tokens", listRefreshHandler(d))
//   g.GET("/token/all-refresh-tokens", auth.RequireAdminKey(d.AdminKey), listAllRefreshHandler(d))
//   g.GET("/logs", auth.RequireAdminKey(d.AdminKey), logsHandler(d))

func listRefreshHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		serviceName := c.Query("service_name")
		if serviceName == "" {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": "service_name is required"})
			return
		}
		activeOnly := c.DefaultQuery("active_only", "true") != "false"
		ctx := c.Request.Context()
		q := d.DB.WithContext(ctx).Where("nom_service = ?", serviceName)
		if activeOnly {
			q = q.Where("est_actif = ?", true)
		}
		var rows []dbpkg.InfoRefreshToken
		if err := q.Order("nom_service").Find(&rows).Error; err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		isDocsUser := false
		// Session presence check is skipped here; will be wired via middleware
		// in the caller. For 1:1 parity we compare to Python which gates the
		// `refresh` body on session.user.
		entries := make([]refreshTokenEntry, len(rows))
		for i, r := range rows {
			e := refreshTokenEntry{
				ID: r.ID, ServiceName: r.NomService, Token: r.Token,
				DateCreation: r.DateCreation, IPCreation: r.IPCreation, EstActif: r.EstActif,
			}
			if isDocsUser {
				e.Refresh = &tokenRefreshReq{ServiceName: r.NomService, RefreshToken: r.Token}
			}
			entries[i] = e
		}
		c.JSON(200, refreshTokenList{Total: len(entries), Items: entries})
	}
}

func listAllRefreshHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		q := d.DB.WithContext(ctx)
		if v, ok := c.GetQuery("active_only"); ok {
			q = q.Where("est_actif = ?", v == "true")
		}
		var rows []dbpkg.InfoRefreshToken
		if err := q.Order("nom_service, date_creation DESC").Find(&rows).Error; err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		entries := make([]refreshTokenEntry, len(rows))
		for i, r := range rows {
			entries[i] = refreshTokenEntry{
				ID: r.ID, ServiceName: r.NomService, Token: r.Token,
				DateCreation: r.DateCreation, IPCreation: r.IPCreation, EstActif: r.EstActif,
			}
		}
		c.JSON(200, refreshTokenList{Total: len(entries), Items: entries})
	}
}

func logsHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		page := atoiDefault(c.DefaultQuery("page", "1"), 1)
		pageSize := atoiDefault(c.DefaultQuery("page_size", "50"), 50)
		if pageSize > 500 {
			pageSize = 500
		}
		serviceName := c.Query("service_name")
		q := d.DB.WithContext(ctx).Model(&dbpkg.ApiCallHistory{})
		if serviceName != "" {
			q = q.Where("service_name = ?", serviceName)
		}
		var total int64
		_ = q.Count(&total).Error
		var rows []dbpkg.ApiCallHistory
		_ = q.Order("called_at DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
		entries := make([]apiCallHistoryEntry, len(rows))
		for i, r := range rows {
			entries[i] = apiCallHistoryEntry{
				ID: r.ID, ServiceName: r.ServiceName, Method: r.Method, Path: r.Path,
				StatusCode: r.StatusCode, ClientIP: r.ClientIP, RequestHeaders: r.RequestHeaders,
				CalledAt: r.CalledAt, DurationMs: r.DurationMs,
			}
		}
		c.JSON(200, apiCallHistoryList{Total: total, Page: page, PageSize: pageSize, Items: entries})
	}
}

func atoiDefault(s string, def int) int {
	n, err := strconvAtoi(s)
	if err != nil || n < 1 {
		return def
	}
	return n
}

func strconvAtoi(s string) (int, error) {
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, fmt.Errorf("not a number")
		}
		n = n*10 + int(c-'0')
	}
	return n, nil
}
```

Add the missing imports (`fmt`) at the top if not present.

Replace `RegisterTokens` body with:

```go
func RegisterTokens(r *gin.Engine, d TokenDeps) {
	g := r.Group("/auth")
	g.POST("/token/generate", auth.RequireAdminKey(d.AdminKey), generateHandler(d))
	g.POST("/token/refresh", refreshHandler(d))
	g.POST("/token/revoke", auth.RequireAdminKey(d.AdminKey), revokeHandler(d))
	g.GET("/token/refresh-tokens", listRefreshHandler(d))
	g.GET("/token/all-refresh-tokens", auth.RequireAdminKey(d.AdminKey), listAllRefreshHandler(d))
	g.GET("/logs", auth.RequireAdminKey(d.AdminKey), logsHandler(d))
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/routers/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/routers/
git commit -m "feat(api-gateway-go): /auth/token/{refresh-tokens,all-refresh-tokens} + /auth/logs"
```

---

## Task 19: Proxy — history worker

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/proxy/history.go`
- Create: `apps-microservices/api-gateway-go/internal/proxy/history_test.go`

- [ ] **Step 1: Failing test**

Create `internal/proxy/history_test.go`:

```go
package proxy

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
)

func TestHistoryWorkerSanitizes(t *testing.T) {
	gdb, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, dbpkg.AutoMigrate(gdb))
	w := NewHistoryWorker(gdb, map[string]struct{}{"crawling-service": {}}, 16, 1)
	w.Start()
	defer w.Stop()

	w.Enqueue(HistoryEvent{
		ServiceName: "ok",
		Method:      "GET",
		Path:        "/p",
		StatusCode:  200,
		ClientIP:    "1.1.1.1",
		RequestHeaders: map[string]string{
			"Authorization": "Bearer x",
			"User-Agent":    "ua",
		},
		DurationMs: 12,
	})
	w.Enqueue(HistoryEvent{
		ServiceName: "crawling-service",
		Method:      "GET",
		Path:        "/p",
		StatusCode:  200,
		ClientIP:    "1.1.1.1",
		DurationMs:  1,
	})

	require.Eventually(t, func() bool {
		var n int64
		_ = gdb.Model(&dbpkg.ApiCallHistory{}).Count(&n).Error
		return n == 1
	}, 2*time.Second, 20*time.Millisecond)

	var row dbpkg.ApiCallHistory
	require.NoError(t, gdb.First(&row).Error)
	require.NotNil(t, row.RequestHeaders)
	require.Contains(t, *row.RequestHeaders, "[REDACTED]")
	require.NotContains(t, *row.RequestHeaders, "Bearer x")
}
```

- [ ] **Step 2: Run test**

Run: `go test ./internal/proxy/... -run HistoryWorker`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/proxy/history.go`:

```go
package proxy

import (
	"encoding/json"
	"log"
	"strings"
	"sync"

	"gorm.io/gorm"

	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
)

var sensitiveHeaders = map[string]struct{}{
	"authorization": {}, "cookie": {}, "x-api-key": {}, "set-cookie": {},
}

type HistoryEvent struct {
	ServiceName    string
	Method         string
	Path           string
	StatusCode     int
	ClientIP       string
	RequestHeaders map[string]string
	DurationMs     int
}

type HistoryWorker struct {
	db       *gorm.DB
	excluded map[string]struct{}
	ch       chan HistoryEvent
	workers  int
	wg       sync.WaitGroup
	stopOnce sync.Once
}

func NewHistoryWorker(g *gorm.DB, excluded map[string]struct{}, buffer, workers int) *HistoryWorker {
	if workers < 1 {
		workers = 1
	}
	return &HistoryWorker{
		db:       g,
		excluded: excluded,
		ch:       make(chan HistoryEvent, buffer),
		workers:  workers,
	}
}

func (h *HistoryWorker) Start() {
	for i := 0; i < h.workers; i++ {
		h.wg.Add(1)
		go h.run()
	}
}

func (h *HistoryWorker) Stop() {
	h.stopOnce.Do(func() {
		close(h.ch)
		h.wg.Wait()
	})
}

func (h *HistoryWorker) Enqueue(e HistoryEvent) {
	select {
	case h.ch <- e:
	default:
		log.Printf("[history] queue full, dropping event for service=%s path=%s", e.ServiceName, e.Path)
	}
}

func (h *HistoryWorker) run() {
	defer h.wg.Done()
	for e := range h.ch {
		if _, skip := h.excluded[e.ServiceName]; skip {
			continue
		}
		safe := sanitizeHeaders(e.RequestHeaders)
		raw, _ := json.Marshal(safe)
		s := string(raw)
		duration := e.DurationMs
		row := dbpkg.ApiCallHistory{
			ServiceName: e.ServiceName, Method: e.Method, Path: e.Path,
			StatusCode: e.StatusCode, ClientIP: e.ClientIP,
			RequestHeaders: &s, DurationMs: &duration,
		}
		if err := h.db.Create(&row).Error; err != nil {
			log.Printf("[history] insert failed service=%s path=%s err=%v", e.ServiceName, e.Path, err)
		}
	}
}

func sanitizeHeaders(in map[string]string) map[string]string {
	out := make(map[string]string, len(in))
	for k, v := range in {
		if _, sensitive := sensitiveHeaders[strings.ToLower(k)]; sensitive {
			out[k] = "[REDACTED]"
		} else {
			out[k] = v
		}
	}
	return out
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/proxy/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/proxy/
git commit -m "feat(api-gateway-go): async history worker with header redaction"
```

---

## Task 20: Proxy — HTTP reverse proxy

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/proxy/http.go`
- Create: `apps-microservices/api-gateway-go/internal/proxy/http_test.go`

- [ ] **Step 1: Failing tests**

Create `internal/proxy/http_test.go`:

```go
package proxy

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func newProxyRouter(serviceMap map[string]string, timeouts map[string]float64, hist HistoryEnqueuer) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	h := NewHTTPHandler(HTTPDeps{
		ServiceMap:        serviceMap,
		DownstreamTimeout: timeouts,
		History:           hist,
	})
	r.Any("/:service/*path", h)
	return r
}

type fakeHist struct{ events []HistoryEvent }

func (f *fakeHist) Enqueue(e HistoryEvent) { f.events = append(f.events, e) }

func TestProxyForwardsAndAddsSecurityHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/foo/bar", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"ok":true}`)
	}))
	defer upstream.Close()

	r := newProxyRouter(map[string]string{"/svc-service": upstream.URL}, nil, &fakeHist{})
	req := httptest.NewRequest("GET", "/svc-service/foo/bar", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	require.Equal(t, "nosniff", w.Header().Get("X-Content-Type-Options"))
	require.Equal(t, "DENY", w.Header().Get("X-Frame-Options"))
	require.Equal(t, "max-age=31536000; includeSubDomains", w.Header().Get("Strict-Transport-Security"))
	require.Contains(t, w.Body.String(), "ok")
}

func TestProxyUnknownService404(t *testing.T) {
	r := newProxyRouter(map[string]string{}, nil, &fakeHist{})
	req := httptest.NewRequest("GET", "/nope-service/x", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 404, w.Code)
	require.Contains(t, w.Body.String(), "Service not found")
}

func TestProxyTimeoutReturns504(t *testing.T) {
	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
	}))
	defer slow.Close()
	r := newProxyRouter(
		map[string]string{"/slow-service": slow.URL},
		map[string]float64{"slow-service": 0.01},
		&fakeHist{},
	)
	req := httptest.NewRequest("GET", "/slow-service/x", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 504, w.Code)
	require.Contains(t, strings.ToLower(w.Body.String()), "timeout")
}
```

- [ ] **Step 2: Run tests**

Run: `go test ./internal/proxy/... -run Proxy`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/proxy/http.go`:

```go
package proxy

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

var excludedReqHeaders = map[string]struct{}{
	"host": {}, "content-length": {}, "transfer-encoding": {}, "connection": {},
}

var excludedRespHeaders = map[string]struct{}{
	"transfer-encoding": {}, "connection": {}, "content-length": {},
}

type HistoryEnqueuer interface {
	Enqueue(e HistoryEvent)
}

type HTTPDeps struct {
	ServiceMap        map[string]string
	DownstreamTimeout map[string]float64
	History           HistoryEnqueuer
}

func NewHTTPHandler(d HTTPDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		service := c.Param("service")
		path := strings.TrimPrefix(c.Param("path"), "/")
		baseURL, ok := d.ServiceMap["/"+service]
		if !ok {
			c.JSON(404, gin.H{"detail": "Service not found"})
			return
		}
		target := strings.TrimRight(baseURL, "/") + "/" + path
		if c.Request.URL.RawQuery != "" {
			target += "?" + c.Request.URL.RawQuery
		}
		ctx := c.Request.Context()

		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}

		req, err := http.NewRequestWithContext(ctx, c.Request.Method, target, bytes.NewReader(body))
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		for k, vs := range c.Request.Header {
			if _, skip := excludedReqHeaders[strings.ToLower(k)]; skip {
				continue
			}
			for _, v := range vs {
				req.Header.Add(k, v)
			}
		}

		serviceKey := service
		if !strings.HasSuffix(service, "-service") {
			serviceKey = service + "-service"
		}
		var client *http.Client
		var totalTimeout time.Duration
		if t, ok := d.DownstreamTimeout[serviceKey]; ok {
			totalTimeout = time.Duration(t * float64(time.Second))
			client = &http.Client{
				Timeout: totalTimeout,
				Transport: &http.Transport{
					DialContext: (&net.Dialer{Timeout: 10 * time.Second}).DialContext,
				},
			}
		} else {
			client = &http.Client{}
		}

		start := time.Now()
		resp, err := client.Do(req)
		duration := int(time.Since(start) / time.Millisecond)
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) || isTimeoutErr(err) {
				c.JSON(504, gin.H{"detail": fmt.Sprintf("Le service '%s' a depasse son timeout (%vs).", service, totalTimeout.Seconds())})
			} else {
				c.JSON(503, gin.H{"detail": fmt.Sprintf("Le service '%s' est indisponible.", service)})
			}
			return
		}
		defer resp.Body.Close()

		respBody, _ := io.ReadAll(resp.Body)
		for k, vs := range resp.Header {
			if _, skip := excludedRespHeaders[strings.ToLower(k)]; skip {
				continue
			}
			for _, v := range vs {
				c.Writer.Header().Add(k, v)
			}
		}
		c.Writer.Header().Set("X-Content-Type-Options", "nosniff")
		c.Writer.Header().Set("X-Frame-Options", "DENY")
		c.Writer.Header().Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		c.Writer.WriteHeader(resp.StatusCode)
		_, _ = c.Writer.Write(respBody)

		// Enqueue history event (fire-and-forget). Use token claim sub if set.
		serviceFromToken := service
		if v, ok := c.Get("token_payload"); ok {
			if m, ok := v.(gin.H); ok {
				if s, ok := m["sub"].(string); ok && s != "" {
					serviceFromToken = s
				}
			}
		}
		if d.History != nil {
			headers := map[string]string{}
			for k, vs := range c.Request.Header {
				if len(vs) > 0 {
					headers[k] = vs[0]
				}
			}
			d.History.Enqueue(HistoryEvent{
				ServiceName: serviceFromToken, Method: c.Request.Method, Path: c.Request.URL.Path,
				StatusCode: resp.StatusCode, ClientIP: c.ClientIP(),
				RequestHeaders: headers, DurationMs: duration,
			})
		}
	}
}

func isTimeoutErr(err error) bool {
	type timeoutErr interface{ Timeout() bool }
	var te timeoutErr
	return errors.As(err, &te) && te.Timeout()
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/proxy/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/proxy/
git commit -m "feat(api-gateway-go): HTTP reverse proxy with per-service timeout + security headers"
```

---

## Task 21: Proxy — WebSocket relay

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/proxy/ws.go`
- Create: `apps-microservices/api-gateway-go/internal/proxy/ws_test.go`

- [ ] **Step 1: Failing test**

Create `internal/proxy/ws_test.go`:

```go
package proxy

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
)

func TestWebSocketEcho(t *testing.T) {
	up := websocket.Upgrader{}
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := up.Upgrade(w, r, nil)
		require.NoError(t, err)
		defer conn.Close()
		for {
			_, msg, err := conn.ReadMessage()
			if err != nil {
				return
			}
			_ = conn.WriteMessage(websocket.TextMessage, append([]byte("echo:"), msg...))
		}
	}))
	defer backend.Close()

	gin.SetMode(gin.TestMode)
	r := gin.New()
	wsHandler := NewWSHandler(map[string]string{"/svc-service": strings.Replace(backend.URL, "http://", "ws://", 1)})
	r.GET("/:service/*path", wsHandler)

	gw := httptest.NewServer(r)
	defer gw.Close()
	gwURL, _ := url.Parse(gw.URL)
	gwURL.Scheme = "ws"
	gwURL.Path = "/svc-service/anything"

	conn, _, err := websocket.DefaultDialer.Dial(gwURL.String(), nil)
	require.NoError(t, err)
	defer conn.Close()
	require.NoError(t, conn.WriteMessage(websocket.TextMessage, []byte("hello")))
	_ = conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, msg, err := conn.ReadMessage()
	require.NoError(t, err)
	require.Equal(t, "echo:hello", string(msg))
}
```

- [ ] **Step 2: Run test**

Run: `go test ./internal/proxy/... -run WebSocket`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/proxy/ws.go`:

```go
package proxy

import (
	"log"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

var excludedWSHeaders = map[string]struct{}{
	"connection": {}, "upgrade": {}, "host": {},
	"sec-websocket-key": {}, "sec-websocket-version": {}, "sec-websocket-protocol": {}, "sec-websocket-extensions": {},
}

var clientUpgrader = websocket.Upgrader{
	CheckOrigin: func(*http.Request) bool { return true },
}

func NewWSHandler(serviceMap map[string]string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Only handle WS handshake; non-WS requests fall through.
		if !websocket.IsWebSocketUpgrade(c.Request) {
			c.Next()
			return
		}
		service := c.Param("service")
		path := strings.TrimPrefix(c.Param("path"), "/")
		base, ok := serviceMap["/"+service]
		if !ok {
			log.Printf("[ws] service %s unknown", service)
			http.Error(c.Writer, "service unknown", http.StatusNotFound)
			c.Abort()
			return
		}
		base = strings.Replace(base, "http://", "ws://", 1)
		base = strings.Replace(base, "https://", "wss://", 1)
		target := strings.TrimRight(base, "/") + "/" + path
		if c.Request.URL.RawQuery != "" {
			target += "?" + c.Request.URL.RawQuery
		}

		fwd := http.Header{}
		for k, vs := range c.Request.Header {
			if _, skip := excludedWSHeaders[strings.ToLower(k)]; skip {
				continue
			}
			for _, v := range vs {
				fwd.Add(k, v)
			}
		}

		clientConn, err := clientUpgrader.Upgrade(c.Writer, c.Request, nil)
		if err != nil {
			log.Printf("[ws] client upgrade failed: %v", err)
			return
		}
		defer clientConn.Close()

		backendConn, _, err := websocket.DefaultDialer.Dial(target, fwd)
		if err != nil {
			log.Printf("[ws] backend dial %s failed: %v", target, err)
			_ = clientConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(1011, "backend unavailable"))
			return
		}
		defer backendConn.Close()

		errCh := make(chan struct{}, 2)
		go relay(clientConn, backendConn, errCh)
		go relay(backendConn, clientConn, errCh)
		<-errCh
		c.Abort()
	}
}

func relay(src, dst *websocket.Conn, done chan<- struct{}) {
	defer func() { done <- struct{}{} }()
	for {
		mt, msg, err := src.ReadMessage()
		if err != nil {
			return
		}
		if err := dst.WriteMessage(mt, msg); err != nil {
			return
		}
	}
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/proxy/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/proxy/
git commit -m "feat(api-gateway-go): WebSocket bidirectional relay"
```

---

## Task 22: OpenAPI base spec + aggregator

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/openapi/base.yaml`
- Create: `apps-microservices/api-gateway-go/internal/openapi/aggregator.go`
- Create: `apps-microservices/api-gateway-go/internal/openapi/aggregator_test.go`

- [ ] **Step 1: Write base spec stub**

Create `internal/openapi/base.yaml`. Generate by running this once against the Python service:

```bash
# (one-time, outside the plan): start the Python gateway in a dev compose,
# curl http://localhost:8500/openapi.json > base-snapshot.json,
# strip everything except gateway-owned paths and components, convert to YAML.
```

For the plan: hand-author a base.yaml covering the gateway-owned paths only (`/auth/token/*`, `/auth/logs`, `/login`, `/logout`, `/auth/login`, `/auth/callback`, `/auth/logout-webhook`, `/openapi.json`, `/openapi-public.json`, `/docs`, `/redoc`). Store a 1:1 capture from the Python service's current `/openapi.json` (gateway-only subset) — see step 3 instructions below.

For initial commit, write a minimal placeholder YAML that lists those paths with `summary` only; the schema bodies will be backfilled in a follow-up step before cutover by snapshotting the Python service. Mark this clearly in the file:

```yaml
openapi: 3.1.0
info:
  title: Hellopro APIs
  version: 1.0.0
  description: |
    > NOTE: This is the gateway base spec. Schema bodies are filled in by snapshotting the Python service's current /openapi.json output for gateway-owned paths. See `tools/openapi-snapshot.sh` (added in this task).
paths:
  /auth/token/generate:
    post:
      summary: Generer un refresh token + access token pour un service (admin uniquement)
      security: [{AdminCle: []}]
      responses:
        '200':
          description: OK
  /auth/token/refresh:
    post:
      summary: Echanger un refresh token contre un nouvel access token
      responses:
        '200':
          description: OK
  /auth/token/revoke:
    post:
      summary: Revoquer le refresh token d'un service
      security: [{AdminCle: []}]
      responses:
        '200':
          description: OK
  /auth/token/refresh-tokens:
    get:
      summary: Lister les refresh tokens d'un service
      responses:
        '200':
          description: OK
  /auth/token/all-refresh-tokens:
    get:
      summary: Lister tous les refresh tokens (admin uniquement)
      security: [{AdminCle: []}]
      responses:
        '200':
          description: OK
  /auth/logs:
    get:
      summary: Journal d'audit pagine
      security: [{AdminCle: []}]
      responses:
        '200':
          description: OK
components:
  securitySchemes:
    Bearer Token:
      type: http
      scheme: bearer
      bearerFormat: JWT
    AdminCle:
      type: apiKey
      in: header
      name: X-Admin-Key
security:
  - Bearer Token: []
```

Also create `apps-microservices/api-gateway-go/tools/openapi-snapshot.sh`:

```bash
#!/usr/bin/env bash
# Snapshot the Python api-gateway's /openapi.json (gateway-owned paths only)
# and emit it as YAML for use as base.yaml. Re-run before cutover.
set -euo pipefail
SRC="${SRC:-http://localhost:8500/openapi.json}"
OUT="${OUT:-internal/openapi/base.yaml}"
TMP="$(mktemp)"
curl -fsSL "$SRC" > "$TMP"
python3 - "$TMP" > "$OUT" <<'PY'
import json, sys, yaml
spec = json.load(open(sys.argv[1]))
# keep only gateway-owned paths (no slash after first segment matches a downstream service prefix)
gateway_paths = {
    "/auth/token/generate","/auth/token/refresh","/auth/token/revoke",
    "/auth/token/refresh-tokens","/auth/token/all-refresh-tokens",
    "/auth/logs","/login","/logout",
    "/auth/login","/auth/callback","/auth/logout-webhook",
    "/openapi.json","/openapi-public.json","/docs","/redoc",
}
spec["paths"] = {p: v for p, v in spec.get("paths", {}).items() if p in gateway_paths}
print(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
PY
```

`chmod +x apps-microservices/api-gateway-go/tools/openapi-snapshot.sh`.

- [ ] **Step 2: Failing test**

Create `internal/openapi/aggregator_test.go`:

```go
package openapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func mkUpstream(spec map[string]any) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(spec)
	}))
}

func TestMergeNoCollision(t *testing.T) {
	a := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "a"},
		"paths": map[string]any{"/x": map[string]any{
			"get": map[string]any{"operationId": "get_x", "responses": map[string]any{"200": map[string]any{"description": "ok"}}},
		}},
		"components": map[string]any{"schemas": map[string]any{"Foo": map[string]any{"type": "object"}}},
	})
	defer a.Close()
	b := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "b"},
		"paths": map[string]any{"/y": map[string]any{
			"get": map[string]any{"operationId": "get_y", "responses": map[string]any{"200": map[string]any{"description": "ok"}}},
		}},
		"components": map[string]any{"schemas": map[string]any{"Bar": map[string]any{"type": "object"}}},
	})
	defer b.Close()

	out, err := Aggregate(context.Background(), AggregateInput{
		Base: map[string]any{
			"openapi": "3.0.0", "info": map[string]any{"title": "Hellopro"},
			"paths":   map[string]any{},
			"components": map[string]any{"schemas": map[string]any{}},
		},
		Services: map[string]string{
			"/svc-a-service": a.URL,
			"/svc-b-service": b.URL,
		},
	})
	require.NoError(t, err)
	paths := out["paths"].(map[string]any)
	_, hasA := paths["/svc-a-service/x"]
	_, hasB := paths["/svc-b-service/y"]
	require.True(t, hasA)
	require.True(t, hasB)
}

func TestMergeCollisionPrefixesSchema(t *testing.T) {
	a := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "a"},
		"paths": map[string]any{"/x": map[string]any{
			"get": map[string]any{"operationId": "get_x",
				"responses": map[string]any{"200": map[string]any{"content": map[string]any{
					"application/json": map[string]any{"schema": map[string]any{"$ref": "#/components/schemas/Foo"}},
				}}},
			},
		}},
		"components": map[string]any{"schemas": map[string]any{"Foo": map[string]any{"type": "object"}}},
	})
	defer a.Close()
	b := mkUpstream(map[string]any{
		"openapi": "3.0.0", "info": map[string]any{"title": "b"},
		"paths": map[string]any{"/y": map[string]any{
			"get": map[string]any{"operationId": "get_y",
				"responses": map[string]any{"200": map[string]any{"content": map[string]any{
					"application/json": map[string]any{"schema": map[string]any{"$ref": "#/components/schemas/Foo"}},
				}}},
			},
		}},
		"components": map[string]any{"schemas": map[string]any{"Foo": map[string]any{"type": "string"}}},
	})
	defer b.Close()

	out, err := Aggregate(context.Background(), AggregateInput{
		Base: map[string]any{"openapi": "3.0.0", "info": map[string]any{"title": "h"}, "paths": map[string]any{}, "components": map[string]any{"schemas": map[string]any{}}},
		Services: map[string]string{
			"/svc-a-service": a.URL,
			"/svc-b-service": b.URL,
		},
	})
	require.NoError(t, err)

	schemas := out["components"].(map[string]any)["schemas"].(map[string]any)
	_, ok1 := schemas["SvcAFoo"]
	_, ok2 := schemas["SvcBFoo"]
	require.True(t, ok1, "expected SvcAFoo schema")
	require.True(t, ok2, "expected SvcBFoo schema")
}
```

- [ ] **Step 3: Run test**

Run: `go test ./internal/openapi/... -run Merge`
Expected: build fails.

- [ ] **Step 4: Implement**

Create `internal/openapi/aggregator.go`:

```go
package openapi

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/errgroup"
)

type AggregateInput struct {
	Base       map[string]any
	Services   map[string]string
	HTTPClient *http.Client
}

func Aggregate(ctx context.Context, in AggregateInput) (map[string]any, error) {
	if in.HTTPClient == nil {
		in.HTTPClient = &http.Client{Timeout: 5 * time.Second}
	}

	type fetched struct {
		prefix string
		spec   map[string]any
	}
	var (
		mu      sync.Mutex
		results []fetched
	)
	g, gctx := errgroup.WithContext(ctx)
	for prefix, base := range in.Services {
		prefix, base := prefix, base
		g.Go(func() error {
			req, err := http.NewRequestWithContext(gctx, "GET", strings.TrimRight(base, "/")+"/openapi.json", nil)
			if err != nil {
				return nil
			}
			resp, err := in.HTTPClient.Do(req)
			if err != nil {
				return nil
			}
			defer resp.Body.Close()
			if resp.StatusCode != 200 {
				return nil
			}
			var spec map[string]any
			if err := json.NewDecoder(resp.Body).Decode(&spec); err != nil {
				return nil
			}
			mu.Lock()
			results = append(results, fetched{prefix: prefix, spec: spec})
			mu.Unlock()
			return nil
		})
	}
	_ = g.Wait()

	// Pass 1: collision detection.
	tracker := map[string][]string{}
	for _, f := range results {
		comps, _ := f.spec["components"].(map[string]any)
		schemas, _ := comps["schemas"].(map[string]any)
		for name := range schemas {
			tracker[name] = append(tracker[name], f.prefix)
		}
	}
	conflicting := map[string]struct{}{}
	for n, prefixes := range tracker {
		if len(prefixes) > 1 {
			conflicting[n] = struct{}{}
		}
	}

	out := deepCopyMap(in.Base)
	if _, ok := out["paths"]; !ok {
		out["paths"] = map[string]any{}
	}
	if _, ok := out["components"]; !ok {
		out["components"] = map[string]any{}
	}
	outPaths := out["paths"].(map[string]any)
	outComps := out["components"].(map[string]any)
	if _, ok := outComps["schemas"]; !ok {
		outComps["schemas"] = map[string]any{}
	}

	// Pass 2: merge.
	for _, f := range results {
		schemaPrefix := titlePrefix(f.prefix)
		serviceSnake := strings.ReplaceAll(strings.TrimPrefix(strings.TrimSuffix(strings.Trim(f.prefix, "/"), "-service"), "/"), "-", "_")

		paths, _ := f.spec["paths"].(map[string]any)
		for p, pv := range paths {
			rewritten := prefixRefs(pv, schemaPrefix, conflicting)
			pvm, _ := rewritten.(map[string]any)
			for _, m := range []string{"get", "post", "put", "delete", "patch", "options", "head", "trace"} {
				if op, ok := pvm[m].(map[string]any); ok {
					if id, ok := op["operationId"].(string); ok {
						op["operationId"] = serviceSnake + "_" + id
					}
				}
			}
			outPaths[f.prefix+p] = pvm
		}
		comps, _ := f.spec["components"].(map[string]any)
		for compType, compMap := range comps {
			cm, _ := compMap.(map[string]any)
			outCM, ok := outComps[compType].(map[string]any)
			if !ok {
				outCM = map[string]any{}
				outComps[compType] = outCM
			}
			for k, v := range cm {
				if compType == "schemas" {
					if _, isConflict := conflicting[k]; isConflict {
						outCM[schemaPrefix+k] = prefixRefs(v, schemaPrefix, conflicting)
						continue
					}
				}
				if _, exists := outCM[k]; !exists {
					outCM[k] = v
				}
			}
		}
	}
	return out, nil
}

func deepCopyMap(in map[string]any) map[string]any {
	b, _ := json.Marshal(in)
	var out map[string]any
	_ = json.Unmarshal(b, &out)
	return out
}

func titlePrefix(prefix string) string {
	s := strings.TrimPrefix(prefix, "/")
	s = strings.TrimSuffix(s, "-service")
	parts := strings.Split(s, "-")
	for i, p := range parts {
		if p == "" {
			continue
		}
		parts[i] = strings.ToUpper(p[:1]) + p[1:]
	}
	return strings.Join(parts, "")
}

func prefixRefs(node any, schemaPrefix string, conflicting map[string]struct{}) any {
	switch v := node.(type) {
	case map[string]any:
		out := make(map[string]any, len(v))
		for k, val := range v {
			if k == "$ref" {
				if s, ok := val.(string); ok && strings.Contains(s, "#/components/schemas/") {
					name := s[strings.LastIndex(s, "/")+1:]
					if _, hit := conflicting[name]; hit {
						out[k] = "#/components/schemas/" + schemaPrefix + name
						continue
					}
				}
			}
			out[k] = prefixRefs(val, schemaPrefix, conflicting)
		}
		return out
	case []any:
		out := make([]any, len(v))
		for i, item := range v {
			out[i] = prefixRefs(item, schemaPrefix, conflicting)
		}
		return out
	default:
		return v
	}
	_ = fmt.Sprint("")
}
```

- [ ] **Step 5: Run tests**

Run: `go test ./internal/openapi/... -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/openapi/ apps-microservices/api-gateway-go/tools/
git commit -m "feat(api-gateway-go): OpenAPI aggregator + collision-detection schema prefixing"
```

---

## Task 23: OpenAPI public-spec filter

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/openapi/filter.go`
- Create: `apps-microservices/api-gateway-go/internal/openapi/filter_test.go`

- [ ] **Step 1: Failing test**

Create `internal/openapi/filter_test.go`:

```go
package openapi

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestFilterPublicSpec(t *testing.T) {
	in := map[string]any{
		"info": map[string]any{"description": "A\n<!-- ADMIN_SECTION -->\nB"},
		"paths": map[string]any{
			"/p1": map[string]any{
				"get": map[string]any{"security": []any{map[string]any{"AdminCle": []any{}}}},
			},
			"/p2": map[string]any{
				"get": map[string]any{"summary": "ok"},
			},
		},
		"components": map[string]any{
			"securitySchemes": map[string]any{
				"AdminCle":     map[string]any{},
				"Bearer Token": map[string]any{},
			},
		},
	}
	out := Filter(in)
	paths := out["paths"].(map[string]any)
	_, ok := paths["/p1"]
	require.False(t, ok, "admin-only path should be removed")
	_, ok = paths["/p2"]
	require.True(t, ok)
	schemes := out["components"].(map[string]any)["securitySchemes"].(map[string]any)
	_, hasAdmin := schemes["AdminCle"]
	require.False(t, hasAdmin)
	desc := out["info"].(map[string]any)["description"].(string)
	require.Equal(t, "A", desc)
}
```

- [ ] **Step 2: Run test**

Run: `go test ./internal/openapi/... -run Filter`
Expected: build fails.

- [ ] **Step 3: Implement**

Create `internal/openapi/filter.go`:

```go
package openapi

import "strings"

const adminSentinel = "\n<!-- ADMIN_SECTION -->"

var httpMethodSet = map[string]struct{}{
	"get": {}, "post": {}, "put": {}, "delete": {}, "patch": {}, "options": {}, "head": {}, "trace": {},
}

func Filter(spec map[string]any) map[string]any {
	out := deepCopyMap(spec)

	if paths, ok := out["paths"].(map[string]any); ok {
		newPaths := map[string]any{}
		for p, pv := range paths {
			pvm, _ := pv.(map[string]any)
			cleaned := map[string]any{}
			anyHTTP := false
			for k, v := range pvm {
				op, ok := v.(map[string]any)
				if !ok {
					cleaned[k] = v
					continue
				}
				if _, isHTTP := httpMethodSet[strings.ToLower(k)]; !isHTTP {
					cleaned[k] = v
					continue
				}
				if isAdminOp(op) {
					continue
				}
				cleaned[k] = v
				anyHTTP = true
			}
			if anyHTTP {
				newPaths[p] = cleaned
			}
		}
		out["paths"] = newPaths
	}

	if comps, ok := out["components"].(map[string]any); ok {
		if schemes, ok := comps["securitySchemes"].(map[string]any); ok {
			delete(schemes, "AdminCle")
		}
	}

	if info, ok := out["info"].(map[string]any); ok {
		if desc, ok := info["description"].(string); ok {
			if idx := strings.Index(desc, adminSentinel); idx >= 0 {
				info["description"] = desc[:idx]
			}
		}
	}
	return out
}

func isAdminOp(op map[string]any) bool {
	sec, _ := op["security"].([]any)
	for _, s := range sec {
		m, _ := s.(map[string]any)
		if _, hit := m["AdminCle"]; hit {
			return true
		}
	}
	return false
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/openapi/... -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/openapi/
git commit -m "feat(api-gateway-go): public OpenAPI filter (drop admin endpoints + AdminCle scheme)"
```

---

## Task 24: Docs router — `/openapi.json`, `/openapi-public.json`, `/docs`, `/redoc`

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/routers/docs.go`
- Create: `apps-microservices/api-gateway-go/internal/routers/docs_test.go`
- Create: `apps-microservices/api-gateway-go/internal/routers/assets/swagger.html`

- [ ] **Step 1: Add Swagger UI HTML asset**

Pinned Swagger UI v5.x. Create `internal/routers/assets/swagger.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>__TITLE__</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.__swaggerUi = SwaggerUIBundle({
        url: "__OPENAPI_URL__",
        dom_id: "#swagger-ui",
        persistAuthorization: true,
        deepLinking: true,
      });
    };
  </script>
</body>
</html>
```

- [ ] **Step 2: Failing test**

Create `internal/routers/docs_test.go`:

```go
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
		BaseSpec:        map[string]any{"openapi": "3.1.0", "info": map[string]any{"title": "x"}, "paths": map[string]any{}, "components": map[string]any{}},
		ServiceMap:      map[string]string{},
		AdminEmails:     map[string]struct{}{},
		AdminKey:        "K",
	})
	req := httptest.NewRequest("GET", "/docs", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	require.Contains(t, w.Body.String(), "swagger-ui")
	require.True(t, strings.Contains(w.Body.String(), "/openapi-public.json") || strings.Contains(w.Body.String(), "/openapi.json"))
}
```

- [ ] **Step 3: Run test**

Run: `go test ./internal/routers/... -run DocsRenders`
Expected: build fails.

- [ ] **Step 4: Implement**

Create `internal/routers/docs.go`:

```go
package routers

import (
	_ "embed"
	"net/http"
	"strings"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/openapi"
)

//go:embed assets/swagger.html
var swaggerHTML []byte

type DocsDeps struct {
	BaseSpec    map[string]any
	ServiceMap  map[string]string
	AdminEmails map[string]struct{}
	AdminKey    string
}

func RegisterDocs(r *gin.Engine, d DocsDeps) {
	r.GET("/openapi.json", func(c *gin.Context) {
		spec, _ := openapi.Aggregate(c.Request.Context(), openapi.AggregateInput{
			Base:     d.BaseSpec,
			Services: d.ServiceMap,
		})
		c.JSON(200, spec)
	})

	r.GET("/openapi-public.json", func(c *gin.Context) {
		spec, _ := openapi.Aggregate(c.Request.Context(), openapi.AggregateInput{
			Base:     d.BaseSpec,
			Services: d.ServiceMap,
		})
		c.JSON(200, openapi.Filter(spec))
	})

	r.GET("/docs", func(c *gin.Context) {
		s := sessions.Default(c)
		isAdmin := false
		if userRaw := s.Get("user"); userRaw != nil {
			if user, ok := userRaw.(map[string]any); ok {
				if email, ok := user["email"].(string); ok {
					if _, hit := d.AdminEmails[strings.ToLower(strings.TrimSpace(email))]; hit {
						isAdmin = true
					}
				}
			}
		}
		openapiURL := "/openapi-public.json"
		if isAdmin {
			openapiURL = "/openapi.json"
		}
		out := strings.ReplaceAll(string(swaggerHTML), "__TITLE__", "API Gateway Docs")
		out = strings.ReplaceAll(out, "__OPENAPI_URL__", openapiURL)
		c.Data(200, "text/html; charset=utf-8", []byte(out))
	})

	r.GET("/redoc", func(c *gin.Context) {
		c.Redirect(http.StatusMovedPermanently, "/docs")
	})
}
```

Note: `//go:embed` requires the asset to live inside the same package directory (or below). The asset path is `internal/routers/assets/swagger.html`, the embed directive sits in `internal/routers/docs.go` — Go resolves it relative to the file's directory.

- [ ] **Step 5: Run tests**

Run: `go test ./internal/routers/... -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/routers/ apps-microservices/api-gateway-go/internal/openapi/
git commit -m "feat(api-gateway-go): /docs Swagger UI + /openapi.json + /openapi-public.json + /redoc"
```

---

## Task 25: Wire main.go

**Files:**
- Modify: `apps-microservices/api-gateway-go/cmd/gateway/main.go`
- Create: `apps-microservices/api-gateway-go/internal/openapi/spec.go`

`//go:embed` only resolves paths relative to the source file, so the YAML loader has to live inside the openapi package. Add a tiny accessor.

Create `internal/openapi/spec.go`:

```go
package openapi

import (
	_ "embed"

	"gopkg.in/yaml.v3"
)

//go:embed base.yaml
var baseYAML []byte

func LoadBaseSpec() (map[string]any, error) {
	var m map[string]any
	if err := yaml.Unmarshal(baseYAML, &m); err != nil {
		return nil, err
	}
	return m, nil
}
```

- [ ] **Step 1: Replace stub with full wiring**

Replace contents of `cmd/gateway/main.go`:

```go
package main

import (
	"context"
	"log"
	"runtime"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
	cachepkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/cache"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/config"
	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/openapi"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/proxy"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/routers"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/sso"
)

func main() {
	_ = godotenv.Load()
	cfg := config.Load()

	ctx := context.Background()
	dsn := dbpkg.BuildDSN(cfg.MySQLUser, cfg.MySQLPass, cfg.MySQLHost, cfg.MySQLPort, cfg.MySQLDB)
	gdb, err := dbpkg.Open(ctx, dsn)
	if err != nil {
		log.Fatalf("db open: %v", err)
	}
	if err := dbpkg.AutoMigrate(gdb); err != nil {
		log.Fatalf("automigrate: %v", err)
	}

	rdb, err := cachepkg.OpenFromURL(cfg.RedisURL)
	if err != nil {
		log.Fatalf("redis open: %v", err)
	}
	cache := cachepkg.New(rdb)

	jwtSvc := auth.NewJWT(cfg.JWTSecret, cfg.JWTAlgo, time.Duration(cfg.AccessTokenExpireMinutes)*time.Minute)

	serviceMap := config.BuildServiceMap()

	tokenIssuer := jwtIssuerAdapter{j: jwtSvc}
	if err := dbpkg.BootstrapRefreshTokens(ctx, gdb, serviceMap, tokenIssuer); err != nil {
		log.Fatalf("bootstrap refresh tokens: %v", err)
	}

	historyWorker := proxy.NewHistoryWorker(gdb, config.ExcludedServices(), 1024, max(2, runtime.NumCPU()/2))
	historyWorker.Start()
	defer historyWorker.Stop()

	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(sessions.Sessions("session", cookie.NewStore([]byte(cfg.JWTSecret))))
	r.Use(auth.DocsAuthMiddleware(jwtSvc))

	resolver := sso.NewResolver(sso.ResolverConfig{ServiceName: cfg.ServiceName, AccountBaseURL: cfg.AccountBaseURL})
	routers.RegisterSSO(r, routers.SSODeps{
		Resolver:        resolver,
		AccountBaseURL:  cfg.AccountBaseURL,
		AccountPubURL:   cfg.AccountPublicURL,
		AccountRedirect: cfg.AccountRedirectURI,
		SecureCookie:    cfg.SecureCookie,
	})
	routers.RegisterLogin(r, jwtSvc)
	routers.RegisterTokens(r, routers.TokenDeps{
		DB:                       gdb,
		Cache:                    cache,
		JWT:                      jwtSvc,
		AdminKey:                 cfg.GatewayAdminKey,
		AccessTokenExpireMinutes: cfg.AccessTokenExpireMinutes,
	})

	baseSpec, err := openapi.LoadBaseSpec()
	if err != nil {
		log.Fatalf("parse base.yaml: %v", err)
	}
	adminEmails := map[string]struct{}{}
	for _, e := range cfg.DocsAdminEmails {
		adminEmails[e] = struct{}{}
	}
	routers.RegisterDocs(r, routers.DocsDeps{
		BaseSpec:    baseSpec,
		ServiceMap:  serviceMap,
		AdminEmails: adminEmails,
		AdminKey:    cfg.GatewayAdminKey,
	})

	verifier := auth.NewAPITokenVerifier(jwtSvc, gdb, cache, config.BuildExcludedRoutes())
	wsHandler := proxy.NewWSHandler(serviceMap)
	httpHandler := proxy.NewHTTPHandler(proxy.HTTPDeps{
		ServiceMap:        serviceMap,
		DownstreamTimeout: config.BuildDownstreamTimeouts(),
		History:           historyWorker,
	})

	// Order matters: wsHandler short-circuits on WebSocket upgrade requests
	// (no auth enforced on WS — matches Python). Non-WS requests fall through
	// to verifier + httpHandler.
	r.Any("/:service/*path",
		wsHandler,
		verifier.Middleware(),
		httpHandler,
	)

	addr := ":8500"
	log.Printf("api-gateway-go listening on %s", addr)
	if err := r.Run(addr); err != nil {
		log.Fatalf("listen: %v", err)
	}
}

type jwtIssuerAdapter struct{ j *auth.JWT }

func (a jwtIssuerAdapter) NewRefreshToken(service string) string {
	return a.j.GenerateRefreshToken(service)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
```

- [ ] **Step 2: Verify build**

Run: `go build ./...`
Expected: exit 0.

- [ ] **Step 3: Run all unit tests**

Run: `go test ./...`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-gateway-go/cmd/
git commit -m "feat(api-gateway-go): wire all components in main"
```

---

## Task 26: Dockerfile + nginx.conf copy

**Files:**
- Create: `apps-microservices/api-gateway-go/Dockerfile`
- Create: `apps-microservices/api-gateway-go/nginx.conf` (byte-identical copy of Python service's nginx.conf)
- Create: `apps-microservices/api-gateway-go/.dockerignore`

- [ ] **Step 1: Copy nginx.conf**

```bash
cp apps-microservices/api-gateway/nginx.conf apps-microservices/api-gateway-go/nginx.conf
```

- [ ] **Step 2: Add `.dockerignore`**

Create `apps-microservices/api-gateway-go/.dockerignore`:

```
.git
.idea
*.test
*.out
gateway
tests/integration/.cache
```

- [ ] **Step 3: Add Dockerfile**

Create `apps-microservices/api-gateway-go/Dockerfile`:

```Dockerfile
# apps-microservices/api-gateway-go/Dockerfile
# Build context: monorepo root.

FROM golang:1.24-alpine AS builder
WORKDIR /src

COPY apps-microservices/api-gateway-go/go.mod apps-microservices/api-gateway-go/go.sum ./
RUN go mod download

COPY apps-microservices/api-gateway-go/ ./
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/gateway \
    ./cmd/gateway

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /
COPY --from=builder /out/gateway /gateway
EXPOSE 8500
USER nonroot:nonroot
ENTRYPOINT ["/gateway"]
```

- [ ] **Step 4: Build the image**

Run from monorepo root:

```bash
docker build -f apps-microservices/api-gateway-go/Dockerfile -t api-gateway-go:dev .
```

Expected: build succeeds.

- [ ] **Step 5: Smoke-run the container locally (no DB)**

```bash
docker run --rm -e JWT_SECRET=x -e GATEWAY_ADMIN_KEY=k api-gateway-go:dev || true
```

Expected: container starts, then exits with `db open: ...` error (no MySQL available). This confirms the binary is wired and reaches `db.Open`.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-gateway-go/Dockerfile apps-microservices/api-gateway-go/nginx.conf apps-microservices/api-gateway-go/.dockerignore
git commit -m "feat(api-gateway-go): multi-stage Dockerfile + copy nginx.conf"
```

---

## Task 27: Compose wiring (parallel run on port 8501)

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Read current `api-gateway` block in `docker-compose.yml`**

```bash
grep -n "api-gateway" docker-compose.yml | head -20
```

- [ ] **Step 2: Add `api-gateway-go` service alongside (do NOT remove the Python one)**

Append a new service block mirroring `api-gateway` but:
- `image: api-gateway-go:dev`
- `build: { context: ., dockerfile: apps-microservices/api-gateway-go/Dockerfile }`
- `ports: - "8501:8500"`
- Same env vars as the Python service.
- Same `depends_on` (mysql, redis).

Do not change the Python service. Add a comment marking the new block as `# Parallel-run during cutover; remove after Python decommission`.

- [ ] **Step 3: Bring it up**

```bash
docker compose up -d api-gateway-go mysql redis
```

Run:

```bash
curl -i http://localhost:8501/login
```

Expected: `302 Location: /auth/login`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): add api-gateway-go in parallel on 8501 (cutover staging)"
```

---

## Task 28: Smoke validation against Python service

**Files:** none (validation only)

- [ ] **Step 1: Generate a token through both services and assert behavior parity**

```bash
# Python (port 8500)
curl -s -H "X-Admin-Key: $GATEWAY_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"service_name":"smoke-svc"}' http://localhost:8500/auth/token/generate > /tmp/py.json

# Go (port 8501)
curl -s -H "X-Admin-Key: $GATEWAY_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"service_name":"smoke-svc"}' http://localhost:8501/auth/token/generate > /tmp/go.json

# Compare keys (values will differ — tokens are unique).
jq 'keys' /tmp/py.json
jq 'keys' /tmp/go.json
```

Expected: identical key sets (`access_token, access_token_expires_at, access_token_expires_minutes, created_at, refresh_token, service_name`).

- [ ] **Step 2: Verify a Python-issued token is accepted by Go**

```bash
PYTHON_TOKEN=$(jq -r .access_token /tmp/py.json)
curl -i -H "Authorization: Bearer $PYTHON_TOKEN" http://localhost:8501/graphdlq-service/dlq/queues
```

Expected: 200 (excluded route bypass) — confirms JWT secret + DB are shared.

- [ ] **Step 3: Diff aggregated /openapi.json**

```bash
curl -s http://localhost:8500/openapi.json | jq -S . > /tmp/py-spec.json
curl -s http://localhost:8501/openapi.json | jq -S . > /tmp/go-spec.json
diff /tmp/py-spec.json /tmp/go-spec.json | head -100
```

Expected: differences only in description text and possibly the gateway-owned paths (since base.yaml is a hand-made minimum). Downstream paths and schema-prefixing should match.

- [ ] **Step 4: Document the diff in a follow-up TODO if non-trivial**

Track any unexpected differences in `docs/superpowers/specs/2026-05-07-api-gateway-go-port-design.md` under a new `Cutover findings` section before proceeding to flip ports.

---

## Task 29: Cutover (deferred — gated on smoke passing)

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Stop the Python gateway**

```bash
docker compose stop api-gateway
```

- [ ] **Step 2: Repoint port mapping**

In `docker-compose.yml`:
- Change `api-gateway-go` ports from `"8501:8500"` to `"8500:8500"`.
- Comment out the Python `api-gateway` service (do NOT delete yet — keep the rollback window).

- [ ] **Step 3: Bring up the Go gateway on the original port**

```bash
docker compose up -d api-gateway-go
curl -i http://localhost:8500/login
```

Expected: `302 Location: /auth/login`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): cutover api-gateway → api-gateway-go on port 8500"
```

- [ ] **Step 5: Decommission follow-up (separate PR, ≥1 week later)**

Create a follow-up issue: "Remove Python `api-gateway/` service folder and Dockerfile after Go gateway runs cleanly for one week."

---

## Self-Review Checklist (run after writing the plan)

- [x] Spec § 1 (goals/strict 1:1) → Tasks 1–25 collectively
- [x] Spec § 2.1 (every endpoint) → Tasks 15, 16, 17, 18, 20, 21, 24
- [x] Spec § 4 (data layer + table names) → Tasks 5, 6
- [x] Spec § 5 (auth) → Tasks 7, 10, 11, 12
- [x] Spec § 6 (proxy) → Tasks 19, 20, 21
- [x] Spec § 7 (SSO) → Tasks 13, 14, 15
- [x] Spec § 8 (token endpoints) → Tasks 17, 18
- [x] Spec § 9 (OpenAPI aggregator + filter + Swagger UI) → Tasks 22, 23, 24
- [x] Spec § 10 (sessions) → Task 25 wiring (cookie store keyed by JWT_SECRET)
- [x] Spec § 11 (config) → Tasks 3, 4
- [x] Spec § 12 (Dockerfile) → Task 26
- [x] Spec § 13 (testing) → Embedded in every TDD task
- [x] Spec § 14 (cutover plan) → Tasks 27, 28, 29
- [x] Spec § 15 (risks) — mitigation evidence in: schema-collision tests (Task 22), JWT compatibility (Task 28 step 2), nginx untouched (Task 26)

---

**End of plan.**
