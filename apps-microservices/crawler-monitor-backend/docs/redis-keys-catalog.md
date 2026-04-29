# Catalogue Redis — crawler-monitor-backend

> Référence Phase 0 pour la migration Node → Go.
> Sources analysées : `server.js` (1813 lignes) + `src/lib/*.js`

---

## Constantes (noms et valeurs)

| Constante | Valeur | Type Redis | Source | Description |
|---|---|---|---|---|
| `CRAWL_UPDATES_CHANNEL` | `'crawl_updates'` | pubsub | server.js:43 | Channel Pub/Sub — broadcast des mises à jour de jobs vers les clients WebSocket |
| `CRAWL_JOB_PREFIX` | `'crawl_job:'` | string (JSON) | server.js:44 | Préfixe des clés de jobs : `crawl_job:<crawl_id>` |
| `CRAWL_RUNNING_COUNT_KEY` | `'crawl_jobs:running_count'` | string (entier) | server.js:45 | Compteur courant de crawls actifs (écrit par crawler-service) |
| `CRAWL_MAX_GLOBAL_KEY` | `'crawl_jobs:max_global_crawls'` | string (entier) | server.js:46 | Limite maximale de crawls simultanés (écrit par crawler-service) |
| `FAILED_CALLBACKS_KEY` | `'crawl_jobs:failed_callbacks'` | list (JSON) | server.js:47 | Liste des callbacks HTTP GET ayant échoué (écrit par crawler-service Python) |
| `CAPACITY_HISTORY_KEY` | `'capacity:history:zset'` | sorted-set (JSON) | capacityHistory.js:7 | Historique de capacité (running/max) — score = timestamp ms |
| `REPLICA_HISTORY_PREFIX` | `'replica:history:'` | sorted-set (JSON) | replicaHistory.js:15 | Préfixe des séries temporelles CPU/RAM par replica : `replica:history:<replicaId>` |
| `KNOWN_REPLICAS_KEY` | `'replica:known'` | set (strings) | replicaHistory.js:16 | Ensemble des replicaId connus — mis à jour à chaque heartbeat |
| `JOB_PERF_PREFIX` | `'job:perf:'` | sorted-set (JSON) | jobPerformance.js:12 | Préfixe des séries CPU/RAM par job : `job:perf:<jobId>` |

---

## Clés statiques (sans préfixe)

| Clé | Type | Source | Description |
|---|---|---|---|
| `crawl_jobs:running_count` | string (entier) | server.js:45 | Valeur de `CRAWL_RUNNING_COUNT_KEY` — lecture seule côté monitor |
| `crawl_jobs:max_global_crawls` | string (entier) | server.js:46 | Valeur de `CRAWL_MAX_GLOBAL_KEY` — lecture seule côté monitor |
| `crawl_jobs:failed_callbacks` | list (JSON) | server.js:47 | Valeur de `FAILED_CALLBACKS_KEY` — liste Redis, lecture + mutation par le monitor |
| `capacity:history:zset` | sorted-set (JSON) | capacityHistory.js:7 | Valeur de `CAPACITY_HISTORY_KEY` — écrit + lu par le monitor (snapshot toutes les 60s) |
| `replica:known` | set (strings) | replicaHistory.js:16 | Valeur de `KNOWN_REPLICAS_KEY` — registre des replicas actifs |

---

## Channels pub/sub

| Channel | Source | Émetteur | Consommateur | Payload |
|---|---|---|---|---|
| `crawl_updates` (`CRAWL_UPDATES_CHANNEL`) | server.js:43, 1740 | crawler-service (Python) | crawler-monitor-backend (subscriber) → broadcast WebSocket | JSON `{ crawl_id }` |
| `crawler:heartbeat` | server.js:1750 | crawler-service (Python) | crawler-monitor-backend (subscriber) → broadcast + persistHeartbeat + persistJobPerf | JSON `{ type, replicaId, jobId, domain, cpu, ram, totalRam, topProcesses, timestamp }` |

---

## Patterns d'accès par endpoint/fonction

