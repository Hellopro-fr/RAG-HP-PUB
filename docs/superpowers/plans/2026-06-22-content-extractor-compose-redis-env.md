# content-extractor compose Redis env wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the composed `REDIS_URL` and `SERVICE_NAME` env vars to the `content-extractor-api-service` entry in `docker-compose.yml` so its result cache and async job store connect to the real authenticated Redis.

**Architecture:** Single-file, two-line addition to one Compose service's `environment:` block, mirroring the repo-wide convention (`REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}`). No application code, Dockerfile, or cross-service change. Defaults in `config.py` / `Dockerfile` cover every other knob; the deploy-time `.env` (already wired via `env_file: .env`) supplies the `REDIS_*` primitives.

**Tech Stack:** Docker Compose, YAML. (Validation: PyYAML for local parse; `docker compose config` + service smoke for deploy.)

**Spec:** `docs/superpowers/specs/2026-06-22-content-extractor-compose-redis-env-design.md`

---

### Task 0: Add REDIS_URL + SERVICE_NAME to the content-extractor compose entry

**Goal:** The `content-extractor-api-service` `environment:` block carries `SERVICE_NAME` and the composed `REDIS_URL`, and nothing else in the block changes.

**Files:**
- Modify: `docker-compose.yml` (service `content-extractor-api-service`, `environment:` block — currently lines 607-610, immediately before `env_file:` at 611)

**Acceptance Criteria:**
- [ ] `SERVICE_NAME=content-extractor-api-service` present in the block
- [ ] `REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}` present in the block (byte-identical to the other services' line)
- [ ] `PORT`, `LOG_LEVEL`, `MAX_PAYLOAD_SIZE_MB` lines unchanged; `env_file: .env` preserved
- [ ] No change to any other service, app code, or Dockerfile
- [ ] `docker-compose.yml` still parses as valid YAML

**Verify (local):**
```bash
python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('YAML OK')"
git diff docker-compose.yml
```
Expected: `YAML OK`; the diff shows **exactly two added lines** (`SERVICE_NAME` + `REDIS_URL`) inside the `content-extractor-api-service` block and nothing else.

**Verify (deploy — operator, on the VM, per spec §7):**
1. Container startup logs do **NOT** contain `REDIS_URL environment variable not set` (`cache_service.py:89`).
2. `GET /health` → `200`.
3. `POST /clean` same payload twice → 2nd is a cache hit (`extract_cache_hits_total` increments).
4. `POST /clean-async` 1 item → `202 {job_id}` → poll `GET /jobs/{job_id}` → `completed`.

**Steps:**

- [ ] **Step 1: Confirm the current block**

Read `docker-compose.yml` around line 598-620 and confirm the `environment:` block reads exactly:

```yaml
    environment:
      - PORT=8600
      - LOG_LEVEL=info
      - MAX_PAYLOAD_SIZE_MB=10
    env_file:
      - .env
```

If the lines have shifted from 607-610, match on content (the three `environment:` items immediately followed by `env_file:`), not on line numbers.

- [ ] **Step 2: Apply the edit**

Replace:

```yaml
    environment:
      - PORT=8600
      - LOG_LEVEL=info
      - MAX_PAYLOAD_SIZE_MB=10
    env_file:
      - .env
```

with:

```yaml
    environment:
      - PORT=8600
      - LOG_LEVEL=info
      - MAX_PAYLOAD_SIZE_MB=10
      - SERVICE_NAME=content-extractor-api-service
      - REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}
    env_file:
      - .env
```

This `old_string` is unique to the `content-extractor-api-service` block (no other service has `MAX_PAYLOAD_SIZE_MB=10` directly followed by `env_file: .env`). Verify uniqueness before editing; if not unique, include the preceding `container_name`/`ports` lines for disambiguation.

- [ ] **Step 3: Validate YAML + inspect the diff**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('YAML OK')"
git diff docker-compose.yml
```
Expected: `YAML OK`; diff shows exactly the two `+` lines (`SERVICE_NAME`, `REDIS_URL`) within the content-extractor block, zero other changes.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "fix(content-extractor): wire REDIS_URL + SERVICE_NAME in compose" -m "EN: Add the composed REDIS_URL and SERVICE_NAME to the content-extractor-api-service docker-compose entry so the result cache and async job store connect to the authenticated Redis (init_redis_pool reads os.getenv REDIS_URL; previously unset -> redis_client None). Mirrors the repo-wide convention." -m "FR: Ajoute REDIS_URL compose et SERVICE_NAME a l'entree docker-compose de content-extractor-api-service pour que le cache de resultats et le job store async se connectent au Redis authentifie (init_redis_pool lit os.getenv REDIS_URL; auparavant absent -> redis_client None). Conforme a la convention du depot."
```

---

## Notes / out of scope (from spec §2)

- No app code, Dockerfile, or `config.py` change.
- `ASYNC_JOBS_ENABLED` left at default `true` (async live but inert — no caller; spec §5).
- No `deploy:` replicas/limits block (deferred — spec §3/§6).
- api-gateway `extractor-service: 60` timeout is a separate, already-landed item (`api-gateway-go` `d6120318`); not touched here. Worth a one-line deploy confirm but outside this plan.

## Verification environment note

Per project constraints, the local sandbox can lint/parse but cannot run the full Compose stack or connect to the production Redis. `docker compose config` run locally will warn `variable is not set` for `REDIS_SECRET`/`REDIS_HOST`/`REDIS_PORT` (no local `.env`) — that is **expected**, not a failure. The authoritative deploy verification is the operator smoke above; the local gate is the PyYAML parse + the two-line diff.
