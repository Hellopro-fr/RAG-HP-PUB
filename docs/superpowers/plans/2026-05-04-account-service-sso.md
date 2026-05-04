# Account Service SSO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `account-service-backend` (Go 1.24 + GORM + MySQL) and `account-service-frontend` (Vue 3 + TailAdmin) — a centralized SSO server with OAuth 2.1 + PKCE, skip-consent, back-channel logout, and an admin UI to register downstream client services.

**Architecture:** Backend lifts `apps-microservices/mcp-gateway-service/internal/authserver/` as the OAuth2 base, removes the consent step, adds claim mapping, branding, allowed-roles gating, configurable token TTL, and a HMAC-signed logout webhook broadcaster. Frontend is cloned from `public/admin-dashboad/` (TailAdmin Pro 2.0) and adapted with Pinia store, dual-mode login (admin UI vs OAuth2 SSO), and admin views for OAuth2 client + user management.

**Tech Stack:**
- Backend: Go 1.24, `net/http`, GORM v1.25, MySQL, JWT HS256 (`golang-jwt/jwt/v5`), AES-256-GCM, `prometheus/client_golang`, `log/slog`.
- Frontend: Vue 3.5, TypeScript 5.7, Vite 6, Pinia, Tailwind 4 (TailAdmin Pro), nginx 1.27-alpine.
- CI/CD: GitHub Actions, testcontainers MySQL for integration tests, Vitest, Trivy.

**Spec:** `docs/superpowers/specs/2026-05-04-account-service-sso-design.md`

**Reference services (read for patterns, do not modify):**
- `apps-microservices/mcp-gateway-service/` — backend pattern source.
- `apps-microservices/mcp-gateway-frontend/` — Pinia + auth store + router guard pattern.
- `public/admin-dashboad/` — TailAdmin Pro template to clone.

**Conventions enforced:**
- TDD: write failing test → implement → green → commit per task.
- One responsibility per file (mirrors mcp-gateway layout).
- All env vars via Pydantic-equivalent loader (Go `Configuration` struct).
- No hardcoded URLs or secrets. Bilingual EN+FR commit messages (Conventional Commits) per `.claude/rules/commit-messages.md`.

**Plan scope note:** This single plan covers both services because they ship together for the SSO feature. Backend is fully testable on its own (curl + integration tests); frontend depends on backend running. Plan is split into 12 phases, ~110 tasks. If you want to ship in waves, Phase 1–7 produce a working backend; Phases 8–11 add the frontend; Phase 12 is deployment glue.

---

## File Structure

### `apps-microservices/account-service-backend/`

| Path | Responsibility |
|---|---|
| `cmd/server/main.go` | Entry point, wire repos → handlers → mux → http.Server, graceful shutdown |
| `internal/config/config.go` | Env-var loader |
| `internal/db/models.go` | GORM models (6 tables) |
| `internal/db/mysql.go` | DB connection, pool, AutoMigrate |
| `internal/crypto/encrypt.go` | AES-256-GCM encrypt/decrypt for client secrets |
| `internal/auth/jwt.go` | SignJWT, ValidateJWT (HS256) |
| `internal/auth/session.go` | Session cookie set/get/clear |
| `internal/auth/hellopro.go` | AuthenticateHellopro proxy |
| `internal/auth/handlers.go` | POST /api/v1/login, POST /api/v1/logout |
| `internal/auth/middleware.go` | RequireAuth, RequireAdmin |
| `internal/repository/user_repo.go` | User CRUD + UpsertOnLogin + admin bootstrap |
| `internal/repository/oauth2_client_repo.go` | OAuth2 client CRUD |
| `internal/repository/authcode_repo.go` | Auth code CRUD + PurgeExpired |
| `internal/repository/refresh_repo.go` | Refresh token CRUD + Rotate + RevokeBySID + ReuseDetection |
| `internal/repository/audit_repo.go` | Audit log insert + paginated list |
| `internal/repository/logout_event_repo.go` | Logout event CRUD |
| `internal/authserver/handler.go` | AuthServer struct + route registration |
| `internal/authserver/metadata.go` | GET /.well-known/oauth-authorization-server |
| `internal/authserver/authorize.go` | GET/POST /authorize (skip consent) |
| `internal/authserver/token_endpoint.go` | POST /token (auth_code + refresh_token) |
| `internal/authserver/register.go` | POST /register (RFC 7591) |
| `internal/authserver/introspect.go` | POST /introspect (RFC 7662) |
| `internal/authserver/pkce.go` | S256 verify |
| `internal/authserver/codes.go` | Auth code gen + SHA-256 hash |
| `internal/authserver/claim_mapper.go` | Apply client.claim_mappings to JWT |
| `internal/authserver/branding.go` | GET /authorize/branding/{client_id}.json |
| `internal/logout/broadcaster.go` | HMAC-signed webhook delivery + retries |
| `internal/logout/queue.go` | Buffered channel + worker pool |
| `internal/api/handler.go` | Top-level mux + middleware chain |
| `internal/api/admin_service_handlers.go` | /admin/services CRUD |
| `internal/api/admin_user_handlers.go` | /admin/users + sessions |
| `internal/api/me_handlers.go` | /me + /me/sessions |
| `internal/api/audit_handlers.go` | /admin/audit |
| `internal/api/middleware.go` | Logging, recovery, JSON content-type |
| `internal/health/health.go` | /health handler |
| `internal/metrics/metrics.go` | Prometheus collectors |
| `init-db/init-account-db.sql` | CREATE DATABASE only |
| `Dockerfile` | Multi-stage build |
| `go.mod`, `go.sum` | |
| `CLAUDE.md` | Service documentation |

### `apps-microservices/account-service-frontend/`

| Path | Responsibility |
|---|---|
| `src/api/client.ts` | Typed fetch wrapper, Bearer header, /api prefix |
| `src/api/services.ts` | OAuth2 client CRUD calls |
| `src/api/users.ts` | User CRUD calls |
| `src/api/audit.ts` | Audit log fetch |
| `src/stores/auth.ts` | Pinia: token, user, isAdmin, login, logout, checkSession |
| `src/router/index.ts` | Routes + guards |
| `src/views/LoginView.vue` | Dual-mode login (admin UI vs OAuth2 SSO) |
| `src/views/AdminServicesView.vue` | List OAuth2 clients |
| `src/views/ServiceFormView.vue` | Create/edit OAuth2 client |
| `src/views/AdminUsersView.vue` | List + manage users |
| `src/views/UserSessionsView.vue` | Active sessions per user |
| `src/views/AuditLogView.vue` | Paginated audit |
| `src/views/MeView.vue` | Profile + own sessions |
| `src/components/services/RedirectUriList.vue` | Add/remove redirect URI rows |
| `src/components/services/ClaimMapperEditor.vue` | Key-value editor for claim mappings |
| `src/components/services/BrandingPreview.vue` | Logo + color picker |
| `nginx.conf` | SPA serving + reverse proxy |
| `Dockerfile` | node:22-alpine build → nginx:1.27-alpine |
| `vite.config.ts` | Dev proxy /api → :8600 |
| `package.json` | (cloned, renamed, Pinia added) |
| `CLAUDE.md` | Service documentation |

---

## Phase 0 — Branch + Skeleton Bootstrap

### Task 1: Create the working branches

**Files:**
- N/A (git operations only)

- [ ] **Step 1: Verify clean working tree**

```bash
git status
```
Expected: clean (or only the spec doc on `account-service` branch).

- [ ] **Step 2: Push current branch**

```bash
git push -u origin account-service
```
Expected: branch tracked.

- [ ] **Step 3: Create the two feature branches off `account-service`**

```bash
git checkout -b feature/account-service-backend
git push -u origin feature/account-service-backend
git checkout account-service
git checkout -b feature/account-service-frontend
git push -u origin feature/account-service-frontend
git checkout feature/account-service-backend
```
Expected: both branches exist on origin.

- [ ] **Step 4: Commit empty marker file to verify branch wiring**

This is optional. Skip if you prefer to start with real code.

---

### Task 2: Scaffold backend directory tree

**Files:**
- Create: `apps-microservices/account-service-backend/.gitkeep`
- Create: `apps-microservices/account-service-backend/CLAUDE.md`

- [ ] **Step 1: Create directory skeleton**

```bash
cd apps-microservices/account-service-backend
mkdir -p cmd/server
mkdir -p internal/{api,auth,authserver,authserver/templates,config,crypto,db,health,logout,metrics,repository}
mkdir -p init-db
touch .gitkeep
```

- [ ] **Step 2: Write the placeholder CLAUDE.md**

```markdown
# account-service-backend

Centralized SSO and OAuth2 Authorization Server for the Hellopro platform.

## Tech Stack

- Go 1.24
- net/http (standard library)
- GORM v1.25 (MySQL via go-sql-driver/mysql)
- JWT HS256 (golang-jwt/jwt/v5)
- AES-256-GCM (crypto/aes)
- Docker (multi-stage golang:1.24-alpine → alpine:3.20), exposed port **8600**

## Run

```bash
cd apps-microservices/account-service-backend
go run ./cmd/server/
```

## Spec

See `docs/superpowers/specs/2026-05-04-account-service-sso-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/account-service-backend
git commit -m "$(cat <<'EOF'
chore(account-service-backend): scaffold directory skeleton

