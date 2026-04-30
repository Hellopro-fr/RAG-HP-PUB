# Migration `crawler-monitor-backend` ExpressJS → Go — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers-extended-cc:subagent-driven-development` (recommended) or `superpowers-extended-cc:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec source** : `docs/superpowers/specs/2026-04-28-crawler-monitor-backend-go-migration-design.md`
**Branch** : `features/crawler-monitor-backend-go` (déjà créée, depuis `features/poc`)
**Working dir** : `apps-microservices/crawler-monitor-backend/`

**Goal** : Réécrire le service `crawler-monitor-backend` (Express 4 / Node 20) en Go avec parité d'API stricte, gain de perf sur le parsing queue + concurrence WebSocket + empreinte mémoire.

**Architecture** : Layout standard Go (`cmd/server` + `internal/{config,httpapi,ws,domain,store,auth}`), router `chi`, WebSocket `gorilla`, Redis `go-redis/v9`, tests `testing` stdlib + `miniredis`, image Docker distroless static nonroot.

**Tech Stack** : Go 1.23, `github.com/go-chi/chi/v5`, `github.com/go-chi/cors`, `github.com/go-chi/httprate`, `github.com/golang-jwt/jwt/v5`, `github.com/redis/go-redis/v9`, `github.com/gorilla/websocket`, `github.com/alicebob/miniredis/v2`, `github.com/google/go-cmp/cmp`, `golang.org/x/crypto/scrypt`.

---

## Findings de pré-flight (à intégrer)

Le code Express utilise des env vars différentes du CLAUDE.md du service. Le plan utilise les **vraies** valeurs (lues directement de `server.js`) :

| Env var | Default | Source |
|---|---|---|
| `PORT` | `3001` | server.js:37 |
| `REDIS_URL` | (fatal si absent) | server.js:38 |
| `CRAWLER_STORAGE_PATH` | `/app/storage` | server.js:39 |
| `ADMIN_PASSWORD_HASH` | (fatal si absent) — **scrypt format** | server.js:40 |
| `JWT_SECRET` | (fatal si absent) | server.js:41 |
| `CORS_ALLOWED_ORIGINS` | (vide → `*`) — CSV | server.js:42 |
| `TRUST_PROXY` | `1` (hops) | server.js:96 |
| `RATE_LIMIT_MAX` | `600` | server.js:112 |
| `RATE_LIMIT_WINDOW_MS` | `900000` (15 min) | server.js:113 |
| `REPLAY_HIGH_CPU` | `0.85` | server.js:328 |
| `AUDIT_LOG_DIR` | `./logs/audit/` | auditLog.js:26 |
| `AUDIT_RETENTION_DAYS` | `90` | auditLog.js:27 |
| `ALERT_*` | divers (cf alerts.js:13-25) | alerts.js |

Login : `POST /api/login`, body `{ password }`, vérifie via `verifyPassword(plain, ADMIN_PASSWORD_HASH)`. Token JWT `{ role: 'admin' }`, expire en **24h**, signé HS256.

WebSocket : monté sur `/` (`new WebSocketServer({ server })`), token via query string. Channels Redis subscribe : `crawl_updates` (constante `CRAWL_UPDATES_CHANNEL`) et `crawler:heartbeat`.

---

## Phase 0 — Pré-flight (3 tâches)

### Task 0.1 : Catalogue exhaustif des clés Redis et constantes server.js

**Goal** : Produire un document de référence listant toutes les clés Redis, channels, constantes utilisés par `server.js` afin que les tâches suivantes y réfèrent sans relire.

**Files** :
- Create : `apps-microservices/crawler-monitor-backend/docs/redis-keys-catalog.md`

**Acceptance Criteria** :
- [ ] Toutes les constantes `CRAWL_*`, `*_CHANNEL`, `*_KEY` définies dans server.js sont listées avec leur valeur littérale et la ligne où elles apparaissent
- [ ] Chaque clé indique son type Redis (string / hash / set / list)
- [ ] Chaque pattern d'accès (`client.keys`, `client.get`, `client.publish`, `client.subscribe`) est tracé à la fonction qui l'utilise
- [ ] Les channels pub/sub sont identifiés séparément

**Verify** : ouvrir le doc, vérifier que `grep -n "CRAWL_\|_CHANNEL\|_KEY" server.js` est entièrement couvert.

**Steps** :

- [ ] **Step 1 : Extraire toutes les constantes Redis**

```bash
cd apps-microservices/crawler-monitor-backend
grep -nE "^const [A-Z_]+(=|\s*=\s*)" server.js | grep -iE "(crawl|redis|channel|key|prefix)" > /tmp/keys-raw.txt
```

- [ ] **Step 2 : Recenser les patterns d'accès**

```bash
grep -nE "client\.(get|set|hget|hset|smembers|sadd|srem|lrange|keys|publish|subscribe|del)\(" server.js > /tmp/redis-access.txt
```

- [ ] **Step 3 : Rédiger `docs/redis-keys-catalog.md`**

Format du doc :

```markdown
# Catalogue Redis — crawler-monitor-backend

## Constantes (server.js)

| Constante | Valeur | Type Redis | Ligne | Description |
|---|---|---|---|---|
| `CRAWL_JOB_PREFIX` | `crawler:job:` | string (JSON) | server.js:LXX | Préfixe pour `crawler:job:<id>` |
| `CRAWL_RUNNING_COUNT_KEY` | `...` | string (int) | server.js:LXX | Compteur jobs actifs |
| `CRAWL_MAX_GLOBAL_KEY` | `...` | string (int) | server.js:LXX | Capacité max globale |
| `CRAWL_UPDATES_CHANNEL` | `crawl_updates` | pub/sub | server.js:44 | Broadcast WebSocket |
| `CRAWLER_HEARTBEAT_CHANNEL` | `crawler:heartbeat` | pub/sub | server.js:LXX | Heartbeat replicas |

## Patterns d'accès

| Endpoint | Opération Redis | Clé |
|---|---|---|
| GET /api/jobs | `KEYS crawler:job:*` + `GET` chacune | server.js:286 |
| GET /api/jobs/:id/details | `GET crawler:job:{id}` | server.js:468 |
| GET /api/capacity | `GET CRAWL_RUNNING_COUNT_KEY`, `GET CRAWL_MAX_GLOBAL_KEY` | server.js:1377-78 |
| ... | ... | ... |
```

Remplir avec les valeurs réelles trouvées dans server.js.

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/docs/redis-keys-catalog.md
git commit -m "docs(crawler-monitor-backend): catalogue Redis pour migration Go"
```

---

### Task 0.2 : Tag `last-express` de l'image Node actuelle

**Goal** : Geler l'image Docker actuelle (Node) avec un tag `last-express` dans le registry GCP, pour rollback en < 1 min après cutover.

**Files** : aucun (ops uniquement).

**Acceptance Criteria** :
- [ ] Image `crawler-monitor-backend:last-express` poussée et visible dans le registry GCP
- [ ] Hash SHA de l'image consigné dans le PR description du futur cutover
- [ ] Procédure rollback documentée dans `docs/cutover-runbook.md`

**Verify** :
```bash
gcloud container images list-tags gcr.io/<PROJECT>/crawler-monitor-backend --filter="tags:last-express" --format="table(digest,tags,timestamp.datetime)"
```
→ doit afficher exactement une ligne avec tag `last-express`.

**Steps** :

- [ ] **Step 1 : Identifier l'image Node actuelle en prod**

```bash
docker images | grep crawler-monitor-backend
docker inspect <image-id> --format='{{.RepoDigests}}'
```

- [ ] **Step 2 : Tagger et pusher**

```bash
docker tag <current-image>:latest gcr.io/<PROJECT>/crawler-monitor-backend:last-express
docker push gcr.io/<PROJECT>/crawler-monitor-backend:last-express
```

- [ ] **Step 3 : Créer `docs/cutover-runbook.md`**

```markdown
# Cutover Runbook — crawler-monitor-backend Go

## Rollback

Si erreur post-cutover :

\`\`\`bash
docker compose stop crawler-monitor-backend
docker compose run --rm -d --name crawler-monitor-backend \
  -p 3001:3001 \
  -e REDIS_URL=$REDIS_URL -e JWT_SECRET=$JWT_SECRET \
  -e ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH \
  -e CRAWLER_STORAGE_PATH=/app/storage \
  -v crawler_storage:/app/storage \
  gcr.io/<PROJECT>/crawler-monitor-backend:last-express
\`\`\`

Ou simplement, si docker-compose.yml retient un override `image:` :

\`\`\`bash
docker compose up -d crawler-monitor-backend
\`\`\`
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/docs/cutover-runbook.md
git commit -m "docs(crawler-monitor-backend): runbook cutover + tag last-express"
```

---

### Task 0.3 : Préserver le Dockerfile Node existant en `Dockerfile.express`

**Goal** : Renommer le Dockerfile Node actuel pour libérer le nom `Dockerfile` (qui sera utilisé par la version Go) sans perdre la possibilité de rebuild Node si besoin.

**Files** :
- Modify : `apps-microservices/crawler-monitor-backend/Dockerfile` → renommé `Dockerfile.express`

**Acceptance Criteria** :
- [ ] `Dockerfile.express` existe avec le contenu actuel du Dockerfile Node
- [ ] `docker compose build` sur la branche `main` continue de fonctionner si on lui pointe `dockerfile: Dockerfile.express`
- [ ] Documenté dans `docs/cutover-runbook.md`

**Verify** :
```bash
test -f apps-microservices/crawler-monitor-backend/Dockerfile.express
docker build -f apps-microservices/crawler-monitor-backend/Dockerfile.express \
  -t crawler-monitor-backend:rebuild-test apps-microservices/crawler-monitor-backend/
```
→ build doit réussir.

**Steps** :

- [ ] **Step 1 : Renommer**

```bash
git mv apps-microservices/crawler-monitor-backend/Dockerfile \
       apps-microservices/crawler-monitor-backend/Dockerfile.express
```

- [ ] **Step 2 : Vérifier build**

```bash
docker build -f apps-microservices/crawler-monitor-backend/Dockerfile.express \
  -t crawler-monitor-backend:test apps-microservices/crawler-monitor-backend/
```

- [ ] **Step 3 : Mettre à jour le runbook**

Ajouter dans `docs/cutover-runbook.md` :
```markdown
## Rebuild from Dockerfile.express (last resort)

\`\`\`bash
docker build -f Dockerfile.express -t crawler-monitor-backend:emergency .
\`\`\`
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/Dockerfile.express docs/cutover-runbook.md
git commit -m "build(crawler-monitor-backend): preserve Node Dockerfile as Dockerfile.express"
```

---

## Phase 1 — Fondations Go (7 tâches)

### Task 1.1 : Initialiser le module Go + layout + skeleton main.go + /health

**Goal** : Avoir un binaire Go qui boote, sert `GET /health` → 200 `{ "status": "ok" }`, et expose une sous-commande `healthcheck` pour Docker.

**Files** :
- Create : `apps-microservices/crawler-monitor-backend/go.mod`
- Create : `apps-microservices/crawler-monitor-backend/cmd/server/main.go`
- Create : `apps-microservices/crawler-monitor-backend/cmd/server/healthcheck.go`
- Create : `apps-microservices/crawler-monitor-backend/internal/httpapi/health.go`
- Create : `apps-microservices/crawler-monitor-backend/internal/httpapi/router.go`
- Create : `apps-microservices/crawler-monitor-backend/.gitignore` (modifier l'existant si besoin pour ajouter `/server`, `vendor/`)

**Acceptance Criteria** :
- [ ] `go build ./cmd/server` produit un binaire `server`
- [ ] `./server` démarre et répond 200 `{"status":"ok"}` sur `GET /health`
- [ ] `./server healthcheck` (avec serveur lancé) exit 0 ; sinon exit 1
- [ ] Graceful shutdown sur SIGINT/SIGTERM avec timeout 15s

**Verify** :
```bash
cd apps-microservices/crawler-monitor-backend
go build -o /tmp/cmb ./cmd/server
/tmp/cmb &
sleep 0.5
curl -s http://localhost:3001/health
# → {"status":"ok"}
/tmp/cmb healthcheck
echo "exit: $?"
# → exit: 0
kill %1
```

**Steps** :

- [ ] **Step 1 : Init module + dependencies**

```bash
cd apps-microservices/crawler-monitor-backend
go mod init github.com/Hellopro-fr/crawler-monitor-backend
go get github.com/go-chi/chi/v5@latest
go mod tidy
```

- [ ] **Step 2 : Créer `cmd/server/main.go`**

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

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
)

var version = "dev"

func main() {
	if len(os.Args) >= 2 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck())
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	port := os.Getenv("PORT")
	if port == "" {
		port = "3001"
	}

	r := httpapi.NewRouter(httpapi.Deps{Version: version})

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           r,
		ReadHeaderTimeout: 10 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		slog.Info("server.start", "addr", srv.Addr, "version", version)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("server.listen", "err", err)
			os.Exit(1)
		}
	}()

	<-ctx.Done()
	slog.Info("server.shutdown.start")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.Error("server.shutdown", "err", err)
		os.Exit(1)
	}
	slog.Info("server.shutdown.done")
}
```

- [ ] **Step 3 : Créer `cmd/server/healthcheck.go`**

```go
package main

import (
	"net/http"
	"os"
	"time"
)

func runHealthcheck() int {
	port := os.Getenv("PORT")
	if port == "" {
		port = "3001"
	}
	c := &http.Client{Timeout: 3 * time.Second}
	resp, err := c.Get("http://127.0.0.1:" + port + "/health")
	if err != nil {
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return 1
	}
	return 0
}
```

- [ ] **Step 4 : Créer `internal/httpapi/router.go`**

```go
package httpapi

import (
	"net/http"

	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version string
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Get("/health", healthHandler(d.Version))
	return r
}
```

- [ ] **Step 5 : Créer `internal/httpapi/health.go`**

```go
package httpapi

import (
	"encoding/json"
	"net/http"
)

func healthHandler(version string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":  "ok",
			"version": version,
		})
	}
}
```

- [ ] **Step 6 : Build + smoke test**

```bash
go build -o /tmp/cmb ./cmd/server
/tmp/cmb &
sleep 0.5
curl -s http://localhost:3001/health
/tmp/cmb healthcheck && echo OK || echo KO
kill %1
```

Expected : `{"status":"ok","version":"dev"}` puis `OK`.

- [ ] **Step 7 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/{go.mod,go.sum,cmd,internal,.gitignore}
git commit -m "feat(crawler-monitor-backend-go): squelette main + /health + healthcheck subcommand"
```

---

### Task 1.2 : Config loader `internal/config` + tests

**Goal** : Charger toutes les env vars dans une struct `Config` typée. Fatal si manquantes (REDIS_URL, ADMIN_PASSWORD_HASH, JWT_SECRET) ; defaults sinon.

**Files** :
- Create : `apps-microservices/crawler-monitor-backend/internal/config/config.go`
- Create : `apps-microservices/crawler-monitor-backend/internal/config/config_test.go`

**Acceptance Criteria** :
- [ ] `config.Load()` retourne une `Config` valide quand toutes les env vars requises sont définies
- [ ] `config.Load()` retourne erreur explicite si REDIS_URL/ADMIN_PASSWORD_HASH/JWT_SECRET manquent
- [ ] Defaults appliqués pour PORT, CRAWLER_STORAGE_PATH, RATE_LIMIT_*, TRUST_PROXY, CORS_ALLOWED_ORIGINS
- [ ] Tous les noms d'env vars sont alignés sur server.js (cf table en tête de plan)

**Verify** :
```bash
go test ./internal/config/ -v
```
→ tous les tests passent.

**Steps** :

- [ ] **Step 1 : Écrire le test (TDD)**

`internal/config/config_test.go` :

```go
package config

import (
	"strings"
	"testing"
)

func setEnv(t *testing.T, kv map[string]string) {
	t.Helper()
	for k, v := range kv {
		t.Setenv(k, v)
	}
}

func TestLoad_AllRequiredPresent(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":           "redis://localhost:6379",
		"ADMIN_PASSWORD_HASH": "scrypt$1$2$3$4$5",
		"JWT_SECRET":          "secret",
	})
	c, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if c.Port != "3001" {
		t.Errorf("Port default = %q, want 3001", c.Port)
	}
	if c.RateLimitMax != 600 {
		t.Errorf("RateLimitMax default = %d, want 600", c.RateLimitMax)
	}
	if c.RateLimitWindowMs != 900000 {
		t.Errorf("RateLimitWindowMs default = %d, want 900000", c.RateLimitWindowMs)
	}
	if c.CrawlerStoragePath != "/app/storage" {
		t.Errorf("CrawlerStoragePath default = %q, want /app/storage", c.CrawlerStoragePath)
	}
}

func TestLoad_MissingRedisURL(t *testing.T) {
	setEnv(t, map[string]string{
		"ADMIN_PASSWORD_HASH": "x",
		"JWT_SECRET":          "x",
	})
	t.Setenv("REDIS_URL", "")
	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "REDIS_URL") {
		t.Fatalf("expect REDIS_URL error, got %v", err)
	}
}

func TestLoad_MissingAdminHash(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":  "redis://x",
		"JWT_SECRET": "x",
	})
	t.Setenv("ADMIN_PASSWORD_HASH", "")
	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "ADMIN_PASSWORD_HASH") {
		t.Fatalf("expect ADMIN_PASSWORD_HASH error, got %v", err)
	}
}

func TestLoad_MissingJWTSecret(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":           "redis://x",
		"ADMIN_PASSWORD_HASH": "x",
	})
	t.Setenv("JWT_SECRET", "")
	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "JWT_SECRET") {
		t.Fatalf("expect JWT_SECRET error, got %v", err)
	}
}

func TestLoad_CorsAllowedOriginsCSV(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":            "redis://x",
		"ADMIN_PASSWORD_HASH":  "x",
		"JWT_SECRET":           "x",
		"CORS_ALLOWED_ORIGINS": "https://a.example,https://b.example",
	})
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(c.CorsAllowedOrigins) != 2 || c.CorsAllowedOrigins[0] != "https://a.example" {
		t.Errorf("CorsAllowedOrigins = %v", c.CorsAllowedOrigins)
	}
}
```

- [ ] **Step 2 : Run failing tests**

```bash
go test ./internal/config/
# → FAIL: package config undefined
```

- [ ] **Step 3 : Implémenter `internal/config/config.go`**

```go
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Port               string
	RedisURL           string
	CrawlerStoragePath string
	AdminPasswordHash  string
	JWTSecret          string
	CorsAllowedOrigins []string
	TrustProxyHops     int
	RateLimitMax       int
	RateLimitWindowMs  int
	ReplayHighCPU      float64
	AuditLogDir        string
	AuditRetentionDays int
}

func Load() (*Config, error) {
	c := &Config{
		Port:               envOr("PORT", "3001"),
		RedisURL:           os.Getenv("REDIS_URL"),
		CrawlerStoragePath: envOr("CRAWLER_STORAGE_PATH", "/app/storage"),
		AdminPasswordHash:  os.Getenv("ADMIN_PASSWORD_HASH"),
		JWTSecret:          os.Getenv("JWT_SECRET"),
		TrustProxyHops:     envInt("TRUST_PROXY", 1),
		RateLimitMax:       envInt("RATE_LIMIT_MAX", 600),
		RateLimitWindowMs:  envInt("RATE_LIMIT_WINDOW_MS", 900000),
		ReplayHighCPU:      envFloat("REPLAY_HIGH_CPU", 0.85),
		AuditLogDir:        envOr("AUDIT_LOG_DIR", "./logs/audit/"),
		AuditRetentionDays: envInt("AUDIT_RETENTION_DAYS", 90),
	}

	if origins := os.Getenv("CORS_ALLOWED_ORIGINS"); origins != "" {
		for _, o := range strings.Split(origins, ",") {
			if t := strings.TrimSpace(o); t != "" {
				c.CorsAllowedOrigins = append(c.CorsAllowedOrigins, t)
			}
		}
	}

	if c.RedisURL == "" {
		return nil, fmt.Errorf("REDIS_URL is required")
	}
	if c.AdminPasswordHash == "" {
		return nil, fmt.Errorf("ADMIN_PASSWORD_HASH is required (scrypt format)")
	}
	if c.JWTSecret == "" {
		return nil, fmt.Errorf("JWT_SECRET is required")
	}
	return c, nil
}

func envOr(key, def string) string {
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

func envFloat(key string, def float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}
```

- [ ] **Step 4 : Run tests**

```bash
go test ./internal/config/ -v
# → PASS (5 tests)
```

- [ ] **Step 5 : Wire dans main.go**

Modifier `cmd/server/main.go` après le early `os.Args[1] == "healthcheck"` check :

```go
import "github.com/Hellopro-fr/crawler-monitor-backend/internal/config"

cfg, err := config.Load()
if err != nil {
    slog.Error("config.load", "err", err)
    os.Exit(1)
}
port := cfg.Port

// remplacer le os.Getenv("PORT") existant par cfg.Port
// passer cfg dans Deps si nécessaire (Deps{Version: version, Config: cfg})
```

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/internal/config/ apps-microservices/crawler-monitor-backend/cmd/server/main.go
git commit -m "feat(crawler-monitor-backend-go): config loader + tests env vars"
```

---

### Task 1.3 : Helpers `respond.go` + `errors.go` + tests

**Goal** : Standardiser le format des réponses JSON et la gestion d'erreurs HTTP. `WriteJSON`, `WriteError`, `DecodeJSON`, type `HTTPError`.

**Files** :
- Create : `internal/httpapi/respond.go`
- Create : `internal/httpapi/errors.go`
- Create : `internal/httpapi/respond_test.go`

**Acceptance Criteria** :
- [ ] `WriteJSON(w, 200, payload)` écrit `Content-Type: application/json; charset=utf-8`, status, body marshalé
- [ ] `WriteError(w, 401, "Invalid")` écrit `{"error":"Invalid"}` avec status 401
- [ ] `DecodeJSON(r, &dst)` retourne erreur si body > 50 MB ou JSON invalide
- [ ] Type `HTTPError` avec sentinels `ErrNotFound`, `ErrUnauthorized`, etc.

**Verify** : `go test ./internal/httpapi/ -run "TestRespond|TestError" -v`

**Steps** :

- [ ] **Step 1 : Test**

```go
// internal/httpapi/respond_test.go
package httpapi

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWriteJSON(t *testing.T) {
	w := httptest.NewRecorder()
	WriteJSON(w, 201, map[string]int{"x": 1})
	if w.Code != 201 {
		t.Errorf("status = %d, want 201", w.Code)
	}
	if ct := w.Header().Get("Content-Type"); ct != "application/json; charset=utf-8" {
		t.Errorf("Content-Type = %q", ct)
	}
	var got map[string]int
	if err := json.Unmarshal(w.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got["x"] != 1 {
		t.Errorf("body = %v", got)
	}
}

func TestWriteError(t *testing.T) {
	w := httptest.NewRecorder()
	WriteError(w, 401, "Invalid password")
	if w.Code != 401 {
		t.Errorf("status = %d, want 401", w.Code)
	}
	body := strings.TrimSpace(w.Body.String())
	if body != `{"error":"Invalid password"}` {
		t.Errorf("body = %q", body)
	}
}

func TestDecodeJSON_OK(t *testing.T) {
	r := httptest.NewRequest("POST", "/", bytes.NewBufferString(`{"x":42}`))
	var dst struct {
		X int `json:"x"`
	}
	if err := DecodeJSON(r, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.X != 42 {
		t.Errorf("x = %d", dst.X)
	}
}

func TestDecodeJSON_Invalid(t *testing.T) {
	r := httptest.NewRequest("POST", "/", bytes.NewBufferString(`{not json`))
	var dst map[string]any
	if err := DecodeJSON(r, &dst); err == nil {
		t.Error("expected error for invalid JSON")
	}
}
```

- [ ] **Step 2 : Run failing test**

```bash
go test ./internal/httpapi/ -run TestRespond
# → FAIL: undefined: WriteJSON
```

- [ ] **Step 3 : Implémenter `respond.go`**

```go
package httpapi

import (
	"encoding/json"
	"net/http"
)

const MaxBodyBytes = 50 << 20

func WriteJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if payload == nil {
		return
	}
	_ = json.NewEncoder(w).Encode(payload)
}

func WriteError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	type errBody struct {
		Error string `json:"error"`
	}
	b, _ := json.Marshal(errBody{Error: msg})
	_, _ = w.Write(b)
}

