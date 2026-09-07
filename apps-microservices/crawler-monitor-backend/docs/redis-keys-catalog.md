# Catalogue Redis — crawler-monitor-backend

> Catalogue des cles Redis du service (implementation Go).
> Les colonnes `Source` renvoient a l'ancien `server.js` / `src/lib/*.js`,
> conserve comme reference de comportement.
>
> **Mise a jour 2026-08 :** toutes les enumerations de cles utilisent `SCAN`
> (jamais `KEYS`), et le monitor **n'ecrit plus jamais** `crawl_job:<id>` :
> cette cle appartient a crawler-service.

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
| `GET /api/jobs` | `SCAN` (COUNT 10000) | `crawl_job:*` | redisstore/jobs.go | Enumère les clés de jobs sans bloquer Redis (`KEYS` proscrit) |
| `GET /api/jobs` | `MGET` | `crawl_job:*` (clés issues du SCAN) | redisstore/jobs.go | Batch GET de toutes les valeurs JSON des jobs |
| `GET /api/jobs/:id/performance` | `ZRANGEBYSCORE` (`zRangeByScore`) | `job:perf:<id>` | jobPerformance.js:50 | Délégué à `readJobPerf` — range `-inf` → `+inf` |
| `GET /api/jobs/:id/replay` | `ZRANGEBYSCORE` (`zRangeByScore`) | `job:perf:<id>` | jobPerformance.js:50 (via `readJobPerf`) | Points de performance pour le player |
| `GET /api/jobs/:id/replay` | `GET` | `crawl_job:<id>` | server.js:335 | Métadonnées du job pour le replay (domain, status, oom_restart_count…) |
| `GET /api/jobs/:id/details` | `GET` | `crawl_job:<id>` | server.js:463 | Données de base du job avant lecture du fichier log |
| `GET /api/jobs/:id/dataset/analyze` | `GET` | `crawl_job:<id>` | server.js:1141 | Récupère le domaine du job pour trouver le dossier dataset |
| `POST /api/jobs/:id/dataset/deduplicate` | `GET` | `crawl_job:<id>` | server.js:1221 | Récupère le domaine du job pour trouver le dossier dataset |
| `GET /api/capacity` | `GET` ×2 | `crawl_jobs:running_count`, `crawl_jobs:max_global_crawls` | server.js:1372–1373 | Lecture de la capacité courante |
| `GET /api/alerts` | `SCAN` + `MGET` | `crawl_job:*` | redisstore.ListJobs | Charge tous les jobs pour évaluer les règles d'alertes |
| `GET /api/alerts` | `ZRANGEBYSCORE` (`zRangeByScore`) | `capacity:history:zset` | capacityHistory.js:52 (via `readCapacityHistory`) | Dernière 1h d'historique de capacité |
| `GET /api/alerts` | `LLEN` | `crawl_jobs:failed_callbacks` | server.js:1399 | Compte le nombre de callbacks en échec |
| `GET /api/alerts` | `SMEMBERS` + `ZRANGEBYSCORE` | `replica:known`, `replica:history:<id>` (par replica) | replicaHistory.js:77,64 (via `readAllReplicasHistory`) | Historique CPU des replicas pour détecter CPU élevé soutenu |
| `GET /api/domains` | `SCAN` + `MGET` | `crawl_job:*` | redisstore.ListJobs | Charge tous les jobs pour agréger par domaine |
| `GET /api/domains/:domain` | `SCAN` + `MGET` | `crawl_job:*` | redisstore.ListJobs | Charge tous les jobs pour filtrer par domaine |
| `GET /api/timeline` | `SCAN` + `MGET` | `crawl_job:*` | redisstore.ListJobs | Charge tous les jobs pour la timeline |
| `GET /api/capacity-planning/ram` | `SMEMBERS` + `ZRANGEBYSCORE` (window=1h) | `replica:known` + `replica:history:<id>` | replicaHistory.js:77,64 (via `readAllReplicasHistory`) | Chemin rapide 1h |
| `GET /api/capacity-planning/ram` | `SCAN` + `ZRANGEBYSCORE` (window=24h\|7d) | `job:perf:*` + score range | redisstore.ScanJobPerfByReplica | `SCAN` COUNT 200 sur `job:perf:*` + ZRANGEBYSCORE par clé |
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
| `GET /api/system/stats` | `SCAN` + `MGET` | `crawl_job:*` | redisstore.ListJobs | Stats agrégées sur fenêtre de temps |
| `GET /api/system/stats` | `ZRANGEBYSCORE` | `capacity:history:zset` | capacityHistory.js:52 (via `readCapacityHistory`) | Saturation de capacité sur la fenêtre |
| `GET /api/system/health` | `PING` | — | server.js:1681 | Healthcheck Redis (avec timeout 1.5s) |
| `helper: redisstore.ListJobs` | `SCAN` | `crawl_job:*` | redisstore/jobs.go | Récupère toutes les clés de jobs (curseur, COUNT 10000) |
| `helper: redisstore.ListJobs` | `MGET` | toutes clés issues du SCAN | redisstore/jobs.go | Batch GET de toutes les valeurs JSON des jobs |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `ZADD` | `replica:history:<replicaId>` | replicaHistory.js:50 | Insère un point CPU/RAM (score=ts) |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `ZREMRANGEBYSCORE` | `replica:history:<replicaId>` | replicaHistory.js:51 | Taille la fenêtre à 1h (supprime les points > retention) |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `SADD` | `replica:known` | redisstore/replicas.go | Enregistre le replicaId dans l'ensemble des replicas connus |
| `sub: crawler:heartbeat` → `persistHeartbeat` | `EXPIRE` (2h) | `replica:history:<replicaId>` | redisstore/replicas.go | TTL de sécurité : une réplique disparue ne laisse pas de série orpheline |
| `sub: crawler:heartbeat` → `persistJobPerf` | `ZADD` | `job:perf:<jobId>` | jobPerformance.js:32 | Insère un point CPU/RAM (score=ts) |
| `sub: crawler:heartbeat` → `persistJobPerf` | `ZREMRANGEBYSCORE` | `job:perf:<jobId>` | jobPerformance.js:34 | Taille la fenêtre à 7j |
| `sub: crawler:heartbeat` → `persistJobPerf` | `EXPIRE` | `job:perf:<jobId>` | jobPerformance.js:36 | TTL 7j pour nettoyage automatique des clés abandonnées |
| `cron: snapshotCapacity (60s)` | `GET` ×2 | `crawl_jobs:running_count`, `crawl_jobs:max_global_crawls` | capacityHistory.js:29–30 | Lit les valeurs courantes |
| `cron: snapshotCapacity (60s)` | `ZADD` | `capacity:history:zset` | capacityHistory.js:40 | Insère un snapshot {ts, running, max, full} |
| `cron: snapshotCapacity (60s)` | `ZREMRANGEBYSCORE` | `capacity:history:zset` | capacityHistory.js:42 | Taille la fenêtre à 24h |
| `readAllReplicasHistory` | `SREM` | `replica:known` | redisstore/replicas.go | Purge un replica sans données **uniquement** si la fenêtre demandée ≥ rétention (1h) : sur une fenêtre courte l'absence de points ne prouve pas la mort du replica |

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