- Bootstrap empty internal/* layout matching the design spec.
- CLAUDE.md placeholder pointing at the spec.

chore(account-service-backend) : squelette des répertoires
- Mise en place de l'arborescence internal/* vide selon la spec.
EOF
)"
```

---

### Task 3: Initialize Go module and pin dependencies

**Files:**
- Create: `apps-microservices/account-service-backend/go.mod`

- [ ] **Step 1: Create the module**

```bash
cd apps-microservices/account-service-backend
go mod init github.com/hellopro/account-service
```

- [ ] **Step 2: Add the runtime dependencies**

```bash
go get github.com/golang-jwt/jwt/v5@v5.2.1
go get gorm.io/gorm@v1.25.12
go get gorm.io/driver/mysql@v1.5.7
go get github.com/google/uuid@v1.6.0
go get github.com/prometheus/client_golang@v1.20.5
```

- [ ] **Step 3: Add the test dependencies**

```bash
go get github.com/testcontainers/testcontainers-go@v0.34.0
go get github.com/testcontainers/testcontainers-go/modules/mysql@v0.34.0
go get github.com/stretchr/testify@v1.10.0
```

- [ ] **Step 4: Tidy and verify**

```bash
go mod tidy
go vet ./...
```
Expected: no error (module empty so vet is a no-op).

- [ ] **Step 5: Commit**

```bash
git add go.mod go.sum
git commit -m "chore(account-service-backend): init Go module / Initialise le module Go"
```

---

## Phase 1 — Configuration, Crypto, JWT, Session

### Task 4: Configuration loader (env-var)

**Files:**
- Create: `internal/config/config.go`
- Test: `internal/config/config_test.go`

- [ ] **Step 1: Write the failing test**

```go
package config

import (
	"os"
	"testing"
)

func TestLoad_RequiresMandatoryVars(t *testing.T) {
	os.Clearenv()
	if _, err := Load(); err == nil {
		t.Fatal("expected error when MYSQL_DSN is missing")
	}
}

func TestLoad_AppliesDefaults(t *testing.T) {
	os.Clearenv()
	t.Setenv("MYSQL_DSN", "u:p@tcp(localhost:3306)/account_db")
	t.Setenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	t.Setenv("JWT_SECRET", "x")
	t.Setenv("AUTH_URL", "https://www.hellopro.fr/login")
	t.Setenv("ACCOUNT_PUBLIC_URL", "https://account.hellopro.fr")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Port != 8600 {
		t.Errorf("Port=%d, want 8600", cfg.Port)
	}
	if cfg.DefaultTokenTTL != 60 {
		t.Errorf("DefaultTokenTTL=%d, want 60", cfg.DefaultTokenTTL)
	}
	if cfg.DefaultRefreshTTL != 2592000 {
		t.Errorf("DefaultRefreshTTL=%d, want 2592000", cfg.DefaultRefreshTTL)
	}
	if cfg.AuthCodeTTL != 600 {
		t.Errorf("AuthCodeTTL=%d, want 600", cfg.AuthCodeTTL)
	}
	if !cfg.SecureCookie {
		t.Error("SecureCookie default should be true")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
go test ./internal/config/...
```
Expected: FAIL — package doesn't compile (no `Load`).

- [ ] **Step 3: Implement the config loader**

```go
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Configuration struct {
	Port              int
	PublicURL         string
	MySQLDSN          string
	EncryptionKey     string
	JWTSecret         string
	JWTAudience       string
	AuthURL           string
	FallbackUser      string
	FallbackPass      string
	FallbackEmail     string
	AdminEmails       []string
	DefaultTokenTTL   int
	DefaultRefreshTTL int
	AuthCodeTTL       int
	WebhookTimeoutS   int
	WebhookRetries    int
	LogoutWorkers     int
	SecureCookie      bool
	SlackWebhookURL   string
	SlackCooldownS   int
}

func Load() (*Configuration, error) {
	cfg := &Configuration{
		Port:              envInt("ACCOUNT_PORT", 8600),
		PublicURL:         strings.TrimRight(os.Getenv("ACCOUNT_PUBLIC_URL"), "/"),
		MySQLDSN:          os.Getenv("MYSQL_DSN"),
		EncryptionKey:     os.Getenv("ENCRYPTION_KEY"),
		JWTSecret:         os.Getenv("JWT_SECRET"),
		JWTAudience:       envStr("JWT_AUDIENCE", "https://www.hellopro.fr"),
		AuthURL:           os.Getenv("AUTH_URL"),
		FallbackUser:      os.Getenv("FALLBACK_USER"),
		FallbackPass:      os.Getenv("FALLBACK_PASS"),
		FallbackEmail:     os.Getenv("FALLBACK_EMAIL"),
		AdminEmails:       splitCSV(os.Getenv("ADMIN_EMAILS")),
		DefaultTokenTTL:   envInt("OAUTH2_DEFAULT_TOKEN_TTL", 60),
		DefaultRefreshTTL: envInt("OAUTH2_DEFAULT_REFRESH_TTL", 2592000),
		AuthCodeTTL:       envInt("OAUTH2_AUTH_CODE_TTL", 600),
		WebhookTimeoutS:   envInt("LOGOUT_WEBHOOK_TIMEOUT", 5),
		WebhookRetries:    envInt("LOGOUT_WEBHOOK_RETRIES", 3),
		LogoutWorkers:     envInt("LOGOUT_WORKERS", 4),
		SecureCookie:      envBool("SECURE_COOKIE", true),
		SlackWebhookURL:   os.Getenv("SLACK_WEBHOOK_URL"),
		SlackCooldownS:    envInt("SLACK_AUTH_ALERT_COOLDOWN", 600),
	}
	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

func (c *Configuration) validate() error {
	if c.MySQLDSN == "" {
		return fmt.Errorf("MYSQL_DSN is required")
	}
	if c.EncryptionKey == "" || len(c.EncryptionKey) != 64 {
		return fmt.Errorf("ENCRYPTION_KEY must be 32 bytes hex (64 chars)")
	}
	if c.JWTSecret == "" {
		return fmt.Errorf("JWT_SECRET is required")
	}
	if c.AuthURL == "" {
		return fmt.Errorf("AUTH_URL is required")
	}
	if c.PublicURL == "" {
		return fmt.Errorf("ACCOUNT_PUBLIC_URL is required")
	}
	return nil
}

func envStr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func envInt(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envBool(k string, def bool) bool {
	if v := os.Getenv(k); v != "" {
		return v == "1" || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}
	return def
}

func splitCSV(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
go test ./internal/config/...
```
Expected: PASS, both tests.

- [ ] **Step 5: Commit**

```bash
git add internal/config/
git commit -m "feat(account-service-backend): add env-var config loader / Ajout du chargeur de configuration"
```

---

### Task 5: AES-256-GCM crypto module

**Files:**
- Create: `internal/crypto/encrypt.go`
- Test: `internal/crypto/encrypt_test.go`

- [ ] **Step 1: Write the failing test**

```go
package crypto

import (
	"strings"
	"testing"
)

const testKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

func TestRoundTrip(t *testing.T) {
	c, err := New(testKey)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	plain := "super-secret-client-secret"
	cipher, err := c.Encrypt([]byte(plain))
	if err != nil {
		t.Fatalf("Encrypt: %v", err)
	}
	if strings.Contains(string(cipher), plain) {
		t.Fatal("ciphertext should not contain plaintext")
	}
	got, err := c.Decrypt(cipher)
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if string(got) != plain {
		t.Fatalf("Decrypt got=%q want=%q", string(got), plain)
	}
}

func TestDecryptRejectsTampered(t *testing.T) {
	c, err := New(testKey)
	if err != nil {
		t.Fatal(err)
	}
	cipher, _ := c.Encrypt([]byte("hello"))
	cipher[len(cipher)-1] ^= 0x01
	if _, err := c.Decrypt(cipher); err == nil {
		t.Fatal("expected auth error for tampered ciphertext")
	}
}

func TestNewRejectsBadKeyLen(t *testing.T) {
	if _, err := New("deadbeef"); err == nil {
		t.Fatal("expected error for short key")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
go test ./internal/crypto/...
```
Expected: FAIL — package doesn't exist.

- [ ] **Step 3: Implement**

```go
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
)

type Cipher struct {
	gcm cipher.AEAD
}

func New(hexKey string) (*Cipher, error) {
	if len(hexKey) != 64 {
		return nil, fmt.Errorf("key must be 32 bytes hex (got %d chars)", len(hexKey))
	}
	key, err := hex.DecodeString(hexKey)
	if err != nil {
		return nil, fmt.Errorf("decode key: %w", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return &Cipher{gcm: gcm}, nil
}

func (c *Cipher) Encrypt(plain []byte) ([]byte, error) {
	nonce := make([]byte, c.gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}
	out := c.gcm.Seal(nonce, nonce, plain, nil)
	return out, nil
}

func (c *Cipher) Decrypt(cipherBytes []byte) ([]byte, error) {
	ns := c.gcm.NonceSize()
	if len(cipherBytes) < ns {
		return nil, fmt.Errorf("ciphertext too short")
	}
	nonce, ct := cipherBytes[:ns], cipherBytes[ns:]
	return c.gcm.Open(nil, nonce, ct, nil)
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
go test ./internal/crypto/...
```
Expected: PASS, all three.

- [ ] **Step 5: Commit**

```bash
git add internal/crypto/
git commit -m "feat(account-service-backend): add AES-256-GCM cipher / Ajout du chiffrement AES-256-GCM"
```

---

### Task 6: JWT sign + validate (HS256)

**Files:**
- Create: `internal/auth/jwt.go`
- Test: `internal/auth/jwt_test.go`

- [ ] **Step 1: Write the failing test**

```go
package auth

import (
	"testing"
	"time"
)

func TestSignValidateRoundTrip(t *testing.T) {
	claims := Claims{
		Sub:   "alice@example.com",
		Email: "alice@example.com",
		Name:  "Alice",
		Aud:   "test-aud",
		Iss:   "https://account.test",
		Sid:   "sid-1",
		Iat:   time.Now().Unix(),
		Exp:   time.Now().Add(1 * time.Minute).Unix(),
	}
	tok, err := SignJWT("secret", claims)
	if err != nil {
		t.Fatalf("SignJWT: %v", err)
	}
	got, err := ValidateJWT(tok, "secret", "test-aud")
	if err != nil {
		t.Fatalf("ValidateJWT: %v", err)
	}
	if got.Sub != "alice@example.com" {
		t.Errorf("Sub=%q want alice@example.com", got.Sub)
	}
}

func TestValidateRejectsExpired(t *testing.T) {
	claims := Claims{
		Aud: "x",
		Iat: time.Now().Add(-2 * time.Hour).Unix(),
		Exp: time.Now().Add(-1 * time.Hour).Unix(),
	}
	tok, _ := SignJWT("secret", claims)
	if _, err := ValidateJWT(tok, "secret", "x"); err == nil {
		t.Fatal("expected expired error")
	}
}

func TestValidateRejectsBadSignature(t *testing.T) {
	tok, _ := SignJWT("secret", Claims{Aud: "x", Exp: time.Now().Add(time.Minute).Unix()})
	if _, err := ValidateJWT(tok, "other-secret", "x"); err == nil {
		t.Fatal("expected signature error")
	}
}

func TestValidateRejectsAudienceMismatch(t *testing.T) {
	tok, _ := SignJWT("secret", Claims{Aud: "x", Exp: time.Now().Add(time.Minute).Unix()})
	if _, err := ValidateJWT(tok, "secret", "y"); err == nil {
		t.Fatal("expected audience error")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
go test ./internal/auth/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package auth

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
)

type Claims struct {
	Sub    string                 `json:"sub,omitempty"`
	Email  string                 `json:"email,omitempty"`
	Name   string                 `json:"name,omitempty"`
	Aud    string                 `json:"aud"`
	Iss    string                 `json:"iss,omitempty"`
	Sid    string                 `json:"sid,omitempty"`
	Iat    int64                  `json:"iat"`
	Exp    int64                  `json:"exp"`
	IsAdmin bool                  `json:"is_admin,omitempty"`
	Custom map[string]interface{} `json:"-"`
}

func (c Claims) toMap() jwt.MapClaims {
	m := jwt.MapClaims{
		"aud": c.Aud,
		"exp": c.Exp,
		"iat": c.Iat,
	}
	if c.Sub != "" {
		m["sub"] = c.Sub
	}
	if c.Email != "" {
		m["email"] = c.Email
	}
	if c.Name != "" {
		m["name"] = c.Name
	}
	if c.Iss != "" {
		m["iss"] = c.Iss
	}
	if c.Sid != "" {
		m["sid"] = c.Sid
	}
	if c.IsAdmin {
		m["is_admin"] = true
	}
	for k, v := range c.Custom {
		m[k] = v
	}
	return m
}

func SignJWT(secret string, c Claims) (string, error) {
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, c.toMap())
	return tok.SignedString([]byte(secret))
}

func ValidateJWT(token, secret, expectedAud string) (*Claims, error) {
	parsed, err := jwt.Parse(token, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return []byte(secret), nil
	})
	if err != nil || !parsed.Valid {
		return nil, fmt.Errorf("invalid token: %w", err)
	}
	mc, ok := parsed.Claims.(jwt.MapClaims)
	if !ok {
		return nil, errors.New("unexpected claims type")
	}
	if expectedAud != "" {
		if aud, _ := mc["aud"].(string); aud != expectedAud {
			return nil, fmt.Errorf("audience mismatch: %q != %q", aud, expectedAud)
		}
	}
	out := &Claims{Custom: map[string]interface{}{}}
	for k, v := range mc {
		switch k {
		case "sub":
			out.Sub, _ = v.(string)
		case "email":
			out.Email, _ = v.(string)
		case "name":
			out.Name, _ = v.(string)
		case "aud":
			out.Aud, _ = v.(string)
		case "iss":
			out.Iss, _ = v.(string)
		case "sid":
			out.Sid, _ = v.(string)
		case "iat":
			if f, ok := v.(float64); ok {
				out.Iat = int64(f)
			}
		case "exp":
			if f, ok := v.(float64); ok {
				out.Exp = int64(f)
			}
		case "is_admin":
			out.IsAdmin, _ = v.(bool)
		default:
			out.Custom[k] = v
		}
	}
	return out, nil
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
go test ./internal/auth/...
```
Expected: PASS, all four cases.

- [ ] **Step 5: Commit**

```bash
git add internal/auth/jwt.go internal/auth/jwt_test.go
git commit -m "feat(account-service-backend): add HS256 JWT helpers / Ajout des aides JWT HS256"
```

---

### Task 7: Session cookie helpers

**Files:**
- Create: `internal/auth/session.go`
- Test: `internal/auth/session_test.go`

- [ ] **Step 1: Write the failing test**

```go
package auth

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSetGetSessionRoundTrip(t *testing.T) {
	w := httptest.NewRecorder()
	data := SessionData{Email: "alice@example.com", DisplayName: "Alice", Token: "tok"}
	if err := SetSession(w, "secret", data, false); err != nil {
		t.Fatalf("SetSession: %v", err)
	}

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	for _, c := range w.Result().Cookies() {
		r.AddCookie(c)
	}
	got, err := GetSession(r, "secret")
	if err != nil {
		t.Fatalf("GetSession: %v", err)
	}
	if got.Email != "alice@example.com" {
		t.Errorf("Email=%q", got.Email)
	}
}

func TestClearSessionExpires(t *testing.T) {
	w := httptest.NewRecorder()
	ClearSession(w)
	cookies := w.Result().Cookies()
	if len(cookies) == 0 {
		t.Fatal("no cookie set")
	}
	if cookies[0].MaxAge >= 0 {
		t.Fatalf("MaxAge=%d, want <0", cookies[0].MaxAge)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
go test ./internal/auth/...
```
Expected: FAIL — `SessionData`/`SetSession`/`GetSession`/`ClearSession` undefined.

- [ ] **Step 3: Implement**

```go
package auth

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"
)

const sessionCookieName = "account_session"

type SessionData struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
	Token       string `json:"token"`
}

func SetSession(w http.ResponseWriter, secret string, data SessionData, secure bool) error {
	body, err := json.Marshal(data)
	if err != nil {
		return err
	}
	claims := Claims{
		Sub:   data.Email,
		Email: data.Email,
		Name:  data.DisplayName,
		Aud:   "session",
		Iat:   time.Now().Unix(),
		Exp:   time.Now().Add(24 * time.Hour).Unix(),
	}
	tok, err := SignJWT(secret, claims)
	if err != nil {
		return err
	}
	enc := base64.RawURLEncoding.EncodeToString(body)
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    fmt.Sprintf("%s.%s", tok, enc),
		Path:     "/",
		MaxAge:   24 * 60 * 60,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   secure,
	})
	return nil
}

func GetSession(r *http.Request, secret string) (*SessionData, error) {
	c, err := r.Cookie(sessionCookieName)
	if err != nil {
		return nil, err
	}
	parts := []string{}
	for _, p := range splitDot(c.Value) {
		parts = append(parts, p)
	}
	if len(parts) != 2 {
		return nil, errors.New("malformed session cookie")
	}
	if _, err := ValidateJWT(parts[0], secret, "session"); err != nil {
		return nil, err
	}
	body, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, err
	}
	var d SessionData
	if err := json.Unmarshal(body, &d); err != nil {
		return nil, err
	}
	return &d, nil
}

func ClearSession(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		HttpOnly: true,
	})
}

func splitDot(s string) []string {
	var out []string
	cur := ""
	for _, r := range s {
		if r == '.' {
			out = append(out, cur)
			cur = ""
			continue
		}
		cur += string(r)
	}
	out = append(out, cur)
	return out
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
go test ./internal/auth/...
```
Expected: PASS — all jwt + session tests.

- [ ] **Step 5: Commit**

```bash
git add internal/auth/session.go internal/auth/session_test.go
git commit -m "feat(account-service-backend): add session cookie helpers / Ajout des cookies de session"
```

---

### Task 8: Hellopro authentication proxy

**Files:**
- Create: `internal/auth/hellopro.go`
- Test: `internal/auth/hellopro_test.go`

- [ ] **Step 1: Write the failing test**

```go
package auth

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAuthenticateHellopro_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		if r.FormValue("login") != "alice" || r.FormValue("password") != "p" {
			http.Error(w, "bad", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
	defer srv.Close()

	resp, err := AuthenticateHellopro(srv.URL, "alice", "p")
	if err != nil {
		t.Fatalf("AuthenticateHellopro: %v", err)
	}
	if !resp.Success {
		t.Fatal("Success=false")
	}
	if resp.Email != "alice@example.com" {
		t.Errorf("Email=%q", resp.Email)
	}
}

func TestAuthenticateHellopro_RejectsHTTPRemote(t *testing.T) {
	if _, err := AuthenticateHellopro("http://attacker.example/login", "x", "y"); err == nil {
		t.Fatal("expected scheme error")
	}
}

func TestAuthenticateHellopro_AllowsLocalhostHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":false}`))
	}))
	defer srv.Close()
	if !strings.HasPrefix(srv.URL, "http://127.0.0.1") {
		t.Skipf("test server URL %q not localhost", srv.URL)
	}
	resp, err := AuthenticateHellopro(srv.URL, "x", "y")
	if err != nil {
		t.Fatalf("expected no error for localhost, got %v", err)
	}
	if resp.Success {
		t.Fatal("Success=true")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
go test ./internal/auth/...
```
Expected: FAIL — undefined symbol.

- [ ] **Step 3: Implement**

```go
package auth

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

type HelloProAuthResponse struct {
	Success     bool   `json:"success"`
	Token       string `json:"token,omitempty"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

func AuthenticateHellopro(authURL, username, password string) (*HelloProAuthResponse, error) {
	parsed, err := url.Parse(authURL)
	if err != nil {
		return nil, fmt.Errorf("invalid auth URL: %w", err)
	}
	host := parsed.Hostname()
	if parsed.Scheme != "https" && host != "localhost" && host != "127.0.0.1" {
		return nil, fmt.Errorf("auth URL must use HTTPS (got %s)", parsed.Scheme)
	}

	form := url.Values{
		"login":    {username},
		"password": {password},
	}

	client := &http.Client{
		Timeout: 10 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	resp, err := client.PostForm(authURL, form)
	if err != nil {
		return nil, fmt.Errorf("auth request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("auth returned status %d (body %d bytes)", resp.StatusCode, len(body))
	}
	var out HelloProAuthResponse
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}
	return &out, nil
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
go test ./internal/auth/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/auth/hellopro.go internal/auth/hellopro_test.go
git commit -m "feat(account-service-backend): add hellopro auth proxy / Ajout du proxy d'authentification hellopro"
```

---

## Phase 2 — DB Models, Connection, Repositories

### Task 9: GORM models for the 6 tables

**Files:**
- Create: `internal/db/models.go`

This task is a pure declaration; no test in isolation. The first repository test (Task 11) will exercise the schema end-to-end via testcontainers.

- [ ] **Step 1: Write the models**

```go
package db

import "time"

type User struct {
	ID          string    `gorm:"type:char(36);primaryKey"`
	Email       string    `gorm:"size:255;uniqueIndex;not null"`
	DisplayName string    `gorm:"size:255"`
	IsAdmin     bool      `gorm:"not null;default:false"`
	IsAllowed   bool      `gorm:"not null;default:true"`
	LastLoginAt *time.Time
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

type OAuth2Client struct {
	ID                 string    `gorm:"type:char(36);primaryKey"`
	ClientID           string    `gorm:"size:64;uniqueIndex;not null"`
	ClientSecretEnc    []byte    `gorm:"type:blob;not null"`
	Name               string    `gorm:"size:255;not null"`
	Description        string    `gorm:"type:text"`
	LogoURL            string    `gorm:"size:512"`
	BrandColor         string    `gorm:"size:16"`
	RedirectURIs       *string   `gorm:"type:json"`
	AllowedRoles       *string   `gorm:"type:json"`
	LogoutWebhookURL   string    `gorm:"size:512"`
	TokenTTLSeconds    int       `gorm:"not null;default:60"`
	RefreshTTLSeconds  int       `gorm:"not null;default:2592000"`
	ClaimMappings      *string   `gorm:"type:json"`
	Scope              string    `gorm:"size:512"`
	IsActive           bool      `gorm:"not null;default:true"`
	CreatedBy          string    `gorm:"size:255"`
	CreatedAt          time.Time
	UpdatedAt          time.Time
}

type OAuth2AuthorizationCode struct {
	CodeHash      string    `gorm:"type:char(64);primaryKey"`
	ClientID      string    `gorm:"size:64;not null;index:idx_authcode_purge,priority:1"`
	UserEmail     string    `gorm:"size:255;not null"`
	RedirectURI   string    `gorm:"size:512;not null"`
	CodeChallenge string    `gorm:"size:128;not null"`
	Scope         string    `gorm:"size:512"`
	Used          bool      `gorm:"not null;default:false"`
	ExpiresAt     time.Time `gorm:"not null;index:idx_authcode_purge,priority:2"`
	CreatedAt     time.Time
}

type OAuth2RefreshToken struct {
	ID            string    `gorm:"type:char(36);primaryKey"`
	TokenHash     string    `gorm:"type:char(64);uniqueIndex;not null"`
	SID           string    `gorm:"type:char(36);not null;index"`
	ClientID      string    `gorm:"size:64;not null"`
	UserEmail     string    `gorm:"size:255;not null;index:idx_refresh_user,priority:1"`
	ExpiresAt     time.Time `gorm:"not null"`
	Revoked       bool      `gorm:"not null;default:false;index:idx_refresh_user,priority:2"`
	RevokedAt     *time.Time
	RevokedReason string    `gorm:"size:64"`
	RotatedFrom   string    `gorm:"type:char(36);index"`
	CreatedAt     time.Time
	LastUsedAt    *time.Time
}

type LogoutEvent struct {
	ID             string    `gorm:"type:char(36);primaryKey"`
	ClientID       string    `gorm:"size:64;not null"`
	UserEmail      string    `gorm:"size:255;not null"`
	SID            string    `gorm:"type:char(36);not null"`
	WebhookURL     string    `gorm:"size:512;not null"`
	Status         string    `gorm:"size:16;not null;default:'pending';index:idx_logout_pickup,priority:1"`
	Attempts       int       `gorm:"not null;default:0"`
	LastError      string    `gorm:"type:text"`
	NextAttemptAt  time.Time `gorm:"index:idx_logout_pickup,priority:2"`
	CreatedAt      time.Time
	UpdatedAt      time.Time
}

type AuditLog struct {
	ID          int64     `gorm:"primaryKey;autoIncrement"`
	Event       string    `gorm:"size:32;not null;index:idx_audit_event,priority:1"`
	ActorEmail  string    `gorm:"size:255;index:idx_audit_actor,priority:1"`
	TargetEmail string    `gorm:"size:255"`
	ClientID    string    `gorm:"size:64"`
	IPAddr      string    `gorm:"size:64"`
	UserAgent   string    `gorm:"size:512"`
	Metadata    *string   `gorm:"type:json"`
	CreatedAt   time.Time `gorm:"index:idx_audit_event,priority:2;index:idx_audit_actor,priority:2"`
}
```

- [ ] **Step 2: Compile-check**

```bash
go build ./internal/db/...
```
Expected: success (no `_test.go` yet).

- [ ] **Step 3: Commit**

```bash
git add internal/db/models.go
git commit -m "feat(account-service-backend): add GORM models / Ajout des modèles GORM"
```

---

### Task 10: MySQL connection + AutoMigrate

**Files:**
- Create: `internal/db/mysql.go`
- Test: `internal/db/mysql_test.go`

- [ ] **Step 1: Write the integration test**

```go
//go:build integration

package db

import (
	"context"
	"testing"

	"github.com/testcontainers/testcontainers-go/modules/mysql"
)

func TestConnectAndMigrate(t *testing.T) {
	ctx := context.Background()
	container, err := mysql.Run(ctx,
		"mysql:8.0",
		mysql.WithDatabase("account_db"),
		mysql.WithUsername("acct"),
		mysql.WithPassword("acct"),
	)
	if err != nil {
		t.Fatalf("container: %v", err)
	}
	t.Cleanup(func() { _ = container.Terminate(ctx) })

	dsn, err := container.ConnectionString(ctx, "parseTime=true")
	if err != nil {
		t.Fatalf("dsn: %v", err)
	}
	gormDB, err := Connect(dsn)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if err := AutoMigrate(gormDB); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	for _, name := range []string{"users", "oauth2_clients", "oauth2_authorization_codes", "oauth2_refresh_tokens", "logout_events", "audit_logs"} {
		if !gormDB.Migrator().HasTable(name) {
			t.Errorf("table %s missing after migrate", name)
		}
	}
}
```

- [ ] **Step 2: Run the test (will fail to build)**

```bash
go test -tags=integration ./internal/db/...
```
Expected: FAIL — `Connect` undefined.

- [ ] **Step 3: Implement**

```go
package db

import (
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func Connect(dsn string) (*gorm.DB, error) {
	gormDB, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, err
	}
	sqlDB, err := gormDB.DB()
	if err != nil {
		return nil, err
	}
	sqlDB.SetMaxOpenConns(25)
	sqlDB.SetMaxIdleConns(5)
	sqlDB.SetConnMaxLifetime(time.Hour)
	return gormDB, nil
}

func AutoMigrate(g *gorm.DB) error {
	return g.AutoMigrate(
		&User{},
		&OAuth2Client{},
		&OAuth2AuthorizationCode{},
		&OAuth2RefreshToken{},
		&LogoutEvent{},
		&LogoutEvent{},
		&AuditLog{},
	)
}
```

Wait — `LogoutEvent{}` repeated. Replace the body of `AutoMigrate` with the corrected list:

```go
func AutoMigrate(g *gorm.DB) error {
	return g.AutoMigrate(
		&User{},
		&OAuth2Client{},
		&OAuth2AuthorizationCode{},
		&OAuth2RefreshToken{},
		&LogoutEvent{},
		&AuditLog{},
	)
}
```

- [ ] **Step 4: Run integration test**

```bash
go test -tags=integration ./internal/db/...
```
Expected: PASS (Docker required).

- [ ] **Step 5: Commit**

```bash
git add internal/db/mysql.go internal/db/mysql_test.go
git commit -m "feat(account-service-backend): connect MySQL + AutoMigrate / Connexion MySQL et auto-migration"
```

---

### Task 11: User repository (UpsertOnLogin + admin bootstrap)

**Files:**
- Create: `internal/repository/user_repo.go`
- Test: `internal/repository/user_repo_test.go`
- Create: `internal/repository/testhelp_test.go` (shared `setupTestDB`)

- [ ] **Step 1: Write the shared test helper**

```go
//go:build integration

package repository

import (
	"context"
	"testing"

	"github.com/hellopro/account-service/internal/db"
	"github.com/testcontainers/testcontainers-go/modules/mysql"
	"gorm.io/gorm"
)

func setupTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	ctx := context.Background()
	container, err := mysql.Run(ctx,
		"mysql:8.0",
		mysql.WithDatabase("account_db"),
		mysql.WithUsername("acct"),
		mysql.WithPassword("acct"),
	)
	if err != nil {
		t.Fatalf("container: %v", err)
	}
	t.Cleanup(func() { _ = container.Terminate(ctx) })
	dsn, err := container.ConnectionString(ctx, "parseTime=true")
	if err != nil {
		t.Fatalf("dsn: %v", err)
	}
	gormDB, err := db.Connect(dsn)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if err := db.AutoMigrate(gormDB); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	return gormDB
}
```

- [ ] **Step 2: Write the failing UserRepo test**

```go
//go:build integration

package repository

import "testing"

func TestUpsertOnLogin_FirstUserBecomesAdmin(t *testing.T) {
	g := setupTestDB(t)
	r := NewUserRepo(g, nil)

	u, err := r.UpsertOnLogin("alice@example.com", "Alice")
	if err != nil {
		t.Fatalf("UpsertOnLogin: %v", err)
	}
	if !u.IsAdmin {
		t.Fatalf("first user should be admin")
	}
}

func TestUpsertOnLogin_HonorsAdminEmailsList(t *testing.T) {
	g := setupTestDB(t)
	// seed an existing user so first-user rule does NOT apply
	_, _ = NewUserRepo(g, nil).UpsertOnLogin("seed@example.com", "Seed")

	r := NewUserRepo(g, []string{"alice@example.com"})
	u, err := r.UpsertOnLogin("alice@example.com", "Alice")
	if err != nil {
		t.Fatalf("UpsertOnLogin: %v", err)
	}
	if !u.IsAdmin {
		t.Fatal("alice should be admin via env list")
	}
	other, _ := r.UpsertOnLogin("bob@example.com", "Bob")
	if other.IsAdmin {
		t.Fatal("bob should not be admin")
	}
}

func TestUpsertOnLogin_UpdatesLastLogin(t *testing.T) {
	g := setupTestDB(t)
	r := NewUserRepo(g, nil)

	u1, _ := r.UpsertOnLogin("alice@example.com", "Alice")
	first := u1.LastLoginAt
	u2, _ := r.UpsertOnLogin("alice@example.com", "Alice Updated")
	if u2.LastLoginAt == nil || (first != nil && !u2.LastLoginAt.After(*first)) {
		t.Fatal("LastLoginAt not bumped")
	}
	if u2.DisplayName != "Alice Updated" {
		t.Fatalf("DisplayName not updated: %q", u2.DisplayName)
	}
}
```

- [ ] **Step 3: Run the failing tests**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: FAIL — `NewUserRepo` undefined.

- [ ] **Step 4: Implement**

```go
package repository

import (
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type UserRepo struct {
	g           *gorm.DB
	adminEmails map[string]struct{}
}

func NewUserRepo(g *gorm.DB, adminEmails []string) *UserRepo {
	set := make(map[string]struct{}, len(adminEmails))
	for _, e := range adminEmails {
		set[e] = struct{}{}
	}
	return &UserRepo{g: g, adminEmails: set}
}

func (r *UserRepo) UpsertOnLogin(email, displayName string) (*db.User, error) {
	now := time.Now()
	var existing db.User
	err := r.g.Where("email = ?", email).First(&existing).Error
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	if errors.Is(err, gorm.ErrRecordNotFound) {
		// First user OR matches admin allowlist → admin
		var count int64
		if err := r.g.Model(&db.User{}).Count(&count).Error; err != nil {
			return nil, err
		}
		_, isAllowed := r.adminEmails[email]
		isAdmin := count == 0 || isAllowed
		u := db.User{
			ID:          uuid.New().String(),
			Email:       email,
			DisplayName: displayName,
			IsAdmin:     isAdmin,
			IsAllowed:   true,
			LastLoginAt: &now,
		}
		if err := r.g.Create(&u).Error; err != nil {
			return nil, err
		}
		return &u, nil
	}
	existing.DisplayName = displayName
	existing.LastLoginAt = &now
	if err := r.g.Save(&existing).Error; err != nil {
		return nil, err
	}
	return &existing, nil
}

func (r *UserRepo) FindByEmail(email string) (*db.User, error) {
	var u db.User
	if err := r.g.Where("email = ?", email).First(&u).Error; err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UserRepo) List(limit, offset int) ([]db.User, int64, error) {
	var users []db.User
	var total int64
	if err := r.g.Model(&db.User{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	if err := r.g.Order("created_at DESC").Limit(limit).Offset(offset).Find(&users).Error; err != nil {
		return nil, 0, err
	}
	return users, total, nil
}

func (r *UserRepo) SetAdmin(email string, admin bool) error {
	return r.g.Model(&db.User{}).Where("email = ?", email).Update("is_admin", admin).Error
}

func (r *UserRepo) SetAllowed(email string, allowed bool) error {
	return r.g.Model(&db.User{}).Where("email = ?", email).Update("is_allowed", allowed).Error
}
```

- [ ] **Step 5: Run tests**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: PASS, three cases.

- [ ] **Step 6: Commit**

```bash
git add internal/repository/user_repo.go internal/repository/user_repo_test.go internal/repository/testhelp_test.go
git commit -m "feat(account-service-backend): add user repo / Ajout du repo utilisateurs"
```

---

### Task 12: OAuth2 client repository

**Files:**
- Create: `internal/repository/oauth2_client_repo.go`
- Test: `internal/repository/oauth2_client_repo_test.go`

- [ ] **Step 1: Write the failing test**

```go
//go:build integration

package repository

import (
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestOAuth2ClientCRUD(t *testing.T) {
	g := setupTestDB(t)
	r := NewOAuth2ClientRepo(g)

	c := &db.OAuth2Client{
		ClientID:        "cli-1",
		ClientSecretEnc: []byte("ciphertext"),
		Name:            "Test",
		TokenTTLSeconds: 60,
		RefreshTTLSeconds: 86400,
		IsActive:        true,
	}
	if err := r.Create(c); err != nil {
		t.Fatalf("Create: %v", err)
	}
	if c.ID == "" {
		t.Fatal("Create should set ID")
	}

	got, err := r.GetByClientID("cli-1")
	if err != nil {
		t.Fatalf("GetByClientID: %v", err)
	}
	if got.Name != "Test" {
		t.Errorf("Name=%q", got.Name)
	}

	if err := r.Update(c.ID, map[string]interface{}{"name": "Renamed"}); err != nil {
		t.Fatalf("Update: %v", err)
	}
	got, _ = r.GetByID(c.ID)
	if got.Name != "Renamed" {
		t.Fatalf("Update did not persist: %q", got.Name)
	}

	clients, total, err := r.List(10, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 1 || len(clients) != 1 {
		t.Fatalf("List total=%d len=%d", total, len(clients))
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package repository

import (
	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type OAuth2ClientRepo struct {
	g *gorm.DB
}

func NewOAuth2ClientRepo(g *gorm.DB) *OAuth2ClientRepo {
	return &OAuth2ClientRepo{g: g}
}

func (r *OAuth2ClientRepo) Create(c *db.OAuth2Client) error {
	if c.ID == "" {
		c.ID = uuid.New().String()
	}
	return r.g.Create(c).Error
}

func (r *OAuth2ClientRepo) GetByID(id string) (*db.OAuth2Client, error) {
	var c db.OAuth2Client
	if err := r.g.Where("id = ?", id).First(&c).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

func (r *OAuth2ClientRepo) GetByClientID(clientID string) (*db.OAuth2Client, error) {
	var c db.OAuth2Client
	if err := r.g.Where("client_id = ?", clientID).First(&c).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

func (r *OAuth2ClientRepo) Update(id string, fields map[string]interface{}) error {
	return r.g.Model(&db.OAuth2Client{}).Where("id = ?", id).Updates(fields).Error
}

func (r *OAuth2ClientRepo) Delete(id string) error {
	return r.g.Delete(&db.OAuth2Client{}, "id = ?", id).Error
}

func (r *OAuth2ClientRepo) List(limit, offset int) ([]db.OAuth2Client, int64, error) {
	var clients []db.OAuth2Client
	var total int64
	if err := r.g.Model(&db.OAuth2Client{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	if err := r.g.Order("created_at DESC").Limit(limit).Offset(offset).Find(&clients).Error; err != nil {
		return nil, 0, err
	}
	return clients, total, nil
}
```

- [ ] **Step 4: Run tests**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/repository/oauth2_client_repo.go internal/repository/oauth2_client_repo_test.go
git commit -m "feat(account-service-backend): add OAuth2 client repo / Ajout du repo des clients OAuth2"
```

---

### Task 13: Auth code repository (single-use)

**Files:**
- Create: `internal/repository/authcode_repo.go`
- Test: `internal/repository/authcode_repo_test.go`

- [ ] **Step 1: Failing test**

```go
//go:build integration

package repository

import (
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

func TestAuthCodeSingleUse(t *testing.T) {
	g := setupTestDB(t)
	r := NewAuthCodeRepo(g)

	code := &db.OAuth2AuthorizationCode{
		CodeHash:      "hash-1",
		ClientID:      "cli-1",
		UserEmail:     "alice@example.com",
		RedirectURI:   "https://x/cb",
		CodeChallenge: "challenge",
		ExpiresAt:     time.Now().Add(10 * time.Minute),
	}
	if err := r.Create(code); err != nil {
		t.Fatalf("Create: %v", err)
	}
	got, err := r.ConsumeUnused("hash-1")
	if err != nil {
		t.Fatalf("ConsumeUnused: %v", err)
	}
	if got.UserEmail != "alice@example.com" {
		t.Fatal("wrong row")
	}
	if _, err := r.ConsumeUnused("hash-1"); err == nil {
		t.Fatal("second ConsumeUnused should fail")
	}
}

func TestPurgeExpired(t *testing.T) {
	g := setupTestDB(t)
	r := NewAuthCodeRepo(g)
	_ = r.Create(&db.OAuth2AuthorizationCode{
		CodeHash:    "old",
		ClientID:    "c",
		UserEmail:   "x@y",
		RedirectURI: "https://x",
		ExpiresAt:   time.Now().Add(-1 * time.Hour),
	})
	n, err := r.PurgeExpired()
	if err != nil {
		t.Fatalf("PurgeExpired: %v", err)
	}
	if n != 1 {
		t.Errorf("purged=%d want 1", n)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package repository

import (
	"errors"
	"time"

	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type AuthCodeRepo struct {
	g *gorm.DB
}

func NewAuthCodeRepo(g *gorm.DB) *AuthCodeRepo {
	return &AuthCodeRepo{g: g}
}

func (r *AuthCodeRepo) Create(c *db.OAuth2AuthorizationCode) error {
	return r.g.Create(c).Error
}

// ConsumeUnused finds an unused, non-expired code by hash and marks it used in the same tx.
// Returns the row content as it was before the flag flip.
func (r *AuthCodeRepo) ConsumeUnused(codeHash string) (*db.OAuth2AuthorizationCode, error) {
	var out db.OAuth2AuthorizationCode
	err := r.g.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("code_hash = ? AND used = ? AND expires_at > ?", codeHash, false, time.Now()).
			First(&out).Error; err != nil {
			return err
		}
		return tx.Model(&db.OAuth2AuthorizationCode{}).
			Where("code_hash = ? AND used = ?", codeHash, false).
			Update("used", true).Error
	})
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("invalid_grant")
		}
		return nil, err
	}
	return &out, nil
}

func (r *AuthCodeRepo) PurgeExpired() (int64, error) {
	res := r.g.Where("expires_at < ?", time.Now()).Delete(&db.OAuth2AuthorizationCode{})
	return res.RowsAffected, res.Error
}
```

- [ ] **Step 4: Run**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/repository/authcode_repo.go internal/repository/authcode_repo_test.go
git commit -m "feat(account-service-backend): add auth code repo with single-use semantics / Ajout du repo des codes d'autorisation"
```

---

### Task 14: Refresh token repository (rotation + reuse detection)

**Files:**
- Create: `internal/repository/refresh_repo.go`
- Test: `internal/repository/refresh_repo_test.go`

- [ ] **Step 1: Failing test**

```go
//go:build integration

package repository

import (
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
)

func newRefresh(sid, hash string) *db.OAuth2RefreshToken {
	return &db.OAuth2RefreshToken{
		ID:        uuid.New().String(),
		TokenHash: hash,
		SID:       sid,
		ClientID:  "cli-1",
		UserEmail: "alice@example.com",
		ExpiresAt: time.Now().Add(24 * time.Hour),
	}
}

func TestRefreshRotateChain(t *testing.T) {
	g := setupTestDB(t)
	r := NewRefreshRepo(g)
	old := newRefresh("sid-A", "h1")
	if err := r.Create(old); err != nil {
		t.Fatalf("Create: %v", err)
	}
	rotated, err := r.Rotate("h1", "h2")
	if err != nil {
		t.Fatalf("Rotate: %v", err)
	}
	if rotated.SID != "sid-A" {
		t.Errorf("SID drift on rotate")
	}
	// Old must now be revoked.
	got, err := r.FindByHash("h1")
	if err != nil {
		t.Fatalf("FindByHash: %v", err)
	}
	if !got.Revoked {
		t.Fatal("old row not revoked after rotate")
	}
}

func TestRefreshReuseDetectionRevokesChain(t *testing.T) {
	g := setupTestDB(t)
	r := NewRefreshRepo(g)
	first := newRefresh("sid-B", "ha")
	if err := r.Create(first); err != nil {
		t.Fatalf("Create: %v", err)
	}
	if _, err := r.Rotate("ha", "hb"); err != nil {
		t.Fatalf("Rotate1: %v", err)
	}
	// Reuse the original (now-revoked) hash.
	if _, err := r.Rotate("ha", "hc"); err == nil {
		t.Fatal("expected reuse to fail")
	}
	// All rows for the sid should now be revoked.
	rows, err := r.ListBySID("sid-B")
	if err != nil {
		t.Fatalf("ListBySID: %v", err)
	}
	for _, x := range rows {
		if !x.Revoked {
			t.Fatalf("row %s should be revoked after reuse detection", x.ID)
		}
	}
}

func TestRefreshRevokeAllForUser(t *testing.T) {
	g := setupTestDB(t)
	r := NewRefreshRepo(g)
	_ = r.Create(newRefresh("s1", "h1"))
	_ = r.Create(newRefresh("s2", "h2"))
	if err := r.RevokeAllForUser("alice@example.com", "admin_revoke"); err != nil {
		t.Fatalf("RevokeAllForUser: %v", err)
	}
	rows, _ := r.ListByUser("alice@example.com")
	for _, x := range rows {
		if !x.Revoked {
			t.Fatalf("row %s not revoked", x.ID)
		}
	}
}
```

- [ ] **Step 2: Failing run**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package repository

import (
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type RefreshRepo struct {
	g *gorm.DB
}

func NewRefreshRepo(g *gorm.DB) *RefreshRepo {
	return &RefreshRepo{g: g}
}

func (r *RefreshRepo) Create(t *db.OAuth2RefreshToken) error {
	if t.ID == "" {
		t.ID = uuid.New().String()
	}
	return r.g.Create(t).Error
}

func (r *RefreshRepo) FindByHash(hash string) (*db.OAuth2RefreshToken, error) {
	var t db.OAuth2RefreshToken
	if err := r.g.Where("token_hash = ?", hash).First(&t).Error; err != nil {
		return nil, err
	}
	return &t, nil
}

func (r *RefreshRepo) ListBySID(sid string) ([]db.OAuth2RefreshToken, error) {
	var out []db.OAuth2RefreshToken
	err := r.g.Where("sid = ?", sid).Find(&out).Error
	return out, err
}

func (r *RefreshRepo) ListByUser(email string) ([]db.OAuth2RefreshToken, error) {
	var out []db.OAuth2RefreshToken
	err := r.g.Where("user_email = ?", email).Find(&out).Error
	return out, err
}

// Rotate atomically:
//   - looks up the row by oldHash
//   - if it's already revoked → reuse attack: revoke entire sid chain, return error
//   - else mark row revoked, insert new row with same sid
func (r *RefreshRepo) Rotate(oldHash, newHash string) (*db.OAuth2RefreshToken, error) {
	var newRow db.OAuth2RefreshToken
	err := r.g.Transaction(func(tx *gorm.DB) error {
		var existing db.OAuth2RefreshToken
		if err := tx.Where("token_hash = ?", oldHash).First(&existing).Error; err != nil {
			return err
		}
		if existing.Revoked {
			// Reuse attack — revoke the entire chain
			now := time.Now()
			if err := tx.Model(&db.OAuth2RefreshToken{}).
				Where("sid = ?", existing.SID).
				Updates(map[string]interface{}{
					"revoked":        true,
					"revoked_at":     &now,
					"revoked_reason": "reuse_attack",
				}).Error; err != nil {
				return err
			}
			return errors.New("reuse_attack")
		}
		now := time.Now()
		if err := tx.Model(&db.OAuth2RefreshToken{}).
			Where("id = ?", existing.ID).
			Updates(map[string]interface{}{
				"revoked":        true,
				"revoked_at":     &now,
				"revoked_reason": "rotated",
				"last_used_at":   &now,
			}).Error; err != nil {
			return err
		}
		newRow = db.OAuth2RefreshToken{
			ID:          uuid.New().String(),
			TokenHash:   newHash,
			SID:         existing.SID,
			ClientID:    existing.ClientID,
			UserEmail:   existing.UserEmail,
			ExpiresAt:   existing.ExpiresAt,
			RotatedFrom: existing.ID,
		}
		return tx.Create(&newRow).Error
	})
	if err != nil {
		return nil, err
	}
	return &newRow, nil
}

func (r *RefreshRepo) RevokeBySID(sid, reason string) error {
	now := time.Now()
	return r.g.Model(&db.OAuth2RefreshToken{}).
		Where("sid = ? AND revoked = ?", sid, false).
		Updates(map[string]interface{}{
			"revoked":        true,
			"revoked_at":     &now,
			"revoked_reason": reason,
		}).Error
}

func (r *RefreshRepo) RevokeAllForUser(email, reason string) error {
	now := time.Now()
	return r.g.Model(&db.OAuth2RefreshToken{}).
		Where("user_email = ? AND revoked = ?", email, false).
		Updates(map[string]interface{}{
			"revoked":        true,
			"revoked_at":     &now,
			"revoked_reason": reason,
		}).Error
}
```

- [ ] **Step 4: Run**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/repository/refresh_repo.go internal/repository/refresh_repo_test.go
git commit -m "feat(account-service-backend): add refresh repo with rotation and reuse detection / Ajout du repo des refresh tokens"
```

---

### Task 15: Logout-event repository

**Files:**
- Create: `internal/repository/logout_event_repo.go`
- Test: `internal/repository/logout_event_repo_test.go`

- [ ] **Step 1: Failing test**

```go
//go:build integration

package repository

import (
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
)

func TestLogoutEventEnqueueAndPickPending(t *testing.T) {
	g := setupTestDB(t)
	r := NewLogoutEventRepo(g)
	ev := &db.LogoutEvent{
		ID:            uuid.New().String(),
		ClientID:      "c",
		UserEmail:     "u@x",
		SID:           "sid",
		WebhookURL:    "https://x",
		Status:        "pending",
		NextAttemptAt: time.Now(),
	}
	if err := r.Create(ev); err != nil {
		t.Fatalf("Create: %v", err)
	}
	pending, err := r.PickPending(10)
	if err != nil {
		t.Fatalf("PickPending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("len=%d", len(pending))
	}
	if err := r.MarkSent(pending[0].ID); err != nil {
		t.Fatalf("MarkSent: %v", err)
	}
	again, _ := r.PickPending(10)
	if len(again) != 0 {
		t.Fatalf("sent row picked again")
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package repository

import (
	"time"

	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type LogoutEventRepo struct {
	g *gorm.DB
}

func NewLogoutEventRepo(g *gorm.DB) *LogoutEventRepo {
	return &LogoutEventRepo{g: g}
}

func (r *LogoutEventRepo) Create(e *db.LogoutEvent) error {
	if e.Status == "" {
		e.Status = "pending"
	}
	return r.g.Create(e).Error
}

func (r *LogoutEventRepo) PickPending(limit int) ([]db.LogoutEvent, error) {
	var out []db.LogoutEvent
	err := r.g.Where("status = ? AND next_attempt_at <= ?", "pending", time.Now()).
		Order("next_attempt_at ASC").Limit(limit).Find(&out).Error
	return out, err
}

func (r *LogoutEventRepo) MarkSent(id string) error {
	return r.g.Model(&db.LogoutEvent{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status":     "sent",
		"updated_at": time.Now(),
	}).Error
}

func (r *LogoutEventRepo) MarkFailed(id, errMsg string) error {
	return r.g.Model(&db.LogoutEvent{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status":     "failed",
		"last_error": errMsg,
		"updated_at": time.Now(),
	}).Error
}

func (r *LogoutEventRepo) Reschedule(id string, attempts int, nextAt time.Time, errMsg string) error {
	return r.g.Model(&db.LogoutEvent{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status":          "pending",
		"attempts":        attempts,
		"next_attempt_at": nextAt,
		"last_error":      errMsg,
		"updated_at":      time.Now(),
	}).Error
}
```

- [ ] **Step 4: Run**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/repository/logout_event_repo.go internal/repository/logout_event_repo_test.go
git commit -m "feat(account-service-backend): add logout-event repo / Ajout du repo des événements de déconnexion"
```

---

### Task 16: Audit log repository

**Files:**
- Create: `internal/repository/audit_repo.go`
- Test: `internal/repository/audit_repo_test.go`

- [ ] **Step 1: Failing test**

```go
//go:build integration

package repository

import (
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestAuditInsertAndList(t *testing.T) {
	g := setupTestDB(t)
	r := NewAuditRepo(g)

	for i := 0; i < 5; i++ {
		_ = r.Insert(&db.AuditLog{Event: "login", ActorEmail: "a@x"})
	}
	rows, total, err := r.List(map[string]interface{}{"event": "login"}, 3, 0)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if total != 5 {
		t.Errorf("total=%d", total)
	}
	if len(rows) != 3 {
		t.Errorf("len=%d", len(rows))
	}
}
```

- [ ] **Step 2: Run**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package repository

import (
	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type AuditRepo struct {
	g *gorm.DB
}

func NewAuditRepo(g *gorm.DB) *AuditRepo {
	return &AuditRepo{g: g}
}

func (r *AuditRepo) Insert(l *db.AuditLog) error {
	return r.g.Create(l).Error
}

func (r *AuditRepo) List(filters map[string]interface{}, limit, offset int) ([]db.AuditLog, int64, error) {
	q := r.g.Model(&db.AuditLog{})
	for k, v := range filters {
		q = q.Where(k+" = ?", v)
	}
	var total int64
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	var rows []db.AuditLog
	if err := q.Order("created_at DESC").Limit(limit).Offset(offset).Find(&rows).Error; err != nil {
		return nil, 0, err
	}
	return rows, total, nil
}
```

- [ ] **Step 4: Run**

```bash
go test -tags=integration ./internal/repository/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/repository/audit_repo.go internal/repository/audit_repo_test.go
git commit -m "feat(account-service-backend): add audit log repo / Ajout du repo des journaux d'audit"
```

---

## Phase 3 — Admin-UI Session Login & Middleware

### Task 17: Auth middleware (RequireAuth, RequireAdmin)

**Files:**
- Create: `internal/auth/middleware.go`
- Test: `internal/auth/middleware_test.go`

- [ ] **Step 1: Write the failing test**

```go
package auth

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRequireAuth_RejectsMissingCookie(t *testing.T) {
	called := false
	h := RequireAuth("secret")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("Code=%d, want 401", w.Code)
	}
	if called {
		t.Fatal("inner handler should not run")
	}
}

func TestRequireAuth_PassesWithValidSession(t *testing.T) {
	w := httptest.NewRecorder()
	_ = SetSession(w, "secret", SessionData{Email: "a@x", Token: "t"}, false)
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	for _, c := range w.Result().Cookies() {
		r.AddCookie(c)
	}

	called := false
	h := RequireAuth("secret")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
	}))
	h.ServeHTTP(httptest.NewRecorder(), r)
	if !called {
		t.Fatal("inner handler should run")
	}
}

func TestRequireAdmin_RejectsNonAdmin(t *testing.T) {
	w := httptest.NewRecorder()
	_ = SetSession(w, "secret", SessionData{Email: "a@x", Token: "t"}, false)
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	for _, c := range w.Result().Cookies() {
		r.AddCookie(c)
	}
	// Inject a fake user-lookup that returns non-admin.
	resolver := func(email string) (bool, bool) { return true, false } // is_allowed, is_admin
	h := RequireAdmin("secret", resolver)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, r)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("Code=%d, want 403", rr.Code)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/auth/...
```
Expected: FAIL — `RequireAuth`/`RequireAdmin` undefined.

- [ ] **Step 3: Implement**

```go
package auth

import (
	"context"
	"net/http"
)

type ctxKey int

const sessionCtxKey ctxKey = 1

// AdminResolver answers (isAllowed, isAdmin) for a given email. Plug a UserRepo lookup at boot.
type AdminResolver func(email string) (bool, bool)

func RequireAuth(secret string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			data, err := GetSession(r, secret)
			if err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_, _ = w.Write([]byte(`{"error":"unauthorized"}`))
				return
			}
			ctx := context.WithValue(r.Context(), sessionCtxKey, data)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func RequireAdmin(secret string, resolve AdminResolver) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return RequireAuth(secret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			data, _ := SessionFromContext(r.Context())
			allowed, isAdmin := resolve(data.Email)
			if !allowed {
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(`{"error":"forbidden","error_description":"user blocked"}`))
				return
			}
			if !isAdmin {
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(`{"error":"forbidden","error_description":"admin only"}`))
				return
			}
			next.ServeHTTP(w, r)
		}))
	}
}

func SessionFromContext(ctx context.Context) (*SessionData, bool) {
	d, ok := ctx.Value(sessionCtxKey).(*SessionData)
	return d, ok
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/auth/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/auth/middleware.go internal/auth/middleware_test.go
git commit -m "feat(account-service-backend): add RequireAuth/RequireAdmin middleware / Ajout du middleware d'authentification"
```

---

### Task 18: Login handler — POST /api/v1/login

**Files:**
- Create: `internal/auth/handlers.go`
- Test: `internal/auth/handlers_test.go`

- [ ] **Step 1: Failing test (against an in-process hellopro mock)**

```go
package auth

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

type fakeUserRepo struct {
	upsertCalled bool
	isAdmin      bool
	isAllowed    bool
	failUpsert   bool
}

type fakeUser struct {
	Email     string
	IsAdmin   bool
	IsAllowed bool
}

func (f *fakeUserRepo) UpsertOnLogin(email, name string) (*fakeUser, error) {
	f.upsertCalled = true
	return &fakeUser{Email: email, IsAdmin: f.isAdmin, IsAllowed: f.isAllowed}, nil
}

func TestHandleLogin_RoundTripJSON(t *testing.T) {
	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
	defer hellopro.Close()

	cfg := Config{
		AuthURL:   hellopro.URL,
		JWTSecret: "secret",
	}
	repo := &fakeUserRepo{isAllowed: true, isAdmin: true}

	h := NewLoginHandler(cfg, repo)
	body, _ := json.Marshal(map[string]string{"username": "alice", "password": "p"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var out map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &out)
	if out["email"] != "alice@example.com" {
		t.Errorf("email=%v", out["email"])
	}
	if out["is_admin"] != true {
		t.Errorf("is_admin=%v", out["is_admin"])
	}
	if !repo.upsertCalled {
		t.Fatal("upsert not called")
	}
}

func TestHandleLogin_InvalidCredentials(t *testing.T) {
	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":false}`))
	}))
	defer hellopro.Close()

	cfg := Config{AuthURL: hellopro.URL, JWTSecret: "s"}
	h := NewLoginHandler(cfg, &fakeUserRepo{})
	body, _ := json.Marshal(map[string]string{"username": "alice", "password": "bad"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Fatalf("Code=%d", w.Code)
	}
}

func TestHandleLogin_BlockedUser(t *testing.T) {
	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"a@x","display_name":"A"}`))
	}))
	defer hellopro.Close()

	cfg := Config{AuthURL: hellopro.URL, JWTSecret: "s"}
	repo := &fakeUserRepo{isAllowed: false}
	h := NewLoginHandler(cfg, repo)
	body, _ := json.Marshal(map[string]string{"username": "a", "password": "p"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusForbidden {
		t.Fatalf("Code=%d", w.Code)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/auth/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package auth

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

// Config carries the env-derived knobs the auth package uses. Wired by main.go.
type Config struct {
	AuthURL      string
	JWTSecret    string
	JWTAudience  string
	SecureCookie bool
	FallbackUser string
	FallbackPass string
	FallbackEmail string
}

// UserUpserter is the interface the login handler depends on. The real
// implementation is repository.UserRepo; tests use a fake.
type UserUpserter interface {
	UpsertOnLogin(email, displayName string) (*UpsertedUser, error)
}

// UpsertedUser is the minimal shape the handler reads back. The repo returns
// its own User type; main.go wires an adapter in Task 26 to bridge.
type UpsertedUser struct {
	Email     string
	IsAdmin   bool
	IsAllowed bool
}

func NewLoginHandler(cfg Config, repo UserUpserter) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Username string `json:"username"`
			Password string `json:"password"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeErr(w, http.StatusBadRequest, "invalid_request", "invalid body")
			return
		}
		username := strings.TrimSpace(body.Username)
		if username == "" || body.Password == "" {
			writeErr(w, http.StatusBadRequest, "invalid_request", "missing fields")
			return
		}

		resp, err := AuthenticateHellopro(cfg.AuthURL, username, body.Password)
		if (err != nil || !resp.Success) && cfg.FallbackUser != "" &&
			username == cfg.FallbackUser && body.Password == cfg.FallbackPass {
			resp = &HelloProAuthResponse{
				Success:     true,
				Email:       cfg.FallbackEmail,
				DisplayName: cfg.FallbackUser,
			}
			err = nil
		}
		if err != nil {
			writeErr(w, http.StatusUnauthorized, "auth_error", "authentication failed")
			return
		}
		if !resp.Success {
			writeErr(w, http.StatusUnauthorized, "invalid_grant", "invalid credentials")
			return
		}

		u, err := repo.UpsertOnLogin(resp.Email, resp.DisplayName)
		if err != nil {
			writeErr(w, http.StatusInternalServerError, "server_error", "user upsert failed")
			return
		}
		if !u.IsAllowed {
			writeErr(w, http.StatusForbidden, "forbidden", "user blocked")
			return
		}

		claims := Claims{
			Sub:     u.Email,
			Email:   u.Email,
			Name:    resp.DisplayName,
			Aud:     cfg.JWTAudience,
			Iat:     time.Now().Unix(),
			Exp:     time.Now().Add(24 * time.Hour).Unix(),
			IsAdmin: u.IsAdmin,
		}
		tok, err := SignJWT(cfg.JWTSecret, claims)
		if err != nil {
			writeErr(w, http.StatusInternalServerError, "server_error", "sign failed")
			return
		}
		_ = SetSession(w, cfg.JWTSecret, SessionData{
			Email: u.Email, DisplayName: resp.DisplayName, Token: tok,
		}, cfg.SecureCookie)

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"token":        tok,
			"email":        u.Email,
			"display_name": resp.DisplayName,
			"is_admin":     u.IsAdmin,
		})
	})
}

func NewLogoutHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ClearSession(w)
		w.WriteHeader(http.StatusNoContent)
	})
}

func writeErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": desc,
	})
}
```

Update the test's fake to satisfy `UserUpserter` (rename `fakeUser` → `UpsertedUser`):

```go
func (f *fakeUserRepo) UpsertOnLogin(email, name string) (*UpsertedUser, error) {
	f.upsertCalled = true
	return &UpsertedUser{Email: email, IsAdmin: f.isAdmin, IsAllowed: f.isAllowed}, nil
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/auth/...
```
Expected: PASS, all three login cases plus jwt + session + middleware.

- [ ] **Step 5: Commit**

```bash
git add internal/auth/handlers.go internal/auth/handlers_test.go
git commit -m "feat(account-service-backend): add login/logout handlers / Ajout des handlers de connexion/déconnexion"
```

---

### Task 19: API package — request logging + recovery middleware

**Files:**
- Create: `internal/api/middleware.go`
- Test: `internal/api/middleware_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRecoverFromPanic(t *testing.T) {
	h := Recover(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		panic("boom")
	}))
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/", nil)
	h.ServeHTTP(w, r)
	if w.Code != http.StatusInternalServerError {
		t.Fatalf("Code=%d", w.Code)
	}
}

func TestJSONContentType(t *testing.T) {
	h := JSON(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("{}"))
	}))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/", nil))
	if got := w.Header().Get("Content-Type"); got != "application/json" {
		t.Fatalf("Content-Type=%q", got)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL — package doesn't exist.

- [ ] **Step 3: Implement**

```go
package api

import (
	"log/slog"
	"net/http"
	"time"
)

func Recover(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				slog.Error("panic", "recover", rec, "path", r.URL.Path, "method", r.Method)
				http.Error(w, `{"error":"server_error"}`, http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

func JSON(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		next.ServeHTTP(w, r)
	})
}

func RequestLog(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, code: http.StatusOK}
		next.ServeHTTP(sw, r)
		slog.Info("http",
			"method", r.Method,
			"path", r.URL.Path,
			"status", sw.code,
			"dur_ms", time.Since(start).Milliseconds(),
		)
	})
}

type statusWriter struct {
	http.ResponseWriter
	code int
}

func (s *statusWriter) WriteHeader(c int) {
	s.code = c
	s.ResponseWriter.WriteHeader(c)
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/middleware.go internal/api/middleware_test.go
git commit -m "feat(account-service-backend): add request log/recover/JSON middleware / Ajout du middleware HTTP"
```

---

### Task 20: `/me` and `/me/sessions` handlers

**Files:**
- Create: `internal/api/me_handlers.go`
- Test: `internal/api/me_handlers_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/auth"
)

type fakeUserResolver struct {
	isAdmin bool
}

func (f *fakeUserResolver) FindByEmail(email string) (UserInfo, error) {
	return UserInfo{
		Email:       email,
		DisplayName: "Alice",
		IsAdmin:     f.isAdmin,
		IsAllowed:   true,
	}, nil
}

func TestMeHandler_ReturnsCurrentUser(t *testing.T) {
	h := NewMeHandler(&fakeUserResolver{isAdmin: true})
	r := httptest.NewRequest(http.MethodGet, "/me", nil)
	ctx := context.WithValue(r.Context(), authSessionKey, &auth.SessionData{Email: "alice@example.com"})
	r = r.WithContext(ctx)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["email"] != "alice@example.com" {
		t.Errorf("email=%v", got["email"])
	}
	if got["is_admin"] != true {
		t.Errorf("is_admin=%v", got["is_admin"])
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package api

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/auth"
)

type ctxKey int

// authSessionKey mirrors the value used by auth.SessionFromContext so handlers
// in this package don't depend on internal/auth/middleware constants.
const authSessionKey ctxKey = 0

type UserInfo struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
	IsAdmin     bool   `json:"is_admin"`
	IsAllowed   bool   `json:"is_allowed"`
}

type UserResolver interface {
	FindByEmail(email string) (UserInfo, error)
}

func NewMeHandler(repo UserResolver) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sess, ok := sessionFromAnyKey(r.Context())
		if !ok {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		u, err := repo.FindByEmail(sess.Email)
		if err != nil {
			http.Error(w, `{"error":"server_error"}`, http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(u)
	})
}

// sessionFromAnyKey checks both auth's context key and the local key used in
// tests so the handler is wireable from production middleware.
func sessionFromAnyKey(ctx context.Context) (*auth.SessionData, bool) {
	if d, ok := auth.SessionFromContext(ctx); ok {
		return d, true
	}
	if d, ok := ctx.Value(authSessionKey).(*auth.SessionData); ok {
		return d, true
	}
	return nil, false
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/me_handlers.go internal/api/me_handlers_test.go
git commit -m "feat(account-service-backend): add /me handler / Ajout du handler /me"
```

---

## Phase 4 — OAuth2 Authorization Server

### Task 21: PKCE S256 verifier

**Files:**
- Create: `internal/authserver/pkce.go`
- Test: `internal/authserver/pkce_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"crypto/sha256"
	"encoding/base64"
	"testing"
)

func makeVerifierAndChallenge() (string, string) {
	verifier := "ZWY1MWQ5ZDQyZjA4MWE0YTI2OTAyZmFlMmM4MWM4MzM"
	sum := sha256.Sum256([]byte(verifier))
	chal := base64.RawURLEncoding.EncodeToString(sum[:])
	return verifier, chal
}

func TestVerifyPKCE_S256_OK(t *testing.T) {
	v, c := makeVerifierAndChallenge()
	if !VerifyPKCES256(v, c) {
		t.Fatal("expected match")
	}
}

func TestVerifyPKCE_S256_Reject(t *testing.T) {
	if VerifyPKCES256("wrong", "definitely-not-the-hash") {
		t.Fatal("expected no match")
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
)

func VerifyPKCES256(verifier, challenge string) bool {
	if verifier == "" || challenge == "" {
		return false
	}
	sum := sha256.Sum256([]byte(verifier))
	got := base64.RawURLEncoding.EncodeToString(sum[:])
	return subtle.ConstantTimeCompare([]byte(got), []byte(challenge)) == 1
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/pkce.go internal/authserver/pkce_test.go
git commit -m "feat(account-service-backend): add PKCE S256 verifier / Ajout de la vérification PKCE S256"
```

---

### Task 22: Auth code generator (random + SHA-256 hash)

**Files:**
- Create: `internal/authserver/codes.go`
- Test: `internal/authserver/codes_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"strings"
	"testing"
)

func TestGenerateAuthCode_Unique(t *testing.T) {
	seen := map[string]struct{}{}
	for i := 0; i < 100; i++ {
		raw, hash, err := GenerateAuthCode()
		if err != nil {
			t.Fatalf("GenerateAuthCode: %v", err)
		}
		if len(raw) < 32 {
			t.Errorf("raw len=%d", len(raw))
		}
		if len(hash) != 64 {
			t.Errorf("hash len=%d", len(hash))
		}
		if strings.Contains(hash, raw) {
			t.Error("hash should not contain raw")
		}
		if _, dup := seen[raw]; dup {
			t.Fatal("collision in 100 iterations — broken RNG")
		}
		seen[raw] = struct{}{}
	}
}

func TestHashAuthCodeMatchesGenerator(t *testing.T) {
	raw, hash, _ := GenerateAuthCode()
	if got := HashAuthCode(raw); got != hash {
		t.Fatalf("HashAuthCode(%q)=%q want %q", raw, got, hash)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"io"
)

func GenerateAuthCode() (raw, hash string, err error) {
	buf := make([]byte, 32)
	if _, err := io.ReadFull(rand.Reader, buf); err != nil {
		return "", "", err
	}
	raw = base64.RawURLEncoding.EncodeToString(buf)
	hash = HashAuthCode(raw)
	return raw, hash, nil
}

func HashAuthCode(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/codes.go internal/authserver/codes_test.go
git commit -m "feat(account-service-backend): add auth code generator / Ajout du générateur de codes d'autorisation"
```

---

### Task 23: Branding endpoint

**Files:**
- Create: `internal/authserver/branding.go`
- Test: `internal/authserver/branding_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeClientLookup struct {
	out *db.OAuth2Client
	err error
}

func (f fakeClientLookup) GetByClientID(id string) (*db.OAuth2Client, error) {
	if f.err != nil {
		return nil, f.err
	}
	return f.out, nil
}

func TestBrandingHandler_ReturnsPublicFields(t *testing.T) {
	cli := &db.OAuth2Client{ClientID: "x", Name: "Hellopro X", LogoURL: "/u/x.png", BrandColor: "#0055ff"}
	h := NewBrandingHandler(fakeClientLookup{out: cli})

	r := httptest.NewRequest(http.MethodGet, "/authorize/branding/x.json", nil)
	r.SetPathValue("client_id", "x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["name"] != "Hellopro X" || got["logo_url"] != "/u/x.png" || got["brand_color"] != "#0055ff" {
		t.Fatalf("unexpected body: %v", got)
	}
}

func TestBrandingHandler_404OnUnknownClient(t *testing.T) {
	h := NewBrandingHandler(fakeClientLookup{err: errors.New("not found")})
	r := httptest.NewRequest(http.MethodGet, "/authorize/branding/x.json", nil)
	r.SetPathValue("client_id", "x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusNotFound {
		t.Fatalf("Code=%d", w.Code)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type ClientLookup interface {
	GetByClientID(id string) (*db.OAuth2Client, error)
}

func NewBrandingHandler(lookup ClientLookup) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("client_id")
		c, err := lookup.GetByClientID(id)
		if err != nil {
			http.Error(w, `{"error":"not_found"}`, http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "public, max-age=60")
		_ = json.NewEncoder(w).Encode(map[string]string{
			"name":        c.Name,
			"logo_url":    c.LogoURL,
			"brand_color": c.BrandColor,
		})
	})
}
```

> **Note for the engineer:** `r.PathValue` requires Go 1.22+ pattern routes. Wire it up in main.go via `mux.Handle("GET /authorize/branding/{client_id}.json", brandingHandler)`.

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/branding.go internal/authserver/branding_test.go
git commit -m "feat(account-service-backend): add OAuth2 branding endpoint / Ajout de l'endpoint de branding"
```

---

### Task 24: Claim mapper

**Files:**
- Create: `internal/authserver/claim_mapper.go`
- Test: `internal/authserver/claim_mapper_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestApplyClaimMappings_DefaultsWhenEmpty(t *testing.T) {
	user := UserClaimSource{Email: "a@x", DisplayName: "Alice", IsAdmin: true}
	got := ApplyClaimMappings(nil, user)
	want := map[string]interface{}{
		"sub":   "a@x",
		"email": "a@x",
		"name":  "Alice",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got=%v want=%v", got, want)
	}
}

func TestApplyClaimMappings_CustomMapping(t *testing.T) {
	mapping, _ := json.Marshal(map[string]string{"email": "user_email", "is_admin": "role_admin"})
	got := ApplyClaimMappings(string(mapping), UserClaimSource{Email: "a@x", IsAdmin: true})
	if got["user_email"] != "a@x" {
		t.Errorf("user_email=%v", got["user_email"])
	}
	if got["role_admin"] != true {
		t.Errorf("role_admin=%v", got["role_admin"])
	}
	if _, found := got["sub"]; !found {
		t.Error("sub default missing")
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import "encoding/json"

type UserClaimSource struct {
	Email       string
	DisplayName string
	IsAdmin     bool
}

// ApplyClaimMappings produces a map[string]interface{} suitable to merge into
// auth.Claims.Custom. It always emits sub/email/name defaults. Custom mapping
// is a JSON object {user_field: jwt_claim_name}.
func ApplyClaimMappings(rawMapping string, src UserClaimSource) map[string]interface{} {
	out := map[string]interface{}{
		"sub":   src.Email,
		"email": src.Email,
		"name":  src.DisplayName,
	}
	if rawMapping == "" {
		return out
	}
	var mapping map[string]string
	if err := json.Unmarshal([]byte(rawMapping), &mapping); err != nil {
		return out
	}
	for userField, claim := range mapping {
		switch userField {
		case "email":
			out[claim] = src.Email
		case "display_name":
			out[claim] = src.DisplayName
		case "is_admin":
			out[claim] = src.IsAdmin
		}
	}
	return out
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/claim_mapper.go internal/authserver/claim_mapper_test.go
git commit -m "feat(account-service-backend): add claim mapper / Ajout du mapper de claims"
```

---

### Task 25: Server metadata endpoint (RFC 8414)

**Files:**
- Create: `internal/authserver/metadata.go`
- Test: `internal/authserver/metadata_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMetadataEndpoint(t *testing.T) {
	h := NewMetadataHandler("https://account.test")
	r := httptest.NewRequest(http.MethodGet, "/.well-known/oauth-authorization-server", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["issuer"] != "https://account.test" {
		t.Errorf("issuer=%v", got["issuer"])
	}
	if got["authorization_endpoint"] != "https://account.test/authorize" {
		t.Errorf("authorization_endpoint=%v", got["authorization_endpoint"])
	}
	methods, _ := got["code_challenge_methods_supported"].([]interface{})
	if len(methods) == 0 || methods[0] != "S256" {
		t.Errorf("code_challenge_methods_supported=%v", methods)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"encoding/json"
	"net/http"
)

func NewMetadataHandler(issuer string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"issuer":                                issuer,
			"authorization_endpoint":                issuer + "/authorize",
			"token_endpoint":                        issuer + "/token",
			"introspection_endpoint":                issuer + "/introspect",
			"revocation_endpoint":                   issuer + "/token/revoke",
			"registration_endpoint":                 issuer + "/register",
			"response_types_supported":              []string{"code"},
			"grant_types_supported":                 []string{"authorization_code", "refresh_token"},
			"code_challenge_methods_supported":      []string{"S256"},
			"token_endpoint_auth_methods_supported": []string{"client_secret_basic", "client_secret_post"},
		})
	})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/metadata.go internal/authserver/metadata_test.go
git commit -m "feat(account-service-backend): add /.well-known metadata / Ajout du endpoint metadata RFC 8414"
```

---

### Task 26: `/authorize` — params parser + redirect_uri validator

**Files:**
- Create: `internal/authserver/authorize.go`
- Test: `internal/authserver/authorize_params_test.go`

This task only covers the parser and URI validator. The full handler that
performs login + issues a code is Task 27 once the dependencies are in place.

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestParseAuthorizeParams_Required(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet,
		"/authorize?response_type=code&client_id=x&redirect_uri=https://x/cb&code_challenge=c&code_challenge_method=S256&state=s",
		nil)
	p, err := parseAuthorizeParams(r)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if p.ClientID != "x" || p.RedirectURI != "https://x/cb" || p.CodeChallenge != "c" {
		t.Fatalf("got %+v", p)
	}
}

func TestParseAuthorizeParams_RejectsNonCode(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=token&client_id=x&redirect_uri=https://x&code_challenge=c&code_challenge_method=S256", nil)
	if _, err := parseAuthorizeParams(r); err == nil {
		t.Fatal("expected error")
	}
}

func TestParseAuthorizeParams_RejectsPlainPKCE(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=code&client_id=x&redirect_uri=https://x&code_challenge=c&code_challenge_method=plain", nil)
	if _, err := parseAuthorizeParams(r); err == nil {
		t.Fatal("expected error")
	}
}

func TestIsRegisteredRedirectURI(t *testing.T) {
	uris := `["https://a/cb","https://b/cb"]`
	c := &db.OAuth2Client{RedirectURIs: &uris}
	if !isRegisteredRedirectURI(c, "https://b/cb") {
		t.Fatal("expected match")
	}
	if isRegisteredRedirectURI(c, "https://evil/cb") {
		t.Fatal("expected no match")
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type AuthorizeParams struct {
	ResponseType        string
	ClientID            string
	RedirectURI         string
	CodeChallenge       string
	CodeChallengeMethod string
	State               string
	Scope               string
}

func parseAuthorizeParams(r *http.Request) (*AuthorizeParams, error) {
	getValue := func(key string) string {
		if v := r.FormValue(key); v != "" {
			return v
		}
		return r.URL.Query().Get(key)
	}
	p := &AuthorizeParams{
		ResponseType:        getValue("response_type"),
		ClientID:            getValue("client_id"),
		RedirectURI:         getValue("redirect_uri"),
		CodeChallenge:       getValue("code_challenge"),
		CodeChallengeMethod: getValue("code_challenge_method"),
		State:               getValue("state"),
		Scope:               getValue("scope"),
	}
	if p.ResponseType != "code" {
		return nil, errors.New("response_type must be code")
	}
	if p.ClientID == "" {
		return nil, errors.New("client_id required")
	}
	if p.RedirectURI == "" {
		return nil, errors.New("redirect_uri required")
	}
	if p.CodeChallenge == "" {
		return nil, errors.New("code_challenge required (PKCE)")
	}
	if p.CodeChallengeMethod != "S256" {
		return nil, errors.New("code_challenge_method must be S256")
	}
	return p, nil
}

func isRegisteredRedirectURI(c *db.OAuth2Client, uri string) bool {
	if c.RedirectURIs == nil || *c.RedirectURIs == "" {
		return false
	}
	var uris []string
	if err := json.Unmarshal([]byte(*c.RedirectURIs), &uris); err != nil {
		return false
	}
	for _, registered := range uris {
		if registered == uri {
			return true
		}
	}
	return false
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/authorize.go internal/authserver/authorize_params_test.go
git commit -m "feat(account-service-backend): parse /authorize params + redirect URI guard / Validation des paramètres /authorize"
```

---

### Task 27: `/authorize` — full handler with skip-consent

**Files:**
- Modify: `internal/authserver/authorize.go`
- Create: `internal/authserver/handler.go`
- Test: `internal/authserver/authorize_handler_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type fakeAuthCodeRepo struct {
	created *db.OAuth2AuthorizationCode
}

func (f *fakeAuthCodeRepo) Create(c *db.OAuth2AuthorizationCode) error {
	f.created = c
	return nil
}

type fakeClientRepo struct {
	c *db.OAuth2Client
}

func (f *fakeClientRepo) GetByClientID(id string) (*db.OAuth2Client, error) {
	return f.c, nil
}

type fakeUserSrc struct{}

func (fakeUserSrc) UpsertOnLogin(email, name string) (*auth.UpsertedUser, error) {
	return &auth.UpsertedUser{Email: email, IsAllowed: true, IsAdmin: false}, nil
}

func TestAuthorizePOST_LoginIssuesCodeAndRedirects(t *testing.T) {
	uris := `["https://x/cb"]`
	cli := &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris, IsActive: true}

	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
	defer hellopro.Close()

	srv := NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
		UserUpserter: fakeUserSrc{},
		AuthURL:      hellopro.URL,
		JWTSecret:    "s",
		Issuer:       "https://account.test",
		AuthCodeTTL:  10 * time.Minute,
		SecureCookie: false,
	})

	form := url.Values{
		"action":                {"login"},
		"response_type":         {"code"},
		"client_id":             {"x"},
		"redirect_uri":          {"https://x/cb"},
		"code_challenge":        {"chal"},
		"code_challenge_method": {"S256"},
		"state":                 {"abc"},
		"username":              {"alice"},
		"password":              {"p"},
	}
	r := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)

	if w.Code != http.StatusFound {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	loc := w.Header().Get("Location")
	if !strings.HasPrefix(loc, "https://x/cb?") {
		t.Fatalf("Location=%q", loc)
	}
	q, _ := url.Parse(loc)
	if q.Query().Get("state") != "abc" {
		t.Fatalf("state=%q", q.Query().Get("state"))
	}
	if q.Query().Get("code") == "" {
		t.Fatal("missing code in redirect")
	}
}

func TestAuthorizeGET_BadRedirectURI(t *testing.T) {
	uris := `["https://x/cb"]`
	cli := &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris}
	srv := NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
	})
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=code&client_id=x&redirect_uri=https://evil/&code_challenge=c&code_challenge_method=S256", nil)
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["error"] != "invalid_request" {
		t.Fatalf("error=%q", body["error"])
	}
}

func TestAuthorizeGET_NoSession_RedirectsToLoginVue(t *testing.T) {
	uris := `["https://x/cb"]`
	cli := &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris}
	srv := NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
		LoginPath:    "/login",
	})
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=code&client_id=x&redirect_uri=https://x/cb&code_challenge=c&code_challenge_method=S256&state=abc", nil)
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)
	if w.Code != http.StatusFound {
		t.Fatalf("Code=%d", w.Code)
	}
	loc := w.Header().Get("Location")
	if !strings.HasPrefix(loc, "/login?") {
		t.Fatalf("Location=%q", loc)
	}
	if !strings.Contains(loc, "client_id=x") {
		t.Fatalf("client_id missing in %q", loc)
	}
	_ = uuid.Nil // keep import
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement the AuthServer struct + handler**

```go
// File: internal/authserver/handler.go
package authserver

import (
	"encoding/json"
	"net/http"
	"net/url"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type AuthCodeRepo interface {
	Create(c *db.OAuth2AuthorizationCode) error
}

type ClientRepo interface {
	GetByClientID(id string) (*db.OAuth2Client, error)
}

type AuthServerDeps struct {
	ClientRepo      ClientRepo
	AuthCodeRepo    AuthCodeRepo
	UserUpserter    auth.UserUpserter
	AuthURL         string
	JWTSecret       string
	JWTAudience     string
	Issuer          string
	AuthCodeTTL     time.Duration
	SecureCookie    bool
	FallbackUser    string
	FallbackPass    string
	FallbackEmail   string
	LoginPath       string // default "/login" — relative path to Vue login route
}

type AuthServer struct {
	deps AuthServerDeps
}

func NewAuthServer(d AuthServerDeps) *AuthServer {
	if d.AuthCodeTTL == 0 {
		d.AuthCodeTTL = 10 * time.Minute
	}
	if d.LoginPath == "" {
		d.LoginPath = "/login"
	}
	return &AuthServer{deps: d}
}

func (s *AuthServer) HandleAuthorize(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	p, err := parseAuthorizeParams(r)
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	client, err := s.deps.ClientRepo.GetByClientID(p.ClientID)
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "unknown client_id")
		return
	}
	if !client.IsActive {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "client inactive")
		return
	}
	if !isRegisteredRedirectURI(client, p.RedirectURI) {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "redirect_uri not registered")
		return
	}

	switch r.Method {
	case http.MethodGet:
		// Already-authenticated browser → issue code immediately (skip consent)
		if sess, err := auth.GetSession(r, s.deps.JWTSecret); err == nil {
			s.issueCodeAndRedirect(w, r, client, p, sess.Email)
			return
		}
		// Otherwise bounce to Vue login route, preserving every OAuth2 param
		q := url.Values{}
		q.Set("response_type", p.ResponseType)
		q.Set("client_id", p.ClientID)
		q.Set("redirect_uri", p.RedirectURI)
		q.Set("code_challenge", p.CodeChallenge)
		q.Set("code_challenge_method", p.CodeChallengeMethod)
		if p.State != "" {
			q.Set("state", p.State)
		}
		http.Redirect(w, r, s.deps.LoginPath+"?"+q.Encode(), http.StatusFound)

	case http.MethodPost:
		action := r.FormValue("action")
		if action != "login" {
			writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "unknown action")
			return
		}
		s.handleLogin(w, r, client, p)

	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (s *AuthServer) handleLogin(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, p *AuthorizeParams) {
	username := r.FormValue("username")
	password := r.FormValue("password")
	if username == "" || password == "" {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "missing credentials")
		return
	}
	resp, err := auth.AuthenticateHellopro(s.deps.AuthURL, username, password)
	if (err != nil || !resp.Success) && s.deps.FallbackUser != "" &&
		username == s.deps.FallbackUser && password == s.deps.FallbackPass {
		resp = &auth.HelloProAuthResponse{
			Success:     true,
			Email:       s.deps.FallbackEmail,
			DisplayName: s.deps.FallbackUser,
		}
		err = nil
	}
	if err != nil || !resp.Success {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_grant", "invalid credentials")
		return
	}
	u, err := s.deps.UserUpserter.UpsertOnLogin(resp.Email, resp.DisplayName)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "user upsert failed")
		return
	}
	if !u.IsAllowed {
		writeOAuthErr(w, http.StatusForbidden, "access_denied", "user blocked")
		return
	}
	if !s.userMatchesAllowedRoles(u, client) {
		writeOAuthErr(w, http.StatusForbidden, "access_denied", "role not allowed for this client")
		return
	}
	// Persist session so subsequent SSO into other clients skips login
	_ = auth.SetSession(w, s.deps.JWTSecret, auth.SessionData{
		Email: u.Email, DisplayName: resp.DisplayName,
	}, s.deps.SecureCookie)
	s.issueCodeAndRedirect(w, r, client, p, u.Email)
}

func (s *AuthServer) userMatchesAllowedRoles(u *auth.UpsertedUser, c *db.OAuth2Client) bool {
	if c.AllowedRoles == nil || *c.AllowedRoles == "" || *c.AllowedRoles == "null" || *c.AllowedRoles == "[]" {
		return true
	}
	var roles []string
	if err := json.Unmarshal([]byte(*c.AllowedRoles), &roles); err != nil {
		return true
	}
	if len(roles) == 0 {
		return true
	}
	role := "user"
	if u.IsAdmin {
		role = "admin"
	}
	for _, r := range roles {
		if r == role {
			return true
		}
	}
	return false
}

func (s *AuthServer) issueCodeAndRedirect(w http.ResponseWriter, r *http.Request, c *db.OAuth2Client, p *AuthorizeParams, userEmail string) {
	raw, hash, err := GenerateAuthCode()
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "code gen failed")
		return
	}
	code := &db.OAuth2AuthorizationCode{
		CodeHash:      hash,
		ClientID:      c.ClientID,
		UserEmail:     userEmail,
		RedirectURI:   p.RedirectURI,
		CodeChallenge: p.CodeChallenge,
		Scope:         p.Scope,
		ExpiresAt:     time.Now().Add(s.deps.AuthCodeTTL),
	}
	if err := s.deps.AuthCodeRepo.Create(code); err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "code persist failed")
		return
	}
	u, _ := url.Parse(p.RedirectURI)
	q := u.Query()
	q.Set("code", raw)
	if p.State != "" {
		q.Set("state", p.State)
	}
	u.RawQuery = q.Encode()
	http.Redirect(w, r, u.String(), http.StatusFound)
	_ = uuid.Nil
}

func writeOAuthErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": desc,
	})
}
```

> **Note:** The `auth.UserUpserter` interface used here is the one defined in Task 18; tests in this file reuse the same fake. Ensure both packages compile together (`go vet ./...`).

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
go vet ./...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/handler.go internal/authserver/authorize.go internal/authserver/authorize_handler_test.go
git commit -m "feat(account-service-backend): /authorize skip-consent flow / Flux /authorize sans consentement"
```

---

### Task 28: `/token` — authorization_code grant

**Files:**
- Create: `internal/authserver/token_endpoint.go`
- Test: `internal/authserver/token_authcode_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

type fakeConsumeAuthCode struct {
	stored *db.OAuth2AuthorizationCode
}

func (f *fakeConsumeAuthCode) ConsumeUnused(hash string) (*db.OAuth2AuthorizationCode, error) {
	if f.stored == nil || f.stored.CodeHash != hash {
		return nil, fakeNotFound{}
	}
	if f.stored.ExpiresAt.Before(time.Now()) {
		return nil, fakeNotFound{}
	}
	return f.stored, nil
}

type fakeNotFound struct{}

func (fakeNotFound) Error() string { return "invalid_grant" }

type fakeRefreshSink struct {
	created *db.OAuth2RefreshToken
}

func (f *fakeRefreshSink) Create(t *db.OAuth2RefreshToken) error {
	f.created = t
	return nil
}

func TestToken_AuthCodeGrant_Success(t *testing.T) {
	verifier, challenge := makeVerifierAndChallenge()
	plainSecret := "client-secret"
	cipher := []byte("ENC:" + plainSecret) // tests use a fake cipher (see helpers.go)

	cli := &db.OAuth2Client{
		ClientID:          "x",
		ClientSecretEnc:   cipher,
		TokenTTLSeconds:   60,
		RefreshTTLSeconds: 86400,
	}
	stored := &db.OAuth2AuthorizationCode{
		CodeHash:      HashAuthCode("rawcode"),
		ClientID:      "x",
		UserEmail:     "alice@example.com",
		RedirectURI:   "https://x/cb",
		CodeChallenge: challenge,
		ExpiresAt:     time.Now().Add(5 * time.Minute),
	}

	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:    &fakeClientRepo{c: cli},
		AuthCodeRepo:  &fakeConsumeAuthCode{stored: stored},
		RefreshRepo:   &fakeRefreshSink{},
		Decrypt:       func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:     "s",
		Issuer:        "https://account.test",
	})

	form := url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {"rawcode"},
		"redirect_uri":  {"https://x/cb"},
		"code_verifier": {verifier},
	}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plainSecret)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["token_type"] != "Bearer" {
		t.Errorf("token_type=%v", body["token_type"])
	}
	if body["access_token"].(string) == "" {
		t.Error("missing access_token")
	}
	if body["refresh_token"].(string) == "" {
		t.Error("missing refresh_token")
	}
	if body["expires_in"].(float64) != 60 {
		t.Errorf("expires_in=%v", body["expires_in"])
	}
}

func TestToken_AuthCodeGrant_PKCEMismatch(t *testing.T) {
	_, challenge := makeVerifierAndChallenge()
	plainSecret := "s"
	cipher := []byte("ENC:" + plainSecret)
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: cipher, TokenTTLSeconds: 60}
	stored := &db.OAuth2AuthorizationCode{
		CodeHash:      HashAuthCode("rawcode"),
		ClientID:      "x",
		RedirectURI:   "https://x/cb",
		CodeChallenge: challenge,
		ExpiresAt:     time.Now().Add(5 * time.Minute),
	}
	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeConsumeAuthCode{stored: stored},
		RefreshRepo:  &fakeRefreshSink{},
		Decrypt:      func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:    "s",
		Issuer:       "https://account.test",
	})
	form := url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {"rawcode"},
		"redirect_uri":  {"https://x/cb"},
		"code_verifier": {"WRONG-VERIFIER"},
	}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plainSecret)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("Code=%d", w.Code)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type AuthCodeConsumer interface {
	ConsumeUnused(hash string) (*db.OAuth2AuthorizationCode, error)
}

type RefreshSink interface {
	Create(t *db.OAuth2RefreshToken) error
}

type RefreshRotator interface {
	Rotate(oldHash, newHash string) (*db.OAuth2RefreshToken, error)
	FindByHash(hash string) (*db.OAuth2RefreshToken, error)
}

type DecryptFunc func([]byte) ([]byte, error)

type TokenEndpointDeps struct {
	ClientRepo     ClientRepo
	AuthCodeRepo   AuthCodeConsumer
	RefreshRepo    RefreshSink
	RefreshRotator RefreshRotator
	Decrypt        DecryptFunc
	JWTSecret      string
	Issuer         string
}

type TokenEndpoint struct {
	deps TokenEndpointDeps
}

func NewTokenEndpoint(d TokenEndpointDeps) *TokenEndpoint {
	return &TokenEndpoint{deps: d}
}

func (t *TokenEndpoint) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	_ = r.ParseForm()
	switch r.FormValue("grant_type") {
	case "authorization_code":
		t.handleAuthCode(w, r)
	case "refresh_token":
		t.handleRefresh(w, r)
	default:
		writeOAuthErr(w, http.StatusBadRequest, "unsupported_grant_type", "")
	}
}

func (t *TokenEndpoint) handleAuthCode(w http.ResponseWriter, r *http.Request) {
	clientID, secret, ok := extractClientAuth(r)
	if !ok {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "missing client credentials")
		return
	}
	cli, err := t.deps.ClientRepo.GetByClientID(clientID)
	if err != nil || !t.checkSecret(cli, secret) {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "bad credentials")
		return
	}

	rawCode := r.FormValue("code")
	verifier := r.FormValue("code_verifier")
	redirect := r.FormValue("redirect_uri")
	if rawCode == "" || verifier == "" {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "missing fields")
		return
	}
	stored, err := t.deps.AuthCodeRepo.ConsumeUnused(HashAuthCode(rawCode))
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "code invalid or used")
		return
	}
	if stored.ClientID != clientID {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "client mismatch")
		return
	}
	if stored.RedirectURI != redirect {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "redirect_uri mismatch")
		return
	}
	if !VerifyPKCES256(verifier, stored.CodeChallenge) {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "PKCE mismatch")
		return
	}

	sid := uuid.New().String()
	mappings := ""
	if cli.ClaimMappings != nil {
		mappings = *cli.ClaimMappings
	}
	custom := ApplyClaimMappings(mappings, UserClaimSource{
		Email:       stored.UserEmail,
		DisplayName: "",
		IsAdmin:     false,
	})

	tokenTTL := cli.TokenTTLSeconds
	if tokenTTL <= 0 {
		tokenTTL = 60
	}
	refreshTTL := cli.RefreshTTLSeconds
	if refreshTTL <= 0 {
		refreshTTL = 2592000
	}

	claims := auth.Claims{
		Sub:    stored.UserEmail,
		Email:  stored.UserEmail,
		Aud:    cli.ClientID,
		Iss:    t.deps.Issuer,
		Sid:    sid,
		Iat:    time.Now().Unix(),
		Exp:    time.Now().Add(time.Duration(tokenTTL) * time.Second).Unix(),
		Custom: custom,
	}
	access, err := auth.SignJWT(t.deps.JWTSecret, claims)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "sign failed")
		return
	}

	rawRef, refHash, err := GenerateAuthCode() // reuse the random generator
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
		return
	}
	if err := t.deps.RefreshRepo.Create(&db.OAuth2RefreshToken{
		ID:        uuid.New().String(),
		TokenHash: refHash,
		SID:       sid,
		ClientID:  cli.ClientID,
		UserEmail: stored.UserEmail,
		ExpiresAt: time.Now().Add(time.Duration(refreshTTL) * time.Second),
	}); err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "refresh persist failed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"access_token":  access,
		"token_type":    "Bearer",
		"expires_in":    tokenTTL,
		"refresh_token": rawRef,
		"scope":         stored.Scope,
	})
}

func (t *TokenEndpoint) checkSecret(c *db.OAuth2Client, presented string) bool {
	if c == nil || t.deps.Decrypt == nil {
		return false
	}
	plain, err := t.deps.Decrypt(c.ClientSecretEnc)
	if err != nil {
		return false
	}
	return subtle.ConstantTimeCompare(plain, []byte(presented)) == 1
}

func extractClientAuth(r *http.Request) (clientID, secret string, ok bool) {
	if user, pass, basicOK := r.BasicAuth(); basicOK {
		return user, pass, true
	}
	id := r.FormValue("client_id")
	sec := r.FormValue("client_secret")
	if id == "" || sec == "" {
		return "", "", false
	}
	return id, sec, true
}

// HashRefreshToken is the canonical hash for refresh tokens, used by both the
// repo and the introspection endpoint.
func HashRefreshToken(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

// errInvalidGrant is reserved for non-public matching against repo errors.
var errInvalidGrant = errors.New("invalid_grant")

// shut up unused imports when handleRefresh isn't yet wired in this task
var _ = strings.TrimPrefix
var _ = base64.StdEncoding
```

> **Note:** `handleRefresh` is implemented in Task 29.

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS for the auth_code path; refresh path will be added next.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/token_endpoint.go internal/authserver/token_authcode_test.go
git commit -m "feat(account-service-backend): /token authorization_code grant / Grant authorization_code"
```

---

### Task 29: `/token` — refresh_token grant + rotation + reuse detection

**Files:**
- Modify: `internal/authserver/token_endpoint.go`
- Test: `internal/authserver/token_refresh_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

type fakeRotator struct {
	rows  map[string]*db.OAuth2RefreshToken
	calls int
}

func (f *fakeRotator) FindByHash(h string) (*db.OAuth2RefreshToken, error) {
	if r, ok := f.rows[h]; ok {
		return r, nil
	}
	return nil, fakeNotFound{}
}

func (f *fakeRotator) Rotate(oldHash, newHash string) (*db.OAuth2RefreshToken, error) {
	f.calls++
	old, ok := f.rows[oldHash]
	if !ok {
		return nil, fakeNotFound{}
	}
	if old.Revoked {
		// emulate reuse-detection branch
		for _, r := range f.rows {
			if r.SID == old.SID {
				r.Revoked = true
			}
		}
		return nil, fakeNotFound{}
	}
	old.Revoked = true
	newRow := &db.OAuth2RefreshToken{
		TokenHash: newHash,
		SID:       old.SID,
		ClientID:  old.ClientID,
		UserEmail: old.UserEmail,
		ExpiresAt: old.ExpiresAt,
	}
	f.rows[newHash] = newRow
	return newRow, nil
}

func TestToken_Refresh_Success(t *testing.T) {
	plain := "s"
	cipher := []byte("ENC:" + plain)
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: cipher, TokenTTLSeconds: 60}

	old := &db.OAuth2RefreshToken{
		TokenHash: HashRefreshToken("oldraw"),
		SID:       "sid1",
		ClientID:  "x",
		UserEmail: "a@x",
		ExpiresAt: time.Now().Add(time.Hour),
	}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{old.TokenHash: old}}

	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:     &fakeClientRepo{c: cli},
		RefreshRepo:    &fakeRefreshSink{}, // not used on refresh path; rotator handles inserts
		RefreshRotator: rot,
		Decrypt:        func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:      "s",
		Issuer:         "https://account.test",
	})

	form := url.Values{
		"grant_type":    {"refresh_token"},
		"refresh_token": {"oldraw"},
	}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["refresh_token"].(string) == "oldraw" {
		t.Fatal("refresh did not rotate")
	}
	if rot.calls != 1 {
		t.Fatalf("rotator calls=%d", rot.calls)
	}
}

func TestToken_Refresh_ReuseAttack(t *testing.T) {
	plain := "s"
	cipher := []byte("ENC:" + plain)
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: cipher, TokenTTLSeconds: 60}
	old := &db.OAuth2RefreshToken{
		TokenHash: HashRefreshToken("raw"),
		SID:       "sid1",
		ClientID:  "x",
		UserEmail: "a@x",
		ExpiresAt: time.Now().Add(time.Hour),
		Revoked:   true, // already rotated/revoked
	}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{old.TokenHash: old}}

	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:     &fakeClientRepo{c: cli},
		RefreshRepo:    &fakeRefreshSink{},
		RefreshRotator: rot,
		Decrypt:        func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:      "s",
		Issuer:         "https://account.test",
	})
	form := url.Values{"grant_type": {"refresh_token"}, "refresh_token": {"raw"}}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("Code=%d", w.Code)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Add the refresh handler to `token_endpoint.go`**

```go
func (t *TokenEndpoint) handleRefresh(w http.ResponseWriter, r *http.Request) {
	clientID, secret, ok := extractClientAuth(r)
	if !ok {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "missing client credentials")
		return
	}
	cli, err := t.deps.ClientRepo.GetByClientID(clientID)
	if err != nil || !t.checkSecret(cli, secret) {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "bad credentials")
		return
	}
	raw := r.FormValue("refresh_token")
	if raw == "" {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "missing refresh_token")
		return
	}
	oldHash := HashRefreshToken(raw)
	newRaw, newHash, err := GenerateAuthCode()
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
		return
	}
	rotated, err := t.deps.RefreshRotator.Rotate(oldHash, newHash)
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "refresh invalid")
		return
	}
	if rotated.ClientID != clientID {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "client mismatch")
		return
	}
	tokenTTL := cli.TokenTTLSeconds
	if tokenTTL <= 0 {
		tokenTTL = 60
	}
	mappings := ""
	if cli.ClaimMappings != nil {
		mappings = *cli.ClaimMappings
	}
	custom := ApplyClaimMappings(mappings, UserClaimSource{Email: rotated.UserEmail})
	claims := auth.Claims{
		Sub:    rotated.UserEmail,
		Email:  rotated.UserEmail,
		Aud:    cli.ClientID,
		Iss:    t.deps.Issuer,
		Sid:    rotated.SID,
		Iat:    time.Now().Unix(),
		Exp:    time.Now().Add(time.Duration(tokenTTL) * time.Second).Unix(),
		Custom: custom,
	}
	access, err := auth.SignJWT(t.deps.JWTSecret, claims)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "sign failed")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"access_token":  access,
		"token_type":    "Bearer",
		"expires_in":    tokenTTL,
		"refresh_token": newRaw,
	})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS for both refresh test cases.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/token_endpoint.go internal/authserver/token_refresh_test.go
git commit -m "feat(account-service-backend): /token refresh grant with rotation + reuse detection / Grant refresh_token avec rotation"
```

---

### Task 30: `/token/revoke` and `/introspect`

**Files:**
- Create: `internal/authserver/introspect.go`
- Test: `internal/authserver/introspect_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type fakeRevoke struct {
	revoked map[string]bool
}

func (f *fakeRevoke) RevokeBySID(sid, reason string) error {
	if f.revoked == nil {
		f.revoked = map[string]bool{}
	}
	f.revoked[sid] = true
	return nil
}

func TestRevoke_RemovesChainBySID(t *testing.T) {
	plain := "s"
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: []byte("ENC:" + plain)}
	row := &db.OAuth2RefreshToken{TokenHash: HashRefreshToken("raw"), SID: "sid1", ClientID: "x"}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{row.TokenHash: row}}
	rev := &fakeRevoke{}

	h := NewRevokeHandler(RevokeDeps{
		ClientRepo:  &fakeClientRepo{c: cli},
		Rotator:     rot,
		Revoker:     rev,
		Decrypt:     func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
	})
	form := url.Values{"token": {"raw"}, "token_type_hint": {"refresh_token"}}
	r := httptest.NewRequest(http.MethodPost, "/token/revoke", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	if !rev.revoked["sid1"] {
		t.Fatal("sid1 not revoked")
	}
}

func TestIntrospect_ActiveJWT(t *testing.T) {
	tok, _ := auth.SignJWT("s", auth.Claims{
		Sub: "alice@x", Aud: "x", Iss: "https://account.test", Sid: "sid1",
		Exp: time.Now().Add(60 * time.Second).Unix(), Iat: time.Now().Unix(),
	})
	plain := "secret"
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: []byte("ENC:" + plain)}
	row := &db.OAuth2RefreshToken{SID: "sid1", Revoked: false}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{"placeholder": row}}

	h := NewIntrospectHandler(IntrospectDeps{
		ClientRepo:    &fakeClientRepo{c: cli},
		Rotator:       rot,
		Decrypt:       func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:     "s",
		Issuer:        "https://account.test",
		Audience:      "x",
	})
	form := url.Values{"token": {tok}}
	r := httptest.NewRequest(http.MethodPost, "/introspect", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["active"] != true {
		t.Fatalf("active=%v body=%v", body["active"], body)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
// File: internal/authserver/introspect.go
package authserver

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type Revoker interface {
	RevokeBySID(sid, reason string) error
}

type RevokeDeps struct {
	ClientRepo ClientRepo
	Rotator    RefreshRotator
	Revoker    Revoker
	Decrypt    DecryptFunc
}

func NewRevokeHandler(d RevokeDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		_ = r.ParseForm()
		clientID, secret, ok := extractClientAuth(r)
		cli, err := d.ClientRepo.GetByClientID(clientID)
		if !ok || err != nil {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		plain, err := d.Decrypt(cli.ClientSecretEnc)
		if err != nil || subtle.ConstantTimeCompare(plain, []byte(secret)) != 1 {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		raw := r.FormValue("token")
		row, err := d.Rotator.FindByHash(HashRefreshToken(raw))
		if err == nil {
			_ = d.Revoker.RevokeBySID(row.SID, "user_logout")
		}
		// RFC 7009: always 200 OK
		w.WriteHeader(http.StatusOK)
	})
}

type IntrospectDeps struct {
	ClientRepo ClientRepo
	Rotator    RefreshRotator
	Decrypt    DecryptFunc
	JWTSecret  string
	Issuer     string
	Audience   string
}

func NewIntrospectHandler(d IntrospectDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		_ = r.ParseForm()
		clientID, secret, ok := extractClientAuth(r)
		cli, err := d.ClientRepo.GetByClientID(clientID)
		if !ok || err != nil {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		plain, err := d.Decrypt(cli.ClientSecretEnc)
		if err != nil || subtle.ConstantTimeCompare(plain, []byte(secret)) != 1 {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		tok := r.FormValue("token")
		claims, err := auth.ValidateJWT(tok, d.JWTSecret, d.Audience)
		if err != nil {
			respondInactive(w)
			return
		}
		// Look up sid in refresh store (if revoked → inactive)
		if claims.Sid != "" {
			rows, err := listRowsBySID(d.Rotator, claims.Sid)
			if err == nil && allRevoked(rows) {
				respondInactive(w)
				return
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"active": true,
			"sub":    claims.Sub,
			"sid":    claims.Sid,
			"exp":    claims.Exp,
			"iat":    claims.Iat,
			"aud":    claims.Aud,
			"iss":    claims.Iss,
		})
	})
}

func respondInactive(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"active": false})
}

func listRowsBySID(rot RefreshRotator, sid string) ([]*db.OAuth2RefreshToken, error) {
	// Quick adapter: walk a single FindByHash isn't possible by sid, so fall back
	// to a small interface upgrade if available, else return an empty slice and
	// trust the JWT exp.
	if lister, ok := rot.(interface {
		ListBySID(string) ([]db.OAuth2RefreshToken, error)
	}); ok {
		rows, err := lister.ListBySID(sid)
		if err != nil {
			return nil, err
		}
		out := make([]*db.OAuth2RefreshToken, len(rows))
		for i := range rows {
			out[i] = &rows[i]
		}
		return out, nil
	}
	return nil, errors.New("no lister")
}

func allRevoked(rows []*db.OAuth2RefreshToken) bool {
	if len(rows) == 0 {
		return false
	}
	for _, r := range rows {
		if !r.Revoked {
			return false
		}
	}
	return true
}
```

> **Note:** `RefreshRepo` (Task 14) already implements `ListBySID`; main.go in Task 38 will pass the same instance as `Rotator` in `IntrospectDeps`, so the type assertion above succeeds in production. The fake test rotator implements only `FindByHash`/`Rotate`, so the introspect path treats sid lookup as best-effort and trusts the JWT signature for the test.

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/introspect.go internal/authserver/introspect_test.go
git commit -m "feat(account-service-backend): /token/revoke and /introspect / Endpoints de révocation et d'introspection"
```

---

### Task 31: `/register` (RFC 7591, admin-gated)

**Files:**
- Create: `internal/authserver/register.go`
- Test: `internal/authserver/register_test.go`

- [ ] **Step 1: Failing test**

```go
package authserver

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeClientCreator struct {
	created *db.OAuth2Client
}

func (f *fakeClientCreator) Create(c *db.OAuth2Client) error {
	c.ID = "id-1"
	f.created = c
	return nil
}

func TestRegister_CreatesClientReturnsSecretOnce(t *testing.T) {
	c := &fakeClientCreator{}
	h := NewRegisterHandler(RegisterDeps{
		Creator: c,
		Encrypt: func(plain []byte) ([]byte, error) { return append([]byte("ENC:"), plain...), nil },
	})
	body, _ := json.Marshal(map[string]interface{}{
		"client_name":   "Example",
		"redirect_uris": []string{"https://x/cb"},
	})
	r := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusCreated {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["client_id"] == "" || got["client_secret"] == "" {
		t.Fatalf("missing client_id/secret: %v", got)
	}
	if c.created.Name != "Example" {
		t.Errorf("Name=%q", c.created.Name)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/authserver/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package authserver

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type ClientCreator interface {
	Create(c *db.OAuth2Client) error
}

type EncryptFunc func([]byte) ([]byte, error)

type RegisterDeps struct {
	Creator ClientCreator
	Encrypt EncryptFunc
}

type registerRequest struct {
	ClientName       string   `json:"client_name"`
	RedirectURIs     []string `json:"redirect_uris"`
	LogoutWebhookURL string   `json:"logout_webhook_url,omitempty"`
}

func NewRegisterHandler(d RegisterDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body registerRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", err.Error())
			return
		}
		if body.ClientName == "" || len(body.RedirectURIs) == 0 {
			writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "client_name and redirect_uris required")
			return
		}
		clientID, _, err := newRandomB64(24)
		if err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
			return
		}
		_, secret, err := newRandomB64(32)
		if err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
			return
		}
		enc, err := d.Encrypt([]byte(secret))
		if err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "encrypt failed")
			return
		}
		urisJSON, _ := json.Marshal(body.RedirectURIs)
		urisStr := string(urisJSON)
		c := &db.OAuth2Client{
			ClientID:          clientID,
			ClientSecretEnc:   enc,
			Name:              body.ClientName,
			RedirectURIs:      &urisStr,
			LogoutWebhookURL:  body.LogoutWebhookURL,
			TokenTTLSeconds:   60,
			RefreshTTLSeconds: 2592000,
			IsActive:          true,
		}
		if err := d.Creator.Create(c); err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "create failed")
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"client_id":     clientID,
			"client_secret": secret,
			"client_name":   c.Name,
			"redirect_uris": body.RedirectURIs,
		})
	})
}

func newRandomB64(n int) (raw, b64 string, err error) {
	buf := make([]byte, n)
	if _, err := io.ReadFull(rand.Reader, buf); err != nil {
		return "", "", err
	}
	enc := base64.RawURLEncoding.EncodeToString(buf)
	return enc, enc, nil
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/authserver/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/authserver/register.go internal/authserver/register_test.go
git commit -m "feat(account-service-backend): RFC 7591 dynamic client registration / Inscription dynamique de clients"
```

---

## Phase 5 — Logout Broadcaster

### Task 32: HMAC-SHA256 webhook signer

**Files:**
- Create: `internal/logout/sign.go`
- Test: `internal/logout/sign_test.go`

- [ ] **Step 1: Failing test**

```go
package logout

import (
	"strings"
	"testing"
)

func TestSignWebhook_DeterministicAndVerifiable(t *testing.T) {
	body := []byte(`{"sub":"a@x"}`)
	secret := "the-client-secret"
	sig1 := SignWebhook(secret, body)
	sig2 := SignWebhook(secret, body)
	if sig1 != sig2 {
		t.Fatal("signature should be deterministic")
	}
	if !strings.HasPrefix(sig1, "sha256=") {
		t.Fatalf("prefix: %q", sig1)
	}
	if !VerifyWebhook(secret, body, sig1) {
		t.Fatal("VerifyWebhook should accept its own output")
	}
	if VerifyWebhook("wrong", body, sig1) {
		t.Fatal("VerifyWebhook accepted wrong secret")
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/logout/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package logout

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

func SignWebhook(secret string, body []byte) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(body)
	return "sha256=" + hex.EncodeToString(h.Sum(nil))
}

func VerifyWebhook(secret string, body []byte, sig string) bool {
	want := SignWebhook(secret, body)
	if !strings.EqualFold(want[:7], sig[:min(7, len(sig))]) {
		return false
	}
	return hmac.Equal([]byte(want), []byte(sig))
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/logout/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/logout/sign.go internal/logout/sign_test.go
git commit -m "feat(account-service-backend): add HMAC webhook signer / Ajout du signataire HMAC"
```

---

### Task 33: Webhook delivery (single-shot, with retries)

**Files:**
- Create: `internal/logout/broadcaster.go`
- Test: `internal/logout/broadcaster_test.go`

- [ ] **Step 1: Failing test**

```go
package logout

import (
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestDeliver_Success(t *testing.T) {
	var received int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Logout-Signature") == "" {
			t.Error("missing signature header")
		}
		atomic.AddInt32(&received, 1)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	d := NewDeliverer(DelivererConfig{Timeout: 2 * time.Second, MaxAttempts: 3})
	res := d.Deliver(srv.URL, "secret", []byte(`{"sub":"a@x"}`))
	if !res.Sent {
		t.Fatalf("Sent=false attempts=%d err=%s", res.Attempts, res.LastError)
	}
	if got := atomic.LoadInt32(&received); got != 1 {
		t.Errorf("received=%d", got)
	}
}

func TestDeliver_RetriesOn5xx(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&hits, 1)
		if n < 3 {
			http.Error(w, "boom", http.StatusBadGateway)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	d := NewDeliverer(DelivererConfig{Timeout: 2 * time.Second, MaxAttempts: 3, BackoffBase: 1 * time.Millisecond})
	res := d.Deliver(srv.URL, "secret", []byte(`{}`))
	if !res.Sent {
		t.Fatalf("Sent=false attempts=%d", res.Attempts)
	}
	if res.Attempts != 3 {
		t.Errorf("Attempts=%d want 3", res.Attempts)
	}
}

func TestDeliver_GivesUpAfterMax(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()
	d := NewDeliverer(DelivererConfig{Timeout: 2 * time.Second, MaxAttempts: 2, BackoffBase: 1 * time.Millisecond})
	res := d.Deliver(srv.URL, "secret", []byte(`{}`))
	if res.Sent {
		t.Fatal("expected Sent=false")
	}
	if res.Attempts != 2 {
		t.Errorf("Attempts=%d", res.Attempts)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/logout/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package logout

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"time"
)

type DelivererConfig struct {
	Timeout     time.Duration
	MaxAttempts int
	BackoffBase time.Duration // first retry waits BackoffBase, doubled each time
}

type Deliverer struct {
	cfg DelivererConfig
	cli *http.Client
}

type DeliveryResult struct {
	Sent      bool
	Attempts  int
	LastError string
}

func NewDeliverer(cfg DelivererConfig) *Deliverer {
	if cfg.Timeout == 0 {
		cfg.Timeout = 5 * time.Second
	}
	if cfg.MaxAttempts == 0 {
		cfg.MaxAttempts = 3
	}
	if cfg.BackoffBase == 0 {
		cfg.BackoffBase = 1 * time.Second
	}
	return &Deliverer{
		cfg: cfg,
		cli: &http.Client{Timeout: cfg.Timeout},
	}
}

func (d *Deliverer) Deliver(url, secret string, body []byte) DeliveryResult {
	res := DeliveryResult{}
	wait := d.cfg.BackoffBase
	for attempt := 1; attempt <= d.cfg.MaxAttempts; attempt++ {
		res.Attempts = attempt
		req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			res.LastError = err.Error()
			return res
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Logout-Signature", SignWebhook(secret, body))
		resp, err := d.cli.Do(req)
		if err != nil {
			res.LastError = err.Error()
		} else {
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				res.Sent = true
				return res
			}
			res.LastError = fmt.Sprintf("HTTP %d", resp.StatusCode)
			if resp.StatusCode >= 400 && resp.StatusCode < 500 {
				return res // 4xx => non-retryable
			}
		}
		if attempt < d.cfg.MaxAttempts {
			time.Sleep(wait)
			wait *= 2
		}
	}
	return res
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/logout/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/logout/broadcaster.go internal/logout/broadcaster_test.go
git commit -m "feat(account-service-backend): add webhook deliverer with retries / Livraison de webhook avec retry"
```

---

### Task 34: Worker pool (queue + persisted retry)

**Files:**
- Create: `internal/logout/queue.go`
- Test: `internal/logout/queue_test.go`

- [ ] **Step 1: Failing test**

```go
package logout

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

type fakeRepo struct {
	mu      sync.Mutex
	created []db.LogoutEvent
	sent    map[string]bool
	failed  map[string]string
}

func (f *fakeRepo) Create(e *db.LogoutEvent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.created = append(f.created, *e)
	return nil
}
func (f *fakeRepo) MarkSent(id string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.sent == nil {
		f.sent = map[string]bool{}
	}
	f.sent[id] = true
	return nil
}
func (f *fakeRepo) MarkFailed(id, errMsg string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failed == nil {
		f.failed = map[string]string{}
	}
	f.failed[id] = errMsg
	return nil
}

type fakeDeliverer struct {
	calls int32
	ok    bool
}

func (f *fakeDeliverer) Deliver(url, secret string, body []byte) DeliveryResult {
	atomic.AddInt32(&f.calls, 1)
	return DeliveryResult{Sent: f.ok, Attempts: 1, LastError: "x"}
}

func TestWorkerPool_DispatchesAndMarks(t *testing.T) {
	repo := &fakeRepo{}
	deliv := &fakeDeliverer{ok: true}
	pool := NewWorkerPool(WorkerConfig{
		Workers:    2,
		BufferSize: 10,
		Deliverer:  deliv,
		Repo:       repo,
	})
	ctx, cancel := context.WithCancel(context.Background())
	pool.Start(ctx)

	for i := 0; i < 5; i++ {
		pool.Enqueue(LogoutJob{
			ID:           "id-" + string(rune('a'+i)),
			ClientID:     "x",
			UserEmail:    "a@x",
			SID:          "sid",
			WebhookURL:   "https://x",
			ClientSecret: "secret",
			Body:         []byte(`{}`),
		})
	}

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		repo.mu.Lock()
		ok := len(repo.sent) == 5
		repo.mu.Unlock()
		if ok {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	cancel()
	pool.Wait()
	if int(deliv.calls) != 5 {
		t.Fatalf("calls=%d", deliv.calls)
	}
	if len(repo.sent) != 5 {
		t.Fatalf("sent=%d", len(repo.sent))
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/logout/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package logout

import (
	"context"
	"sync"

	"github.com/hellopro/account-service/internal/db"
)

type EventRepo interface {
	Create(e *db.LogoutEvent) error
	MarkSent(id string) error
	MarkFailed(id, errMsg string) error
}

type Sender interface {
	Deliver(url, secret string, body []byte) DeliveryResult
}

type LogoutJob struct {
	ID           string
	ClientID     string
	UserEmail    string
	SID          string
	WebhookURL   string
	ClientSecret string
	Body         []byte
}

type WorkerConfig struct {
	Workers    int
	BufferSize int
	Deliverer  Sender
	Repo       EventRepo
}

type WorkerPool struct {
	cfg  WorkerConfig
	ch   chan LogoutJob
	wg   sync.WaitGroup
}

func NewWorkerPool(cfg WorkerConfig) *WorkerPool {
	if cfg.Workers == 0 {
		cfg.Workers = 4
	}
	if cfg.BufferSize == 0 {
		cfg.BufferSize = 256
	}
	return &WorkerPool{cfg: cfg, ch: make(chan LogoutJob, cfg.BufferSize)}
}

func (p *WorkerPool) Start(ctx context.Context) {
	for i := 0; i < p.cfg.Workers; i++ {
		p.wg.Add(1)
		go p.run(ctx)
	}
}

func (p *WorkerPool) run(ctx context.Context) {
	defer p.wg.Done()
	for {
		select {
		case <-ctx.Done():
			return
		case job, ok := <-p.ch:
			if !ok {
				return
			}
			res := p.cfg.Deliverer.Deliver(job.WebhookURL, job.ClientSecret, job.Body)
			if res.Sent {
				_ = p.cfg.Repo.MarkSent(job.ID)
			} else {
				_ = p.cfg.Repo.MarkFailed(job.ID, res.LastError)
			}
		}
	}
}

// Enqueue is non-blocking: drops the job if the buffer is full and logs a
// warning. The caller still has the persisted logout_events row to retry from.
func (p *WorkerPool) Enqueue(j LogoutJob) bool {
	select {
	case p.ch <- j:
		return true
	default:
		return false
	}
}

func (p *WorkerPool) Wait() {
	p.wg.Wait()
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/logout/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/logout/queue.go internal/logout/queue_test.go
git commit -m "feat(account-service-backend): add logout worker pool / Ajout du pool de workers de déconnexion"
```

---

### Task 35: Logout broadcast helper (DB write + enqueue)

**Files:**
- Create: `internal/logout/broadcast.go`
- Test: `internal/logout/broadcast_test.go`

- [ ] **Step 1: Failing test**

```go
package logout

import (
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

type captureRepo struct {
	mu       sync.Mutex
	created  []db.LogoutEvent
}

func (c *captureRepo) Create(e *db.LogoutEvent) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.created = append(c.created, *e)
	return nil
}
func (c *captureRepo) MarkSent(id string) error                  { return nil }
func (c *captureRepo) MarkFailed(id, errMsg string) error        { return nil }

type fakeDecrypter struct{}

func (fakeDecrypter) Decrypt(in []byte) ([]byte, error) {
	return []byte(strings.TrimPrefix(string(in), "ENC:")), nil
}

type capturePool struct {
	mu   sync.Mutex
	jobs []LogoutJob
}

func (c *capturePool) Enqueue(j LogoutJob) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.jobs = append(c.jobs, j)
	return true
}

func TestBroadcastSendsToActiveClients(t *testing.T) {
	repo := &captureRepo{}
	pool := &capturePool{}

	clients := []db.OAuth2Client{
		{ClientID: "x1", ClientSecretEnc: []byte("ENC:s1"), LogoutWebhookURL: "https://x1/lo"},
		{ClientID: "x2", ClientSecretEnc: []byte("ENC:s2"), LogoutWebhookURL: ""}, // no webhook
		{ClientID: "x3", ClientSecretEnc: []byte("ENC:s3"), LogoutWebhookURL: "https://x3/lo"},
	}
	b := NewBroadcaster(BroadcasterDeps{
		Decrypter: fakeDecrypter{},
		Repo:      repo,
		Pool:      pool,
		Issuer:    "https://account.test",
	})
	b.Broadcast("a@x", "sid1", clients)

	if len(pool.jobs) != 2 {
		t.Fatalf("jobs=%d (want 2 active webhooks)", len(pool.jobs))
	}
	if len(repo.created) != 2 {
		t.Fatalf("logout_events=%d", len(repo.created))
	}
	for _, j := range pool.jobs {
		var body map[string]interface{}
		_ = json.Unmarshal(j.Body, &body)
		if body["sub"] != "a@x" {
			t.Errorf("sub=%v", body["sub"])
		}
		if body["sid"] != "sid1" {
			t.Errorf("sid=%v", body["sid"])
		}
		iat, _ := body["iat"].(float64)
		if int64(iat) > time.Now().Unix() {
			t.Errorf("iat in future")
		}
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/logout/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package logout

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
)

type Decrypter interface {
	Decrypt(in []byte) ([]byte, error)
}

type Enqueuer interface {
	Enqueue(LogoutJob) bool
}

type BroadcasterDeps struct {
	Decrypter Decrypter
	Repo      EventRepo
	Pool      Enqueuer
	Issuer    string
}

type Broadcaster struct {
	deps BroadcasterDeps
}

func NewBroadcaster(d BroadcasterDeps) *Broadcaster {
	return &Broadcaster{deps: d}
}

// Broadcast sends a back-channel logout event to every client in the slice
// that has a non-empty logout_webhook_url. Each gets its own logout_events row
// (persistence) and is enqueued onto the worker pool (delivery).
func (b *Broadcaster) Broadcast(userEmail, sid string, clients []db.OAuth2Client) {
	body := map[string]interface{}{
		"iss":    b.deps.Issuer,
		"sub":    userEmail,
		"sid":    sid,
		"iat":    time.Now().Unix(),
		"events": map[string]interface{}{"http://schemas.openid.net/event/backchannel-logout": map[string]interface{}{}},
	}
	bytes, _ := json.Marshal(body)

	for _, c := range clients {
		if c.LogoutWebhookURL == "" {
			continue
		}
		secret, err := b.deps.Decrypter.Decrypt(c.ClientSecretEnc)
		if err != nil {
			continue
		}
		ev := &db.LogoutEvent{
			ID:            uuid.New().String(),
			ClientID:      c.ClientID,
			UserEmail:     userEmail,
			SID:           sid,
			WebhookURL:    c.LogoutWebhookURL,
			Status:        "pending",
			NextAttemptAt: time.Now(),
		}
		if err := b.deps.Repo.Create(ev); err != nil {
			continue
		}
		b.deps.Pool.Enqueue(LogoutJob{
			ID:           ev.ID,
			ClientID:     c.ClientID,
			UserEmail:    userEmail,
			SID:          sid,
			WebhookURL:   c.LogoutWebhookURL,
			ClientSecret: string(secret),
			Body:         bytes,
		})
	}
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/logout/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/logout/broadcast.go internal/logout/broadcast_test.go
git commit -m "feat(account-service-backend): add logout broadcast helper / Ajout de l'orchestrateur de diffusion"
```

---

## Phase 6 — Admin REST API

### Task 36: Admin services CRUD handler

**Files:**
- Create: `internal/api/admin_service_handlers.go`
- Test: `internal/api/admin_service_handlers_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeServiceRepo struct {
	clients []db.OAuth2Client
	created *db.OAuth2Client
}

func (f *fakeServiceRepo) Create(c *db.OAuth2Client) error {
	c.ID = "id-1"
	f.created = c
	f.clients = append(f.clients, *c)
	return nil
}
func (f *fakeServiceRepo) GetByID(id string) (*db.OAuth2Client, error) {
	for i := range f.clients {
		if f.clients[i].ID == id {
			return &f.clients[i], nil
		}
	}
	return nil, errNotFound
}
func (f *fakeServiceRepo) GetByClientID(string) (*db.OAuth2Client, error) { return nil, errNotFound }
func (f *fakeServiceRepo) Update(id string, fields map[string]interface{}) error {
	for i := range f.clients {
		if f.clients[i].ID == id {
			if v, ok := fields["name"]; ok {
				f.clients[i].Name = v.(string)
			}
			return nil
		}
	}
	return errNotFound
}
func (f *fakeServiceRepo) Delete(string) error { return nil }
func (f *fakeServiceRepo) List(int, int) ([]db.OAuth2Client, int64, error) {
	return f.clients, int64(len(f.clients)), nil
}

func TestAdminServices_CreateReturnsSecretOnce(t *testing.T) {
	repo := &fakeServiceRepo{}
	h := NewAdminServiceHandler(AdminServiceDeps{
		Repo:    repo,
		Encrypt: func(p []byte) ([]byte, error) { return append([]byte("ENC:"), p...), nil },
	})
	body, _ := json.Marshal(map[string]interface{}{
		"name":          "Example",
		"redirect_uris": []string{"https://x/cb"},
	})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/services", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusCreated {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["client_id"] == "" || got["client_secret"] == "" {
		t.Fatalf("missing fields: %v", got)
	}
}

func TestAdminServices_List(t *testing.T) {
	repo := &fakeServiceRepo{
		clients: []db.OAuth2Client{{ID: "id-1", Name: "Example"}},
	}
	h := NewAdminServiceHandler(AdminServiceDeps{
		Repo:    repo,
		Encrypt: func(p []byte) ([]byte, error) { return p, nil },
	})
	r := httptest.NewRequest(http.MethodGet, "/api/v1/admin/services", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if int(got["total"].(float64)) != 1 {
		t.Errorf("total=%v", got["total"])
	}
}
```

Add to the same test file:

```go
package api

import "errors"

var errNotFound = errors.New("not found")
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package api

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type ServiceRepo interface {
	Create(c *db.OAuth2Client) error
	GetByID(id string) (*db.OAuth2Client, error)
	GetByClientID(id string) (*db.OAuth2Client, error)
	Update(id string, fields map[string]interface{}) error
	Delete(id string) error
	List(limit, offset int) ([]db.OAuth2Client, int64, error)
}

type EncryptFunc func([]byte) ([]byte, error)

type AdminServiceDeps struct {
	Repo    ServiceRepo
	Encrypt EncryptFunc
}

type adminServiceHandler struct {
	deps AdminServiceDeps
}

func NewAdminServiceHandler(d AdminServiceDeps) http.Handler {
	return &adminServiceHandler{deps: d}
}

func (h *adminServiceHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.list(w, r)
	case http.MethodPost:
		h.create(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *adminServiceHandler) list(w http.ResponseWriter, r *http.Request) {
	limit := parseIntParam(r, "limit", 20, 100)
	offset := parseIntParam(r, "offset", 0, 100000)
	clients, total, err := h.deps.Repo.List(limit, offset)
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	out := make([]map[string]interface{}, 0, len(clients))
	for _, c := range clients {
		out = append(out, redactClient(c))
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"items": out, "total": total, "limit": limit, "offset": offset,
	})
}

type createServiceReq struct {
	Name             string            `json:"name"`
	Description      string            `json:"description,omitempty"`
	LogoURL          string            `json:"logo_url,omitempty"`
	BrandColor       string            `json:"brand_color,omitempty"`
	RedirectURIs     []string          `json:"redirect_uris"`
	AllowedRoles     []string          `json:"allowed_roles,omitempty"`
	LogoutWebhookURL string            `json:"logout_webhook_url,omitempty"`
	TokenTTLSeconds  int               `json:"token_ttl_s,omitempty"`
	RefreshTTLSeconds int              `json:"refresh_ttl_s,omitempty"`
	ClaimMappings    map[string]string `json:"claim_mappings,omitempty"`
	Scope            string            `json:"scope,omitempty"`
}

func (h *adminServiceHandler) create(w http.ResponseWriter, r *http.Request) {
	var req createServiceReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	if req.Name == "" || len(req.RedirectURIs) == 0 {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "name and redirect_uris required")
		return
	}
	clientID := randB64(24)
	secret := randB64(32)
	enc, err := h.deps.Encrypt([]byte(secret))
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "encrypt failed")
		return
	}
	urisJSON, _ := json.Marshal(req.RedirectURIs)
	urisStr := string(urisJSON)
	rolesStr := ""
	if len(req.AllowedRoles) > 0 {
		b, _ := json.Marshal(req.AllowedRoles)
		rolesStr = string(b)
	}
	claimStr := ""
	if len(req.ClaimMappings) > 0 {
		b, _ := json.Marshal(req.ClaimMappings)
		claimStr = string(b)
	}
	ttl := req.TokenTTLSeconds
	if ttl == 0 {
		ttl = 60
	}
	rttl := req.RefreshTTLSeconds
	if rttl == 0 {
		rttl = 2592000
	}
	c := &db.OAuth2Client{
		ClientID:          clientID,
		ClientSecretEnc:   enc,
		Name:              req.Name,
		Description:       req.Description,
		LogoURL:           req.LogoURL,
		BrandColor:        req.BrandColor,
		RedirectURIs:      &urisStr,
		AllowedRoles:      ifNonEmpty(rolesStr),
		LogoutWebhookURL:  req.LogoutWebhookURL,
		TokenTTLSeconds:   ttl,
		RefreshTTLSeconds: rttl,
		ClaimMappings:     ifNonEmpty(claimStr),
		Scope:             req.Scope,
		IsActive:          true,
	}
	if err := h.deps.Repo.Create(c); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "create failed")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"id":            c.ID,
		"client_id":     clientID,
		"client_secret": secret, // ONLY time secret is returned
		"name":          c.Name,
		"redirect_uris": req.RedirectURIs,
	})
}

func redactClient(c db.OAuth2Client) map[string]interface{} {
	return map[string]interface{}{
		"id":                  c.ID,
		"client_id":           c.ClientID,
		"name":                c.Name,
		"description":         c.Description,
		"logo_url":            c.LogoURL,
		"brand_color":         c.BrandColor,
		"redirect_uris":       jsonRaw(c.RedirectURIs),
		"allowed_roles":       jsonRaw(c.AllowedRoles),
		"logout_webhook_url":  c.LogoutWebhookURL,
		"token_ttl_s":         c.TokenTTLSeconds,
		"refresh_ttl_s":       c.RefreshTTLSeconds,
		"claim_mappings":      jsonRaw(c.ClaimMappings),
		"scope":               c.Scope,
		"is_active":           c.IsActive,
		"created_at":          c.CreatedAt,
		"updated_at":          c.UpdatedAt,
	}
}

func jsonRaw(s *string) interface{} {
	if s == nil || *s == "" {
		return nil
	}
	var any interface{}
	_ = json.Unmarshal([]byte(*s), &any)
	return any
}

func ifNonEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func parseIntParam(r *http.Request, key string, def, max int) int {
	v := r.URL.Query().Get(key)
	if v == "" {
		return def
	}
	n := 0
	for _, ch := range v {
		if ch < '0' || ch > '9' {
			return def
		}
		n = n*10 + int(ch-'0')
		if n > max {
			return max
		}
	}
	if n == 0 {
		return def
	}
	return n
}

func randB64(n int) string {
	buf := make([]byte, n)
	_, _ = io.ReadFull(rand.Reader, buf)
	return base64.RawURLEncoding.EncodeToString(buf)
}

func writeJSONErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error": errCode, "error_description": desc,
	})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/admin_service_handlers.go internal/api/admin_service_handlers_test.go
git commit -m "feat(account-service-backend): admin services list+create / Liste et création de services"
```

---

### Task 37: Admin services — detail / update / rotate-secret / test-webhook

**Files:**
- Modify: `internal/api/admin_service_handlers.go`
- Test: `internal/api/admin_service_detail_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

func TestAdminServices_RotateSecret(t *testing.T) {
	repo := &fakeServiceRepo{
		clients: []db.OAuth2Client{{ID: "id-1", ClientID: "cli-1", Name: "Example", ClientSecretEnc: []byte("ENC:old")}},
	}
	h := NewAdminServiceDetailHandler(AdminServiceDetailDeps{
		Repo:    repo,
		Encrypt: func(p []byte) ([]byte, error) { return append([]byte("ENC:"), p...), nil },
	})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/services/id-1/rotate-secret", nil)
	r.SetPathValue("id", "id-1")
	r.SetPathValue("op", "rotate-secret")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["client_secret"] == "" {
		t.Fatal("missing client_secret in response")
	}
}

func TestAdminServices_Update(t *testing.T) {
	repo := &fakeServiceRepo{
		clients: []db.OAuth2Client{{ID: "id-1", Name: "Old"}},
	}
	h := NewAdminServiceDetailHandler(AdminServiceDetailDeps{Repo: repo})
	body, _ := json.Marshal(map[string]interface{}{"name": "New"})
	r := httptest.NewRequest(http.MethodPut, "/api/v1/admin/services/id-1", bytes.NewReader(body))
	r.SetPathValue("id", "id-1")
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	if repo.clients[0].Name != "New" {
		t.Fatalf("name=%q", repo.clients[0].Name)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
type AdminServiceDetailDeps struct {
	Repo    ServiceRepo
	Encrypt EncryptFunc
	Tester  WebhookTester
}

type WebhookTester interface {
	TestWebhook(url, secret string) (status int, err error)
}

type adminServiceDetailHandler struct {
	deps AdminServiceDetailDeps
}

func NewAdminServiceDetailHandler(d AdminServiceDetailDeps) http.Handler {
	return &adminServiceDetailHandler{deps: d}
}

func (h *adminServiceDetailHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	op := r.PathValue("op")
	switch r.Method {
	case http.MethodGet:
		h.get(w, id)
	case http.MethodPut:
		h.update(w, r, id)
	case http.MethodDelete:
		h.delete(w, id)
	case http.MethodPost:
		switch op {
		case "rotate-secret":
			h.rotate(w, id)
		case "test-webhook":
			h.testWebhook(w, id)
		default:
			writeJSONErr(w, http.StatusBadRequest, "invalid_request", "unknown op")
		}
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *adminServiceDetailHandler) get(w http.ResponseWriter, id string) {
	c, err := h.deps.Repo.GetByID(id)
	if err != nil {
		writeJSONErr(w, http.StatusNotFound, "not_found", "client not found")
		return
	}
	_ = json.NewEncoder(w).Encode(redactClient(*c))
}

func (h *adminServiceDetailHandler) update(w http.ResponseWriter, r *http.Request, id string) {
	var fields map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&fields); err != nil {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	// Forbid touching id, client_id, client_secret_enc here
	delete(fields, "id")
	delete(fields, "client_id")
	delete(fields, "client_secret_enc")
	// Reshape JSON-ish fields back to JSON strings
	for _, key := range []string{"redirect_uris", "allowed_roles", "claim_mappings"} {
		if v, ok := fields[key]; ok && v != nil {
			b, _ := json.Marshal(v)
			fields[key] = string(b)
		}
	}
	// Map JSON keys to GORM column names
	rename := map[string]string{
		"token_ttl_s":   "token_ttl_seconds",
		"refresh_ttl_s": "refresh_ttl_seconds",
	}
	for jsonKey, col := range rename {
		if v, ok := fields[jsonKey]; ok {
			fields[col] = v
			delete(fields, jsonKey)
		}
	}
	if err := h.deps.Repo.Update(id, fields); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	c, _ := h.deps.Repo.GetByID(id)
	if c != nil {
		_ = json.NewEncoder(w).Encode(redactClient(*c))
	} else {
		w.WriteHeader(http.StatusNoContent)
	}
}

func (h *adminServiceDetailHandler) delete(w http.ResponseWriter, id string) {
	if err := h.deps.Repo.Delete(id); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *adminServiceDetailHandler) rotate(w http.ResponseWriter, id string) {
	secret := randB64(32)
	enc, err := h.deps.Encrypt([]byte(secret))
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "encrypt failed")
		return
	}
	if err := h.deps.Repo.Update(id, map[string]interface{}{"client_secret_enc": enc}); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"client_secret": secret})
}

func (h *adminServiceDetailHandler) testWebhook(w http.ResponseWriter, id string) {
	c, err := h.deps.Repo.GetByID(id)
	if err != nil {
		writeJSONErr(w, http.StatusNotFound, "not_found", "client not found")
		return
	}
	if c.LogoutWebhookURL == "" {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "no webhook configured")
		return
	}
	if h.deps.Tester == nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "no tester wired")
		return
	}
	status, err := h.deps.Tester.TestWebhook(c.LogoutWebhookURL, "")
	if err != nil {
		writeJSONErr(w, http.StatusBadGateway, "webhook_failed", err.Error())
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"status": status})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/admin_service_handlers.go internal/api/admin_service_detail_test.go
git commit -m "feat(account-service-backend): admin service detail/update/rotate/test / Détail et opérations admin sur services"
```

---

### Task 38: Admin users — list / promote / demote / block / unblock / revoke

**Files:**
- Create: `internal/api/admin_user_handlers.go`
- Test: `internal/api/admin_user_handlers_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeUserAdminRepo struct {
	users []db.User
	last  string
}

func (f *fakeUserAdminRepo) List(limit, offset int) ([]db.User, int64, error) {
	return f.users, int64(len(f.users)), nil
}
func (f *fakeUserAdminRepo) FindByEmail(email string) (*db.User, error) {
	for i := range f.users {
		if f.users[i].Email == email {
			return &f.users[i], nil
		}
	}
	return nil, errors.New("not found")
}
func (f *fakeUserAdminRepo) SetAdmin(email string, admin bool) error {
	for i := range f.users {
		if f.users[i].Email == email {
			f.users[i].IsAdmin = admin
			f.last = "admin"
			return nil
		}
	}
	return errors.New("not found")
}
func (f *fakeUserAdminRepo) SetAllowed(email string, ok bool) error {
	for i := range f.users {
		if f.users[i].Email == email {
			f.users[i].IsAllowed = ok
			f.last = "allowed"
			return nil
		}
	}
	return errors.New("not found")
}

type fakeRevokeAll struct {
	called string
}

func (f *fakeRevokeAll) RevokeAllForUser(email, reason string) error {
	f.called = email
	return nil
}

type fakeBroadcast struct {
	users []string
}

func (f *fakeBroadcast) BroadcastForUser(email string) {
	f.users = append(f.users, email)
}

func TestAdminUsers_PromoteDemoteBlockUnblock(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	h := NewAdminUserHandler(AdminUserDeps{
		Repo:        repo,
		RevokeAll:   &fakeRevokeAll{},
		Broadcaster: &fakeBroadcast{},
	})

	cases := []struct {
		op      string
		check   func() bool
		message string
	}{
		{"promote", func() bool { return repo.users[0].IsAdmin }, "promote did not set IsAdmin=true"},
		{"demote", func() bool { return !repo.users[0].IsAdmin }, "demote did not set IsAdmin=false"},
		{"block", func() bool { return !repo.users[0].IsAllowed }, "block did not set IsAllowed=false"},
		{"unblock", func() bool { return repo.users[0].IsAllowed }, "unblock did not set IsAllowed=true"},
	}
	for _, c := range cases {
		r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/"+c.op, nil)
		r.SetPathValue("email", "alice@x")
		r.SetPathValue("op", c.op)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != http.StatusOK {
			t.Fatalf("op=%s Code=%d body=%s", c.op, w.Code, w.Body.String())
		}
		if !c.check() {
			t.Fatalf("op=%s: %s", c.op, c.message)
		}
	}
}

func TestAdminUsers_RevokeAllSessions(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	rev := &fakeRevokeAll{}
	bc := &fakeBroadcast{}
	h := NewAdminUserHandler(AdminUserDeps{
		Repo:        repo,
		RevokeAll:   rev,
		Broadcaster: bc,
	})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/revoke", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "revoke")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	if rev.called != "alice@x" {
		t.Fatal("RevokeAll not called")
	}
	if len(bc.users) != 1 || bc.users[0] != "alice@x" {
		t.Fatalf("broadcast users=%v", bc.users)
	}

	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "revoked" {
		t.Errorf("status=%v", body["status"])
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package api

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type UserAdminRepo interface {
	List(limit, offset int) ([]db.User, int64, error)
	FindByEmail(email string) (*db.User, error)
	SetAdmin(email string, admin bool) error
	SetAllowed(email string, ok bool) error
}

type RevokeAll interface {
	RevokeAllForUser(email, reason string) error
}

type LogoutBroadcaster interface {
	BroadcastForUser(email string)
}

type AdminUserDeps struct {
	Repo        UserAdminRepo
	RevokeAll   RevokeAll
	Broadcaster LogoutBroadcaster
}

func NewAdminUserHandler(d AdminUserDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		op := r.PathValue("op")
		email := r.PathValue("email")
		switch r.Method {
		case http.MethodGet:
			handleListUsers(w, r, d.Repo)
			return
		case http.MethodPost:
			switch op {
			case "promote":
				_ = d.Repo.SetAdmin(email, true)
			case "demote":
				_ = d.Repo.SetAdmin(email, false)
			case "block":
				_ = d.Repo.SetAllowed(email, false)
				_ = d.RevokeAll.RevokeAllForUser(email, "blocked")
				d.Broadcaster.BroadcastForUser(email)
			case "unblock":
				_ = d.Repo.SetAllowed(email, true)
			case "revoke":
				_ = d.RevokeAll.RevokeAllForUser(email, "admin_revoke")
				d.Broadcaster.BroadcastForUser(email)
				_ = json.NewEncoder(w).Encode(map[string]string{"status": "revoked"})
				return
			default:
				writeJSONErr(w, http.StatusBadRequest, "invalid_request", "unknown op")
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
}

func handleListUsers(w http.ResponseWriter, r *http.Request, repo UserAdminRepo) {
	limit := parseIntParam(r, "limit", 20, 100)
	offset := parseIntParam(r, "offset", 0, 100000)
	users, total, err := repo.List(limit, offset)
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	out := make([]map[string]interface{}, 0, len(users))
	for _, u := range users {
		out = append(out, map[string]interface{}{
			"email":         u.Email,
			"display_name":  u.DisplayName,
			"is_admin":      u.IsAdmin,
			"is_allowed":    u.IsAllowed,
			"last_login_at": u.LastLoginAt,
			"created_at":    u.CreatedAt,
		})
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"items": out, "total": total, "limit": limit, "offset": offset,
	})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/admin_user_handlers.go internal/api/admin_user_handlers_test.go
git commit -m "feat(account-service-backend): admin user management / Gestion administrative des utilisateurs"
```

---

### Task 39: Sessions handler (list per user, revoke single sid)

**Files:**
- Modify: `internal/api/admin_user_handlers.go`
- Test: `internal/api/sessions_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeSessionRepo struct {
	rows    []db.OAuth2RefreshToken
	revoked string
}

func (f *fakeSessionRepo) ListByUser(email string) ([]db.OAuth2RefreshToken, error) {
	return f.rows, nil
}
func (f *fakeSessionRepo) ListBySID(string) ([]db.OAuth2RefreshToken, error) { return nil, nil }
func (f *fakeSessionRepo) RevokeBySID(sid, reason string) error {
	f.revoked = sid
	return nil
}

func TestSessions_List(t *testing.T) {
	repo := &fakeSessionRepo{rows: []db.OAuth2RefreshToken{{ID: "x", SID: "sid1"}}}
	h := NewSessionsHandler(SessionsDeps{Repo: repo})
	r := httptest.NewRequest(http.MethodGet, "/api/v1/admin/users/alice@x/sessions", nil)
	r.SetPathValue("email", "alice@x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if int(body["total"].(float64)) != 1 {
		t.Errorf("total=%v", body["total"])
	}
}

func TestSessions_RevokeOne(t *testing.T) {
	repo := &fakeSessionRepo{}
	h := NewSessionsHandler(SessionsDeps{Repo: repo})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/sessions/sid1/revoke", nil)
	r.SetPathValue("sid", "sid1")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	if repo.revoked != "sid1" {
		t.Fatal("not revoked")
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package api

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type SessionRepo interface {
	ListByUser(email string) ([]db.OAuth2RefreshToken, error)
	ListBySID(sid string) ([]db.OAuth2RefreshToken, error)
	RevokeBySID(sid, reason string) error
}

type SessionsDeps struct {
	Repo SessionRepo
}

func NewSessionsHandler(d SessionsDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			email := r.PathValue("email")
			rows, err := d.Repo.ListByUser(email)
			if err != nil {
				writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
				return
			}
			out := make([]map[string]interface{}, 0, len(rows))
			for _, row := range rows {
				out = append(out, map[string]interface{}{
					"id":             row.ID,
					"sid":            row.SID,
					"client_id":      row.ClientID,
					"created_at":     row.CreatedAt,
					"last_used_at":   row.LastUsedAt,
					"expires_at":     row.ExpiresAt,
					"revoked":        row.Revoked,
					"revoked_reason": row.RevokedReason,
				})
			}
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"items": out, "total": len(out),
			})
		case http.MethodPost:
			sid := r.PathValue("sid")
			if err := d.Repo.RevokeBySID(sid, "admin_revoke"); err != nil {
				writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "revoked"})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/admin_user_handlers.go internal/api/sessions_test.go
git commit -m "feat(account-service-backend): list+revoke sessions / Lister et révoquer les sessions"
```

---

### Task 40: Audit log handler

**Files:**
- Create: `internal/api/audit_handlers.go`
- Test: `internal/api/audit_handlers_test.go`

- [ ] **Step 1: Failing test**

```go
package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeAuditRepo struct {
	rows []db.AuditLog
}

func (f *fakeAuditRepo) List(filters map[string]interface{}, limit, offset int) ([]db.AuditLog, int64, error) {
	out := []db.AuditLog{}
	for _, r := range f.rows {
		ev, ok := filters["event"].(string)
		if ok && r.Event != ev {
			continue
		}
		out = append(out, r)
	}
	return out, int64(len(out)), nil
}

func TestAuditList_FiltersByEvent(t *testing.T) {
	repo := &fakeAuditRepo{rows: []db.AuditLog{
		{Event: "login"}, {Event: "logout"}, {Event: "login"},
	}}
	h := NewAuditHandler(AuditDeps{Repo: repo})
	r := httptest.NewRequest(http.MethodGet, "/api/v1/admin/audit?event=login", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if int(body["total"].(float64)) != 2 {
		t.Fatalf("total=%v", body["total"])
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/api/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
package api

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type AuditRepo interface {
	List(filters map[string]interface{}, limit, offset int) ([]db.AuditLog, int64, error)
}

type AuditDeps struct {
	Repo AuditRepo
}

func NewAuditHandler(d AuditDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		filters := map[string]interface{}{}
		for _, k := range []string{"event", "actor_email", "client_id"} {
			if v := r.URL.Query().Get(k); v != "" {
				filters[k] = v
			}
		}
		limit := parseIntParam(r, "limit", 20, 100)
		offset := parseIntParam(r, "offset", 0, 100000)
		rows, total, err := d.Repo.List(filters, limit, offset)
		if err != nil {
			writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
			return
		}
		out := make([]map[string]interface{}, 0, len(rows))
		for _, row := range rows {
			out = append(out, map[string]interface{}{
				"id":           row.ID,
				"event":        row.Event,
				"actor_email":  row.ActorEmail,
				"target_email": row.TargetEmail,
				"client_id":    row.ClientID,
				"ip_addr":      row.IPAddr,
				"user_agent":   row.UserAgent,
				"metadata":     jsonRaw(row.Metadata),
				"created_at":   row.CreatedAt,
			})
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"items": out, "total": total, "limit": limit, "offset": offset,
		})
	})
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/api/...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/api/audit_handlers.go internal/api/audit_handlers_test.go
git commit -m "feat(account-service-backend): audit log handler / Handler du journal d'audit"
```

---

## Phase 7 — Observability + main.go Wiring + Dockerfile + init-db

### Task 41: Health check + Prometheus metrics

**Files:**
- Create: `internal/health/health.go`
- Create: `internal/metrics/metrics.go`
- Test: `internal/health/health_test.go`

- [ ] **Step 1: Failing test**

```go
package health

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

type fakePinger struct {
	ok bool
}

func (f fakePinger) Ping() error {
	if !f.ok {
		return errFake
	}
	return nil
}

var errFake = &fakeErr{}

type fakeErr struct{}

func (*fakeErr) Error() string { return "down" }

func TestHealth_OK(t *testing.T) {
	h := NewHandler("v1", fakePinger{ok: true})
	r := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "ok" {
		t.Errorf("status=%v", body["status"])
	}
	if body["db"] != "ok" {
		t.Errorf("db=%v", body["db"])
	}
}

func TestHealth_DBDown(t *testing.T) {
	h := NewHandler("v1", fakePinger{ok: false})
	r := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("Code=%d", w.Code)
	}
}
```

- [ ] **Step 2: Run failing test**

```bash
go test ./internal/health/...
```
Expected: FAIL.

- [ ] **Step 3: Implement**

```go
// internal/health/health.go
package health

import (
	"encoding/json"
	"net/http"
)

type Pinger interface {
	Ping() error
}

func NewHandler(version string, p Pinger) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dbStatus := "ok"
		ok := true
		if err := p.Ping(); err != nil {
			dbStatus = "down: " + err.Error()
			ok = false
		}
		w.Header().Set("Content-Type", "application/json")
		if !ok {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":  ifTrue(ok, "ok", "degraded"),
			"db":      dbStatus,
			"version": version,
		})
	})
}

func ifTrue(b bool, t, f string) string {
	if b {
		return t
	}
	return f
}
```

```go
// internal/metrics/metrics.go
package metrics

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	LoginTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_login_total",
		Help: "Login attempts grouped by result.",
	}, []string{"result"})

	TokenIssueTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_token_issue_total",
		Help: "Token issuances grouped by grant type and client.",
	}, []string{"grant_type", "client_id"})

	LogoutWebhookTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_logout_webhook_total",
		Help: "Logout webhook deliveries grouped by status.",
	}, []string{"status"})

	ActiveRefreshTokens = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "account_active_refresh_tokens",
		Help: "Current count of non-revoked, non-expired refresh tokens.",
	})

	TokenReuseAttacks = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_token_reuse_attacks_total",
		Help: "Refresh-token reuse attempts grouped by client.",
	}, []string{"client_id"})

	HTTPDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "http_request_duration_seconds",
		Help:    "HTTP request duration histogram.",
		Buckets: prometheus.DefBuckets,
	}, []string{"method", "path", "status"})
)

func Handler() http.Handler {
	return promhttp.Handler()
}
```

- [ ] **Step 4: Run**

```bash
go test ./internal/health/...
go vet ./...
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/health/ internal/metrics/
git commit -m "feat(account-service-backend): /health + Prometheus /metrics / Probes santé et Prometheus"
```

---

### Task 42: `main.go` — wire everything together

**Files:**
- Create: `cmd/server/main.go`

This is a wiring task. No new tests — the integration tests in earlier tasks
already exercise the components. After this task you should be able to run the
binary, hit `/health`, and the OAuth2 flow end-to-end via curl.

- [ ] **Step 1: Implement `main.go`**

```go
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/hellopro/account-service/internal/api"
	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/authserver"
	"github.com/hellopro/account-service/internal/config"
	"github.com/hellopro/account-service/internal/crypto"
	"github.com/hellopro/account-service/internal/db"
	"github.com/hellopro/account-service/internal/health"
	"github.com/hellopro/account-service/internal/logout"
	"github.com/hellopro/account-service/internal/metrics"
	"github.com/hellopro/account-service/internal/repository"
)

const version = "0.1.0"

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error("config load", "err", err)
		os.Exit(1)
	}

	gormDB, err := db.Connect(cfg.MySQLDSN)
	if err != nil {
		logger.Error("db connect", "err", err)
		os.Exit(1)
	}
	if err := db.AutoMigrate(gormDB); err != nil {
		logger.Error("auto migrate", "err", err)
		os.Exit(1)
	}

	cipher, err := crypto.New(cfg.EncryptionKey)
	if err != nil {
		logger.Error("crypto", "err", err)
		os.Exit(1)
	}

	userRepo := repository.NewUserRepo(gormDB, cfg.AdminEmails)
	oauthRepo := repository.NewOAuth2ClientRepo(gormDB)
	authCodeRepo := repository.NewAuthCodeRepo(gormDB)
	refreshRepo := repository.NewRefreshRepo(gormDB)
	logoutEvtRepo := repository.NewLogoutEventRepo(gormDB)
	auditRepo := repository.NewAuditRepo(gormDB)
	_ = auditRepo // wired into handlers below

	upsertAdapter := auth.UserUpserterFunc(func(email, name string) (*auth.UpsertedUser, error) {
		u, err := userRepo.UpsertOnLogin(email, name)
		if err != nil {
			return nil, err
		}
		return &auth.UpsertedUser{Email: u.Email, IsAdmin: u.IsAdmin, IsAllowed: u.IsAllowed}, nil
	})

	deliv := logout.NewDeliverer(logout.DelivererConfig{
		Timeout:     time.Duration(cfg.WebhookTimeoutS) * time.Second,
		MaxAttempts: cfg.WebhookRetries,
	})
	pool := logout.NewWorkerPool(logout.WorkerConfig{
		Workers:    cfg.LogoutWorkers,
		BufferSize: 256,
		Deliverer:  deliv,
		Repo:       logoutEvtRepo,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	pool.Start(ctx)

	broadcaster := logout.NewBroadcaster(logout.BroadcasterDeps{
		Decrypter: cryptoAdapter{cipher},
		Repo:      logoutEvtRepo,
		Pool:      pool,
		Issuer:    cfg.PublicURL,
	})

	authSrv := authserver.NewAuthServer(authserver.AuthServerDeps{
		ClientRepo:    oauthRepo,
		AuthCodeRepo:  authCodeRepo,
		UserUpserter:  upsertAdapter,
		AuthURL:       cfg.AuthURL,
		JWTSecret:     cfg.JWTSecret,
		JWTAudience:   cfg.JWTAudience,
		Issuer:        cfg.PublicURL,
		AuthCodeTTL:   time.Duration(cfg.AuthCodeTTL) * time.Second,
		SecureCookie:  cfg.SecureCookie,
		FallbackUser:  cfg.FallbackUser,
		FallbackPass:  cfg.FallbackPass,
		FallbackEmail: cfg.FallbackEmail,
	})
	tokenEP := authserver.NewTokenEndpoint(authserver.TokenEndpointDeps{
		ClientRepo:     oauthRepo,
		AuthCodeRepo:   authCodeRepo,
		RefreshRepo:    refreshRepo,
		RefreshRotator: refreshRepo,
		Decrypt:        cipher.Decrypt,
		JWTSecret:      cfg.JWTSecret,
		Issuer:         cfg.PublicURL,
	})

	mux := http.NewServeMux()

	// Public OAuth2 endpoints
	mux.Handle("GET /.well-known/oauth-authorization-server", authserver.NewMetadataHandler(cfg.PublicURL))
	mux.Handle("/authorize", http.HandlerFunc(authSrv.HandleAuthorize))
	mux.Handle("POST /token", tokenEP)
	mux.Handle("POST /token/revoke", authserver.NewRevokeHandler(authserver.RevokeDeps{
		ClientRepo: oauthRepo, Rotator: refreshRepo, Revoker: refreshRepo, Decrypt: cipher.Decrypt,
	}))
	mux.Handle("POST /introspect", authserver.NewIntrospectHandler(authserver.IntrospectDeps{
		ClientRepo: oauthRepo, Rotator: refreshRepo, Decrypt: cipher.Decrypt,
		JWTSecret: cfg.JWTSecret, Issuer: cfg.PublicURL,
	}))
	mux.Handle("GET /authorize/branding/{client_id}.json", authserver.NewBrandingHandler(oauthRepo))

	// Admin UI session endpoints
	loginHandler := auth.NewLoginHandler(auth.Config{
		AuthURL: cfg.AuthURL, JWTSecret: cfg.JWTSecret, JWTAudience: cfg.JWTAudience,
		SecureCookie: cfg.SecureCookie, FallbackUser: cfg.FallbackUser,
		FallbackPass: cfg.FallbackPass, FallbackEmail: cfg.FallbackEmail,
	}, upsertAdapter)
	mux.Handle("POST /api/v1/login", loginHandler)
	mux.Handle("POST /api/v1/logout", auth.NewLogoutHandler())

	// Admin guard
	resolver := func(email string) (bool, bool) {
		u, err := userRepo.FindByEmail(email)
		if err != nil {
			return false, false
		}
		return u.IsAllowed, u.IsAdmin
	}
	requireAdmin := auth.RequireAdmin(cfg.JWTSecret, resolver)

	mux.Handle("GET /api/v1/me", auth.RequireAuth(cfg.JWTSecret)(api.NewMeHandler(userInfoAdapter{userRepo})))
	mux.Handle("/api/v1/admin/services", requireAdmin(api.NewAdminServiceHandler(api.AdminServiceDeps{Repo: oauthRepo, Encrypt: cipher.Encrypt})))
	mux.Handle("/api/v1/admin/services/{id}", requireAdmin(api.NewAdminServiceDetailHandler(api.AdminServiceDetailDeps{Repo: oauthRepo, Encrypt: cipher.Encrypt})))
	mux.Handle("/api/v1/admin/services/{id}/{op}", requireAdmin(api.NewAdminServiceDetailHandler(api.AdminServiceDetailDeps{Repo: oauthRepo, Encrypt: cipher.Encrypt})))
	mux.Handle("GET /api/v1/admin/users", requireAdmin(api.NewAdminUserHandler(api.AdminUserDeps{
		Repo: userRepo, RevokeAll: refreshRepo, Broadcaster: userBroadcastAdapter{oauthRepo, refreshRepo, broadcaster},
	})))
	mux.Handle("POST /api/v1/admin/users/{email}/{op}", requireAdmin(api.NewAdminUserHandler(api.AdminUserDeps{
		Repo: userRepo, RevokeAll: refreshRepo, Broadcaster: userBroadcastAdapter{oauthRepo, refreshRepo, broadcaster},
	})))
	mux.Handle("/api/v1/admin/users/{email}/sessions", requireAdmin(api.NewSessionsHandler(api.SessionsDeps{Repo: refreshRepo})))
	mux.Handle("POST /api/v1/admin/sessions/{sid}/revoke", requireAdmin(api.NewSessionsHandler(api.SessionsDeps{Repo: refreshRepo})))
	mux.Handle("GET /api/v1/admin/audit", requireAdmin(api.NewAuditHandler(api.AuditDeps{Repo: auditRepo})))

	// Health + metrics
	mux.Handle("GET /health", health.NewHandler(version, dbPinger{gormDB}))
	mux.Handle("GET /metrics", metrics.Handler())

	// Top-level middleware chain
	root := api.RequestLog(api.Recover(mux))

	srv := &http.Server{
		Addr:              ":" + itoa(cfg.Port),
		Handler:           root,
		ReadHeaderTimeout: 5 * time.Second,
	}

	stopChan := make(chan os.Signal, 1)
	signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)
	go func() {
		logger.Info("listening", "addr", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("listen", "err", err)
			os.Exit(1)
		}
	}()
	<-stopChan
	logger.Info("shutdown signal received")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	_ = srv.Shutdown(shutdownCtx)
	cancel()
	pool.Wait()
	logger.Info("clean shutdown")
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	digits := []byte{}
	for n > 0 {
		digits = append([]byte{byte('0' + n%10)}, digits...)
		n /= 10
	}
	return string(digits)
}
```

Add the small adapters in the same file:

```go
// adapters.go portion of main.go (kept inline for simplicity)
type cryptoAdapter struct {
	c *crypto.Cipher
}

func (a cryptoAdapter) Decrypt(in []byte) ([]byte, error) { return a.c.Decrypt(in) }

type dbPinger struct {
	g *gorm.DB
}

func (p dbPinger) Ping() error {
	sqlDB, err := p.g.DB()
	if err != nil {
		return err
	}
	return sqlDB.Ping()
}

type userInfoAdapter struct {
	repo *repository.UserRepo
}

func (a userInfoAdapter) FindByEmail(email string) (api.UserInfo, error) {
	u, err := a.repo.FindByEmail(email)
	if err != nil {
		return api.UserInfo{}, err
	}
	return api.UserInfo{
		Email: u.Email, DisplayName: u.DisplayName,
		IsAdmin: u.IsAdmin, IsAllowed: u.IsAllowed,
	}, nil
}

type userBroadcastAdapter struct {
	clients *repository.OAuth2ClientRepo
	refresh *repository.RefreshRepo
	bc      *logout.Broadcaster
}

func (a userBroadcastAdapter) BroadcastForUser(email string) {
	rows, err := a.refresh.ListByUser(email)
	if err != nil {
		return
	}
	clientIDs := map[string]struct{}{}
	for _, r := range rows {
		clientIDs[r.ClientID] = struct{}{}
	}
	clients := make([]db.OAuth2Client, 0, len(clientIDs))
	for cid := range clientIDs {
		c, err := a.clients.GetByClientID(cid)
		if err != nil {
			continue
		}
		clients = append(clients, *c)
	}
	// One sid per row would be ideal, but for admin "revoke all" we group by user.
	// Send a single broadcast carrying empty sid; client handlers should treat
	// (sub, sid="") as "all sessions for user".
	a.bc.Broadcast(email, "", clients)
}
```

Add the missing imports `gorm.io/gorm` etc. as needed.

Define the helper used by the Login handler in `internal/auth/handlers.go`:

```go
type UserUpserterFunc func(email, name string) (*UpsertedUser, error)

func (f UserUpserterFunc) UpsertOnLogin(email, name string) (*UpsertedUser, error) {
	return f(email, name)
}
```

- [ ] **Step 2: Build**

```bash
go build ./cmd/server
go vet ./...
```
Expected: success.

- [ ] **Step 3: Smoke run**

```bash
MYSQL_DSN="root:root@tcp(localhost:3306)/account_db?parseTime=true" \
ENCRYPTION_KEY=$(openssl rand -hex 32) \
JWT_SECRET=$(openssl rand -hex 16) \
AUTH_URL=https://www.hellopro.fr/login \
ACCOUNT_PUBLIC_URL=http://localhost:8600 \
go run ./cmd/server &
sleep 2
curl -fsS http://localhost:8600/health
curl -fsS http://localhost:8600/.well-known/oauth-authorization-server | jq
kill %1
```
Expected: `/health` → `{"status":"ok",...}`; metadata JSON contains `"issuer":"http://localhost:8600"`.

- [ ] **Step 4: Commit**

```bash
git add cmd/server/main.go internal/auth/handlers.go
git commit -m "feat(account-service-backend): wire main.go end-to-end / Câblage main.go bout en bout"
```

---

### Task 43: Dockerfile + init-db SQL

**Files:**
- Create: `Dockerfile`
- Create: `init-db/init-account-db.sql`
- Create: `.dockerignore`

- [ ] **Step 1: Write `init-db/init-account-db.sql`**

```sql
-- account-service-backend bootstrap
CREATE DATABASE IF NOT EXISTS `account_db`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'account'@'%' IDENTIFIED BY 'account';
GRANT ALL PRIVILEGES ON `account_db`.* TO 'account'@'%';
FLUSH PRIVILEGES;
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git
.gitignore
.dockerignore
*_test.go
*.md
docs/
node_modules/
```

- [ ] **Step 3: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7

FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/account-service ./cmd/server

FROM alpine:3.20
RUN addgroup -S app && adduser -S app -G app
RUN apk add --no-cache ca-certificates curl
USER app
COPY --from=build /out/account-service /app/account-service
EXPOSE 8600
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -fsS http://localhost:8600/health || exit 1
ENTRYPOINT ["/app/account-service"]
```

- [ ] **Step 4: Build the image locally**

```bash
docker build -t account-service-backend:dev apps-microservices/account-service-backend
```
Expected: image built successfully.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/Dockerfile apps-microservices/account-service-backend/init-db apps-microservices/account-service-backend/.dockerignore
git commit -m "feat(account-service-backend): add Dockerfile and init-db SQL / Ajout du Dockerfile et SQL d'init"
```

---

## Phase 8 — Frontend Bootstrap from `public/admin-dashboad/`

> **Branch switch:** `git checkout feature/account-service-frontend` for all of Phase 8–11.

### Task 44: Clone TailAdmin template into the new service

**Files:**
- Create: `apps-microservices/account-service-frontend/` (full tree from template)

- [ ] **Step 1: Copy the template**

```bash
cd apps-microservices
cp -r ../public/admin-dashboad ./account-service-frontend
cd account-service-frontend
rm -rf node_modules .git package-lock.json
```

- [ ] **Step 2: Rename in `package.json`**

```bash
sed -i 's/"name": "tailadmin-vue-pro-2.0.1"/"name": "account-service-frontend"/' package.json
```

- [ ] **Step 3: Install fresh dependencies + add Pinia**

```bash
npm install
npm install pinia@^2.1.0
```

- [ ] **Step 4: Verify type-check passes**

```bash
npm run type-check
```
Expected: success (clean inherited template).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-frontend
git commit -m "chore(account-service-frontend): clone admin-dashboad template + add Pinia / Clone du template"
```

---

### Task 45: Strip unused TailAdmin demo views and routes

**Files:**
- Delete: `src/views/Charts/`, `src/views/Calendar.vue`, `src/views/Kanban.vue`, `src/views/Forms/FormElements.vue`, `src/views/Forms/FormLayout.vue`, `src/views/Tables/`, `src/views/UiElements/`, `src/views/Pages/`, `src/views/Others/`, `src/views/Ecommerce.vue`
- Modify: `src/router/index.ts` (remove the deleted routes)
- Modify: `src/components/layout/AppSidebar.vue` (remove their nav entries)

This task is bulk-pruning. Keep:
- `src/views/Auth/Signin.vue` (we will adapt it in Task 50)
- `src/views/Errors/` (404 etc.)
- `src/views/Profile.vue` (basis for `MeView.vue` later)
- Layout, sidebar, header components.

- [ ] **Step 1: Delete the unused folders**

```bash
cd apps-microservices/account-service-frontend
git rm -r src/views/Charts \
            src/views/Calendar.vue \
            src/views/Kanban.vue \
            src/views/Forms/FormElements.vue \
            src/views/Forms/FormLayout.vue \
            src/views/Tables \
            src/views/UiElements \
            src/views/Pages \
            src/views/Others \
            src/views/Ecommerce.vue
```

- [ ] **Step 2: Open `src/router/index.ts`**

Remove every route whose `component:` referenced a deleted view. Replace the
homepage redirect rule with a placeholder that we'll fill in Task 51:

```ts
// at the top of routes, before the deleted routes:
{ path: '/', redirect: '/login' },
```

Keep `Auth/Signin.vue` and `Errors/*` mappings.

- [ ] **Step 3: Open `src/components/layout/AppSidebar.vue`**

Remove every menu item that pointed to a deleted route. Leave the section
headers (we'll repopulate them in Task 52+).

- [ ] **Step 4: Verify**

```bash
npm run type-check
npm run lint
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(account-service-frontend): drop TailAdmin demo views / Suppression des vues démo"
```

---

### Task 46: Vite + nginx config (proxy /api to backend)

**Files:**
- Modify: `vite.config.ts`
- Create: `nginx.conf`

- [ ] **Step 1: Edit `vite.config.ts`**

Add the dev-time backend proxy. Keep all existing config:

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'
import { fileURLToPath, URL } from 'node:url'

const BACKEND = process.env.ACCOUNT_BACKEND_URL || 'http://localhost:8600'

export default defineConfig({
  plugins: [vue(), vueJsx(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: false },
      '/authorize': { target: BACKEND, changeOrigin: false },
      '/token': { target: BACKEND, changeOrigin: false },
      '/introspect': { target: BACKEND, changeOrigin: false },
      '/register': { target: BACKEND, changeOrigin: false },
      '/.well-known': { target: BACKEND, changeOrigin: false },
    },
  },
})
```

- [ ] **Step 2: Write `nginx.conf` for production**

```nginx
worker_processes auto;
events { worker_connections 1024; }

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;
    server_tokens off;

    upstream backend {
        server account-service-backend:8600;
        keepalive 32;
    }

    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    server {
        listen 8601;
        server_name _;
        root /usr/share/nginx/html;

        # SPA fallback
        location / { try_files $uri $uri/ /index.html; }

        # Backend-proxied paths
        location /api/         { proxy_pass http://backend; include /etc/nginx/proxy.inc; }
        location /authorize    { proxy_pass http://backend; include /etc/nginx/proxy.inc; }
        location /token        { proxy_pass http://backend; include /etc/nginx/proxy.inc; }
        location /token/revoke { proxy_pass http://backend; include /etc/nginx/proxy.inc; }
        location /introspect   { proxy_pass http://backend; include /etc/nginx/proxy.inc; }
        location /register     { proxy_pass http://backend; include /etc/nginx/proxy.inc; }
        location /.well-known/ { proxy_pass http://backend; include /etc/nginx/proxy.inc; }

        # Static caching for built assets (vite emits hashed filenames)
        location ~* \.(js|css|woff2?|svg|png|jpg|jpeg|webp|ico)$ {
            expires 30d;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

Create the proxy include used above:

```bash
cat > nginx-proxy.inc <<'EOF'
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_read_timeout 30s;
EOF
mv nginx-proxy.inc /etc/nginx/proxy.inc 2>/dev/null || true
```

(Note: the actual placement of `proxy.inc` happens in the Dockerfile in Task 63.)

- [ ] **Step 3: Verify the dev server starts (proxy works against the running backend)**

In one terminal, run the backend (Task 42 smoke). In another:

```bash
cd apps-microservices/account-service-frontend
npm run dev -- --host
curl -fsS http://localhost:5173/api/v1/admin/services # expect 401 (no session cookie) — proves the proxy
```

- [ ] **Step 4: Commit**

```bash
git add vite.config.ts nginx.conf
git commit -m "feat(account-service-frontend): vite proxy + nginx config / Proxy vite et configuration nginx"
```

---

## Phase 9 — Frontend Auth, Router, LoginView

### Task 47: Typed API client wrapper

**Files:**
- Create: `src/api/client.ts`

This is a small library file. We test it in Task 58 when Vitest is set up.

- [ ] **Step 1: Implement**

```ts
// src/api/client.ts
export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

let unauthorizedHandler: (() => void) | null = null

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler
}

export interface ApiOpts {
  method?: string
  body?: unknown
  query?: Record<string, string | number | undefined>
  signal?: AbortSignal
}

function buildUrl(path: string, query?: ApiOpts['query']): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null) params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

export async function api<T>(path: string, opts: ApiOpts = {}): Promise<T> {
  const init: RequestInit = {
    method: opts.method ?? 'GET',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    signal: opts.signal,
  }
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body)

  const res = await fetch(buildUrl(path, opts.query), init)
  if (res.status === 401) {
    if (unauthorizedHandler) unauthorizedHandler()
    throw new ApiError('Unauthorized', 401, 'unauthorized')
  }
  if (!res.ok) {
    let body: { error?: string; error_description?: string } = {}
    try { body = await res.json() } catch { /* ignore */ }
    throw new ApiError(body.error_description || body.error || res.statusText, res.status, body.error || 'http_error')
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
```

- [ ] **Step 2: Commit**

```bash
git add src/api/client.ts
git commit -m "feat(account-service-frontend): typed fetch wrapper / Wrapper fetch typé"
```

---

### Task 48: Auth store (Pinia)

**Files:**
- Create: `src/stores/auth.ts`
- Create: `src/types/user.ts`

- [ ] **Step 1: Implement types**

```ts
// src/types/user.ts
export interface CurrentUser {
  email: string
  display_name?: string
  is_admin: boolean
  is_allowed: boolean
}
```

- [ ] **Step 2: Implement the Pinia store**

```ts
// src/stores/auth.ts
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, onUnauthorized } from '@/api/client'
import type { CurrentUser } from '@/types/user'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const isLoading = ref(false)
  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.is_admin === true)

  onUnauthorized(() => {
    user.value = null
  })

  async function checkSession(): Promise<boolean> {
    try {
      isLoading.value = true
      const me = await api<CurrentUser>('/api/v1/me')
      user.value = me
      return true
    } catch {
      user.value = null
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function login(username: string, password: string): Promise<void> {
    isLoading.value = true
    try {
      const resp = await api<CurrentUser>('/api/v1/login', {
        method: 'POST',
        body: { username, password },
      })
      user.value = resp
    } finally {
      isLoading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await api('/api/v1/logout', { method: 'POST' })
    } finally {
      user.value = null
    }
  }

  return { user, isLoading, isAuthenticated, isAdmin, checkSession, login, logout }
})
```

- [ ] **Step 3: Wire Pinia in `src/main.ts`**

```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import './assets/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
```

- [ ] **Step 4: Build**

```bash
npm run type-check
```
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add src/stores/auth.ts src/types/user.ts src/main.ts
git commit -m "feat(account-service-frontend): Pinia auth store / Store Pinia auth"
```

