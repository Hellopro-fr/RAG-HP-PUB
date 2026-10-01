# Dead Workflows Cleanup — Design

**Date:** 2026-06-10
**Branch:** `features/poc`
**Backup branch:** `archive/dead-services-2026-06-10`
**Related specs:** `2026-04-09-dead-services-cleanup-design.md`, `2026-04-09-dormant-services-cleanup-design.md`, `2026-04-10-remaining-services-cleanup-design.md`

## Goal

Remove the GitHub Actions workflows belonging to dead services from `.github/workflows/`, keeping only the workflows for services that are still active. The services themselves stay in `apps-microservices/` — this cleanup targets workflow files only.

## Current State

`.github/workflows/` contains 35 files. The dead workflows reference nine retired services (api-ingestion, devis-processor, di-database-qdrant, echange-database-qdrant, echange-processor, embedding, webhook, website-database-qdrant, website-processor), each with three workflow generations (`ci_services_*`, `cd_build_push_services_*`, `service-*-pipeline`), plus one orphan test workflow.

## Decisions

1. **Keep `ci_services_api_catalog.yml`.** The original keep list omitted it while keeping `cd_build_push_api_catalog.yml`; confirmed as an oversight — both CI and CD for api-catalog stay.
2. **Backup pattern: snapshot branch.** Same as the three prior cleanups: create `archive/dead-services-2026-06-10` pointing at the current `features/poc` HEAD (no checkout, no extra commit), then commit the deletion directly on `features/poc`.
3. **Single deletion commit.** One `git rm` commit removes all 28 files. Atomic; one `git revert` undoes everything; individual files restore from the archive branch.
4. **User pushes.** Both refs (`archive/dead-services-2026-06-10` and `features/poc`) are pushed manually by the user after verification.

## Files Kept (7)

| File | Reason |
|---|---|
| `cd_build_push_api_catalog.yml` | api-catalog active |
| `ci_services_api_catalog.yml` | api-catalog active (added per Decision 1) |
| `ci_account_service_backend.yml` | account-service active |
| `ci_account_service_frontend.yml` | account-service active |
| `ci_services_crawler.yml` | crawler-service active |
| `graphify-auto-rebuild.yml` | graphify infrastructure |
| `graphify-coverage-check.yml` | graphify infrastructure |

## Files Deleted (28)

Nine dead services × three workflow families, plus one orphan:

- `cd_build_push_services_{api_ingestion, devis_processor, di_database_qdrant, echange_database_qdrant, echange_processor, embedding, webhook, website_database_qdrant, website_processor}.yml` (9)
- `ci_services_{api_ingestion, devis_processor, di_database_qdrant, echange_database_qdrant, echange_processor, embedding, webhook, website_database_qdrant, website_processor}.yml` (9)
- `service-{api-ingestion, devis-processor, di-database-qdrant, echange-database-qdrant, echange-processor, embedding, webhook, website-database-qdrant, website-processor}-pipeline.yml` (9)
- `test-embedding-service.yaml` (1)

## Procedure

1. Verify clean working tree on `features/poc` (untracked noise like `bash.exe.stackdump`, `requirements.txt` stays untracked — do not stage).
2. `git branch archive/dead-services-2026-06-10` (snapshot at current HEAD).
3. `git rm` the 28 files listed above.
4. Commit on `features/poc` (bilingual conventional commit; language confirmed with user before committing).
5. Verify (see below).
6. User pushes: `git push origin archive/dead-services-2026-06-10 features/poc`.

## Verification

- `ls .github/workflows` returns exactly the 7 kept files.
- `git ls-tree --name-only archive/dead-services-2026-06-10 -- .github/workflows/` returns all 35 files (snapshot intact).
- `git show --stat HEAD` shows only `.github/workflows/` deletions, 28 files.

## Risks & Follow-ups

- **Branch protection required checks:** if the GitHub repo's protected branches list any deleted CI workflow as a required status check, future PRs will hang on "Expected" checks. Verify repository settings after push (Settings → Branches → required status checks, or `gh api repos/Hellopro-fr/RAG-HP-PUB/branches/main/protection`).
- **Restore paths:** single file — `git checkout archive/dead-services-2026-06-10 -- .github/workflows/<file>`; full rollback — `git revert <deletion-commit>`.
- **Out of scope:** deleting the dead service directories themselves; touching any kept workflow's content.
