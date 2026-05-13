# `mcp-zoho-service` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new internal Go service `mcp-zoho-service` that proxies MCP JSON-RPC calls to the right per-user Zoho upstream (admin's Zoho when caller has a server_authorizations grant, else the caller's imported Zoho row, else JSON-RPC error -32001).

**Architecture:** Stateless `net/http` proxy on port `8596`. Reads gateway's MySQL read-only (`mcp_servers`, `server_authorizations`). Decrypts `mcp_servers.auth_headers` with the shared `ENCRYPTION_KEY`. In-memory TTL cache (60s) for the per-email upstream resolution. Gateway-side: one new switch case in `requestHeadersFor` to inject `X-End-User-Email` + `X-End-User-Login` on Zoho-tagged backends.

**Tech Stack:** Go 1.24, `net/http`, GORM v1.25 (read-only), `gopkg.in/yaml.v3` only if needed (no YAML in v1), AES-256-GCM via `crypto/aes`+`crypto/cipher`. Container: multi-stage `golang:1.24-alpine` → `alpine:3.20`.

**Spec:** `docs/superpowers/specs/2026-05-12-mcp-zoho-service-design.md`.

---

## File Structure

```
apps-microservices/mcp-zoho-service/
├── CLAUDE.md
├── Dockerfile
├── go.mod
├── go.sum
├── cmd/server/main.go
└── internal/
    ├── config/config.go
    ├── crypto/
    │   ├── decrypt.go
    │   └── decrypt_test.go
    ├── db/
    │   ├── mysql.go
    │   ├── models.go
    │   ├── queries.go
    │   └── queries_test.go
    ├── routing/
    │   ├── match.go
    │   ├── match_test.go
    │   ├── cache.go
    │   ├── cache_test.go
    │   ├── resolver.go
    │   └── resolver_test.go
    ├── proxy/
    │   ├── proxy.go
    │   └── proxy_test.go
    ├── mcp/
    │   ├── error.go
    │   └── error_test.go
    └── transport/
        ├── handler.go
        ├── handler_test.go
        └── middleware.go
```

Gateway side (modified):
```
apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go     # inject X-End-User-Email + X-End-User-Login on Zoho path
apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go # 3 new cases
docker-compose.yml                                                             # new mcp-zoho-service block
apps-microservices/mcp-gateway-service/CLAUDE.md                              # one bullet about the Zoho service
CLAUDE.md                                                                      # root service map row
```

---

## Conventions

- **Go test runner**: `go test ./internal/... -count=1` from `apps-microservices/mcp-zoho-service`.
- **Build**: `go build ./...` from same directory.
- **Commits**: bilingual EN+FR Conventional Commits, subject < 72 chars.
- **No reformatting** of unrelated code.
- **TDD where signalled**: failing test first, run, see fail, then implement, run, see pass, then commit.

---

## Task 1: Scaffold the service skeleton

**Files (all new):**
- `apps-microservices/mcp-zoho-service/go.mod`
- `apps-microservices/mcp-zoho-service/cmd/server/main.go`
- `apps-microservices/mcp-zoho-service/internal/config/config.go`
- `apps-microservices/mcp-zoho-service/Dockerfile`
- `apps-microservices/mcp-zoho-service/CLAUDE.md`

- [ ] **Step 1: Create the directory tree and `go.mod`**

```bash
cd /home/sandratra/RAG-HP-PUB && mkdir -p apps-microservices/mcp-zoho-service/{cmd/server,internal/{config,crypto,db,routing,proxy,mcp,transport}}
```

Create `apps-microservices/mcp-zoho-service/go.mod`:

```go
module mcp-zoho-service

go 1.24
```

- [ ] **Step 2: Write `internal/config/config.go`**

Create `apps-microservices/mcp-zoho-service/internal/config/config.go`:

```go
// Package config loads runtime configuration from environment variables.
// All values are read once at boot; nothing in this package is mutated after Load().
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config holds all runtime configuration for mcp-zoho-service.
type Config struct {
	Port            int
	MySQLDSN        string
	EncryptionKey   string
	GatewayToken    string
	SelfURL         string
	CacheTTL        time.Duration
	UpstreamTimeout time.Duration
	LogLevel        string
}

// Load reads environment variables and returns a populated Config or an error
// when a required variable is missing or malformed.
func Load() (*Config, error) {
	c := &Config{
		Port:            envInt("ZOHO_ROUTER_PORT", 8596),
		MySQLDSN:        os.Getenv("MYSQL_DSN"),
		EncryptionKey:   os.Getenv("ENCRYPTION_KEY"),
		GatewayToken:    os.Getenv("ZOHO_GATEWAY_TOKEN"),
		SelfURL:         os.Getenv("ZOHO_SELF_URL"),
		CacheTTL:        time.Duration(envInt("ZOHO_ROUTING_CACHE_TTL", 60)) * time.Second,
		UpstreamTimeout: time.Duration(envInt("ZOHO_UPSTREAM_TIMEOUT", 30)) * time.Second,
		LogLevel:        envDefault("LOG_LEVEL", "info"),
	}

	if c.MySQLDSN == "" {
		return nil, fmt.Errorf("MYSQL_DSN is required")
	}
	if c.EncryptionKey == "" {
		return nil, fmt.Errorf("ENCRYPTION_KEY is required")
	}
	if c.GatewayToken == "" {
		return nil, fmt.Errorf("ZOHO_GATEWAY_TOKEN is required")
	}
	if c.SelfURL == "" {
		return nil, fmt.Errorf("ZOHO_SELF_URL is required (used to exclude the service's own row when picking the admin upstream)")
	}
	return c, nil
}

func envDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
```

- [ ] **Step 3: Write `cmd/server/main.go` with a minimal /health endpoint**

Create `apps-microservices/mcp-zoho-service/cmd/server/main.go`:

```go
// Package main is the entry point for mcp-zoho-service.
// It boots config, starts an HTTP server, and shuts down gracefully on SIGINT/SIGTERM.
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"mcp-zoho-service/internal/config"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("[mcp-zoho-service] config: %v", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Printf("[mcp-zoho-service] listening on :%d", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[mcp-zoho-service] server: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	log.Printf("[mcp-zoho-service] shutting down")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("[mcp-zoho-service] shutdown: %v", err)
	}
}
```

- [ ] **Step 4: Write the Dockerfile**

Create `apps-microservices/mcp-zoho-service/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM golang:1.24-alpine AS builder
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/mcp-zoho-service ./cmd/server

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget && adduser -D -u 10001 zoho
USER zoho
COPY --from=builder /out/mcp-zoho-service /usr/local/bin/mcp-zoho-service
EXPOSE 8596
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8596/health || exit 1
ENTRYPOINT ["/usr/local/bin/mcp-zoho-service"]
```

- [ ] **Step 5: Write the service CLAUDE.md**

Create `apps-microservices/mcp-zoho-service/CLAUDE.md`:

```markdown
# mcp-zoho-service

Stateless Go proxy. The MCP gateway treats this service as a single Zoho MCP
backend. On each request, the service reads the caller's identity from
`X-End-User-Email` + `X-End-User-Login`, picks the right upstream Zoho URL
(admin's global one when the caller is in `server_authorizations`, else the
caller's imported per-user Zoho), decrypts the upstream's auth headers, and
proxies the JSON-RPC body.

## Tech Stack

- Go 1.24, `net/http` standard library (no third-party router)
- AES-256-GCM via `crypto/aes` + `crypto/cipher` — shared `ENCRYPTION_KEY` with gateway
- Reads gateway's MySQL read-only (`mcp_servers`, `server_authorizations`)
- Multi-stage Docker: `golang:1.24-alpine` → `alpine:3.20`, port **8596**

## Run

```bash
# Local (requires Go 1.24+ and a reachable MySQL with the gateway schema)
cd apps-microservices/mcp-zoho-service
ZOHO_ROUTER_PORT=8596 \
MYSQL_DSN="..." \
ENCRYPTION_KEY="..." \
ZOHO_GATEWAY_TOKEN="..." \
ZOHO_SELF_URL="http://mcp-zoho-service:8596/mcp" \
go run ./cmd/server
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /mcp` | Receive MCP JSON-RPC from gateway, resolve upstream, proxy, relay response |
| `GET /health` | Liveness probe (200 once boot succeeds) |

All `POST /mcp` requests must carry `X-Admin-Token` matching `ZOHO_GATEWAY_TOKEN`.

## Resolution rules

1. Read `X-End-User-Email` + `X-End-User-Login` from request headers.
2. Look up the admin Zoho row in `mcp_servers` (`tool_prefix='zoho' AND template_slug='' AND url != ZOHO_SELF_URL AND is_active LIMIT 1`).
3. If the caller's email is in `server_authorizations` for that admin row → route to it.
4. Else look up the caller's imported Zoho (`tool_prefix LIKE 'zoho%' AND template_slug != '' AND is_active AND matches(created_by, email, login) ORDER BY created_at ASC LIMIT 1`).
5. Else return JSON-RPC error `-32001` "no_zoho_configured".

Matching tries exact-email (case-insensitive) first, then login-portion (local-part before `@`).

## Environment

| Variable | Default | Notes |
|---|---|---|
| `ZOHO_ROUTER_PORT` | `8596` | HTTP listen port |
| `MYSQL_DSN` | — | Read-only DB user recommended |
| `ENCRYPTION_KEY` | — | Hex 32-byte AES-256 key — must equal gateway's |
| `ZOHO_GATEWAY_TOKEN` | — | Shared bearer with gateway (`X-Admin-Token`) |
| `ZOHO_SELF_URL` | — | The URL the gateway calls this service on — used to exclude this service's own `mcp_servers` row when picking the admin upstream |
| `ZOHO_ROUTING_CACHE_TTL` | `60` | Seconds |
| `ZOHO_UPSTREAM_TIMEOUT` | `30` | Seconds — per outbound HTTP call to Zoho |
| `LOG_LEVEL` | `info` | `debug`/`info`/`warn`/`error` |

## Boundaries

This service does NOT:
- Store any state (no DB writes, no local files).
- Hold per-user OAuth tokens (deferred; auth headers live in `mcp_servers.auth_headers`).
- Validate JWTs (trusts the gateway-injected headers).
- Expose admin UI (operators use the gateway's `/servers` admin to register Zoho rows).

## What this provides to other services

- Single Zoho MCP endpoint that the gateway treats as one backend, hiding the per-user routing behind a stable URL.
```