---

### Task 49: Router with guards

**Files:**
- Modify: `src/router/index.ts`

- [ ] **Step 1: Replace the contents with the SSO routes**

```ts
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    title?: string
    minRole?: 'admin' | 'user'
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { requiresAuth: false } },
    { path: '/me', name: 'me', component: () => import('@/views/MeView.vue'), meta: { requiresAuth: true } },
    { path: '/admin/services', name: 'services', component: () => import('@/views/AdminServicesView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Services' } },
    { path: '/admin/services/new', name: 'service-create', component: () => import('@/views/ServiceFormView.vue'), meta: { requiresAuth: true, minRole: 'admin' } },
    { path: '/admin/services/:id/edit', name: 'service-edit', component: () => import('@/views/ServiceFormView.vue'), meta: { requiresAuth: true, minRole: 'admin' } },
    { path: '/admin/users', name: 'users', component: () => import('@/views/AdminUsersView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: 'Utilisateurs' } },
    { path: '/admin/users/:email/sessions', name: 'user-sessions', component: () => import('@/views/UserSessionsView.vue'), meta: { requiresAuth: true, minRole: 'admin' } },
    { path: '/admin/audit', name: 'audit', component: () => import('@/views/AuditLogView.vue'), meta: { requiresAuth: true, minRole: 'admin', title: "Journal d'audit" } },
    { path: '/', name: 'root', redirect: () => {
      const a = useAuthStore()
      return a.isAdmin ? '/admin/services' : '/me'
    }},
    { path: '/:pathMatch(.*)*', redirect: '/login' },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.requiresAuth === false) return true

  const a = useAuthStore()
  if (!a.isAuthenticated) {
    const ok = await a.checkSession()
    if (!ok) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta.minRole === 'admin' && !a.isAdmin) {
    return { path: '/me' }
  }
  return true
})
```

