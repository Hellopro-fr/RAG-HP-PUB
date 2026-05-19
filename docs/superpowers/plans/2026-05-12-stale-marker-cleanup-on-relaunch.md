# Stale Marker Cleanup on Relaunch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `_cleanup_stale_state_for_relaunch` helper on `CrawlerManager` that deletes `{storage_path}/_completion_marker.json` if present, and call it from `start_crawl` after `os.makedirs`. Eliminates the false reconciliation log line `Reconciling from marker; webhook skipped` that appears on dropData=true relaunches and skips the new run's success webhook.

**Architecture:** Single private async helper in `crawler_manager.py`. Called once in `start_crawl` immediately after `os.makedirs(job_storage_path, exist_ok=True)` (~L231). Reserves a single named extension point for future cleanup items (Redis lock, local_processes, other persistent files) — currently performs marker deletion only.

**Tech Stack:** Python 3, FastAPI, asyncio. Uses `os.unlink` + `os.path.isfile` + `logger`. No new dependencies. No new tests required by spec but a lightweight test class is recommended (3 cases).

**Spec:** `docs/superpowers/specs/2026-05-12-stale-marker-cleanup-on-relaunch-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Modify | Add `_cleanup_stale_state_for_relaunch(crawl_id, storage_path)` method (~25 LOC). Insert single call at top of `start_crawl` after `os.makedirs`. |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | Modify (optional) | Add `TestCleanupStaleStateForRelaunch` class (3 cases). Mirrors project's loose logic-shape test pattern. |

Single sub-problem. 2 files. ~50 LOC total. Tight for single plan.

**Pre-existing context:** branch `features/poc` on `RAG-HP-PUB` worktree. Sub-problem A's commits (`a0c13778`, `1d388c64`) already deployed — this fix is a targeted regression fix for that path. `os.unlink`, `os.path.isfile`, `os.path.join`, `logger` already imported / in scope in `crawler_manager.py`.

---

## Task 1: Add `_cleanup_stale_state_for_relaunch` helper + unit tests

**Goal:** New private async method on `CrawlerManager`. Cleans `_completion_marker.json` if present. Fail-open on `OSError` (log WARNING, no raise). Dead code at end of task — no callers wired in `start_crawl` yet. Plus 3 unit tests covering: marker exists → unlinked, marker missing → no-op, permission error → logged + no raise.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — append helper near `_load_completion_marker_or_none` (added in sub-problem A, ~L1880).
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` — append `TestCleanupStaleStateForRelaunch` class.

**Acceptance Criteria:**
- [ ] `_cleanup_stale_state_for_relaunch(self, crawl_id: str, storage_path: str) -> None` exists with full docstring per spec §4.1
- [ ] Method is `async` (prefix `async def`)
- [ ] Method is on `CrawlerManager` class
- [ ] Deletes `{storage_path}/_completion_marker.json` via `os.unlink` if `os.path.isfile` returns true
- [ ] Logs INFO on successful delete: `Removed stale completion marker for crawl_id '{X}' (relaunch)`
- [ ] Logs WARNING on `OSError`: `Could not remove stale completion marker for '{X}': {error}`
- [ ] Does NOT raise on `OSError` (fail-open)
- [ ] No callers wired in `start_crawl` yet — pure addition
- [ ] 3 unit test cases pass: existing marker unlinked, missing marker no-op, permission error logged + not raised
- [ ] Reuses existing `os`, `logger` imports — no new module imports