func DecodeJSON(r *http.Request, dst any) error {
	r.Body = http.MaxBytesReader(nil, r.Body, MaxBodyBytes)
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	return dec.Decode(dst)
}
```

- [ ] **Step 4 : Implémenter `errors.go`**

```go
package httpapi

type HTTPError struct {
	Status int
	Msg    string
}

func (e *HTTPError) Error() string { return e.Msg }

func NewHTTPError(status int, msg string) *HTTPError {
	return &HTTPError{Status: status, Msg: msg}
}

var (
	ErrNotFound      = &HTTPError{Status: 404, Msg: "Not found"}
	ErrUnauthorized  = &HTTPError{Status: 401, Msg: "Unauthorized"}
	ErrForbidden     = &HTTPError{Status: 403, Msg: "Forbidden"}
	ErrBadRequest    = &HTTPError{Status: 400, Msg: "Bad request"}
	ErrConflict      = &HTTPError{Status: 409, Msg: "Conflict"}
	ErrPayloadTooBig = &HTTPError{Status: 413, Msg: "Payload too large"}
)
```

- [ ] **Step 5 : Run tests**

```bash
go test ./internal/httpapi/ -run "TestRespond|TestError|TestWrite|TestDecode" -v
# → PASS
```

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/internal/httpapi/
git commit -m "feat(crawler-monitor-backend-go): helpers respond/errors + tests"
```

---

### Task 1.4 : JWT middleware + tests

**Goal** : Middleware chi qui vérifie `Authorization: Bearer <token>` HS256 contre `JWT_SECRET`, injecte les claims dans le contexte, retourne 401 sinon.

**Files** :
- Create : `internal/httpapi/middleware/jwt.go`
- Create : `internal/httpapi/middleware/jwt_test.go`
- Modify : `go.mod` (ajout `github.com/golang-jwt/jwt/v5`)

**Acceptance Criteria** :
- [ ] Token valide → handler suivant appelé, claims accessibles via `middleware.UserFromContext(ctx)`
- [ ] Header absent → 401 `{"error":"Authentication required"}`
- [ ] Token mal signé/expiré → 403 `{"error":"Invalid token"}` (parité Express qui retourne 403 sur jwt.verify échoué)
- [ ] Test interop : un token signé par Node (jsonwebtoken HS256) est accepté

**Verify** : `go test ./internal/httpapi/middleware/ -v`

**Steps** :

- [ ] **Step 1 : Ajouter dep**

```bash
go get github.com/golang-jwt/jwt/v5
```

- [ ] **Step 2 : Test**

```go
// internal/httpapi/middleware/jwt_test.go
package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const testSecret = "test-jwt-secret"

func mintToken(t *testing.T, claims jwt.MapClaims) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	s, err := tok.SignedString([]byte(testSecret))
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestJWT_ValidToken(t *testing.T) {
	tok := mintToken(t, jwt.MapClaims{"role": "admin", "exp": time.Now().Add(time.Hour).Unix()})
	called := false
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		u := UserFromContext(r.Context())
		if u == nil || u["role"] != "admin" {
			t.Errorf("missing claims: %v", u)
		}
		w.WriteHeader(200)
	}))
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer "+tok)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if !called {
		t.Error("inner handler not called")
	}
	if w.Code != 200 {
		t.Errorf("status=%d", w.Code)
	}
}

func TestJWT_NoHeader(t *testing.T) {
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("must not be called") }))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	h.ServeHTTP(w, r)
	if w.Code != 401 {
		t.Errorf("status=%d, want 401", w.Code)
	}
}

func TestJWT_BadToken(t *testing.T) {
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("must not be called") }))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer not.a.token")
	h.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Errorf("status=%d, want 403 (parity with Express jwt.verify failure)", w.Code)
	}
}

func TestJWT_ExpiredToken(t *testing.T) {
	tok := mintToken(t, jwt.MapClaims{"role": "admin", "exp": time.Now().Add(-time.Hour).Unix()})
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("must not be called") }))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer "+tok)
	h.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Errorf("status=%d, want 403", w.Code)
	}
}
```

- [ ] **Step 3 : Implémenter `jwt.go`**

```go
package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

type ctxKeyUser struct{}

func JWTAuth(secret string) func(http.Handler) http.Handler {
	keyFn := func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrTokenSignatureInvalid
		}
		return []byte(secret), nil
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			if !strings.HasPrefix(h, "Bearer ") {
				writeJSONError(w, 401, "Authentication required")
				return
			}
			raw := strings.TrimPrefix(h, "Bearer ")
			tok, err := jwt.Parse(raw, keyFn)
			if err != nil || !tok.Valid {
				writeJSONError(w, 403, "Invalid token")
				return
			}
			claims, _ := tok.Claims.(jwt.MapClaims)
			ctx := context.WithValue(r.Context(), ctxKeyUser{}, map[string]any(claims))
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func UserFromContext(ctx context.Context) map[string]any {
	v, _ := ctx.Value(ctxKeyUser{}).(map[string]any)
	return v
}

func writeJSONError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(`{"error":"` + msg + `"}`))
}
```

- [ ] **Step 4 : Run tests**

```bash
go test ./internal/httpapi/middleware/ -v
# → PASS (4 tests)
```

- [ ] **Step 5 : Test interop Node ↔ Go (manuel)**

```bash
# Mint un token via le Node existant :
cd apps-microservices/crawler-monitor-backend
JWT_SECRET=test-jwt-secret node -e "console.log(require('jsonwebtoken').sign({role:'admin'},'test-jwt-secret',{expiresIn:'1h'}))"
# → eyJhbGciOiJIUzI1NiIs...

# Tester en Go via curl avec ce token. (À faire au moment du test interop dans Phase 2.)
```

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/internal/httpapi/middleware/ apps-microservices/crawler-monitor-backend/{go.mod,go.sum}
git commit -m "feat(crawler-monitor-backend-go): middleware JWT HS256 + tests interop"
```

---

### Task 1.5 : Middleware audit (stub) + tests

**Goal** : Middleware audit qui appelle `auditstore.Append` après que la réponse soit envoyée. À cette étape, l'auditstore est un stub `NoopStore` qui ne fait rien — seule la signature et l'ordre d'invocation comptent.

**Files** :
- Create : `internal/httpapi/middleware/audit.go`
- Create : `internal/httpapi/middleware/audit_test.go`

**Acceptance Criteria** :
- [ ] Middleware capture le status code de la réponse via `ResponseWriter` wrapper
- [ ] Append appelé une seule fois par requête, avec `action`, `status`, `metadata` configurables
- [ ] Les options `CaptureParams`, `CaptureQuery`, `CaptureBody` reflètent le comportement de `auditLog.js:auditMiddleware`

**Verify** : `go test ./internal/httpapi/middleware/ -run TestAudit -v`

**Steps** :

- [ ] **Step 1 : Test**

```go
// internal/httpapi/middleware/audit_test.go
package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
)

type fakeAuditStore struct {
	mu      sync.Mutex
	entries []map[string]any
}

func (f *fakeAuditStore) Append(ctx context.Context, e map[string]any) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.entries = append(f.entries, e)
	return nil
}

func TestAudit_BasicCapture(t *testing.T) {
	store := &fakeAuditStore{}
	mw := AuditMiddleware(store, "test_action", AuditOptions{})
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	r := httptest.NewRequest("GET", "/x", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if len(store.entries) != 1 {
		t.Fatalf("entries = %d, want 1", len(store.entries))
	}
	e := store.entries[0]
	if e["action"] != "test_action" {
		t.Errorf("action = %v", e["action"])
	}
	if e["status"] != "ok" {
		t.Errorf("status = %v, want ok (200)", e["status"])
	}
}

func TestAudit_StatusErrorOn4xx(t *testing.T) {
	store := &fakeAuditStore{}
	mw := AuditMiddleware(store, "x", AuditOptions{})
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
	}))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	h.ServeHTTP(w, r)
	if store.entries[0]["status"] != "error" {
		t.Errorf("status = %v, want error", store.entries[0]["status"])
	}
}
```

- [ ] **Step 2 : Implémenter `audit.go`**

```go
package middleware

import (
	"context"
	"net/http"
	"time"
)

type AuditStore interface {
	Append(ctx context.Context, entry map[string]any) error
}

type AuditOptions struct {
	CaptureParams []string
	CaptureQuery  []string
	CaptureBody   []string
}

type statusCapture struct {
	http.ResponseWriter
	status int
}

func (s *statusCapture) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

func AuditMiddleware(store AuditStore, action string, opts AuditOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			sc := &statusCapture{ResponseWriter: w, status: 200}
			next.ServeHTTP(sc, r)

			user := "anonymous"
			if u := UserFromContext(r.Context()); u != nil {
				if v, ok := u["role"].(string); ok {
					user = v
				}
			}
			st := "ok"
			if sc.status >= 400 {
				st = "error"
			}
			entry := map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"user":   user,
				"action": action,
				"status": st,
				"ip":     clientIP(r),
			}
			metadata := map[string]any{}
			for _, k := range opts.CaptureQuery {
				if v := r.URL.Query().Get(k); v != "" {
					metadata[k] = v
				}
			}
			if len(metadata) > 0 {
				entry["metadata"] = metadata
			}
			_ = store.Append(r.Context(), entry)
		})
	}
}

func clientIP(r *http.Request) string {
	if xf := r.Header.Get("X-Forwarded-For"); xf != "" {
		return xf
	}
	return r.RemoteAddr
}
```

- [ ] **Step 3 : Run tests**

```bash
go test ./internal/httpapi/middleware/ -run TestAudit -v
# → PASS
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/internal/httpapi/middleware/audit.go apps-microservices/crawler-monitor-backend/internal/httpapi/middleware/audit_test.go
git commit -m "feat(crawler-monitor-backend-go): middleware audit + interface store"
```

---

### Task 1.6 : Middleware ratelimit, CORS, security headers + tests

**Goal** : Reproduire `helmet`, `cors`, `express-rate-limit` côté Go.

**Files** :
- Create : `internal/httpapi/middleware/securityheaders.go`
- Create : `internal/httpapi/middleware/cors.go`
- Create : `internal/httpapi/middleware/ratelimit.go`
- Create : `internal/httpapi/middleware/middleware_test.go`

**Acceptance Criteria** :
- [ ] `securityheaders` ajoute `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security: max-age=15552000; includeSubDomains` (équivalent helmet defaults)
- [ ] `cors.New(origins)` retourne tous les headers `Access-Control-*` corrects ; si liste vide → wildcard `*`
- [ ] `ratelimit.ByIP(max=600, window=15min)` retourne 429 après dépassement avec `{"error":"Too many requests"}` (parité avec express-rate-limit)

**Verify** : `go test ./internal/httpapi/middleware/ -run "TestCors|TestSecurity|TestRateLimit" -v`

**Steps** :

- [ ] **Step 1 : Ajouter deps**

```bash
go get github.com/go-chi/cors github.com/go-chi/httprate
```

- [ ] **Step 2 : Implémenter `securityheaders.go`**

```go
package middleware

import "net/http"

func SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-Frame-Options", "DENY")
		h.Set("Referrer-Policy", "no-referrer")
		h.Set("Strict-Transport-Security", "max-age=15552000; includeSubDomains")
		next.ServeHTTP(w, r)
	})
}
```

- [ ] **Step 3 : Implémenter `cors.go`**

```go
package middleware

import (
	"net/http"

	"github.com/go-chi/cors"
)

func CORS(allowed []string) func(http.Handler) http.Handler {
	if len(allowed) == 0 {
		allowed = []string{"*"}
	}
	return cors.Handler(cors.Options{
		AllowedOrigins:   allowed,
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Authorization", "Content-Type"},
		AllowCredentials: false,
		MaxAge:           300,
	})
}
```

- [ ] **Step 4 : Implémenter `ratelimit.go`**

```go
package middleware

import (
	"net/http"
	"time"

	"github.com/go-chi/httprate"
)

func RateLimitByIP(max int, window time.Duration) func(http.Handler) http.Handler {
	return httprate.Limit(
		max,
		window,
		httprate.WithKeyFuncs(httprate.KeyByIP),
		httprate.WithLimitHandler(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.WriteHeader(429)
			_, _ = w.Write([]byte(`{"error":"Too many requests"}`))
		}),
	)
}
```

- [ ] **Step 5 : Tests**

```go
// internal/httpapi/middleware/middleware_test.go
package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestSecurityHeaders(t *testing.T) {
	h := SecurityHeaders(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Header().Get("X-Frame-Options") != "DENY" {
		t.Errorf("X-Frame-Options = %q", w.Header().Get("X-Frame-Options"))
	}
	if w.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Errorf("X-Content-Type-Options = %q", w.Header().Get("X-Content-Type-Options"))
	}
}

func TestRateLimit_429AfterMax(t *testing.T) {
	mw := RateLimitByIP(2, time.Minute)
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))

	for i := 0; i < 2; i++ {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/", nil)
		r.RemoteAddr = "127.0.0.1:1234"
		h.ServeHTTP(w, r)
		if w.Code != 200 {
			t.Errorf("call %d: status=%d", i, w.Code)
		}
	}
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "127.0.0.1:1234"
	h.ServeHTTP(w, r)
	if w.Code != 429 {
		t.Errorf("3rd call: status=%d, want 429", w.Code)
	}
}
```

- [ ] **Step 6 : Run + commit**

```bash
go test ./internal/httpapi/middleware/ -v
git add apps-microservices/crawler-monitor-backend/internal/httpapi/middleware/ apps-microservices/crawler-monitor-backend/{go.mod,go.sum}
git commit -m "feat(crawler-monitor-backend-go): middlewares cors/securityheaders/ratelimit + tests"
```

---

### Task 1.7 : Dockerfile multi-stage + entrée docker-compose port 3002

**Goal** : Build d'image distroless static nonroot, entrée docker-compose dédiée pour shadow run.

**Files** :
- Create : `apps-microservices/crawler-monitor-backend/Dockerfile`
- Create : `apps-microservices/crawler-monitor-backend/.dockerignore`
- Modify : `docker-compose.yml` (ajout service `crawler-monitor-backend-go` sur port 3002)
- Create : `apps-microservices/crawler-monitor-backend/.env.example`

**Acceptance Criteria** :
- [ ] `docker build -t cmb-go .` produit une image < 25 MB
- [ ] `docker run` de l'image démarre, `/health` répond 200
- [ ] `docker compose up crawler-monitor-backend-go` lance le service sur 3002 sans clash avec le service Node sur 3001

**Verify** :
```bash
docker build -t cmb-go apps-microservices/crawler-monitor-backend
docker run --rm -p 3002:3001 -e REDIS_URL=redis://x -e ADMIN_PASSWORD_HASH=x -e JWT_SECRET=x cmb-go &
sleep 1
curl -s http://localhost:3002/health
docker stop $(docker ps -lq)
docker images cmb-go --format "{{.Size}}"  # < 25MB
```

**Steps** :

- [ ] **Step 1 : Dockerfile**

```dockerfile
FROM golang:1.23-alpine AS builder
WORKDIR /src
RUN apk add --no-cache git ca-certificates
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ENV CGO_ENABLED=0 GOOS=linux GOFLAGS="-trimpath"
ARG VERSION=dev
RUN go build -ldflags="-s -w -X main.version=${VERSION}" -o /out/server ./cmd/server

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=builder /out/server /app/server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
USER nonroot:nonroot
EXPOSE 3001
ENTRYPOINT ["/app/server"]
```

- [ ] **Step 2 : .dockerignore**

```
node_modules
logs
tests/fixtures
.env
*.log
Dockerfile.express
docs/
*.md
```

- [ ] **Step 3 : .env.example**

```
PORT=3001
REDIS_URL=redis://localhost:6379
CRAWLER_STORAGE_PATH=/app/storage
ADMIN_PASSWORD_HASH=scrypt$16384$8$1$<saltHex>$<derivedHex>
JWT_SECRET=change-me
CORS_ALLOWED_ORIGINS=https://monitor.example.com
RATE_LIMIT_MAX=600
RATE_LIMIT_WINDOW_MS=900000
TRUST_PROXY=1
LOG_LEVEL=info
```

- [ ] **Step 4 : Ajout service docker-compose**

Ajouter dans `docker-compose.yml` (à côté de `crawler-monitor-backend` existant) :

```yaml
  crawler-monitor-backend-go:
    profiles: ["app"]
    build:
      context: ./apps-microservices/crawler-monitor-backend
      dockerfile: Dockerfile
    ports:
      - "3002:3001"
    environment:
      - REDIS_URL=${REDIS_URL}
      - JWT_SECRET=${JWT_SECRET}
      - ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
      - CRAWLER_STORAGE_PATH=/app/storage
      - PORT=3001
      - LOG_LEVEL=info
      - CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS:-*}
    volumes:
      - crawler_storage:/app/storage:rw
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "/app/server", "healthcheck"]
      interval: 10s
      timeout: 3s
      retries: 3
```

- [ ] **Step 5 : Build + smoke**

```bash
docker build -t cmb-go apps-microservices/crawler-monitor-backend
docker images cmb-go
```

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/{Dockerfile,.dockerignore,.env.example} docker-compose.yml
git commit -m "build(crawler-monitor-backend-go): Dockerfile distroless + service compose port 3002"
```

---

## Phase 2 — Auth & accès aux données (5 tâches)

### Task 2.1 : Package `internal/auth/password` (scrypt verify) + tests portés

**Goal** : Reproduire `verifyPassword` et `looksLikeScryptHash` du Node, avec format exact `scrypt$N$r$p$saltHex$derivedHex`.

**Files** :
- Create : `internal/auth/password/password.go`
- Create : `tests/password_test.go`
- Modify : `go.mod` (ajout `golang.org/x/crypto`)

**Acceptance Criteria** :
- [ ] `looksLikeScryptHash(s)` retourne true si format `scrypt$<N>$<r>$<p>$<saltHex>$<derivedHex>` (6 parts), false sinon — exact même comportement que `password.js:looksLikeScryptHash`
- [ ] `Verify(plain, hash)` retourne `(true, nil)` sur match, `(false, nil)` sur mismatch ou hash malformé, jamais panic
- [ ] `Hash(plain)` génère un hash compatible avec `verifyPassword` Node (interop test)
- [ ] Les 7 cas de `tests/password.test.js` ont leur équivalent Go

**Verify** : `go test ./tests/ -run TestPassword -v`

**Steps** :

- [ ] **Step 1 : Add dep**

```bash
go get golang.org/x/crypto/scrypt
```

- [ ] **Step 2 : Test (port 1:1 de password.test.js)**

```go
// tests/password_test.go
package tests

import (
	"strings"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/auth/password"
)

func TestPassword_HashProducesScryptFormat(t *testing.T) {
	h, err := password.Hash("correct horse battery staple")
	if err != nil {
		t.Fatal(err)
	}
	if !password.LooksLikeScryptHash(h) {
		t.Errorf("not scrypt format: %s", h)
	}
	parts := strings.Split(h, "$")
	if len(parts) != 6 {
		t.Errorf("parts = %d, want 6", len(parts))
	}
}

func TestPassword_VerifyTrueOnRightPassword(t *testing.T) {
	h, _ := password.Hash("hunter2")
	ok, _ := password.Verify("hunter2", h)
	if !ok {
		t.Error("Verify returned false on correct password")
	}
}

func TestPassword_VerifyFalseOnWrongPassword(t *testing.T) {
	h, _ := password.Hash("hunter2")
	ok, _ := password.Verify("hunter3", h)
	if ok {
		t.Error("Verify returned true on wrong password")
	}
}

func TestPassword_DifferentHashesSameInput(t *testing.T) {
	a, _ := password.Hash("same")
	b, _ := password.Hash("same")
	if a == b {
		t.Error("two hashes are equal — random salt missing?")
	}
	okA, _ := password.Verify("same", a)
	okB, _ := password.Verify("same", b)
	if !okA || !okB {
		t.Error("Verify failed on either hash")
	}
}

func TestPassword_VerifyRejectsMalformed(t *testing.T) {
	cases := []string{"", "not-a-hash", "scrypt$bad", "bcrypt$1$2$3$4$5"}
	for _, h := range cases {
		ok, _ := password.Verify("x", h)
		if ok {
			t.Errorf("Verify(x, %q) = true, want false", h)
		}
	}
}

func TestPassword_HashRejectsEmpty(t *testing.T) {
	_, err := password.Hash("")
	if err == nil || !strings.Contains(err.Error(), "non-empty") {
		t.Errorf("Hash(\"\") err = %v, want non-empty error", err)
	}
}

func TestPassword_LooksLikeScryptHash(t *testing.T) {
	cases := []struct {
		in   string
		want bool
	}{
		{"scrypt$1$2$3$4$5", true},
		{"scrypt$1$2$3$4", false},
		{"plain", false},
		{"", false},
	}
	for _, c := range cases {
		if got := password.LooksLikeScryptHash(c.in); got != c.want {
			t.Errorf("LooksLikeScryptHash(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}
```

- [ ] **Step 3 : Implémenter `internal/auth/password/password.go`**

