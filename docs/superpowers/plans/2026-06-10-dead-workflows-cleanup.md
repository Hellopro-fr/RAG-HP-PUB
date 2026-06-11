# Dead Workflows Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete 28 dead-service GitHub Actions workflows from `.github/workflows/`, protected by a snapshot backup branch `archive/dead-services-2026-06-10`.

**Architecture:** Pure git operation, no code changes. Snapshot branch at current `features/poc` HEAD preserves all 35 workflow files; a single atomic `git rm` commit on `features/poc` then removes the 28 dead ones. User pushes both refs manually afterward.

**Tech Stack:** git (Bash tool). No tests to run — verification is via git/ls commands with expected outputs.

**Spec:** `docs/superpowers/specs/2026-06-10-dead-workflows-cleanup-design.md`

---

## Context for the engineer

- Repository: `D:\DevHellopro\Workspaces\RAG-HP-PUB` (in Bash: `/d/DevHellopro/Workspaces/RAG-HP-PUB`). Current branch: `features/poc`.
- Backup convention: three prior branches exist (`archive/dead-services-2026-04-09`, `-04-09-b`, `-04-10`). Each is a pure snapshot of `features/poc` HEAD taken just before a deletion commit — no commits of its own.
- The 9 dead services (api-ingestion, devis-processor, di-database-qdrant, echange-database-qdrant, echange-processor, embedding, webhook, website-database-qdrant, website-processor) each have 3 workflow generations; their directories stay in `apps-microservices/` — this plan touches ONLY `.github/workflows/`.
- Untracked noise (`bash.exe.stackdump`, `requirements.txt`, `.claude/scheduled_tasks.lock` deletion) must NOT be staged.
- Commit messages: bilingual EN+FR (user already chose "both"). Multi-line commit messages go through a temp file + `git commit --file=` — heredocs with `-f`/`force` tokens trip the PreToolUse force-push blocker.
- Do NOT push — the user pushes both refs himself.

---

### Task 1: Create snapshot backup branch

**Goal:** `archive/dead-services-2026-06-10` exists, pointing at the current `features/poc` HEAD, with all 35 workflow files reachable from it.

**Files:**
- None modified (branch ref only).

**Acceptance Criteria:**
- [ ] Working tree clean apart from known untracked noise; current branch is `features/poc`
- [ ] Branch `archive/dead-services-2026-06-10` exists and points at the same commit as `features/poc`
- [ ] `git ls-tree` of the branch shows all 35 files under `.github/workflows/`

**Verify:** `git rev-parse archive/dead-services-2026-06-10 features/poc` → two identical SHAs; `git ls-tree --name-only archive/dead-services-2026-06-10 -- .github/workflows/ | wc -l` → `35`

**Steps:**

- [ ] **Step 1: Preconditions — clean tree, right branch**

```bash
cd /d/DevHellopro/Workspaces/RAG-HP-PUB
git branch --show-current
git status --porcelain
```

Expected: `features/poc`; status shows only untracked noise (`?? bash.exe.stackdump`, `?? requirements.txt`) and possibly ` D .claude/scheduled_tasks.lock` — NO staged entries, NO modifications under `.github/`. If anything else appears, STOP and report.

- [ ] **Step 2: Create the snapshot branch (no checkout)**

```bash
git branch archive/dead-services-2026-06-10
```

Expected: no output, exit 0. If "branch already exists", STOP and report (a prior partial run — verify its SHA before reusing).

- [ ] **Step 3: Verify snapshot**

```bash
git rev-parse archive/dead-services-2026-06-10 features/poc
git ls-tree --name-only archive/dead-services-2026-06-10 -- .github/workflows/ | wc -l
```

Expected: first command prints the SAME SHA twice; second prints `35`.

No commit in this task — a branch ref is not a commit. Proceed to Task 2.

---

### Task 2: Delete the 28 dead workflows, commit, verify