- [ ] **Step 2: Build**

```bash
npm run type-check
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add src/router/index.ts
git commit -m "feat(account-service-frontend): router with SSO guards / Routeur avec gardes SSO"
```

---

### Task 50: LoginView dual-mode (admin UI vs OAuth2 SSO)

**Files:**
- Create: `src/views/LoginView.vue`
- Replace: `src/views/Auth/Signin.vue` (kept as legacy reference, can delete after this task)

- [ ] **Step 1: Implement**

```vue
<!-- src/views/LoginView.vue -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')

const oauthMode = computed(() =>
  Boolean(route.query.client_id && route.query.redirect_uri && route.query.code_challenge)
)

interface Branding {
  name?: string
  logo_url?: string
  brand_color?: string
}
const branding = ref<Branding | null>(null)

onMounted(async () => {
  if (!oauthMode.value) return
  try {
    const cid = String(route.query.client_id)
    const res = await fetch(`/authorize/branding/${cid}.json`)
    if (res.ok) branding.value = await res.json()
  } catch {
    /* ignore — fallback to default branding */
  }
})

async function handleAdminLogin() {
  errorMessage.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || (auth.isAdmin ? '/admin/services' : '/me')
    router.push(redirect)
  } catch (e) {
    errorMessage.value = e instanceof ApiError ? e.message : 'Erreur de connexion'
  }
}

// In oauthMode the form is a real <form action="/authorize" method="POST"> so
// the browser follows the 302 redirect from the backend natively. JavaScript
// only handles error display before submit if creds are empty.
function ensureFilled(e: Event) {
  if (!username.value || !password.value) {
    e.preventDefault()
    errorMessage.value = 'Tous les champs sont obligatoires'
  }
}
</script>

<template>
  <div class="min-h-screen flex">
    <div class="hidden lg:flex lg:w-1/2 bg-[#1C2434] relative items-center justify-center px-12">
      <div class="relative z-10 text-center max-w-md">
        <div v-if="branding?.logo_url" class="mx-auto mb-8 w-20 h-20 rounded-2xl bg-white flex items-center justify-center p-3 shadow-lg">
          <img :src="branding.logo_url" :alt="branding.name ?? 'Service'" class="w-full h-full object-contain" />
        </div>
        <h1 class="text-3xl font-bold text-white mb-4">
          {{ oauthMode ? `Connexion à ${branding?.name ?? 'votre service'}` : 'Account Service' }}
        </h1>
        <p class="text-gray-400 text-base leading-relaxed">
          Plateforme d'identité unifiée Hellopro.
        </p>
      </div>
    </div>

    <div class="w-full lg:w-1/2 flex items-center justify-center bg-gray-100 dark:bg-gray-950 px-6">
      <div class="w-full max-w-sm">
        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-md p-8">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-1">Connexion</h2>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">
            {{ oauthMode ? 'Authentifiez-vous pour accéder à ce service.' : 'Accédez au tableau de bord.' }}
          </p>

          <div v-if="errorMessage" class="mb-4 p-3 bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md text-sm text-error-600 dark:text-error-400">
            {{ errorMessage }}
          </div>

          <!-- OAuth2 mode: real form POST /authorize -->
          <form
            v-if="oauthMode"
            action="/authorize"
            method="POST"
            enctype="application/x-www-form-urlencoded"
            @submit="ensureFilled"
          >
            <input type="hidden" name="action" value="login" />
            <input type="hidden" name="response_type" :value="route.query.response_type" />
            <input type="hidden" name="client_id" :value="route.query.client_id" />
            <input type="hidden" name="redirect_uri" :value="route.query.redirect_uri" />
            <input type="hidden" name="code_challenge" :value="route.query.code_challenge" />
            <input type="hidden" name="code_challenge_method" value="S256" />
            <input type="hidden" name="state" :value="route.query.state ?? ''" />
            <div class="mb-4">
              <label for="u-oauth" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nom d'utilisateur</label>
              <input id="u-oauth" name="username" v-model="username" type="text" required class="h-11 w-full rounded-lg border border-gray-300 px-3" />
            </div>
            <div class="mb-6">
              <label for="p-oauth" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Mot de passe</label>
              <input id="p-oauth" name="password" v-model="password" type="password" required class="h-11 w-full rounded-lg border border-gray-300 px-3" />
            </div>
            <button type="submit" class="w-full py-2.5 px-4 bg-brand-500 text-white font-medium rounded-md hover:bg-brand-600">Se connecter</button>
          </form>

          <!-- Admin UI mode: JS-driven JSON POST /api/v1/login -->
          <form v-else @submit.prevent="handleAdminLogin">
            <div class="mb-4">
              <label for="u-admin" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nom d'utilisateur</label>
              <input id="u-admin" v-model="username" type="text" required class="h-11 w-full rounded-lg border border-gray-300 px-3" />
            </div>
            <div class="mb-6">
              <label for="p-admin" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Mot de passe</label>
              <input id="p-admin" v-model="password" type="password" required class="h-11 w-full rounded-lg border border-gray-300 px-3" />
            </div>
            <button type="submit" :disabled="auth.isLoading" class="w-full py-2.5 px-4 bg-brand-500 text-white font-medium rounded-md hover:bg-brand-600 disabled:opacity-50">
              {{ auth.isLoading ? 'Connexion...' : 'Se connecter' }}
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Build**

```bash
npm run type-check
```
Expected: success.

- [ ] **Step 3: Manually verify both modes**

Run the backend (Task 42), the frontend dev server, and:

1. Open `http://localhost:5173/login` → admin mode form. Enter creds (need a hellopro.fr-valid account or set `FALLBACK_USER`). Should redirect to `/admin/services`.
2. Open `http://localhost:5173/login?response_type=code&client_id=test&redirect_uri=https%3A%2F%2Fexample.com%2Fcb&code_challenge=AAAA&code_challenge_method=S256&state=xyz` → OAuth2 mode form. The form POSTs to `/authorize` and the backend bounces (in this case it returns 400 because `test` is not registered — that's expected without a real client).

- [ ] **Step 4: Commit**

```bash
git add src/views/LoginView.vue
git commit -m "feat(account-service-frontend): dual-mode LoginView / Vue de connexion à deux modes"
```

---

## Phase 10 — Admin Views

### Task 51: API modules (services, users, audit)

**Files:**
- Create: `src/api/services.ts`
- Create: `src/api/users.ts`
- Create: `src/api/audit.ts`
- Create: `src/types/oauth2.ts`
- Create: `src/types/audit.ts`

- [ ] **Step 1: Types**

```ts
// src/types/oauth2.ts
export interface OAuth2Client {
  id: string
  client_id: string
  name: string
  description?: string
  logo_url?: string
  brand_color?: string
  redirect_uris: string[] | null
  allowed_roles: string[] | null
  logout_webhook_url?: string
  token_ttl_s: number
  refresh_ttl_s: number
  claim_mappings: Record<string, string> | null
  scope?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface OAuth2ClientCreatePayload {
  name: string
  description?: string
  logo_url?: string
  brand_color?: string
  redirect_uris: string[]
  allowed_roles?: string[]
  logout_webhook_url?: string
  token_ttl_s?: number
  refresh_ttl_s?: number
  claim_mappings?: Record<string, string>
  scope?: string
}

export interface OAuth2ClientCreateResponse {
  id: string
  client_id: string
  client_secret: string
  name: string
  redirect_uris: string[]
}

export interface ListResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
```

```ts
// src/types/audit.ts
export interface AuditEntry {
  id: number
  event: string
  actor_email?: string
  target_email?: string
  client_id?: string
  ip_addr?: string
  user_agent?: string
  metadata?: unknown
  created_at: string
}
```

- [ ] **Step 2: API modules**

```ts
// src/api/services.ts
import { api } from './client'
import type { ListResponse, OAuth2Client, OAuth2ClientCreatePayload, OAuth2ClientCreateResponse } from '@/types/oauth2'

export function list(limit = 20, offset = 0) {
  return api<ListResponse<OAuth2Client>>('/api/v1/admin/services', { query: { limit, offset } })
}
export function get(id: string) { return api<OAuth2Client>(`/api/v1/admin/services/${encodeURIComponent(id)}`) }
export function create(payload: OAuth2ClientCreatePayload) {
  return api<OAuth2ClientCreateResponse>('/api/v1/admin/services', { method: 'POST', body: payload })
}
export function update(id: string, payload: Partial<OAuth2ClientCreatePayload>) {
  return api<OAuth2Client>(`/api/v1/admin/services/${encodeURIComponent(id)}`, { method: 'PUT', body: payload })
}
export function remove(id: string) {
  return api<void>(`/api/v1/admin/services/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
export function rotateSecret(id: string) {
  return api<{ client_secret: string }>(`/api/v1/admin/services/${encodeURIComponent(id)}/rotate-secret`, { method: 'POST' })
}
export function testWebhook(id: string) {
  return api<{ status: number }>(`/api/v1/admin/services/${encodeURIComponent(id)}/test-webhook`, { method: 'POST' })
}
```

```ts
// src/api/users.ts
import { api } from './client'
import type { ListResponse } from '@/types/oauth2'

export interface AdminUser {
  email: string
  display_name?: string
  is_admin: boolean
  is_allowed: boolean
  last_login_at?: string
  created_at: string
}

export interface AdminSession {
  id: string
  sid: string
  client_id: string
  created_at: string
  last_used_at?: string
  expires_at: string
  revoked: boolean
  revoked_reason?: string
}

export function list(limit = 20, offset = 0) {
  return api<ListResponse<AdminUser>>('/api/v1/admin/users', { query: { limit, offset } })
}
export function promote(email: string) { return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/promote`, { method: 'POST' }) }
export function demote(email: string) { return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/demote`, { method: 'POST' }) }
export function block(email: string) { return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/block`, { method: 'POST' }) }
export function unblock(email: string) { return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/unblock`, { method: 'POST' }) }
export function revoke(email: string) { return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/revoke`, { method: 'POST' }) }

export function listSessions(email: string) {
  return api<{ items: AdminSession[]; total: number }>(`/api/v1/admin/users/${encodeURIComponent(email)}/sessions`)
}
export function revokeSession(sid: string) {
  return api<{ status: string }>(`/api/v1/admin/sessions/${encodeURIComponent(sid)}/revoke`, { method: 'POST' })
}
```

```ts
// src/api/audit.ts
import { api } from './client'
import type { ListResponse } from '@/types/oauth2'
import type { AuditEntry } from '@/types/audit'

export function list(filters: { event?: string; actor_email?: string; client_id?: string }, limit = 20, offset = 0) {
  return api<ListResponse<AuditEntry>>('/api/v1/admin/audit', { query: { ...filters, limit, offset } })
}
```

- [ ] **Step 3: Type-check**

```bash
npm run type-check
```
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add src/api/services.ts src/api/users.ts src/api/audit.ts src/types/oauth2.ts src/types/audit.ts
git commit -m "feat(account-service-frontend): typed API modules / Modules API typés"
```

---

### Task 52: AdminServicesView (list)

**Files:**
- Create: `src/views/AdminServicesView.vue`

- [ ] **Step 1: Implement**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as servicesApi from '@/api/services'
import type { OAuth2Client } from '@/types/oauth2'

const router = useRouter()
const items = ref<OAuth2Client[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const limit = 20
const offset = ref(0)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await servicesApi.list(limit, offset.value)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function nextPage() { offset.value += limit; load() }
function prevPage() { offset.value = Math.max(0, offset.value - limit); load() }
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-semibold">Services OAuth2</h1>
      <button class="px-4 py-2 bg-brand-500 text-white rounded-md hover:bg-brand-600"
              @click="router.push('/admin/services/new')">
        + Nouveau service
      </button>
    </div>

    <div v-if="error" class="mb-4 p-3 bg-error-50 text-error-600 rounded-md">{{ error }}</div>

    <div class="bg-white dark:bg-gray-900 rounded-lg shadow overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-gray-100 dark:bg-gray-800">
          <tr>
            <th class="px-4 py-2 text-left">Nom</th>
            <th class="px-4 py-2 text-left">client_id</th>
            <th class="px-4 py-2 text-left">Redirect URIs</th>
            <th class="px-4 py-2 text-left">TTL token</th>
            <th class="px-4 py-2 text-left">Actif</th>
            <th class="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in items" :key="c.id" class="border-t">
            <td class="px-4 py-2 font-medium">{{ c.name }}</td>
            <td class="px-4 py-2 font-mono">{{ c.client_id.slice(0, 12) }}…</td>
            <td class="px-4 py-2">{{ c.redirect_uris?.length ?? 0 }}</td>
            <td class="px-4 py-2">{{ c.token_ttl_s }}s</td>
            <td class="px-4 py-2">
              <span :class="c.is_active ? 'text-success-600' : 'text-error-600'">
                {{ c.is_active ? 'oui' : 'non' }}
              </span>
            </td>
            <td class="px-4 py-2 text-right">
              <button class="text-brand-500 hover:underline" @click="router.push(`/admin/services/${c.id}/edit`)">
                Modifier
              </button>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
            <td colspan="6" class="px-4 py-8 text-center text-gray-500">Aucun service</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-4 flex justify-between items-center text-sm">
      <span>{{ total }} service(s)</span>
      <div class="space-x-2">
        <button class="px-3 py-1 border rounded" :disabled="offset === 0" @click="prevPage">Précédent</button>
        <button class="px-3 py-1 border rounded" :disabled="offset + limit >= total" @click="nextPage">Suivant</button>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Type-check**

```bash
npm run type-check
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add src/views/AdminServicesView.vue
git commit -m "feat(account-service-frontend): admin services list / Liste des services"
```

---

### Task 53: ServiceFormView with sub-components

**Files:**
- Create: `src/views/ServiceFormView.vue`
- Create: `src/components/services/RedirectUriList.vue`
- Create: `src/components/services/ClaimMapperEditor.vue`

- [ ] **Step 1: `RedirectUriList.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ modelValue: string[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string[]): void }>()

