# Crawl Status Singular Endpoint Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `GET /status/{crawl_id}` from returning 500 on malformed Redis blobs by (a) applying the same `setdefault('crawl_id', crawl_id)` heal-on-read in `get_job_or_recover` that the plural endpoint already uses, and (b) converting the residual `None` return from `get_status()` into a clear `HTTPException(404)` instead of letting Pydantic surface a 500.

**Architecture:** Single file change in `app/router/crawler.py`. Two insertions: one in the dependency function `get_job_or_recover` (~L34), one in the endpoint `get_crawl_status` (~L274-279). No changes to `crawler_manager.py` or the plural endpoint.

**Tech Stack:** Python 3, FastAPI, Pydantic. `HTTPException` + `status` already imported. No new deps.

**Spec:** `docs/superpowers/specs/2026-05-19-crawl-status-singular-endpoint-fix-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `apps-microservices/crawler-service/app/router/crawler.py` | Modify | 2 insertions: `setdefault` heal in `get_job_or_recover` (L33-34 area), `None`-check + 404 raise in `get_crawl_status` (L274-279 area). ~10 LOC delta + comments. |
| `apps-microservices/crawler-service/tests/test_router_crawler.py` | Modify or create | Optional unit tests for the heal pattern. Add if test infra accepts; skip otherwise per prior session findings. |

Single file change in the production path. ~10 LOC delta. Test file optional.

**Branch:** `features/poc` on `RAG-HP-PUB` worktree. Pre-existing TS WIP exists in this branch — watch for accidental bundling on commit (use `git show HEAD --stat` after each commit per prior session pattern).

---

## Task 1: Apply heal-on-read + endpoint 404 guard (single commit)

**Goal:** Both spec changes in one commit since they're tightly coupled (heal makes most blobs work; 404 guard handles the residual None case). Single file, ~10 LOC delta.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/crawler.py` — two distinct insertions in same file

**Acceptance Criteria:**
- [ ] `get_job_or_recover` (around L33-34) applies `job_info.setdefault('crawl_id', crawl_id)` BEFORE returning the early-return `job_info` from Redis. Mirrors plural-endpoint `get_all_statuses` pattern.
- [ ] Comment block above the `setdefault` line explains the WHY (legacy blob from 6664, Pydantic 500 root cause).
- [ ] `get_crawl_status` endpoint (around L274-279) captures the return of `crawler_manager.get_status(job_info)` into a local variable, checks `is None`, raises `HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="...")`.
- [ ] `response_model=CrawlStatus` stays non-optional (raise BEFORE the serialize, so Pydantic never sees None).
- [ ] Disk-recovery branch of `get_job_or_recover` (L36+) untouched.
- [ ] `get_all_statuses` (plural) untouched.
- [ ] `crawler_manager.get_status` untouched.
- [ ] `python -m py_compile` passes on the modified file.
- [ ] No new imports (HTTPException + status already imported at top of file via existing 404 raise at L42).

**Verify:**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
python -m py_compile apps-microservices/crawler-service/app/router/crawler.py
```
Expected: no output (clean).

```bash
grep -n "setdefault('crawl_id'\|raise HTTPException" apps-microservices/crawler-service/app/router/crawler.py
```
Expected:
- 1 line at the heal site (setdefault inside get_job_or_recover)
- 2 HTTPException raises (existing one at L42 + new one at L~277)

### Steps

- [ ] **Step 1: Pre-flight branch + WIP check**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git branch --show-current
```
Expected: `features/poc`.

```bash
git status --short
```
Check for pre-existing WIP. TS files (e.g. `crawler/src/*.ts`) — leave alone. The plan touches only Python files in `apps-microservices/crawler-service/app/router/crawler.py`.

- [ ] **Step 2: Read current code around L23-34 (`get_job_or_recover` early-return path)**

Open `apps-microservices/crawler-service/app/router/crawler.py` and confirm L30-34 matches:

```python
job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
job_info = await cache_service.get_json(job_key)

if job_info:
    return job_info
```

