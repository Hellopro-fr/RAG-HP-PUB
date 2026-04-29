# Cutover Runbook — crawler-monitor-backend Go

Document de référence pour la bascule production Express → Go (Phase 7) et les opérations de rollback.

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