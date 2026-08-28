# crawler-monitor-backend

Backend **Go** du dashboard de monitoring du crawler : API REST + WebSocket temps reel
au-dessus de Redis et du stockage disque du crawler.

> Ce service etait historiquement un `server.js` Express mono-fichier. Il a ete
> reecrit en Go ; les commentaires `Mirrors server.js:NNN` du code renvoient a
> cet ancien fichier et servent de reference de comportement.

## Stack

| Couche | Techno |
|---|---|
| Langage | Go 1.25 |
| Routeur HTTP | `github.com/go-chi/chi/v5` |
| Redis | `github.com/redis/go-redis/v9` |
| WebSocket | `github.com/gorilla/websocket` |
| Auth | JWT HS256 (`github.com/golang-jwt/jwt/v5`) |
| Rate limit | `github.com/go-chi/httprate` (cle = IP TCP, en-tetes proxy honores seulement si l'appelant est prive/loopback) |
| CORS | `github.com/go-chi/cors` |
| Logs | `log/slog` (JSON sur stdout) |
| Tests | `testing` + `github.com/alicebob/miniredis/v2` |

## Commandes

| Action | Commande |
|---|---|
| Build | `go build ./...` |
| Lancer | `go run ./cmd/server` |
| Vet | `go vet ./...` |
| Tests | `go test ./...` |
| Tests + detecteur de course | `go test -race ./...` |
| Couverture | `go test -coverpkg=./internal/... -coverprofile=cover.out ./...` |
| Healthcheck (binaire) | `./server healthcheck` |

> Ne pas lancer les tests avec `GOFLAGS=-mod=mod` : cela reecrit `go.mod`.

## Arborescence

```
cmd/server/            # main.go (wiring) + healthcheck.go (sous-commande Docker)
internal/
  config/              # chargement des variables d'env (Load)
  datetime/            # parsing tolerant des dates (ParseAnyMs, AnyToISO)
  auth/password/       # verification du hash scrypt de l'admin
  domain/              # logique metier pure, sans I/O HTTP
    alerts/ callbacks/ capacityplanning/ domains/ imageproxy/
    joblog/ jobperf/ queue/ replicahistory/ systemstats/ timeline/
  httpapi/             # handlers HTTP + router.go (montage des routes)
    middleware/        # jwt, cors, ratelimit, securityheaders, audit
  store/
    redisstore/        # acces Redis (jobs, capacity, replicas, job perf)
    filestore/         # acces au stockage crawler (safejoin anti path-traversal)
    auditstore/        # journal d'audit JSONL sur disque
  ws/                  # hub, client, upgrade, pubsub (abonnement Redis)
tests/                 # tests d'integration (package tests) + tests/benchmarks
docs/                  # catalogue des cles Redis, runbook de bascule
```

## Routes

Publiques :

- `GET /health` — statut + version du binaire
- `POST /api/login` — mot de passe admin -> JWT HS256
- `GET /` et `GET /api` — upgrade WebSocket (`?token=<jwt>`)

Protegees par JWT (`Authorization: Bearer <jwt>`) :

| Methode | Route | Notes |
|---|---|---|
| GET | `/api/jobs` | tableau de jobs, filtres optionnels `?status=` et `?window=` (`15m,1h,6h,24h,7d,30d`) |
| GET | `/api/jobs/{id}/details` | job + parsing de `crawler.log` + cles `config` et `callback` |
| GET | `/api/jobs/{id}/performance` | serie `job:perf:<id>` |
| GET | `/api/jobs/{id}/replay` | points, evenements, zones CPU chaudes |
| GET | `/api/jobs/{id}/dataset/counts` `/urls` `/analyze` | dataset sur disque |
| POST | `/api/jobs/{id}/dataset/deduplicate` | **audite** |
| GET | `/api/jobs/{id}/request-queues` | listing pagine (`page`, `limit`, `search`, `status`) |
| GET | `/api/jobs/{id}/request-queues/analyze` | URLs valides vs bloquees |
| POST | `/api/jobs/{id}/request-queues/clean-patterns` | corps JSON optionnel ; **audite** |
| POST | `/api/jobs/{id}/request-queues/repair` | **audite** |
| POST | `/api/jobs/{id}/request-queues/drop` | **audite** |
| GET/POST | `/api/jobs/{id}/request-queues/{domain}/{filename}` | POST **audite**, corps <= 50 Mo |
| GET | `/api/capacity` | slots courants |
| GET | `/api/capacity/history` | `?window=15m,1h,6h,24h,7d` (400 si inconnue) |
| GET | `/api/capacity-planning/ram` | `?window=1h,6h,24h,7d` (400 si inconnue) ; `15m` reste propre a `/capacity/history`, une fenetre trop courte ne donne pas de pic RAM exploitable |
| GET | `/api/replicas/history` `/api/replicas/{id}/history` | `?window=15m,1h` |
| GET | `/api/system/stats` | `?window=1h,24h,7d` |
| GET | `/api/system/health` | Redis, clients WS, fraicheur du pub/sub |
| GET | `/api/domains` `/api/domains/{domain}` | `count` (domaines) + `total_jobs` (somme) |
| GET | `/api/timeline` `/api/alerts` | |
| GET/POST/DELETE | `/api/callbacks` `…/clear` `…/{idx}/retry` `…/{idx}` | retry en echec -> 200 `{success:false}` |
| GET | `/api/audit` | journal d'audit filtrable |
| GET/POST/DELETE | `/api/albums/*` | proxy vers image-download-service, actions destructrices auditees |

### Redaction

`/api/jobs` et `/api/jobs/{id}/details` retirent systematiquement `params`,
`callback_url`, `failure_callback_url`, `storage_path`, `start_url`, `pid` et
`_redisKey`. Le detail republie une vue sure : `config` (allowlist de `params`,
tout ce qui matche `proxy|apify|token|secret|password|key|auth` est ignore) et
`callback` (`url` / `failure_url` sans query string, `status` — `none` quand
aucun webhook n'est configure).

L'allowlist de `config` est **stricte** : seules les 11 cles de
`configAllowlist` sortent, tout le reste de `params` est ignore. Le motif
`proxy|apify|token|secret|password|key|auth` n'est plus un filtre mais une
assertion : si une cle de l'allowlist venait a le matcher, la valeur est tue et
`config.allowlist_leak` est logue en `ERROR`.

### Dates

`crawler-service` ecrit des dates naives (`2026-08-28 13:20:03.306901`). Les
handlers normalisent `start_time`, `end_time`, `finished_at`, `archived_at`,
`stashed_at`, `downloaded_at`, `last_heartbeat` en RFC3339 UTC via
`datetime.AnyToISO`, et trient numeriquement via `datetime.ParseAnyMs`. Meme
normalisation cote `/api/domains*` (`rawJobsToDomain`) et `/api/timeline`.

Deux limites assumees : `AnyToISO` passe par des millisecondes, donc la
**sous-milliseconde est perdue** (`…03.306901` -> `…03.306Z`) ; et un
`start_time` illisible (`ParseAnyMs` = -1) n'est **pas** filtre par `?window=`
— un job reste visible plutot que de disparaitre a cause d'une date cassee.

## Cles Redis

| Cle | Type | Ecrite par |
|---|---|---|
| `crawl_job:<crawl_id>` | string JSON | **crawler-service uniquement** (le monitor ne fait que lire) |
| `crawl_jobs:running_count` / `crawl_jobs:max_global_crawls` | string entier | crawler-service |
| `crawl_jobs:failed_callbacks` | list JSON | crawler-service (mutee par le monitor) |
| `capacity:history:zset` | zset JSON | monitor (snapshot 60 s, retention 24 h) |
| `replica:history:<replicaId>` | zset JSON | monitor (`PersistHeartbeat`, fenetre 1 h, TTL 2 h) |
| `replica:known` | set | monitor |
| `job:perf:<jobId>` | zset JSON | monitor (`PersistJobPerfSample`, fenetre + TTL 7 j) |

Detail complet dans `docs/redis-keys-catalog.md`.

## Pub/sub

| Canal | Emetteur | Traitement |
|---|---|---|
| `crawl_updates` | crawler-service (Python) | `{crawl_id,status,timestamp}` -> diffuse `{type:"job_update",crawl_id}` |
| `crawler:heartbeat` | sous-process crawler TS (toutes les 2 s) | persiste `replica:history` + `job:perf`, puis diffuse `{type:"replica_heartbeat",data:{…}}` |

`internal/ws/pubsub.go` **diffuse d'abord, persiste ensuite** (la latence WS du
dashboard n'attend pas l'aller-retour Redis), chaque etape isolee dans son
propre `recover()` (`ws.pubsub.panic`) : un panic de l'une n'empeche pas
l'autre. La fermeture du canal go-redis remonte une erreur pour que `Run` se
reabonne avec backoff, remis a 1 s des qu'un abonnement a servi au moins un
message.

**Watchdog** : une connexion subscriber a demi-morte ne ferme pas le canal
go-redis, donc `Run` ne se relancerait jamais. `runOnce` arme un timer
(`idleTimeout`, 120 s) : passe ce delai sans message alors que
`crawl_jobs:running_count > 0`, il logue `ws.pubsub.idle_resubscribe` et rend
`errPubSubIdle` pour reconstruire l'abonnement. Sans crawl actif, le silence
est normal et l'abonnement est conserve.

`PubSub.LastMessageAt()` (amorce a l'abonnement) alimente
`pubsub_last_message_ms` et `pubsub_last_message_age_ms` dans
`/api/system/health` : `status: "degraded"` si plus de 60 s sans message alors
que des crawls tournent. Age = `-1` tant qu'aucun message n'est arrive (service
qui vient de booter) : ce cas n'est pas une panne.

## Variables d'environnement

| Variable | Defaut | Role |
|---|---|---|
| `REDIS_URL` | — | **obligatoire** |
| `ADMIN_PASSWORD_HASH` | — | **obligatoire**, format scrypt |
| `JWT_SECRET` | — | **obligatoire** |
| `PORT` | `3001` | |
| `CRAWLER_STORAGE_PATH` | `/app/storage` | racine des donnees crawler |
| `CORS_ALLOWED_ORIGINS` | vide (tout accepte) | CSV ; sert aussi au `CheckOrigin` WebSocket. Valeur recommandee en prod : `https://cmf.hellopro.eu`. Vide ou `*` -> `slog.Warn("cors.permissive")` au demarrage |
| — | — | `POST /api/login` a son propre quota, plus strict : 10 req/min par IP |
| `RATE_LIMIT_MAX` | `600` | requetes par fenetre |
| `RATE_LIMIT_WINDOW_MS` | `900000` | fenetre du rate limit |
| `REPLAY_HIGH_CPU` | `0.85` | seuil des zones chaudes du replay |
| `AUDIT_LOG_DIR` | `./logs/audit/` | journal JSONL |
| `AUDIT_RETENTION_DAYS` | `90` | rotation du journal |
| `IMAGE_DOWNLOAD_SERVICE_URL` | `http://image-download-service:8505` | cible du proxy albums |

## Docker

- Build multi-etages `golang:1.25-alpine` -> `gcr.io/distroless/static-debian12:nonroot`
- `ARG VERSION` injecte dans `main.version` (`-ldflags -X`) ; passe par
  `docker-compose.yml` via `build.args.VERSION: ${CRAWLER_MONITOR_VERSION:-dev}`
  pour que `/health` soit tracable
- Healthcheck : `["CMD", "/app/server", "healthcheck"]`
- Port 3001

## Conventions

- Handlers HTTP fins : la logique vit dans `internal/domain/*`, testable sans HTTP
- Les erreurs d'ecriture Redis ne bloquent pas le flux mais sont loggees (`redis.write_failed`)
- `filestore` passe par `safejoin` : aucun chemin utilisateur ne sort de la racine
- Commentaires en francais, noms de symboles en anglais
- Nouveau comportement = nouveau test dans `tests/` (miniredis, pas de Redis reel)

## Dependances

- **Redis** — etat des jobs, capacite, series temporelles, pub/sub
- **crawler-service** (Python + sous-process TS) — ecrit `crawl_job:*` et publie les evenements
- **image-download-service** — cible du proxy `/api/albums/*`
- **crawler-monitor-frontend** — SPA React consommatrice de cette API