**Goal:** Single commit on `features/poc` removing exactly the 28 dead workflow files; 7 files remain in `.github/workflows/`.

**Files:**
- Delete (28, all under `.github/workflows/`):
  - `cd_build_push_services_api_ingestion.yml`
  - `cd_build_push_services_devis_processor.yml`
  - `cd_build_push_services_di_database_qdrant.yml`
  - `cd_build_push_services_echange_database_qdrant.yml`
  - `cd_build_push_services_echange_processor.yml`
  - `cd_build_push_services_embedding.yml`
  - `cd_build_push_services_webhook.yml`
  - `cd_build_push_services_website_database_qdrant.yml`
  - `cd_build_push_services_website_processor.yml`
  - `ci_services_api_ingestion.yml`
  - `ci_services_devis_processor.yml`
  - `ci_services_di_database_qdrant.yml`
  - `ci_services_echange_database_qdrant.yml`
  - `ci_services_echange_processor.yml`
  - `ci_services_embedding.yml`
  - `ci_services_webhook.yml`
  - `ci_services_website_database_qdrant.yml`
  - `ci_services_website_processor.yml`
  - `service-api-ingestion-pipeline.yml`
  - `service-devis-processor-pipeline.yml`
  - `service-di-database-qdrant-pipeline.yml`
  - `service-echange-database-qdrant-pipeline.yml`
  - `service-echange-processor-pipeline.yml`
  - `service-embedding-pipeline.yml`
  - `service-webhook-pipeline.yml`
  - `service-website-database-qdrant-pipeline.yml`
  - `service-website-processor-pipeline.yml`
  - `test-embedding-service.yaml` (note: `.yaml`, not `.yml`)
- Keep (7, must still exist after): `cd_build_push_api_catalog.yml`, `ci_services_api_catalog.yml`, `ci_account_service_backend.yml`, `ci_account_service_frontend.yml`, `ci_services_crawler.yml`, `graphify-auto-rebuild.yml`, `graphify-coverage-check.yml`

**Acceptance Criteria:**
- [ ] Deletion commit on `features/poc` touches exactly 28 files, all deletions, all under `.github/workflows/`
- [ ] `.github/workflows/` contains exactly the 7 kept files
- [ ] Working tree clean after commit (apart from known untracked noise)
- [ ] Commit message is bilingual EN+FR conventional commit

**Verify:** `ls -1 .github/workflows | wc -l` → `7`; `git show --stat HEAD | grep -c '\.github/workflows/'` → `28`

**Steps:**

- [ ] **Step 1: git rm the 28 files**

```bash
cd /d/DevHellopro/Workspaces/RAG-HP-PUB
git rm \
  .github/workflows/cd_build_push_services_api_ingestion.yml \
  .github/workflows/cd_build_push_services_devis_processor.yml \
  .github/workflows/cd_build_push_services_di_database_qdrant.yml \
  .github/workflows/cd_build_push_services_echange_database_qdrant.yml \
  .github/workflows/cd_build_push_services_echange_processor.yml \
  .github/workflows/cd_build_push_services_embedding.yml \
  .github/workflows/cd_build_push_services_webhook.yml \
  .github/workflows/cd_build_push_services_website_database_qdrant.yml \
  .github/workflows/cd_build_push_services_website_processor.yml \
  .github/workflows/ci_services_api_ingestion.yml \
  .github/workflows/ci_services_devis_processor.yml \
  .github/workflows/ci_services_di_database_qdrant.yml \
  .github/workflows/ci_services_echange_database_qdrant.yml \
  .github/workflows/ci_services_echange_processor.yml \
  .github/workflows/ci_services_embedding.yml \
  .github/workflows/ci_services_webhook.yml \
  .github/workflows/ci_services_website_database_qdrant.yml \
  .github/workflows/ci_services_website_processor.yml \
  .github/workflows/service-api-ingestion-pipeline.yml \
  .github/workflows/service-devis-processor-pipeline.yml \
  .github/workflows/service-di-database-qdrant-pipeline.yml \
  .github/workflows/service-echange-database-qdrant-pipeline.yml \
  .github/workflows/service-echange-processor-pipeline.yml \
  .github/workflows/service-embedding-pipeline.yml \
  .github/workflows/service-webhook-pipeline.yml \
  .github/workflows/service-website-database-qdrant-pipeline.yml \
  .github/workflows/service-website-processor-pipeline.yml \
  .github/workflows/test-embedding-service.yaml
```