| Endpoint / fonction | Opération Redis | Clé / pattern | Source | Notes |
|---|---|---|---|---|
| `GET /api/jobs` | `KEYS` | `crawl_job:*` | server.js:281 | Récupère toutes les clés de jobs (potentiellement coûteux en prod) |
| `GET /api/jobs` | `MGET` | `crawl_job:*` (toutes clés issues de KEYS) | server.js:284 | Batch GET de toutes les valeurs JSON des jobs |
| `GET /api/jobs/:id/performance` | `ZRANGEBYSCORE` (`zRangeByScore`) | `job:perf:<id>` | jobPerformance.js:50 | Délégué à `readJobPerf` — range `-inf` → `+inf` |
| `GET /api/jobs/:id/replay` | `ZRANGEBYSCORE` (`zRangeByScore`) | `job:perf:<id>` | jobPerformance.js:50 (via `readJobPerf`) | Points de performance pour le player |
| `GET /api/jobs/:id/replay` | `GET` | `crawl_job:<id>` | server.js:335 | Métadonnées du job pour le replay (domain, status, oom_restart_count…) |
| `GET /api/jobs/:id/details` | `GET` | `crawl_job:<id>` | server.js:463 | Données de base du job avant lecture du fichier log |
| `GET /api/jobs/:id/dataset/analyze` | `GET` | `crawl_job:<id>` | server.js:1141 | Récupère le domaine du job pour trouver le dossier dataset |
| `POST /api/jobs/:id/dataset/deduplicate` | `GET` | `crawl_job:<id>` | server.js:1221 | Récupère le domaine du job pour trouver le dossier dataset |
| `GET /api/capacity` | `GET` ×2 | `crawl_jobs:running_count`, `crawl_jobs:max_global_crawls` | server.js:1372–1373 | Lecture de la capacité courante |
| `GET /api/alerts` | `KEYS` + `MGET` | `crawl_job:*` | server.js:1396–1397 (via `loadAllJobs`) | Charge tous les jobs pour évaluer les règles d'alertes |
| `GET /api/alerts` | `ZRANGEBYSCORE` (`zRangeByScore`) | `capacity:history:zset` | capacityHistory.js:52 (via `readCapacityHistory`) | Dernière 1h d'historique de capacité |
| `GET /api/alerts` | `LLEN` | `crawl_jobs:failed_callbacks` | server.js:1399 | Compte le nombre de callbacks en échec |
| `GET /api/alerts` | `SMEMBERS` + `ZRANGEBYSCORE` | `replica:known`, `replica:history:<id>` (par replica) | replicaHistory.js:77,64 (via `readAllReplicasHistory`) | Historique CPU des replicas pour détecter CPU élevé soutenu |
| `GET /api/domains` | `KEYS` + `MGET` | `crawl_job:*` | server.js:1434 (via `loadAllJobs`) | Charge tous les jobs pour agréger par domaine |
| `GET /api/domains/:domain` | `KEYS` + `MGET` | `crawl_job:*` | server.js:1449 (via `loadAllJobs`) | Charge tous les jobs pour filtrer par domaine |
| `GET /api/timeline` | `KEYS` + `MGET` | `crawl_job:*` | server.js:1472 (via `loadAllJobs` dans `computeTimeline`) | Charge tous les jobs pour la timeline |
| `GET /api/capacity-planning/ram` | `KEYS` + `ZRANGEBYSCORE` (window=1h) | `replica:known` + `replica:history:<id>` | replicaHistory.js:77,64 (via `readAllReplicasHistory`) | Chemin rapide 1h |
| `GET /api/capacity-planning/ram` | `KEYS` + `ZRANGEBYSCORE` (window=24h\|7d) | `job:perf:*` + score range | capacityPlanning.js:144,149 (via `defaultScanJobPerf`) | Scan de toutes les clés `job:perf:*` + ZRANGEBYSCORE par clé |
| `GET /api/replicas/history` | `SMEMBERS` + `ZRANGEBYSCORE` | `replica:known`, `replica:history:<id>` | replicaHistory.js:77,64 (via `readAllReplicasHistory`) | Historique de tous les replicas connus |
| `GET /api/replicas/:replicaId/history` | `ZRANGEBYSCORE` | `replica:history:<replicaId>` | replicaHistory.js:64 (via `readReplicaHistory`) | Historique d'un replica spécifique |
| `GET /api/capacity/history` | `ZRANGEBYSCORE` | `capacity:history:zset` | capacityHistory.js:52 (via `readCapacityHistory`) | Historique de capacité sur une fenêtre glissante |
| `GET /api/callbacks` | `LRANGE` | `crawl_jobs:failed_callbacks` 0 -1 | server.js:1541 | Retourne toute la liste des callbacks en échec |
| `POST /api/callbacks/:index/retry` | `LINDEX` | `crawl_jobs:failed_callbacks` | server.js:1564 | Lit un callback par index pour le rejouer |
| `POST /api/callbacks/:index/retry` (succès) | `LREM` | `crawl_jobs:failed_callbacks` | server.js:1575 | Supprime le callback rejoué avec succès (count=1, premier match) |
| `POST /api/callbacks/:index/retry` (échec) | `LSET` | `crawl_jobs:failed_callbacks` | server.js:1591 | Met à jour le callback avec le nombre de tentatives manuelles |
| `DELETE /api/callbacks/:index` | `LINDEX` | `crawl_jobs:failed_callbacks` | server.js:1616 | Lit l'entrée pour vérifier son existence |
| `DELETE /api/callbacks/:index` | `LREM` | `crawl_jobs:failed_callbacks` | server.js:1618 | Supprime le callback (count=1, premier match) |
| `POST /api/callbacks/clear` | `LLEN` | `crawl_jobs:failed_callbacks` | server.js:1633 | Compte avant suppression |
| `POST /api/callbacks/clear` | `DEL` | `crawl_jobs:failed_callbacks` | server.js:1634 | Supprime toute la liste |
| `GET /api/system/stats` | `KEYS` + `MGET` | `crawl_job:*` | server.js:1664 (via `loadAllJobs` dans `computeSystemStats`) | Stats agrégées sur fenêtre de temps |
| `GET /api/system/stats` | `ZRANGEBYSCORE` | `capacity:history:zset` | capacityHistory.js:52 (via `readCapacityHistory`) | Saturation de capacité sur la fenêtre |
| `GET /api/system/health` | `PING` | — | server.js:1681 | Healthcheck Redis (avec timeout 1.5s) |
| `helper: loadAllJobs(client)` | `KEYS` | `crawl_job:*` | server.js:1645 | Récupère toutes les clés de jobs |
| `helper: loadAllJobs(client)` | `MGET` | toutes clés issues de KEYS | server.js:1647 | Batch GET de toutes les valeurs JSON des jobs |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `ZADD` | `replica:history:<replicaId>` | replicaHistory.js:50 | Insère un point CPU/RAM (score=ts) |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `ZREMRANGEBYSCORE` | `replica:history:<replicaId>` | replicaHistory.js:51 | Taille la fenêtre à 1h (supprime les points > retention) |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `SADD` | `replica:known` | replicaHistory.js:52 | Enregistre le replicaId dans l'ensemble des replicas connus |
| `sub: crawler:heartbeat` → `persistJobPerf` | `ZADD` | `job:perf:<jobId>` | jobPerformance.js:32 | Insère un point CPU/RAM (score=ts) |
| `sub: crawler:heartbeat` → `persistJobPerf` | `ZREMRANGEBYSCORE` | `job:perf:<jobId>` | jobPerformance.js:34 | Taille la fenêtre à 7j |
| `sub: crawler:heartbeat` → `persistJobPerf` | `EXPIRE` | `job:perf:<jobId>` | jobPerformance.js:36 | TTL 7j pour nettoyage automatique des clés abandonnées |
| `cron: snapshotCapacity (60s)` | `GET` ×2 | `crawl_jobs:running_count`, `crawl_jobs:max_global_crawls` | capacityHistory.js:29–30 | Lit les valeurs courantes |
| `cron: snapshotCapacity (60s)` | `ZADD` | `capacity:history:zset` | capacityHistory.js:40 | Insère un snapshot {ts, running, max, full} |
| `cron: snapshotCapacity (60s)` | `ZREMRANGEBYSCORE` | `capacity:history:zset` | capacityHistory.js:42 | Taille la fenêtre à 24h |
| `readAllReplicasHistory` | `SREM` | `replica:known` | replicaHistory.js:84 | Supprime de l'ensemble un replica sans données dans la fenêtre (opportuniste) |

