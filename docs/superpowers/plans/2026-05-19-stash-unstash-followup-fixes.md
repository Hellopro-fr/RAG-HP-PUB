# Stash/Unstash Follow-Up Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply 6 follow-up fixes from final code review of stash/unstash feature: drop Prometheus counter claim (replace with grep-friendly log prefix), harden tar extract against CVE-2007-4559, close TOCTOU races in stash_crawl + unstash_crawl, wrap stash pre-flight fail-open, replace no-op test with concrete marker assertion.

**Architecture:** All edits are surgical patches inside existing functions or single-line replacements in docs. No new dependencies. No env var changes. No daemon restart.

**Tech Stack:** Python 3.10, FastAPI, pytest, asyncio, pydantic-settings, aiofiles.

**Spec:** `docs/superpowers/specs/2026-05-19-stash-unstash-followup-fixes-design.md` (commit `adebe489`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/CLAUDE.md` | Modify (1 line, Stash section step 7) | Drop counter claim, add log prefix mention |
| `docs/daemon_guide.md` | Modify (orphan-troubleshooting block) | Drop counter claim, add grep guidance |
| `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md` | Modify (append Amendment 2026-05-19) | Cross-reference follow-up spec |
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | Modify | Items 2-5: tarfile filter, fail-open wrap, orphan log rewrite, TOCTOU re-validation x2 |
| `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` | Modify | Add 4 regression tests + rewrite 1 no-op test |

---

## Task Sequence

7 tasks, executed in safety-first order: docs drop (no code risk) → mechanical 1-line patches → orchestration changes (TOCTOU) → test rewrite. Each task is one committable change.

---

### Task 1: Drop Prometheus counter claim from docs + spec

**Goal:** Stop false advertising in `CLAUDE.md`, `daemon_guide.md`, and the original spec. Replace counter promise with `UNSTASH_GCS_ORPHAN` log-prefix guidance.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`
- Modify: `docs/daemon_guide.md`
- Modify: `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`

**Acceptance Criteria:**
- [ ] No occurrence of `unstash_gcs_orphan_total` in `CLAUDE.md` or `daemon_guide.md`.
- [ ] Both files mention `UNSTASH_GCS_ORPHAN` as grep prefix for orphan inventory.
- [ ] Original spec has "Amendment 2026-05-19" section at the bottom cross-referencing the follow-up spec.

**Verify:** `git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" grep -nE "unstash_gcs_orphan_total" -- apps-microservices/crawler-service/CLAUDE.md docs/daemon_guide.md` returns empty.

**Steps:**

- [ ] **Step 1.1: Drop Prometheus counter line in `apps-microservices/crawler-service/CLAUDE.md`**

Find the Stash section step 7 (currently mentions `unstash_gcs_orphan_total Prometheus counter incremented`). Edit:

```markdown
# OLD (existing line in CLAUDE.md):
7. On grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'` (orphan GCS object — `unstash_gcs_orphan_total` Prometheus counter incremented)

# NEW:
7. On grace expired: clear `stashed_at`, return 200 with `gcs_cleanup_status='deferred'`. Orphan GCS object is logged as `UNSTASH_GCS_ORPHAN crawl_id=… elapsed_seconds=… reason=cleanup_grace_expired gcs_path=…` for operator grep (no Prometheus counter — operational observability is log-based).
```

- [ ] **Step 1.2: Drop Prometheus counter line in `docs/daemon_guide.md`**

Find the orphan-troubleshooting block. Edit:

```markdown
# OLD:
If `POST /unstash/{crawl_id}` returns `gcs_cleanup_status="deferred"`, the local data was restored but the GCS source object was not deleted within `UNSTASH_CLEANUP_GRACE_SECONDS`. Prometheus counter `unstash_gcs_orphan_total` is incremented. To investigate:

# NEW:
If `POST /unstash/{crawl_id}` returns `gcs_cleanup_status="deferred"`, the local data was restored but the GCS source object was not deleted within `UNSTASH_CLEANUP_GRACE_SECONDS`. The service logs `UNSTASH_GCS_ORPHAN crawl_id=… elapsed_seconds=… reason=cleanup_grace_expired gcs_path=…` in `crawler.log`. Grep that prefix to inventory orphans. To investigate:
```

- [ ] **Step 1.3: Append Amendment block to original spec**

In `docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md`, append at the end:

```markdown

---

## Amendment 2026-05-19

Final code review (`superpowers-extended-cc:code-reviewer`) of commits `21bf809f..7ebbb0c8` identified 6 blockers, addressed by follow-up spec `docs/superpowers/specs/2026-05-19-stash-unstash-followup-fixes-design.md`. Summary of contract changes:

- **§2.10 + §10 Prometheus counters** (`stash_total`, `unstash_total`, `unstash_duration_seconds`, `unstash_gcs_orphan_total`): **scoped out**. Replaced by structured `logger.warning` lines with grep-friendly prefixes (e.g., `UNSTASH_GCS_ORPHAN`). Rationale: `crawler-service` has no existing `prometheus_client` usage; adding the dependency + `/metrics` endpoint wiring is out of scope for this fix cycle. Operators rely on `crawler.log` grep until a dedicated observability spec ships.
- **§5.1 pre-flight fail-open**: clarified — `stash_crawl` now wraps the measurement helpers in `try/except` matching the `archive_crawl` pattern (was: implicit; now: explicit).
- **§7.2 unstash extract path**: `tarfile.extractall` now uses `filter="data"` per PEP 706 (CVE-2007-4559 hardening + Python 3.14 forward compat).
- **§5 stash + unstash pre-condition checks**: post-lock re-validation against fresh Redis blob added to close a 2-replica TOCTOU race window between caller's `job_info` snapshot and ownership lock acquisition.
- **§8 test_unstash_writes_request_marker**: replaced timeout-only assertion with concrete marker file path + content capture via `asyncio` polling helper.

See follow-up spec for full rationale and implementation details.
```

- [ ] **Step 1.4: Verify**

```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" grep -nE "unstash_gcs_orphan_total" -- apps-microservices/crawler-service/CLAUDE.md docs/daemon_guide.md
```

Expected: empty.

```bash
grep -c "UNSTASH_GCS_ORPHAN" "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service/CLAUDE.md" "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB/docs/daemon_guide.md"
```

Expected: each file ≥1.

- [ ] **Step 1.5: Commit (bilingual EN+FR)**

Write commit message to `.git/COMMIT_EDITMSG` via Write tool (Windows cp1252 hazard), then commit:

```
docs(crawler-service): drop Prometheus counter claim from stash docs

EN:
crawler-service has no prometheus_client dependency. Replace the
unstash_gcs_orphan_total counter claim in CLAUDE.md + daemon_guide.md
with a grep-friendly UNSTASH_GCS_ORPHAN log prefix. Amend original
stash/unstash spec with an Amendment 2026-05-19 section cross-
referencing the follow-up spec.

FR:
crawler-service n'a pas de dépendance prometheus_client. Remplace la
promesse de compteur unstash_gcs_orphan_total dans CLAUDE.md +
daemon_guide.md par un préfixe de log UNSTASH_GCS_ORPHAN grepable.
Ajoute une section « Amendment 2026-05-19 » à la spec originale qui
référence la spec de suivi.
```

Stage exactly:
```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/CLAUDE.md \
    docs/daemon_guide.md \
    docs/superpowers/specs/2026-05-19-stash-unstash-gcs-design.md
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 2: Add `tarfile.extractall(filter="data")`

**Goal:** Patch the unstash extract path with PEP 706 `filter="data"` argument. Add a regression test asserting extracted files don't escape `target_storage`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (line 2142)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (add 1 test)

**Acceptance Criteria:**
- [ ] Line `tar.extractall(path=target_storage)` is replaced with `tar.extractall(path=target_storage, filter="data")`.
- [ ] New test `test_unstash_tar_filter_blocks_path_traversal` asserts a tar containing a member with `../` prefix is rejected by the extract step.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v -k "tar_filter"` → 1 PASS.

**Steps:**

- [ ] **Step 2.1: Apply the patch**

In `apps-microservices/crawler-service/app/core/crawler_manager.py` around line 2142:

```python
# OLD:
                with tarfile.open(download_path, 'r:gz') as tar:
                    tar.extractall(path=target_storage)

# NEW:
                with tarfile.open(download_path, 'r:gz') as tar:
                    tar.extractall(path=target_storage, filter="data")
```

`filter="data"` is the PEP 706 standard safe filter: rejects absolute paths, `..` traversal, device files, special permissions. Available in Python 3.12+.

- [ ] **Step 2.2: Add regression test**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`:

```python
@pytest.mark.asyncio
async def test_unstash_tar_filter_blocks_path_traversal(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Verify tarfile.extractall(filter='data') rejects path-traversal members.

    Build a malicious tar.gz with a member named '../escape.txt'. The PEP 706
    safe filter must reject it; the unstash branch then returns 502
    EXTRACT_FAILED and preserves stashed_at in Redis.
    """
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    storage_root = tmp_path / "storage"
    req_dir.mkdir()
    res_dir.mkdir()
    storage_root.mkdir()

    # Build a tar.gz with a path-traversal member.
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.txt").write_text("legit")
    tar_path = res_dir / "test_id.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as t:
        # Legit member
        t.add(str(src / "ok.txt"), arcname="ok.txt")
        # Path-traversal member
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = 5
        import io
        t.addfile(info, io.BytesIO(b"boom!"))
    (res_dir / "test_id.done").touch()

    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "CRAWLER_STORAGE_PATH", str(storage_root))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "EXTRACT_FAILED"
    # Confirm the escape file did NOT land outside storage_root
    assert not (tmp_path / "escape.txt").exists()
```

- [ ] **Step 2.3: Run the test**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_unstash_tar_filter_blocks_path_traversal -v
```

Expected: PASS.

- [ ] **Step 2.4: Run full stash suite (no regression)**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -10
```

Expected: 19 passed (18 prior + 1 new).

- [ ] **Step 2.5: Commit (bilingual EN+FR)**

```
fix(crawler-service): harden unstash tarfile.extractall with PEP 706 filter

EN:
Add filter="data" to tarfile.extractall in unstash_crawl. Closes
CVE-2007-4559 path traversal vector. Forward-compatible with Python
3.14's hard-reject default. New test exercises a malicious tar with
'../escape.txt' member and asserts EXTRACT_FAILED 502.

FR:
Ajout de filter="data" à tarfile.extractall dans unstash_crawl. Ferme
le vecteur de traversée de chemin CVE-2007-4559. Compatible avec le
rejet strict par défaut de Python 3.14. Nouveau test exerce un tar
malicieux avec un membre '../escape.txt' et vérifie EXTRACT_FAILED
502.
```

Stage:
```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/app/core/crawler_manager.py \
    apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 3: Wrap `stash_crawl` pre-flight in fail-open try/except

**Goal:** Per spec §5.1, a measurement-helper exception must not escalate to a 500. Mirror the `archive_crawl` pattern. Add regression test.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (lines 1941-1960)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (add 1 test)

**Acceptance Criteria:**
- [ ] Pre-flight block in `stash_crawl` is wrapped in `try / except HTTPException: raise / except Exception: log warning + continue`.
- [ ] New test `test_stash_preflight_failopen_on_measurement_exception` simulates `_get_archives_disk_state` raising and asserts stash still succeeds.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v -k "preflight_failopen"` → 1 PASS.

**Steps:**

- [ ] **Step 3.1: Apply the wrap**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, replace the block at lines 1941-1960:

```python
# OLD:
            # --- Pre-flight disk space check ---
            baseline_state = self._get_archives_disk_state(stash_dir)
            logger.info(f"Stash disk state for '{crawl_id}': {baseline_state}")
            required_bytes = self._estimate_archive_required_bytes(job_storage_path)
            required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

            if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
                logger.warning(
                    f"Rejecting stash '{crawl_id}': insufficient disk space. "
                    f"Required: {required_bytes}, Available: {baseline_state['free_bytes']}"
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error_code": "INSUFFICIENT_DISK_SPACE",
                        "required_bytes": required_bytes,
                        "available_bytes": baseline_state["free_bytes"],
                        "disk_state": baseline_state,
                    },
                )

# NEW:
            # --- Pre-flight disk space check (fail-open per spec §5.1) ---
            try:
                baseline_state = self._get_archives_disk_state(stash_dir)
                logger.info(f"Stash disk state for '{crawl_id}': {baseline_state}")
                required_bytes = self._estimate_archive_required_bytes(job_storage_path)
                required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

                if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
                    logger.warning(
                        f"Rejecting stash '{crawl_id}': insufficient disk space. "
                        f"Required: {required_bytes}, Available: {baseline_state['free_bytes']}"
                    )
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error_code": "INSUFFICIENT_DISK_SPACE",
                            "required_bytes": required_bytes,
                            "available_bytes": baseline_state["free_bytes"],
                            "disk_state": baseline_state,
                        },
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(
                    f"Stash pre-flight measurement failed for '{crawl_id}': {e}. "
                    f"Proceeding without disk-space check (fail-open)."
                )
```

- [ ] **Step 3.2: Add regression test**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`:

```python
@pytest.mark.asyncio
async def test_stash_preflight_failopen_on_measurement_exception(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Per spec §5.1: a measurement-helper exception must not escalate to 500.
    Stash proceeds without the disk-space check (fail-open)."""
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")

    # _get_archives_disk_state raises a generic Exception
    def boom(d):
        raise RuntimeError("simulated filesystem error")
    monkeypatch.setattr(cm_instance, "_get_archives_disk_state", boom)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    result = await cm_instance.stash_crawl(base_job_info)
    assert result["status"] == "stashing"
    assert result["crawl_id"] == "test_id"
    # Tar still created — measurement skip did not block the stash
    assert (stash_dir / "test_id.tar.gz").exists()
```

- [ ] **Step 3.3: Run the test**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_stash_preflight_failopen_on_measurement_exception -v
```

Expected: PASS.

- [ ] **Step 3.4: Full suite (no regression)**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5
```

Expected: 20 passed.

- [ ] **Step 3.5: Commit (bilingual EN+FR)**

```
fix(crawler-service): stash pre-flight fail-open per spec §5.1

EN:
Wrap _get_archives_disk_state + _estimate_archive_required_bytes in
try/except inside stash_crawl. A measurement exception now logs a
warning and proceeds with the stash instead of escalating to a generic
500. Mirrors the existing archive_crawl fail-open pattern. New test
asserts stash succeeds even when _get_archives_disk_state raises.

FR:
Wrap de _get_archives_disk_state + _estimate_archive_required_bytes
dans un try/except à l'intérieur de stash_crawl. Une exception de
mesure log désormais un warning et procède au stash au lieu d'escalader
en 500 générique. Réplique le pattern fail-open existant
d'archive_crawl. Nouveau test vérifie que stash réussit même quand
_get_archives_disk_state lève.
```

```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/app/core/crawler_manager.py \
    apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 4: Rewrite orphan log line to `UNSTASH_GCS_ORPHAN` grep prefix

**Goal:** Replace the free-form warning with a structured grep-friendly line matching the docs amendment from Task 1.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (lines 2171-2176)

**Acceptance Criteria:**
- [ ] The deferred-cleanup branch emits a log line starting with `UNSTASH_GCS_ORPHAN`.
- [ ] Existing test `test_unstash_gcs_cleanup_deferred_returns_200_with_warning` still passes (asserts `gcs_cleanup_status == "deferred"`, agnostic to log content).
- [ ] `grep -n UNSTASH_GCS_ORPHAN apps-microservices/crawler-service/app/core/crawler_manager.py` returns ≥1.

**Verify:** `grep -n UNSTASH_GCS_ORPHAN apps-microservices/crawler-service/app/core/crawler_manager.py` → ≥1 line; full stash suite passes.

**Steps:**

- [ ] **Step 4.1: Apply the rewrite**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, replace lines 2171-2176:

```python
# OLD:
            if gcs_cleanup_status == "deferred":
                logger.warning(
                    f"Unstash cleanup-done marker not arrived within "
                    f"{settings.UNSTASH_CLEANUP_GRACE_SECONDS}s for '{crawl_id}'. "
                    f"GCS object may be orphaned at gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz."
                )

# NEW:
            if gcs_cleanup_status == "deferred":
                logger.warning(
                    f"UNSTASH_GCS_ORPHAN crawl_id={crawl_id} "
                    f"elapsed_seconds={settings.UNSTASH_CLEANUP_GRACE_SECONDS} "
                    f"reason=cleanup_grace_expired "
                    f"gcs_path=gs://{settings.GCS_BUCKET_NAME}/stash/{crawl_id}.tar.gz"
                )
```

- [ ] **Step 4.2: Verify grep + existing test**

```bash
grep -n UNSTASH_GCS_ORPHAN "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service/app/core/crawler_manager.py"
```

Expected: 1 line (around line 2172).

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_unstash_gcs_cleanup_deferred_returns_200_with_warning -v
```

Expected: PASS.

- [ ] **Step 4.3: Commit (bilingual EN+FR)**

```
fix(crawler-service): UNSTASH_GCS_ORPHAN grep prefix for deferred-cleanup log

EN:
Restructure the deferred-cleanup warning in unstash_crawl with a
grep-friendly key=value format prefixed by UNSTASH_GCS_ORPHAN. Aligns
with the docs amendment that drops the false Prometheus counter claim
and tells operators to grep this prefix in crawler.log.

FR:
Restructure le warning de deferred-cleanup dans unstash_crawl avec un
format key=value grepable préfixé par UNSTASH_GCS_ORPHAN. S'aligne sur
l'amendement docs qui retire la promesse fausse de compteur Prometheus
et indique aux opérateurs de grep ce préfixe dans crawler.log.
```

```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/app/core/crawler_manager.py
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 5: Close `stash_crawl` TOCTOU race with post-lock re-validation

**Goal:** Insert a fresh Redis read + re-validation block right after `_acquire_ownership_lock` so a 2-replica race on the same crawl_id cannot overwrite GCS data. Add regression test.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert after line 1934, before line 1936 `try:`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (add 1 test)

**Acceptance Criteria:**
- [ ] After lock acquire, fresh Redis read happens BEFORE any disk-space check or tar staging.
- [ ] Re-validation raises the same 409s the upfront check would (CRAWL_IS_ACTIVE / ALREADY_ARCHIVED / ALREADY_STASHED) using fresh status.
- [ ] On re-validation mismatch, lock is released explicitly via `_release_ownership_lock(stash_lock_key, lock_value)` before raise, and `lock_value` is set to `None` so the `finally` block does not double-release.
- [ ] New test `test_stash_toctou_revalidation_blocks_concurrent_winner` simulates a concurrent winner via `get_json` returning a `stashed_at`-populated blob and asserts 409 ALREADY_STASHED + lock release.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v -k "toctou"` → 1 PASS.

**Steps:**

- [ ] **Step 5.1: Insert re-validation block**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, find the block at lines 1929-1936:

```python
# CONTEXT (existing code):
        lock_value = await self._acquire_ownership_lock(stash_lock_key, settings.STASH_LOCK_TTL_SECONDS)
        if lock_value is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "OPERATION_IN_PROGRESS", "operation": "stash"}
            )

        try:
            stash_dir = settings.STASH_SHARED_PATH
```

Replace with:

```python
        lock_value = await self._acquire_ownership_lock(stash_lock_key, settings.STASH_LOCK_TTL_SECONDS)
        if lock_value is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "OPERATION_IN_PROGRESS", "operation": "stash"}
            )

        # --- Post-lock TOCTOU re-validation (spec follow-up §4.2) ---
        # Another replica may have completed the operation between the caller's
        # job_info snapshot and our lock acquire. Re-fetch and re-validate against
        # the same pre-conditions; on mismatch, release the lock and raise the
        # canonical 409.
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        fresh_job_info = await cache_service.get_json(job_key)
        if fresh_job_info is None:
            await self._release_ownership_lock(stash_lock_key, lock_value)
            lock_value = None
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{crawl_id}' vanished from Redis during stash claim."
            )
        fresh_status = fresh_job_info.get("status")
        if fresh_status in ("running", "restarting_oom", "stopping"):
            await self._release_ownership_lock(stash_lock_key, lock_value)
            lock_value = None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "CRAWL_IS_ACTIVE", "current_status": fresh_status},
            )
        if fresh_status == "archived":
            await self._release_ownership_lock(stash_lock_key, lock_value)
            lock_value = None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "ALREADY_ARCHIVED"},
            )
        if fresh_job_info.get("stashed_at"):
            await self._release_ownership_lock(stash_lock_key, lock_value)
            lock_value = None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "ALREADY_STASHED", "stashed_at": fresh_job_info["stashed_at"]},
            )
        # Use the fresh blob from here on.
        job_info = fresh_job_info

        try:
            stash_dir = settings.STASH_SHARED_PATH
```

(Inserted block comes BEFORE the existing `try:` at the old line 1936. `job_info` is re-bound to the fresh dict so downstream code uses the up-to-date status/storage_path.)

- [ ] **Step 5.2: Verify `_release_ownership_lock` is `None`-guarded**

Find the helper (around line 1874). Confirm it short-circuits on `None`:

```bash
grep -A 5 "async def _release_ownership_lock" "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service/app/core/crawler_manager.py" | head -8
```

If it does NOT guard `None`, ALSO add the guard inline before the early-return release calls:

```python
if lock_value is not None:
    await self._release_ownership_lock(stash_lock_key, lock_value)
    lock_value = None
```

(The block above already follows this shape — but verify the helper itself for safety. If the helper guards None internally, the inline checks are redundant but harmless.)

- [ ] **Step 5.3: Add regression test**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`:

```python
@pytest.mark.asyncio
async def test_stash_toctou_revalidation_blocks_concurrent_winner(cm_instance, base_job_info, mock_cache_service, monkeypatch):
    """Spec follow-up §4.2: 2-replica TOCTOU race.

    Caller-passed job_info has no stashed_at; SET NX succeeds. Fresh Redis
    read inside stash_crawl returns the same crawl with stashed_at populated
    by a concurrent winner. stash_crawl must raise 409 ALREADY_STASHED and
    release the lock instead of proceeding to overwrite GCS.
    """
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    stashed_blob = dict(base_job_info)
    stashed_blob["stashed_at"] = "2026-05-19T10:00:00Z"
    mock_cache_service.get_json = AsyncMock(return_value=stashed_blob)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "ALREADY_STASHED"
    assert exc.value.detail["stashed_at"] == "2026-05-19T10:00:00Z"
    # Lock release (Lua eval) was called for compare-and-delete
    assert mock_cache_service.redis_client.eval.call_count >= 1
```

- [ ] **Step 5.4: Run tests**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_stash_toctou_revalidation_blocks_concurrent_winner -v
```

Expected: PASS.

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5
```

Expected: 21 passed (no regression on prior 20).

- [ ] **Step 5.5: Commit (bilingual EN+FR)**

```
fix(crawler-service): close stash_crawl TOCTOU race via post-lock re-validation

EN:
After acquiring the ownership lock, re-fetch the Redis blob and
re-validate stashed_at / status against the spec §5 pre-conditions.
Closes a 2-replica race window where the caller's job_info snapshot
was stale by the time SET NX succeeded — without re-validation a
second replica would proceed to overwrite GCS data. On mismatch we
explicitly release the lock and null out lock_value so the finally
block does not double-release. Regression test exercises the
concurrent-winner path.

FR:
Après acquisition du lock d'ownership, re-fetch le blob Redis et
re-valide stashed_at / status contre les pré-conditions de la spec §5.
Ferme une fenêtre de race 2-replica où le snapshot job_info du caller
était périmé au moment où le SET NX réussit — sans re-validation un
second replica écraserait les données GCS. Sur mismatch on libère
explicitement le lock et on null lock_value pour que le finally ne
double-libère pas. Test de régression exerce le chemin du
concurrent-winner.
```

```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/app/core/crawler_manager.py \
    apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 6: Close `unstash_crawl` TOCTOU race with post-lock re-validation

**Goal:** Symmetric fix on the unstash side. Insert post-lock re-validation of `stashed_at IS NOT NULL`. Add regression test.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert after `unstash_crawl` lock-acquire block)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (add 1 test)

**Acceptance Criteria:**
- [ ] After `unstash_crawl` lock acquire, fresh Redis read + re-validation.
- [ ] On `stashed_at == None`, lock released + 409 NOT_STASHED raised.
- [ ] New test `test_unstash_toctou_revalidation_blocks_concurrent_winner` asserts the path.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v -k "toctou"` → 2 PASS.

**Steps:**

- [ ] **Step 6.1: Locate `unstash_crawl` lock acquire**

```bash
grep -n "_acquire_ownership_lock" "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service/app/core/crawler_manager.py"
```

Note the line in `unstash_crawl` (after the NOT_STASHED early-check).

- [ ] **Step 6.2: Insert re-validation block**

After the `unstash_crawl` `lock_value = await self._acquire_ownership_lock(unstash_lock_key, ...)` call and its `if lock_value is None: raise ...` block, BEFORE the next `try:` line, insert:

```python
        # --- Post-lock TOCTOU re-validation (spec follow-up §4.2) ---
        # Another replica may have completed unstash between caller's job_info
        # snapshot and our lock acquire. Re-fetch and verify stashed_at is still
        # populated; on mismatch, release the lock and raise 409 NOT_STASHED.
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        fresh_job_info = await cache_service.get_json(job_key)
        if fresh_job_info is None:
            await self._release_ownership_lock(unstash_lock_key, lock_value)
            lock_value = None
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{crawl_id}' vanished from Redis during unstash claim."
            )
        if not fresh_job_info.get("stashed_at"):
            await self._release_ownership_lock(unstash_lock_key, lock_value)
            lock_value = None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "NOT_STASHED"},
            )
        # Use the fresh blob from here on.
        job_info = fresh_job_info
```

(Block goes immediately after the lock-acquire check and BEFORE any disk pre-flight / file IO.)

- [ ] **Step 6.3: Add regression test**

Append to `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`:

```python
@pytest.mark.asyncio
async def test_unstash_toctou_revalidation_blocks_concurrent_winner(cm_instance, stashed_job_info, mock_cache_service, monkeypatch):
    """Spec follow-up §4.2: symmetric to the stash TOCTOU test.

    Caller-passed job_info has stashed_at set; lock acquire succeeds. Fresh
    Redis read returns the same crawl with stashed_at popped by a concurrent
    winning unstash. unstash_crawl must raise 409 NOT_STASHED and release
    the lock instead of proceeding to download/extract.
    """
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    unstashed_blob = dict(stashed_job_info)
    unstashed_blob.pop("stashed_at", None)
    mock_cache_service.get_json = AsyncMock(return_value=unstashed_blob)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "NOT_STASHED"
    assert mock_cache_service.redis_client.eval.call_count >= 1
```

- [ ] **Step 6.4: Run tests**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_unstash_toctou_revalidation_blocks_concurrent_winner -v
```

Expected: PASS.

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5
```

Expected: 22 passed.

- [ ] **Step 6.5: Commit (bilingual EN+FR)**

```
fix(crawler-service): close unstash_crawl TOCTOU race via post-lock re-validation

EN:
Symmetric to the stash_crawl fix: after acquiring the unstash lock,
re-fetch the Redis blob and re-validate stashed_at is still populated.
On mismatch (another replica completed unstash first), release the
lock and raise 409 NOT_STASHED instead of proceeding to download +
extract. Regression test exercises the path.

FR:
Symétrique au fix de stash_crawl : après acquisition du lock d'unstash,
re-fetch le blob Redis et re-valide que stashed_at est toujours
peuplé. Sur mismatch (un autre replica a terminé l'unstash en premier),
libère le lock et lève 409 NOT_STASHED au lieu de procéder au
download + extract. Test de régression exerce le chemin.
```

```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/app/core/crawler_manager.py \
    apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 7: Rewrite `test_unstash_writes_request_marker` with concrete capture

**Goal:** Replace the timeout-only assertion with a concrete capture of the marker file path and content via async polling helper.

**Files:**
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (replace `test_unstash_writes_request_marker`)

**Acceptance Criteria:**
- [ ] Old `test_unstash_writes_request_marker` body replaced with a concrete capture pattern.
- [ ] Test asserts the marker filename is `test_id.request` and content equals `test_id`.
- [ ] Test still completes within the existing `UNSTASH_TIMEOUT_SECONDS=2` budget.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_unstash_writes_request_marker -v` → PASS.

**Steps:**

- [ ] **Step 7.1: Replace the test body**

In `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py`, replace the existing `test_unstash_writes_request_marker` function (lines ~213-234):

```python
# OLD:
@pytest.mark.asyncio
async def test_unstash_writes_request_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 2)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)

    with pytest.raises(HTTPException):  # will timeout (no .done written)
        await cm_instance.unstash_crawl(stashed_job_info)

    # Request marker must have been written
    # (cleaned up on timeout, so check via Redis exists / mock_set_json calls)
    # — alternative: spy on aiofiles.open
    # Here we rely on the timeout path removing it; verify timeout raised 504
    # The actual write is verified by reaching the polling loop without error.

# NEW:
@pytest.mark.asyncio
async def test_unstash_writes_request_marker(cm_instance, stashed_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Concrete capture: assert the marker file path + content actually written
    by unstash_crawl before the polling loop times out.

    Prior version asserted only the 504 timeout — passed even if the marker
    write was a no-op. Spec §8 (and follow-up §4.4) require the write itself
    to be verified.
    """
    req_dir = tmp_path / "stash-req"
    res_dir = tmp_path / "stash-res"
    req_dir.mkdir()
    res_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(req_dir))
    monkeypatch.setattr(cm_module.settings, "STASH_DOWNLOAD_RESULTS_PATH", str(res_dir))
    monkeypatch.setattr(cm_module.settings, "UNSTASH_TIMEOUT_SECONDS", 2)

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    # Post-lock TOCTOU re-validation in unstash_crawl reads fresh blob — return
    # the still-stashed one so the path proceeds to the request-marker write.
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    captured = {"name": None, "content": None}

    async def _capture_marker():
        # Poll req_dir for any *.request file. The marker exists between the
        # write and the timeout-cleanup at the end of unstash_crawl, so we
        # snapshot its content the moment it appears.
        for _ in range(50):
            await asyncio.sleep(0.05)
            files = list(req_dir.glob("*.request"))
            if files:
                captured["name"] = files[0].name
                captured["content"] = files[0].read_text()
                return

    capture_task = asyncio.create_task(_capture_marker())

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)
    # The polling loop expired — 504 is expected
    assert exc.value.status_code == 504

    # Wait for the capture task to finish (it may have already captured)
    await capture_task

    assert captured["name"] == "test_id.request", (
        f"Marker file path mismatch: got {captured['name']!r}"
    )
    assert captured["content"] == "test_id", (
        f"Marker file content mismatch: got {captured['content']!r}"
    )
