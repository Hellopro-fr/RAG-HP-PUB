# Dormant Services Cleanup (Phase 2) — 2026-04-09

## Context

Phase 1 archived 5 clearly dead/superseded services (see `2026-04-09-dead-services-cleanup-design.md`). Phase 2 targets 6 dormant services: defined in docker-compose.yml but not running, with zero external references from any active service. Additionally, 12 CI/CD workflow files associated with 4 of these services will be archived.

## Scope

### Services to archive and remove

| # | Directory | Profile | Reason | docker-compose entries | CI/CD workflows |
|---|-----------|---------|--------|------------------------|-----------------|
| 1 | `apps-microservices/categories-processor-service` | `disabled` | Dormant categories ingestion pipeline | `categories-processor-service` (lines 766-777) | `ci_services_categories_processor.yml`, `cd_build_push_services_categories_processor.yml`, `service-categories-processor-pipeline.yml` |
| 2 | `apps-microservices/fournisseurs-processor-service` | `disabled` | Dormant suppliers ingestion pipeline | `fournisseurs-processor-service` (lines 779-790) | `ci_services_fournisseurs_processor.yml`, `cd_build_push_services_fournisseurs_processor.yml`, `service-fournisseurs-processor-pipeline.yml` |
| 3 | `apps-microservices/ocr-service` | `app` | Superseded by `deepseek-ocr` (GPU/vLLM) | `ocr-service` (lines 792-813) | None |
| 4 | `apps-microservices/categories-database-qdrant-service` | `disabled` | Dormant categories vector DB writer | `categories-database-qdrant-service` (lines 1046-1057) | `ci_services_categories_database_qdrant.yml`, `cd_build_push_services_categories_database_qdrant.yml`, `service-categories-database-qdrant-pipeline.yml` |
| 5 | `apps-microservices/fournisseurs-database-qdrant-service` | `disabled` | Dormant suppliers vector DB writer | `fournisseurs-database-qdrant-service` (lines 1059-1070) | `ci_services_fournisseurs_database_qdrant.yml`, `cd_build_push_services_fournisseurs_database_qdrant.yml`, `service-fournisseurs-database-qdrant-pipeline.yml` |
| 6 | `apps-microservices/api-check-doublon-produit` | `app` | Not running, zero references | `api-check-doublon-produit` (lines 1134-1145) | None |

### Additional cleanup

- Remove commented-out `depends_on: ocr-service` in `document-echange-processor-service` block (docker-compose.yml lines 867-868)

### Excluded from this phase

- `graph-rag-question-processor` — kept per user decision
- `graph-rag-reponse-processor` — kept per user decision
- `mcp-gateway-frontend` — active development (30+ commits in 2 weeks)
- `product-database-qdrant-service` — active development (commits today)
- `redis-client-frontend` — maintained admin tool

## Approach

**Approach A + timestamped branch** (same as Phase 1).

### Step 1 — Create archive branch

Create branch `archive/dead-services-2026-04-09-b` from current `features/poc`. This is the second archive of the day (suffix `-b` per convention).

### Step 2 — Remove on `features/poc`

In a single commit on `features/poc`:

1. Delete 6 directories:
   - `apps-microservices/categories-processor-service/`
   - `apps-microservices/fournisseurs-processor-service/`
   - `apps-microservices/ocr-service/`
   - `apps-microservices/categories-database-qdrant-service/`
   - `apps-microservices/fournisseurs-database-qdrant-service/`
   - `apps-microservices/api-check-doublon-produit/`

2. Delete 12 CI/CD workflow files:
   - `.github/workflows/ci_services_categories_processor.yml`
   - `.github/workflows/cd_build_push_services_categories_processor.yml`
   - `.github/workflows/service-categories-processor-pipeline.yml`
   - `.github/workflows/ci_services_fournisseurs_processor.yml`
   - `.github/workflows/cd_build_push_services_fournisseurs_processor.yml`
   - `.github/workflows/service-fournisseurs-processor-pipeline.yml`
   - `.github/workflows/ci_services_categories_database_qdrant.yml`
   - `.github/workflows/cd_build_push_services_categories_database_qdrant.yml`
   - `.github/workflows/service-categories-database-qdrant-pipeline.yml`
   - `.github/workflows/ci_services_fournisseurs_database_qdrant.yml`
   - `.github/workflows/cd_build_push_services_fournisseurs_database_qdrant.yml`
   - `.github/workflows/service-fournisseurs-database-qdrant-pipeline.yml`

3. Remove from `docker-compose.yml`:
   - `categories-processor-service` block
   - `fournisseurs-processor-service` block
   - `ocr-service` block
   - `categories-database-qdrant-service` block
   - `fournisseurs-database-qdrant-service` block
   - `api-check-doublon-produit` block
   - Commented-out `depends_on: ocr-service` in `document-echange-processor-service`

### Step 3 — Commit

```
chore: archive 6 dormant services to archive/dead-services-2026-04-09-b
```

## Verification

- `docker compose config` must pass after the docker-compose.yml edits
- No remaining references to the 6 services in docker-compose.yml (except `deepseek-ocr` which replaces `ocr-service` — that stays)
- No remaining CI/CD workflows for the 6 services
- Archive branch preserves all files for recovery

## Recovery procedure

```bash
# List all archive branches
git branch --list 'archive/*'

# Restore a single service
git checkout archive/dead-services-2026-04-09-b -- apps-microservices/ocr-service/

# Restore CI/CD workflows
git checkout archive/dead-services-2026-04-09-b -- .github/workflows/ci_services_categories_processor.yml

# Restore docker-compose entries (manual extraction)
git show archive/dead-services-2026-04-09-b:docker-compose.yml | grep -A 20 'ocr-service:'
```

## Convention

Same as Phase 1 — see `2026-04-09-dead-services-cleanup-design.md` for the full convention.