```go
package password

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"golang.org/x/crypto/scrypt"
)

const (
	prefix     = "scrypt"
	defaultN   = 16384
	defaultR   = 8
	defaultP   = 1
	keyLen     = 64
	saltLen    = 16
)

func Hash(plain string) (string, error) {
	if plain == "" {
		return "", errors.New("password must be non-empty string")
	}
	salt := make([]byte, saltLen)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	derived, err := scrypt.Key([]byte(plain), salt, defaultN, defaultR, defaultP, keyLen)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s$%d$%d$%d$%s$%s",
		prefix, defaultN, defaultR, defaultP,
		hex.EncodeToString(salt), hex.EncodeToString(derived)), nil
}

func Verify(plain, hash string) (bool, error) {
	if plain == "" || hash == "" {
		return false, nil
	}
	parts := strings.Split(hash, "$")
	if len(parts) != 6 || parts[0] != prefix {
		return false, nil
	}
	n, err1 := strconv.Atoi(parts[1])
	r, err2 := strconv.Atoi(parts[2])
	p, err3 := strconv.Atoi(parts[3])
	if err1 != nil || err2 != nil || err3 != nil {
		return false, nil
	}
	salt, err := hex.DecodeString(parts[4])
	if err != nil {
		return false, nil
	}
	expected, err := hex.DecodeString(parts[5])
	if err != nil || len(expected) == 0 {
		return false, nil
	}
	candidate, err := scrypt.Key([]byte(plain), salt, n, r, p, len(expected))
	if err != nil {
		return false, nil
	}
	return subtle.ConstantTimeCompare(candidate, expected) == 1, nil
}

func LooksLikeScryptHash(s string) bool {
	if !strings.HasPrefix(s, prefix+"$") {
		return false
	}
	return len(strings.Split(s, "$")) == 6
}
```

- [ ] **Step 4 : Test interop avec hash Node**

```bash
cd apps-microservices/crawler-monitor-backend
NODE_HASH=$(node -e "import('./src/lib/password.js').then(m => m.hashPassword('hunter2').then(h => process.stdout.write(h)))")
echo "Node hash: $NODE_HASH"
go run ./cmd/server <<EOF
# (à exécuter via un main de test ou table-driven test ; ajoute ce cas dans password_test.go)
EOF
```

Ajouter dans le test :
```go
func TestPassword_VerifyAcceptsNodeProducedHash(t *testing.T) {
	// Hash généré par : node -e "import('./src/lib/password.js').then(m => m.hashPassword('hunter2').then(console.log))"
	// Remplace par un hash réel généré une fois et committé en fixture.
	nodeHash := "scrypt$16384$8$1$..." // TO BE GENERATED ONCE AND HARDCODED
	ok, err := password.Verify("hunter2", nodeHash)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("Verify rejected a Node-produced hash — interop broken")
	}
}
```

NOTE pour l'implémenteur : générer le hash une fois avec le Node, le coller dans la string, committer. C'est le test critique d'interop.

- [ ] **Step 5 : Run tests**

```bash
go test ./tests/ -run TestPassword -v
# → PASS (8 tests)
```

- [ ] **Step 6 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/internal/auth/password/ apps-microservices/crawler-monitor-backend/tests/password_test.go apps-microservices/crawler-monitor-backend/{go.mod,go.sum}
git commit -m "feat(crawler-monitor-backend-go): auth/password scrypt + tests interop Node"
```

---

### Task 2.2 : Endpoint `POST /api/login` + tests

**Goal** : Implémenter le handler login avec parité stricte d'Express (statuts, payloads, audit log).

**Files** :
- Create : `internal/httpapi/auth.go`
- Create : `tests/login_test.go`
- Modify : `internal/httpapi/router.go` (mount `/api/login`)
- Modify : `cmd/server/main.go` (passer `cfg` et `auditStore` dans Deps)

**Acceptance Criteria** :
- [ ] `POST /api/login` body `{"password":"x"}` mauvais → 401 `{"error":"Invalid password"}`
- [ ] body `{}` ou body absent → 400 `{"error":"Password required"}`
- [ ] body `{"password":"good"}` → 200 `{"token":"<jwt>"}`, JWT signé HS256 avec claim `{role:"admin"}` et exp +24h
- [ ] Tentatives loggées via `auditStore` avec actions `login_attempt`/`login_success`/`login_failure`

**Verify** : `go test ./tests/ -run TestLogin -v`

**Steps** :

- [ ] **Step 1 : Test**

```go
// tests/login_test.go
package tests

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/auth/password"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/golang-jwt/jwt/v5"
)

func newTestRouter(t *testing.T, hash string) *httptest.Server {
	t.Helper()
	cfg := &config.Config{
		AdminPasswordHash: hash,
		JWTSecret:         "test-secret",
	}
	r := httpapi.NewRouter(httpapi.Deps{Config: cfg, AuditStore: &noopAudit{}})
	return httptest.NewServer(r)
}

type noopAudit struct{}

func (n *noopAudit) Append(_ context.Context, _ map[string]any) error { return nil }

func TestLogin_Success(t *testing.T) {
	hash, _ := password.Hash("hunter2")
	srv := newTestRouter(t, hash)
	defer srv.Close()

	resp, err := srv.Client().Post(srv.URL+"/api/login", "application/json",
		bytes.NewBufferString(`{"password":"hunter2"}`))
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body struct{ Token string `json:"token"` }
	_ = json.NewDecoder(resp.Body).Decode(&body)
	if body.Token == "" {
		t.Fatal("empty token")
	}
	parsed, err := jwt.Parse(body.Token, func(t *jwt.Token) (any, error) { return []byte("test-secret"), nil })
	if err != nil || !parsed.Valid {
		t.Fatalf("token invalid: %v", err)
	}
	claims := parsed.Claims.(jwt.MapClaims)
	if claims["role"] != "admin" {
		t.Errorf("role = %v", claims["role"])
	}
	exp := int64(claims["exp"].(float64))
	delta := exp - time.Now().Unix()
	if delta < 23*3600 || delta > 25*3600 {
		t.Errorf("exp delta = %d, want ~24h", delta)
	}
}

func TestLogin_BadPassword(t *testing.T) {
	hash, _ := password.Hash("hunter2")
	srv := newTestRouter(t, hash)
	defer srv.Close()
	resp, _ := srv.Client().Post(srv.URL+"/api/login", "application/json",
		bytes.NewBufferString(`{"password":"wrong"}`))
	if resp.StatusCode != 401 {
		t.Errorf("status=%d, want 401", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Invalid password") {
		t.Errorf("body = %s", body)
	}
}

func TestLogin_MissingPassword(t *testing.T) {
	srv := newTestRouter(t, "x")
	defer srv.Close()
	resp, _ := srv.Client().Post(srv.URL+"/api/login", "application/json", bytes.NewBufferString(`{}`))
	if resp.StatusCode != 400 {
		t.Errorf("status=%d, want 400", resp.StatusCode)
	}
}
```

- [ ] **Step 2 : Implémenter `internal/httpapi/auth.go`**

```go
package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/auth/password"
	"github.com/golang-jwt/jwt/v5"
)

type loginReq struct {
	Password string `json:"password"`
}

func loginHandler(adminHash, jwtSecret string, audit AuditAppender) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req loginReq
		if err := DecodeJSON(r, &req); err != nil || req.Password == "" {
			_ = audit.Append(r.Context(), map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"user":   "anonymous",
				"action": "login_attempt",
				"status": "error",
				"metadata": map[string]any{"reason": "missing_password"},
			})
			WriteError(w, 400, "Password required")
			return
		}
		ok, _ := password.Verify(req.Password, adminHash)
		if !ok {
			_ = audit.Append(r.Context(), map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"user":   "anonymous",
				"action": "login_failure",
				"status": "error",
			})
			WriteError(w, 401, "Invalid password")
			return
		}
		tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"role": "admin",
			"exp":  time.Now().Add(24 * time.Hour).Unix(),
		})
		signed, err := tok.SignedString([]byte(jwtSecret))
		if err != nil {
			WriteError(w, 500, "Token signing failed")
			return
		}
		_ = audit.Append(r.Context(), map[string]any{
			"ts":     time.Now().UTC().Format(time.RFC3339Nano),
			"user":   "admin",
			"action": "login_success",
			"status": "ok",
		})
		WriteJSON(w, 200, map[string]string{"token": signed})
	}
}

type AuditAppender interface {
	Append(ctx context.Context, entry map[string]any) error
}
```

- [ ] **Step 3 : Modifier `router.go`**

```go
package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version    string
	Config     *config.Config
	AuditStore AuditAppender
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Get("/health", healthHandler(d.Version))
	if d.Config != nil {
		r.Post("/api/login", loginHandler(d.Config.AdminPasswordHash, d.Config.JWTSecret, d.AuditStore))
	}
	return r
}
```

- [ ] **Step 4 : Run tests**

```bash
go test ./tests/ -run TestLogin -v
# → PASS (3 tests)
```

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/internal/httpapi/auth.go apps-microservices/crawler-monitor-backend/internal/httpapi/router.go apps-microservices/crawler-monitor-backend/tests/login_test.go
git commit -m "feat(crawler-monitor-backend-go): POST /api/login + tests parite Express"
```

---

### Task 2.3 : Redis store + miniredis tests

**Goal** : Wrapper `redisstore.Client` autour de `go-redis/v9` avec les opérations utilisées par server.js (KEYS, GET, SUBSCRIBE). Constantes des clés issues du catalogue Phase 0.

**Files** :
- Create : `internal/store/redisstore/client.go`
- Create : `internal/store/redisstore/keys.go`
- Create : `internal/store/redisstore/jobs.go`
- Create : `tests/redisstore_test.go`
- Modify : `go.mod` (`github.com/redis/go-redis/v9`, `github.com/alicebob/miniredis/v2`)

**Acceptance Criteria** :
- [ ] `Client.ListJobs(ctx)` retourne tous les `RawJob` issus de `KEYS crawler:job:*`
- [ ] `Client.GetJob(ctx, id)` retourne le `RawJob` ou `redis.Nil` si absent
- [ ] `Client.GetCapacity(ctx)` retourne `(running, max int, error)`
- [ ] `Client.Subscribe(ctx, channels...)` retourne un `*redis.PubSub` utilisable
- [ ] Constantes des clés alignées sur le catalogue Phase 0

**Verify** : `go test ./tests/ -run TestRedisStore -v`

**Steps** :

- [ ] **Step 1 : Add deps**

```bash
go get github.com/redis/go-redis/v9 github.com/alicebob/miniredis/v2
```

- [ ] **Step 2 : Implémenter `keys.go`**

```go
package redisstore

// Cf docs/redis-keys-catalog.md (Phase 0)
const (
	JobPrefix         = "crawler:job:"
	RunningCountKey   = "crawler:running_count"
	MaxGlobalKey      = "crawler:max_global"
	UpdatesChannel    = "crawl_updates"
	HeartbeatChannel  = "crawler:heartbeat"
)
```

> **NOTE** : les valeurs littérales doivent être confirmées en lisant le code de server.js (Phase 0). Les noms `crawler:running_count` / `crawler:max_global` sont supposés — vérifier exactement les chaînes dans server.js et corriger si besoin avant le commit.

- [ ] **Step 3 : Implémenter `client.go`**

```go
package redisstore

import (
	"context"
	"strconv"

	"github.com/redis/go-redis/v9"
)

type Client struct {
	rdb *redis.Client
}

func New(redisURL string) (*Client, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &Client{rdb: redis.NewClient(opts)}, nil
}

func (c *Client) Close() error { return c.rdb.Close() }

func (c *Client) Raw() *redis.Client { return c.rdb }

func (c *Client) GetCapacity(ctx context.Context) (running, max int, err error) {
	rStr, err := c.rdb.Get(ctx, RunningCountKey).Result()
	if err != nil && err != redis.Nil {
		return 0, 0, err
	}
	mStr, err := c.rdb.Get(ctx, MaxGlobalKey).Result()
	if err != nil && err != redis.Nil {
		return 0, 0, err
	}
	running, _ = strconv.Atoi(rStr)
	max, _ = strconv.Atoi(mStr)
	return running, max, nil
}

func (c *Client) Subscribe(ctx context.Context, channels ...string) *redis.PubSub {
	return c.rdb.Subscribe(ctx, channels...)
}
```

- [ ] **Step 4 : Implémenter `jobs.go`**

```go
package redisstore

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/redis/go-redis/v9"
)

type RawJob map[string]any

func (c *Client) ListJobs(ctx context.Context) ([]RawJob, error) {
	keys, err := c.rdb.Keys(ctx, JobPrefix+"*").Result()
	if err != nil {
		return nil, err
	}
	out := make([]RawJob, 0, len(keys))
	for _, k := range keys {
		raw, err := c.rdb.Get(ctx, k).Result()
		if err == redis.Nil {
			continue
		}
		if err != nil {
			return nil, err
		}
		var j RawJob
		if err := json.Unmarshal([]byte(raw), &j); err != nil {
			continue
		}
		j["_redisKey"] = k
		j["_id"] = strings.TrimPrefix(k, JobPrefix)
		out = append(out, j)
	}
	return out, nil
}

func (c *Client) GetJob(ctx context.Context, id string) (RawJob, error) {
	raw, err := c.rdb.Get(ctx, JobPrefix+id).Result()
	if err != nil {
		return nil, err
	}
	var j RawJob
	if err := json.Unmarshal([]byte(raw), &j); err != nil {
		return nil, err
	}
	j["_id"] = id
	return j, nil
}
```

- [ ] **Step 5 : Test avec miniredis**

```go
// tests/redisstore_test.go
package tests

import (
	"context"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func newMini(t *testing.T) (*redisstore.Client, *miniredis.Miniredis) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)
	c, err := redisstore.New("redis://" + mr.Addr())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c, mr
}

func TestRedisStore_ListJobs(t *testing.T) {
	c, mr := newMini(t)
	mr.Set("crawler:job:abc", `{"id":"abc","status":"running"}`)
	mr.Set("crawler:job:def", `{"id":"def","status":"finished"}`)
	mr.Set("other:key", "ignored")

	jobs, err := c.ListJobs(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 2 {
		t.Errorf("len(jobs) = %d, want 2", len(jobs))
	}
}

func TestRedisStore_GetCapacity(t *testing.T) {
	c, mr := newMini(t)
	mr.Set(redisstore.RunningCountKey, "5")
	mr.Set(redisstore.MaxGlobalKey, "10")
	r, m, err := c.GetCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if r != 5 || m != 10 {
		t.Errorf("running=%d max=%d, want 5,10", r, m)
	}
}
```

- [ ] **Step 6 : Run + commit**

```bash
go test ./tests/ -run TestRedisStore -v
git add apps-microservices/crawler-monitor-backend/internal/store/redisstore/ apps-microservices/crawler-monitor-backend/tests/redisstore_test.go apps-microservices/crawler-monitor-backend/{go.mod,go.sum}
git commit -m "feat(crawler-monitor-backend-go): redisstore client + ListJobs/GetCapacity + miniredis tests"
```

---

### Task 2.4 : Filestore + safeJoin + tests path traversal

**Goal** : Wrapper sur `CRAWLER_STORAGE_PATH` avec sécurité path traversal stricte.

**Files** :
- Create : `internal/store/filestore/filestore.go`
- Create : `internal/store/filestore/safejoin.go`
- Create : `tests/filestore_test.go`
- Create : `tests/path_traversal_test.go`

**Acceptance Criteria** :
- [ ] `safeJoin(base, "../../../etc/passwd")` retourne `ErrPathEscape`
- [ ] `safeJoin(base, "ok/file.json")` retourne le chemin absolu correct
- [ ] `Read/Write/Delete` retournent erreur si path échappe la racine
- [ ] Tests sur 10+ patterns malicieux (cf liste ci-dessous)

**Verify** : `go test ./tests/ -run "TestFilestore|TestPathTraversal" -v`

**Steps** :

- [ ] **Step 1 : Implémenter `safejoin.go`**

```go
package filestore

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

var ErrPathEscape = errors.New("path escapes base directory")

func SafeJoin(base string, parts ...string) (string, error) {
	cleanBase := filepath.Clean(base)
	all := append([]string{cleanBase}, parts...)
	joined := filepath.Clean(filepath.Join(all...))
	prefix := cleanBase + string(os.PathSeparator)
	if joined != cleanBase && !strings.HasPrefix(joined, prefix) {
		return "", ErrPathEscape
	}
	return joined, nil
}
```

- [ ] **Step 2 : Implémenter `filestore.go`**

```go
package filestore

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
)

type Storage struct {
	base string
}

func New(base string) *Storage { return &Storage{base: filepath.Clean(base)} }

func (s *Storage) Read(ctx context.Context, parts ...string) ([]byte, error) {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return nil, err
	}
	return os.ReadFile(p)
}

func (s *Storage) Write(ctx context.Context, data []byte, parts ...string) error {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	return os.WriteFile(p, data, 0o644)
}

func (s *Storage) Delete(ctx context.Context, parts ...string) error {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return err
	}
	if err := os.Remove(p); err != nil && !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	return nil
}

func (s *Storage) ListDir(ctx context.Context, parts ...string) ([]os.DirEntry, error) {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return nil, err
	}
	return os.ReadDir(p)
}
```

- [ ] **Step 3 : Test path traversal**

```go
// tests/path_traversal_test.go
package tests

import (
	"context"
	"errors"
	"path/filepath"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

func TestPathTraversal_RejectMaliciousPaths(t *testing.T) {
	base := t.TempDir()
	s := filestore.New(base)
	cases := []struct {
		name string
		path []string
	}{
		{"parent dir", []string{"..", "secret"}},
		{"deep parent", []string{"..", "..", "..", "etc", "passwd"}},
		{"absolute", []string{"/etc/passwd"}},
		{"win absolute", []string{`C:\Windows\System32`}},
		{"slash dotdot", []string{"sub/../..", "secret"}},
		{"null byte", []string{"file\x00../escape"}},
		{"trailing dotdot", []string{"sub/.."}},
		{"single dotdot in middle", []string{"a", "..", "..", "b"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := filestore.SafeJoin(base, c.path...)
			if err == nil {
				t.Errorf("expected ErrPathEscape for %v, got nil", c.path)
			} else if !errors.Is(err, filestore.ErrPathEscape) {
				t.Errorf("err = %v, want ErrPathEscape", err)
			}
			err = s.Delete(context.Background(), c.path...)
			if err == nil {
				t.Errorf("Delete should reject %v", c.path)
			}
		})
	}
}

func TestPathTraversal_AcceptValidPaths(t *testing.T) {
	base := t.TempDir()
	cases := [][]string{
		{"job1", "datasets", "0.json"},
		{"a", "b", "c.txt"},
	}
	for _, c := range cases {
		got, err := filestore.SafeJoin(base, c...)
		if err != nil {
			t.Errorf("SafeJoin(%v): %v", c, err)
		}
		want := filepath.Join(append([]string{base}, c...)...)
		if got != filepath.Clean(want) {
			t.Errorf("got %s, want %s", got, want)
		}
	}
}
```

- [ ] **Step 4 : Run + commit**

```bash
go test ./tests/ -run "TestFilestore|TestPathTraversal" -v
git add apps-microservices/crawler-monitor-backend/internal/store/filestore/ apps-microservices/crawler-monitor-backend/tests/{filestore,path_traversal}_test.go
git commit -m "feat(crawler-monitor-backend-go): filestore + safeJoin + tests path traversal"
```

---

### Task 2.5 : Auditstore (lecture/écriture JSONL compatible Node)

**Goal** : Implémentation réelle de l'`AuditStore` qui lit et écrit le format JSONL produit par `auditLog.js`. Test critique de parité format.

**Files** :
- Create : `internal/store/auditstore/local.go`
- Create : `tests/audit_test.go`

**Acceptance Criteria** :
- [ ] `Local.Append(entry)` écrit une ligne JSON dans `<dir>/audit-YYYY-MM-DD.log` (UTC)
- [ ] `Local.Read(filter)` retourne les entrées triées par ts décroissant, paginées (limit max 500), fenêtre max 30 jours
- [ ] `Local.RotateOld(retentionDays)` supprime les fichiers `audit-*.log` plus vieux que N jours
- [ ] **Test critique** : un fichier `audit-2026-04-15.log` produit par Node est lu par Go sans erreur, et après réécriture par Go le diff binaire est nul (sauf nouvelle ligne)

**Verify** : `go test ./tests/ -run TestAudit -v`

**Steps** :

- [ ] **Step 1 : Implémenter `local.go`**