const uris = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

function add() { uris.value = [...uris.value, ''] }
function remove(i: number) { uris.value = uris.value.filter((_, idx) => idx !== i) }
function update(i: number, v: string) {
  const copy = [...uris.value]
  copy[i] = v
  uris.value = copy
}
function isValid(u: string): boolean {
  if (!u) return true
  return /^https?:\/\//.test(u)
}
</script>

<template>
  <div class="space-y-2">
    <div v-for="(u, i) in uris" :key="i" class="flex gap-2">
      <input :value="u" @input="update(i, ($event.target as HTMLInputElement).value)"
             type="url" placeholder="https://service.example/callback"
             class="flex-1 h-10 px-3 border rounded"
             :class="isValid(u) ? '' : 'border-error-500'" />
      <button type="button" class="px-3 py-1 text-error-600" @click="remove(i)">×</button>
    </div>
    <button type="button" class="text-sm text-brand-500" @click="add">+ Ajouter une URI</button>
  </div>
</template>
```

- [ ] **Step 2: `ClaimMapperEditor.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'

interface Mapping { user_field: string; claim_name: string }

const props = defineProps<{ modelValue: Record<string, string> }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: Record<string, string>): void }>()

const rows = computed<Mapping[]>(() =>
  Object.entries(props.modelValue ?? {}).map(([user_field, claim_name]) => ({ user_field, claim_name }))
)