**Verify:**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py::TestCleanupStaleStateForRelaunch -v
```
Expected: 3 PASS.

```bash
grep -n "_cleanup_stale_state_for_relaunch" apps-microservices/crawler-service/app/core/crawler_manager.py
```
Expected: 1 hit (definition only). No callers yet.

```bash
grep -n "Removed stale completion marker\|Could not remove stale completion marker" apps-microservices/crawler-service/app/core/crawler_manager.py
```
Expected: 2 hits (INFO log + WARNING log).

### Steps

- [ ] **Step 1: Read existing helper style + insertion point**

Open `apps-microservices/crawler-service/app/core/crawler_manager.py`. Locate `_load_completion_marker_or_none` (added in sub-problem A, around L1880). Confirm:
- Method signature pattern: `async def _xxx(self, ...) -> ...:`
- Logger usage: `logger.info(...)`, `logger.warning(...)`
- File imports include `os` (used by `_load_completion_marker_or_none`), `logger` (module-level)

Pick insertion point: immediately after `_load_completion_marker_or_none` so related helpers are grouped.

Also check `tests/test_crawler_manager.py` for the canonical test pattern. Existing pattern (per prior sub-problem A work): lightweight, uses `tmp_path` fixture, bare `CrawlerManager()` construction works for disk-only helpers, `mocker` fixture NOT available (use `unittest.mock.patch` instead if needed).

- [ ] **Step 2: Write failing tests first (TDD red)**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python
class TestCleanupStaleStateForRelaunch:
    """
    Verifies _cleanup_stale_state_for_relaunch wipes any prior-run
    _completion_marker.json on crawl relaunch. Used by start_crawl
    to prevent the reconciler's marker-check (sub-problem A) from
    falsely declaring the new running crawl finished.
    """

    @pytest.mark.asyncio
    async def test_existing_marker_is_unlinked(self, tmp_path):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text('{"final_status": "finished", "exit_code": 0}')
        assert marker.exists()
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        await manager._cleanup_stale_state_for_relaunch("test-123", str(tmp_path))
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_missing_marker_is_noop(self, tmp_path):
        # tmp_path has no _completion_marker.json
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        # Should not raise. Should not log anything.
        await manager._cleanup_stale_state_for_relaunch("test-456", str(tmp_path))

    @pytest.mark.asyncio
    async def test_permission_error_logged_not_raised(
        self, tmp_path, caplog
    ):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text("{}")
        from unittest.mock import patch
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        with patch("os.unlink", side_effect=PermissionError("denied")):
            with caplog.at_level("WARNING"):
                await manager._cleanup_stale_state_for_relaunch("test-789", str(tmp_path))
        assert any(
            "Could not remove stale completion marker" in r.message
            for r in caplog.records
        )
```

If `import pytest`, `import json` are not already at top of test file, add them.

- [ ] **Step 3: Run tests — confirm RED**

```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py::TestCleanupStaleStateForRelaunch -v
```
Expected: ALL 3 FAIL with `AttributeError: 'CrawlerManager' object has no attribute '_cleanup_stale_state_for_relaunch'`.

If they fail with import errors or fixture errors, fix those first. RED must be on the helper missing.

- [ ] **Step 4: Implement helper (TDD green)**

Insert into `crawler_manager.py` immediately after `_load_completion_marker_or_none` method. Indent with 4 spaces (match class methods).

```python
    async def _cleanup_stale_state_for_relaunch(self, crawl_id: str, storage_path: str) -> None:
        """
        Wipes any persistent state from a prior run of this crawl_id that
        would mislead the reconciler or downstream consumers into thinking
        the new run is in a stale terminal state.

        Called at the top of start_crawl (after makedirs) BEFORE the new
        subprocess is spawned and BEFORE the new Redis state is written.

        Currently cleans:
          - {storage_path}/_completion_marker.json (any prior terminal marker:
            success, OOM-failure, OOM-relaunch-failure, force-finish, or
            reconciler-stale write — all 5 writers funnel here)

        Future items (deferred — see spec §7):
          - Stale crawl_lock:{crawl_id} Redis key
          - Stale local_processes[crawl_id] entry
          - Audit other persistent files in storage_path

        Fail-open: each cleanup logs and continues on error. A failed cleanup
        leaves the existing observed symptom (false marker reconciliation) —
        no regression. The error is surfaced in logs for triage.

        Args:
            crawl_id: identifier of the crawl being launched.
            storage_path: absolute path to {CRAWLER_STORAGE_PATH}/{crawl_id}/.
        """
        # 1. Completion marker — removes false signal that misleads the
        #    reconciler's marker-check (sub-problem A) into declaring the
        #    new running crawl finished and skipping its success webhook.
        marker_path = os.path.join(storage_path, '_completion_marker.json')
        if os.path.isfile(marker_path):
            try:
                os.unlink(marker_path)
                logger.info(f"Removed stale completion marker for crawl_id '{crawl_id}' (relaunch)")
            except OSError as e:
                logger.warning(f"Could not remove stale completion marker for '{crawl_id}': {e}")
```

