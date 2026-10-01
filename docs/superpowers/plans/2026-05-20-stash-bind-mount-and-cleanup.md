# Stash Bind-Mount Pre-Flight + Cleanup Keep-Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `_verify_bind_mount(path, label)` defensive helper raising 503 `BIND_MOUNT_MISSING` when a host bind-mount is missing (Issue B), and replace `stash_crawl`'s full-nuke cleanup with `_cleanup_data_keep_logs()` that mirrors `archive_crawl._cleanup_local_data` (Issue C).

**Architecture:** New `CrawlerManager._verify_bind_mount` method wraps `os.path.ismount(path)`. Called from `stash_crawl` (1 site) and `unstash_crawl` (2 sites) right after the existing post-lock TOCTOU re-validation, before any filesystem write. The cleanup phase in `stash_crawl` swaps `shutil.rmtree(job_storage_path)` for an inner `_cleanup_data_keep_logs()` function that walks the dir bottom-up, deleting only files NOT in the same `files_to_keep` set used by `archive_crawl`. Lock release stays in the existing `finally` block — no new error paths. Tests live in `test_crawler_manager.py` (helper) and `test_crawler_manager_stash.py` (endpoint integration + cleanup behavior).

**Tech Stack:** Python 3.10+, FastAPI HTTPException, pytest, monkeypatch, `os.path.ismount`, `os.walk` topdown=False.

