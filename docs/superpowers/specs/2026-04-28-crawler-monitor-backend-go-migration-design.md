# Migration `crawler-monitor-backend` ExpressJS → Go (Golang)

**Date** : 2026-04-28
**Statut** : Design validé section par section, en attente de relecture finale
**Repo** : `Hellopro-fr/RAG-HP-PUB`
**Service** : `apps-microservices/crawler-monitor-backend/`

---

## 1. Contexte & motivation

### 1.1 Service actuel

Le service `crawler-monitor-backend` est l'API + WebSocket consommé par `crawler-monitor-frontend` (Vite SPA) pour piloter et observer le crawler de la plateforme HelloPro.

État au 2026-04-28 :

| Aspect | Valeur |
|---|---|
| Stack | Express 4 ESM + Node 20 |
| Port | 3001 |
| Code total | ~3 300 lignes (`server.js` 1 813 lignes + 13 modules `src/lib/*.js` ~1 490 lignes) |
| Routes REST | ~35 (catalogue exhaustif, voir §6.1) |
| WebSocket | montage sur `/`, auth via `?token=`, pub/sub Redis `crawl_updates` et `crawler:heartbeat` |
| Dépendances externes | **Redis seul** (pas de DB SQL) + filesystem `CRAWLER_STORAGE_PATH` |
| Sécurité | JWT HS256, helmet, express-rate-limit (100 req / 15 min / IP), CORS |
| Tests | 17 fichiers `node:test` + supertest + helpers fixture |
| Image Docker | `node:20-alpine`, ~180 MB |

### 1.2 Motivations de la migration (validées avec l'équipe)

1. **Throughput REST + parsing fichiers queue** — endpoints `/request-queues/analyze` et `/dataset/analyze` parcourent de gros fichiers JSON sur disque ; Go offre un gain CPU/IO sync substantiel vs Node.
2. **Concurrence WebSocket / pub/sub Redis** — broadcast vers de nombreux clients simultanés saturé par l'event loop Node ; les goroutines + channels Go parallélisent naturellement.
3. **Empreinte mémoire / coût VM GCP** — Node ~150 MB idle, Go ~20-30 MB attendus.

### 1.3 Décisions structurantes (validées)

| Question | Décision |
|---|---|
| Stratégie de migration | **Big-bang rewrite** (service petit, surface limitée) |
| Framework HTTP Go | **net/http stdlib + `github.com/go-chi/chi/v5`** (idiomatique, zéro magie, écosystème stdlib-compatible) |
| Compatibilité API | **Iso strict** — mêmes URLs, payloads JSON, codes HTTP, messages d'erreur que l'Express. Aucun changement côté frontend Vite |
| Stratégie de tests | **Port 1:1 des 17 tests Node** vers Go (`testing` stdlib + `httptest` + miniredis) |
| Continuité JWT | `JWT_SECRET` identique entre Express et Go, même algo HS256 → tokens existants restent valides |

---

## 2. Architecture & layout des packages Go