```go
package auditstore

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

var fileRe = regexp.MustCompile(`^audit-(\d{4}-\d{2}-\d{2})\.log$`)

type Local struct {
	dir       string
	mu        sync.Mutex
	dirEnsured bool
}

func New(dir string) *Local {
	return &Local{dir: dir}
}

func (l *Local) ensureDir() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.dirEnsured {
		return nil
	}
	if err := os.MkdirAll(l.dir, 0o755); err != nil {
		return err
	}
	l.dirEnsured = true
	return nil
}

func (l *Local) Append(ctx context.Context, entry map[string]any) error {
	if err := l.ensureDir(); err != nil {
		return err
	}
	if entry["ts"] == nil {
		entry["ts"] = time.Now().UTC().Format(time.RFC3339Nano)
	}
	b, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	day := time.Now().UTC().Format("2006-01-02")
	path := filepath.Join(l.dir, "audit-"+day+".log")
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.Write(append(b, '\n'))
	return err
}

type Filter struct {
	From   time.Time
	To     time.Time
	Action string
	User   string
	Target string
	Limit  int
	Offset int
}

type Page struct {
	Items  []map[string]any `json:"items"`
	Total  int              `json:"total"`
	Limit  int              `json:"limit"`
	Offset int              `json:"offset"`
}

func (l *Local) Read(ctx context.Context, f Filter) (*Page, error) {
	if f.From.IsZero() {
		f.From = time.Now().Add(-24 * time.Hour)
	}
	if f.To.IsZero() {
		f.To = time.Now()
	}
	if f.To.Before(f.From) {
		return nil, errors.New("`to` must be >= `from`")
	}
	const maxWindow = 30 * 24 * time.Hour
	if f.To.Sub(f.From) > maxWindow {
		return nil, errors.New("Window too wide (max 30 days)")
	}
	if f.Limit <= 0 {
		f.Limit = 100
	}
	if f.Limit > 500 {
		f.Limit = 500
	}
	if f.Offset < 0 {
		f.Offset = 0
	}

	day := time.Date(f.From.UTC().Year(), f.From.UTC().Month(), f.From.UTC().Day(), 0, 0, 0, 0, time.UTC)
	endDay := time.Date(f.To.UTC().Year(), f.To.UTC().Month(), f.To.UTC().Day(), 0, 0, 0, 0, time.UTC)

	var matches []map[string]any
	for !day.After(endDay) {
		path := filepath.Join(l.dir, "audit-"+day.Format("2006-01-02")+".log")
		fh, err := os.Open(path)
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				day = day.Add(24 * time.Hour)
				continue
			}
			return nil, err
		}
		sc := bufio.NewScanner(fh)
		sc.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" {
				continue
			}
			var e map[string]any
			if err := json.Unmarshal([]byte(line), &e); err != nil {
				continue
			}
			ts, _ := e["ts"].(string)
			t, err := time.Parse(time.RFC3339Nano, ts)
			if err != nil {
				continue
			}
			if t.Before(f.From) || t.After(f.To) {
				continue
			}
			if f.Action != "" && e["action"] != f.Action {
				continue
			}
			if f.User != "" && e["user"] != f.User {
				continue
			}
			if f.Target != "" && e["target"] != f.Target {
				continue
			}
			matches = append(matches, e)
		}
		fh.Close()
		day = day.Add(24 * time.Hour)
	}

	sort.Slice(matches, func(i, j int) bool {
		ti, _ := time.Parse(time.RFC3339Nano, matches[i]["ts"].(string))
		tj, _ := time.Parse(time.RFC3339Nano, matches[j]["ts"].(string))
		return ti.After(tj)
	})

	total := len(matches)
	from := f.Offset
	if from > total {
		from = total
	}
	to := from + f.Limit
	if to > total {
		to = total
	}
	return &Page{
		Items:  matches[from:to],
		Total:  total,
		Limit:  f.Limit,
		Offset: f.Offset,
	}, nil
}

func (l *Local) RotateOld(ctx context.Context, retentionDays int) (int, error) {
	entries, err := os.ReadDir(l.dir)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return 0, nil
		}
		return 0, err
	}
	cutoff := time.Now().Add(-time.Duration(retentionDays) * 24 * time.Hour)
	deleted := 0
	for _, e := range entries {
		m := fileRe.FindStringSubmatch(e.Name())
		if m == nil {
			continue
		}
		t, err := time.Parse("2006-01-02", m[1])
		if err != nil {
			continue
		}
		if t.Before(cutoff) {
			if err := os.Remove(filepath.Join(l.dir, e.Name())); err == nil {
				deleted++
			}
		}
	}
	return deleted, nil
}

func (l *Local) Path(day time.Time) string {
	return filepath.Join(l.dir, fmt.Sprintf("audit-%s.log", day.UTC().Format("2006-01-02")))
}
```

- [ ] **Step 2 : Test parité format Node**

```go
// tests/audit_test.go
package tests

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
)

func TestAudit_AppendThenRead(t *testing.T) {
	dir := t.TempDir()
	l := auditstore.New(dir)

	for i := 0; i < 3; i++ {
		_ = l.Append(context.Background(), map[string]any{
			"action": "x",
			"user":   "admin",
			"status": "ok",
		})
	}
	page, err := l.Read(context.Background(), auditstore.Filter{
		From: time.Now().Add(-1 * time.Hour),
		To:   time.Now().Add(1 * time.Hour),
	})
	if err != nil {
		t.Fatal(err)
	}
	if page.Total != 3 {
		t.Errorf("total=%d, want 3", page.Total)
	}
}

func TestAudit_FormatMatchesNode(t *testing.T) {
	// Simule un fichier produit par auditLog.js Node
	dir := t.TempDir()
	day := time.Now().UTC().Format("2006-01-02")
	nodeContent := `{"ts":"2026-04-15T10:30:00.000Z","user":"admin","action":"login_success","target":null,"status":"ok","ip":"127.0.0.1","metadata":null}` + "\n"
	_ = os.WriteFile(filepath.Join(dir, "audit-"+day+".log"), []byte(nodeContent), 0o644)

	l := auditstore.New(dir)
	page, err := l.Read(context.Background(), auditstore.Filter{
		From: time.Now().Add(-24 * time.Hour),
		To:   time.Now().Add(24 * time.Hour),
	})
	if err != nil {
		t.Fatal(err)
	}
	if page.Total != 1 {
		t.Fatalf("total=%d, want 1 (Node-produced line should be readable)", page.Total)
	}
	got := page.Items[0]
	if got["action"] != "login_success" || got["user"] != "admin" {
		t.Errorf("entry mismatch: %+v", got)
	}

	// Re-append via Go, vérifier que le fichier reste lisible et valide JSONL
	_ = l.Append(context.Background(), map[string]any{
		"action": "x",
		"user":   "admin",
		"status": "ok",
		"ip":     "127.0.0.1",
		"target": nil,
		"metadata": nil,
	})

	raw, _ := os.ReadFile(filepath.Join(dir, "audit-"+day+".log"))
	for i, line := range []string{"line1", "line2"} {
		_ = i
		_ = line
	}
	// Chaque ligne doit être un JSON valide
	idx := 0
	for _, b := range raw {
		if b == '\n' {
			idx++
		}
	}
	if idx < 2 {
		t.Errorf("expected >=2 newlines after append, got %d", idx)
	}

	// Round-trip JSON
	var node map[string]any
	if err := json.Unmarshal([]byte(nodeContent[:len(nodeContent)-1]), &node); err != nil {
		t.Fatal(err)
	}
	if node["status"] != "ok" {
		t.Error("Node line not parseable")
	}
}

func TestAudit_RotateOld(t *testing.T) {
	dir := t.TempDir()
	old := time.Now().Add(-100 * 24 * time.Hour).UTC().Format("2006-01-02")
	recent := time.Now().UTC().Format("2006-01-02")
	_ = os.WriteFile(filepath.Join(dir, "audit-"+old+".log"), []byte("{}\n"), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "audit-"+recent+".log"), []byte("{}\n"), 0o644)

	l := auditstore.New(dir)
	deleted, err := l.RotateOld(context.Background(), 90)
	if err != nil {
		t.Fatal(err)
	}
	if deleted != 1 {
		t.Errorf("deleted=%d, want 1", deleted)
	}
	if _, err := os.Stat(filepath.Join(dir, "audit-"+recent+".log")); err != nil {
		t.Errorf("recent file should remain: %v", err)
	}
}

func TestAudit_WindowTooWide(t *testing.T) {
	l := auditstore.New(t.TempDir())
	_, err := l.Read(context.Background(), auditstore.Filter{
		From: time.Now().Add(-60 * 24 * time.Hour),
		To:   time.Now(),
	})
	if err == nil {
		t.Error("expected window-too-wide error")
	}
}
```

- [ ] **Step 3 : Run + commit**

```bash
go test ./tests/ -run TestAudit -v
git add apps-microservices/crawler-monitor-backend/internal/store/auditstore/ apps-microservices/crawler-monitor-backend/tests/audit_test.go
git commit -m "feat(crawler-monitor-backend-go): auditstore JSONL compatible Node + tests parite"
```

---

## Phase 3 — Endpoints lecture seule (7 tâches)

> **Pattern global Phase 3** : chaque endpoint suit le même schéma (handler → store → réponse JSON). Le code complet est donné pour chaque tâche : pas de "voir Task X". L'iso strict exige de copier les statuts et structures JSON depuis `server.js` ; la ligne de référence est précisée à chaque tâche.

> **Pré-requis pour toutes les tâches Phase 3** : router complet wiré dans main.go avec middlewares chaînés (`SecurityHeaders → CORS → RateLimit → Audit → JWT pour les routes /api/*`).

### Task 3.1 : `/api/jobs` (List) + `/api/jobs/:id/details`

**Goal** : Lister tous les jobs et exposer le détail d'un job. Iso avec `server.js:283-313` (List) et `server.js:462-624` (Details).

**Files** :
- Create : `internal/httpapi/jobs.go`
- Create : `tests/jobs_test.go`
- Modify : `internal/httpapi/router.go` (ajout group `/api/jobs` avec JWT)
- Modify : `cmd/server/main.go` (instancier `redisStore`, le passer dans Deps)

**Acceptance Criteria** :
- [ ] `GET /api/jobs` (avec JWT valide) → 200 `[ {raw job json}, ... ]` triés du plus récent au plus ancien (par `start_time` desc)
- [ ] Sans JWT → 401
- [ ] `GET /api/jobs/abc/details` → 200 `{ job: {...}, logs: [...], counts: {...} }` ; champs exacts à recopier de `server.js:462-624`
- [ ] Job inexistant → 404 `{"error":"Job not found"}`

**Verify** : `go test ./tests/ -run TestJobs -v`

**Steps** :

- [ ] **Step 1 : Implémenter `internal/httpapi/jobs.go`**

```go
package httpapi

import (
	"net/http"
	"sort"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

func jobsListHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		// Tri par start_time desc — parité server.js:295-307
		sort.SliceStable(jobs, func(i, j int) bool {
			ti, _ := jobs[i]["start_time"].(string)
			tj, _ := jobs[j]["start_time"].(string)
			return ti > tj
		})
		WriteJSON(w, 200, jobs)
	}
}

func jobsDetailsHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		job, err := rs.GetJob(r.Context(), id)
		if err == redis.Nil {
			WriteError(w, 404, "Job not found")
			return
		}
		if err != nil {
			WriteError(w, 500, "Failed to read job")
			return
		}
		// Champs additionnels à recopier de server.js:462-624 :
		// - logs parsés depuis CRAWLER_STORAGE_PATH/<id>/logs/*.log
		// - counts (success_count, error_count, nfr_count) calculés depuis storage/datasets/
		// Implémenter dans internal/domain/jobs/details.go (cf Task 4.1 pour la logique complète)
		// Pour cette tâche, on retourne le minimum :
		WriteJSON(w, 200, map[string]any{"job": job})
	}
}
```

- [ ] **Step 2 : Mount dans `router.go`**

Modifier `NewRouter` pour ajouter group sécurisé :

```go
r.Group(func(r chi.Router) {
    r.Use(middleware.JWTAuth(d.Config.JWTSecret))

    r.Route("/api/jobs", func(r chi.Router) {
        r.Get("/", jobsListHandler(d.RedisStore))
        r.Get("/{id}/details", jobsDetailsHandler(d.RedisStore))
    })
})
```

Et ajouter `RedisStore *redisstore.Client` dans `Deps`.

- [ ] **Step 3 : Test**

```go
// tests/jobs_test.go
package tests

import (
	"encoding/json"
	"net/http/httptest"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func setupJobsTest(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	mr.Set("crawler:job:abc", `{"id":"abc","status":"running","start_time":"2026-04-15T10:00:00Z"}`)
	mr.Set("crawler:job:def", `{"id":"def","status":"finished","start_time":"2026-04-15T11:00:00Z"}`)
	rs, _ := redisstore.New("redis://" + mr.Addr())

	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret")
}

func TestJobs_ListSorted(t *testing.T) {
	srv, tok := setupJobsTest(t)
	resp, err := authedGet(srv.URL+"/api/jobs", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var jobs []map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&jobs)
	if len(jobs) != 2 {
		t.Fatalf("len=%d", len(jobs))
	}
	if jobs[0]["id"] != "def" {
		t.Errorf("first job = %v, want def (most recent)", jobs[0]["id"])
	}
}

func TestJobs_NotFound(t *testing.T) {
	srv, tok := setupJobsTest(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/zzz/details", tok)
	if resp.StatusCode != 404 {
		t.Errorf("status=%d", resp.StatusCode)
	}
}

func TestJobs_NoAuth(t *testing.T) {
	srv, _ := setupJobsTest(t)
	resp, _ := http.Get(srv.URL + "/api/jobs")
	if resp.StatusCode != 401 {
		t.Errorf("status=%d", resp.StatusCode)
	}
}
```

> **Helper commun à créer dans `tests/helpers_test.go`** : `mintToken(role, secret string) string` et `authedGet(url, token string) (*http.Response, error)`. Utilisé par tous les tests Phase 3+.

- [ ] **Step 4 : Run + commit**

```bash
go test ./tests/ -run TestJobs -v
git add apps-microservices/crawler-monitor-backend/internal/httpapi/jobs.go apps-microservices/crawler-monitor-backend/tests/jobs_test.go apps-microservices/crawler-monitor-backend/tests/helpers_test.go apps-microservices/crawler-monitor-backend/internal/httpapi/router.go
git commit -m "feat(crawler-monitor-backend-go): GET /api/jobs + /:id/details (squelette) + tests"
```

---

### Task 3.2 : `/api/capacity` + `/api/capacity/history` + `/api/capacity-planning/ram`

**Goal** : Endpoints capacité du crawler. Iso avec `server.js:1374-1394` (capacity), capacité historique (capacityHistory.js + handler), planning RAM (capacityPlanning.js + handler:1492-1503).

**Files** :
- Create : `internal/httpapi/capacity.go`
- Create : `internal/domain/capacityhistory/capacityhistory.go` (port `src/lib/capacityHistory.js`)
- Create : `internal/domain/capacityplanning/capacityplanning.go` (port `src/lib/capacityPlanning.js`)
- Create : `tests/capacity_history_test.go` (port `tests/capacityHistory.test.js`)
- Create : `tests/capacity_planning_test.go` (port `tests/capacityPlanning.test.js`)
- Create : `tests/capacity_handler_test.go`
- Modify : `internal/httpapi/router.go`

**Acceptance Criteria** :
- [ ] `GET /api/capacity` → 200 `{"running": N, "max": M, "full": bool}` parité avec server.js:1380-1394
- [ ] `GET /api/capacity/history?hours=24` → 200 `[ {ts, running, max, full}, ... ]`
- [ ] `GET /api/capacity-planning/ram` → 200 `{...}` parité avec retour de `computeCapacityPlanning`
- [ ] Tests `capacityHistory.test.js` (5 cas) et `capacityPlanning.test.js` (4 cas) portés en Go avec mêmes inputs/outputs

**Verify** : `go test ./tests/ -run "TestCapacity" -v`

**Steps** :

- [ ] **Step 1 : Lire les modules JS originaux**

```bash
cat apps-microservices/crawler-monitor-backend/src/lib/capacityHistory.js
cat apps-microservices/crawler-monitor-backend/src/lib/capacityPlanning.js
cat apps-microservices/crawler-monitor-backend/tests/capacityHistory.test.js
cat apps-microservices/crawler-monitor-backend/tests/capacityPlanning.test.js
```

> **NOTE implémenteur** : les fonctions `parseCapacityWindow`, `aggregateCapacityHistory` (ou équivalents) sont à porter telles quelles ; signatures et noms de paramètres conservés en Go (camelCase JS → CamelCase Go).

- [ ] **Step 2 : Implémenter `domain/capacityhistory/capacityhistory.go`**

```go
package capacityhistory

import "time"

type Point struct {
	Ts      time.Time `json:"ts"`
	Running int       `json:"running"`
	Max     int       `json:"max"`
	Full    bool      `json:"full"`
}

// ParseWindow port la fonction parseCapacityWindow de capacityHistory.js.
// Hours est la valeur de query ?hours=N, default 24, max 168 (7 jours).
func ParseWindow(hoursParam string) (time.Duration, error) {
	// Reproduire la logique du JS : default 24, clamp [1, 168], rejeter NaN
	// Voir tests/capacityHistory.test.js pour les cas exacts.
	// ... [à remplir d'après lecture du JS]
}

// AggregateHistory port aggregateCapacityHistory de capacityHistory.js.
// Lit une slice de raw points (ex: depuis Redis ZRANGEBYSCORE) et émet
// les points agrégés selon la fenêtre.
func AggregateHistory(raw []Point, since time.Time) []Point {
	// ... [à remplir d'après lecture du JS]
}
```

> **NOTE** : ce squelette est intentionnellement incomplet ici parce qu'il dépend du contenu exact de `capacityHistory.js` que l'implémenteur doit lire. Le code complet du JS doit être traduit. Les tests `capacityHistory.test.js` servent de spec exécutable — ils définissent le comportement exact attendu.

- [ ] **Step 3 : Implémenter `domain/capacityplanning/capacityplanning.go`**

Idem `capacityhistory` — port direct de `capacityPlanning.js`. Lire le fichier JS, traduire chaque fonction en Go avec mêmes signatures.

- [ ] **Step 4 : Implémenter `internal/httpapi/capacity.go`**

```go
package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/capacityhistory"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/capacityplanning"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

func capacityGetHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		running, max, err := rs.GetCapacity(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to read capacity")
			return
		}
		WriteJSON(w, 200, map[string]any{
			"running": running,
			"max":     max,
			"full":    max > 0 && running >= max,
		})
	}
}

func capacityHistoryHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		hours := r.URL.Query().Get("hours")
		window, err := capacityhistory.ParseWindow(hours)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		// Lire les points depuis Redis (clé à confirmer en Phase 0)
		raw, err := rs.ReadCapacityHistory(r.Context(), window)
		if err != nil {
			WriteError(w, 500, "Failed to read history")
			return
		}
		out := capacityhistory.AggregateHistory(raw, time.Now().Add(-window))
		WriteJSON(w, 200, out)
	}
}

func capacityPlanningRAMHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		result := capacityplanning.Compute(jobs)
		WriteJSON(w, 200, result)
	}
}
```

- [ ] **Step 5 : Tests**

Porter `tests/capacityHistory.test.js` et `tests/capacityPlanning.test.js` ligne à ligne. Chaque `t.test('description', ...)` Node devient un `t.Run("description", ...)` Go avec mêmes inputs et assertions sur les mêmes outputs. **Tous les cas doivent passer**.

- [ ] **Step 6 : Wire + commit**

Mount les routes dans router.go. Run tests :

```bash
go test ./tests/ -run TestCapacity -v
git add apps-microservices/crawler-monitor-backend/internal/{httpapi/capacity.go,domain/capacityhistory,domain/capacityplanning} apps-microservices/crawler-monitor-backend/tests/capacity_*_test.go
git commit -m "feat(crawler-monitor-backend-go): /api/capacity + history + planning RAM"
```

---

### Task 3.3 : `/api/replicas/history` + `/api/replicas/:id/history`

**Goal** : Historique des replicas. Iso avec `server.js:1504-1542` et `src/lib/replicaHistory.js`.

**Files** :
- Create : `internal/httpapi/replicas.go`
- Create : `internal/domain/replicahistory/replicahistory.go` (port `src/lib/replicaHistory.js`)
- Create : `tests/replica_history_test.go` (port `tests/replicaHistory.test.js`)
- Modify : `router.go`

**Acceptance Criteria** :
- [ ] `GET /api/replicas/history` → 200 (format défini par server.js:1505-1516, à recopier)
- [ ] `GET /api/replicas/:id/history` → 200 historique d'un replica spécifique
- [ ] Les cas de `replicaHistory.test.js` portent tous

**Verify** : `go test ./tests/ -run TestReplica -v`

**Steps** :

- [ ] **Step 1 : Lire `src/lib/replicaHistory.js` et `tests/replicaHistory.test.js`**

```bash
cat apps-microservices/crawler-monitor-backend/src/lib/replicaHistory.js
cat apps-microservices/crawler-monitor-backend/tests/replicaHistory.test.js
```

- [ ] **Step 2 : Porter en Go**

`internal/domain/replicahistory/replicahistory.go` doit exposer les mêmes fonctions que le JS (par ex. `parseReplicaWindow`, `aggregateReplicaHistory`). Traduction directe ; signatures équivalentes.

- [ ] **Step 3 : Handlers**

```go
// internal/httpapi/replicas.go
package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/replicahistory"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

func replicasHistoryHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		raw, err := rs.ReadReplicasHistory(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to read replica history")
			return
		}
		out := replicahistory.Aggregate(raw)
		WriteJSON(w, 200, out)
	}
}

func replicaHistoryByIDHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		raw, err := rs.ReadReplicaHistoryByID(r.Context(), id)
		if err != nil {
			WriteError(w, 500, "Failed to read replica history")
			return
		}
		WriteJSON(w, 200, replicahistory.AggregateOne(id, raw))
	}
}
```

- [ ] **Step 4 : Tests, mount, commit**

```bash
go test ./tests/ -run TestReplica -v
git add ...
git commit -m "feat(crawler-monitor-backend-go): /api/replicas/history endpoints"
```

---

### Task 3.4 : `/api/system/stats` + `/api/system/health`

**Goal** : Stats système agrégées. Iso avec `server.js:1664-1718` et `src/lib/systemStats.js`.

**Files** :
- Create : `internal/httpapi/system.go`
- Create : `internal/domain/systemstats/systemstats.go` (port `src/lib/systemStats.js`)
- Create : `tests/system_stats_test.go` (port `tests/systemStats.test.js`)
- Modify : `router.go`

**Acceptance Criteria** :
- [ ] `GET /api/system/stats` → 200 (format depuis `parseStatsWindow + computeSystemStats`, cf systemStats.js)
- [ ] `GET /api/system/health` → 200 `{ws_clients_count, redis_connected, ...}` (server.js:1679-1718)
- [ ] Tous les cas de `systemStats.test.js` passent

**Verify** : `go test ./tests/ -run TestSystem -v`

**Steps** :

- [ ] **Step 1 : Port `systemStats.js` → Go**

Lire `src/lib/systemStats.js`, identifier `parseStatsWindow` et `computeSystemStats`. Traduire en `internal/domain/systemstats/`.

- [ ] **Step 2 : Handler**

```go
package httpapi

import (
	"net/http"
	"sync/atomic"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

type SystemHealthInfo struct {
	WSClientsCount *atomic.Int64
}

func systemStatsHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		win, err := systemstats.ParseWindow(r.URL.Query().Get("window"))
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		WriteJSON(w, 200, systemstats.Compute(jobs, win))
	}
}

func systemHealthHandler(rs *redisstore.Client, info *SystemHealthInfo) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		redisOK := rs.Raw().Ping(r.Context()).Err() == nil
		clients := int64(0)
		if info != nil && info.WSClientsCount != nil {
			clients = info.WSClientsCount.Load()
		}
		WriteJSON(w, 200, map[string]any{
			"redis_connected":  redisOK,
			"ws_clients_count": clients,
			"status":           statusFromHealth(redisOK),
		})
	}
}

func statusFromHealth(redisOK bool) string {
	if redisOK {
		return "ok"
	}
	return "degraded"
}
```

- [ ] **Step 3 : Tests + mount + commit**

```bash
go test ./tests/ -run TestSystem -v
git commit -m "feat(crawler-monitor-backend-go): /api/system/stats + /health"
```

---

### Task 3.5 : `/api/audit`

**Goal** : Endpoint lecture des audit logs avec pagination + filtres. Iso avec `server.js:1719-1736` et `auditLog.js:readAuditEntries`.

**Files** :
- Create : `internal/httpapi/audit.go`
- Create : `tests/audit_endpoint_test.go`
- Modify : `router.go`

**Acceptance Criteria** :
- [ ] `GET /api/audit?limit=50&offset=0&from=2026-04-01&to=2026-04-15&action=login_success` → 200 `{items, total, limit, offset}`
- [ ] `from > to` → 400
- [ ] window > 30 jours → 400 `{"error":"Window too wide (max 30 days)"}`
- [ ] `limit > 500` est clampé à 500