**Spec:** `docs/superpowers/specs/2026-05-20-stash-bind-mount-and-cleanup-design.md` (commit `c42ce34e`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | modify | T0: add `_verify_bind_mount` method on `CrawlerManager`. T1: call from `stash_crawl`. T2: call twice from `unstash_crawl`. T3: replace `_delete_local()` with `_cleanup_data_keep_logs()`. |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | modify | T0: add `TestVerifyBindMount` class with 3 helper unit tests. |
| `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` | modify | T1: add autouse `mock_bind_mounts_present` fixture + 1 endpoint 503 test. T2: 1 endpoint 503 test for unstash. T3: update existing `test_stash_success_sets_timestamp_and_deletes_local` (rename + adjust assertions for keep-logs) + 1 new cleanup file-set test. |
| `docs/daemon_guide.md` | modify | T4: append two sections: "Troubleshooting: 503 BIND_MOUNT_MISSING" + "Recovery: stash tars trapped in pre-fix ephemeral container". |

---

## Task Sequence

5 tasks, sequential because all code edits land in the same `crawler_manager.py` file and tests in the same `test_crawler_manager_stash.py` file.

| Task | Touches | Depends on |
|---|---|---|
| T0 | manager.py (helper) + test_crawler_manager.py | — |
| T1 | manager.py (stash wiring) + test_crawler_manager_stash.py (fixture + 503 test + adjust existing) | T0 |
| T2 | manager.py (unstash wiring) + test_crawler_manager_stash.py (503 test) | T0, T1 |
| T3 | manager.py (cleanup) + test_crawler_manager_stash.py (cleanup test + adjust existing) | T1 (autouse fixture) |
| T4 | daemon_guide.md | — |

---

## Task 0: Add `_verify_bind_mount` helper + 3 helper unit tests

**Goal:** Add the `_verify_bind_mount(path, label)` method to `CrawlerManager`. Ship it with 3 unit tests proving it raises 503 for non-existent paths, ordinary dirs, and passes when `ismount` returns True. No call sites yet — helper-only commit.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert method on `CrawlerManager` class, alongside other helpers like `_acquire_ownership_lock`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (append new `TestVerifyBindMount` class at the end)

**Acceptance Criteria:**
- [ ] Method `CrawlerManager._verify_bind_mount(path: str, label: str) -> None` exists.
- [ ] Raises `HTTPException(status_code=503, detail={...})` when `os.path.ismount(path)` returns False.
- [ ] Returns None when `os.path.ismount(path)` returns True.
- [ ] Detail dict contains exactly the keys: `error_code`, `path`, `label`, `ops_action`, `hint`.
- [ ] `error_code` is the literal string `"BIND_MOUNT_MISSING"`.
- [ ] 3 unit tests pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py::TestVerifyBindMount -v` → 3 passed.

**Steps:**

- [ ] **Step 0.1: Locate insertion point for the helper**

Read the file and find the line containing `async def _acquire_ownership_lock`. The new helper goes **immediately before** it as a sibling method on `CrawlerManager`. Confirm imports already include `os` and `HTTPException, status` (they do — top of file).

- [ ] **Step 0.2: Add the helper method**

Insert this block right before the `async def _acquire_ownership_lock(self, ...)` definition:

```python
    def _verify_bind_mount(self, path: str, label: str) -> None:
        """Raise 503 BIND_MOUNT_MISSING if path is not a real mount point.

        Detects the silent-data-loss case where docker-compose volumes
        were added but the container was not recreated. Without this guard
        Python's os.makedirs creates an ephemeral in-container dir; data
        written there is invisible to host-side daemons and lost on
        container recreate.

        Detection: os.path.ismount(p) returns True only for bind-mounts
        and named volumes — False for ordinary dirs (or non-existent
        paths).
        """
        if not os.path.ismount(path):
            raise HTTPException(
                status_code=503,
                detail={
                    "error_code": "BIND_MOUNT_MISSING",
                    "path": path,
                    "label": label,
                    "ops_action": "docker-compose --profile crawling up -d --force-recreate crawler-service",
                    "hint": "Container was started before compose mount declaration; recreate required.",
                },
            )
```

- [ ] **Step 0.3: Append `TestVerifyBindMount` class to test file**

At the bottom of `apps-microservices/crawler-service/tests/test_crawler_manager.py`, append:

```python


class TestVerifyBindMount:
    """Defensive helper: raises 503 BIND_MOUNT_MISSING when stash/unstash
    target paths are not real bind-mounts. Catches the silent-data-loss
    case where docker-compose volumes were declared but the container was
    not recreated to pick them up (incident 2026-05-20 crawl 1958)."""

    def test_raises_503_when_path_is_ordinary_dir(self, tmp_path):
        from fastapi import HTTPException
        from app.core.crawler_manager import CrawlerManager

        cm = CrawlerManager()
        ordinary = tmp_path / "ephemeral"
        ordinary.mkdir()  # plain dir, NOT a mount

        with pytest.raises(HTTPException) as exc:
            cm._verify_bind_mount(str(ordinary), "test-label")

        assert exc.value.status_code == 503
        assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
        assert exc.value.detail["path"] == str(ordinary)
        assert exc.value.detail["label"] == "test-label"
        assert "force-recreate" in exc.value.detail["ops_action"]
        assert "hint" in exc.value.detail

    def test_raises_503_when_path_does_not_exist(self, tmp_path):
        from fastapi import HTTPException
        from app.core.crawler_manager import CrawlerManager

        cm = CrawlerManager()
        missing = tmp_path / "nonexistent"  # never created

        with pytest.raises(HTTPException) as exc:
            cm._verify_bind_mount(str(missing), "test-label")

        assert exc.value.status_code == 503
        assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"

    def test_returns_none_when_ismount_true(self, tmp_path, monkeypatch):
        """Simulate a real mount point by mocking os.path.ismount."""
        import os
        from app.core.crawler_manager import CrawlerManager

        cm = CrawlerManager()
        fake_mount = tmp_path / "mounted"
        fake_mount.mkdir()
        monkeypatch.setattr(os.path, "ismount", lambda p: str(p) == str(fake_mount))

        # Must not raise
        result = cm._verify_bind_mount(str(fake_mount), "test-label")
        assert result is None
```

- [ ] **Step 0.4: Run the 3 tests**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py::TestVerifyBindMount -v
```

Expected: 3 passed.

- [ ] **Step 0.5: Confirm no regression on existing crawler_manager tests**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py -v 2>&1 | tail -5
```

Expected: total passes (previous count + 3).

- [ ] **Step 0.6: Commit (bilingual EN+FR via COMMIT_EDITMSG)**

```bash
# Write commit message to .git/COMMIT_EDITMSG (Windows cp1252 hazard avoidance)
```

Write file `.git/COMMIT_EDITMSG` with this content:

```
feat(crawler-service): add _verify_bind_mount helper for stash/unstash preflight

EN:
Add CrawlerManager._verify_bind_mount(path, label) helper that raises
HTTPException 503 BIND_MOUNT_MISSING when os.path.ismount(path) is False.
Catches both non-existent paths and ordinary in-container dirs created
by os.makedirs() when the expected bind-mount is absent.

Detail payload: error_code=BIND_MOUNT_MISSING + path + label + ops_action
(force-recreate command) + hint. Operator can read the 503 and act
directly.

3 unit tests cover: ordinary dir rejection, non-existent path rejection,
mounted path pass-through (via monkeypatched ismount).

Helper-only commit; call sites added in follow-up tasks for stash_crawl
and unstash_crawl.

Spec: docs/superpowers/specs/2026-05-20-stash-bind-mount-and-cleanup-design.md

FR:
Ajout du helper CrawlerManager._verify_bind_mount(path, label) qui leve
HTTPException 503 BIND_MOUNT_MISSING quand os.path.ismount(path) est
False. Capture les chemins inexistants ET les dirs ordinaires in-container
crees par os.makedirs() quand le bind-mount attendu est absent.

Payload detail : error_code=BIND_MOUNT_MISSING + path + label +
ops_action (commande force-recreate) + hint. L'operateur peut lire le 503
et agir directement.

3 tests unitaires couvrent : rejet dir ordinaire, rejet chemin
inexistant, passage si chemin monte (via ismount monkeypatche).

Commit helper uniquement; sites d'appel ajoutes dans les taches de suivi
pour stash_crawl et unstash_crawl.
```

Then commit:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py \
        apps-microservices/crawler-service/tests/test_crawler_manager.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

If the graphify hook overwrites EDITMSG and lands a wrong message, fix with:

```bash
# Re-write .git/COMMIT_EDITMSG with the proper message above, then:
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG
```

Verify SHA + message:
```bash
git log -1 --format="%H %s"
```

---

## Task 1: Wire `_verify_bind_mount` into `stash_crawl` + autouse fixture + 503 integration test

**Goal:** Call `_verify_bind_mount(settings.STASH_SHARED_PATH, "stash upload")` from `stash_crawl` right after the existing post-lock TOCTOU re-validation block, before the disk pre-flight. Add an autouse pytest fixture in `test_crawler_manager_stash.py` so all existing happy-path tests get `ismount → True` automatically (no per-test changes needed). Add 1 new integration test for the 503 propagation.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert one line in `stash_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (add autouse fixture near the existing fixtures + 1 new test)

**Acceptance Criteria:**
- [ ] `stash_crawl` calls `self._verify_bind_mount(settings.STASH_SHARED_PATH, "stash upload")` after the TOCTOU `job_info = fresh_job_info` line, before the `try:` block that opens disk pre-flight.
- [ ] Autouse fixture `mock_bind_mounts_present` defined in `test_crawler_manager_stash.py` makes `os.path.ismount` return True by default for all tests in that file.
- [ ] New test `test_stash_crawl_rejects_when_stash_dir_not_mount` overrides ismount to False and asserts 503 BIND_MOUNT_MISSING + lock released.
- [ ] All previously-passing tests in `test_crawler_manager_stash.py` still pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5` → all passes (previous count + 1 new test).

**Steps:**

- [ ] **Step 1.1: Locate the post-TOCTOU block in `stash_crawl`**

Read `crawler_manager.py` and find the comment line `# Use the fresh blob from here on.` followed by `job_info = fresh_job_info` and then a blank line + `try:`. This is the insertion point.

- [ ] **Step 1.2: Insert the `_verify_bind_mount` call**

Replace this exact block:

```python
        # Use the fresh blob from here on.
        job_info = fresh_job_info

        try:
            stash_dir = settings.STASH_SHARED_PATH
```

With:

```python
        # Use the fresh blob from here on.
        job_info = fresh_job_info

        # --- Defensive bind-mount check (spec 2026-05-20 §4) ---
        # Rejects with 503 BIND_MOUNT_MISSING if /app/stash is not a real
        # bind-mount. Without this guard os.makedirs would create an
        # ephemeral in-container dir; tar would land in container overlay
        # FS, invisible to the host upload daemon (incident: crawl 1958).
        self._verify_bind_mount(settings.STASH_SHARED_PATH, "stash upload")

        try:
            stash_dir = settings.STASH_SHARED_PATH
```

- [ ] **Step 1.3: Add the autouse fixture in `test_crawler_manager_stash.py`**

Locate the existing `@pytest.fixture\ndef cm_instance` block near the top of `test_crawler_manager_stash.py`. **Immediately AFTER** that fixture (and before `base_job_info`), insert:

```python


@pytest.fixture(autouse=True)
def mock_bind_mounts_present(monkeypatch):
    """Default for this test module: os.path.ismount returns True.

    Without this, every test that exercises stash_crawl / unstash_crawl
    would hit the new _verify_bind_mount 503 check because tmp_path is
    not a real mount point. Tests that WANT to assert the 503 path can
    override with monkeypatch.setattr(os.path, "ismount", lambda p: False)
    inside the test body — local monkeypatch wins over autouse.
    """
    monkeypatch.setattr(os.path, "ismount", lambda p: True)
```

Confirm `import os` is already at the top of the file (it is — needed by existing tests).

- [ ] **Step 1.4: Add the 503 integration test**

Find the existing test `test_stash_blocks_already_stashed`. Insert the new test **immediately after it** (group with the other stash precondition rejection tests):

```python


@pytest.mark.asyncio
async def test_stash_crawl_rejects_when_stash_dir_not_mount(
    cm_instance, base_job_info, mock_cache_service, monkeypatch
):
    """Spec 2026-05-20 §4: bind-mount preflight rejects with 503 when
    STASH_SHARED_PATH is not a real mount point. Lock must be released
    by the existing finally block."""
    # All Redis mocks pass TOCTOU successfully
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    # Override autouse fixture: ismount returns False (no bind-mount)
    monkeypatch.setattr(os.path, "ismount", lambda p: False)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.stash_crawl(base_job_info)

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    assert exc.value.detail["label"] == "stash upload"
    # Lock released by finally (Lua eval invoked at least once)
    assert mock_cache_service.redis_client.eval.call_count >= 1
```

- [ ] **Step 1.5: Run the new test + full stash suite (no regression)**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager_stash.py::test_stash_crawl_rejects_when_stash_dir_not_mount -v
```

Expected: 1 passed.

```bash
python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5
```

Expected: previous count + 1 (22 → 23) all passing.

- [ ] **Step 1.6: Commit (bilingual EN+FR via COMMIT_EDITMSG)**

Write `.git/COMMIT_EDITMSG` with:

```
feat(crawler-service): stash_crawl bind-mount preflight 503 BIND_MOUNT_MISSING

EN:
Wire CrawlerManager._verify_bind_mount(STASH_SHARED_PATH, "stash upload")
into stash_crawl, called right after the post-lock TOCTOU re-validation
and before the disk pre-flight. Rejects with 503 BIND_MOUNT_MISSING when
/app/stash is not a real mount point — preventing the silent data loss
seen on 2026-05-20 (crawl 1958: 148MB tar trapped in container overlay
FS because compose volumes were edited but the container was not
recreated).

Existing finally block handles lock release on the 503 path.

New autouse fixture mock_bind_mounts_present in
test_crawler_manager_stash.py makes os.path.ismount default to True so
all existing happy-path tests continue to pass without per-test edits.
Tests that assert the 503 path locally override with
monkeypatch.setattr(os.path, "ismount", lambda p: False).

1 new integration test covers the 503 propagation + lock release.

FR:
Cable CrawlerManager._verify_bind_mount(STASH_SHARED_PATH, "stash upload")
dans stash_crawl, appele juste apres la re-validation TOCTOU post-lock
et avant le pre-flight disque. Rejette avec 503 BIND_MOUNT_MISSING quand
/app/stash n'est pas un point de montage reel — empechant la perte
silencieuse de donnees vue le 2026-05-20 (crawl 1958 : tar de 148 Mo
piege dans la couche overlay du conteneur car les volumes compose ont
ete edites sans recreate du conteneur).

Le bloc finally existant gere la liberation du lock sur le chemin 503.

Nouvelle fixture autouse mock_bind_mounts_present dans
test_crawler_manager_stash.py fait que os.path.ismount renvoie True par
defaut, donc tous les tests existants happy-path continuent a passer
sans edits par-test. Les tests qui veulent asserter le chemin 503
overrident localement avec monkeypatch.setattr(os.path, "ismount",
lambda p: False).

1 nouveau test d'integration couvre la propagation du 503 + la liberation
du lock.
```

Commit:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/app/core/crawler_manager.py \
        apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
# If graphify hook clobbered the message:
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG
git log -1 --format="%H %s"
```

---

## Task 2: Wire `_verify_bind_mount` into `unstash_crawl` (2 sites) + 503 integration test

**Goal:** Call `_verify_bind_mount` twice in `unstash_crawl` (once for `STASH_DOWNLOAD_REQUESTS_PATH`, once for `STASH_DOWNLOAD_RESULTS_PATH`) immediately after the existing post-lock TOCTOU block, before the `try:` that opens the request marker write. Add 1 integration test that asserts 503 propagation when either dir is not a mount.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (insert two lines in `unstash_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (1 new test)

**Acceptance Criteria:**
- [ ] `unstash_crawl` calls `self._verify_bind_mount(settings.STASH_DOWNLOAD_REQUESTS_PATH, "unstash requests")` AND `self._verify_bind_mount(settings.STASH_DOWNLOAD_RESULTS_PATH, "unstash results")` after the TOCTOU re-validation block, before the request-marker write.
- [ ] New test `test_unstash_crawl_rejects_when_dir_not_mount` asserts 503 + lock release.
- [ ] All previously-passing tests still pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5` → all passes (23 → 24).

**Steps:**

- [ ] **Step 2.1: Locate the post-TOCTOU block in `unstash_crawl`**

Find this exact block in `crawler_manager.py`:

```python
        # Use the fresh blob from here on.
        job_info = fresh_job_info

        requests_dir = settings.STASH_DOWNLOAD_REQUESTS_PATH
        results_dir = settings.STASH_DOWNLOAD_RESULTS_PATH
```

- [ ] **Step 2.2: Insert the two `_verify_bind_mount` calls**

Replace with:

```python
        # Use the fresh blob from here on.
        job_info = fresh_job_info

        # --- Defensive bind-mount check (spec 2026-05-20 §4) ---
        # Rejects with 503 BIND_MOUNT_MISSING if either stash download dir
        # is not a real bind-mount. Without these guards os.makedirs would
        # create ephemeral in-container dirs; .request marker would never
        # reach the host daemon and unstash would hang until UNSTASH_TIMEOUT.
        self._verify_bind_mount(settings.STASH_DOWNLOAD_REQUESTS_PATH, "unstash requests")
        self._verify_bind_mount(settings.STASH_DOWNLOAD_RESULTS_PATH, "unstash results")

        requests_dir = settings.STASH_DOWNLOAD_REQUESTS_PATH
        results_dir = settings.STASH_DOWNLOAD_RESULTS_PATH
```

- [ ] **Step 2.3: Add the integration test**

Locate the existing test `test_unstash_blocks_not_stashed`. Insert the new test **immediately after it**:

```python


@pytest.mark.asyncio
async def test_unstash_crawl_rejects_when_dir_not_mount(
    cm_instance, stashed_job_info, mock_cache_service, monkeypatch
):
    """Spec 2026-05-20 §4: bind-mount preflight rejects with 503 when
    either STASH_DOWNLOAD_REQUESTS_PATH or STASH_DOWNLOAD_RESULTS_PATH is
    not a real mount point. Lock must be released by the existing
    finally block."""
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(stashed_job_info))

    # Override autouse fixture: ismount returns False
    monkeypatch.setattr(os.path, "ismount", lambda p: False)

    with pytest.raises(HTTPException) as exc:
        await cm_instance.unstash_crawl(stashed_job_info)

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
    # First call site is the requests dir — that's what 503s
    assert exc.value.detail["label"] == "unstash requests"
    # Lock released
    assert mock_cache_service.redis_client.eval.call_count >= 1
```

- [ ] **Step 2.4: Run the test + full suite**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager_stash.py::test_unstash_crawl_rejects_when_dir_not_mount -v
```

Expected: 1 passed.

```bash
python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5
```

Expected: 24 passed.

- [ ] **Step 2.5: Commit (bilingual EN+FR)**

Write `.git/COMMIT_EDITMSG`:

```
feat(crawler-service): unstash_crawl bind-mount preflight 503 BIND_MOUNT_MISSING

EN:
Wire two CrawlerManager._verify_bind_mount calls into unstash_crawl —
one for STASH_DOWNLOAD_REQUESTS_PATH (label "unstash requests"), one
for STASH_DOWNLOAD_RESULTS_PATH (label "unstash results"). Both fire
immediately after the post-lock TOCTOU re-validation, before the
.request marker write. The first failure shortcircuits, so the label
tells ops which dir is missing.

Without these guards an ephemeral in-container dir would absorb the
.request marker; the host download daemon would never see it and
unstash would hang until UNSTASH_TIMEOUT_SECONDS (300s) before
returning 504. The 503 fires immediately with operator-actionable
detail.

Existing finally block handles lock release.

1 new integration test covers the 503 propagation + lock release for
unstash.

FR:
Cable deux appels CrawlerManager._verify_bind_mount dans unstash_crawl
— un pour STASH_DOWNLOAD_REQUESTS_PATH (label "unstash requests"), un
pour STASH_DOWNLOAD_RESULTS_PATH (label "unstash results"). Les deux
tirent juste apres la re-validation TOCTOU post-lock, avant l'ecriture
du marker .request. Le premier echec court-circuite, donc le label dit
a l'ops quel dir manque.

Sans ces gardes un dir ephemere in-container absorberait le marker
.request ; le daemon de download host ne le verrait jamais et l'unstash
hangerait jusqu'a UNSTASH_TIMEOUT_SECONDS (300s) avant de renvoyer 504.
Le 503 tire immediatement avec un detail actionable par l'operateur.

Le bloc finally existant gere la liberation du lock.

1 nouveau test d'integration couvre la propagation du 503 + la liberation
du lock pour unstash.
```

Commit:

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py \
        apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
# Amend if graphify hook clobbers:
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG
git log -1 --format="%H %s"
```

---

## Task 3: Replace `_delete_local` with `_cleanup_data_keep_logs` + update existing fixture + 1 new cleanup test

**Goal:** Swap the full-nuke cleanup in `stash_crawl` for an `os.walk` bottom-up pass that mirrors `archive_crawl._cleanup_local_data`: delete data files, keep logs + markers, keep the root storage dir. Update the existing `test_stash_success_sets_timestamp_and_deletes_local` (which previously asserted the storage_path was fully gone) to assert the new keep-logs invariant. Add 1 dedicated test that creates a richer fixture (kept files + data files in subdirs) and asserts the exact post-cleanup file set.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (replace the `_delete_local` block in `stash_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager_stash.py` (update `base_job_info` fixture to seed both a kept file + a data file, update `test_stash_success_sets_timestamp_and_deletes_local` assertions, add new `test_stash_keeps_logs_and_markers_on_cleanup`)

**Acceptance Criteria:**
- [ ] `stash_crawl` invokes `_cleanup_data_keep_logs()` (replacing `_delete_local`) — same `files_to_keep` set as `archive_crawl._cleanup_local_data` lines 1735-1739.
- [ ] After stash, `crawler.log` and `_completion_marker.json` still exist on disk; data files (e.g. `dataset.json`) deleted.
- [ ] Root `job_storage_path` directory still exists (not removed).
- [ ] `test_stash_success_sets_timestamp_and_deletes_local` renamed to `test_stash_success_sets_timestamp_and_keeps_logs` with updated assertions.
- [ ] New test `test_stash_keeps_logs_and_markers_on_cleanup` passes.
- [ ] All other stash tests still pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5` → 24 → 25 passed (renamed test still counted; +1 new).

**Steps:**

- [ ] **Step 3.1: Locate the `_delete_local` block in `stash_crawl`**

Find this exact block in `crawler_manager.py`:

```python
            # --- Delete local crawl storage dir (safe to fail — data is in the tar) ---
            try:
                def _delete_local():
                    if os.path.isdir(job_storage_path):
                        shutil.rmtree(job_storage_path)
                await anyio.to_thread.run_sync(_delete_local)
                logger.info(f"Deleted local storage for stashed crawl '{crawl_id}'.")
            except Exception as e:
                logger.warning(f"Local cleanup failed for stashed '{crawl_id}' (tar is safe): {e}")
```

- [ ] **Step 3.2: Replace with `_cleanup_data_keep_logs`**

Replace with:

```python
            # --- Cleanup data files; keep logs + markers (spec 2026-05-20 §5) ---
            # Mirrors archive_crawl._cleanup_local_data so operator UX is
            # consistent: ops can peek at logs locally without restoring via
            # unstash. The tar contains everything; unstash restore is
            # idempotent over kept files.
            try:
                def _cleanup_data_keep_logs():
                    files_to_keep = {
                        'crawler.log', '_callback_payload.json',
                        '_completion_marker.json', '_status_snapshot.json',
                        '_exit_reason.json', '_update_report.json',
                        'update_stats.json',
                        'timing.jsonl', 'timing-summary.json',
                    }
                    if not os.path.isdir(job_storage_path):
                        return
                    for root, dirs, files in os.walk(job_storage_path, topdown=False):
                        for name in files:
                            if name not in files_to_keep:
                                try:
                                    os.remove(os.path.join(root, name))
                                except OSError:
                                    pass
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                            except OSError:
                                pass  # non-empty (kept file inside) → leave dir

                await anyio.to_thread.run_sync(_cleanup_data_keep_logs)
                logger.info(f"Cleaned data (kept logs) for stashed crawl '{crawl_id}'.")
            except Exception as e:
                logger.warning(f"Data cleanup failed for stashed '{crawl_id}' (tar is safe): {e}")
```

- [ ] **Step 3.3: Update the `base_job_info` fixture in `test_crawler_manager_stash.py`**

Find the existing fixture:

```python
@pytest.fixture
def base_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    (storage / "dataset.json").write_text('{"records": [1,2,3]}')
    return {
        "crawl_id": "test_id",
        "status": "failed",
        "storage_path": str(storage),
        "domain": "example.com",
    }
```

Replace with:

```python
@pytest.fixture
def base_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    # Seed both a kept file (log) and a data file so cleanup-keep-logs
    # behavior is exercised by every test using this fixture.
    (storage / "crawler.log").write_text("log content")
    (storage / "dataset.json").write_text('{"records": [1,2,3]}')
    return {
        "crawl_id": "test_id",
        "status": "failed",
        "storage_path": str(storage),
        "domain": "example.com",
    }
```

- [ ] **Step 3.4: Update the existing success test**

Find this test:

```python
@pytest.mark.asyncio
async def test_stash_success_sets_timestamp_and_deletes_local(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    result = await cm_instance.stash_crawl(base_job_info)

    assert result["status"] == "stashing"
    assert result["crawl_id"] == "test_id"
    assert result["stash_path"] == "gs://test-bucket/stash/test_id.tar.gz"
    assert "stashed_at" in result

    # Verify tar created in /app/stash + integrity
    final_tar = stash_dir / "test_id.tar.gz"
    assert final_tar.exists(), "Tar should exist in stash dir"
    with tarfile.open(final_tar, 'r:gz') as t:
        assert any("dataset.json" in n for n in t.getnames())

    # Verify local storage deleted
    assert not os.path.exists(base_job_info["storage_path"])

    # Verify Redis HSET (stashed_at set on Redis blob)
    last_call = mock_cache_service.set_json.call_args
    written = last_call[0][1]
    assert "stashed_at" in written
```

Replace with (renamed + assertions updated for keep-logs):

```python
@pytest.mark.asyncio
async def test_stash_success_sets_timestamp_and_keeps_logs(cm_instance, base_job_info, mock_cache_service, monkeypatch, tmp_path):
    """Happy-path stash: tar created in stash dir, Redis stashed_at set,
    DATA files deleted from storage but LOG files kept (spec 2026-05-20 §5)."""
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )

    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(base_job_info))

    result = await cm_instance.stash_crawl(base_job_info)

    assert result["status"] == "stashing"
    assert result["crawl_id"] == "test_id"
    assert result["stash_path"] == "gs://test-bucket/stash/test_id.tar.gz"
    assert "stashed_at" in result

    # Tar present in stash dir, contains both seeded files
    final_tar = stash_dir / "test_id.tar.gz"
    assert final_tar.exists(), "Tar should exist in stash dir"
    with tarfile.open(final_tar, 'r:gz') as t:
        names = t.getnames()
        assert any("dataset.json" in n for n in names)
        assert any("crawler.log" in n for n in names)

    # Keep-logs behavior: storage dir still exists, log kept, data gone
    storage_path = base_job_info["storage_path"]
    assert os.path.isdir(storage_path), "storage dir should remain (kept files inside)"
    assert (Path(storage_path) / "crawler.log").exists(), "crawler.log should be kept"
    assert not (Path(storage_path) / "dataset.json").exists(), "dataset.json should be deleted"

    # Redis HSET wrote stashed_at
    last_call = mock_cache_service.set_json.call_args
    written = last_call[0][1]
    assert "stashed_at" in written
```

If `Path` is not imported in the test file, add `from pathlib import Path` to the top of the imports block.

- [ ] **Step 3.5: Add new dedicated cleanup test**

At the very bottom of `test_crawler_manager_stash.py`, append:

```python


@pytest.mark.asyncio
async def test_stash_keeps_logs_and_markers_on_cleanup(
    cm_instance, mock_cache_service, monkeypatch, tmp_path
):
    """Dedicated cleanup-scope test: a richer storage tree with multiple
    kept-class files (log + completion marker) AND data files (root +
    nested subdir) exercises the full files_to_keep set + os.walk
    bottom-up subdir rmdir."""
    stash_dir = tmp_path / "stash"
    stash_dir.mkdir()

    storage = tmp_path / "crawl_data"
    storage.mkdir()
    # 2 kept files at root
    (storage / "crawler.log").write_text("log content")
    (storage / "_completion_marker.json").write_text('{"final_status":"finished"}')
    # 1 data file at root
    (storage / "dataset.json").write_text('{"records":[1,2,3]}')
    # 1 data file in nested subdir
    sub = storage / "storage" / "datasets"
    sub.mkdir(parents=True)
    (sub / "000001.json").write_text("data")

    job_info = {
        "crawl_id": "rich_test_id",
        "status": "failed",
        "storage_path": str(storage),
        "domain": "example.com",
    }

    monkeypatch.setattr(cm_module.settings, "STASH_SHARED_PATH", str(stash_dir))
    monkeypatch.setattr(cm_module.settings, "GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        cm_instance,
        "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0, "file_count": 0, "oldest_file_age_seconds": None},
    )
    mock_cache_service.redis_client.exists = AsyncMock(return_value=0)
    mock_cache_service.redis_client.set = AsyncMock(return_value=True)
    mock_cache_service.redis_client.eval = AsyncMock(return_value=1)
    mock_cache_service.get_json = AsyncMock(return_value=dict(job_info))

    await cm_instance.stash_crawl(job_info)

    # Kept
    assert (storage / "crawler.log").exists()
    assert (storage / "_completion_marker.json").exists()
    # Deleted (root-level data file)
    assert not (storage / "dataset.json").exists()
    # Deleted (nested data file + its empty subdirs)
    assert not (sub / "000001.json").exists()
    assert not sub.exists(), "empty data subdir should be rmdir'd"
    # Root storage dir kept (contains 2 kept files)
    assert storage.exists()
```

- [ ] **Step 3.6: Run the tests**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager_stash.py::test_stash_success_sets_timestamp_and_keeps_logs tests/test_crawler_manager_stash.py::test_stash_keeps_logs_and_markers_on_cleanup -v
```

Expected: 2 passed.

```bash
python -m pytest tests/test_crawler_manager_stash.py -v 2>&1 | tail -5
```

Expected: 25 passed total.

- [ ] **Step 3.7: Commit (bilingual EN+FR)**

Write `.git/COMMIT_EDITMSG`:

```
fix(crawler-service): stash keep logs+markers like archive_crawl

EN:
Replace stash_crawl's shutil.rmtree(job_storage_path) with
_cleanup_data_keep_logs() that mirrors archive_crawl._cleanup_local_data:
walk job_storage_path bottom-up, delete files NOT in files_to_keep, try
os.rmdir on emptied subdirs. Same files_to_keep set as archive
(crawler.log, _callback_payload.json, _completion_marker.json,
_status_snapshot.json, _exit_reason.json, _update_report.json,
update_stats.json, timing.jsonl, timing-summary.json).

Operator can now peek at logs + markers locally without restoring via
unstash. Restore via unstash is idempotent: tarfile.extractall
overwrites kept files with the tar's copies (same content).

Update existing happy-path test:
- Renamed test_stash_success_sets_timestamp_and_deletes_local ->
  test_stash_success_sets_timestamp_and_keeps_logs.
- base_job_info fixture now seeds both crawler.log (kept) and
  dataset.json (deleted).
- Assertions check log kept + data deleted + root dir kept.

Add 1 new test test_stash_keeps_logs_and_markers_on_cleanup that
exercises a richer tree (root kept files + root data file + nested
data file in subdir) to confirm the full files_to_keep set + bottom-up
rmdir works end-to-end.

FR:
Remplace le shutil.rmtree(job_storage_path) de stash_crawl par
_cleanup_data_keep_logs() qui replique archive_crawl._cleanup_local_data :
walk job_storage_path bottom-up, supprime les fichiers PAS dans
files_to_keep, tente os.rmdir sur les sous-dirs vides. Meme set
files_to_keep que archive (crawler.log, _callback_payload.json,
_completion_marker.json, _status_snapshot.json, _exit_reason.json,
_update_report.json, update_stats.json, timing.jsonl,
timing-summary.json).

L'operateur peut maintenant inspecter logs + markers localement sans
restaurer via unstash. Le restore via unstash est idempotent :
tarfile.extractall ecrase les fichiers conserves avec ceux du tar (meme
contenu).

Mise a jour du test happy-path existant :
- Renomme test_stash_success_sets_timestamp_and_deletes_local ->
  test_stash_success_sets_timestamp_and_keeps_logs.
- La fixture base_job_info seede maintenant a la fois crawler.log
  (conserve) et dataset.json (supprime).
- Assertions verifient log conserve + data supprime + dir racine conserve.

Ajout d'1 nouveau test test_stash_keeps_logs_and_markers_on_cleanup qui
exerce un arbre plus riche (fichiers kept racine + fichier data racine +
fichier data dans sous-dir imbrique) pour confirmer que le full set
files_to_keep + le rmdir bottom-up fonctionne end-to-end.
```

Commit:

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py \
        apps-microservices/crawler-service/tests/test_crawler_manager_stash.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG  # if hook clobbered
git log -1 --format="%H %s"
```

---

## Task 4: Runbook in `docs/daemon_guide.md`

**Goal:** Append two ops-facing sections to `docs/daemon_guide.md`: troubleshooting for the new 503 `BIND_MOUNT_MISSING`, and recovery procedure for tars trapped in pre-fix ephemeral container layers (verbatim runbook the user followed to rescue crawl 1958).

**Files:**
- Modify: `docs/daemon_guide.md` (append two sections at the end)

**Acceptance Criteria:**
- [ ] `docs/daemon_guide.md` contains a section titled `## Troubleshooting: 503 BIND_MOUNT_MISSING`.
- [ ] `docs/daemon_guide.md` contains a section titled `## Recovery: stash tars trapped in pre-fix ephemeral container`.
- [ ] Both sections include verifiable bash commands (no placeholders).
- [ ] `grep -c "BIND_MOUNT_MISSING" docs/daemon_guide.md` returns ≥1.

**Verify:** `grep -c "BIND_MOUNT_MISSING" docs/daemon_guide.md && grep -c "Recovery: stash tars trapped" docs/daemon_guide.md` → both ≥1.

**Steps:**

- [ ] **Step 4.1: Append the two sections**

Open `docs/daemon_guide.md`, jump to the end of the file, append:

```markdown


## Troubleshooting: 503 `BIND_MOUNT_MISSING`

Returned by `POST /stash/{id}` or `POST /unstash/{id}` when one of the
stash bind-mounts (`/app/stash`, `/app/gcs-stash-requests`,
`/app/gcs-stash-downloads`) is not a real mount point. Indicates the
running container was started BEFORE `docker-compose.yaml` declared
those mounts (commit `14a02524`). Docker-compose only applies new volume
declarations at **container creation** — a plain `docker-compose up -d`
after editing the file does not bridge them.

**Response body:**

```json
{
  "detail": {
    "error_code": "BIND_MOUNT_MISSING",
    "path": "/app/stash",
    "label": "stash upload",
    "ops_action": "docker-compose --profile crawling up -d --force-recreate crawler-service",
    "hint": "Container was started before compose mount declaration; recreate required."
  }
}
```

### Fix

```bash
# 1. Stop the service
docker-compose --profile crawling stop crawler-service

# 2. Recreate (rebuilds container with the latest compose mounts)
docker-compose --profile crawling up -d --force-recreate crawler-service

# 3. Verify all three stash mounts are bridged
docker inspect $(docker ps -qf name=crawler-service | head -1) \
  --format='{{range .Mounts}}{{.Destination}} ({{.Type}}){{println}}{{end}}' \
  | grep -E "stash|gcs-stash"
```

Expected output:

```
/app/stash (bind)
/app/gcs-stash-requests (bind)
/app/gcs-stash-downloads (bind)
```

If any line is missing, the recreate did not apply the latest compose
file. Verify the commit `14a02524` is pulled and re-run.

## Recovery: stash tars trapped in pre-fix ephemeral container

If `POST /stash/{id}` returned 202 BEFORE the recreate above, the tar
lives in the container's overlay filesystem at `/app/stash/{id}.tar.gz`
instead of on the host bind-mount. Rescue it BEFORE recreating (which
would destroy the layer):

```bash
CONTAINER=$(docker ps -qf name=crawler-service | head -1)

# Confirm the tar is in the ephemeral /app/stash
docker exec "$CONTAINER" ls -la /app/stash/

# Rescue to the host (replace {id} with the actual crawl_id)
docker cp "$CONTAINER":/app/stash/{id}.tar.gz ./recovered_{id}.tar.gz

# Now recreate the container (Troubleshooting section above)

# After recreate, copy back into the bind-mount source dir
cp ./recovered_{id}.tar.gz \
   ./apps-microservices/crawler-service/crawler_stash/{id}.tar.gz

# The upload daemon picks it up within CHECK_INTERVAL (60s). Verify:
gcloud storage ls "gs://${GCS_BUCKET_NAME}/stash/{id}.tar.gz"
```

Redis `stashed_at` was set by the original `POST /stash/{id}` call, so
`POST /unstash/{id}` will succeed once the tar reaches GCS.
```

- [ ] **Step 4.2: Verify the docs**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
grep -c "BIND_MOUNT_MISSING" docs/daemon_guide.md
grep -c "Recovery: stash tars trapped" docs/daemon_guide.md
```

Expected: both output ≥1.

- [ ] **Step 4.3: Commit (bilingual EN+FR)**

Write `.git/COMMIT_EDITMSG`:

```
docs(daemon-guide): troubleshooting 503 BIND_MOUNT_MISSING + tar recovery

EN:
Add two ops-facing sections to docs/daemon_guide.md:

1. "Troubleshooting: 503 BIND_MOUNT_MISSING" — explains when the new
   503 fires (container created before compose volume declaration), the
   exact response body shape, and the docker-compose --force-recreate
   procedure with a verification grep on docker inspect output.

2. "Recovery: stash tars trapped in pre-fix ephemeral container" — the
   docker cp rescue procedure the user followed for crawl 1958
   (148MB tar stuck in container overlay FS). Verbatim commands to
   confirm tar presence, copy out, recreate, copy back, and verify
   GCS arrival via gcloud storage ls. Notes that Redis stashed_at is
   already set so unstash works once tar reaches GCS.

FR:
Ajout de deux sections ops-facing a docs/daemon_guide.md :

1. « Troubleshooting: 503 BIND_MOUNT_MISSING » — explique quand le
   nouveau 503 tire (conteneur cree avant la declaration de volume
   compose), la shape exacte du body de reponse, et la procedure
   docker-compose --force-recreate avec un grep de verification sur
   la sortie docker inspect.

2. « Recovery: stash tars trapped in pre-fix ephemeral container » —
   la procedure docker cp de sauvetage que l'utilisateur a suivie pour
   le crawl 1958 (tar de 148 Mo coince dans le FS overlay du conteneur).
   Commandes verbatim pour confirmer la presence du tar, copier
   dehors, recreate, copier dedans, et verifier l'arrivee GCS via
   gcloud storage ls. Note que Redis stashed_at est deja positionne
   donc unstash fonctionne une fois le tar arrive en GCS.
```

Commit:

```bash
git add docs/daemon_guide.md
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG  # if hook clobbered
git log -1 --format="%H %s"
```

---

## Post-Plan Verification

After all 5 tasks land:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service
python -m pytest tests/test_crawler_manager.py tests/test_crawler_manager_stash.py 2>&1 | tail -5
```

Expected: **all passes** (helper 3 + stash 25 = 28 stash-specific tests; total file count unchanged for crawler_manager.py existing tests).

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
grep -nE "BIND_MOUNT_MISSING|_cleanup_data_keep_logs|_verify_bind_mount" \
  apps-microservices/crawler-service/app/core/crawler_manager.py
```

Expected: helper definition (1) + 3 call sites (1 stash + 2 unstash) + cleanup function definition (1) + BIND_MOUNT_MISSING in helper detail (1) = ≥6 matches.

```bash
git log --oneline c42ce34e..HEAD
```

Expected: 5 commits, one per task, message subjects matching the bilingual templates above.

---

## Self-Review

**1. Spec coverage:**

| Spec section | Plan task | Notes |
|---|---|---|
| §4 helper signature + detail shape | T0 | exact helper code matches spec §4 |
| §4 call sites stash (1) | T1 | one call after TOCTOU before disk preflight |
| §4 call sites unstash (2) | T2 | two calls after TOCTOU before .request write |
| §5 `_cleanup_data_keep_logs` | T3 | files_to_keep set, os.walk bottom-up |
| §6 helper unit tests (3) | T0 | TestVerifyBindMount class |
| §6 endpoint integration tests (2) | T1 + T2 | one each |
| §6 cleanup file-set test (1) | T3 | new test + existing test rename |
| §7 runbook docs/daemon_guide.md | T4 | both sections present |

All 6 unit tests promised in spec accounted for: 3 helper (T0) + 1 stash 503 (T1) + 1 unstash 503 (T2) + 1 cleanup file-set (T3) = 6. The existing-test rename in T3 is bookkeeping, not new coverage.

**2. Placeholder scan:** No TBD/TODO/"implement later". Every step shows the exact code. Verify commands are exact.

**3. Type/name consistency:**
- `_verify_bind_mount(path: str, label: str) -> None` — same signature in T0, T1, T2.
- `BIND_MOUNT_MISSING` literal — same across T0, T1, T2, T4.
- Labels: `"stash upload"` (T1), `"unstash requests"` and `"unstash results"` (T2) — match spec §4 table.
- `_cleanup_data_keep_logs` — same name in T3 spec section and plan task.
- Autouse fixture `mock_bind_mounts_present` — used implicitly by T1, T2, T3.

---

## Task ID Mapping

This plan creates 5 native tasks. After the plan write, native tasks will be created with the metadata fence pattern. Mapping :

| Plan Task | Native Task |
|---|---|
| T0 — helper | (to be created) |
| T1 — stash wiring | (to be created, depends on T0) |
| T2 — unstash wiring | (to be created, depends on T0, T1) |
| T3 — cleanup keep-logs | (to be created, depends on T1) |
| T4 — runbook | (to be created, independent) |