(Line numbers may have shifted since the spec was written; verify before editing.)

- [ ] **Step 3: Insert `setdefault` heal in `get_job_or_recover`**

Use Edit. OLD:

```python
    if job_info:
        return job_info
```

NEW:

```python
    if job_info:
        # Heal legacy / partial blobs missing crawl_id. Mirrors get_all_statuses
        # setdefault pattern (commit 508de256). Without this, downstream
        # get_status() returns None on the malformed-blob guard and the
        # singular /status/{crawl_id} endpoint's Pydantic response_model
        # fails with 500 (observed on crawl 6664 — blob had 'id' but not
        # 'crawl_id', likely written by an older code version or an
        # external resource-monitor service).
        job_info.setdefault('crawl_id', crawl_id)
        return job_info
```

Match the file's existing 4-space indent inside the function.

- [ ] **Step 4: Read current code around L274-279 (`get_crawl_status` endpoint)**

Confirm the body matches:

```python
@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.
    """
    return await crawler_manager.get_status(job_info)
```

- [ ] **Step 5: Insert None-check + 404 raise in endpoint**

OLD:

```python
@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.
    """
    return await crawler_manager.get_status(job_info)
```

NEW:

```python
@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.

    Raises 404 when get_status() returns None (malformed blob beyond heal-on-read —
    e.g. missing storage_path as well as crawl_id). Without this guard, Pydantic
    response_model validation would surface a 500 on the None response.
    """
    status_data = await crawler_manager.get_status(job_info)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job '{crawl_id}' state is malformed (missing required fields).",
        )
    return status_data
```

Match indentation (4 spaces).

- [ ] **Step 6: Verify imports**

Check that `HTTPException` and `status` are already imported at top of file:

```bash
grep -nE "^from fastapi import|^import fastapi" apps-microservices/crawler-service/app/router/crawler.py | head -5
```

Expected: `HTTPException` and `status` present (used by `get_job_or_recover` L42 disk-recovery branch).

If missing (unlikely), add to existing fastapi import line.

- [ ] **Step 7: Syntax check**

```bash
python -m py_compile apps-microservices/crawler-service/app/router/crawler.py
```
Expected: no output. If syntax error, re-read the diff.

- [ ] **Step 8: Verify call-site shape**

```bash
grep -nE "setdefault\('crawl_id'|raise HTTPException" apps-microservices/crawler-service/app/router/crawler.py
```

Expected:
- 1 line inside `get_job_or_recover` for `setdefault('crawl_id', crawl_id)`
- 2 lines for `raise HTTPException` (existing at L42 area + new at L277 area)

- [ ] **Step 9: Confirm minimal diff**

```bash
git diff apps-microservices/crawler-service/app/router/crawler.py
```

Expected: only 2 small additions (~10 lines each with comments). No deletions. No changes elsewhere.

- [ ] **Step 10: Commit FR**

⚠️ **WIP guard:**

```bash
git status --short
```

Confirm only `apps-microservices/crawler-service/app/router/crawler.py` is the staged change after `git add`. Pre-existing TS files / graphify-out — DO NOT stage.

```bash
git add apps-microservices/crawler-service/app/router/crawler.py
git status --short | grep "^M " | head -5
```

Expected: exactly 1 line — `M apps-microservices/crawler-service/app/router/crawler.py`.

Commit:

```bash
git commit -m "$(cat <<'EOF'
fix(crawler-service): heal malformed blob + 404 sur singular /status/{id}

Corrige le bug 500 sur GET /status/{crawl_id} quand le blob Redis n'a
pas le champ crawl_id (regression du commit 508de256 qui a fixe le
plural endpoint mais a laisse le singular endpoint vulnerable).

Probleme observe (crawl 6664) :

  GET /status/6664 -> 500. Log :
    ERROR Skipping malformed job entry (missing 'crawl_id'):
      keys=['cpu','domain','id','ram','replica_id','start_time',
            'status','total_ram']
    fastapi.exceptions.ResponseValidationError: Input should be a
      valid dictionary or object to extract fields from, input: None

Cause racine :

  Commit 508de256 (2026-05-03) a applique le setdefault('crawl_id',
  from_key_suffix) heal-on-read dans get_all_statuses (plural). MAIS
  get_job_or_recover (dependency du singular endpoint) ne fait pas
  le setdefault. get_status() recoit blob sans crawl_id, retourne
  None, et le response_model=CrawlStatus non-optional fait planter
  Pydantic -> 500.

Architecture du correctif :

  1. router/crawler.py:33-34 — heal-on-read symetrique au plural :
     job_info.setdefault('crawl_id', crawl_id) apres le get_json
     dans la branche early-return de get_job_or_recover.

  2. router/crawler.py:274-279 — endpoint singular capture la valeur
     de get_status, check is None, raise HTTPException(404, "state
     is malformed..."). Sans ce check, Pydantic surface un 500.

Aucun changement a :
  * get_all_statuses (plural endpoint)
  * get_status() dans crawler_manager.py
  * disk-recovery branch de get_job_or_recover (L36+)
  * response_model=CrawlStatus (reste non-optional ; on raise AVANT)

Hors scope :
  * Forensic origine des blobs 6664 (legacy / external writer)
  * Cleanup script backfill crawl_id
  * Push heal-on-read dans get_status (architectural drift)
  * Telemetry counter

Verification : python -m py_compile + docker smoke avec blob injecte
+ retest production /status/6664.

Spec : docs/superpowers/specs/2026-05-19-crawl-status-singular-endpoint-fix-design.md
Predecesseur deploye : commit 508de256.
EOF
)"
git show HEAD --stat
```

`git show HEAD --stat` MUST show exactly 1 file.

If extras appear: `git reset --soft HEAD~1` + `git restore --staged <unwanted>` + recommit. Same recovery as prior commits in this branch.

---

## Task 2: Manual verification (docker smoke + production retest)

**Goal:** Confirm the fix works end-to-end. Docker smoke with synthetic malformed blob + retest the original failing case in production. Operations task — Claude prepares commands, user executes.

**Files:** None modified.

**Acceptance Criteria:**
- [ ] `python -m py_compile` clean on modified file (already verified in Task 1, re-run here as deploy gate)
- [ ] Docker smoke: inject blob without `crawl_id`, GET singular endpoint → 200 or 404, NOT 500
- [ ] Healthy blob: GET singular endpoint → 200 + body unchanged
- [ ] Plural endpoint regression check: GET /status → 200 + array
- [ ] Production: `GET /status/6664` (or whatever blob still has the legacy shape) → 200 or 404, NOT 500
- [ ] No `Exception in ASGI application` 500 traceback in crawler-service logs for `/status/{id}` after deploy

**Verify:** Steps below produce concrete log + response evidence.

### Steps

- [ ] **Step 1: pytest sweep**

If test infrastructure is in place (Docker compose + pytest-mock available per environment), add the 2-3 logic-shape tests from spec §6.1. Otherwise skip — verification rests on Docker smoke.

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
docker compose run --rm crawler-service pytest tests/ -v -k "status or recover" 2>&1 | tail -30
```

Expected: existing tests pass. If new tests were added, they pass too.

- [ ] **Step 2: Docker compose smoke — inject malformed blob**

```bash
cd apps-microservices/crawler-service
docker compose up -d crawler-service redis
```

Wait for healthcheck. Then inject a blob matching the 6664 shape (missing `crawl_id`, has `id` instead):

```bash
docker compose exec redis redis-cli SET "crawl_jobs:test-bad" '{"id":"test-bad","domain":"example.com","status":"running","cpu":1,"ram":1024,"replica_id":"node-1","start_time":"2026-05-19T08:00:00","total_ram":4096}'
```

Test the singular endpoint:

```bash
curl -i http://localhost:<port>/status/test-bad
```

Outcome A (heal worked, get_status passes other guards): `HTTP/1.1 200 OK` + CrawlStatus body with `crawl_id=test-bad`.

Outcome B (heal worked but storage_path missing): `HTTP/1.1 404 Not Found` + body `{"detail":"Crawl job 'test-bad' state is malformed (missing required fields)."}`.

NOT `HTTP/1.1 500`. If 500 → fix failed; re-check.

- [ ] **Step 3: Docker smoke — healthy blob**

```bash
docker compose exec redis redis-cli SET "crawl_jobs:test-ok" '{"crawl_id":"test-ok","domain":"example.com","status":"running","storage_path":"/app/storage/test-ok","start_time":"2026-05-19T08:00:00"}'

