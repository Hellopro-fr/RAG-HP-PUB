# Dormant Services Cleanup (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive 6 dormant services + 12 CI/CD workflows to a timestamped branch and remove them from the working branch.

**Architecture:** Create archive branch from current `features/poc`, then delete directories, workflow files, and docker-compose entries in a single commit.

**Tech Stack:** Git (branching), docker-compose (YAML editing)

**Spec:** `docs/superpowers/specs/2026-04-09-dormant-services-cleanup-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Delete directory | `apps-microservices/categories-processor-service/` | Dormant categories HTML processor |
| Delete directory | `apps-microservices/fournisseurs-processor-service/` | Dormant suppliers HTML processor |
| Delete directory | `apps-microservices/ocr-service/` | Superseded by deepseek-ocr |
| Delete directory | `apps-microservices/categories-database-qdrant-service/` | Dormant categories vector DB writer |
| Delete directory | `apps-microservices/fournisseurs-database-qdrant-service/` | Dormant suppliers vector DB writer |
| Delete directory | `apps-microservices/api-check-doublon-produit/` | Not running, zero references |
| Delete file | `.github/workflows/ci_services_categories_processor.yml` | CI for categories-processor |
| Delete file | `.github/workflows/cd_build_push_services_categories_processor.yml` | CD for categories-processor |
| Delete file | `.github/workflows/service-categories-processor-pipeline.yml` | Pipeline for categories-processor |
| Delete file | `.github/workflows/ci_services_fournisseurs_processor.yml` | CI for fournisseurs-processor |
| Delete file | `.github/workflows/cd_build_push_services_fournisseurs_processor.yml` | CD for fournisseurs-processor |
| Delete file | `.github/workflows/service-fournisseurs-processor-pipeline.yml` | Pipeline for fournisseurs-processor |
| Delete file | `.github/workflows/ci_services_categories_database_qdrant.yml` | CI for categories-database-qdrant |
| Delete file | `.github/workflows/cd_build_push_services_categories_database_qdrant.yml` | CD for categories-database-qdrant |
| Delete file | `.github/workflows/service-categories-database-qdrant-pipeline.yml` | Pipeline for categories-database-qdrant |
| Delete file | `.github/workflows/ci_services_fournisseurs_database_qdrant.yml` | CI for fournisseurs-database-qdrant |
| Delete file | `.github/workflows/cd_build_push_services_fournisseurs_database_qdrant.yml` | CD for fournisseurs-database-qdrant |
| Delete file | `.github/workflows/service-fournisseurs-database-qdrant-pipeline.yml` | Pipeline for fournisseurs-database-qdrant |
| Modify | `docker-compose.yml` | Remove 6 service blocks + 1 commented depends_on |

---

### Task 1: Create the archive branch

- [ ] **Step 1: Verify clean working tree**

```bash
git status
```

Expected: On branch `features/poc`. Working tree clean or only unrelated untracked files.

- [ ] **Step 2: Create the archive branch**

```bash
git branch archive/dead-services-2026-04-09-b features/poc
```

Expected: Branch created silently. Stay on `features/poc`.

- [ ] **Step 3: Verify the archive branch exists**

```bash
git branch --list 'archive/*'
```

Expected:
```
  archive/dead-services-2026-04-09
  archive/dead-services-2026-04-09-b
```

---

### Task 2: Delete the 6 service directories

- [ ] **Step 1: Remove the 6 directories from git tracking**

```bash
git rm -r \
  apps-microservices/categories-processor-service/ \
  apps-microservices/fournisseurs-processor-service/ \
  apps-microservices/ocr-service/ \
  apps-microservices/categories-database-qdrant-service/ \
  apps-microservices/fournisseurs-database-qdrant-service/ \
  apps-microservices/api-check-doublon-produit/
```

Expected: Git lists all deleted files. Each line starts with `rm '...'`.

- [ ] **Step 2: Remove any leftover untracked files (e.g., .venv, node_modules)**

```bash
for dir in categories-processor-service fournisseurs-processor-service ocr-service categories-database-qdrant-service fournisseurs-database-qdrant-service api-check-doublon-produit; do
  rm -rf "apps-microservices/$dir" 2>/dev/null