function add() {
  emit('update:modelValue', { ...props.modelValue, '': '' })
}
function remove(field: string) {
  const copy = { ...props.modelValue }
  delete copy[field]
  emit('update:modelValue', copy)
}
function setField(oldField: string, newField: string) {
  const copy: Record<string, string> = {}
  for (const [k, v] of Object.entries(props.modelValue)) {
    copy[k === oldField ? newField : k] = v
  }
  emit('update:modelValue', copy)
}
function setClaim(field: string, claim: string) {
  emit('update:modelValue', { ...props.modelValue, [field]: claim })
}
</script>

<template>
  <div class="space-y-2">
    <div v-for="row in rows" :key="row.user_field" class="flex gap-2">
      <select :value="row.user_field"
              @change="setField(row.user_field, ($event.target as HTMLSelectElement).value)"
              class="h-10 px-3 border rounded">
        <option value="">— champ utilisateur —</option>
        <option value="email">email</option>
        <option value="display_name">display_name</option>
        <option value="is_admin">is_admin</option>
      </select>
      <input :value="row.claim_name"
             @input="setClaim(row.user_field, ($event.target as HTMLInputElement).value)"
             placeholder="claim JWT"
             class="flex-1 h-10 px-3 border rounded" />
      <button type="button" class="text-error-600" @click="remove(row.user_field)">×</button>
    </div>
    <button type="button" class="text-sm text-brand-500" @click="add">+ Ajouter un mapping</button>
  </div>