curl -i http://localhost:<port>/status/test-ok
```

Expected: `HTTP/1.1 200 OK` + CrawlStatus body. Regression check that healthy case is unchanged.

- [ ] **Step 4: Plural endpoint regression**

```bash
curl -i http://localhost:<port>/status
```

Expected: `HTTP/1.1 200 OK` + array containing all entries including `test-bad` and `test-ok`. Confirms plural endpoint's existing self-heal still works (this fix didn't break it).

- [ ] **Step 5: Cleanup smoke test**

```bash
docker compose exec redis redis-cli DEL "crawl_jobs:test-bad" "crawl_jobs:test-ok"
```

- [ ] **Step 6: Deploy to production**

Standard crawler-service release path. Confirm new container running on all replicas.

- [ ] **Step 7: Retest production**

```bash
curl -i https://<crawler-service>/status/6664
```

Expected: `HTTP/1.1 200 OK` or `HTTP/1.1 404 Not Found`. NOT 500.

```bash
docker compose logs crawler-service --since 30m | grep "/status/6664"
```

Expected: status 200 or 404 in uvicorn.access logs. No `Exception in ASGI application` traceback.

- [ ] **Step 8: Monitor production for 24h**

```bash
docker compose logs crawler-service --since 24h | grep -E "Exception in ASGI application|fastapi.exceptions.ResponseValidationError" | head -20
```

Expected: empty. Any remaining 500s on `/status/{id}` would indicate a different failure mode (not the malformed-blob root cause this spec addresses).

```bash
docker compose logs crawler-service --since 24h | grep "Skipping malformed job entry" | wc -l
```

Expected: still some occurrences (the log fires inside `get_status()` BEFORE returning None — it now means "404 raised cleanly" not "500 imminent"). Volume should match or be lower than pre-deploy.

- [ ] **Step 9: Update primer + memory if findings emerge**

If the 24h observation reveals patterns (e.g. specific blob writer producing the malformed shape), document in `~/.claude/primer.md` and consider follow-up forensic investigation per spec §9.

---

## Self-Review

**Spec coverage:**
- §3.1 two-line change → Task 1 Steps 3 + 5 implement both
- §3.2 unchanged surfaces → Task 1 acceptance criteria list
- §4.1 heal-on-read code → Task 1 Step 3 verbatim
- §4.2 endpoint None-check code → Task 1 Step 5 verbatim
- §4.3 no new imports → Task 1 Step 6 verifies
- §5 failure modes F1-F8 → covered by code logic + Task 2 Steps 2-3 exercise F1-F3
- §6 verification → Task 2 implements §6.1 (pytest), §6.2 (Docker smoke), §6.3 (production retest)
- §7 out of scope → respected (no forensic, no cleanup, no get_status push-down, no telemetry)

**Placeholder scan:** clean. The `<port>` placeholder in Task 2 Step 2 is intentional — operator fills with their actual exposed port (varies per docker compose setup).

**Type consistency:**
- `setdefault('crawl_id', crawl_id)` — single call site, parameter name matches function signature
- `status_data` local var — used once for the None-check, once for the return
- `HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=...)` — matches existing usage at L42

**Branch + WIP hygiene:**
- Single commit on `features/poc` branch
- `git show HEAD --stat` must show exactly 1 file (apps-microservices/crawler-service/app/router/crawler.py)
- Recovery via `git reset --soft HEAD~1` documented in Task 1 Step 10