done
```

- [ ] **Step 3: Verify all 6 directories are gone**

```bash
ls -d \
  apps-microservices/categories-processor-service \
  apps-microservices/fournisseurs-processor-service \
  apps-microservices/ocr-service \
  apps-microservices/categories-database-qdrant-service \
  apps-microservices/fournisseurs-database-qdrant-service \
  apps-microservices/api-check-doublon-produit 2>&1
```

Expected: All 6 report "No such file or directory".

---

### Task 3: Delete the 12 CI/CD workflow files

- [ ] **Step 1: Remove the 12 workflow files from git tracking**

```bash
git rm \
  .github/workflows/ci_services_categories_processor.yml \
  .github/workflows/cd_build_push_services_categories_processor.yml \
  .github/workflows/service-categories-processor-pipeline.yml \
  .github/workflows/ci_services_fournisseurs_processor.yml \
  .github/workflows/cd_build_push_services_fournisseurs_processor.yml \
  .github/workflows/service-fournisseurs-processor-pipeline.yml \
  .github/workflows/ci_services_categories_database_qdrant.yml \
  .github/workflows/cd_build_push_services_categories_database_qdrant.yml \
  .github/workflows/service-categories-database-qdrant-pipeline.yml \
  .github/workflows/ci_services_fournisseurs_database_qdrant.yml \
  .github/workflows/cd_build_push_services_fournisseurs_database_qdrant.yml \
  .github/workflows/service-fournisseurs-database-qdrant-pipeline.yml
```

Expected: 12 `rm '...'` lines.

- [ ] **Step 2: Verify no remaining workflows for these services**

```bash
grep -rl "categories-processor\|fournisseurs-processor\|categories-database-qdrant\|fournisseurs-database-qdrant" .github/workflows/ 2>/dev/null || echo "Clean — no matches"
```

Expected: `Clean — no matches`

---

### Task 4: Remove docker-compose entries

Six service blocks and one commented-out reference to remove. Work from **bottom to top** to preserve line numbers for earlier edits.

- [ ] **Step 1: Remove `api-check-doublon-produit` block (lines 1134-1145)**

In `docker-compose.yml`, remove from `  api-check-doublon-produit:` through `    logging: *logging_defaults` and the trailing blank line. The result should connect:

```yaml
    logging: *logging_defaults

  optimize-service:
```

- [ ] **Step 2: Remove `fournisseurs-database-qdrant-service` block (lines 1059-1070)**

Remove from `  fournisseurs-database-qdrant-service:` through `    logging: *logging_defaults` and the trailing blank line. The result should connect:

```yaml
    logging: *logging_defaults

  document-database-qdrant-service:
```

- [ ] **Step 3: Remove `categories-database-qdrant-service` block (lines 1046-1057)**

Remove from `  categories-database-qdrant-service:` through `    logging: *logging_defaults` and the trailing blank line. The result should connect:

```yaml
    logging: *logging_defaults

  document-database-qdrant-service:
```

(After Step 2, `document-database-qdrant-service` is now the next block.)

- [ ] **Step 4: Remove commented-out `depends_on: ocr-service` (lines 867-868)**

In the `document-echange-processor-service` block, remove:
```yaml
    # depends_on:
    #   - ocr-service
```

The result should connect:
```yaml
      - services-net
    deploy:
```

- [ ] **Step 5: Remove `ocr-service` block (lines 792-813)**

Remove from `  ocr-service:` through `    logging: *logging_defaults` and the trailing blank line. The result should connect:

```yaml
    logging: *logging_defaults

  deepseek-ocr:
```

- [ ] **Step 6: Remove `fournisseurs-processor-service` block (lines 779-790)**

Remove from `  fournisseurs-processor-service:` through `    logging: *logging_defaults` and the trailing blank line. The result should connect:

```yaml
    logging: *logging_defaults

  ocr-service:
```

Wait — after Step 5, `ocr-service` is already removed. So this should connect to:

```yaml
    logging: *logging_defaults

  deepseek-ocr:
```

- [ ] **Step 7: Remove `categories-processor-service` block (lines 766-777)**

Remove from `  categories-processor-service:` through `    logging: *logging_defaults` and the trailing blank line. The result should connect:

```yaml
    logging: *logging_defaults

  deepseek-ocr:
```

- [ ] **Step 8: Verify no dangling references**

```bash
grep -n "categories-processor-service\|fournisseurs-processor-service\|categories-database-qdrant-service\|fournisseurs-database-qdrant-service\|api-check-doublon-produit" docker-compose.yml
```

Expected: No output.

```bash
grep -n "ocr-service" docker-compose.yml
```

Expected: Only matches for `nettoyage-bruit-ocr-service` and `deepseek_ocr-service` (the `URL_OCR` env var). No standalone `ocr-service` references.

---

### Task 5: Validate docker-compose

- [ ] **Step 1: Run docker compose config**

```bash
docker compose config --quiet
```

Expected: Exit code 0, no output.

- [ ] **Step 2: Verify no references to deleted service directories**

```bash
grep -n "categories-processor-service/\|fournisseurs-processor-service/\|ocr-service/Dockerfile\|categories-database-qdrant-service/\|fournisseurs-database-qdrant-service/\|api-check-doublon-produit/" docker-compose.yml
```

Expected: No output.

---

### Task 6: Commit

- [ ] **Step 1: Stage docker-compose.yml**

```bash
git add docker-compose.yml
```

(Directory and workflow deletions from `git rm` are already staged.)

- [ ] **Step 2: Review staged changes**

```bash
git diff --cached --stat | tail -5
```

Expected: Shows deleted files from 6 directories + 12 workflows + `docker-compose.yml` modified.

- [ ] **Step 3: Create the commit (bilingual EN/FR)**

```bash
git commit -m "$(cat <<'EOF'
chore: archive 6 dormant services to archive/dead-services-2026-04-09-b

Remove directories, docker-compose entries, and CI/CD workflows for dormant services:
- categories-processor-service (disabled profile)
- fournisseurs-processor-service (disabled profile)
- ocr-service (superseded by deepseek-ocr)
- categories-database-qdrant-service (disabled profile)
- fournisseurs-database-qdrant-service (disabled profile)
- api-check-doublon-produit (not running, zero references)

Also removes 12 associated CI/CD workflow files and a stale
commented-out depends_on reference to ocr-service.

Archive branch preserves full repo state for recovery.

---

chore : archiver 6 services dormants vers archive/dead-services-2026-04-09-b

Suppression des répertoires, entrées docker-compose et workflows CI/CD
des services dormants :
- categories-processor-service (profil disabled)
- fournisseurs-processor-service (profil disabled)
- ocr-service (remplacé par deepseek-ocr)
- categories-database-qdrant-service (profil disabled)
- fournisseurs-database-qdrant-service (profil disabled)
- api-check-doublon-produit (non actif, aucune référence)

Supprime aussi 12 fichiers de workflow CI/CD associés et une référence
depends_on commentée vers ocr-service.

La branche d'archive conserve l'état complet du dépôt pour récupération.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify the commit**

```bash
git log -1 --stat | tail -5
```

---

### Task 7: Final verification

- [ ] **Step 1: Verify archive branch contains the deleted services**

```bash
git ls-tree --name-only archive/dead-services-2026-04-09-b apps-microservices/ | grep -E "categories-processor|fournisseurs-processor|ocr-service|categories-database-qdrant|fournisseurs-database-qdrant|api-check-doublon-produit"
```

Expected: All 6 directories listed.

- [ ] **Step 2: Verify archive branch contains the deleted workflows**

```bash
git ls-tree --name-only archive/dead-services-2026-04-09-b .github/workflows/ | grep -E "categories_processor|fournisseurs_processor|categories_database_qdrant|fournisseurs_database_qdrant"
```

Expected: 12 workflow files listed.

- [ ] **Step 3: Verify working branch no longer has them**

```bash
ls -d \
  apps-microservices/categories-processor-service \
  apps-microservices/fournisseurs-processor-service \
  apps-microservices/ocr-service \
  apps-microservices/categories-database-qdrant-service \
  apps-microservices/fournisseurs-database-qdrant-service \
  apps-microservices/api-check-doublon-produit 2>&1
```

Expected: All 6 report "No such file or directory".

- [ ] **Step 4: Verify recovery works**

```bash
git show archive/dead-services-2026-04-09-b:apps-microservices/ocr-service/Dockerfile > /dev/null 2>&1 && echo "Recovery OK" || echo "Recovery FAILED"
```

Expected: `Recovery OK`