</template>
```

- [ ] **Step 3: `ServiceFormView.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as servicesApi from '@/api/services'
import type { OAuth2ClientCreatePayload } from '@/types/oauth2'
import RedirectUriList from '@/components/services/RedirectUriList.vue'
import ClaimMapperEditor from '@/components/services/ClaimMapperEditor.vue'

const route = useRoute()
const router = useRouter()
const isEdit = !!route.params.id

const form = ref<OAuth2ClientCreatePayload>({
  name: '',
  redirect_uris: [''],
  token_ttl_s: 60,
  refresh_ttl_s: 2592000,
  allowed_roles: [],
  claim_mappings: {},
})
const error = ref('')
const saving = ref(false)
const issuedSecret = ref<string | null>(null)
const issuedClientId = ref<string | null>(null)

onMounted(async () => {
  if (!isEdit) return
  try {
    const c = await servicesApi.get(String(route.params.id))
    form.value = {
      name: c.name,
      description: c.description,
      logo_url: c.logo_url,
      brand_color: c.brand_color,
      redirect_uris: c.redirect_uris ?? [''],
      allowed_roles: c.allowed_roles ?? [],
      logout_webhook_url: c.logout_webhook_url,
      token_ttl_s: c.token_ttl_s,
      refresh_ttl_s: c.refresh_ttl_s,
      claim_mappings: c.claim_mappings ?? {},
      scope: c.scope,
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  }
})

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (isEdit) {
      await servicesApi.update(String(route.params.id), form.value)
      router.push('/admin/services')
    } else {
      const r = await servicesApi.create(form.value)
      issuedClientId.value = r.client_id
      issuedSecret.value = r.client_secret
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  } finally {
    saving.value = false
  }
}

