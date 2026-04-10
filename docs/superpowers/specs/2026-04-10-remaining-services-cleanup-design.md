# Remaining Services Cleanup (Phase 3) — 2026-04-10

## Context

Phase 1 archived 5 dead/superseded services. Phase 2 archived 6 dormant services. Phase 3 addresses the last 3 non-running services selected for cleanup from the original 20 identified.

## Scope

### Services to archive and remove

| # | Directory | Profile | Reason | docker-compose entries |
|---|-----------|---------|--------|------------------------|
| 1 | `apps-microservices/graph-rag-question-processor` | `graph-rag` | Not running, zero external refs, last real activity 16 days ago | `graph-rag-question-processor` (lines 1554-1568) |
| 2 | `apps-microservices/graph-rag-reponse-processor` | `graph-rag` | Not running, zero external refs, last real activity 16 days ago | `graph-rag-reponse-processor` (lines 1570-1584) |
| 3 | `apps-microservices/crawler-service-python` | Not in compose | Standalone Python crawler, not deployed, last commit 9 days ago | None |

No CI/CD workflow files exist for these 3 services.

### Not included in this phase

The remaining 6 services from the original 20 are kept for specific reasons:
- `mcp-gateway-frontend` — active development (commits yesterday)
- `product-database-qdrant-service` — active development (commits yesterday, Prometheus active)
- `redis-client-frontend` — maintained admin tool
- `api-chatbot-html-service` — to be reviewed separately
- `api-question-caracteristique` — to be reviewed separately
- `api-recherche` — build context for the running `api-recherche-service`

## Approach

**Approach A + timestamped branch** (same as Phase 1 & 2).

### Step 1 — Create archive branch

Create branch `archive/dead-services-2026-04-10` from current `features/poc`.

### Step 2 — Remove on `features/poc`

In a single commit:

1. Delete 3 directories:
   - `apps-microservices/graph-rag-question-processor/`
   - `apps-microservices/graph-rag-reponse-processor/`
   - `apps-microservices/crawler-service-python/`

2. Remove from `docker-compose.yml`:
   - `graph-rag-question-processor` block (lines 1554-1568)
   - `graph-rag-reponse-processor` block (lines 1570-1584)
   - Both blocks are adjacent

### Step 3 — Commit

```
chore: archive 3 remaining non-running services to archive/dead-services-2026-04-10
```

## Verification

- `docker compose config` must pass
- No remaining references to the 3 services in docker-compose.yml
- Archive branch preserves all files for recovery

## Recovery procedure

```bash
git branch --list 'archive/*'
git checkout archive/dead-services-2026-04-10 -- apps-microservices/crawler-service-python/
```

## Convention

Same as Phase 1 & 2 — see `2026-04-09-dead-services-cleanup-design.md`.