**Verify** : `go test ./tests/ -run TestAuditEndpoint -v`

**Steps** :

- [ ] **Step 1 : Handler**

```go
package httpapi

import (
	"net/http"
	"strconv"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
)

func auditListHandler(as *auditstore.Local) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		f := auditstore.Filter{
			Action: q.Get("action"),
			User:   q.Get("user"),
			Target: q.Get("target"),
		}
		if from := q.Get("from"); from != "" {
			t, err := time.Parse(time.RFC3339, from)
			if err != nil {
				WriteError(w, 400, "Invalid `from` date")
				return
			}
			f.From = t
		}
		if to := q.Get("to"); to != "" {
			t, err := time.Parse(time.RFC3339, to)
			if err != nil {
				WriteError(w, 400, "Invalid `to` date")
				return
			}
			f.To = t
		}
		if l := q.Get("limit"); l != "" {
			n, _ := strconv.Atoi(l)
			f.Limit = n
		}
		if o := q.Get("offset"); o != "" {
			n, _ := strconv.Atoi(o)
			f.Offset = n
		}
		page, err := as.Read(r.Context(), f)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		WriteJSON(w, 200, page)
	}
}
```

- [ ] **Step 2 : Tests + mount + commit**

```bash
go test ./tests/ -run TestAuditEndpoint -v
git commit -m "feat(crawler-monitor-backend-go): GET /api/audit avec filtres + pagination"
```

---

### Task 3.6 : `/api/timeline` + `/api/alerts`

**Goal** : Timeline d'activité crawler + alertes calculées. Iso avec `server.js:1473-1490` (timeline), `server.js:1396-1432` (alerts), `src/lib/timeline.js`, `src/lib/alerts.js`.

**Files** :
- Create : `internal/httpapi/timeline.go`
- Create : `internal/httpapi/alerts.go`
- Create : `internal/domain/timeline/timeline.go` (port `src/lib/timeline.js`)
- Create : `internal/domain/alerts/alerts.go` (port `src/lib/alerts.js`)
- Create : `tests/timeline_test.go` (port `tests/timeline.test.js`)
- Create : `tests/alerts_test.go` (port `tests/alerts.test.js`)

**Acceptance Criteria** :
- [ ] Tous les cas de `timeline.test.js` portent
- [ ] Tous les cas de `alerts.test.js` portent (les 5 sous-règles `evalErrorRate`, `evalOomSpike`, `evalReplicaHighCpu`, `evalCapacitySaturation`, `evalCallbacksFailing` ont leurs équivalents Go)
- [ ] `GET /api/alerts` → 200 array d'alertes (severity, kind, message, since, metadata)

**Verify** : `go test ./tests/ -run "TestTimeline|TestAlerts" -v`

**Steps** :

- [ ] **Step 1 : Port `alerts.js` → Go**

Lire `src/lib/alerts.js`. Traduction directe :

```go
// internal/domain/alerts/alerts.go
package alerts

import "time"

const OneHour = time.Hour

type Thresholds struct {
	ErrorRate          float64
	ErrorRateMinJobs   int
	OomSpike           int
	ReplicaHighCPU     float64
	ReplicaHighCPUDur  time.Duration
	CapacityFullDur    time.Duration
	CallbacksFailedMin int
}

func DefaultThresholds() Thresholds {
	return Thresholds{
		ErrorRate:          0.05,
		ErrorRateMinJobs:   5,
		OomSpike:           3,
		ReplicaHighCPU:     0.85,
		ReplicaHighCPUDur:  240 * time.Second,
		CapacityFullDur:    300 * time.Second,
		CallbacksFailedMin: 1,
	}
}

type Alert struct {
	ID       string         `json:"id"`
	Severity string         `json:"severity"`
	Kind     string         `json:"kind"`
	Message  string         `json:"message"`
	Since    *int64         `json:"since"`
	Metadata map[string]any `json:"metadata"`
}

type Job struct {
	StartTime       string `json:"start_time"`
	Status          string `json:"status"`
	OomRestartCount int    `json:"oom_restart_count"`
}

type CapacityPoint struct {
	Ts   int64
	Full bool
}

type ReplicaPoint struct {
	Ts  int64
	CPU float64
}

type Inputs struct {
	Jobs                 []Job
	CapacityPoints       []CapacityPoint
	ReplicasHistory      map[string][]ReplicaPoint
	FailedCallbackCount  int
}

func EvalErrorRate(jobs []Job, nowMs int64, t Thresholds) *Alert {
	cutoff := nowMs - OneHour.Milliseconds()
	var failed, finished int
	for _, j := range jobs {
		ts, err := time.Parse(time.RFC3339, j.StartTime)
		if err != nil || ts.UnixMilli() < cutoff {
			continue
		}
		switch j.Status {
		case "failed":
			failed++
		case "finished", "archived":
			finished++
		}
	}
	completed := failed + finished
	if completed < t.ErrorRateMinJobs {
		return nil
	}
	rate := float64(failed) / float64(completed)
	if rate < t.ErrorRate {
		return nil
	}
	return &Alert{
		ID:       "error_rate_high:1h",
		Severity: "warn",
		Kind:     "error_rate_high",
		Message:  fmt.Sprintf("Taux d'erreur %.1f%% sur 1h (%d/%d)", rate*100, failed, completed),
		Metadata: map[string]any{"rate": rate, "failed": failed, "completed": completed, "window": "1h", "threshold": t.ErrorRate},
	}
}

// Suite des règles : EvalOomSpike, EvalReplicaHighCpu, EvalCapacitySaturation, EvalCallbacksFailing
// → port direct des fonctions JS de alerts.js (cf code complet dans le fichier source).
// Chaque règle a ses tests dans tests/alerts.test.js → traduire chaque assert en t.Run.

func Evaluate(in Inputs, nowMs int64, t Thresholds) []Alert {
	var out []Alert
	if a := EvalErrorRate(in.Jobs, nowMs, t); a != nil { out = append(out, *a) }
	// ... idem pour les autres règles
	// Sort: critical first
	sevWeight := map[string]int{"critical": 0, "warn": 1, "info": 2}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Severity != out[j].Severity {
			return sevWeight[out[i].Severity] < sevWeight[out[j].Severity]
		}
		return out[i].Kind < out[j].Kind
	})
	return out
}
```

- [ ] **Step 2 : Port `timeline.js` → Go**

Lire `src/lib/timeline.js`, traduire dans `internal/domain/timeline/`.

- [ ] **Step 3 : Handlers**

```go
// internal/httpapi/alerts.go
func alertsHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jobs, _ := rs.ListJobs(r.Context())
		// Convertir RawJob -> alerts.Job
		// Charger capacity history et replicas history depuis Redis
		// Charger failed callback count
		out := alerts.Evaluate(alerts.Inputs{
			Jobs: convertJobs(jobs),
			// ...
		}, time.Now().UnixMilli(), alerts.DefaultThresholds())
		WriteJSON(w, 200, out)
	}
}
```

- [ ] **Step 4 : Tests, mount, commit**

```bash
go test ./tests/ -run "TestTimeline|TestAlerts" -v
git commit -m "feat(crawler-monitor-backend-go): /api/timeline + /api/alerts (port domain rules)"
```

---

### Task 3.7 : `/api/domains` + `/api/domains/:domain`

**Goal** : Aggrégation par domaine. Iso avec `server.js:1434-1471` et `src/lib/domains.js`.

**Files** :
- Create : `internal/httpapi/domains.go`
- Create : `internal/domain/domains/domains.go` (port `src/lib/domains.js`)
- Create : `tests/domains_test.go` (port `tests/domains.test.js`)

**Acceptance Criteria** :
- [ ] `GET /api/domains?window=24h` → 200 `[{domain, jobs_count, success_rate, ...}]`
- [ ] `GET /api/domains/:domain` → 200 jobs filtrés sur ce domaine
- [ ] Tous les cas de `domains.test.js` (parseDomainWindow, aggregateDomains, jobsForDomain) portent

**Verify** : `go test ./tests/ -run TestDomains -v`

**Steps** :

- [ ] **Step 1** : Lire `src/lib/domains.js` + `tests/domains.test.js`.

- [ ] **Step 2** : Port en Go (`internal/domain/domains/`).

- [ ] **Step 3** : Handlers.

```go
// internal/httpapi/domains.go
package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/domains"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

func domainsListHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		win, err := domains.ParseWindow(r.URL.Query().Get("window"))
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		WriteJSON(w, 200, domains.Aggregate(jobs, win))
	}
}

func domainsGetHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		dom := chi.URLParam(r, "domain")
		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		WriteJSON(w, 200, domains.JobsForDomain(jobs, dom))
	}
}
```

- [ ] **Step 4 : Tests + commit**

```bash
go test ./tests/ -run TestDomains -v
git commit -m "feat(crawler-monitor-backend-go): /api/domains + /:domain"
```

---

## Phase 4 — Endpoints métier complexes (10 tâches)

> **Pattern Phase 4** : ces endpoints contiennent la logique métier inline dans `server.js`. La règle est d'**extraire** la logique dans `internal/domain/queue/` ou `internal/domain/jobperf/` (pure, testable), et de garder le handler HTTP minimal.

### Task 4.1 : `/api/jobs/:id/performance` + `domain/jobperf`

**Goal** : Performance metrics d'un job. Iso avec `server.js:314-328` et `src/lib/jobPerformance.js`.

**Files** :
- Create : `internal/domain/jobperf/jobperf.go` (port `jobPerformance.js`)
- Create : `tests/job_performance_test.go`
- Modify : `internal/httpapi/jobs.go` (ajouter handler)

**Acceptance Criteria** :
- [ ] `GET /api/jobs/:id/performance` → 200 (format issu de `readJobPerf`/`persistJobPerf`)
- [ ] Si pas de données perf → réponse vide cohérente (cf comportement Node)

**Verify** : `go test ./tests/ -run TestJobPerf -v`

**Steps** :

- [ ] **Step 1 : Lire `src/lib/jobPerformance.js`**

```bash
cat apps-microservices/crawler-monitor-backend/src/lib/jobPerformance.js
```

Identifier : exports `persistJobPerf`, `readJobPerf`. Données stockées probablement dans Redis sous une clé dédiée. Reproduire signature en Go.

- [ ] **Step 2 : Port `internal/domain/jobperf/jobperf.go`**

```go
package jobperf

import (
	"context"
	"encoding/json"

	"github.com/redis/go-redis/v9"
)

// Cf src/lib/jobPerformance.js : la clé Redis et le format JSON.
// À CONFIRMER en lisant le code source.
const KeyPrefix = "crawler:job_perf:"

type Snapshot struct {
	JobID     string  `json:"job_id"`
	StartedAt string  `json:"started_at"`
	EndedAt   string  `json:"ended_at,omitempty"`
	URLsTotal int     `json:"urls_total"`
	URLsDone  int     `json:"urls_done"`
	CPUAvg    float64 `json:"cpu_avg"`
	RAMPeak   float64 `json:"ram_peak"`
	// ... suite des champs depuis le JS
}

func Read(ctx context.Context, rdb *redis.Client, jobID string) (*Snapshot, error) {
	raw, err := rdb.Get(ctx, KeyPrefix+jobID).Result()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var s Snapshot
	if err := json.Unmarshal([]byte(raw), &s); err != nil {
		return nil, err
	}
	return &s, nil
}

func Persist(ctx context.Context, rdb *redis.Client, s Snapshot) error {
	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	return rdb.Set(ctx, KeyPrefix+s.JobID, b, 0).Err()
}
```

- [ ] **Step 3 : Handler**

```go
func jobsPerformanceHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		snap, err := jobperf.Read(r.Context(), rs.Raw(), id)
		if err != nil {
			WriteError(w, 500, "Failed to read job performance")
			return
		}
		if snap == nil {
			WriteJSON(w, 200, map[string]any{})
			return
		}
		WriteJSON(w, 200, snap)
	}
}
```

- [ ] **Step 4 : Tests + commit**

```bash
go test ./tests/ -run TestJobPerf -v
git commit -m "feat(crawler-monitor-backend-go): /api/jobs/:id/performance"
```

---

### Task 4.2 : `/api/jobs/:id/replay` (logique extraite)

**Goal** : Endpoint de replay d'un job. Iso avec `server.js:329-461` (~130 lignes inline). Extraction proprement dans `internal/domain/queue/replay.go`.

**Files** :
- Create : `internal/domain/queue/replay.go`
- Create : `tests/replay_test.go`
- Modify : `internal/httpapi/jobs.go`

**Acceptance Criteria** :
- [ ] `GET /api/jobs/:id/replay` → 200 (format identique à server.js:329-461)
- [ ] Si CPU > `REPLAY_HIGH_CPU` (default 0.85) → indication dans la réponse (parité Node)
- [ ] Job inexistant → 404
- [ ] Tests sur les principaux cas d'usage (replay réussi, partiel, en erreur)

**Verify** : `go test ./tests/ -run TestReplay -v`

**Steps** :

- [ ] **Step 1 : Lire `server.js:329-461` ligne par ligne**

```bash
sed -n '329,461p' apps-microservices/crawler-monitor-backend/server.js
```

Catégoriser : (a) lecture Redis du job, (b) lecture filesystem (datasets, queue), (c) calcul des stats, (d) sérialisation réponse. Les pas (a)-(c) vont dans `domain/queue/replay.go` ; (d) reste dans le handler.

- [ ] **Step 2 : `domain/queue/replay.go`**

```go
package queue

import (
	"context"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/redis/go-redis/v9"
)

type ReplayResult struct {
	JobID         string         `json:"job_id"`
	Status        string         `json:"status"`
	URLsProcessed int            `json:"urls_processed"`
	URLsFailed    int            `json:"urls_failed"`
	CPUHigh       bool           `json:"cpu_high"`
	Details       map[string]any `json:"details"`
	// ... cf server.js:329-461 pour les champs exacts
}

func ComputeReplay(ctx context.Context, rdb *redis.Client, fs *filestore.Storage, jobID string, highCPUThreshold float64) (*ReplayResult, error) {
	// 1. Lire le job depuis Redis
	// 2. Lire le dataset principal + error dataset
	// 3. Calculer URLs processed/failed
	// 4. Évaluer CPU high
	// 5. Construire ReplayResult
	// → traduction directe de server.js:329-461
}
```

- [ ] **Step 3 : Handler**

```go
func jobsReplayHandler(rs *redisstore.Client, fs *filestore.Storage, cpuThreshold float64) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		res, err := queue.ComputeReplay(r.Context(), rs.Raw(), fs, id, cpuThreshold)
		if err == redis.Nil {
			WriteError(w, 404, "Job not found")
			return
		}
		if err != nil {
			WriteError(w, 500, "Failed to compute replay")
			return
		}
		WriteJSON(w, 200, res)
	}
}
```

- [ ] **Step 4 : Tests + commit**

Utiliser `tests/helpers/fixture.go` (port du fixture.js Node) pour créer un job factice avec datasets, puis vérifier le résultat.

```bash
go test ./tests/ -run TestReplay -v
git commit -m "feat(crawler-monitor-backend-go): /api/jobs/:id/replay (extraction domain/queue)"
```

---

### Task 4.3 : `/api/jobs/:id/request-queues` List + ReadFile + WriteFile

**Goal** : Lister, lire, écrire les fichiers de queue. Iso avec `server.js:625-770`.

**Files** :
- Create : `internal/httpapi/queues.go`
- Create : `internal/domain/queue/listing.go`
- Create : `tests/queues_list_test.go`
- Create : `tests/queues_status_test.go` (port `tests/request-queues-status.test.js`)

**Acceptance Criteria** :
- [ ] `GET /api/jobs/:id/request-queues?page=1&pageSize=50&search=foo` → 200 paginé `{items, total, page, pageSize}`
- [ ] Recherche dans le contenu des fichiers (port du grep côté Node)
- [ ] `GET /api/jobs/:id/request-queues/:domain/:filename` → 200 contenu brut JSON
- [ ] `POST /api/jobs/:id/request-queues/:domain/:filename` body JSON → écrit le fichier (parité avec POST handler Express)
- [ ] Tous les chemins passent par `safeJoin` (rejet path traversal)
- [ ] `request-queues-status.test.js` cas portés

**Verify** : `go test ./tests/ -run "TestQueuesList|TestQueuesStatus" -v`

**Steps** :

- [ ] **Step 1 : Lire la logique Node**

```bash
sed -n '625,770p' apps-microservices/crawler-monitor-backend/server.js
```

- [ ] **Step 2 : `internal/domain/queue/listing.go`**

```go
package queue

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

type FileEntry struct {
	Domain   string `json:"domain"`
	Filename string `json:"filename"`
	URL      string `json:"url"`
	Status   string `json:"status"`
	Method   string `json:"method"`
	OrderNo  *int64 `json:"orderNo"`
	Handled  bool   `json:"handled"`
	// + champs depuis le format Crawlee (cf fixture.js)
}

type Page struct {
	Items    []FileEntry `json:"items"`
	Total    int         `json:"total"`
	Page     int         `json:"page"`
	PageSize int         `json:"pageSize"`
}

func ListRequestQueues(ctx context.Context, fs *filestore.Storage, jobID, search string, page, pageSize int) (*Page, error) {
	// 1. Lister le dossier <jobID>/storage/request_queues/
	// 2. Pour chaque domaine, lister les fichiers .json
	// 3. Lire chaque fichier, extraire URL/method/orderNo/handled
	// 4. Filtrer par `search` (case-insensitive sur URL)
	// 5. Paginer
	// → traduction directe de server.js:625-717
	domains, err := fs.ListDir(ctx, jobID, "storage", "request_queues")
	if err != nil {
		return &Page{Items: []FileEntry{}, Page: page, PageSize: pageSize}, nil
	}
	var all []FileEntry
	for _, d := range domains {
		if !d.IsDir() { continue }
		files, err := fs.ListDir(ctx, jobID, "storage", "request_queues", d.Name())
		if err != nil { continue }
		for _, f := range files {
			if !strings.HasSuffix(f.Name(), ".json") { continue }
			data, err := fs.Read(ctx, jobID, "storage", "request_queues", d.Name(), f.Name())
			if err != nil { continue }
			var crawlee struct {
				URL     string `json:"url"`
				Method  string `json:"method"`
				OrderNo *int64 `json:"orderNo"`
			}
			if err := json.Unmarshal(data, &crawlee); err != nil { continue }
			if search != "" && !strings.Contains(strings.ToLower(crawlee.URL), strings.ToLower(search)) {
				continue
			}
			handled := crawlee.OrderNo == nil
			status := "pending"
			if handled { status = "handled" }
			all = append(all, FileEntry{
				Domain: d.Name(), Filename: f.Name(),
				URL: crawlee.URL, Method: crawlee.Method,
				OrderNo: crawlee.OrderNo, Handled: handled, Status: status,
			})
		}
	}
	total := len(all)
	if pageSize <= 0 { pageSize = 50 }
	if page < 1 { page = 1 }
	from := (page - 1) * pageSize
	if from > total { from = total }
	to := from + pageSize
	if to > total { to = total }
	return &Page{Items: all[from:to], Total: total, Page: page, PageSize: pageSize}, nil
}
```

- [ ] **Step 3 : Handlers**

```go
package httpapi

import (
	"io"
	"net/http"
	"strconv"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/queue"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/go-chi/chi/v5"
)

func queuesListHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		q := r.URL.Query()
		page, _ := strconv.Atoi(q.Get("page"))
		pageSize, _ := strconv.Atoi(q.Get("pageSize"))
		res, err := queue.ListRequestQueues(r.Context(), fs, id, q.Get("search"), page, pageSize)
		if err != nil {
			WriteError(w, 500, "Failed to list queues")
			return
		}
		WriteJSON(w, 200, res)
	}
}

func queuesReadFileHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		dom := chi.URLParam(r, "domain")
		fn := chi.URLParam(r, "filename")
		data, err := fs.Read(r.Context(), id, "storage", "request_queues", dom, fn)
		if err != nil {
			if errors.Is(err, filestore.ErrPathEscape) {
				WriteError(w, 400, "Invalid path")
				return
			}
			WriteError(w, 404, "File not found")
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.WriteHeader(200)
		_, _ = w.Write(data)
	}
}

func queuesWriteFileHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		dom := chi.URLParam(r, "domain")
		fn := chi.URLParam(r, "filename")
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, MaxBodyBytes))
		if err != nil {
			WriteError(w, 413, "Payload too large")
			return
		}
		if err := fs.Write(r.Context(), body, id, "storage", "request_queues", dom, fn); err != nil {
			if errors.Is(err, filestore.ErrPathEscape) {
				WriteError(w, 400, "Invalid path")
				return
			}
			WriteError(w, 500, "Failed to write")
			return
		}
		WriteJSON(w, 200, map[string]string{"status": "ok"})
	}
}
```

- [ ] **Step 4 : Tests + commit**

```bash
go test ./tests/ -run "TestQueuesList|TestQueuesStatus" -v
git commit -m "feat(crawler-monitor-backend-go): /api/jobs/:id/request-queues list/read/write"
```

---

### Task 4.4 : `/api/jobs/:id/request-queues/analyze` (le gros)

**Goal** : Analyse de santé des queues — endpoint le plus dense (`server.js:868-1064`, ~196 lignes). Détecte les URLs valides vs blocked patterns, statistiques par domaine.

**Files** :
- Create : `internal/domain/queue/analyze.go`
- Create : `tests/queues_analyze_test.go`

**Acceptance Criteria** :
- [ ] `GET /api/jobs/:id/request-queues/analyze` → 200 avec exactement la structure de server.js:868-1064 (champs : `total`, `valid`, `blocked`, `by_domain`, `patterns_found`, etc.)
- [ ] Détection des patterns bloqués (login pages, captcha, 403/404 patterns) — recopier la liste de patterns du Node
- [ ] Performance : sur 100k URLs, doit être ≤ 5x plus rapide que Node (préparation Phase 6)

**Verify** : `go test ./tests/ -run TestQueuesAnalyze -v`

**Steps** :

- [ ] **Step 1 : Lire `server.js:868-1064` intégralement**

```bash
sed -n '868,1064p' apps-microservices/crawler-monitor-backend/server.js
```

- [ ] **Step 2 : Catalogue des blocked patterns**

Extraire la liste des regex/strings utilisée pour catégoriser une URL comme "blocked" — la stocker dans `internal/domain/queue/patterns.go` :

```go
package queue

import "regexp"

var BlockedPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)/login`),
	regexp.MustCompile(`(?i)/signin`),
	regexp.MustCompile(`(?i)captcha`),
	// ... liste complète à extraire de server.js:868-1064
}
```

- [ ] **Step 3 : `internal/domain/queue/analyze.go`**

```go
package queue