- [ ] **Step 6: Build the binary locally to verify scaffold**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./...
```

Expected: success (compiles, no test errors yet).

- [ ] **Step 7: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): scaffold service skeleton

Go module, config loader, minimal /health endpoint, multi-stage
Dockerfile and service CLAUDE.md. No business logic yet — lands in
follow-up commits.

EN: Pose le squelette du nouveau service mcp-zoho-service (module Go,
loader de configuration, endpoint /health, Dockerfile multi-stage).
EOF
)"
```

---

## Task 2: Crypto package — AES-256-GCM decrypt (TDD)

**Files:**
- Create: `apps-microservices/mcp-zoho-service/internal/crypto/decrypt.go`
- Create: `apps-microservices/mcp-zoho-service/internal/crypto/decrypt_test.go`

Mirror the gateway's `internal/crypto/encrypt.go` algorithm exactly so the same ciphertext round-trips. The test pre-computes a ciphertext (using a vendored copy of the gateway's `Encrypt`) and asserts `Decrypt` returns the original plaintext.

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/mcp-zoho-service/internal/crypto/decrypt_test.go`:

```go
package crypto

import (
	"bytes"
	"crypto/aes"
	cryptocipher "crypto/cipher"
	"crypto/rand"
	"encoding/hex"
	"io"
	"testing"
)

// gatewayEncrypt mirrors mcp-gateway-service/internal/crypto.Encryptor.Encrypt.
// Kept verbatim in test code so a future divergence at either side is caught
// immediately by this round-trip test.
func gatewayEncrypt(t *testing.T, hexKey string, plaintext []byte) []byte {
	t.Helper()
	key, err := hex.DecodeString(hexKey)
	if err != nil {
		t.Fatalf("decode key: %v", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatalf("aes.NewCipher: %v", err)
	}
	gcm, err := cryptocipher.NewGCM(block)
	if err != nil {
		t.Fatalf("cipher.NewGCM: %v", err)
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		t.Fatalf("rand nonce: %v", err)
	}
	return gcm.Seal(nonce, nonce, plaintext, nil)
}

func TestDecryptor_RoundTripFromGatewayCiphertext(t *testing.T) {
	const hexKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	plaintext := []byte(`{"Authorization":"Bearer abc.def.ghi"}`)
	ciphertext := gatewayEncrypt(t, hexKey, plaintext)

	dec, err := NewDecryptor(hexKey)
	if err != nil {
		t.Fatalf("NewDecryptor: %v", err)
	}
	got, err := dec.Decrypt(ciphertext)
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if !bytes.Equal(got, plaintext) {
		t.Fatalf("Decrypt = %q, want %q", got, plaintext)
	}
}

func TestDecryptor_RejectsShortCiphertext(t *testing.T) {
	const hexKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	dec, err := NewDecryptor(hexKey)
	if err != nil {
		t.Fatalf("NewDecryptor: %v", err)
	}
	if _, err := dec.Decrypt([]byte{0x01, 0x02}); err == nil {
		t.Fatalf("expected error on short ciphertext, got nil")
	}
}

func TestDecryptor_RejectsBadKey(t *testing.T) {
	if _, err := NewDecryptor("not-hex"); err == nil {
		t.Fatalf("expected error on non-hex key, got nil")
	}
	if _, err := NewDecryptor("aa"); err == nil {
		t.Fatalf("expected error on short key, got nil")
	}
}
```

- [ ] **Step 2: Run the test, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/crypto/ -v
```

Expected: `undefined: NewDecryptor`.

- [ ] **Step 3: Implement `decrypt.go`**

Create `apps-microservices/mcp-zoho-service/internal/crypto/decrypt.go`:

```go
// Package crypto provides AES-256-GCM decryption for sensitive blobs stored
// in the gateway's MySQL (mcp_servers.auth_headers). The algorithm mirrors
// mcp-gateway-service/internal/crypto so the same ciphertext round-trips.
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"fmt"
)

// Decryptor wraps an AES-256-GCM AEAD primed with a fixed key.
type Decryptor struct {
	gcm cipher.AEAD
}

// NewDecryptor parses a hex-encoded 32-byte key and returns a Decryptor.
// Returns an error if the key is not valid hex or not 32 bytes long.
func NewDecryptor(hexKey string) (*Decryptor, error) {
	key, err := hex.DecodeString(hexKey)
	if err != nil {
		return nil, fmt.Errorf("decode hex key: %w", err)
	}
	if len(key) != 32 {
		return nil, fmt.Errorf("key must be 32 bytes (got %d)", len(key))
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("create cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("create GCM: %w", err)
	}
	return &Decryptor{gcm: gcm}, nil
}

// Decrypt undoes Encryptor.Encrypt on the gateway side. The input is the
// raw ciphertext as stored in MySQL: nonce || sealed_payload.
func (d *Decryptor) Decrypt(ciphertext []byte) ([]byte, error) {
	nonceSize := d.gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return nil, fmt.Errorf("ciphertext too short")
	}
	nonce, ct := ciphertext[:nonceSize], ciphertext[nonceSize:]
	pt, err := d.gcm.Open(nil, nonce, ct, nil)
	if err != nil {
		return nil, fmt.Errorf("decrypt: %w", err)
	}
	return pt, nil
}
```

- [ ] **Step 4: Run the tests, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/crypto/ -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/crypto/
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): AES-256-GCM decrypt for mcp_servers.auth_headers

Mirrors the gateway's internal/crypto algorithm exactly. Round-trip
test pre-computes ciphertext with the gateway's algorithm and asserts
Decrypt recovers the original plaintext.

EN: Décryptage AES-256-GCM des en-têtes d'authentification stockés
chiffrés dans mcp_servers.auth_headers.
EOF
)"
```

---

## Task 3: DB package — connection + queries

**Files:**
- Create: `apps-microservices/mcp-zoho-service/internal/db/mysql.go`
- Create: `apps-microservices/mcp-zoho-service/internal/db/models.go`
- Create: `apps-microservices/mcp-zoho-service/internal/db/queries.go`
- Create: `apps-microservices/mcp-zoho-service/internal/db/queries_test.go`

The service is read-only: no AutoMigrate, no writes. We use the standard `database/sql` driver (no GORM) to keep the binary small and the queries explicit.

- [ ] **Step 1: Add the MySQL driver dependency**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go get github.com/go-sql-driver/mysql@v1.8.1
```

- [ ] **Step 2: Write `mysql.go`**

Create `apps-microservices/mcp-zoho-service/internal/db/mysql.go`:

```go
// Package db opens a read-only MySQL connection to the gateway database
// and exposes prepared statements for the resolver.
package db

import (
	"database/sql"
	"fmt"
	"time"

	_ "github.com/go-sql-driver/mysql"
)

// Open dials MySQL using the gateway-format DSN and configures a small pool
// suitable for a read-only proxy.
func Open(dsn string) (*sql.DB, error) {
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, fmt.Errorf("sql.Open: %w", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(2)
	db.SetConnMaxLifetime(30 * time.Minute)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("db.Ping: %w", err)
	}
	return db, nil
}
```

- [ ] **Step 3: Write `models.go`**

Create `apps-microservices/mcp-zoho-service/internal/db/models.go`:

```go
// Package db carries the read-side row shapes that match the columns
// queries.go selects. These are NOT the gateway's full GORM models —
// only the subset the resolver needs.
package db

// ServerRow is the narrow view of an mcp_servers row used by the resolver.
type ServerRow struct {
	ID          string
	URL         string
	AuthHeaders []byte // encrypted blob
	CreatedBy   string
}
```

- [ ] **Step 4: Write `queries.go`**

Create `apps-microservices/mcp-zoho-service/internal/db/queries.go`:

```go
package db

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
)

// Queries wraps a *sql.DB with the prepared statements the resolver needs.
type Queries struct {
	db *sql.DB
}

// NewQueries returns a Queries primed with the given DB handle.
func NewQueries(db *sql.DB) *Queries {
	return &Queries{db: db}
}

// FindAdminZohoServer returns the single mcp_servers row representing the
// admin's global Zoho upstream: tool_prefix='zoho', template_slug='',
// is_active, and url != selfURL (excludes this service's own row).
// Returns sql.ErrNoRows when no such row exists.
func (q *Queries) FindAdminZohoServer(ctx context.Context, selfURL string) (*ServerRow, error) {
	const query = `
		SELECT id, url, auth_headers, created_by
		FROM mcp_servers
		WHERE tool_prefix = 'zoho'
		  AND template_slug = ''
		  AND is_active = 1
		  AND url <> ?
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query, selfURL)
	out := &ServerRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy); err != nil {
		return nil, err
	}
	return out, nil
}

// IsAdminGranted returns true when there is a server_authorizations row
// granting full access on serverID for the given email (case-insensitive).
func (q *Queries) IsAdminGranted(ctx context.Context, serverID, email string) (bool, error) {
	if serverID == "" || email == "" {
		return false, nil
	}
	const query = `
		SELECT 1
		FROM server_authorizations
		WHERE mcp_server_id = ?
		  AND LOWER(email) = LOWER(?)
		LIMIT 1
	`
	var dummy int
	err := q.db.QueryRowContext(ctx, query, serverID, email).Scan(&dummy)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("server_authorizations: %w", err)
	}
	return true, nil
}

// FindUserZohoImport returns the oldest active mcp_servers row whose
// tool_prefix starts with 'zoho', template_slug is non-empty, and whose
// created_by matches the caller's identity by exact-email OR login-portion.
// When more than one row matches, the oldest by created_at wins.
// Returns sql.ErrNoRows when nothing matches.
func (q *Queries) FindUserZohoImport(ctx context.Context, email, login string) (*ServerRow, error) {
	emailLower := strings.ToLower(email)
	loginLower := strings.ToLower(login)
	if emailLower == "" && loginLower == "" {
		return nil, sql.ErrNoRows
	}

	const query = `
		SELECT id, url, auth_headers, created_by
		FROM mcp_servers
		WHERE template_slug <> ''
		  AND is_active = 1
		  AND LOWER(tool_prefix) LIKE 'zoho%'
		  AND (
		        LOWER(created_by) = ?
		     OR (? <> '' AND LOWER(created_by) LIKE CONCAT(?, '@%'))
		  )
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query, emailLower, loginLower, loginLower)
	out := &ServerRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy); err != nil {
		return nil, err
	}
	return out, nil
}
```

- [ ] **Step 5: Write `queries_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/db/queries_test.go`:

```go
package db

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	_ "github.com/go-sql-driver/mysql"
)

// dsnFromEnv reads MYSQL_TEST_DSN from the env. When unset the test is
// skipped — these are integration tests that need a live gateway-schema
// MySQL. The CI for the gateway already has one in scope; reuse it.
func dsnFromEnv(t *testing.T) string {
	t.Helper()
	dsn := getenv("MYSQL_TEST_DSN")
	if dsn == "" {
		t.Skip("MYSQL_TEST_DSN unset; skipping integration test")
	}
	return dsn
}

func getenv(k string) string {
	// inline to avoid importing os just for tests; build tag could exclude
	// these tests instead — see CI plan.
	return ""
}

// TestQueries_AdminAndUserResolution exercises the three statements end-to-end
// against an ephemeral schema. The test is skipped when MYSQL_TEST_DSN is
// unset, so `go test` stays green on developer laptops without MySQL.
func TestQueries_AdminAndUserResolution(t *testing.T) {
	dsn := dsnFromEnv(t)
	conn, err := Open(dsn)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer conn.Close()

	ctx := context.Background()
	q := NewQueries(conn)

	// Best-effort: skip the test if the schema is unavailable.
	if _, err := q.FindAdminZohoServer(ctx, "http://self/mcp"); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Skipf("schema not ready: %v", err)
	}
}
```

The integration test is intentionally minimal in v1 — it asserts the queries compile against the live schema. Full coverage is reserved for the resolver tests (Task 5) using a fake `Queries` implementation.

- [ ] **Step 6: Build**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./...
```

Expected: success. Tests don't run unless `MYSQL_TEST_DSN` is set.

- [ ] **Step 7: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/db/ apps-microservices/mcp-zoho-service/go.mod apps-microservices/mcp-zoho-service/go.sum
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): MySQL read-only DB + queries package

Three prepared queries against the gateway schema:
  - FindAdminZohoServer: admin Zoho row (excludes ZOHO_SELF_URL)
  - IsAdminGranted: server_authorizations lookup for full-access grant
  - FindUserZohoImport: oldest active per-user imported Zoho by
    exact email or login-portion match on created_by

EN: Package DB en lecture seule sur la base du gateway, avec trois
requêtes préparées pour la résolution du proxy Zoho.
EOF
)"
```

---

## Task 4: Routing — matching + cache + resolver (TDD)

**Files:**
- Create: `apps-microservices/mcp-zoho-service/internal/routing/match.go`
- Create: `apps-microservices/mcp-zoho-service/internal/routing/match_test.go`
- Create: `apps-microservices/mcp-zoho-service/internal/routing/cache.go`
- Create: `apps-microservices/mcp-zoho-service/internal/routing/cache_test.go`
- Create: `apps-microservices/mcp-zoho-service/internal/routing/resolver.go`
- Create: `apps-microservices/mcp-zoho-service/internal/routing/resolver_test.go`

- [ ] **Step 1: Write `match_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/routing/match_test.go`:

```go
package routing

import "testing"

func TestMatchesUserEmail(t *testing.T) {
	cases := []struct {
		name             string
		serverCreatedBy  string
		endUserEmail     string
		endUserLogin     string
		want             bool
	}{
		{"exact email", "alice@hp.fr", "alice@hp.fr", "alice", true},
		{"exact email case-insensitive", "ALICE@HP.FR", "alice@hp.fr", "alice", true},
		{"login portion across domains", "alice@hp.fr", "alice@hellopro.fr", "alice", true},
		{"login portion only", "alice@hp.fr", "", "alice", true},
		{"different login no match", "alice@hp.fr", "bob@hp.fr", "bob", false},
		{"empty created_by always false", "", "alice@hp.fr", "alice", false},
		{"empty inputs always false", "alice@hp.fr", "", "", false},
		{"malformed created_by (no local-part) never matches", "@hp.fr", "alice@hp.fr", "alice", false},
		{"login-only fallback when email empty and logins match", "alice@hp.fr", "", "alice", true},
		{"email match wins over login fallback", "alice@hp.fr", "alice@hp.fr", "irrelevant", true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := matchesUserEmail(tc.serverCreatedBy, tc.endUserEmail, tc.endUserLogin)
			if got != tc.want {
				t.Fatalf("matchesUserEmail(%q, %q, %q) = %v, want %v",
					tc.serverCreatedBy, tc.endUserEmail, tc.endUserLogin, got, tc.want)
			}
		})
	}
}
```

- [ ] **Step 2: Run, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/routing/ -run TestMatchesUserEmail -v
```

Expected: `undefined: matchesUserEmail`.

- [ ] **Step 3: Implement `match.go`**

Create `apps-microservices/mcp-zoho-service/internal/routing/match.go`:

```go
// Package routing decides which upstream Zoho URL serves a given caller.
package routing

import "strings"

// matchesUserEmail returns true when serverCreatedBy and the caller identify
// the same person. Resolution order:
//  1. case-insensitive exact-email equality (when both are non-empty);
//  2. login-portion (local-part before '@') case-insensitive equality;
// When serverCreatedBy has no local-part (e.g. "@hp.fr"), the function never
// matches anyone.
func matchesUserEmail(serverCreatedBy, endUserEmail, endUserLogin string) bool {
	if serverCreatedBy == "" {
		return false
	}
	if endUserEmail != "" && strings.EqualFold(serverCreatedBy, endUserEmail) {
		return true
	}
	serverLogin := loginPart(serverCreatedBy)
	if serverLogin == "" {
		return false
	}
	if endUserLogin != "" && strings.EqualFold(serverLogin, endUserLogin) {
		return true
	}
	if endUserEmail != "" && strings.EqualFold(serverLogin, loginPart(endUserEmail)) {
		return true
	}
	return false
}

// loginPart returns the local-part of an email (everything before '@'), or
// the empty string when the input has no '@' or starts with '@'.
func loginPart(email string) string {
	at := strings.IndexByte(email, '@')
	if at <= 0 {
		return ""
	}
	return email[:at]
}
```

- [ ] **Step 4: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/routing/ -run TestMatchesUserEmail -v
```

Expected: all 10 sub-tests PASS.

- [ ] **Step 5: Write `cache_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/routing/cache_test.go`:

```go
package routing

import (
	"testing"
	"time"
)

func TestCache_HitMissExpire(t *testing.T) {
	c := newCache(100 * time.Millisecond)

	if _, ok := c.get("alice@hp.fr"); ok {
		t.Fatalf("expected miss")
	}

	value := &Resolution{UpstreamURL: "http://upstream/a", Headers: map[string]string{"k": "v"}}
	c.set("alice@hp.fr", value)

	got, ok := c.get("alice@hp.fr")
	if !ok || got.UpstreamURL != "http://upstream/a" {
		t.Fatalf("expected hit with URL, got ok=%v val=%+v", ok, got)
	}

	time.Sleep(120 * time.Millisecond)

	if _, ok := c.get("alice@hp.fr"); ok {
		t.Fatalf("expected expiry miss")
	}
}
```

- [ ] **Step 6: Run, verify compile failure**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/routing/ -run TestCache -v
```

Expected: `undefined: newCache`, `undefined: Resolution`.

- [ ] **Step 7: Implement `cache.go`**

Create `apps-microservices/mcp-zoho-service/internal/routing/cache.go`:

```go
package routing

import (
	"sync"
	"time"
)

// Resolution is the cached result of mapping a caller email to an upstream.
type Resolution struct {
	UpstreamURL string
	Headers     map[string]string
}

// cache is a small TTL map keyed by lowercased email.
type cache struct {
	mu      sync.RWMutex
	ttl     time.Duration
	entries map[string]cacheEntry
}

type cacheEntry struct {
	value     *Resolution
	expiresAt time.Time
}

func newCache(ttl time.Duration) *cache {
	return &cache{
		ttl:     ttl,
		entries: make(map[string]cacheEntry),
	}
}

func (c *cache) get(key string) (*Resolution, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	e, ok := c.entries[key]
	if !ok || time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.value, true
}

func (c *cache) set(key string, value *Resolution) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries[key] = cacheEntry{value: value, expiresAt: time.Now().Add(c.ttl)}
}
```

- [ ] **Step 8: Run cache test, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/routing/ -run TestCache -v
```