```

- [ ] **Step 7.2: Run the test**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py::test_unstash_writes_request_marker -v
```

Expected: PASS within ~2.5s.

- [ ] **Step 7.3: Run full stash suite (no regression)**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -10
```

Expected: 22 passed (same as Task 6 — replacing the test, not adding one).

- [ ] **Step 7.4: Commit (bilingual EN+FR)**

```
test(crawler-service): assert unstash request marker content via concrete capture

EN:
Replace the timeout-only assertion in test_unstash_writes_request_marker
with an async polling helper that snapshots the marker filename + body
content between the write and the timeout cleanup. Closes a coverage
gap flagged by the final code review: prior version passed even if the
marker write was a no-op. Spec §8 + follow-up §4.4 now both met.

FR:
Remplace l'assertion timeout-uniquement de
test_unstash_writes_request_marker par un helper async de polling qui
snapshot le nom de fichier du marker + le contenu du body entre
l'écriture et le cleanup du timeout. Ferme un gap de couverture
signalé par la revue de code finale : la version précédente passait
même si l'écriture du marker était un no-op. Spec §8 + follow-up §4.4
maintenant satisfaites.
```

```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" add \
    apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Post-Plan Verification

After all 7 tasks land:

```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -10
```

Expected: **22 passed** (18 prior + 4 new + 1 rewritten = 22 distinct tests after replacing the no-op).