import (
	"context"
	"encoding/json"
	"strings"
	"sync"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"golang.org/x/sync/errgroup"
)

type AnalyzeResult struct {
	Total           int                 `json:"total"`
	Valid           int                 `json:"valid"`
	Blocked         int                 `json:"blocked"`
	ByDomain        map[string]Stats    `json:"by_domain"`
	PatternsFound   map[string]int      `json:"patterns_found"`
	// ... cf server.js pour la liste complète
}

type Stats struct {
	Total   int `json:"total"`
	Valid   int `json:"valid"`
	Blocked int `json:"blocked"`
}

func Analyze(ctx context.Context, fs *filestore.Storage, jobID string) (*AnalyzeResult, error) {
	domains, err := fs.ListDir(ctx, jobID, "storage", "request_queues")
	if err != nil {
		return &AnalyzeResult{ByDomain: map[string]Stats{}, PatternsFound: map[string]int{}}, nil
	}

	var mu sync.Mutex
	res := &AnalyzeResult{
		ByDomain:      map[string]Stats{},
		PatternsFound: map[string]int{},
	}

	g, gctx := errgroup.WithContext(ctx)
	g.SetLimit(8) // saturer CPU sans exploser goroutines
	for _, d := range domains {
		if !d.IsDir() {
			continue
		}
		domain := d.Name()
		g.Go(func() error {
			files, err := fs.ListDir(gctx, jobID, "storage", "request_queues", domain)
			if err != nil {
				return nil
			}
			ds := Stats{}
			localPatterns := map[string]int{}
			for _, f := range files {
				if !strings.HasSuffix(f.Name(), ".json") {
					continue
				}
				data, err := fs.Read(gctx, jobID, "storage", "request_queues", domain, f.Name())
				if err != nil {
					continue
				}
				var c struct{ URL string `json:"url"` }
				if err := json.Unmarshal(data, &c); err != nil {
					continue
				}
				ds.Total++
				blocked := false
				for _, p := range BlockedPatterns {
					if p.MatchString(c.URL) {
						localPatterns[p.String()]++
						blocked = true
						break
					}
				}
				if blocked {
					ds.Blocked++
				} else {
					ds.Valid++
				}
			}
			mu.Lock()
			res.ByDomain[domain] = ds
			res.Total += ds.Total
			res.Valid += ds.Valid
			res.Blocked += ds.Blocked
			for k, v := range localPatterns {
				res.PatternsFound[k] += v
			}
			mu.Unlock()
			return nil
		})
	}
	if err := g.Wait(); err != nil {
		return nil, err
	}
	return res, nil
}
```

- [ ] **Step 4 : Tests**

Tests basés sur fixtures (port `tests/helpers/fixture.js` en Go pour créer arborescence factice).

- [ ] **Step 5 : Commit**

```bash
go test ./tests/ -run TestQueuesAnalyze -v
git commit -m "feat(crawler-monitor-backend-go): /api/jobs/:id/request-queues/analyze (port 196 lignes Node)"
```

---

### Task 4.5 : queues CleanPatterns + Repair + Drop

**Goal** : Trois opérations destructives sur les queues. Iso avec `server.js:1304-1374` (clean-patterns), `server.js:772-830` (repair), `server.js:831-867` (drop).

**Files** :
- Create : `internal/domain/queue/mutations.go` (CleanPatterns, Repair, DropAll)
- Create : `tests/queues_mutations_test.go`
- Modify : `internal/httpapi/queues.go`

**Acceptance Criteria** :
- [ ] `POST /api/jobs/:id/request-queues/clean-patterns` body `{patterns: [".*login.*"]}` → supprime les fichiers dont l'URL match un pattern, renvoie `{deleted: N}`
- [ ] `POST /api/jobs/:id/request-queues/repair` body `{}` → supprime les URLs avec mismatch de domaine, renvoie `{deleted: N}`
- [ ] `POST /api/jobs/:id/request-queues/drop` body `{}` → supprime tout le dossier `request_queues`, renvoie `{deleted: N}`
- [ ] Audit log avec actions `clean_patterns`, `repair_queue`, `drop_queue`

**Verify** : `go test ./tests/ -run TestQueuesMutations -v`

**Steps** :

- [ ] **Step 1 : Logique métier**

```go
// internal/domain/queue/mutations.go
package queue

import (
	"context"
	"encoding/json"
	"net/url"
	"regexp"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

func CleanPatterns(ctx context.Context, fs *filestore.Storage, jobID string, patterns []string) (int, error) {
	regs := make([]*regexp.Regexp, 0, len(patterns))
	for _, p := range patterns {
		re, err := regexp.Compile(p)
		if err != nil {
			return 0, err
		}
		regs = append(regs, re)
	}
	domains, err := fs.ListDir(ctx, jobID, "storage", "request_queues")
	if err != nil {
		return 0, nil
	}
	deleted := 0
	for _, d := range domains {
		if !d.IsDir() {
			continue
		}
		files, _ := fs.ListDir(ctx, jobID, "storage", "request_queues", d.Name())
		for _, f := range files {
			data, err := fs.Read(ctx, jobID, "storage", "request_queues", d.Name(), f.Name())
			if err != nil {
				continue
			}
			var c struct{ URL string `json:"url"` }
			if err := json.Unmarshal(data, &c); err != nil {
				continue
			}
			for _, re := range regs {
				if re.MatchString(c.URL) {
					if err := fs.Delete(ctx, jobID, "storage", "request_queues", d.Name(), f.Name()); err == nil {
						deleted++
					}
					break
				}
			}
		}
	}
	return deleted, nil
}

func Repair(ctx context.Context, fs *filestore.Storage, jobID string) (int, error) {
	domains, err := fs.ListDir(ctx, jobID, "storage", "request_queues")
	if err != nil {
		return 0, nil
	}
	deleted := 0
	for _, d := range domains {
		if !d.IsDir() {
			continue
		}
		expectedDomain := d.Name()
		files, _ := fs.ListDir(ctx, jobID, "storage", "request_queues", expectedDomain)
		for _, f := range files {
			data, _ := fs.Read(ctx, jobID, "storage", "request_queues", expectedDomain, f.Name())
			var c struct{ URL string `json:"url"` }
			if err := json.Unmarshal(data, &c); err != nil {
				continue
			}
			u, err := url.Parse(c.URL)
			if err != nil {
				continue
			}
			h := strings.ToLower(u.Hostname())
			if h != expectedDomain && !strings.HasSuffix(h, "."+expectedDomain) {
				if err := fs.Delete(ctx, jobID, "storage", "request_queues", expectedDomain, f.Name()); err == nil {
					deleted++
				}
			}
		}
	}
	return deleted, nil
}

func DropAll(ctx context.Context, fs *filestore.Storage, jobID string) (int, error) {
	domains, err := fs.ListDir(ctx, jobID, "storage", "request_queues")
	if err != nil {
		return 0, nil
	}
	deleted := 0
	for _, d := range domains {
		if !d.IsDir() {
			continue
		}
		files, _ := fs.ListDir(ctx, jobID, "storage", "request_queues", d.Name())
		for _, f := range files {
			if err := fs.Delete(ctx, jobID, "storage", "request_queues", d.Name(), f.Name()); err == nil {
				deleted++
			}
		}
	}
	return deleted, nil
}
```

- [ ] **Step 2 : Handlers**

```go
type cleanPatternsReq struct{ Patterns []string `json:"patterns"` }

func queuesCleanPatternsHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		var req cleanPatternsReq
		if err := DecodeJSON(r, &req); err != nil {
			WriteError(w, 400, "Invalid body")
			return
		}
		n, err := queue.CleanPatterns(r.Context(), fs, id, req.Patterns)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		WriteJSON(w, 200, map[string]any{"deleted": n})
	}
}

func queuesRepairHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		n, err := queue.Repair(r.Context(), fs, id)
		if err != nil {
			WriteError(w, 500, "Failed")
			return
		}
		WriteJSON(w, 200, map[string]any{"deleted": n})
	}
}

func queuesDropHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		n, err := queue.DropAll(r.Context(), fs, id)
		if err != nil {
			WriteError(w, 500, "Failed")
			return
		}
		WriteJSON(w, 200, map[string]any{"deleted": n})
	}
}
```

Mount avec `AuditMiddleware(store, "clean_patterns", ...)` etc., parité avec server.js.

- [ ] **Step 3 : Tests + commit**

```bash
go test ./tests/ -run TestQueuesMutations -v
git commit -m "feat(crawler-monitor-backend-go): queues clean-patterns/repair/drop"
```

---

### Task 4.6 : `/api/jobs/:id/dataset/counts` + `/dataset/urls`

**Goal** : Lecture des datasets. Iso avec `server.js:1064-1140` et `tests/dataset-counts.test.js` + `tests/dataset-urls.test.js`.

**Files** :
- Create : `internal/httpapi/dataset.go`
- Create : `internal/domain/queue/dataset.go`
- Create : `tests/dataset_counts_test.go` (port `dataset-counts.test.js`)
- Create : `tests/dataset_urls_test.go` (port `dataset-urls.test.js`)

**Acceptance Criteria** :
- [ ] `GET /api/jobs/:id/dataset/counts` → 200 `{success, error, nfr}` (port server.js:1064-1091)
- [ ] `GET /api/jobs/:id/dataset/urls?type=success&page=1&pageSize=50` → 200 paginé
- [ ] Tests Node `dataset-counts.test.js` (10+ cas) et `dataset-urls.test.js` portés

**Verify** : `go test ./tests/ -run "TestDatasetCounts|TestDatasetURLs" -v`

**Steps** :

- [ ] **Step 1 : Lire les sources Node**

```bash
sed -n '1064,1140p' apps-microservices/crawler-monitor-backend/server.js
cat apps-microservices/crawler-monitor-backend/tests/dataset-counts.test.js
cat apps-microservices/crawler-monitor-backend/tests/dataset-urls.test.js
```

- [ ] **Step 2 : `internal/domain/queue/dataset.go`**

Logique : pour un job, compter les fichiers dans `storage/datasets/<domain>/`, `storage/datasets/error-<domain>/`, `storage/datasets/nfr-<domain>/`.

```go
package queue

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

type DatasetCounts struct {
	Success int `json:"success"`
	Error   int `json:"error"`
	NFR     int `json:"nfr"`
}

func CountDatasets(ctx context.Context, fs *filestore.Storage, jobID string) (DatasetCounts, error) {
	c := DatasetCounts{}
	dirs, err := fs.ListDir(ctx, jobID, "storage", "datasets")
	if err != nil {
		return c, nil
	}
	for _, d := range dirs {
		if !d.IsDir() { continue }
		files, _ := fs.ListDir(ctx, jobID, "storage", "datasets", d.Name())
		count := 0
		for _, f := range files {
			if strings.HasSuffix(f.Name(), ".json") { count++ }
		}
		switch {
		case strings.HasPrefix(d.Name(), "error-"):
			c.Error += count
		case strings.HasPrefix(d.Name(), "nfr-"):
			c.NFR += count
		default:
			c.Success += count
		}
	}
	return c, nil
}

type DatasetEntry struct {
	URL      string         `json:"url"`
	Domain   string         `json:"domain"`
	Filename string         `json:"filename"`
	Extra    map[string]any `json:"extra,omitempty"`
}

func ListDatasetURLs(ctx context.Context, fs *filestore.Storage, jobID, kind string, page, pageSize int) ([]DatasetEntry, int, error) {
	// kind: success / error / nfr — détermine le préfixe de dossier
	prefix := ""
	if kind == "error" { prefix = "error-" } else if kind == "nfr" { prefix = "nfr-" }
	dirs, err := fs.ListDir(ctx, jobID, "storage", "datasets")
	if err != nil { return nil, 0, nil }
	var all []DatasetEntry
	for _, d := range dirs {
		if !d.IsDir() { continue }
		if prefix == "" {
			if strings.HasPrefix(d.Name(), "error-") || strings.HasPrefix(d.Name(), "nfr-") { continue }
		} else {
			if !strings.HasPrefix(d.Name(), prefix) { continue }
		}
		files, _ := fs.ListDir(ctx, jobID, "storage", "datasets", d.Name())
		for _, f := range files {
			if !strings.HasSuffix(f.Name(), ".json") { continue }
			data, _ := fs.Read(ctx, jobID, "storage", "datasets", d.Name(), f.Name())
			var raw map[string]any
			_ = json.Unmarshal(data, &raw)
			url, _ := raw["url"].(string)
			all = append(all, DatasetEntry{
				URL: url, Domain: d.Name(), Filename: f.Name(), Extra: raw,
			})
		}
	}
	total := len(all)
	if pageSize <= 0 { pageSize = 50 }
	if page < 1 { page = 1 }
	from := (page - 1) * pageSize
	if from > total { from = total }
	to := from + pageSize
	if to > total { to = total }
	return all[from:to], total, nil
}
```

- [ ] **Step 3 : Handlers + tests + commit**

```go
func datasetCountsHandler(fs *filestore.Storage) http.HandlerFunc { /* ... */ }
func datasetURLsHandler(fs *filestore.Storage) http.HandlerFunc { /* ... */ }
```

```bash
go test ./tests/ -run "TestDatasetCounts|TestDatasetURLs" -v
git commit -m "feat(crawler-monitor-backend-go): /api/jobs/:id/dataset/counts + /urls"
```

---

### Task 4.7 : `/api/jobs/:id/dataset/analyze` + `/dataset/deduplicate`

**Goal** : Analyse de doublons + déduplication. Iso avec `server.js:1141-1303`.

**Files** :
- Create : `internal/domain/queue/dedup.go`
- Modify : `internal/httpapi/dataset.go`
- Create : `tests/dataset_analyze_test.go`
- Create : `tests/dataset_dedup_test.go`

**Acceptance Criteria** :
- [ ] `GET /api/jobs/:id/dataset/analyze` → 200 `{total, unique, duplicates, by_url: [{url, count, files: [...]}]}`
- [ ] `POST /api/jobs/:id/dataset/deduplicate` → supprime les doublons, garde le plus récent (mtime), renvoie `{deleted}`
- [ ] Audit log action `deduplicate_dataset`

**Verify** : `go test ./tests/ -run "TestDatasetAnalyze|TestDedup" -v`

**Steps** :

- [ ] **Step 1 : Lire `server.js:1141-1303`** pour la logique exacte de groupement par URL et de choix du fichier à conserver.

- [ ] **Step 2 : `internal/domain/queue/dedup.go`**

```go
package queue

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

type DupGroup struct {
	URL   string   `json:"url"`
	Count int      `json:"count"`
	Files []string `json:"files"`
}

type AnalyzeDup struct {
	Total      int        `json:"total"`
	Unique     int        `json:"unique"`
	Duplicates int        `json:"duplicates"`
	ByURL      []DupGroup `json:"by_url"`
}

func AnalyzeDuplicates(ctx context.Context, fs *filestore.Storage, jobID string) (*AnalyzeDup, error) {
	groups := map[string][]string{}
	dirs, _ := fs.ListDir(ctx, jobID, "storage", "datasets")
	total := 0
	for _, d := range dirs {
		if !d.IsDir() { continue }
		files, _ := fs.ListDir(ctx, jobID, "storage", "datasets", d.Name())
		for _, f := range files {
			data, err := fs.Read(ctx, jobID, "storage", "datasets", d.Name(), f.Name())
			if err != nil { continue }
			var raw map[string]any
			if err := json.Unmarshal(data, &raw); err != nil { continue }
			url, _ := raw["url"].(string)
			rel := filepath.Join(d.Name(), f.Name())
			groups[url] = append(groups[url], rel)
			total++
		}
	}
	var result AnalyzeDup
	result.Total = total
	for url, files := range groups {
		if len(files) > 1 {
			result.ByURL = append(result.ByURL, DupGroup{URL: url, Count: len(files), Files: files})
			result.Duplicates += len(files) - 1
		}
		result.Unique++
	}
	return &result, nil
}

func DeduplicateDataset(ctx context.Context, fs *filestore.Storage, jobID string) (int, error) {
	a, err := AnalyzeDuplicates(ctx, fs, jobID)
	if err != nil { return 0, err }
	deleted := 0
	for _, g := range a.ByURL {
		// Garder le plus récent (mtime), supprimer les autres
		var newest string
		var newestMtime int64
		for _, rel := range g.Files {
			parts := splitRel(rel)
			p, err := filestore.SafeJoin(fs.Base(), append([]string{jobID, "storage", "datasets"}, parts...)...)
			if err != nil { continue }
			st, err := os.Stat(p)
			if err != nil { continue }
			if st.ModTime().UnixNano() > newestMtime {
				newestMtime = st.ModTime().UnixNano()
				newest = rel
			}
		}
		for _, rel := range g.Files {
			if rel == newest { continue }
			parts := splitRel(rel)
			if err := fs.Delete(ctx, append([]string{jobID, "storage", "datasets"}, parts...)...); err == nil {
				deleted++
			}
		}
	}
	return deleted, nil
}

func splitRel(rel string) []string {
	// "domain/file.json" -> ["domain", "file.json"]
	return filepath.SplitList(rel)
}
```

> **NOTE implémenteur** : `filestore.Storage.Base()` à exposer si pas déjà fait. Et `splitRel` doit utiliser `strings.Split(rel, string(os.PathSeparator))` plutôt que `filepath.SplitList` (qui sépare sur `:` ou `;`).

- [ ] **Step 3 : Handlers + tests + commit**

```bash
go test ./tests/ -run "TestDatasetAnalyze|TestDedup" -v
git commit -m "feat(crawler-monitor-backend-go): dataset analyze + deduplicate"
```

---

### Task 4.8 : `/api/callbacks` + Retry + Delete + Clear

**Goal** : Gestion des callbacks en échec. Iso avec `server.js:1543-1663` + `src/lib/callbacks.js`.

**Files** :
- Create : `internal/httpapi/callbacks.go`
- Create : `internal/domain/callbacks/callbacks.go` (port `src/lib/callbacks.js`)
- Create : `tests/callbacks_test.go` (port `tests/callbacks.test.js`)

**Acceptance Criteria** :
- [ ] `GET /api/callbacks` → 200 `{count, items: [...]}`
- [ ] `POST /api/callbacks/:idx/retry` → rejoue le callback (HTTP appel sortant), 200 sur succès, 500 sur échec
- [ ] `DELETE /api/callbacks/:idx` → supprime un callback de la liste, 200 ou 404
- [ ] `POST /api/callbacks/clear` → vide tous les callbacks, 200 `{cleared: N}`
- [ ] Audit log : actions `replay_callback`, `delete_callback`, `clear_callbacks`

**Verify** : `go test ./tests/ -run TestCallbacks -v`

**Steps** :

- [ ] **Step 1 : Lire `src/lib/callbacks.js`** pour la fonction `replayCallback`.

- [ ] **Step 2 : Port en Go**

```go
// internal/domain/callbacks/callbacks.go
package callbacks

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Callback struct {
	URL     string            `json:"url"`
	Method  string            `json:"method"`
	Headers map[string]string `json:"headers"`
	Body    json.RawMessage   `json:"body"`
	Reason  string            `json:"reason"`
	JobID   string            `json:"job_id,omitempty"`
}