---

## Résumé des types Redis utilisés

| Type Redis | Clés concernées |
|---|---|
| **string** (JSON ou entier) | `crawl_job:<id>`, `crawl_jobs:running_count`, `crawl_jobs:max_global_crawls` |
| **list** (JSON entries) | `crawl_jobs:failed_callbacks` |
| **set** (strings) | `replica:known` |
| **sorted-set** (JSON, score=ts ms) | `capacity:history:zset`, `replica:history:<replicaId>`, `job:perf:<jobId>` |
| **pubsub** | `crawl_updates`, `crawler:heartbeat` |

---

## Notes de migration Go

- `KEYS crawl_job:*` + `MGET` apparaît à **5 endroits** différents (via `loadAllJobs`). En Go, centraliser dans une fonction `loadAllJobs(ctx, rdb)` pour éviter la duplication.
- `crawl_jobs:failed_callbacks` est une **liste Redis** écrite par le crawler-service Python (pas par ce service). Les opérations de lecture (`LRANGE`, `LINDEX`, `LLEN`) et de mutation (`LREM`, `LSET`, `DEL`) sont toutes dans ce service.
- Les sorted-sets `replica:history:*` et `job:perf:*` sont écrits **en temps réel** depuis les subscribers Pub/Sub (`crawler:heartbeat`). La rétention est gérée par `ZREMRANGEBYSCORE` (sliding window) + `EXPIRE` sur `job:perf:*`.
- Le client Redis utilise **deux connexions** : une connexion persistante (requêtes normales) et une connexion subscriber dédiée (ne peut pas exécuter d'autres commandes). En Go : `redis.NewClient` + `client.Subscribe`.
- Toutes les valeurs stockées dans les sorted-sets sont des **JSON strings** (pas de valeurs primitives).
