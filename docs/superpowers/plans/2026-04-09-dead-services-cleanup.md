# Dead Services Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive 5 dead/superseded services to a timestamped branch and remove them from the working branch.

**Architecture:** Create an archive branch from the current state of `features/poc`, then delete the 5 service directories and their docker-compose entries on `features/poc` in a single commit.

**Tech Stack:** Git (branching), docker-compose (YAML editing)

**Spec:** `docs/superpowers/specs/2026-04-09-dead-services-cleanup-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Delete directory | `apps-microservices/api-rest-milvus-bkp/` | Superseded backup of api-rest-milvus |
| Delete directory | `apps-microservices/database-service/` | Superseded by product-database-qdrant-service |
| Delete directory | `apps-microservices/extractor-testing-service/` | Test/experiment tool |
| Delete directory | `apps-microservices/api-classification-v2/` | Test variant of api-classification |
| Delete directory | `apps-microservices/stat-pj-service/` | Batch script, not a service |
| Modify | `docker-compose.yml` (lines 520-564) | Remove `api-classification-v2-service` + `api-classification-v2-lb` blocks |

---

### Task 1: Create the archive branch

- [ ] **Step 1: Verify clean working tree**

```bash
git status
```

Expected: On branch `features/poc`. Working tree should be clean (or only untracked files unrelated to these 5 services). If there are uncommitted changes, commit or stash them first.

- [ ] **Step 2: Create the archive branch**

```bash
git branch archive/dead-services-2026-04-09 features/poc
```

Expected: Branch created silently. No output. Stay on `features/poc` (do NOT checkout the archive branch).

- [ ] **Step 3: Verify the archive branch exists**

```bash
git branch --list 'archive/*'
```

Expected:
```
  archive/dead-services-2026-04-09
```

---

### Task 2: Delete the 5 service directories

- [ ] **Step 1: Remove the 5 directories from git tracking**

```bash
git rm -r apps-microservices/api-rest-milvus-bkp/ apps-microservices/database-service/ apps-microservices/extractor-testing-service/ apps-microservices/api-classification-v2/ apps-microservices/stat-pj-service/
```

Expected: Git lists all deleted files (may be hundreds of lines). Each line starts with `rm '...'`.

- [ ] **Step 2: Verify the directories are gone**

```bash
ls -d apps-microservices/api-rest-milvus-bkp apps-microservices/database-service apps-microservices/extractor-testing-service apps-microservices/api-classification-v2 apps-microservices/stat-pj-service 2>&1
```

Expected: All 5 should report "No such file or directory".

---

### Task 3: Remove docker-compose entries for api-classification-v2

- [ ] **Step 1: Remove `api-classification-v2-service` and `api-classification-v2-lb` blocks**

In `docker-compose.yml`, delete lines 520 through 564 (inclusive). This removes:
- The blank line before `api-classification-v2-service:` (line 519 stays — it's the blank line after the previous service's `logging: *logging_defaults`)
- `api-classification-v2-service:` definition (lines 520-549)
- Blank separator (line 550)
- `api-classification-v2-lb:` definition (lines 551-564)

After the edit, line 519 (blank line) should be immediately followed by `api-transcription-service:` (previously line 566).

The result should look like:

```yaml
    logging: *logging_defaults

  api-transcription-service:
    build:
      context: .
      dockerfile: ./apps-microservices/api-transcription-service/Dockerfile
```

- [ ] **Step 2: Verify no dangling references to api-classification-v2**

```bash
grep -n "api-classification-v2" docker-compose.yml
```

Expected: No output (no matches).

---

### Task 4: Validate docker-compose

- [ ] **Step 1: Run docker compose config to validate syntax**

```bash
docker compose config --quiet
```

Expected: Exit code 0, no output. If there's an error, the docker-compose.yml edit broke something — inspect and fix.

- [ ] **Step 2: Verify no remaining references to deleted directories**

```bash
grep -n "api-rest-milvus-bkp\|database-service/\|extractor-testing-service\|api-classification-v2\|stat-pj-service" docker-compose.yml
```

Expected: No output (no matches).

---

### Task 5: Commit

- [ ] **Step 1: Stage the docker-compose.yml change**

```bash
git add docker-compose.yml
```

(The directory deletions from `git rm -r` in Task 2 are already staged.)

- [ ] **Step 2: Review what will be committed**

```bash
git diff --cached --stat
```

Expected: Shows all files from the 5 deleted directories plus `docker-compose.yml` as modified. All deletions, one modification.

- [ ] **Step 3: Create the commit (bilingual EN/FR)**

```bash
git commit -m "$(cat <<'EOF'
chore: archive 5 dead/superseded services to archive/dead-services-2026-04-09

Remove directories and docker-compose entries for services no longer in use:
- api-rest-milvus-bkp (superseded by api-rest-milvus)
- database-service (superseded by product-database-qdrant-service)
- extractor-testing-service (test/experiment tool)
- api-classification-v2 (test variant, includes v2-service + v2-lb in compose)
- stat-pj-service (batch script, not a running service)

Archive branch preserves full repo state for recovery.

---

chore : archiver 5 services obsolètes vers archive/dead-services-2026-04-09

Suppression des répertoires et entrées docker-compose des services hors service :
- api-rest-milvus-bkp (remplacé par api-rest-milvus)
- database-service (remplacé par product-database-qdrant-service)
- extractor-testing-service (outil de test/expérimentation)
- api-classification-v2 (variante de test, inclut v2-service + v2-lb dans compose)
- stat-pj-service (script batch, pas un service actif)

La branche d'archive conserve l'état complet du dépôt pour récupération.
EOF
)"
```

- [ ] **Step 4: Verify the commit**

```bash
git log -1 --stat
```

Expected: Shows the commit with all deleted files and the docker-compose.yml modification.

---

### Task 6: Final verification

- [ ] **Step 1: Verify archive branch still contains the deleted services**

```bash
git ls-tree --name-only archive/dead-services-2026-04-09 apps-microservices/ | grep -E "api-rest-milvus-bkp|database-service|extractor-testing-service|api-classification-v2|stat-pj-service"
```

Expected: All 5 directories listed:
```
apps-microservices/api-classification-v2
apps-microservices/api-rest-milvus-bkp
apps-microservices/database-service
apps-microservices/extractor-testing-service
apps-microservices/stat-pj-service
```

- [ ] **Step 2: Verify working branch no longer has them**

```bash
ls -d apps-microservices/api-rest-milvus-bkp apps-microservices/database-service apps-microservices/extractor-testing-service apps-microservices/api-classification-v2 apps-microservices/stat-pj-service 2>&1
```

Expected: All 5 report "No such file or directory".

- [ ] **Step 3: Verify recovery works (dry run)**

```bash
git show archive/dead-services-2026-04-09:apps-microservices/database-service/main.py > /dev/null 2>&1 && echo "Recovery OK" || echo "Recovery FAILED"
```

Expected: `Recovery OK`