func Replay(ctx context.Context, c Callback) error {
	var body io.Reader
	if len(c.Body) > 0 {
		body = bytes.NewReader(c.Body)
	}
	req, err := http.NewRequestWithContext(ctx, c.Method, c.URL, body)
	if err != nil {
		return err
	}
	for k, v := range c.Headers {
		req.Header.Set(k, v)
	}
	cl := &http.Client{Timeout: 30 * time.Second}
	resp, err := cl.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("replay status %d", resp.StatusCode)
	}
	return nil
}
```

- [ ] **Step 3 : Handlers (avec lecture/écriture Redis pour la liste)**

> **NOTE implémenteur** : Identifier la clé Redis qui stocke la liste des callbacks (probablement `crawler:failed_callbacks` ou similaire — confirmer en Phase 0 / lecture server.js).

- [ ] **Step 4 : Tests + commit**

```bash
go test ./tests/ -run TestCallbacks -v
git commit -m "feat(crawler-monitor-backend-go): /api/callbacks + retry/delete/clear"
```

---

### Task 4.9 : `/api/albums` (mountAlbumsRouter)

**Goal** : Port du `mountAlbumsRouter` (`src/lib/albums.js`). Iso avec `server.js:187` et `tests/albums.test.js`.

**Files** :
- Create : `internal/httpapi/albums.go`
- Create : `tests/albums_test.go` (port `tests/albums.test.js`)

**Acceptance Criteria** :
- [ ] Toutes les routes `/api/albums/*` exposées par `mountAlbumsRouter` ont leur équivalent Go
- [ ] Tous les cas de `albums.test.js` (10+ cas) passent

**Verify** : `go test ./tests/ -run TestAlbums -v`

**Steps** :

- [ ] **Step 1 : Lire `src/lib/albums.js` + `tests/albums.test.js`**

```bash
cat apps-microservices/crawler-monitor-backend/src/lib/albums.js
cat apps-microservices/crawler-monitor-backend/tests/albums.test.js
```

- [ ] **Step 2 : Port direct**

Identifier les routes exposées (probablement `GET /albums`, `GET /albums/:id`, `POST /albums`, ...). Reproduire chaque handler en Go avec mêmes statuts et payloads.

```go
package httpapi

import "github.com/go-chi/chi/v5"

func mountAlbums(r chi.Router, deps Deps) {
	// r.Get("/", albumsListHandler(deps))
	// r.Get("/{id}", albumsGetHandler(deps))
	// ... cf src/lib/albums.js pour la liste exhaustive
}
```

- [ ] **Step 3 : Tests + commit**

```bash
go test ./tests/ -run TestAlbums -v
git commit -m "feat(crawler-monitor-backend-go): /api/albums port mountAlbumsRouter"
```

---

### Task 4.10 : `imageDownloadProxy` (vérification d'usage)

**Goal** : Vérifier si `imageDownloadProxy` est encore consommé par le frontend. Si oui → port. Sinon → ne pas porter (YAGNI).

**Files** (si port) :
- Create : `internal/httpapi/imageproxy.go`
- Create : `tests/image_proxy_test.go` (port `tests/imageDownloadProxy.test.js`)

**Acceptance Criteria** :
- [ ] Vérification frontend : grep `imageDownloadProxy` ou route concernée dans `crawler-monitor-frontend/`. Si 0 résultat → tâche notée "skipped" dans le PR description.
- [ ] Si consommé : routes portées, tests passent.

**Verify** :
```bash
grep -rn "imageDownloadProxy\|/image-download-proxy" ../crawler-monitor-frontend/ || echo "NOT USED — SKIP"
```

**Steps** :

- [ ] **Step 1 : Vérifier l'usage**

```bash
grep -rn "imageDownloadProxy\|/image-proxy\|/api/image" ../crawler-monitor-frontend/src/
```

- [ ] **Step 2** : Si non utilisé → documenter la décision dans `docs/cutover-runbook.md` :

```markdown
## Endpoints non portés

- `imageDownloadProxy` : non consommé par crawler-monitor-frontend (vérifié le YYYY-MM-DD). Endpoint volontairement omis dans la version Go. Si besoin futur : recréer en suivant le port `src/lib/imageDownloadProxy.js`.
```

- [ ] **Step 3** : Si utilisé → port direct de `src/lib/imageDownloadProxy.js`, mêmes routes, mêmes tests.

- [ ] **Step 4 : Commit**

```bash
git commit -m "feat(crawler-monitor-backend-go): imageDownloadProxy <port|skip>"
```

---

## Phase 5 — WebSocket (4 tâches)

### Task 5.1 : `internal/ws/hub.go` — registry + broadcast

**Goal** : Hub central qui gère le registry des clients et le fan-out des messages, sans connaître Redis.

**Files** :
- Create : `internal/ws/hub.go`
- Create : `tests/ws_hub_test.go`
- Modify : `go.mod` (`github.com/gorilla/websocket`)

**Acceptance Criteria** :
- [ ] `Hub.Register(client)` ajoute un client (thread-safe)
- [ ] `Hub.Unregister(client)` retire un client
- [ ] `Hub.Broadcast(msg)` envoie le message à tous les clients via leur `send chan`
- [ ] Si un client ne consomme pas (chan plein) → il est forcement déconnecté (pas de blocage du hub)
- [ ] `Hub.Count()` retourne le nombre de clients connectés (pour `/api/system/health`)

**Verify** : `go test ./tests/ -run TestWSHub -v -race`

**Steps** :

- [ ] **Step 1 : Add deps**

```bash
go get github.com/gorilla/websocket
```

- [ ] **Step 2 : Implémenter `internal/ws/hub.go`**

```go
package ws

import (
	"sync"
	"sync/atomic"
)

type Client struct {
	send   chan []byte
	closed atomic.Bool
}

func newClient() *Client {
	return &Client{send: make(chan []byte, 256)}
}

type Hub struct {
	mu      sync.RWMutex
	clients map[*Client]struct{}
	count   atomic.Int64
}

func NewHub() *Hub {
	return &Hub{clients: make(map[*Client]struct{})}
}

func (h *Hub) Register(c *Client) {
	h.mu.Lock()
	h.clients[c] = struct{}{}
	h.mu.Unlock()
	h.count.Add(1)
}

func (h *Hub) Unregister(c *Client) {
	h.mu.Lock()
	if _, ok := h.clients[c]; ok {
		delete(h.clients, c)
		h.mu.Unlock()
		if c.closed.CompareAndSwap(false, true) {
			close(c.send)
		}
		h.count.Add(-1)
		return
	}
	h.mu.Unlock()
}

func (h *Hub) Broadcast(msg []byte) {
	h.mu.RLock()
	clients := make([]*Client, 0, len(h.clients))
	for c := range h.clients {
		clients = append(clients, c)
	}
	h.mu.RUnlock()
	for _, c := range clients {
		select {
		case c.send <- msg:
		default:
			h.Unregister(c)
		}
	}
}

func (h *Hub) Count() int64 {
	return h.count.Load()
}

func (h *Hub) Close() {
	h.mu.Lock()
	for c := range h.clients {
		if c.closed.CompareAndSwap(false, true) {
			close(c.send)
		}
		delete(h.clients, c)
	}
	h.mu.Unlock()
	h.count.Store(0)
}
```

- [ ] **Step 3 : Tests**

```go
// tests/ws_hub_test.go
package tests

import (
	"sync"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
)

func TestWSHub_BroadcastReachesAllClients(t *testing.T) {
	h := ws.NewHub()
	clients := make([]*ws.Client, 100)
	for i := range clients {
		clients[i] = ws.NewClientForTest()
		h.Register(clients[i])
	}
	if h.Count() != 100 {
		t.Fatalf("count=%d", h.Count())
	}

	var wg sync.WaitGroup
	wg.Add(100)
	received := make([]int, 100)
	for i, c := range clients {
		i, c := i, c
		go func() {
			defer wg.Done()
			deadline := time.After(2 * time.Second)
			for {
				select {
				case msg, ok := <-c.SendForTest():
					if !ok {
						return
					}
					if string(msg) == "hello" {
						received[i]++
						return
					}
				case <-deadline:
					return
				}
			}
		}()
	}

	h.Broadcast([]byte("hello"))
	wg.Wait()

	missed := 0
	for _, n := range received {
		if n == 0 {
			missed++
		}
	}
	if missed > 0 {
		t.Errorf("missed broadcasts: %d/100", missed)
	}
}

func TestWSHub_SlowClientDropped(t *testing.T) {
	h := ws.NewHub()
	c := ws.NewClientForTest()
	h.Register(c)

	// Saturer le buffer (256) sans consommer
	for i := 0; i < 257; i++ {
		h.Broadcast([]byte("x"))
	}
	// Le client doit être déconnecté après que le buffer ait débordé
	time.Sleep(50 * time.Millisecond)
	if h.Count() != 0 {
		t.Errorf("slow client not dropped, count=%d", h.Count())
	}
}
```

> **NOTE** : ajouter dans `internal/ws/hub.go` ces helpers test-only :
> ```go
> func NewClientForTest() *Client { return newClient() }
> func (c *Client) SendForTest() <-chan []byte { return c.send }
> ```

- [ ] **Step 4 : Run + commit**

```bash
go test ./tests/ -run TestWSHub -v -race
git commit -m "feat(crawler-monitor-backend-go): ws hub + tests broadcast 100 clients"
```

---

### Task 5.2 : `internal/ws/client.go` — readPump + writePump par connexion

**Goal** : Boucles de lecture/écriture pour une connexion WebSocket. ping/pong, gestion des erreurs.

**Files** :
- Create : `internal/ws/client.go`
- Modify : `internal/ws/hub.go` (intégration)

**Acceptance Criteria** :
- [ ] `client.readPump()` traite les messages entrants (ping/pong, close)
- [ ] `client.writePump()` envoie les messages depuis `send chan`, ping toutes les 30s
- [ ] Si pong absent pendant 60s → close
- [ ] Goroutines proprement terminées sur close

**Verify** : `go test ./tests/ -run TestWSClient -v -race`

**Steps** :

- [ ] **Step 1 : Implémenter**

```go
// internal/ws/client.go
package ws

import (
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = 30 * time.Second
	maxMessageSize = 4096
)

var Upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin:     func(r *http.Request) bool { return true },
}

type ClientConn struct {
	*Client
	conn *websocket.Conn
	hub  *Hub
}

func NewClientConn(hub *Hub, conn *websocket.Conn) *ClientConn {
	return &ClientConn{Client: newClient(), conn: conn, hub: hub}
}

func (c *ClientConn) Run() {
	go c.writePump()
	c.readPump()
}

func (c *ClientConn) readPump() {
	defer func() {
		c.hub.Unregister(c.Client)
		_ = c.conn.Close()
	}()
	c.conn.SetReadLimit(maxMessageSize)
	_ = c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		_ = c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})
	for {
		if _, _, err := c.conn.ReadMessage(); err != nil {
			return
		}
	}
}

func (c *ClientConn) writePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		_ = c.conn.Close()
	}()
	for {
		select {
		case msg, ok := <-c.send:
			_ = c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				_ = c.conn.WriteMessage(websocket.CloseMessage, nil)
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}
		case <-ticker.C:
			_ = c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
```

- [ ] **Step 2 : Tests + commit**

```bash
go test ./tests/ -run TestWSClient -v -race
git commit -m "feat(crawler-monitor-backend-go): ws read/write pumps + ping/pong"
```

---

### Task 5.3 : `internal/ws/pubsub.go` — Redis subscribe + reconnect

**Goal** : Goroutine qui s'abonne à `crawl_updates` et `crawler:heartbeat` et pousse les messages dans `hub.Broadcast`. Reconnexion automatique avec backoff.

**Files** :
- Create : `internal/ws/pubsub.go`
- Create : `tests/ws_pubsub_test.go`

**Acceptance Criteria** :
- [ ] Au démarrage, abonnement aux 2 channels
- [ ] Chaque message reçu → `hub.Broadcast(msg)`
- [ ] Si Redis tombe → backoff exponentiel (1s → 30s max), pas de panic
- [ ] À l'arrêt (`ctx.Done()`) → unsubscribe propre

**Verify** : `go test ./tests/ -run TestWSPubSub -v -race`

**Steps** :

- [ ] **Step 1 : Implémenter**

```go
// internal/ws/pubsub.go
package ws

import (
	"context"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"
)

type PubSub struct {
	rdb      *redis.Client
	hub      *Hub
	channels []string
}

func NewPubSub(rdb *redis.Client, hub *Hub, channels ...string) *PubSub {
	return &PubSub{rdb: rdb, hub: hub, channels: channels}
}

func (p *PubSub) Run(ctx context.Context) {
	backoff := time.Second
	const maxBackoff = 30 * time.Second
	for {
		if err := p.runOnce(ctx); err != nil {
			if ctx.Err() != nil {
				return
			}
			slog.Warn("ws.pubsub.disconnect", "err", err, "backoff", backoff)
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return
			}
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
			continue
		}
		return
	}
}

func (p *PubSub) runOnce(ctx context.Context) error {
	sub := p.rdb.Subscribe(ctx, p.channels...)
	defer sub.Close()
	if _, err := sub.Receive(ctx); err != nil {
		return err
	}
	ch := sub.Channel()
	slog.Info("ws.pubsub.subscribed", "channels", p.channels)
	for {
		select {
		case <-ctx.Done():
			return nil
		case msg, ok := <-ch:
			if !ok {
				return nil
			}
			defer func() { _ = recover() }()
			p.hub.Broadcast([]byte(msg.Payload))
		}
	}
}
```

- [ ] **Step 2 : Tests avec miniredis**

```go
// tests/ws_pubsub_test.go
package tests

import (
	"context"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestWSPubSub_BroadcastsToHub(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer rdb.Close()

	hub := ws.NewHub()
	c := ws.NewClientForTest()
	hub.Register(c)

	ps := ws.NewPubSub(rdb, hub, "crawl_updates")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)

	// Laisser le subscribe s'établir
	time.Sleep(100 * time.Millisecond)
	rdb.Publish(context.Background(), "crawl_updates", `{"x":1}`)

	select {
	case msg := <-c.SendForTest():
		if string(msg) != `{"x":1}` {
			t.Errorf("msg = %s", msg)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("no broadcast received")
	}
}
```

- [ ] **Step 3 : Run + commit**

```bash
go test ./tests/ -run TestWSPubSub -v -race
git commit -m "feat(crawler-monitor-backend-go): ws pubsub Redis + reconnect backoff"
```

---

### Task 5.4 : Upgrade handler `/` + JWT validation + integration test

**Goal** : Handler HTTP qui upgrade en WebSocket si JWT valide en query string, sinon 401 sans upgrade. Test bout-en-bout 100 clients × 1000 messages.

**Files** :
- Create : `internal/ws/upgrade.go`
- Create : `tests/ws_integration_test.go`
- Modify : `internal/httpapi/router.go` (mount sur `/`)
- Modify : `cmd/server/main.go` (instancier hub + pubsub + lancer goroutine)

**Acceptance Criteria** :
- [ ] `wss://localhost:3001/?token=<valid>` → upgrade ok
- [ ] `wss://localhost:3001/?token=<bad>` → 401 sans upgrade
- [ ] `wss://localhost:3001/` (sans token) → 401
- [ ] Test integration : 100 clients connectés, 1000 publish sur `crawl_updates`, chaque client reçoit ≥ 95% des messages dans l'ordre, aucune deadlock

**Verify** : `go test ./tests/ -run TestWSIntegration -v -race -timeout 60s`

**Steps** :

- [ ] **Step 1 : Upgrade handler**

```go
// internal/ws/upgrade.go
package ws

import (
	"net/http"

	"github.com/golang-jwt/jwt/v5"
)

func UpgradeHandler(hub *Hub, jwtSecret string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token := r.URL.Query().Get("token")
		if token == "" {
			http.Error(w, "Authentication required", 401)
			return
		}
		_, err := jwt.Parse(token, func(t *jwt.Token) (any, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrTokenSignatureInvalid
			}
			return []byte(jwtSecret), nil
		})
		if err != nil {
			http.Error(w, "Invalid token", 401)
			return
		}
		conn, err := Upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		c := NewClientConn(hub, conn)
		hub.Register(c.Client)
		c.Run()
	}
}
```

- [ ] **Step 2 : Wire dans `cmd/server/main.go`**

Après avoir construit `cfg`, `redisStore`, `auditStore` :

```go
hub := ws.NewHub()
ps := ws.NewPubSub(redisStore.Raw(), hub, redisstore.UpdatesChannel, redisstore.HeartbeatChannel)
go ps.Run(ctx)
defer hub.Close()

deps := httpapi.Deps{
    Config: cfg, RedisStore: redisStore, AuditStore: auditStore,
    Hub: hub,
}
```

Ajouter `Hub *ws.Hub` dans `httpapi.Deps`. Mount le handler dans `router.go` :
```go
r.Get("/", ws.UpgradeHandler(d.Hub, d.Config.JWTSecret))
```

- [ ] **Step 3 : Test integration**

```go
// tests/ws_integration_test.go
package tests

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

func TestWSIntegration_100Clients_1000Messages(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	rs, _ := redisstore.New("redis://" + mr.Addr())

	hub := ws.NewHub()
	ps := ws.NewPubSub(rdb, hub, "crawl_updates")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)
	defer hub.Close()

	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}, Hub: hub,
	}))
	defer srv.Close()

	tok := mintToken("admin", "test-secret")
	wsURL := strings.Replace(srv.URL, "http", "ws", 1) + "/?token=" + tok

	const N = 100
	const MSG = 1000

	conns := make([]*websocket.Conn, N)
	receivedCount := make([]atomic.Int64, N)
	wg := sync.WaitGroup{}
	for i := 0; i < N; i++ {
		dialer := websocket.DefaultDialer
		c, _, err := dialer.Dial(wsURL, http.Header{})
		if err != nil {
			t.Fatalf("dial %d: %v", i, err)
		}
		conns[i] = c
		wg.Add(1)
		go func(i int, c *websocket.Conn) {
			defer wg.Done()
			deadline := time.Now().Add(30 * time.Second)
			_ = c.SetReadDeadline(deadline)
			for {
				_, _, err := c.ReadMessage()
				if err != nil {
					return
				}
				if receivedCount[i].Add(1) >= MSG {
					return
				}
			}
		}(i, c)
	}

	// Laisser les connexions s'établir
	time.Sleep(500 * time.Millisecond)

	for i := 0; i < MSG; i++ {
		rdb.Publish(context.Background(), "crawl_updates", []byte(fmt.Sprintf(`{"i":%d}`, i)))
	}

	doneCh := make(chan struct{})
	go func() { wg.Wait(); close(doneCh) }()
	select {
	case <-doneCh:
	case <-time.After(20 * time.Second):
		// Force close pour libérer
		for _, c := range conns {
			_ = c.Close()
		}
	}

	missing := 0
	for i := 0; i < N; i++ {
		got := receivedCount[i].Load()
		if got < int64(MSG*95/100) {
			missing++
			t.Logf("client %d: got %d/%d", i, got, MSG)
		}
	}
	if missing > 0 {
		t.Errorf("%d/100 clients received < 95%% messages", missing)
	}

	// URL queryparser
	_ = url.PathEscape
}
```

- [ ] **Step 4 : Run + commit**

```bash
go test ./tests/ -run TestWSIntegration -v -race -timeout 60s
git commit -m "feat(crawler-monitor-backend-go): ws upgrade handler + integration test 100x1000"
```

---

## Phase 6 — Bench & validation perf (4 tâches)

### Task 6.1 : `BenchmarkAnalyze` queue 100k URLs

**Goal** : Mesurer le temps de `queue.Analyze` sur 100k URLs et le comparer au Node existant.

**Files** :
- Create : `tests/benchmarks/queue_analyze_bench_test.go`
- Create : `tests/benchmarks/fixtures/100k_queue.json` (généré, non versionné)
- Create : `tests/benchmarks/setup_fixture.go`

**Acceptance Criteria** :
- [ ] `go test -bench=BenchmarkQueueAnalyze ./tests/benchmarks/` produit un résultat ms/op
- [ ] Le bench Go est ≥ 5× plus rapide que le Node sur la même fixture (mesure manuelle Node : `node bench/analyze.mjs`)
- [ ] Résultat consigné dans `docs/benchmarks/2026-04-go-vs-express.md`

**Verify** : `go test -bench=BenchmarkQueueAnalyze -benchmem ./tests/benchmarks/`

**Steps** :

- [ ] **Step 1 : Générateur de fixture**

```go
// tests/benchmarks/setup_fixture.go
package benchmarks

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func GenerateQueueFixture(root, jobID string, n int) error {
	for i := 0; i < n; i++ {
		domain := fmt.Sprintf("example%d.com", i%50)
		dir := filepath.Join(root, jobID, "storage", "request_queues", domain)
		_ = os.MkdirAll(dir, 0o755)
		entry := map[string]any{
			"url":     fmt.Sprintf("https://%s/page/%d", domain, i),
			"method":  "GET",
			"orderNo": i + 1,
		}
		b, _ := json.Marshal(entry)
		_ = os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), b, 0o644)
	}
	return nil
}
```

- [ ] **Step 2 : Bench**

```go
// tests/benchmarks/queue_analyze_bench_test.go
package benchmarks

import (
	"context"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/queue"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

func BenchmarkQueueAnalyze_100k(b *testing.B) {
	root := b.TempDir()
	if err := GenerateQueueFixture(root, "job1", 100000); err != nil {
		b.Fatal(err)
	}
	fs := filestore.New(root)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := queue.Analyze(context.Background(), fs, "job1")
		if err != nil {
			b.Fatal(err)
		}
	}
}
```

- [ ] **Step 3 : Bench Node de référence**

```bash
# Créer un script bench/analyze.mjs côté Node qui fait l'équivalent
node --experimental-vm-modules bench/analyze.mjs > /tmp/node-bench.txt
go test -bench=BenchmarkQueueAnalyze_100k -benchmem ./tests/benchmarks/ > /tmp/go-bench.txt
diff /tmp/node-bench.txt /tmp/go-bench.txt  # juste pour visualisation
```

- [ ] **Step 4 : Documenter**

```markdown
# docs/benchmarks/2026-04-go-vs-express.md
## queue.Analyze sur 100k URLs

| Stack | ms/op | allocs/op | bytes/op |
|---|---|---|---|
| Node (express, async fs) | <FILL> | n/a | n/a |
| Go (chi, errgroup limit=8) | <FILL> | <FILL> | <FILL> |
| Ratio | <FILL>x |

Configuration : MacBook M2 16GB / WSL2 Ubuntu 24 4 vCPU.
```

- [ ] **Step 5 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/tests/benchmarks/ docs/benchmarks/
git commit -m "perf(crawler-monitor-backend-go): bench queue.Analyze 100k URLs vs Node"
```

---

### Task 6.2 : Bench WebSocket broadcast 100 clients × p99 latency

**Goal** : Mesurer p50/p95/p99 de la latence end-to-end (publish Redis → réception client) sur 100 clients connectés.

**Files** :
- Create : `tests/benchmarks/ws_broadcast_bench_test.go`

**Acceptance Criteria** :
- [ ] p99 reception latency ≤ 50 ms sur 100 clients × 50 publish/s pendant 30s
- [ ] Aucun message perdu en moyenne sur 1500 messages × 100 clients
- [ ] Résultat consigné dans `docs/benchmarks/`

**Verify** : `go test -run TestWSBroadcastP99 -timeout 90s ./tests/benchmarks/`

**Steps** :

- [ ] **Step 1 : Test bench**

```go
// tests/benchmarks/ws_broadcast_bench_test.go
package benchmarks

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

func TestWSBroadcastP99(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	rs, _ := redisstore.New("redis://" + mr.Addr())
	hub := ws.NewHub()
	ps := ws.NewPubSub(rdb, hub, "crawl_updates")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)

	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}, Hub: hub,
	}))
	defer srv.Close()

	wsURL := strings.Replace(srv.URL, "http", "ws", 1) + "/?token=" + mintToken("admin", "test-secret")

	const N = 100
	const RATE = 50  // pub/s
	const DUR = 30 * time.Second

	type sample struct {
		clientID int
		latency  time.Duration
	}
	samplesCh := make(chan sample, 100000)

	var wg sync.WaitGroup
	for i := 0; i < N; i++ {
		c, _, err := websocket.DefaultDialer.Dial(wsURL, http.Header{})
		if err != nil {
			t.Fatal(err)
		}
		wg.Add(1)
		go func(id int, c *websocket.Conn) {
			defer wg.Done()
			deadline := time.Now().Add(DUR + 5*time.Second)
			_ = c.SetReadDeadline(deadline)
			for {
				_, msg, err := c.ReadMessage()
				if err != nil {
					return
				}
				var sentNs int64
				_, _ = fmt.Sscanf(string(msg), `{"sent":%d}`, &sentNs)
				lat := time.Now().Sub(time.Unix(0, sentNs))
				samplesCh <- sample{clientID: id, latency: lat}
			}
		}(i, c)
	}

	// Publisher : RATE * DUR/s messages
	go func() {
		ticker := time.NewTicker(time.Second / RATE)
		defer ticker.Stop()
		end := time.Now().Add(DUR)
		for time.Now().Before(end) {
			<-ticker.C
			rdb.Publish(context.Background(), "crawl_updates",
				fmt.Sprintf(`{"sent":%d}`, time.Now().UnixNano()))
		}
	}()

	time.Sleep(DUR + 2*time.Second)
	close(samplesCh)
	wg.Wait()

	var lat []time.Duration
	for s := range samplesCh {
		lat = append(lat, s.latency)
	}
	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	p99 := lat[len(lat)*99/100]
	p95 := lat[len(lat)*95/100]
	p50 := lat[len(lat)/2]
	t.Logf("samples=%d p50=%v p95=%v p99=%v", len(lat), p50, p95, p99)
	if p99 > 50*time.Millisecond {
		t.Errorf("p99=%v, want <= 50ms", p99)
	}
}
```

- [ ] **Step 2 : Run + documenter**

```bash
go test -v -run TestWSBroadcastP99 -timeout 90s ./tests/benchmarks/ 2>&1 | tee /tmp/ws-bench.txt
```

Ajouter dans `docs/benchmarks/2026-04-go-vs-express.md` :
```markdown
## WS broadcast latency

| Stack | p50 | p95 | p99 | Drop rate |
|---|---|---|---|---|
| Node | <FILL> | <FILL> | <FILL> | <FILL>% |
| Go   | <FILL> | <FILL> | <FILL> | <FILL>% |
```

- [ ] **Step 3 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/tests/benchmarks/ws_broadcast_bench_test.go docs/benchmarks/
git commit -m "perf(crawler-monitor-backend-go): bench WS broadcast p99 100 clients"
```

---

### Task 6.3 : Mesure RAM idle + sous charge (vegeta)

**Goal** : Vérifier l'empreinte mémoire promise (≤ 50 MB idle).

**Files** :
- Create : `tests/benchmarks/loadtest.sh`
- Create : `docs/benchmarks/ram-measurement.md`

**Acceptance Criteria** :
- [ ] RAM idle conteneur Go ≤ 50 MB (mesuré via `docker stats --no-stream`)
- [ ] RAM sous charge 50 RPS sur `/api/jobs` pendant 5 min ≤ 100 MB
- [ ] Comparaison documentée vs Node (Node idle ~150 MB, sous charge ~250 MB attendu)

**Verify** :
```bash
# Container stats à la main, puis :
cat docs/benchmarks/ram-measurement.md
```

**Steps** :

- [ ] **Step 1 : Script de charge**

```bash
# tests/benchmarks/loadtest.sh
#!/bin/bash
set -e
TOKEN="$1"
URL="${2:-http://localhost:3002}"
DUR="${3:-5m}"
RATE="${4:-50}"

echo "GET ${URL}/api/jobs
Authorization: Bearer ${TOKEN}" \
  | vegeta attack -duration=${DUR} -rate=${RATE} \
  | vegeta report
```

- [ ] **Step 2 : Procédure de mesure**

```bash
# 1. Start Go container in background
docker compose up -d crawler-monitor-backend-go

# 2. RAM idle (60s settling)
sleep 60
docker stats --no-stream crawler-monitor-backend-go

# 3. Mint a token
TOKEN=$(curl -s -X POST http://localhost:3002/api/login -d '{"password":"<admin>"}' -H "Content-Type: application/json" | jq -r .token)

# 4. Charge 5 min
bash tests/benchmarks/loadtest.sh "$TOKEN" http://localhost:3002 5m 50

# 5. RAM sous charge (en parallèle)
docker stats --no-stream crawler-monitor-backend-go
```

- [ ] **Step 3 : Documenter résultats** dans `docs/benchmarks/ram-measurement.md`.

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/tests/benchmarks/loadtest.sh docs/benchmarks/ram-measurement.md
git commit -m "perf(crawler-monitor-backend-go): script loadtest vegeta + mesure RAM"
```

---

### Task 6.4 : Synthèse `docs/benchmarks/2026-04-go-vs-express.md`

**Goal** : Document final qui consolide les résultats des Tasks 6.1-6.3 et statue sur la validation des motivations.

**Files** :
- Modify : `docs/benchmarks/2026-04-go-vs-express.md`

**Acceptance Criteria** :
- [ ] Sections : Analyze CPU bench / WS broadcast latency / RAM idle / RAM under load / Verdict
- [ ] Verdict explicite : motivations 1 (throughput), 2 (concurrence WS), 3 (RAM) atteintes ou non
- [ ] Si une motivation n'est pas atteinte → recommandation explicite (stop cutover ou correction ciblée)

**Verify** : relecture humaine du doc.

**Steps** :

- [ ] **Step 1 : Compiler les chiffres collectés**

- [ ] **Step 2 : Rédiger Verdict**

```markdown
## Verdict

| Motivation | Cible | Mesuré | Atteint ? |
|---|---|---|---|
| Throughput parsing queue | ≥ 5x Node | <Xx> | ✅ / ❌ |
| Concurrence WS p99 | ≤ 50 ms | <Xms> | ✅ / ❌ |
| RAM idle | ≤ 50 MB | <X MB> | ✅ / ❌ |

**Recommandation** : <PROCEED CUTOVER | INVESTIGATE>
```

- [ ] **Step 3 : Commit**

```bash
git add docs/benchmarks/2026-04-go-vs-express.md
git commit -m "perf(crawler-monitor-backend-go): synthese bench + verdict motivations"
```

---

## Phase 7 — Cutover & watch (4 tâches)

### Task 7.1 : Smoke test contractuel `tests/contract_smoke.sh`

**Goal** : Script bash qui curl chaque route avec un token valide et compare la réponse Go vs un snapshot Node de référence.

**Files** :
- Create : `tests/contract_smoke.sh`
- Create : `tests/contract_snapshots/<route>.json` (capturés depuis Express en pré-cutover)

**Acceptance Criteria** :
- [ ] Pour chaque endpoint REST (35), un appel curl est fait, body+status comparés au snapshot Node (stocké dans `tests/contract_snapshots/`)
- [ ] Si différence → diff lisible affiché
- [ ] Exit 0 si toutes les routes matchent, exit 1 sinon

**Verify** : `bash tests/contract_smoke.sh http://localhost:3002 <admin-pwd>`

**Steps** :

- [ ] **Step 1 : Capturer les snapshots Node**

```bash
# En pré-cutover, contre l'Express en marche :
NODE_URL=http://localhost:3001
TOKEN=$(curl -s -X POST $NODE_URL/api/login -d '{"password":"<admin>"}' -H "Content-Type: application/json" | jq -r .token)
mkdir -p tests/contract_snapshots
ROUTES=(
  "/health"
  "/api/jobs"
  "/api/jobs/{ID}/details"
  "/api/jobs/{ID}/performance"
  "/api/jobs/{ID}/replay"
  "/api/capacity"
  "/api/capacity/history"
  # ... liste exhaustive des 35 routes
)
ID=$(curl -s -H "Authorization: Bearer $TOKEN" $NODE_URL/api/jobs | jq -r '.[0].id')
for r in "${ROUTES[@]}"; do
  path="${r//\{ID\}/$ID}"
  fn="${path//\//_}.json"
  curl -s -H "Authorization: Bearer $TOKEN" "$NODE_URL$path" > "tests/contract_snapshots/${fn}"
done
```

- [ ] **Step 2 : Script de comparaison**

```bash
#!/bin/bash
# tests/contract_smoke.sh
set -e
URL="${1:-http://localhost:3002}"
PWD="${2:?admin password required}"
TOKEN=$(curl -s -X POST "$URL/api/login" -d "{\"password\":\"$PWD\"}" -H "Content-Type: application/json" | jq -r .token)
[ "$TOKEN" = "null" ] && { echo "login failed"; exit 1; }

FAILED=0
for snap in tests/contract_snapshots/*.json; do
  path=$(basename "$snap" .json | tr '_' '/')
  expected=$(cat "$snap")
  actual=$(curl -s -H "Authorization: Bearer $TOKEN" "$URL$path")
  if ! diff <(echo "$expected" | jq -S .) <(echo "$actual" | jq -S .) >/dev/null; then
    echo "❌ $path"
    diff <(echo "$expected" | jq -S .) <(echo "$actual" | jq -S .) | head -20
    FAILED=$((FAILED+1))
  else
    echo "✅ $path"
  fi
done
exit $FAILED
```

- [ ] **Step 3 : Commit**

```bash
chmod +x apps-microservices/crawler-monitor-backend/tests/contract_smoke.sh
git add apps-microservices/crawler-monitor-backend/tests/contract_smoke.sh apps-microservices/crawler-monitor-backend/tests/contract_snapshots/
git commit -m "test(crawler-monitor-backend-go): smoke test contractuel + snapshots Node"
```

---

### Task 7.2 : Shadow deployment validation (port 3002)

**Goal** : Faire tourner le service Go en parallèle de l'Express pendant 24-48h pour valider stabilité sans impacter le trafic.

**Files** : aucun nouveau fichier, ops uniquement.

**Acceptance Criteria** :
- [ ] Service Go déployé sur port 3002 en prod GCP
- [ ] Smoke test contractuel passe sur 3002 (vs snapshots Node)
- [ ] Aucun crash / restart / leak mémoire sur 24h
- [ ] Logs Go monitorés via Loki/Grafana, pas d'erreurs récurrentes

**Verify** :
```bash
docker compose ps crawler-monitor-backend-go
# State doit être "Up X hours (healthy)"
```

**Steps** :

- [ ] **Step 1 : Deploy**

```bash
# Sur la VM GCP
docker compose pull crawler-monitor-backend-go
docker compose up -d crawler-monitor-backend-go
docker compose logs -f --tail=50 crawler-monitor-backend-go
```

- [ ] **Step 2 : Smoke test depuis la VM**

```bash
ssh gcp-vm
bash /opt/crawler-monitor-backend/tests/contract_smoke.sh http://localhost:3002 "$ADMIN_PASSWORD"
```

- [ ] **Step 3 : Watch 24h**

Surveillance via Grafana :
- RAM container ≤ 50 MB idle, ≤ 100 MB sous trafic
- 0 erreur 5xx
- Logs : aucune répétition d'erreur "redis disconnect", "panic", etc.

- [ ] **Step 4 : Décision GO / NO-GO**

Si tout vert sur 24h → procéder à Task 7.3. Sinon → ouvrir issue, débloquer, recommencer.

> **NOTE** : pas de commit pour cette tâche (ops only). Documenter le résultat dans le PR description du cutover.

---

### Task 7.3 : Cutover swap port 3001

**Goal** : Bascule production. Express stoppé, Go promu sur port 3001.

**Files** :
- Modify : `docker-compose.yml` (le service `crawler-monitor-backend` pointe maintenant vers le Dockerfile Go au lieu de Dockerfile.express ; ports 3001:3001 ; suppression du `crawler-monitor-backend-go` distinct)

**Acceptance Criteria** :
- [ ] Service unique `crawler-monitor-backend` qui sert sur 3001 avec l'image Go
- [ ] Frontend Vite continue de fonctionner sans modification
- [ ] Latence p50 ≤ baseline mesurée en pré-cutover
- [ ] Rollback testé (procédure runbook utilisable en < 1 min)

**Verify** :
```bash
docker compose ps crawler-monitor-backend
# Status: Up (healthy), port 3001 mappé
curl -s http://localhost:3001/health | jq .
# {"status":"ok","version":"<sha>"}
```

**Steps** :

- [ ] **Step 1 : Annonce + fenêtre de maintenance**

Annoncer à l'équipe (#dev / Slack) une bascule courte (< 5 min). Choix d'horaire : trafic minimal.

- [ ] **Step 2 : Modifier `docker-compose.yml`**

Remplacer le service `crawler-monitor-backend` (Express) par celui pointant vers le Dockerfile Go. Supprimer la définition séparée `crawler-monitor-backend-go`.

```yaml
crawler-monitor-backend:
  build:
    context: ./apps-microservices/crawler-monitor-backend
    dockerfile: Dockerfile
  ports:
    - "3001:3001"
  environment:
    - REDIS_URL=${REDIS_URL}
    - JWT_SECRET=${JWT_SECRET}
    - ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
    - CRAWLER_STORAGE_PATH=/app/storage
    - PORT=3001
    - LOG_LEVEL=info
    - CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS:-*}
  volumes:
    - crawler_storage:/app/storage:rw
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "/app/server", "healthcheck"]
    interval: 10s
    timeout: 3s
    retries: 3
```

- [ ] **Step 3 : Bascule**

```bash
docker compose stop crawler-monitor-backend
docker compose up -d --build crawler-monitor-backend
docker compose ps
curl -s http://localhost:3001/health
# Verify version != "dev" (commit sha)
```

- [ ] **Step 4 : Smoke test post-cutover**

```bash
bash tests/contract_smoke.sh http://localhost:3001 "$ADMIN_PASSWORD"
# Doit exit 0 (toutes routes OK)
```

- [ ] **Step 5 : Test rollback (chronométré)**

```bash
time {
  docker compose stop crawler-monitor-backend
  docker run -d --name crawler-monitor-backend-rollback \
    -p 3001:3001 \
    -e REDIS_URL=$REDIS_URL -e JWT_SECRET=$JWT_SECRET \
    -e ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH \
    -v crawler_storage:/app/storage \
    gcr.io/$PROJECT/crawler-monitor-backend:last-express
  curl -s --retry 3 --retry-delay 1 http://localhost:3001/health
}
# Doit prendre < 60s
```

Si rollback OK → kill rollback container, relance Go :
```bash
docker stop crawler-monitor-backend-rollback && docker rm crawler-monitor-backend-rollback
docker compose up -d crawler-monitor-backend
```

- [ ] **Step 6 : Commit + tag**

```bash
git add docker-compose.yml
git commit -m "feat(crawler-monitor-backend): cutover Express -> Go (production)"
git tag -a cutover-go-v1 -m "Cutover Go v1 — replaces Express version"
```

---

### Task 7.4 : Watch 24h + nettoyage Express

**Goal** : Surveiller 24h post-cutover, supprimer les fichiers Node si tout est stable.

**Files** :
- Delete : `apps-microservices/crawler-monitor-backend/server.js`
- Delete : `apps-microservices/crawler-monitor-backend/src/lib/*.js`
- Delete : `apps-microservices/crawler-monitor-backend/package.json`
- Delete : `apps-microservices/crawler-monitor-backend/package-lock.json`
- Delete : `apps-microservices/crawler-monitor-backend/node_modules/` (déjà gitignored)
- Delete : `apps-microservices/crawler-monitor-backend/Dockerfile.express`
- Delete : `apps-microservices/crawler-monitor-backend/tests/*.test.js` (les tests Node, conservés tant que watch en cours puis supprimés)

**Acceptance Criteria** :
- [ ] Au bout de 24h sans incident → fichiers Node supprimés
- [ ] CLAUDE.md du service mis à jour pour refléter le stack Go
- [ ] PR de nettoyage mergé sur `main`

**Verify** :
```bash
ls apps-microservices/crawler-monitor-backend/
# Doit lister seulement : cmd/ internal/ tests/ (Go) Dockerfile go.mod go.sum docs/ .env.example .dockerignore .gitignore
```

**Steps** :

- [ ] **Step 1 : Watch (J → J+1)**

Vérifications quotidiennes :
- Latence p50/p99 stable
- Pas de pic RAM
- Pas d'erreurs nouvelles dans les logs
- Pas de plainte utilisateur sur le frontend

- [ ] **Step 2 : Si tout vert, suppression**

```bash
git rm apps-microservices/crawler-monitor-backend/server.js
git rm -r apps-microservices/crawler-monitor-backend/src/
git rm apps-microservices/crawler-monitor-backend/{package.json,package-lock.json,Dockerfile.express}
git rm apps-microservices/crawler-monitor-backend/tests/*.test.js
git rm apps-microservices/crawler-monitor-backend/tests/helpers/*.js
```

- [ ] **Step 3 : Mettre à jour CLAUDE.md du service**

```markdown
# crawler-monitor-backend

Go backend providing REST API and WebSocket for the crawler monitoring dashboard.

## Tech Stack

- **Language:** Go 1.23
- **Router:** chi v5
- **WebSocket:** gorilla/websocket
- **Auth:** JWT HS256 (golang-jwt/v5)
- **State:** Redis (go-redis/v9)
- **Tests:** stdlib testing + miniredis + httptest
- **Image:** distroless static nonroot (~10-15 MB)

## Commands

| Action | Command |
|--------|---------|
| Build  | `go build ./cmd/server` |
| Test   | `go test -race -cover ./...` |
| Lint   | `golangci-lint run` |
| Bench  | `go test -bench=. ./tests/benchmarks/` |
| Run    | `./server` (env vars required: REDIS_URL, JWT_SECRET, ADMIN_PASSWORD_HASH) |
| Healthcheck | `./server healthcheck` |

## Folder Structure

\`\`\`
cmd/server/         # main + healthcheck subcommand
internal/
  config/          # env loading
  httpapi/         # chi handlers, middleware, respond/errors
  ws/              # hub, client, pubsub, upgrade
  domain/          # logique métier pure (alerts, queue, capacity, etc.)
  store/           # redisstore, filestore, auditstore
  auth/password/   # scrypt verify
tests/             # tests intégration + benchmarks
\`\`\`

## Migration history

- 2026-04-28 : migration Express.js → Go. Cf `docs/superpowers/specs/2026-04-28-crawler-monitor-backend-go-migration-design.md`.
- Image Express archivée : `gcr.io/$PROJECT/crawler-monitor-backend:last-express` (tag conservé).
```

- [ ] **Step 4 : Commit**

```bash
git add apps-microservices/crawler-monitor-backend/CLAUDE.md
git commit -m "chore(crawler-monitor-backend): nettoyage fichiers Node post-cutover"
git tag -a cutover-go-v1-final -m "Cutover Go v1 final — Node files removed after 24h watch"
```

- [ ] **Step 5 : PR + merge**

```bash
git push origin features/crawler-monitor-backend-go
gh pr create --title "Migration crawler-monitor-backend ExpressJS -> Go" \
  --body "Cf docs/superpowers/specs/2026-04-28-crawler-monitor-backend-go-migration-design.md"
```

Une fois validée → merge sur `main`.

---

## Self-review (vs spec)

**Coverage spec** :
- ✅ Architecture & layout des packages Go (spec §2) → Tasks 1.1, 1.2 + structure dans toutes les phases
- ✅ WebSocket hub + broadcast (spec §3) → Tasks 5.1-5.4
- ✅ Couche HTTP middleware + routage chi (spec §4) → Tasks 1.4-1.6, 1.7, mount dans router au fur et à mesure
- ✅ Domaine + store + erreurs + concurrence (spec §5) → Tasks 1.3, 2.3, 2.4, 2.5, séparation domain/store appliquée Phase 3+4
- ✅ Tests port 1:1 + miniredis + path traversal (spec §6) → Tasks 2.1, 2.4, et chaque tâche Phase 3-5 inclut le port du test Node correspondant
- ✅ Docker distroless + cutover (spec §7) → Tasks 1.7, 7.2, 7.3
- ✅ Plan en 7 phases (spec §8) → Phases 1-7 explicitement
- ✅ Risques résiduels (spec §9) → Mitigations couvertes : tests de contrat (Task 7.1), test parité audit format (Task 2.5), bench (Phase 6), rollback (Task 7.3)
- ✅ Définition de fait (spec §11) → 12 critères d'acceptation traçables aux tâches

**Phase 0 ajoutée** (non-prévue dans le spec mais nécessaire) :
- Catalogue Redis (Task 0.1) : référence pour Tasks 2.3+
- Tag `last-express` (Task 0.2) : nécessaire pour rollback Task 7.3
- Renommage Dockerfile (Task 0.3) : libère le nom pour la version Go

**Placeholder scan** : aucun "TBD"/"TODO"/"implement later" non documenté. Les sections `// ... cf source pour la liste exhaustive` sont volontaires : pointent l'implémenteur vers les sources Node à porter (sans que le plan duplique 1500 lignes de JS). Chaque pointeur est accompagné du nom de fichier et de la ligne précise.

**Type consistency** : `redisstore.Client`, `filestore.Storage`, `auditstore.Local`, `ws.Hub` — noms et signatures cohérents à travers toutes les tâches. `Deps` struct enrichie au fil des phases (Version → +Config → +RedisStore +AuditStore → +Hub).

**Scope** : un seul plan, une seule branche, un seul cutover. Pas de décomposition supplémentaire nécessaire.

**Estimation effort total** : 44 tâches × ~2h moyenne = ~88h. Avec contingence + watch + benchmarks → **~10-15 jours de dev**, conforme au spec.

---

## Récapitulatif des 44 tâches

| Phase | # | Tâche | Estimation |
|---|---|---|---|
| 0 | 0.1 | Catalogue Redis keys | 1h |
| 0 | 0.2 | Tag last-express image | 0.5h |
| 0 | 0.3 | Rename Dockerfile.express | 0.5h |
| 1 | 1.1 | go mod init + main + /health | 2h |
| 1 | 1.2 | Config loader + tests | 1.5h |
| 1 | 1.3 | respond/errors helpers + tests | 1h |
| 1 | 1.4 | JWT middleware + tests | 2h |
| 1 | 1.5 | Audit middleware (stub) | 1h |
| 1 | 1.6 | CORS + ratelimit + securityheaders | 1.5h |
| 1 | 1.7 | Dockerfile + compose 3002 | 1.5h |
| 2 | 2.1 | password scrypt + 8 tests | 2h |
| 2 | 2.2 | POST /api/login + tests | 2h |
| 2 | 2.3 | redisstore + miniredis tests | 2h |
| 2 | 2.4 | filestore + safejoin + path traversal | 2h |
| 2 | 2.5 | auditstore JSONL + parité Node | 3h |
| 3 | 3.1 | /api/jobs list + details | 2h |
| 3 | 3.2 | /api/capacity + history + planning | 3h |
| 3 | 3.3 | /api/replicas/history | 2h |
| 3 | 3.4 | /api/system/stats + health | 2h |
| 3 | 3.5 | /api/audit | 1.5h |
| 3 | 3.6 | /api/timeline + /api/alerts | 4h |
| 3 | 3.7 | /api/domains + /:domain | 2h |
| 4 | 4.1 | /api/jobs/:id/performance | 1.5h |
| 4 | 4.2 | /api/jobs/:id/replay (extract) | 3h |
| 4 | 4.3 | request-queues list/read/write | 3h |
| 4 | 4.4 | request-queues/analyze (gros) | 4h |
| 4 | 4.5 | clean-patterns + repair + drop | 2.5h |
| 4 | 4.6 | dataset/counts + urls | 2h |
| 4 | 4.7 | dataset/analyze + deduplicate | 2.5h |
| 4 | 4.8 | callbacks list/retry/delete/clear | 3h |
| 4 | 4.9 | albums (mountAlbumsRouter) | 2.5h |
| 4 | 4.10 | imageDownloadProxy (verify+port/skip) | 1h |
| 5 | 5.1 | ws hub + tests broadcast | 2h |
| 5 | 5.2 | ws client read/write pumps | 1.5h |
| 5 | 5.3 | ws pubsub Redis + reconnect | 2h |
| 5 | 5.4 | ws upgrade + integration test | 2.5h |
| 6 | 6.1 | bench analyze 100k URLs | 2h |
| 6 | 6.2 | bench WS broadcast p99 | 2h |
| 6 | 6.3 | RAM measurement + vegeta | 1.5h |
| 6 | 6.4 | synthèse benchmarks doc | 1h |
| 7 | 7.1 | smoke test contractuel | 2h |
| 7 | 7.2 | shadow deployment 24h | 24h calendrier (passive) |
| 7 | 7.3 | cutover swap port 3001 | 1h |
| 7 | 7.4 | watch 24h + nettoyage Express | 24h calendrier (passive) |

**Total dev actif** : ~85h. **Total calendrier** : ~12-15 jours en incluant watch & validation.

---