```bash
cd apps-microservices/crawler-service
python -m pytest --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py --ignore=tests/test_routes_invalid_page.py -q 2>&1 | tail -5
```

Expected: full suite pass count holds.

Static grep:
```bash
git -C "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB" grep -nE "unstash_gcs_orphan_total|prometheus_client" -- apps-microservices/crawler-service/ docs/superpowers/specs/
```

Expected: matches ONLY in the original spec's Amendment section (historical reference). No active code references.

---

## Self-Review

**Spec coverage:**
- §2 goal "drop Prometheus claim + replace with grep prefix" → Task 1 (docs/spec) + Task 4 (log line).
- §2 goal "tarfile filter='data'" → Task 2.
- §2 goal "close TOCTOU races" → Task 5 (stash) + Task 6 (unstash).
- §2 goal "wrap pre-flight try/except" → Task 3.
- §2 goal "rewrite no-op test" → Task 7.
- §5.5 spec amendment → Task 1 Step 1.3.

All 6 spec goals mapped. ✓

**Placeholder scan:** No TBD / TODO / "implement later". Every code step shows the exact diff. ✓

**Type / name consistency:** `stash_lock_key`, `unstash_lock_key`, `lock_value`, `_release_ownership_lock(key, value)`, `fresh_job_info`, `UNSTASH_GCS_ORPHAN`, `cleanup_grace_expired` all spelled identically across Tasks 4-7. ✓

**Concurrency safety:** Each task touches one or two files. T5 and T6 are independent (stash side vs unstash side) but share the `_release_ownership_lock` helper — verified in T5 Step 5.2. ✓