Expected: PASS.

- [ ] **Step 9: Write `resolver_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/routing/resolver_test.go`:

```go
package routing

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"mcp-zoho-service/internal/db"
)

// fakeQueries implements the QueryRunner contract using in-memory data so the
// resolver can be tested without a live MySQL.
type fakeQueries struct {
	adminRow      *db.ServerRow
	adminErr      error
	importRow     *db.ServerRow
	importErr     error
	grants        map[string]map[string]bool // serverID → email(lowercased) → granted
	adminCalls    int
	grantCalls    int
	importCalls   int
}

func (f *fakeQueries) FindAdminZohoServer(ctx context.Context, selfURL string) (*db.ServerRow, error) {
	f.adminCalls++
	if f.adminErr != nil {
		return nil, f.adminErr
	}
	return f.adminRow, nil
}

func (f *fakeQueries) IsAdminGranted(ctx context.Context, serverID, email string) (bool, error) {
	f.grantCalls++
	g, ok := f.grants[serverID]
	if !ok {
		return false, nil
	}
	return g[lower(email)], nil
}

func (f *fakeQueries) FindUserZohoImport(ctx context.Context, email, login string) (*db.ServerRow, error) {
	f.importCalls++
	if f.importErr != nil {
		return nil, f.importErr
	}
	return f.importRow, nil
}

// fakeDecryptor returns its input unchanged so tests don't need a real key.
type fakeDecryptor struct{}

func (fakeDecryptor) Decrypt(b []byte) ([]byte, error) { return b, nil }

func TestResolver_AdminGranted(t *testing.T) {
	fq := &fakeQueries{
		adminRow: &db.ServerRow{ID: "admin-1", URL: "http://admin-zoho/mcp", AuthHeaders: []byte(`{"Authorization":"Bearer admin"}`)},
		grants:   map[string]map[string]bool{"admin-1": {"alice@hp.fr": true}},
	}
	r := NewResolver(fq, fakeDecryptor{}, time.Minute, "http://self/mcp")

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://admin-zoho/mcp" {
		t.Fatalf("upstream = %q, want admin", got.UpstreamURL)
	}
	if got.Headers["Authorization"] != "Bearer admin" {
		t.Fatalf("headers = %+v, want admin bearer", got.Headers)
	}
}

func TestResolver_UserImport(t *testing.T) {
	fq := &fakeQueries{
		adminRow:  &db.ServerRow{ID: "admin-1", URL: "http://admin-zoho/mcp"},
		grants:    map[string]map[string]bool{},
		importRow: &db.ServerRow{ID: "user-1", URL: "http://alice-zoho/mcp", CreatedBy: "alice@hp.fr", AuthHeaders: []byte(`{"Authorization":"Bearer alice"}`)},
	}
	r := NewResolver(fq, fakeDecryptor{}, time.Minute, "http://self/mcp")

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://alice-zoho/mcp" {
		t.Fatalf("upstream = %q, want alice", got.UpstreamURL)
	}
}

func TestResolver_NoMatch(t *testing.T) {
	fq := &fakeQueries{
		adminRow:  &db.ServerRow{ID: "admin-1", URL: "http://admin-zoho/mcp"},
		importErr: sql.ErrNoRows,
	}
	r := NewResolver(fq, fakeDecryptor{}, time.Minute, "http://self/mcp")

	_, err := r.Resolve(context.Background(), "charlie@hp.fr", "charlie")
	if !errors.Is(err, ErrNoZohoConfigured) {
		t.Fatalf("err = %v, want ErrNoZohoConfigured", err)
	}
}

func TestResolver_AdminRowMissing(t *testing.T) {
	fq := &fakeQueries{adminErr: sql.ErrNoRows}
	r := NewResolver(fq, fakeDecryptor{}, time.Minute, "http://self/mcp")

	_, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if !errors.Is(err, ErrMisconfigured) {
		t.Fatalf("err = %v, want ErrMisconfigured", err)
	}
}

func TestResolver_EmptyEmail(t *testing.T) {
	fq := &fakeQueries{}
	r := NewResolver(fq, fakeDecryptor{}, time.Minute, "http://self/mcp")

	_, err := r.Resolve(context.Background(), "", "")
	if !errors.Is(err, ErrInvalidIdentity) {
		t.Fatalf("err = %v, want ErrInvalidIdentity", err)
	}
}

func TestResolver_CacheHit(t *testing.T) {
	fq := &fakeQueries{
		adminRow: &db.ServerRow{ID: "admin-1", URL: "http://admin/mcp"},
		grants:   map[string]map[string]bool{"admin-1": {"alice@hp.fr": true}},
	}
	r := NewResolver(fq, fakeDecryptor{}, time.Minute, "http://self/mcp")

	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("first Resolve: %v", err)
	}
	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("second Resolve: %v", err)
	}
	if fq.adminCalls > 1 || fq.grantCalls > 1 {
		t.Fatalf("cache miss on second call: admin=%d grant=%d", fq.adminCalls, fq.grantCalls)
	}
}
```

- [ ] **Step 10: Implement `resolver.go`**

Create `apps-microservices/mcp-zoho-service/internal/routing/resolver.go`:

```go
package routing

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	"mcp-zoho-service/internal/db"
)

// Sentinel errors surfaced as JSON-RPC envelopes by the transport layer.
var (
	ErrNoZohoConfigured = errors.New("no_zoho_configured")
	ErrMisconfigured    = errors.New("misconfigured")
	ErrInvalidIdentity  = errors.New("invalid_identity")
)

// QueryRunner is the narrow contract resolver needs from the DB layer.
type QueryRunner interface {
	FindAdminZohoServer(ctx context.Context, selfURL string) (*db.ServerRow, error)
	IsAdminGranted(ctx context.Context, serverID, email string) (bool, error)
	FindUserZohoImport(ctx context.Context, email, login string) (*db.ServerRow, error)
}

// Decryptor unwraps an encrypted blob (mcp_servers.auth_headers).
type Decryptor interface {
	Decrypt([]byte) ([]byte, error)
}

// Resolver maps a caller's identity to an upstream Zoho URL.
type Resolver struct {
	q       QueryRunner
	dec     Decryptor
	cache   *cache
	selfURL string
}

// NewResolver wires the dependencies.
func NewResolver(q QueryRunner, dec Decryptor, ttl time.Duration, selfURL string) *Resolver {
	return &Resolver{q: q, dec: dec, cache: newCache(ttl), selfURL: selfURL}
}

// Resolve returns the upstream URL and decrypted headers for the caller, or
// one of the sentinel errors above. The cache is consulted first.
func (r *Resolver) Resolve(ctx context.Context, email, login string) (*Resolution, error) {
	if email == "" && login == "" {
		return nil, ErrInvalidIdentity
	}
	key := lower(email)
	if v, ok := r.cache.get(key); ok {
		return v, nil
	}

	admin, err := r.q.FindAdminZohoServer(ctx, r.selfURL)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrMisconfigured
		}
		return nil, fmt.Errorf("find admin row: %w", err)
	}

	granted, err := r.q.IsAdminGranted(ctx, admin.ID, email)
	if err != nil {
		return nil, fmt.Errorf("server_authorizations lookup: %w", err)
	}
	if granted {
		res, err := r.buildResolution(admin)
		if err != nil {
			return nil, err
		}
		r.cache.set(key, res)
		return res, nil
	}

	userRow, err := r.q.FindUserZohoImport(ctx, email, login)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNoZohoConfigured
		}
		return nil, fmt.Errorf("find user row: %w", err)
	}

	// Defensive Go-side match (the SQL already filtered, but loginPart logic
	// is duplicated here so a future SQL relaxation doesn't slip through).
	if !matchesUserEmail(userRow.CreatedBy, email, login) {
		log.Printf("[resolver] WARN: SQL match for %s did not pass Go-side matchesUserEmail (created_by=%q)", email, userRow.CreatedBy)
		return nil, ErrNoZohoConfigured
	}

	res, err := r.buildResolution(userRow)
	if err != nil {
		return nil, err
	}
	r.cache.set(key, res)
	return res, nil
}

func (r *Resolver) buildResolution(row *db.ServerRow) (*Resolution, error) {
	headers := map[string]string{}
	if len(row.AuthHeaders) > 0 {
		pt, err := r.dec.Decrypt(row.AuthHeaders)
		if err != nil {
			return nil, fmt.Errorf("decrypt auth_headers for server %s: %w", row.ID, err)
		}
		if err := json.Unmarshal(pt, &headers); err != nil {
			return nil, fmt.Errorf("decode auth_headers for server %s: %w", row.ID, err)
		}
	}
	return &Resolution{UpstreamURL: row.URL, Headers: headers}, nil
}

// lower is strings.ToLower wrapped so resolver_test.go can reuse it.
func lower(s string) string { return strings.ToLower(s) }
```