async function rotate() {
  if (!confirm('Régénérer le secret ? L\'ancien sera invalidé immédiatement.')) return
  try {
    const r = await servicesApi.rotateSecret(String(route.params.id))
    issuedSecret.value = r.client_secret
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

async function testWebhook() {
  try {
    const r = await servicesApi.testWebhook(String(route.params.id))
    alert(`Webhook répondu: HTTP ${r.status}`)
  } catch (e) {
    alert('Webhook KO: ' + (e instanceof Error ? e.message : ''))
  }
}
</script>

<template>
  <div class="p-6 max-w-3xl">
    <h1 class="text-2xl font-semibold mb-4">
      {{ isEdit ? 'Modifier un service' : 'Nouveau service' }}
    </h1>

    <div v-if="error" class="mb-4 p-3 bg-error-50 text-error-600 rounded">{{ error }}</div>

    <div v-if="issuedSecret" class="mb-6 p-4 bg-warning-50 border border-warning-300 rounded">
      <p class="font-semibold text-warning-800 mb-2">Secret généré — copier maintenant, il ne sera pas réaffiché</p>
      <p class="text-sm">client_id: <code class="font-mono">{{ issuedClientId }}</code></p>
      <p class="text-sm">client_secret: <code class="font-mono break-all">{{ issuedSecret }}</code></p>
      <button class="mt-2 px-3 py-1 bg-brand-500 text-white rounded" @click="router.push('/admin/services')">OK</button>
    </div>

    <form v-else @submit.prevent="save" class="space-y-6">
      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Identité</legend>
        <label class="block text-sm mb-1 mt-2">Nom</label>
        <input v-model="form.name" required class="w-full h-10 px-3 border rounded" />
        <label class="block text-sm mb-1 mt-3">Description</label>
        <textarea v-model="form.description" class="w-full h-20 px-3 py-2 border rounded" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Branding</legend>
        <label class="block text-sm mb-1 mt-2">Logo URL</label>
        <input v-model="form.logo_url" class="w-full h-10 px-3 border rounded" />
        <label class="block text-sm mb-1 mt-3">Couleur</label>
        <input v-model="form.brand_color" type="color" class="h-10 w-20 border rounded" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">URIs de redirection</legend>
        <RedirectUriList v-model="form.redirect_uris" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Politique de jetons</legend>
        <label class="block text-sm mb-1 mt-2">TTL access (s)</label>
        <input v-model.number="form.token_ttl_s" type="number" min="30" max="3600" class="h-10 px-3 border rounded" />
        <label class="block text-sm mb-1 mt-3">TTL refresh (s)</label>
        <input v-model.number="form.refresh_ttl_s" type="number" min="300" max="7776000" class="h-10 px-3 border rounded" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Webhook de déconnexion</legend>
        <input v-model="form.logout_webhook_url" type="url" placeholder="https://service/back-channel-logout"
               class="w-full h-10 px-3 border rounded" />
        <button v-if="isEdit" type="button" class="mt-2 text-sm text-brand-500" @click="testWebhook">
          Tester le webhook
        </button>
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Mappings de claims</legend>
        <ClaimMapperEditor v-model="form.claim_mappings!" />
      </fieldset>

      <div class="flex gap-2">
        <button type="submit" :disabled="saving" class="px-4 py-2 bg-brand-500 text-white rounded">
          {{ saving ? 'Enregistrement…' : (isEdit ? 'Mettre à jour' : 'Créer') }}
        </button>
        <button v-if="isEdit" type="button" @click="rotate" class="px-4 py-2 border rounded">
          Régénérer le secret
        </button>
        <button type="button" @click="router.push('/admin/services')" class="px-4 py-2 border rounded">
          Annuler
        </button>
      </div>
    </form>
  </div>
</template>
```

- [ ] **Step 4: Type-check**

```bash
npm run type-check
```
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add src/views/ServiceFormView.vue src/components/services/
git commit -m "feat(account-service-frontend): service form with sub-components / Formulaire de service"
```

---

### Task 54: AdminUsersView (list + actions)

**Files:**
- Create: `src/views/AdminUsersView.vue`

- [ ] **Step 1: Implement**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as usersApi from '@/api/users'

const router = useRouter()
const items = ref<usersApi.AdminUser[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try {
    const r = await usersApi.list(50, 0)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  } finally {
    loading.value = false
  }
}

async function action(fn: (e: string) => Promise<unknown>, email: string, label: string) {
  if (!confirm(`${label} ${email} ?`)) return
  try {
    await fn(email)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Utilisateurs ({{ total }})</h1>
    <div v-if="error" class="mb-4 p-3 bg-error-50 text-error-600 rounded">{{ error }}</div>

    <table class="w-full text-sm bg-white dark:bg-gray-900 rounded shadow">
      <thead class="bg-gray-100 dark:bg-gray-800">
        <tr>
          <th class="px-4 py-2 text-left">Email</th>
          <th class="px-4 py-2 text-left">Nom</th>
          <th class="px-4 py-2">Admin</th>
          <th class="px-4 py-2">Autorisé</th>
          <th class="px-4 py-2 text-left">Dernière connexion</th>
          <th class="px-4 py-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in items" :key="u.email" class="border-t">
          <td class="px-4 py-2 font-mono">{{ u.email }}</td>
          <td class="px-4 py-2">{{ u.display_name }}</td>
          <td class="px-4 py-2 text-center">{{ u.is_admin ? '✔' : '' }}</td>
          <td class="px-4 py-2 text-center">{{ u.is_allowed ? '✔' : '✗' }}</td>
          <td class="px-4 py-2">{{ u.last_login_at ?? '—' }}</td>
          <td class="px-4 py-2 text-right space-x-2">
            <button v-if="!u.is_admin" class="text-brand-500" @click="action(usersApi.promote, u.email, 'Promouvoir')">Promouvoir</button>
            <button v-else class="text-warning-600" @click="action(usersApi.demote, u.email, 'Rétrograder')">Rétrograder</button>
            <button v-if="u.is_allowed" class="text-error-600" @click="action(usersApi.block, u.email, 'Bloquer')">Bloquer</button>
            <button v-else class="text-success-600" @click="action(usersApi.unblock, u.email, 'Débloquer')">Débloquer</button>
            <button class="text-error-700" @click="action(usersApi.revoke, u.email, 'Révoquer toutes les sessions de')">Révoquer</button>
            <button class="text-gray-600" @click="router.push(`/admin/users/${encodeURIComponent(u.email)}/sessions`)">Sessions</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
```

- [ ] **Step 2: Type-check + commit**

```bash
npm run type-check
git add src/views/AdminUsersView.vue
git commit -m "feat(account-service-frontend): admin users list with actions / Liste des utilisateurs"
```

---

### Task 55: UserSessionsView, AuditLogView, MeView

**Files:**
- Create: `src/views/UserSessionsView.vue`
- Create: `src/views/AuditLogView.vue`
- Create: `src/views/MeView.vue`

- [ ] **Step 1: `UserSessionsView.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import * as usersApi from '@/api/users'

const route = useRoute()
const email = String(route.params.email)
const items = ref<usersApi.AdminSession[]>([])
const error = ref('')

async function load() {
  try { items.value = (await usersApi.listSessions(email)).items }
  catch (e) { error.value = e instanceof Error ? e.message : 'Erreur' }
}
async function revoke(sid: string) {
  if (!confirm('Révoquer cette session ?')) return
  try { await usersApi.revokeSession(sid); await load() }
  catch (e) { error.value = e instanceof Error ? e.message : 'Erreur' }
}
onMounted(load)
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Sessions de {{ email }}</h1>
    <div v-if="error" class="mb-4 p-3 bg-error-50 text-error-600 rounded">{{ error }}</div>
    <table class="w-full text-sm bg-white dark:bg-gray-900 rounded shadow">
      <thead class="bg-gray-100 dark:bg-gray-800">
        <tr>
          <th class="px-4 py-2 text-left">SID</th>
          <th class="px-4 py-2 text-left">Client</th>
          <th class="px-4 py-2 text-left">Créée</th>
          <th class="px-4 py-2 text-left">Expire</th>
          <th class="px-4 py-2">Révoquée</th>
          <th class="px-4 py-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in items" :key="s.id" class="border-t">
          <td class="px-4 py-2 font-mono">{{ s.sid.slice(0, 12) }}…</td>
          <td class="px-4 py-2">{{ s.client_id }}</td>
          <td class="px-4 py-2">{{ s.created_at }}</td>
          <td class="px-4 py-2">{{ s.expires_at }}</td>
          <td class="px-4 py-2 text-center">{{ s.revoked ? `oui (${s.revoked_reason})` : 'non' }}</td>
          <td class="px-4 py-2 text-right">
            <button v-if="!s.revoked" class="text-error-600" @click="revoke(s.sid)">Révoquer</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
```

- [ ] **Step 2: `AuditLogView.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as auditApi from '@/api/audit'
import type { AuditEntry } from '@/types/audit'

const items = ref<AuditEntry[]>([])
const total = ref(0)
const filterEvent = ref('')
const error = ref('')

async function load() {
  try {
    const r = await auditApi.list({ event: filterEvent.value || undefined }, 50, 0)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Journal d'audit ({{ total }})</h1>
    <div class="flex gap-2 mb-4">
      <select v-model="filterEvent" @change="load" class="h-10 px-3 border rounded">
        <option value="">— Tous les événements —</option>
        <option value="login">login</option>
        <option value="login_fail">login_fail</option>
        <option value="token_issue">token_issue</option>
        <option value="token_refresh">token_refresh</option>
        <option value="token_reuse_attack">token_reuse_attack</option>
        <option value="logout">logout</option>
        <option value="webhook_fired">webhook_fired</option>
        <option value="webhook_failed">webhook_failed</option>
      </select>
    </div>
    <div v-if="error" class="mb-4 p-3 bg-error-50 text-error-600 rounded">{{ error }}</div>
    <table class="w-full text-sm bg-white dark:bg-gray-900 rounded shadow">
      <thead class="bg-gray-100 dark:bg-gray-800">
        <tr>
          <th class="px-4 py-2 text-left">Date</th>
          <th class="px-4 py-2 text-left">Évènement</th>
          <th class="px-4 py-2 text-left">Acteur</th>
          <th class="px-4 py-2 text-left">Cible</th>
          <th class="px-4 py-2 text-left">Client</th>
          <th class="px-4 py-2 text-left">IP</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in items" :key="r.id" class="border-t">
          <td class="px-4 py-2 font-mono">{{ r.created_at }}</td>
          <td class="px-4 py-2 font-medium">{{ r.event }}</td>
          <td class="px-4 py-2">{{ r.actor_email }}</td>
          <td class="px-4 py-2">{{ r.target_email }}</td>
          <td class="px-4 py-2">{{ r.client_id }}</td>
          <td class="px-4 py-2">{{ r.ip_addr }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
```

- [ ] **Step 3: `MeView.vue`**

```vue
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="p-6 max-w-xl">
    <h1 class="text-2xl font-semibold mb-4">Mon profil</h1>
    <div class="bg-white dark:bg-gray-900 p-4 rounded shadow space-y-2">
      <p><strong>Email :</strong> {{ auth.user?.email }}</p>
      <p><strong>Nom :</strong> {{ auth.user?.display_name }}</p>
      <p><strong>Admin :</strong> {{ auth.user?.is_admin ? 'oui' : 'non' }}</p>
    </div>
    <button class="mt-4 px-4 py-2 bg-error-500 text-white rounded" @click="logout">
      Se déconnecter
    </button>
  </div>
</template>
```

- [ ] **Step 4: Type-check + commit**

```bash
npm run type-check
git add src/views/UserSessionsView.vue src/views/AuditLogView.vue src/views/MeView.vue
git commit -m "feat(account-service-frontend): sessions + audit + me views / Vues sessions, audit, profil"
```

---

## Phase 11 — Vitest + CI

### Task 56: Vitest setup + auth-store unit test

**Files:**
- Modify: `package.json`
- Create: `vitest.config.ts`
- Create: `src/stores/auth.spec.ts`

- [ ] **Step 1: Install Vitest**

```bash
npm install -D vitest@^2.1.0 @vue/test-utils@^2.4.0 jsdom@^25.0.0
```

- [ ] **Step 2: Add scripts to `package.json`**

```json
"scripts": {
  ...
  "test": "vitest run",
  "test:watch": "vitest"
}
```

- [ ] **Step 3: `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 4: Auth store test**

```ts
// src/stores/auth.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('login sets user on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ email: 'a@x', is_admin: true, is_allowed: true }),
    })
    // @ts-expect-error stub global
    globalThis.fetch = fetchMock

    const a = useAuthStore()
    await a.login('a', 'p')
    expect(a.isAuthenticated).toBe(true)
    expect(a.isAdmin).toBe(true)
  })

  it('login throws ApiError on 401', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: 'invalid_grant', error_description: 'bad creds' }),
    })
    // @ts-expect-error stub global
    globalThis.fetch = fetchMock
    const a = useAuthStore()
    await expect(a.login('a', 'wrong')).rejects.toThrow('Unauthorized')
  })
})
```

- [ ] **Step 5: Run + commit**

```bash
npm test
git add package.json package-lock.json vitest.config.ts src/stores/auth.spec.ts
git commit -m "test(account-service-frontend): Vitest setup + auth store tests / Mise en place Vitest"
```

---

### Task 57: GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci_account_service_backend.yml`
- Create: `.github/workflows/ci_account_service_frontend.yml`

- [ ] **Step 1: Backend CI**

```yaml
name: CI / account-service-backend

on:
  pull_request:
    paths:
      - 'apps-microservices/account-service-backend/**'
      - '.github/workflows/ci_account_service_backend.yml'
  push:
    branches: [main]
    paths:
      - 'apps-microservices/account-service-backend/**'

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
        options: --privileged
    defaults: { run: { working-directory: apps-microservices/account-service-backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with: { go-version: '1.24' }
      - run: go vet ./...
      - run: go test ./...
      - run: go test -tags=integration ./...
        env: { TESTCONTAINERS_RYUK_DISABLED: "true" }
      - name: Trivy
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: config
          scan-ref: apps-microservices/account-service-backend
```

- [ ] **Step 2: Frontend CI**

```yaml
name: CI / account-service-frontend

on:
  pull_request:
    paths:
      - 'apps-microservices/account-service-frontend/**'
      - '.github/workflows/ci_account_service_frontend.yml'
  push:
    branches: [main]
    paths:
      - 'apps-microservices/account-service-frontend/**'

jobs:
  build:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: apps-microservices/account-service-frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm ci
      - run: npm run lint
      - run: npm run type-check
      - run: npm test
      - run: npm run build
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci_account_service_backend.yml .github/workflows/ci_account_service_frontend.yml
git commit -m "ci(account-service): add CI workflows / Ajout des workflows CI"
```

---

## Phase 12 — Frontend Dockerfile + docker-compose entry

### Task 58: Frontend Dockerfile

**Files:**
- Create: `apps-microservices/account-service-frontend/Dockerfile`
- Create: `apps-microservices/account-service-frontend/.dockerignore`

- [ ] **Step 1: `.dockerignore`**

```
node_modules
.git
*.md
dist
.vscode
.dockerignore
```

- [ ] **Step 2: Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN rm -rf /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /src/dist /usr/share/nginx/html
RUN printf 'proxy_http_version 1.1;\nproxy_set_header Host $host;\nproxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\nproxy_set_header X-Forwarded-Proto $scheme;\nproxy_set_header X-Real-IP $remote_addr;\nproxy_read_timeout 30s;\n' > /etc/nginx/proxy.inc
EXPOSE 8601
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost:8601/ >/dev/null || exit 1
```

- [ ] **Step 3: Build**

```bash
docker build -t account-service-frontend:dev apps-microservices/account-service-frontend
```
Expected: image built successfully.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/account-service-frontend/Dockerfile apps-microservices/account-service-frontend/.dockerignore
git commit -m "feat(account-service-frontend): Dockerfile multi-stage / Dockerfile multi-étape"
```

---

### Task 59: docker-compose entry

**Files:**
- Modify: `docker-compose.yml` (root)

- [ ] **Step 1: Append the new services to the existing `docker-compose.yml`**

```yaml
  account-service-backend:
    build:
      context: ./apps-microservices/account-service-backend
    container_name: account-service-backend
    expose: ["8600"]
    env_file: .env
    environment:
      ACCOUNT_PORT: 8600
      ACCOUNT_PUBLIC_URL: ${ACCOUNT_PUBLIC_URL}
      MYSQL_DSN: ${ACCOUNT_MYSQL_DSN}
      ENCRYPTION_KEY: ${ACCOUNT_ENCRYPTION_KEY}
      JWT_SECRET: ${ACCOUNT_JWT_SECRET}
      JWT_AUDIENCE: ${ACCOUNT_JWT_AUDIENCE}
      AUTH_URL: ${HELLOPRO_AUTH_URL}
      ADMIN_EMAILS: ${ACCOUNT_ADMIN_EMAILS}
      OAUTH2_DEFAULT_TOKEN_TTL: ${OAUTH2_DEFAULT_TOKEN_TTL:-60}
      OAUTH2_DEFAULT_REFRESH_TTL: ${OAUTH2_DEFAULT_REFRESH_TTL:-2592000}
      OAUTH2_AUTH_CODE_TTL: ${OAUTH2_AUTH_CODE_TTL:-600}
      LOGOUT_WEBHOOK_TIMEOUT: ${LOGOUT_WEBHOOK_TIMEOUT:-5}
      LOGOUT_WEBHOOK_RETRIES: ${LOGOUT_WEBHOOK_RETRIES:-3}
      SECURE_COOKIE: "true"
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
    depends_on:
      mysql:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8600/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  account-service-frontend:
    build:
      context: ./apps-microservices/account-service-frontend
    container_name: account-service-frontend
    ports:
      - "${ACCOUNT_FRONTEND_PORT:-8601}:8601"
    depends_on:
      - account-service-backend
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
```

- [ ] **Step 2: Add a sample `.env` block (don't commit secrets — just shape)**

Append to `.env.example` (or create one if missing):

```
# Account Service
ACCOUNT_PUBLIC_URL=https://account.example.com
ACCOUNT_MYSQL_DSN=account:account@tcp(mysql:3306)/account_db?parseTime=true
ACCOUNT_ENCRYPTION_KEY=                       # 32-byte hex (openssl rand -hex 32)
ACCOUNT_JWT_SECRET=                           # 32-byte hex
ACCOUNT_JWT_AUDIENCE=https://www.hellopro.fr
HELLOPRO_AUTH_URL=https://www.hellopro.fr/login
ACCOUNT_ADMIN_EMAILS=admin1@hellopro.fr,admin2@hellopro.fr
ACCOUNT_FRONTEND_PORT=8601
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat(account-service): docker-compose entry / Entrée docker-compose"
```

---

### Task 60: Final integration smoke test

**Files:**
- N/A (runbook only — copy into PR description)

- [ ] **Step 1: Bring up the stack**

```bash
docker compose up -d mysql account-service-backend account-service-frontend
docker compose logs -f account-service-backend &
```
Expected: backend logs `auto migrate ok`, `listening 8600`. Frontend container healthy.

- [ ] **Step 2: Hit health & metadata**

```bash
curl -fsS http://localhost:8601/api/v1/admin/services -i        # 401 expected (no session)
curl -fsS http://localhost:8601/.well-known/oauth-authorization-server | jq
```

- [ ] **Step 3: Login as admin via UI**

Open `http://localhost:8601/login` in a browser. Use a hellopro.fr-valid email
that you put into `ACCOUNT_ADMIN_EMAILS`. After login, you land on
`/admin/services`. Click "Nouveau service", fill the form with one redirect URI
(e.g. `https://example.com/cb`) and a logout webhook (e.g. `https://webhook.site/...`).
Save. Copy the `client_id` + `client_secret` from the modal.

- [ ] **Step 4: Run the full PKCE flow against the new client**

```bash
CLIENT_ID="<from UI>"
CLIENT_SECRET="<from UI>"
VERIFIER=$(openssl rand -hex 32)
CHALLENGE=$(echo -n "$VERIFIER" | openssl dgst -sha256 -binary | base64 | tr '/+' '_-' | tr -d '=')
echo "open: http://localhost:8601/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=https://example.com/cb&code_challenge=$CHALLENGE&code_challenge_method=S256&state=demo"
```
Open the URL. The login form should appear. Submit creds. The browser will
redirect to `https://example.com/cb?code=…&state=demo`. Copy the `code` param.

```bash
CODE="<from redirect>"
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
     -d grant_type=authorization_code \
     -d code="$CODE" \
     -d redirect_uri=https://example.com/cb \
     -d code_verifier="$VERIFIER" \
     http://localhost:8601/token | jq
```
Expected: `{access_token, token_type:"Bearer", expires_in:60, refresh_token}`.

- [ ] **Step 5: Test refresh + reuse detection**

```bash
REFRESH="<from previous>"
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
     -d grant_type=refresh_token \
     -d refresh_token="$REFRESH" \
     http://localhost:8601/token | jq        # success — new tokens
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
     -d grant_type=refresh_token \
     -d refresh_token="$REFRESH" \
     http://localhost:8601/token | jq        # expected: {"error":"invalid_grant"}
```
Verify the chain is now revoked: in the UI, `Admin → Audit` should show a
`token_reuse_attack` event, and `User → Sessions` should show all sessions for
that user as `revoked`.

- [ ] **Step 6: Test back-channel logout**

In the UI, click `Révoquer` next to the logged-in user. Watch the
`webhook.site` URL (or whatever logout webhook you registered). A POST should
arrive with header `X-Logout-Signature: sha256=…` and a JSON body containing
`sub`, `sid`, `iat`, `events`. Verify the signature matches `HMAC_SHA256(client_secret, body)`.

- [ ] **Step 7: Document the smoke run**

Capture the curl outputs and the audit events (screenshots OK) and paste them
into the PR description on `feature/account-service-backend`. Open the PR.
Repeat for the frontend branch.

- [ ] **Step 8: Commit (the runbook lives in this plan; no code change)**

No code commit needed. This step is the verification gate — once it passes,
the implementation is done.

---

## Self-Review

Reviewed against `docs/superpowers/specs/2026-05-04-account-service-sso-design.md`:

**Spec coverage:**
- Architecture (Tasks 42, 59).
- Trust model + hellopro.fr proxy (Tasks 8, 18, 27).
- AES-256-GCM secret encryption (Tasks 5, 31, 36).
- HS256 JWT + session cookies (Tasks 6, 7, 17).
- Skip-consent OAuth2 flow (Task 27).
- PKCE S256 (Tasks 21, 28).
- Refresh rotation + reuse detection (Tasks 14, 29).
- RFC 7591 dynamic registration (Task 31).
- RFC 7662 introspection + 7009 revoke (Task 30).
- RFC 8414 metadata (Task 25).
- Branding endpoint (Task 23).
- Claim mappings (Tasks 24, 28).
- Logout webhook with HMAC + retries + persisted queue (Tasks 32–35).
- Admin REST API: services CRUD, users, sessions, audit (Tasks 36–40).
- Health + Prometheus metrics + slog (Task 41).
- Frontend: clone TailAdmin, prune, Pinia, router, dual-mode login, branding fetch, admin views (Tasks 44–55).
- CI workflows (Task 57).
- Docker + docker-compose (Tasks 43, 58, 59).
- Final smoke test runbook covering full PKCE + refresh + reuse + logout (Task 60).

**Placeholder scan:** None of the disallowed patterns ("TBD", "fill in details",
"similar to Task N", etc.) remain. Every implementation step shows full code
or a complete shell snippet.

**Type consistency:**
- `auth.UserUpserter` interface declared in Task 18 and reused by Task 27 +
  Task 42 wiring via `auth.UserUpserterFunc`.
- `RefreshRepo` (Task 14) provides both the `RefreshSink` and `RefreshRotator`
  interfaces required by Task 28/29; `ListBySID` exposed for the introspect
  type-assertion in Task 30.
- `EncryptFunc` / `DecryptFunc` shape is identical between
  `internal/api/admin_service_handlers.go` (Task 36) and
  `internal/authserver/{token_endpoint,introspect,register}.go` (Tasks 28, 30,
  31). Both bind to `crypto.Cipher.Encrypt` / `Decrypt` in `main.go` (Task 42).
- `db.OAuth2Client.RedirectURIs|AllowedRoles|ClaimMappings` are `*string`
  (JSON column) consistently used by `redactClient`, `isRegisteredRedirectURI`,
  and the `ClaimMapperEditor` view.

**Scope check:** This is one plan covering both services so they ship together.
Each phase ends in a working state (backend after Phase 7, frontend after
Phase 11), and Phase 12 plus the smoke runbook close the deployment loop.

**Ambiguity check:** The two places that previously had multiple readings —
how the introspect handler looks up `sid` (resolved by the type-assertion +
`RefreshRepo.ListBySID`), and how admin "revoke all sessions" maps to a
back-channel logout (resolved by `userBroadcastAdapter` in Task 42 sending
`sid=""` and the spec note that clients must treat that as "all sessions for
sub") — are now explicit.

---

## Plan complete. Saved to:

`docs/superpowers/plans/2026-05-04-account-service-sso.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks. Good for a 60-task plan because each task is self-contained.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