```
crawler-monitor-backend/
├── cmd/server/main.go           # entrypoint, wiring, graceful shutdown, sous-commande healthcheck
├── internal/
│   ├── config/                  # chargement env (REDIS_URL, JWT_SECRET, etc.)
│   ├── httpapi/                 # handlers HTTP (1 fichier par groupe d'endpoints)
│   │   ├── router.go            # mount chi routes (mirroir 1:1 d'Express)
│   │   ├── middleware/          # jwt, audit, ratelimit, cors, securityheaders
│   │   ├── jobs.go              # /api/jobs, /api/jobs/:id/details, performance, replay
│   │   ├── queues.go            # /api/jobs/:id/request-queues/*
│   │   ├── dataset.go           # /api/jobs/:id/dataset/*
│   │   ├── capacity.go          # /api/capacity, /api/capacity/history, /api/capacity-planning/*
│   │   ├── alerts.go            # /api/alerts
│   │   ├── domains.go           # /api/domains, /api/domains/:domain
│   │   ├── timeline.go          # /api/timeline
│   │   ├── replicas.go          # /api/replicas/history, /api/replicas/:id/history
│   │   ├── callbacks.go         # /api/callbacks/*
│   │   ├── system.go            # /api/system/stats, /api/system/health
│   │   ├── audit.go             # /api/audit
│   │   ├── albums.go            # /api/albums (mirror de mountAlbumsRouter)
│   │   ├── imageproxy.go        # imageDownloadProxy
│   │   ├── auth.go              # /api/login + verifyPassword
│   │   ├── health.go            # /health
│   │   ├── respond.go           # WriteJSON / WriteError / DecodeJSON
│   │   └── errors.go            # HTTPError + sentinels
│   ├── ws/                      # WebSocket hub
│   │   ├── hub.go               # client registry + broadcast
│   │   ├── client.go            # 1 connexion = 1 readPump + 1 writePump
│   │   └── pubsub.go            # subscribe Redis + reconnexion
│   ├── domain/                  # logique métier pure (aucune dép HTTP / Redis / FS)
│   │   ├── alerts/              # port de src/lib/alerts.js
│   │   ├── capacityplanning/    # port de capacityPlanning.js
│   │   ├── capacityhistory/     # port de capacityHistory.js
│   │   ├── domains/             # port de domains.js
│   │   ├── timeline/            # port de timeline.js
│   │   ├── systemstats/         # port de systemStats.js
│   │   ├── jobperf/             # port de jobPerformance.js
│   │   ├── replicahistory/      # port de replicaHistory.js
│   │   └── queue/               # parsing queue files, dedup dataset, repair, drop
│   ├── store/
│   │   ├── redisstore/          # client go-redis/v9 + clés crawler
│   │   ├── filestore/           # CRAWLER_STORAGE_PATH (lecture/écriture queue files) + safeJoin
│   │   └── auditstore/          # rotation logs + lecture audit (compatible JSONL Node)
│   └── auth/                    # password (scrypt verify), jwt sign/verify
├── go.mod / go.sum
├── Dockerfile                   # multi-stage builder (golang:1.23 → distroless static nonroot)
├── .env.example
└── tests/                       # tests d'intégration httptest (port 1:1 des Node)
    ├── albums_test.go, alerts_test.go, ... (17 fichiers)
    ├── helpers/                 # fixtures + miniredis + tmpdir storage
    └── fixtures/                # données factices versionnées
```

### Mapping Node → Go (modules)

| Node `src/lib/*.js` | Go package |
|---|---|
| `alerts.js` | `internal/domain/alerts` |
| `auditLog.js` | `internal/store/auditstore` + `internal/httpapi/middleware/audit` |
| `albums.js` | `internal/httpapi/albums.go` |
| `callbacks.js` | `internal/httpapi/callbacks.go` |
| `capacityHistory.js` | `internal/domain/capacityhistory` |
| `capacityPlanning.js` | `internal/domain/capacityplanning` |
| `domains.js` | `internal/domain/domains` |
| `imageDownloadProxy.js` | `internal/httpapi/imageproxy.go` |
| `jobPerformance.js` | `internal/domain/jobperf` |
| `password.js` | `internal/auth/password` |
| `replicaHistory.js` | `internal/domain/replicahistory` |
| `systemStats.js` | `internal/domain/systemstats` |
| `timeline.js` | `internal/domain/timeline` |

### Principes de conception

- `internal/` partout → empêche tout autre microservice du monorepo `RAG-HP-PUB` d'importer accidentellement nos handlers.
- `domain/` séparé du HTTP → logique métier testable sans serveur.
- `store/` regroupe les sources de données (Redis, filesystem, audit log) — interface définie côté domaine, implémentation côté infra.
- `httpapi/` regroupe **un fichier par bloc fonctionnel** d'Express (pas un par endpoint) — reflète la mental map de `server.js`.
- `cmd/server/main.go` minimal (~80 lignes) : load config → build stores → build hub → wire chi router → démarre HTTP+WS → graceful shutdown via `signal.NotifyContext`.

---

## 3. WebSocket — hub & broadcast

### 3.1 Architecture