Match file's existing indent + style. No new imports needed — `os`, `logger` already in file (sub-problem A uses both).

- [ ] **Step 5: Run tests — confirm GREEN**

```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py::TestCleanupStaleStateForRelaunch -v
```
Expected: 3 PASS.

If any fail, debug. Common issues:
- Async/await missing → `RuntimeWarning: coroutine was never awaited`
- `os` not imported in test file → use `unittest.mock.patch("os.unlink", ...)` form which patches module-level
- `CrawlerManager()` ctor errors → check existing TestStaleHandler classes for the canonical instantiation pattern

- [ ] **Step 6: Confirm no callers wired yet**

```bash
grep -n "_cleanup_stale_state_for_relaunch" apps-microservices/crawler-service/app/core/crawler_manager.py
```
Expected: 1 line — the definition `async def _cleanup_stale_state_for_relaunch(...)`. No call sites. `start_crawl` not yet modified.

- [ ] **Step 7: Confirm no regression on sub-problem A tests**

```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py::TestLoadCompletionMarker tests/test_crawler_manager.py::TestStaleHandlerCompletionMarker -v
```
Expected: all PASS (sub-problem A tests unchanged).

- [ ] **Step 8: Commit FR**

⚠️ **Branch + WIP guard:**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git branch --show-current  # MUST be features/poc
git status --short
```

The `git status` may show:
- Modified files you edited (intended): `app/core/crawler_manager.py`, `tests/test_crawler_manager.py`
- Pre-existing WIP from user's parallel TypeScript work in `crawler/src/*.ts` — DO NOT include in commit
- Possibly modified `graphify-out/*` files — graphify hook output, NOT to include

Stage ONLY the 2 intended files:

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
```

Verify staged set: `git status --short | grep "^M " | head -10` — exactly 2 lines.

Commit message FR (HEREDOC `<<'EOF'`, bare `$var`):

```
feat(crawler-service): ajout helper _cleanup_stale_state_for_relaunch

Ajoute une methode privee async sur CrawlerManager pour nettoyer
l'etat persistant d'un run precedent qui pourrait induire en erreur
le reconciler (sous-probleme A) au prochain relaunch du meme crawl_id.

Nettoyage actuel :
  * {storage_path}/_completion_marker.json — supprime si present.
    Couvre les 5 ecrivains du marker : success / OOM-max-restart /
    OOM-relaunch-failed / force-finish / reconciler-stale.

Fail-open : OSError logge en WARNING, pas de raise. Si le cleanup
echoue, le symptome existant (false marker reconciliation) reste
mais aucune regression.

Aucun changement de comportement dans ce commit : le helper n'est
pas encore appele depuis start_crawl. Le branchement arrive dans
le commit suivant.

Points d'extension reserves (deferes, cf spec §7) :
  * Cleanup stale crawl_lock:{crawl_id} Redis key
  * Cleanup stale local_processes[crawl_id] entry
  * Audit autres fichiers persistants storage_path

Tests : nouvelle classe TestCleanupStaleStateForRelaunch (3 cas) :
  * marker existant -> unlinked
  * marker absent -> no-op
  * PermissionError -> logge WARNING, pas de raise

Spec : docs/superpowers/specs/2026-05-12-stale-marker-cleanup-on-relaunch-design.md
```

```bash
git commit -m "$(cat <<'EOF'
... (message above)
EOF
)"
git show HEAD --stat   # MUST show exactly 2 files
```

If extras appear: `git reset --soft HEAD~1` + `git restore --staged <unwanted>` + recommit. Same recovery as prior commits in this branch.

---

## Task 2: Wire helper into `start_crawl` after `os.makedirs`

**Goal:** Activate fix. Insert single call to `await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)` in `start_crawl` immediately after the `os.makedirs(job_storage_path, exist_ok=True)` call (~L231).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — insertion at `start_crawl` body around L231-232.

**Acceptance Criteria:**
- [ ] Call is `await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)` (async + self)
- [ ] Inserted AFTER `os.makedirs(job_storage_path, exist_ok=True)` and the immediately-following `logger.info(...)` line
- [ ] Inserted BEFORE the Redis state write (currently around L321 per recon) and BEFORE subprocess spawn
- [ ] Comment block above the call explains the WHY (sub-problem A regression on dropData=true relaunch)
- [ ] No other lines in `start_crawl` change
- [ ] `start_crawl` signature unchanged
- [ ] All existing TestStaleHandler tests still pass (regression guard)
- [ ] All existing TestLoadCompletionMarker + TestStaleHandlerCompletionMarker tests still pass
- [ ] Task 1 TestCleanupStaleStateForRelaunch tests still pass

**Verify:**

```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py -v -k "TestStaleHandler or TestLoadCompletionMarker or TestCleanupStaleStateForRelaunch"
```
Expected: ALL pass.

```bash
grep -n "_cleanup_stale_state_for_relaunch" apps-microservices/crawler-service/app/core/crawler_manager.py
```
Expected: 2 hits — 1 definition (added Task 1) + 1 call site in `start_crawl`.

### Steps

- [ ] **Step 1: Re-read `start_crawl` body around the makedirs call**

```bash
grep -nA3 "os.makedirs(job_storage_path" apps-microservices/crawler-service/app/core/crawler_manager.py
```

Expected output (line numbers may have shifted slightly):
```
231:        os.makedirs(job_storage_path, exist_ok=True)
232:        logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
```

Confirm the exact two lines and their indentation (16 spaces — 4 levels deep in the class method body).

- [ ] **Step 2: Insert call**

Use Edit. The OLD block to match exactly:

```python
        os.makedirs(job_storage_path, exist_ok=True)
        logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
```

Replace with:

```python
        os.makedirs(job_storage_path, exist_ok=True)
        logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")

        # Wipe any persistent state from a prior run of this crawl_id before
        # spawning the new subprocess. Observed bug (crawl 6229 with dropData=true):
        # old _completion_marker.json survives makedirs, reconciler then declares
        # the new running crawl finished and skips its success webhook.
        await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)
```

Match the surrounding 8-space indent for the class method body (or whatever the file actually uses — read first to confirm).

- [ ] **Step 3: Run full test suite for regression**

```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py -v
```

Expected: ALL existing tests still PASS + Task 1's 3 new tests PASS.

If a regression appears, the call insertion broke something. Re-read the diff carefully — likely indent or wrong location.

- [ ] **Step 4: Confirm call site shape**

```bash
grep -nB2 -A2 "_cleanup_stale_state_for_relaunch" apps-microservices/crawler-service/app/core/crawler_manager.py
```

Expected output (line numbers depend on prior edits):
- 1 hit on the `async def _cleanup_stale_state_for_relaunch(...)` definition
- 1 hit on the `await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)` call inside `start_crawl`

- [ ] **Step 5: Confirm minimal diff**

```bash
git diff apps-microservices/crawler-service/app/core/crawler_manager.py
```

Expected: only the comment block + the single `await self._cleanup_...` line added. No other changes to `start_crawl`.

- [ ] **Step 6: Commit FR**

Same WIP guard as Task 1 — verify `git show HEAD --stat` shows exactly 1 file.

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py
```

Suggested message:

```
fix(crawler-service): wire _cleanup_stale_state_for_relaunch dans start_crawl

Active le correctif pour le bug observe sur crawl 6229 avec
dropData=true : l'ancien _completion_marker.json survit a
os.makedirs(exist_ok=True), le reconciler le lit et declare le
nouveau run "finished from marker", skip son webhook success.

Insertion juste apres os.makedirs(job_storage_path, exist_ok=True)
+ logger.info, AVANT le spawn du subprocess Node.js et AVANT
l'ecriture du nouveau state Redis :

  await self._cleanup_stale_state_for_relaunch(crawl_id, job_storage_path)

Le helper (deja ajoute dans le commit precedent) supprime
_completion_marker.json si present, log INFO sur succes, log
WARNING + ne raise pas sur OSError.

Aucun autre changement a start_crawl. Aucun changement a la
signature ni au flux subprocess. Sub-problem A (marker-check du
reconciler) reste fonctionnel pour son cas d'origine (Redis state
drift) — verifie par les tests existants TestStaleHandlerCompletionMarker.

Predecesseur (helper added) :
  feat(crawler-service): ajout helper _cleanup_stale_state_for_relaunch

Spec : docs/superpowers/specs/2026-05-12-stale-marker-cleanup-on-relaunch-design.md
```

```bash
git commit -m "$(cat <<'EOF'
... (message above)
EOF
)"
git show HEAD --stat   # MUST show exactly 1 file
```

---

## Task 3: Manual verification (docker compose smoke + Ecritel production)

**Goal:** Confirm fix end-to-end. Operations task — Claude prepares commands, user executes.

**Files:** None modified.

**Acceptance Criteria:**
- [ ] pytest passes for `TestCleanupStaleStateForRelaunch` + regression suites in Docker
- [ ] Docker compose smoke: trigger crawl, let it finish, relaunch with dropData=true, verify marker removed log + no `Reconciling from marker; webhook skipped` for the new run
- [ ] Production deploy via standard release
- [ ] Production: monitor `Reconciling from marker; webhook skipped` log volume drops to near-zero (only fires now for real Redis state drift, not relaunches)
- [ ] Regression: fresh crawl_id (never run) → no `Removed stale completion marker` log (no-op)
- [ ] Sub-problem A's intended scenario (Redis state drift) still works: forced drift triggers `Reconciling from marker; webhook skipped` as designed

**Verify:** Steps below produce concrete log + DB evidence per spec §6.

### Steps

- [ ] **Step 1: pytest in Docker**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py::TestCleanupStaleStateForRelaunch -v
```
Expected: 3 PASS.

Full regression sweep:
```bash
docker compose run --rm crawler-service pytest tests/test_crawler_manager.py -v
```
Expected: all PASS.

- [ ] **Step 2: Docker compose smoke**

```bash
cd apps-microservices/crawler-service
docker compose up -d crawler-service
docker compose logs -f crawler-service &
```

Pick a small test domain. Trigger a crawl. Let it finish.

Confirm marker exists on disk:
```bash
docker compose exec crawler-service ls -la /app/storage/<crawl_id>/_completion_marker.json
```
Expected: file exists.

Relaunch the same `crawl_id` with `dropData=true`. As soon as the new run starts, check the log:

```bash
docker compose logs crawler-service --since 30s | grep -E "Removed stale completion marker|Reconciling from marker"
```

Expected:
- 1 line: `Removed stale completion marker for crawl_id '<id>' (relaunch)`
- ZERO lines: `Reconciling from marker; webhook skipped` for this run

Confirm marker is briefly gone:
```bash
docker compose exec crawler-service ls -la /app/storage/<crawl_id>/_completion_marker.json 2>&1 | head -1
```
Expected: `No such file or directory` (until new run completes and writes a fresh marker).

Wait for the new run to finish. Confirm:
- New marker written
- Success webhook dispatched to BO
- No false reconciliation

- [ ] **Step 3: Production deploy**

Standard release path for `crawler-service` container update. Confirm new container is running on all replicas.

- [ ] **Step 4: Production observation — 24h**

Monitor the regression-symptom log line:

```bash
docker compose logs crawler-service --since 24h | grep "Reconciling from marker; webhook skipped" | wc -l
```

Expected: drops to near-zero. Pre-fix volume from a typical day → post-fix should approach 0 (only fires now for real Redis state drift, not relaunches).

Cross-check via the new cleanup log:

```bash
docker compose logs crawler-service --since 24h | grep "Removed stale completion marker" | wc -l
```

Expected: > 0 (fires every relaunch that hits a prior marker — confirms the fix is exercising the right path).

- [ ] **Step 5: Regression check — fresh crawl_id**

Trigger a crawl on a brand-new `crawl_id` (never run before). Watch:
```bash
docker compose logs -f crawler-service | grep -E "Removed stale completion marker|Using storage for crawl_id"
```

Expected:
- `Using storage for crawl_id '<id>'` (standard line)
- NO `Removed stale completion marker` (file didn't exist — no-op)

Crawl proceeds normally.

- [ ] **Step 6: Real Redis-drift case — sub-problem A still works**

Force a stale Redis state on a finished crawl (sub-problem A's intended scenario):

1. Run a small crawl to completion. Marker on disk, Redis status=finished.
2. Manually corrupt Redis to set status=running (force the drift):
   ```bash
   docker compose exec redis redis-cli SET "crawl_jobs:<id>" "$(docker compose exec redis redis-cli GET "crawl_jobs:<id>" | python3 -c 'import sys,json;d=json.loads(sys.stdin.read());d["status"]="running";d["last_heartbeat"]="2020-01-01T00:00:00";print(json.dumps(d))')"
   ```
3. **DO NOT** call start_crawl (no cleanup triggered).
4. Wait for reconciler tick (≤300s).

Expected: `Reconciling from marker; webhook skipped` fires (sub-problem A's intended behavior preserved). This confirms the new cleanup at start_crawl doesn't break the existing reconciler use case.

- [ ] **Step 7: Update primer + memory**

Update `~/.claude/primer.md` Active Project section with deploy outcome. If notable observations emerge (e.g. typical relaunch volume per day, dropData usage frequency), record as project memory.

---

## Self-Review

**Spec coverage:**
- §3.1 single helper → Task 1
- §3.2 helper rationale → Task 1 docstring
- §3.3 component diagram (cleanup → start_crawl → reconciler unchanged) → Task 1 + Task 2
- §4.1 helper code → Task 1 Step 4 verbatim
- §4.2 call site → Task 2 Step 2 verbatim
- §4.3 no new imports → Task 1 Step 1 confirms
- §5 failure modes F1-F10 → covered: F1/F2 by code logic + Task 1 test 1, F3 by Task 1 test 2, F4 by Task 1 test 3, F5 (concurrent) by OSError catch (same as F4), F6 (reconciler race) by helper running before subprocess spawn, F7 (file is dir) by `os.path.isfile`, F8 (empty storage_path) by `os.path.isfile` returning False, F9/F10 (race windows) — race window covered by Step 2 of Task 2 (cleanup BEFORE Redis write + spawn)
- §6 verification → Task 3 implements all 5 sub-checks plus pytest sweep
- §7 out of scope → respected: NG1 (Redis lock cleanup deferred), NG2 (local_processes cleanup deferred), NG3 (audit other files), NG4 (archive tarballs), NG5 (Node.js side), NG6 (marker writers)

**Placeholder scan:** clean. No TBD/TODO.

**Type consistency:**
- `_cleanup_stale_state_for_relaunch(self, crawl_id: str, storage_path: str) -> None` — used 1× in Task 2 call site. Matches.
- `crawl_id` passed as `str` (matches sub-problem A's signature pattern from `_load_completion_marker_or_none`).
- `storage_path` passed as `str` (caller passes `job_storage_path` from `start_crawl` — string).
- Log prefix `Removed stale completion marker` — consistent for INFO; `Could not remove stale completion marker` for WARNING.

**Open questions** (spec §8, deferred — non-blocking):
- Other persistent files audit
- Future cleanup items' fail-open semantics

**Branch + WIP hygiene:**
- Both commits on `features/poc`. Each `git show HEAD --stat` MUST show exactly 2 (Task 1) / 1 (Task 2) files. WIP TS files (`DetectionLangueClient.ts`, `context.ts`, etc.) are pre-existing index entries — implementer must verify they are NOT in commits. Recovery via `git reset --soft HEAD~1` documented in Task 1 Step 8.