## Notes d'implémentation Go

- **`crawl_job:<id>` est en lecture seule pour ce service.** Le monitor a un temps
  réécrit cette clé depuis les heartbeats (`persistJob`) : il écrasait le `status`
  écrit par crawler-service (finished/failed/stopping), posait un TTL 48h sur une
  clé qui n'en avait pas et provoquait des lost-updates. Ce code a été supprimé.
- `SCAN crawl_job:*` + `MGET` est centralisé dans `redisstore.ListJobs` (un seul
  point d'entrée pour jobs / alerts / domains / timeline / system stats).
- Les écritures de séries (`PersistHeartbeat`, `PersistJobPerfSample`) passent par
  un **pipeline** (ZADD + ZREMRANGEBYSCORE + EXPIRE + SADD en un aller-retour) et
  loguent toute erreur (`redis.write_failed`) au lieu de l'ignorer.
- `crawl_jobs:failed_callbacks` est une **liste Redis** écrite par le crawler-service Python (pas par ce service). Les opérations de lecture (`LRANGE`, `LINDEX`, `LLEN`) et de mutation (`LREM`, `LSET`, `DEL`) sont toutes dans ce service.
- Les sorted-sets `replica:history:*` et `job:perf:*` sont écrits **en temps réel** depuis les subscribers Pub/Sub (`crawler:heartbeat`). La rétention est gérée par `ZREMRANGEBYSCORE` (sliding window) + `EXPIRE` sur `job:perf:*`.
- Le client Redis utilise **deux connexions** : une connexion persistante (requêtes normales) et une connexion subscriber dédiée (ne peut pas exécuter d'autres commandes). En Go : `redis.NewClient` + `client.Subscribe`.
- Toutes les valeurs stockées dans les sorted-sets sont des **JSON strings** (pas de valeurs primitives).