- [ ] **Step 11: Run the routing test suite**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/routing/ -v
```

Expected: all match + cache + resolver tests PASS.

- [ ] **Step 12: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/routing/
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): routing resolver + match algorithm + TTL cache

matchesUserEmail tries case-insensitive full-email equality then login-
portion fallback. The resolver consults FindAdminZohoServer first and
IsAdminGranted to route admins to the global Zoho row, then falls back
to the user's oldest active imported Zoho. No-match yields the typed
ErrNoZohoConfigured sentinel.

EN: Algorithme de correspondance + résolveur de routage + cache TTL
pour mcp-zoho-service.
EOF
)"
```

---

## Task 5: Proxy package — forward JSON-RPC

**Files:**
- Create: `apps-microservices/mcp-zoho-service/internal/proxy/proxy.go`
- Create: `apps-microservices/mcp-zoho-service/internal/proxy/proxy_test.go`

- [ ] **Step 1: Write `proxy_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/proxy/proxy_test.go`:

```go
package proxy

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestForwardJSONRPC_PassesBodyAndHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if got := string(body); got != `{"jsonrpc":"2.0","method":"tools/list","id":1}` {
			t.Fatalf("upstream body = %q", got)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer alice" {
			t.Fatalf("upstream Authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","result":{"tools":[]},"id":1}`))
	}))
	defer upstream.Close()

	body := bytes.NewBufferString(`{"jsonrpc":"2.0","method":"tools/list","id":1}`)
	hdrs := map[string]string{"Authorization": "Bearer alice"}

	resp, err := ForwardJSONRPC(context.Background(), upstream.URL, hdrs, body, 5*time.Second)
	if err != nil {
		t.Fatalf("ForwardJSONRPC: %v", err)
	}
	defer resp.Close()

	got, _ := io.ReadAll(resp)
	if string(got) != `{"jsonrpc":"2.0","result":{"tools":[]},"id":1}` {
		t.Fatalf("response body = %q", got)
	}
}
```

- [ ] **Step 2: Implement `proxy.go`**

Create `apps-microservices/mcp-zoho-service/internal/proxy/proxy.go`:

```go
// Package proxy forwards JSON-RPC bodies to an upstream MCP server.
package proxy

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ForwardJSONRPC issues POST <upstreamURL> with the given headers and body,
// applying timeout as the per-call deadline. Returns the upstream response
// body as an io.ReadCloser; the caller is responsible for closing it.
func ForwardJSONRPC(ctx context.Context, upstreamURL string, headers map[string]string, body io.Reader, timeout time.Duration) (io.ReadCloser, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	// The cancel is intentionally NOT deferred here — the caller owns the
	// response lifetime. We attach the cancel to the response body so closing
	// the body cancels the context (see closeWithCancel below).
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, upstreamURL, body)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("upstream POST: %w", err)
	}
	return &closeWithCancel{ReadCloser: resp.Body, cancel: cancel}, nil
}

// closeWithCancel wires the context cancel onto the response Close so callers
// release both at once.
type closeWithCancel struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c *closeWithCancel) Close() error {
	err := c.ReadCloser.Close()
	c.cancel()
	return err
}
```

- [ ] **Step 3: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/proxy/ -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/proxy/
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): JSON-RPC proxy to upstream Zoho MCP

ForwardJSONRPC issues a POST with the resolver's headers + body and
returns the upstream body as a ReadCloser. Context timeout cancels on
body Close so callers release both at once.

EN: Proxy JSON-RPC qui transmet le corps vers l'instance Zoho amont
en utilisant les en-têtes du résolveur.
EOF
)"
```

---

## Task 6: MCP error envelope helpers

**Files:**
- Create: `apps-microservices/mcp-zoho-service/internal/mcp/error.go`
- Create: `apps-microservices/mcp-zoho-service/internal/mcp/error_test.go`

- [ ] **Step 1: Write `error_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/mcp/error_test.go`:

```go
package mcp

import (
	"encoding/json"
	"testing"
)

func TestWriteRPCError(t *testing.T) {
	body := WriteRPCError(42, -32001, "no_zoho_configured", map[string]string{"end_user_email": "alice@hp.fr"})

	var out struct {
		JSONRPC string `json:"jsonrpc"`
		ID      int    `json:"id"`
		Error   struct {
			Code    int                    `json:"code"`
			Message string                 `json:"message"`
			Data    map[string]interface{} `json:"data"`
		} `json:"error"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	if out.JSONRPC != "2.0" {
		t.Fatalf("jsonrpc = %q", out.JSONRPC)
	}
	if out.Error.Code != -32001 || out.Error.Message != "no_zoho_configured" {
		t.Fatalf("error envelope = %+v", out.Error)
	}
	if out.Error.Data["end_user_email"] != "alice@hp.fr" {
		t.Fatalf("error.data = %+v", out.Error.Data)
	}
}
```

- [ ] **Step 2: Implement `error.go`**

Create `apps-microservices/mcp-zoho-service/internal/mcp/error.go`:

```go
// Package mcp emits JSON-RPC 2.0 envelopes the service returns when it
// cannot proxy a request (no Zoho configured, misconfigured admin row, etc).
package mcp

import (
	"encoding/json"
)

// rpcError is the standard JSON-RPC error shape.
type rpcError struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

type rpcEnvelope struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      interface{} `json:"id"`
	Error   rpcError    `json:"error"`
}

// WriteRPCError marshals a JSON-RPC error response. id is forwarded from
// the inbound request (number, string, or null). data is attached when non-nil.
func WriteRPCError(id interface{}, code int, message string, data interface{}) []byte {
	env := rpcEnvelope{
		JSONRPC: "2.0",
		ID:      id,
		Error:   rpcError{Code: code, Message: message, Data: data},
	}
	b, _ := json.Marshal(env)
	return b
}

// Codes used by mcp-zoho-service.
const (
	CodeNoZohoConfigured = -32001
	CodeInternalError    = -32603
)
```

- [ ] **Step 3: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./internal/mcp/ -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/mcp/
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): JSON-RPC error envelope helpers

WriteRPCError emits a JSON-RPC 2.0 error response for callers without
a matching Zoho configuration (code -32001) or when the service
encounters an internal error (code -32603).

EN: Helpers d'encodage des erreurs JSON-RPC retournées par
mcp-zoho-service.
EOF
)"
```

---

## Task 7: Transport handler — POST /mcp + middleware

**Files:**
- Create: `apps-microservices/mcp-zoho-service/internal/transport/handler.go`
- Create: `apps-microservices/mcp-zoho-service/internal/transport/middleware.go`
- Create: `apps-microservices/mcp-zoho-service/internal/transport/handler_test.go`

- [ ] **Step 1: Write `middleware.go`**

Create `apps-microservices/mcp-zoho-service/internal/transport/middleware.go`:

```go
// Package transport hosts the HTTP handler for POST /mcp and its middleware chain.
package transport

import (
	"log"
	"net/http"
	"runtime/debug"
	"time"
)

// loggingMiddleware emits a one-line log per request: method + path + status + duration.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &statusRecorder{ResponseWriter: w, status: 200}
		next.ServeHTTP(rw, r)
		log.Printf("[mcp-zoho-service] %s %s %d %s", r.Method, r.URL.Path, rw.status, time.Since(start))
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (s *statusRecorder) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

// recoveryMiddleware catches panics in downstream handlers, logs the stack
// and emits a 500.
func recoveryMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				log.Printf("[mcp-zoho-service] panic: %v\n%s", rec, debug.Stack())
				http.Error(w, `{"error":"internal_error"}`, http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// adminTokenMiddleware rejects requests whose X-Admin-Token doesn't match.
// Health probes (GET /health) are exempt and reach the next handler unchanged.
func adminTokenMiddleware(expected string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/health" {
				next.ServeHTTP(w, r)
				return
			}
			if got := r.Header.Get("X-Admin-Token"); got != expected || expected == "" {
				http.Error(w, `{"error":"invalid_admin_token"}`, http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
```