```
                       ┌─────────────────────────────┐
   Redis pub/sub ─────►│ pubsub.go                   │
   (crawl_updates,     │  - subscribe + reconnect    │
    crawler:heartbeat) │  - 1 goroutine par channel  │
                       └─────────────┬───────────────┘
                                     │ envoie msg
                                     ▼
                       ┌─────────────────────────────┐
                       │ hub.go                      │
                       │  - register/unregister chan │
                       │  - broadcast chan []byte    │
                       │  - clients map[*Client]bool │
                       │    (protégé par RWMutex)    │
                       └─────────┬───────────────────┘
                                 │ fan-out
                                 ▼
                       ┌──────────────┬──────────────┐
                       │ Client #1    │ Client #N    │
                       │ - readPump   │ - readPump   │  (1 read + 1 write goroutine
                       │ - writePump  │ - writePump  │   par connexion)
                       │ - send chan  │ - send chan  │
                       └──────────────┴──────────────┘
```

### 3.2 Décisions

- **Lib WebSocket** : `github.com/gorilla/websocket` (référence écosystème, ping/pong natif, robuste sous charge).
- **Auth** : conservation de `?token=...` en query string. Validation JWT **avant** `Upgrader.Upgrade()`. Si KO → 401 sans upgrade.
- **Backpressure** : chaque `Client` a un `send chan []byte` bufferisé taille 256. Si plein → fermeture de la connexion (sémantique « lent client = on dégage », équivalente à `ws.send` Node).
- **Reconnect Redis** : boucle avec backoff exponentiel (1s → 30s max). Si Redis tombe, le hub continue de servir les clients connectés et reprend l'abonnement quand Redis revient.
- **Heartbeat** : ping toutes les 30s (`pongWait = 60s`) pour détecter les clients fantômes.
- **Format de message** : relais JSON brut publié sur Redis tel quel (pas de re-marshal). Iso avec Express qui fait `ws.send(JSON.stringify(msg))`.
- **Recover panic** : la goroutine `pubsub` recover les panics, log, drop le message, continue.

### 3.3 Cibles de performance

