# Dead Services Cleanup — 2026-04-09

## Context

The RAG-HP-PUB monorepo contains 97 service directories in `apps-microservices/`. A cross-reference of the codebase against `docker compose ps` output revealed 20 services not running. Of those, 5 are clearly dead, superseded, or test-only — confirmed by CLAUDE.md docs, naming conventions (`-bkp`, `-v2`, `-testing`), and absence of references from any running service or CI/CD workflow.

## Scope

### Services to archive and remove

| # | Directory | Reason | docker-compose entries |
|---|-----------|--------|------------------------|
| 1 | `apps-microservices/api-rest-milvus-bkp` | Superseded by `api-rest-milvus` (CLAUDE.md confirms) | None |
| 2 | `apps-microservices/database-service` | Superseded by `product-database-qdrant-service` (CLAUDE.md confirms) | None |
| 3 | `apps-microservices/extractor-testing-service` | Test/experiment tool for extraction libraries | None |
| 4 | `apps-microservices/api-classification-v2` | Test variant of `api-classification` with compare scripts | `api-classification-v2-service`, `api-classification-v2-lb` |
| 5 | `apps-microservices/stat-pj-service` | Batch script (no Dockerfile, no docker-compose) | None |

### Out of scope

- 11 dormant services (defined in docker-compose but not running)
- 4 recently-active services (not in docker-compose but with recent commits)
- Infrastructure services (elasticsearch, grafana, etc.)
- `libs/`, `tools/`, `protos/`, `model-optimizer/`

## Approach

**Approach A + timestamped archive branches.**

### Step 1 — Create archive branch

Create branch `archive/dead-services-2026-04-09` from current `features/poc`. This preserves the full repo state including all 5 services with their build context.

### Step 2 — Remove on `features/poc`

In a single commit on `features/poc`:

1. Delete 5 directories:
   - `apps-microservices/api-rest-milvus-bkp/`
   - `apps-microservices/database-service/`
   - `apps-microservices/extractor-testing-service/`
   - `apps-microservices/api-classification-v2/`
   - `apps-microservices/stat-pj-service/`

2. Remove from `docker-compose.yml`:
   - `api-classification-v2-service` block (service definition + environment + depends_on + networks)
   - `api-classification-v2-lb` block (nginx load balancer)

### Step 3 — Commit

```
chore: archive 5 dead/superseded services to archive/dead-services-2026-04-09
```

## Verification

- `docker compose config` must pass after the docker-compose.yml edit (no broken references)
- No other service in docker-compose.yml references `api-classification-v2-service` or `api-classification-v2-lb`
- No CI/CD workflow references any of the 5 services (already verified: none found)

## Recovery procedure

```bash
# List all archive branches
git branch --list 'archive/*'

# Restore a single service
git checkout archive/dead-services-2026-04-09 -- apps-microservices/database-service/

# Restore the docker-compose entries (manual — extract from the branch's docker-compose.yml)
git show archive/dead-services-2026-04-09:docker-compose.yml | grep -A 50 'api-classification-v2'
```

## Convention for future cleanups

- **Branch naming:** `archive/dead-services-YYYY-MM-DD` (append `-b`, `-c` suffix on same-day collisions)
- **Process:** Always create the archive branch before deleting on the working branch
- **Commit message:** Reference the archive branch name so the cleanup is traceable
- **Scope:** Only archive services confirmed dead/superseded — dormant or in-development services stay