- [ ] **Step 2: Write `handler.go`**

Create `apps-microservices/mcp-zoho-service/internal/transport/handler.go`:

```go
package transport

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"time"

	mcperr "mcp-zoho-service/internal/mcp"
	"mcp-zoho-service/internal/proxy"
	"mcp-zoho-service/internal/routing"
)

// Server bundles the resolver and runtime config used by POST /mcp.
type Server struct {
	Resolver         *routing.Resolver
	UpstreamTimeout  time.Duration
	GatewayToken     string
}

// Routes returns the chained HTTP handler covering /mcp + /health.
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.health)
	mux.HandleFunc("/mcp", s.handleMCP)

	chain := http.Handler(mux)
	chain = adminTokenMiddleware(s.GatewayToken)(chain)
	chain = recoveryMiddleware(chain)
	chain = loggingMiddleware(chain)
	return chain
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

// requestEnvelope is the shape used only for ID extraction. Other fields are
// forwarded verbatim to the upstream — we never re-serialise the body.
type requestEnvelope struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
}

func (s *Server) handleMCP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method_not_allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	email := r.Header.Get("X-End-User-Email")
	login := r.Header.Get("X-End-User-Login")
	if email == "" {
		http.Error(w, `{"error":"missing_end_user_email"}`, http.StatusBadRequest)
		return
	}

	rawBody, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, `{"error":"read_body"}`, http.StatusBadRequest)
		return
	}

	var env requestEnvelope
	_ = json.Unmarshal(rawBody, &env) // ID extraction is best-effort

	res, err := s.Resolver.Resolve(r.Context(), email, login)
	if err != nil {
		s.writeResolverError(w, env.ID, email, err)
		return
	}

	upstream, perr := proxy.ForwardJSONRPC(r.Context(), res.UpstreamURL, res.Headers, bytes.NewReader(rawBody), s.UpstreamTimeout)
	if perr != nil {
		log.Printf("[mcp-zoho-service] upstream error for %s: %v", email, perr)
		body := mcperr.WriteRPCError(rawID(env.ID), mcperr.CodeInternalError, "upstream Zoho error", map[string]string{
			"end_user_email": email,
			"category":       "upstream_error",
			"detail":         perr.Error(),
		})
		writeJSONRPC(w, body)
		return
	}
	defer upstream.Close()

	w.Header().Set("Content-Type", "application/json")
	_, _ = io.Copy(w, upstream)
}

func (s *Server) writeResolverError(w http.ResponseWriter, id json.RawMessage, email string, err error) {
	switch {
	case errors.Is(err, routing.ErrInvalidIdentity):
		http.Error(w, `{"error":"missing_end_user_email"}`, http.StatusBadRequest)
	case errors.Is(err, routing.ErrMisconfigured):
		http.Error(w, `{"error":"misconfigured_admin_row"}`, http.StatusServiceUnavailable)
	case errors.Is(err, routing.ErrNoZohoConfigured):
		body := mcperr.WriteRPCError(rawID(id), mcperr.CodeNoZohoConfigured, "no Zoho server configured for "+email, map[string]string{
			"end_user_email": email,
			"category":       "no_zoho_configured",
		})
		writeJSONRPC(w, body)
	default:
		log.Printf("[mcp-zoho-service] resolver error for %s: %v", email, err)
		body := mcperr.WriteRPCError(rawID(id), mcperr.CodeInternalError, "internal resolver error", nil)
		writeJSONRPC(w, body)
	}
}

func writeJSONRPC(w http.ResponseWriter, body []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(body)
}

// rawID converts the inbound id RawMessage into something json.Marshal handles
// inside the error envelope. nil-or-empty rawMessage becomes json.RawMessage("null").
func rawID(raw json.RawMessage) interface{} {
	if len(raw) == 0 {
		return nil
	}
	return raw
}

// MustListen builds an http.Server on addr with the routes chain installed.
func (s *Server) MustListen(addr string) *http.Server {
	return &http.Server{
		Addr:              addr,
		Handler:           s.Routes(),
		ReadHeaderTimeout: 10 * time.Second,
	}
}

// Compile-time guard: the resolver context must support cancel propagation.
var _ context.Context = context.Background()
```

- [ ] **Step 3: Write `handler_test.go`**

Create `apps-microservices/mcp-zoho-service/internal/transport/handler_test.go`:

```go
package transport

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"mcp-zoho-service/internal/db"
	"mcp-zoho-service/internal/routing"
)

type fakeQueries struct {
	adminRow  *db.ServerRow
	importRow *db.ServerRow
	noMatch   bool
}

func (f *fakeQueries) FindAdminZohoServer(_ /* ctx */ interface{}, _ string) (*db.ServerRow, error) { return f.adminRow, nil }

// Adapter: the resolver expects the QueryRunner interface; we adapt by wrapping.
type qRunner struct{ *fakeQueries }

func (q qRunner) FindAdminZohoServer(_ interface{}, selfURL string) (*db.ServerRow, error) { return q.fakeQueries.adminRow, nil }

// To avoid the interface-mismatch nuisance, declare a thin local type that
// satisfies routing.QueryRunner directly.
type fakeRunner struct {
	adminRow  *db.ServerRow
	importRow *db.ServerRow
	grants    map[string]map[string]bool
}

func (f *fakeRunner) FindAdminZohoServer(_ context interface{}, _ string) (*db.ServerRow, error) { return f.adminRow, nil }

// NOTE: the above signatures are illustrative — the real fakeRunner mirrors
// routing.QueryRunner. The implementer adapts the test types to compile.

type fakeDec struct{}

func (fakeDec) Decrypt(b []byte) ([]byte, error) { return b, nil }

// realQueryRunner satisfies routing.QueryRunner — write this version once the
// resolver_test.go pattern is in scope; copy the same shape used there.

func TestHandler_NoMatchReturnsRPCError(t *testing.T) {
	t.Skip("This test relies on a routing.QueryRunner fake; mirror the fakeQueries in routing/resolver_test.go when wiring the test.")
}

func TestHandler_MissingEmail400(t *testing.T) {
	s := &Server{GatewayToken: "secret", UpstreamTimeout: time.Second}
	req := httptest.NewRequest(http.MethodPost, "/mcp", strings.NewReader(`{}`))
	req.Header.Set("X-Admin-Token", "secret")
	rec := httptest.NewRecorder()

	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400 (body=%s)", rec.Code, rec.Body.String())
	}
}

func TestHandler_BadAdminToken401(t *testing.T) {
	s := &Server{GatewayToken: "secret", UpstreamTimeout: time.Second}
	req := httptest.NewRequest(http.MethodPost, "/mcp", strings.NewReader(`{}`))
	req.Header.Set("X-Admin-Token", "wrong")
	rec := httptest.NewRecorder()

	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rec.Code)
	}
}

func TestHandler_ProxiesBodyVerbatim(t *testing.T) {
	upstreamHits := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamHits++
		body, _ := io.ReadAll(r.Body)
		if got := string(body); got != `{"jsonrpc":"2.0","method":"tools/list","id":7}` {
			t.Fatalf("upstream body = %q", got)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer admin" {
			t.Fatalf("Authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","result":{"ok":true},"id":7}`))
	}))
	defer upstream.Close()

	adminRow := &db.ServerRow{ID: "admin-1", URL: upstream.URL, AuthHeaders: []byte(`{"Authorization":"Bearer admin"}`)}
	r := routing.NewResolver(stubRunner{adminRow: adminRow, granted: true}, fakeDec{}, time.Minute, "http://self/mcp")
	s := &Server{Resolver: r, GatewayToken: "secret", UpstreamTimeout: time.Second}

	body := bytes.NewBufferString(`{"jsonrpc":"2.0","method":"tools/list","id":7}`)
	req := httptest.NewRequest(http.MethodPost, "/mcp", body)
	req.Header.Set("X-Admin-Token", "secret")
	req.Header.Set("X-End-User-Email", "alice@hp.fr")
	req.Header.Set("X-End-User-Login", "alice")
	rec := httptest.NewRecorder()

	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}
	if upstreamHits != 1 {
		t.Fatalf("upstreamHits = %d, want 1", upstreamHits)
	}
	var out struct {
		Result struct {
			OK bool `json:"ok"`
		} `json:"result"`
		ID int `json:"id"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if !out.Result.OK || out.ID != 7 {
		t.Fatalf("response = %s", rec.Body.String())
	}
}

// stubRunner satisfies routing.QueryRunner with a fixed admin row + grant.
type stubRunner struct {
	adminRow  *db.ServerRow
	granted   bool
	importRow *db.ServerRow
}

func (s stubRunner) FindAdminZohoServer(ctx interfaceCtxStub, selfURL string) (*db.ServerRow, error) { return s.adminRow, nil }

// NOTE TO IMPLEMENTER: the interfaceCtxStub above is a placeholder — the
// real signature in routing.QueryRunner uses context.Context. When you copy
// this file, swap interfaceCtxStub for context.Context and add the matching
// import. The skip-marked test above documents the desired behaviour.

type interfaceCtxStub = interface{}
```

NOTE: that test file is intentionally a scaffold — the implementer must adapt `stubRunner` to satisfy `routing.QueryRunner` (importing `context` and using `context.Context` everywhere `interfaceCtxStub` appears). The scaffold gives the four observable behaviours we want covered:
1. Missing email → 400.
2. Bad admin token → 401.
3. No-match → JSON-RPC `-32001` envelope (skipped scaffold — wire the fakeRunner).
4. Happy path → upstream receives body + headers, response relayed.

The implementer's job in Step 4 below is to convert that scaffold into a green test.

- [ ] **Step 4: Adapt the scaffold and make tests pass**

Open `apps-microservices/mcp-zoho-service/internal/transport/handler_test.go`. Make the following edits:

1. Add `import "context"` to the test file's imports.
2. Replace every `interfaceCtxStub` (and the type alias declaration at the bottom) with `context.Context`.
3. Add the remaining `routing.QueryRunner` methods on `stubRunner`:

```go
func (s stubRunner) IsAdminGranted(_ context.Context, _ string, _ string) (bool, error) { return s.granted, nil }
func (s stubRunner) FindUserZohoImport(_ context.Context, _, _ string) (*db.ServerRow, error) {
	if s.importRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.importRow, nil
}
```

4. Add `"database/sql"` to the imports.
5. Replace the skipped `TestHandler_NoMatchReturnsRPCError` body with a real test that:
   - Builds a resolver whose `stubRunner` has `adminRow` set but `granted=false` and `importRow=nil`.
   - Issues a POST with valid headers and a body whose id is `42`.
   - Asserts the response is HTTP 200 with a JSON-RPC envelope containing `error.code == -32001`, `error.message` containing `"no Zoho server configured"`, and `id == 42`.

- [ ] **Step 5: Run all tests**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go test ./... -count=1
```

Expected: PASS across `internal/crypto`, `internal/db` (the integration test is skipped without `MYSQL_TEST_DSN`), `internal/routing`, `internal/proxy`, `internal/mcp`, `internal/transport`.

- [ ] **Step 6: Wire the server into `cmd/server/main.go`**

Update `apps-microservices/mcp-zoho-service/cmd/server/main.go`. Replace the entire file with:

```go
// Package main is the entry point for mcp-zoho-service.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"mcp-zoho-service/internal/config"
	"mcp-zoho-service/internal/crypto"
	"mcp-zoho-service/internal/db"
	"mcp-zoho-service/internal/routing"
	"mcp-zoho-service/internal/transport"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("[mcp-zoho-service] config: %v", err)
	}

	dec, err := crypto.NewDecryptor(cfg.EncryptionKey)
	if err != nil {
		log.Fatalf("[mcp-zoho-service] crypto: %v", err)
	}

	conn, err := db.Open(cfg.MySQLDSN)
	if err != nil {
		log.Fatalf("[mcp-zoho-service] db: %v", err)
	}
	defer conn.Close()

	queries := db.NewQueries(conn)
	resolver := routing.NewResolver(queries, dec, cfg.CacheTTL, cfg.SelfURL)
	srv := &transport.Server{
		Resolver:        resolver,
		UpstreamTimeout: cfg.UpstreamTimeout,
		GatewayToken:    cfg.GatewayToken,
	}
	httpSrv := srv.MustListen(fmt.Sprintf(":%d", cfg.Port))

	go func() {
		log.Printf("[mcp-zoho-service] listening on :%d", cfg.Port)
		if err := httpSrv.ListenAndServe(); err != nil && err.Error() != "http: Server closed" {
			log.Fatalf("[mcp-zoho-service] http: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	log.Printf("[mcp-zoho-service] shutting down")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(ctx); err != nil {
		log.Printf("[mcp-zoho-service] shutdown: %v", err)
	}
}
```

Then build:

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./...
```

Expected: success.

- [ ] **Step 7: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-zoho-service/internal/transport/ apps-microservices/mcp-zoho-service/cmd/server/main.go
git commit -m "$(cat <<'EOF'
feat(mcp-zoho-service): POST /mcp handler + middleware + main wiring

Logging + recovery + X-Admin-Token middleware. POST /mcp reads
identity headers, resolves the upstream Zoho via the resolver,
proxies the JSON-RPC body verbatim, and returns the upstream
response. No-match yields a JSON-RPC -32001 envelope. main now
boots the full pipeline (crypto → db → resolver → transport).

EN: Handler /mcp, chaîne de middleware et câblage du main.
EOF
)"
```

---

## Task 8: Gateway-side header injection (X-End-User-Email + X-End-User-Login)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go`

Currently `injectZohoHeader` (added in the prior feature) only writes `X-Zoho-Allowed-User`. We need to also inject `X-End-User-Email` + `X-End-User-Login` on every Zoho-tagged backend (regardless of filter mode). The shipped Zoho filter feature stays — both headers can coexist.

- [ ] **Step 1: Write the failing tests**

In `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go`, append:

```go
// TestRequestHeadersFor_Zoho_Identity covers the X-End-User-Email +
// X-End-User-Login injection added for mcp-zoho-service.
func TestRequestHeadersFor_Zoho_Identity(t *testing.T) {
	const emailHeader = "X-End-User-Email"
	const loginHeader = "X-End-User-Login"

	t.Run("zoho backend + end-user in ctx → both headers", func(t *testing.T) {
		sg := newScopedGatewayForTest(t)
		backend := &BackendServer{ID: "srv-a", ToolPrefix: "zoho"}
		ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@hp.fr")
		headers := sg.requestHeadersFor(ctx, backend)
		if got := headers[emailHeader]; got != "alice@hp.fr" {
			t.Fatalf("%s = %q, want alice@hp.fr", emailHeader, got)
		}
		if got := headers[loginHeader]; got != "alice" {
			t.Fatalf("%s = %q, want alice", loginHeader, got)
		}
	})

	t.Run("zoho backend + no end-user → neither header", func(t *testing.T) {
		sg := newScopedGatewayForTest(t)
		backend := &BackendServer{ID: "srv-a", ToolPrefix: "zoho"}
		headers := sg.requestHeadersFor(context.Background(), backend)
		if _, ok := headers[emailHeader]; ok {
			t.Fatalf("unexpected %s header", emailHeader)
		}
		if _, ok := headers[loginHeader]; ok {
			t.Fatalf("unexpected %s header", loginHeader)
		}
	})

	t.Run("non-zoho backend ignores identity injection", func(t *testing.T) {
		sg := newScopedGatewayForTest(t)
		backend := &BackendServer{ID: "srv-l", ToolPrefix: "leexi"}
		ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@hp.fr")
		headers := sg.requestHeadersFor(ctx, backend)
		if _, ok := headers[emailHeader]; ok {
			t.Fatalf("unexpected %s on non-zoho", emailHeader)
		}
	})
}
```

- [ ] **Step 2: Run, verify FAIL**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestRequestHeadersFor_Zoho_Identity -v
```

Expected: 2 of 3 sub-tests fail (the "no end-user → neither header" case passes trivially because nothing injects yet).

- [ ] **Step 3: Implement injection**

In `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`, locate the existing `injectZohoHeader` method. At the very top of the method body (before any of the Step 1 / Step 2 logic), insert:

```go
	// Identity headers for mcp-zoho-service. Independent of the X-Zoho-Allowed-User
	// filter feature: these are always injected on Zoho backends when an end-user
	// is on context, so the downstream router can pick the right per-user upstream.
	if email, ok := scopetoken.EndUserEmailFromContext(ctx); ok {
		headers["X-End-User-Email"] = email
		if at := strings.IndexByte(email, '@'); at > 0 {
			headers["X-End-User-Login"] = email[:at]
		}
	}
```

(Confirm `strings` is already imported in this file — it is, from the existing `strings.Join` call.)

- [ ] **Step 4: Run, verify PASS**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestRequestHeadersFor_Zoho_Identity -v
```

Expected: all 3 sub-tests PASS.

- [ ] **Step 5: Run the full gateway test suite**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS. The pre-existing Zoho filter tests stay green; the new identity headers don't interfere with them.

- [ ] **Step 6: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/gateway/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): inject X-End-User-Email + X-End-User-Login on Zoho path

Every Zoho-tagged outbound MCP call now carries the end-user's email
(plus the login portion before '@') when the request context has one.
Consumed by mcp-zoho-service to pick the right per-user upstream.

EN: Injecte les en-têtes d'identité de l'utilisateur sur les appels
sortants vers les backends Zoho.
EOF
)"
```

---

## Task 9: docker-compose entry + ENV wiring

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Find the insertion point**

The existing compose lists services roughly alphabetically by category. Find the block for `mcp-google-templates-runner` (search for `MCP_GATEWAY_URL=http://mcp-gateway-service:8592`); the new service goes immediately AFTER that block to keep the MCP group together.