- 100 clients connectés × 50 publications/s = 5 000 sends/s parallélisés (vs séquentiel sur l'event loop Node).
- RAM par client : ~6-8 KB (goroutine stack + buffer chan). 1 000 clients ≈ 8 MB.

---

## 4. Couche HTTP — middleware & routage

### 4.1 Pile de middleware (mapping)

| Express | Go |
|---|---|
| `helmet()` | middleware maison `securityheaders` (X-Content-Type-Options, X-Frame-Options DENY, Strict-Transport-Security, Referrer-Policy) — ~30 lignes |
| `cors({ origin })` | `github.com/go-chi/cors` |
| `express.json({ limit: '50mb' })` | `http.MaxBytesReader` à 50 MB + `json.Decoder` côté handler |
| `express-rate-limit` (100/15min/IP) | `github.com/go-chi/httprate` (token-bucket Redis-backed envisageable post-cutover si besoin multi-replica) |
| `auditMiddleware` | middleware maison qui wrappe `ResponseWriter` pour capturer status + écrit JSONL via `auditstore` |
| `authenticateToken` JWT | middleware `jwt` parse `Authorization: Bearer ...`, valide HS256 avec `JWT_SECRET`, injecte claims dans `r.Context()`. Lib : `github.com/golang-jwt/jwt/v5` |

### 4.2 Routage chi (mirror exact d'Express)

```go
r := chi.NewRouter()
r.Use(securityheaders.Handler)
r.Use(cors.Handler(corsCfg))
r.Use(httprate.LimitByIP(100, 15*time.Minute))
r.Use(audit.Middleware(auditStore))

r.Get("/health", health.Get)
r.Post("/api/login", auth.Login)

r.Group(func(r chi.Router) {
    r.Use(jwtmw.Verify(jwtSecret))

    r.Route("/api/jobs", func(r chi.Router) {
        r.Get("/", jobs.List)
        r.Get("/{id}/details", jobs.Details)
        r.Get("/{id}/performance", jobs.Performance)
        r.Get("/{id}/replay", jobs.Replay)
        r.Route("/{id}/request-queues", func(r chi.Router) {
            r.Get("/", queues.List)
            r.Get("/analyze", queues.Analyze)
            r.Post("/clean-patterns", queues.CleanPatterns)
            r.Post("/repair", queues.Repair)
            r.Post("/drop", queues.Drop)
            r.Get("/{domain}/{filename}", queues.ReadFile)
            r.Post("/{domain}/{filename}", queues.WriteFile)
        })
        r.Route("/{id}/dataset", func(r chi.Router) {
            r.Get("/counts", dataset.Counts)
            r.Get("/urls", dataset.URLs)
            r.Get("/analyze", dataset.Analyze)
            r.Post("/deduplicate", dataset.Deduplicate)
        })
    })
    r.Route("/api/albums", albums.Mount)
    r.Get("/api/capacity", capacity.Get)
    r.Get("/api/capacity/history", capacity.History)
    r.Get("/api/capacity-planning/ram", capacity.PlanningRAM)
    r.Get("/api/alerts", alerts.Get)
    r.Get("/api/domains", domains.List)
    r.Get("/api/domains/{domain}", domains.Get)
    r.Get("/api/timeline", timeline.Get)
    r.Get("/api/replicas/history", replicas.History)
    r.Get("/api/replicas/{id}/history", replicas.HistoryByID)
    r.Get("/api/callbacks", callbacks.List)
    r.Post("/api/callbacks/{idx}/retry", callbacks.Retry)
    r.Delete("/api/callbacks/{idx}", callbacks.Delete)
    r.Post("/api/callbacks/clear", callbacks.Clear)
    r.Get("/api/system/stats", system.Stats)
    r.Get("/api/system/health", system.Health)
    r.Get("/api/audit", audit.List)
})

r.Get("/", ws.HandleUpgrade(hub, jwtSecret))
```

### 4.3 Iso strict — points de vigilance

| Détail Express | Reproduction Go |
|---|---|
| Format d'erreur `{ "error": "msg" }` | helper `respond.WriteError(w, status, msg)` |
| Codes HTTP exacts (401/403/404/409/422/500) | grep préalable de `server.js` → constantes Go |
| Casing JSON (camelCase majoritaire) | tags struct `json:"someField"` — vérification endpoint par endpoint |
| Pagination `{ items, total, page, pageSize }` | structures génériques `PageResponse[T any]` |
| Body limit 50 MB (request_urls) | `http.MaxBytesReader(w, r.Body, 50<<20)` côté handlers `request-queues` |
| `Content-Type: application/json; charset=utf-8` | helper `respond.WriteJSON` standardisé |

**Endpoints sensibles à porter avec soin** :
- `/api/jobs/:id/replay` (server.js:329→462, ~130 lignes)
- `/api/jobs/:id/request-queues/analyze` (server.js:868→1064, ~196 lignes)

Ces deux endpoints contiennent la majorité de la logique métier inline et doivent être refactorisés dans `internal/domain/queue/`.

---

## 5. Domaine, accès données & gestion d'erreurs

### 5.1 Séparation domaine / store

Le code dans `internal/domain/*` ne connaît **ni** chi **ni** Redis **ni** le filesystem. I/O via interfaces définies dans `internal/store/*`.

```go
// internal/domain/alerts/alerts.go
package alerts

type Job struct {
    ID          string
    Status      string
    QueueDepth  int
    HeartbeatAt time.Time
}

type Threshold struct { /* ... */ }

type Alert struct {
    Severity string `json:"severity"`
    Code     string `json:"code"`
    Message  string `json:"message"`
    JobID    string `json:"jobId,omitempty"`
}

func Evaluate(jobs []Job, t Threshold, now time.Time) []Alert { /* ... */ }
```

Le handler `httpapi/alerts.go` lit les jobs depuis `redisstore`, construit `[]alerts.Job`, appelle `alerts.Evaluate(...)`, écrit la réponse JSON.

### 5.2 Interfaces store

```go
// internal/store/store.go
type JobStore interface {
    ListAll(ctx context.Context) ([]RawJob, error)
    GetByID(ctx context.Context, id string) (RawJob, error)
    GetCallbacks(ctx context.Context) ([]Callback, error)
}

type QueueFileStore interface {
    ListDomains(ctx context.Context, jobID string) ([]string, error)
    ListFiles(ctx context.Context, jobID, domain string) ([]FileInfo, error)
    Read(ctx context.Context, jobID, domain, filename string) ([]byte, error)
    Write(ctx context.Context, jobID, domain, filename string, data []byte) error
    Delete(ctx context.Context, jobID, domain, filename string) error
}

type AuditStore interface {
    Append(ctx context.Context, entry AuditEntry) error
    Read(ctx context.Context, filter AuditFilter) ([]AuditEntry, error)
    RotateOld(ctx context.Context) error
}
```

### 5.3 Sécurité path traversal

```go
func safeJoin(base string, parts ...string) (string, error) {
    p := filepath.Clean(filepath.Join(append([]string{base}, parts...)...))
    if !strings.HasPrefix(p, filepath.Clean(base)+string(os.PathSeparator)) {
        return "", ErrPathEscape
    }
    return p, nil
}
```

Tous les handlers `request-queues/{domain}/{filename}` passent par `safeJoin` avant **toute** opération filesystem. Aucune exception.

### 5.4 Gestion d'erreurs

```go
// internal/httpapi/errors.go
type HTTPError struct {
    Status int
    Code   string
    Msg    string
}

func (e *HTTPError) Error() string { return e.Msg }

var (
    ErrNotFound      = &HTTPError{Status: 404, Code: "not_found"}
    ErrUnauthorized  = &HTTPError{Status: 401, Code: "unauthorized"}
    ErrForbidden     = &HTTPError{Status: 403, Code: "forbidden"}
    ErrBadRequest    = &HTTPError{Status: 400, Code: "bad_request"}
    ErrConflict      = &HTTPError{Status: 409, Code: "conflict"}
    ErrPayloadTooBig = &HTTPError{Status: 413, Code: "payload_too_large"}
)
```

Wrapper `chi.HandlerFunc` convertit `*HTTPError` → JSON `{ "error": msg }` au bon status. Erreurs non typées → 500 + log structuré + corrélation ID dans header `X-Request-ID`. Messages utilisateur copiés à l'identique d'Express (iso strict).

### 5.5 Logging

- `log/slog` stdlib (Go 1.21+), JSON handler.
- Champs systématiques : `request_id`, `route`, `status`, `duration_ms`, `user_sub` (claim JWT).
- Compatible Loki/Grafana directement.
- Horodatage RFC3339Nano.

### 5.6 Règles de concurrence

1. Toute fonction touchant Redis ou filesystem prend `context.Context` en premier paramètre.
2. Pas de variable globale mutable. Hub WS, stores, config injectés via une struct `App` construite dans `cmd/server/main.go`.
3. Parsing batch (`/request-queues/analyze`, `/dataset/analyze`) : parallélisation via `errgroup.Group` avec `SetLimit(runtime.GOMAXPROCS(0))`.
4. Graceful shutdown : `signal.NotifyContext(ctx, SIGINT, SIGTERM)` → `httpServer.Shutdown(ctx)` → `hub.Close()` → fermeture clients Redis. Délai max 15s.

---

## 6. Tests — port 1:1 des 17 fichiers Node

### 6.1 Mapping fichier-pour-fichier

| Test Node (`tests/`) | Test Go équivalent | Cible testée |
|---|---|---|
| `albums.test.js` | `tests/albums_test.go` | handlers `httpapi/albums` |
| `alerts.test.js` | `tests/alerts_test.go` | `domain/alerts` + handler |
| `auditLog.test.js` | `tests/audit_test.go` | `store/auditstore` + middleware |
| `callbacks.test.js` | `tests/callbacks_test.go` | handlers `httpapi/callbacks` |
| `capacityHistory.test.js` | `tests/capacity_history_test.go` | `domain/capacityhistory` |
| `capacityPlanning.test.js` | `tests/capacity_planning_test.go` | `domain/capacityplanning` |
| `dataset-counts.test.js` | `tests/dataset_counts_test.go` | handler `dataset.Counts` |
| `dataset-urls.test.js` | `tests/dataset_urls_test.go` | handler `dataset.URLs` |
| `domains.test.js` | `tests/domains_test.go` | `domain/domains` + handlers |
| `imageDownloadProxy.test.js` | `tests/image_proxy_test.go` | `httpapi/imageproxy` |
| `password.test.js` | `tests/password_test.go` | `auth/password` (scrypt verify) |
| `replicaHistory.test.js` | `tests/replica_history_test.go` | `domain/replicahistory` |
| `request-queues-status.test.js` | `tests/queues_status_test.go` | handler `queues.List` (statuts) |
| `server.test.js` | `tests/server_test.go` | health + smoke startup |
| `systemStats.test.js` | `tests/system_stats_test.go` | `domain/systemstats` |
| `timeline.test.js` | `tests/timeline_test.go` | `domain/timeline` |
| `helpers/fixture.test.js` | `tests/helpers/fixture_test.go` | méta-test du helper |

### 6.2 Stack de test — stdlib partout

- Runner : `go test ./...` (parallèle par défaut, `-race` activé en CI).
- HTTP : `net/http/httptest` (NewServer / NewRecorder).
- Redis : `github.com/alicebob/miniredis/v2` — Redis in-memory pur Go, **aucun conteneur requis**.
- Filesystem : `t.TempDir()` stdlib.
- JSON assertion : `encoding/json.Unmarshal` + `github.com/google/go-cmp/cmp` pour les diffs lisibles.
- Auth : helper `mintTestToken(t, claims)`.
- **Pas de framework BDD** (ni testify/suite, ni ginkgo). Stdlib `testing` + `go-cmp` uniquement.

### 6.3 Discipline qualité

1. Chaque test Node a un test Go portant **exactement les mêmes cas**, traduits en `t.Run("...", func(t *testing.T))`.
2. **Table-driven tests** quand le test Node fait une boucle de cas — on garde la liste exacte des inputs.
3. Coverage minimale au cutover : `go test -cover` ≥ couverture du Node sur les mêmes packages.
4. **Test de parité d'erreur** : pour chaque endpoint, un test confirme que le payload d'erreur (status + corps JSON) est byte-for-byte identique au Node.

### 6.4 Tests additionnels (justifiés par les motivations Go)

- `tests/ws_broadcast_test.go` : 100 clients connectés, 1 000 messages publiés sur miniredis pubsub, assertion sur la réception ordonnée.
- `tests/queues_analyze_bench_test.go` : `BenchmarkAnalyze` sur fichier queue 100k URLs. À comparer manuellement à Node.
- `tests/path_traversal_test.go` : suite de chemins malicieux (`../../../etc/passwd`, etc.) → tous renvoient 400.

### 6.5 Fixtures

Le dossier `tests/fixtures/` actuellement vide est peuplé : 1 job factice, 2 domaines, ~20 URLs queue, 1 dataset, 1 callback. Versionnés (<10 KB total).

### 6.6 CI

```bash
go vet ./...
golangci-lint run                    # config: errcheck, govet, staticcheck, gosec
go test -race -cover ./...
```

GitHub Action sur `RAG-HP-PUB`.

---

## 7. Docker, déploiement & cutover

### 7.1 Dockerfile multi-stage

```dockerfile
# ---- builder ----
FROM golang:1.23-alpine AS builder
WORKDIR /src
RUN apk add --no-cache git ca-certificates
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ENV CGO_ENABLED=0 GOOS=linux GOFLAGS="-trimpath"
RUN go build -ldflags="-s -w -X main.version=$(git rev-parse --short HEAD)" \
    -o /out/server ./cmd/server

# ---- runtime ----
FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=builder /out/server /app/server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
USER nonroot:nonroot
EXPOSE 3001
ENTRYPOINT ["/app/server"]
```

Image finale ~10-15 MB (vs ~180 MB Node).

### 7.2 docker-compose.yml — swap minimal

```yaml
crawler-monitor-backend:
  build: ./apps-microservices/crawler-monitor-backend
  ports:
    - "3001:3001"
  environment:
    - REDIS_URL=${REDIS_URL}
    - JWT_SECRET=${JWT_SECRET}             # IDENTIQUE → tokens valides
    - ADMIN_PASSWORD=${ADMIN_PASSWORD}      # même hash scrypt
    - CRAWLER_STORAGE_PATH=/app/storage
    - PORT=3001
    - LOG_LEVEL=info
  volumes:
    - crawler_storage:/app/storage:rw
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "/app/server", "healthcheck"]
    interval: 10s
    timeout: 3s
    retries: 3
```

Note : `wget` / `curl` absents en distroless → on ajoute une sous-commande `server healthcheck` qui fait un GET local sur `127.0.0.1:3001/health`.

### 7.3 Variables d'environnement

| Variable | Compatibilité | Note |
|---|---|---|
| `REDIS_URL` | Iso (fatal si manquant) | Reproduit le crash startup Node |
| `JWT_SECRET` | Iso (fatal si manquant) | Identique → continuité tokens |
| `ADMIN_PASSWORD` | Iso (fatal si manquant) | Même hash scrypt |
| `CRAWLER_STORAGE_PATH` | Iso (default `/app/storage`) | |
| `PORT` | Iso (default `3001`) | |
| `FRONTEND_ORIGIN` | Iso (CORS) | |
| `LOG_LEVEL` | **Nouveau** (default `info`) | Additif, sans impact |
| `LOG_FORMAT` | **Nouveau** (default `json`) | Additif, sans impact |

### 7.4 Continuité audit log

`auditstore.Local` lit le format JSONL produit par `auditLog.js` (Node) au démarrage et continue à écrire dans le même format. Test de parité dédié : lire un fichier produit par Node, le réécrire avec Go, diff = 0.

### 7.5 Stratégie de cutover

| Étape | Action | Critère de passage |
|---|---|---|
| **0. Pré-cutover** | Snapshot prod : version Express, hash image, métriques baseline (RAM, CPU, p50/p99) | Capturé dans le PR description |
| **1. Mode shadow** | Conteneur Go déployé sur port 3002 en parallèle, sans trafic. Smoke tests `curl` sur les 35 routes avec un token valide | `tests/contract_smoke.sh` passe |
| **2. Bascule** | Stop Express, démarrer Go sur 3001. Frontend reprend automatiquement | Latence p50 ≤ baseline, taux 5xx = 0 sur 5 min |
| **3. Watch (24h)** | Monitoring Grafana : RAM, p99 par endpoint, broadcast WS rate, erreurs JWT | Aucune anomalie sur 24h |
| **4. Rollback prêt** | Image Express tagguée `last-express` dans le registry, `docker compose up crawler-monitor-backend-express` suffit | Rollback testé en staging avant prod |

### 7.6 CI/CD

- PR : `go vet`, `golangci-lint`, `go test -race -cover`, build Docker multi-arch (amd64/arm64).
- Merge `main` : push image registry GCP avec tags `latest`, `<commit-sha>`, `last-express` épinglé.
- Déploiement GCP : manuel comme aujourd'hui (`docker compose pull && up -d`).

---

## 8. Plan de migration en 7 phases

**Phase 1 — Fondations** (~1-2 j)
`go mod init`, layout, `cmd/server/main.go`, config, middlewares stub, helpers respond/errors, `slog`, `/health` + sous-commande `healthcheck`, Dockerfile, entrée docker-compose en port 3002 (non utilisée).
→ Livrable : conteneur Go boote, `/health` répond, JWT middleware testé.

**Phase 2 — Auth & store** (~1-2 j)
`auth/password` (scrypt) + tests, `POST /api/login`, `store/redisstore` (catalogue exhaustif des clés crawler), `store/filestore` + `safeJoin` + tests path traversal, `store/auditstore` compatible JSONL Node.
→ Livrable : login fonctionnel, tokens interopérables avec Express, audit log compatible.

**Phase 3 — Endpoints lecture seule** (~2-3 j)
Ordre : `/api/jobs` (list), `/api/jobs/:id/details`, `/api/capacity*`, `/api/replicas/history`, `/api/system/*`, `/api/audit`, `/api/timeline`, `/api/domains*`, `/api/alerts`, `/api/capacity-planning/ram`. 1 endpoint = 1 PR (handler + domain + test Go).
→ Livrable : ~13 endpoints lecture iso-strict, smoke test contractuel passe.

**Phase 4 — Endpoints métier complexes** (~4-6 j)
1. `/api/jobs/:id/performance` + `/api/jobs/:id/replay` (extraction logique inline → `domain/jobperf` + `domain/queue`).
2. `/api/jobs/:id/request-queues` (list, read/write, analyze, clean-patterns, repair, drop) — bloc le plus dense (~500 lignes Node).
3. `/api/jobs/:id/dataset/*`.
4. `/api/callbacks/*`.
5. `/api/albums`.
6. `imageDownloadProxy` si encore consommé par le front.
→ Livrable : iso strict atteint sur les 35 routes, couverture ≥ baseline Node.

**Phase 5 — WebSocket** (~1-2 j)
`internal/ws/hub.go` + `client.go` + `pubsub.go`. Handler upgrade avec validation JWT en query. Test `ws_broadcast_test.go`. Test reconnexion (kill miniredis).
→ Livrable : WS opérationnel, parité fonctionnelle avec `wss.clients` Express.

**Phase 6 — Bench & validation perf** (~1 j)
1. `BenchmarkAnalyze` queue 100k URLs : Go vs Node.
2. RAM idle + sous charge (vegeta/k6 : 50 RPS, 5 min).
3. WS broadcast : 100 clients × 50 publish/s, p99 reception.
4. Doc `docs/benchmarks/2026-04-go-vs-express.md`.
→ Livrable : preuve chiffrée des motivations gagnées. Si bench déçoit, stop cutover et enquête.

**Phase 7 — Cutover & watch** (~0,5 j cutover + watch passif J+7)
Étapes 1→4 du tableau §7.5. Rollback prêt jusqu'à J+7.
→ Livrable final : Express retiré du `docker-compose.yml`, image `last-express` archivée, dossier `tests/` Express déplacé dans `legacy/` ou retiré.

**Estimation totale** : ~10-15 jours de dev. Le plan d'implémentation détaillé (étape suivante) découpera en tâches ~1-3h chacune.

---

## 9. Risques résiduels & mitigations

| Risque | Mitigation |
|---|---|
| Endpoint Node a un comportement non-documenté qu'on rate | Tests de contrat (port 1:1 + smoke `curl` post-cutover). Si gap découvert post-cutover → patch + redeploy, image Express en rollback |
| `auditstore` Go n'écrit pas exactement le même format JSONL que Node | Test dédié : lire fichier produit par Node, réécrire avec Go, diff = 0 |
| Différence subtile de marshaling JSON (ordre des clés, encoding Unicode) | Test de parité d'erreur + snapshot tests sur 2-3 endpoints sensibles. Go `encoding/json` déterministe, faible risque en pratique |
| Bench performance déçoit sur un endpoint critique | Phase 6 bloque le cutover. Enquête ciblée (profiler `pprof`) avant de poursuivre |
| Régression silencieuse sur le frontend Vite | Tests smoke `curl` post-cutover sur les 35 routes ; surveillance Grafana 24h post-bascule |

---

## 10. Hors périmètre (non couvert par cette migration)

- **Refonte d'API** : aucun changement de contrat (iso strict). Les améliorations (versioning `/v2`, endpoints redondants) feront l'objet d'un design séparé après stabilisation.
- **Migration des autres microservices Go** : ce design ne préjuge pas d'autres migrations Node→Go dans `RAG-HP-PUB`.
- **Refonte du frontend** : `crawler-monitor-frontend` reste inchangé.
- **Migration de stockage** : pas de changement de Redis vers une autre DB ; `CRAWLER_STORAGE_PATH` reste un volume Docker.

---

## 11. Définition de fait (critères d'acceptation)

Le service Go est considéré « prêt pour cutover » quand **tous** les critères suivants sont vrais :

1. ✅ Les 35 routes REST renvoient des réponses byte-for-byte identiques à l'Express sur les fixtures de test (test de parité).
2. ✅ Les 17 tests Node sont portés en Go et tous verts (`go test -race ./...`).
3. ✅ Couverture `go test -cover` ≥ couverture Node sur les mêmes packages.
4. ✅ WebSocket : 100 clients connectés simultanément reçoivent les broadcasts dans l'ordre, sans drop.
5. ✅ Reconnexion Redis automatique vérifiée (test `kill miniredis` puis restart).
6. ✅ Path traversal bloqué sur tous les handlers filesystem.
7. ✅ Tokens JWT émis par l'Express sont acceptés par le Go (test interop).
8. ✅ Audit log Go lit et étend les fichiers JSONL produits par Node sans corruption.
9. ✅ Bench `BenchmarkAnalyze` sur fichier queue 100k URLs montre un gain CPU significatif vs Node.
10. ✅ RAM idle conteneur Go ≤ 50 MB (mesuré avec `docker stats`).
11. ✅ Rollback testé en staging : repasser à l'image Express en < 1 min.
12. ✅ CI verte sur la branche `features/crawler-monitor-backend-go`.