Expected: 28 lines of `rm '.github/workflows/...'`, exit 0. Any "did not match any files" → STOP, filename typo.

- [ ] **Step 2: Pre-commit check — exactly 28 staged deletions, nothing else**

```bash
git diff --cached --name-status | sort
git diff --cached --name-status | wc -l
ls -1 .github/workflows
```

Expected: 28 lines all starting `D\t.github/workflows/`; count `28`; `ls` shows exactly the 7 kept files:
```
cd_build_push_api_catalog.yml
ci_account_service_backend.yml
ci_account_service_frontend.yml
ci_services_api_catalog.yml
ci_services_crawler.yml
graphify-auto-rebuild.yml
graphify-coverage-check.yml
```

- [ ] **Step 3: Write commit message to temp file** (Write tool, path `D:\DevHellopro\Workspaces\RAG-HP-PUB\.git-commit-msg-tmp.txt`)

```text
chore(ci): remove 28 dead-service workflows from .github/workflows

EN: Delete the CI/CD/pipeline workflows of the 9 retired services
(api-ingestion, devis-processor, di-database-qdrant,
echange-database-qdrant, echange-processor, embedding, webhook,
website-database-qdrant, website-processor) plus the orphan
test-embedding-service.yaml. All 35 files remain reachable on the
snapshot branch archive/dead-services-2026-06-10. The 7 workflows of
active services (api-catalog CI+CD, account-service backend+frontend,
crawler, graphify x2) are kept. Service directories are untouched.

FR: Suppression des workflows CI/CD/pipeline des 9 services retirés
(api-ingestion, devis-processor, di-database-qdrant,
echange-database-qdrant, echange-processor, embedding, webhook,
website-database-qdrant, website-processor) ainsi que de l'orphelin
test-embedding-service.yaml. Les 35 fichiers restent accessibles sur la
branche de sauvegarde archive/dead-services-2026-06-10. Les 7 workflows
des services actifs (api-catalog CI+CD, account-service
backend+frontend, crawler, graphify x2) sont conservés. Les répertoires
des services ne sont pas modifiés.

Spec: docs/superpowers/specs/2026-06-10-dead-workflows-cleanup-design.md
```

- [ ] **Step 4: Commit and clean up temp file**

```bash
git commit --file=.git-commit-msg-tmp.txt
rm .git-commit-msg-tmp.txt
```

Expected: `[features/poc <sha>] chore(ci): remove 28 dead-service workflows...`, `28 files changed, ... deletions(-)`.

- [ ] **Step 5: Post-commit verification**

```bash
git show --stat HEAD | tail -3
ls -1 .github/workflows | wc -l
git ls-tree --name-only archive/dead-services-2026-06-10 -- .github/workflows/ | wc -l
git status --porcelain
```

Expected: stat line `28 files changed` with only deletions; `7`; `35` (snapshot untouched); status shows only the pre-existing untracked noise.

---

## Handoff to user (not part of agent execution)

1. Push both refs:
```bash
git push origin archive/dead-services-2026-06-10 features/poc
```
2. Check branch protection required status checks — if any deleted CI workflow is listed as required, remove it (Settings → Branches, or `gh api repos/Hellopro-fr/RAG-HP-PUB/branches/main/protection`).

**Restore paths:** single file → `git checkout archive/dead-services-2026-06-10 -- .github/workflows/<file>`; full rollback → `git revert <deletion-commit-sha>`.