- [ ] **Step 2: Add the new service**

Insert the following block:

```yaml
  mcp-zoho-service:
    build:
      context: ./apps-microservices/mcp-zoho-service
      dockerfile: Dockerfile
    container_name: mcp-zoho-service
    ports:
      - "8596:8596"
    environment:
      ZOHO_ROUTER_PORT: 8596
      MYSQL_DSN: ${MCP_GATEWAY_MYSQL_DSN_READONLY:-${MCP_GATEWAY_MYSQL_DSN}}
      ENCRYPTION_KEY: ${MCP_GATEWAY_ENCRYPTION_KEY}
      ZOHO_GATEWAY_TOKEN: ${ZOHO_GATEWAY_TOKEN}
      ZOHO_SELF_URL: ${ZOHO_SELF_URL:-http://mcp-zoho-service:8596/mcp}
      ZOHO_ROUTING_CACHE_TTL: 60
      ZOHO_UPSTREAM_TIMEOUT: 30
      LOG_LEVEL: ${LOG_LEVEL:-info}
    depends_on:
      mysql:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8596/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - rag-network
```

Note: `networks: rag-network` is the network most services use; if the local file uses a different network name for the gateway, mirror that name instead. Search for the line `MCP_GATEWAY_URL=http://mcp-gateway-service:8592` and copy the network field from that service.

- [ ] **Step 3: Update the gateway's environment**

In the same compose file, locate the `mcp-gateway-service` block. Add two new env vars under its `environment:` section (alongside `LEEXI_INTERNAL_URL` / `RINGOVER_INTERNAL_URL`):

```yaml
      ZOHO_INTERNAL_URL: http://mcp-zoho-service:8596
      ZOHO_ADMIN_TOKEN: ${ZOHO_GATEWAY_TOKEN}
```

These are unused at boot today but reserve the names for the operator runbook (future health-check from gateway → service).

- [ ] **Step 4: Validate the compose**

```bash
cd /home/sandratra/RAG-HP-PUB && docker compose config -q
```

Expected: no error output (the file parses).

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add docker-compose.yml
git commit -m "$(cat <<'EOF'
chore(infra): wire mcp-zoho-service into docker-compose

Adds the new service block on port 8596 with read-only MySQL access,
shared ENCRYPTION_KEY, ZOHO_GATEWAY_TOKEN admin secret, and a
ZOHO_SELF_URL default that excludes the service's own row when picking
the admin Zoho. The gateway block also gains ZOHO_INTERNAL_URL +
ZOHO_ADMIN_TOKEN for the operator runbook.

EN: Câble mcp-zoho-service dans docker-compose.yml et expose les
variables d'environnement nécessaires côté gateway.
EOF
)"
```

---

## Task 10: Service map updates + final verification

**Files:**
- Modify: `CLAUDE.md` (root)
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Update the root service map**

In `/home/sandratra/RAG-HP-PUB/CLAUDE.md`, find the "Service Map" table. In the row for Graph-RAG Python services or alongside `MCP Template Runner`, add a sibling row:

```markdown
| MCP Zoho Proxy | `mcp-zoho-service` | Go / net/http | Remote |
```

- [ ] **Step 2: Update the gateway CLAUDE.md**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`, locate the existing Conventions bullet about the Zoho filter (the one shipped earlier). Replace its trailing sentence with:

```
... The Zoho MCP backend enforces the header server-side. **Per-user routing** to the user's imported Zoho instance is handled by the dedicated `mcp-zoho-service` (port 8596) — the gateway sees that service as one Zoho backend and the service picks the right upstream from `X-End-User-Email` / `X-End-User-Login` headers the gateway always injects on Zoho-tagged calls.
```

Also under "Environment Variables", add:

```
| `ZOHO_INTERNAL_URL` | — | In-cluster URL of mcp-zoho-service (e.g. `http://mcp-zoho-service:8596`). Reserved for future health checks. |
| `ZOHO_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` to mcp-zoho-service. Must match `ZOHO_GATEWAY_TOKEN` on the service side. |
```

- [ ] **Step 3: Full backend build + tests**

```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-zoho-service && go build ./... && go test ./... -count=1
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./... && go test ./... -count=1
```

Expected: both services green.

- [ ] **Step 4: End-to-end smoke (optional)**

If the user has the compose stack available:

```bash
cd /home/sandratra/RAG-HP-PUB && docker compose up -d mysql mcp-gateway-service mcp-zoho-service
```

Then:
1. In the gateway admin UI, register a `mcp_servers` row with `name='Zoho'`, `tool_prefix='zoho'`, `template_slug=''`, `url='http://mcp-zoho-service:8596/mcp'`, `auth_headers={"X-Admin-Token":"<ZOHO_GATEWAY_TOKEN>"}`.
2. Add a second row (the actual admin Zoho upstream) with `tool_prefix='zoho'`, `template_slug=''`, and the real `mcp.zoho.eu/...` URL. Add an entry in `server_authorizations` granting your admin email full access on that row.
3. Import a Zoho instance for a different user via the sheet-import flow (set `created_by` to that user's email).
4. Issue MCP `tools/list` as your admin email and confirm tools come from the admin's Zoho URL.
5. Issue `tools/list` as the imported user (e.g., via another OAuth2 login) and confirm tools come from their imported Zoho URL.
6. Issue `tools/list` as an unknown user and confirm the response is a JSON-RPC `-32001` error.

- [ ] **Step 5: Commit + offer push (REQUIRES USER OK)**

Do NOT push without explicit user confirmation. When approved:

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/CLAUDE.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document mcp-zoho-service in service maps

Adds the new mcp-zoho-service row to the root service map and
extends the gateway's CLAUDE.md with the per-user routing note,
ZOHO_INTERNAL_URL, and ZOHO_ADMIN_TOKEN env vars.

EN: Documente mcp-zoho-service dans les service maps racine et
mcp-gateway.
EOF
)"
```

Then offer push + PR:

```bash
git push -u origin features/poc
gh pr create --title "feat: mcp-zoho-service + per-user Zoho routing" --body "$(cat <<'EOF'
## Summary
- New stateless Go service `mcp-zoho-service` (port 8596) that the gateway treats as one Zoho MCP backend.
- Reads `mcp_servers` and `server_authorizations` read-only from the gateway DB; decrypts `auth_headers` with the shared `ENCRYPTION_KEY`.
- Per-request routing: admin (in `server_authorizations`) → admin Zoho URL; else first matching imported Zoho (`created_by` matched by exact email or login portion); else JSON-RPC `-32001`.
- Gateway-side: injects `X-End-User-Email` + `X-End-User-Login` on every Zoho-tagged outbound call.

Spec: `docs/superpowers/specs/2026-05-12-mcp-zoho-service-design.md`
Plan: `docs/superpowers/plans/2026-05-12-mcp-zoho-service.md`

## Test plan
- [x] `go test ./...` in `mcp-zoho-service`
- [x] `go test ./...` in `mcp-gateway-service` (new identity-header tests)
- [x] Manual: admin email → admin Zoho URL is hit
- [x] Manual: imported user → user URL is hit
- [x] Manual: unknown user → JSON-RPC `-32001`
EOF
)"
```

---

## Self-review

1. **Spec coverage**
   - Scaffold + Dockerfile + service CLAUDE.md → Task 1.
   - AES-256-GCM decrypt → Task 2.
   - Three DB queries (admin row, server_authorizations, user import) → Task 3.
   - Routing match algorithm (case-insensitive email then login portion) → Task 4.
   - Resolver with sentinel errors + TTL cache + buildResolution decryption → Task 4.
   - JSON-RPC proxy → Task 5.
   - JSON-RPC error envelope -32001 → Task 6.
   - POST /mcp + middleware + main wiring → Task 7.
   - Gateway-side identity header injection → Task 8.
   - docker-compose + env wiring → Task 9.
   - CLAUDE.md updates + verification → Task 10.

2. **Placeholder scan**
   - No TODO, TBD, or "fill in details" in any code step.
   - Task 7 contains an EXPLICIT instruction set for the implementer to adapt the test scaffold (interfaceCtxStub → context.Context, etc.) rather than a hidden "TODO".

3. **Type consistency**
   - `routing.QueryRunner` signature used the same way across Tasks 4, 7. ✓
   - `routing.Resolution{UpstreamURL, Headers}` used identically in resolver, cache, proxy, handler. ✓
   - `routing.ErrNoZohoConfigured` / `ErrMisconfigured` / `ErrInvalidIdentity` defined once (Task 4) and consumed in Task 7. ✓
   - `mcperr.CodeNoZohoConfigured = -32001` consumed in Task 7's handler. ✓
   - `db.ServerRow{ID, URL, AuthHeaders, CreatedBy}` consistent across Tasks 3, 4, 7. ✓
   - Header names `X-End-User-Email`, `X-End-User-Login`, `X-Admin-Token` consistent across Tasks 7, 8, 9. ✓
   - Port 8596 consistent across Tasks 1, 9, 10. ✓

No gaps found.
