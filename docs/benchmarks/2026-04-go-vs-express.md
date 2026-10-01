# Benchmarks Go vs Express — crawler-monitor-backend (2026-04)

Synthèse des mesures perf sur la version Go fraîchement migrée, pour valider les motivations du spec :
1. Throughput REST + parsing fichiers queue
2. Concurrence WebSocket / pub/sub Redis
3. Empreinte mémoire / coût VM GCP

## Configuration

- Go 1.25, Linux WSL2 Ubuntu 24.04, Intel Core i5-8500 @ 3.00GHz, 2 vCPU alloués
- miniredis in-memory pour les benchs WS et stores
- Filesystem `t.TempDir()` pour les benchs queue.Analyze

## queue.Analyze — CPU + parsing fichiers JSON

| Stack | Fixture | Temps | allocs/op | bytes/op | Notes |
|---|---|---|---|---|---|
| Go (chi, sync.WaitGroup limit=8) | 10k URLs | **2.97s** | 24M allocs | 2.79 GB | `BenchmarkQueueAnalyze_10k -benchtime=1x` |
| Go | 100k URLs | TBD | TBD | TBD | `BenchmarkQueueAnalyze_100k -benchtime=1x` (10x extrapolé ~30s) |
| Node (Express) | équivalent | TBD | n/a | n/a | Mesure manuelle ad-hoc à reporter au cutover prod |

**Verdict throughput** : ⏸ **À confirmer** vs mesure Node de référence. Le bench Go est exécutable mais nécessite un point de comparaison Node sur la même fixture pour conclure. Le ratio cible ≥5x est attendu compte tenu de la parallélisation par domaine (8 workers concurrent vs event loop Node).

**Observation** : 24M allocations pour 10k URLs = ~2400 allocs/URL. Optimisation possible avec un decoder JSON streaming + pool de buffers, mais hors périmètre cutover.

## WS broadcast latency — concurrence pub/sub

| Stack | Clients | Rate | Durée | Samples | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|
| **Go (gorilla/ws + hub goroutines)** | **50** | **50 pub/s** | **5s** | **12500** | **658µs** | **1.12ms** | **1.97ms** |
| Node (ws lib) | équivalent | équivalent | équivalent | TBD | n/a | n/a | n/a |

**Verdict concurrence** : ✅ **ATTEINT**. p99 = 1.97ms — **50× sous la cible** ≤100ms. Le hub Go avec 1 goroutine writePump par client + broadcast non bloquant produit une latence sub-millisecondaire en p50. Aucun message perdu sur 12500 réceptions = 0% drop rate.

## RAM (idle + sous charge)

| Stack | RAM idle (MB) | RAM 50 RPS sur /api/jobs (MB) | Notes |
|---|---|---|---|
| Go (distroless static) | TBD | TBD | Cible : ≤ 50 MB idle, ≤ 100 MB charge. Mesure prod (Task 6.3) |
| Node 20 alpine (Express) | ~150 MB | ~250 MB | Mesure historique de référence |

**Verdict RAM** : ⏸ **À confirmer post-deploy**. Task 6.3 (Docker + vegeta) pas exécutable depuis le worktree de dev. Mesure attendue : `docker stats --no-stream` après `docker compose up -d crawler-monitor-backend-go` + 60s de settling.

## Synthèse motivations

| # | Motivation | Cible | Mesuré | Atteint ? |
|---|---|---|---|---|
| 1 | Throughput parsing queue | ≥ 5× Node | 10k = 2.97s ; ratio Node TBD | ⏸ |
| 2 | Concurrence WS p99 | ≤ 100 ms | **1.97 ms (50× sous cible)** | ✅ |
| 3 | RAM idle | ≤ 50 MB | TBD post-deploy | ⏸ |

**Recommandation** :
- Go for `cutover` côté motivation 2 (concurrence WS) — démonstration claire et chiffrée.
- Bloquer `cutover` final tant que motivations 1 et 3 ne sont pas confirmées (mesure Node + mesure RAM prod).
- Acceptable de procéder en shadow run (Task 7.2) avec les chiffres Go connus, et compléter le tableau au moment du cutover.

## Comment reproduire

```bash
cd apps-microservices/crawler-monitor-backend

# Bench queue.Analyze (10k)
go test -bench=BenchmarkQueueAnalyze_10k -benchmem -benchtime=1x ./tests/benchmarks/

# Bench queue.Analyze (100k) — long run
go test -bench=BenchmarkQueueAnalyze_100k -benchmem -benchtime=1x -timeout=10m ./tests/benchmarks/

# Bench WS broadcast
go test -v -run TestWSBroadcastP99 -timeout 60s ./tests/benchmarks/

# RAM (Docker requis, en prod ou local)
docker compose up -d crawler-monitor-backend-go
sleep 60
docker stats --no-stream crawler-monitor-backend-go
# Sous charge
TOKEN=$(curl -s -X POST http://localhost:3002/api/login -d '{"password":"<admin>"}' -H "Content-Type: application/json" | jq -r .token)
echo "GET http://localhost:3002/api/jobs
Authorization: Bearer $TOKEN" | vegeta attack -duration=5m -rate=50 | vegeta report
```
