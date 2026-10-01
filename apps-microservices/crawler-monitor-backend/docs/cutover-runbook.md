# Cutover Runbook — crawler-monitor-backend Go

Document de référence pour la bascule production Express → Go (Phase 7) et les opérations de rollback.

## Cutover (passage Express → Go)

Le HEAD de `features/crawler-monitor-backend-go` modifie `docker-compose.yml` pour activer le service Go en lieu et place de l'Express :
- Service unique `crawler-monitor-backend` (Go) sur profile `app` (au lieu de `disabled`)
- Build vers `Dockerfile` (Go), `Dockerfile.express` préservé pour rollback
- Healthcheck via `./server healthcheck` (sous-commande)
- Variables d'env Go : `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `PORT`, `LOG_LEVEL`, `CORS_ALLOWED_ORIGINS`, `IMAGE_DOWNLOAD_SERVICE_URL`

Procédure (sur la VM GCP, après push de la branche) :

```bash
cd /opt/<repo-path>
git fetch
git checkout features/crawler-monitor-backend-go

# Cutover en 2 commandes
docker compose stop crawler-monitor-backend  # arrête l'Express si encore actif
docker compose --profile app up -d --build crawler-monitor-backend

# Vérifier
docker compose ps crawler-monitor-backend
# Doit afficher Up X seconds (healthy)

# Smoke test contractuel (snapshots Node préalablement capturés)
ADMIN_PWD=<le mot de passe admin>
bash apps-microservices/crawler-monitor-backend/tests/contract_smoke.sh http://localhost:3001 "$ADMIN_PWD"
```

## Shadow run (avant cutover, optionnel)

Pour faire tourner le Go en parallèle de l'Express **sans** modifier `docker-compose.yml` :

```bash
# Build l'image Go localement
cd /opt/<repo-path>
docker build -t cmb-go apps-microservices/crawler-monitor-backend

# Lancer en parallèle sur le port 3002 (Express reste sur 3001)
docker run -d --name cmb-go-shadow \
  --network <reseau-services-net> \
  -p 3002:3001 \
  -e REDIS_URL="$REDIS_URL" \
  -e JWT_SECRET="$JWT_SECRET" \
  -e ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH" \
  -e CRAWLER_STORAGE_PATH=/app/storage \
  -v <vol_crawler_data>:/app/storage \
  cmb-go

# Smoke test sur le shadow
bash apps-microservices/crawler-monitor-backend/tests/contract_smoke.sh http://localhost:3002 "$ADMIN_PWD"

# Watch 24h (logs + RAM)
docker logs -f cmb-go-shadow
docker stats cmb-go-shadow
```

Au bout de 24h sans incident → procéder au cutover ci-dessus.

## Rollback (post-cutover)

Si une régression est détectée après la bascule sur la version Go, revenir à l'image Node taguée `last-express` :

```bash
docker compose stop crawler-monitor-backend
docker run -d --name crawler-monitor-backend \
  -p 3001:3001 \
  -e REDIS_URL="$REDIS_URL" \
  -e JWT_SECRET="$JWT_SECRET" \
  -e ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH" \
  -e CRAWLER_STORAGE_PATH=/app/storage \
  -v crawler_storage:/app/storage \
  gcr.io/<PROJECT>/crawler-monitor-backend:last-express
```

Le tag `last-express` est créé en Phase 0 / Task 0.2 avant le cutover.

## Rebuild from Dockerfile.express (last resort)

Si l'image `last-express` n'est plus disponible dans le registry :

```bash
cd apps-microservices/crawler-monitor-backend
docker build -f Dockerfile.express -t crawler-monitor-backend:emergency .
```

`Dockerfile.express` est conservé sur la branche jusqu'à la fin de la Phase 7 watch (24h post-cutover stable). Supprimé en Task 7.4.

## Endpoints non portés

(À compléter en Task 4.10 selon résultat de la vérification d'usage de `imageDownloadProxy` côté frontend.)