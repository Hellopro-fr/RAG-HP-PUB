# Archive Pre-flight Disk Space Check + Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent mid-archive `OSError: No space left on device` by measuring the source directory, checking free disk space before `shutil.make_archive`, rejecting with a clear 503 when insufficient, and logging disk state on every archive attempt.

**Architecture:** Add two pure helper methods to `CrawlerManager` (`_estimate_archive_required_bytes`, `_get_archives_disk_state`). Insert a pre-flight check in `archive_crawl` after the GCS fallback but before the status snapshot + archive creation. Enrich the existing failure-path `except Exception` block with a second disk-state log. Fail-open on helper errors — never block archiving because measurement itself failed.

**Tech Stack:** Python 3.12, `shutil.disk_usage`, `os.walk`, `os.listdir`, `os.path.getmtime`, pytest + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-04-18-archive-disk-space-preflight-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | MODIFY | Add 2 helper methods on `CrawlerManager`; insert pre-flight check in `archive_crawl`; enrich failure-path logging |
| `apps-microservices/crawler-service/tests/test_crawler_manager.py` | MODIFY | Add `TestArchiveDiskPreflight` class with unit tests for helpers + preflight rejection + fail-open |
| `apps-microservices/crawler-service/CLAUDE.md` | MODIFY | Document the pre-flight behavior, 503 response, and fail-open policy |

---

### Task 1: Add helper methods `_estimate_archive_required_bytes` and `_get_archives_disk_state`

**Goal:** Pure, testable helpers that measure the source directory and inspect the archives volume. Used by both the pre-flight check and diagnostic logging.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (add two methods on `CrawlerManager`, after `archive_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add test class for these helpers)

**Acceptance Criteria:**
- [ ] `_estimate_archive_required_bytes(job_storage_path)` returns `int(total * 1.5)` when source dir exists
- [ ] Returns `0` when source dir is missing (caller applies floor)
- [ ] `_get_archives_disk_state(archives_dir)` returns dict with `free_bytes`, `total_bytes`, `used_pct`, `file_count`, `oldest_file_age_seconds`
- [ ] `file_count` excludes files in the `.staging/` subdirectory (only top-level `*.tar.gz`)
- [ ] `oldest_file_age_seconds` returns `None` when archives_dir is empty
- [ ] Both helpers fail-open: on exception, return a safe fallback + log a warning (never raise)
- [ ] Unit tests pass

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestArchiveDiskPreflight -v` → all tests PASS

**Steps:**

- [ ] **Step 1: Add the helper methods to `CrawlerManager`**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, locate the `archive_crawl` method. Immediately **before** the `archive_crawl` method definition (around line 1380, where the docstring `"""Archives a finished crawl..."""` begins), insert these two new methods:

```python
    def _estimate_archive_required_bytes(self, job_storage_path: str) -> int:
        """Walk the source directory, sum file sizes, return size * 1.5 (gzip + safety margin).
        Returns 0 on any error — the caller is expected to apply a floor (1 GB).
        Fail-open: never raises."""
        try:
            if not os.path.isdir(job_storage_path):
                logger.warning(f"Source dir not found for size estimation: '{job_storage_path}'")
                return 0
            total = 0
            for root, _dirs, files in os.walk(job_storage_path):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        continue  # broken symlink or permission denied; skip
            return int(total * 1.5)
        except Exception as e:
            logger.warning(f"Could not estimate required bytes for '{job_storage_path}': {e}")
            return 0

    def _get_archives_disk_state(self, archives_dir: str) -> dict:
        """Collect diagnostics about the archives volume.
        Returns a dict with free_bytes, total_bytes, used_pct, file_count,
        oldest_file_age_seconds. Fail-open: on any error, returns a degraded dict
        with None values and logs a warning (never raises)."""
        degraded = {
            "free_bytes": None,
            "total_bytes": None,
            "used_pct": None,
            "file_count": None,
            "oldest_file_age_seconds": None,
        }
        try:
            usage = shutil.disk_usage(archives_dir)
            total_bytes = usage.total
            free_bytes = usage.free
            used_pct = round(100.0 * (total_bytes - free_bytes) / total_bytes, 2) if total_bytes else None

            file_count = 0
            oldest_mtime = None
            try:
                for name in os.listdir(archives_dir):
                    if not name.endswith(".tar.gz"):
                        continue
                    path = os.path.join(archives_dir, name)
                    if not os.path.isfile(path):
                        continue  # skip dirs like .staging/
                    file_count += 1
                    try:
                        mtime = os.path.getmtime(path)
                        if oldest_mtime is None or mtime < oldest_mtime:
                            oldest_mtime = mtime
                    except OSError:
                        continue
            except FileNotFoundError:
                pass  # archives_dir doesn't exist yet; count stays 0

            oldest_age = int(time.time() - oldest_mtime) if oldest_mtime is not None else None

            return {
                "free_bytes": free_bytes,
                "total_bytes": total_bytes,
                "used_pct": used_pct,
                "file_count": file_count,
                "oldest_file_age_seconds": oldest_age,
            }
        except Exception as e:
            logger.warning(f"Could not get disk state for '{archives_dir}': {e}")
            return degraded
```

Verify these imports already exist at the top of the file:
- `import os` ✓ (already present)
- `import shutil` ✓ (already present)
- `import time` ✓ (already present)

- [ ] **Step 2: Add the test class at the end of `test_crawler_manager.py`**

Append the following test class to `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python


import time
from unittest.mock import MagicMock, patch


class TestArchiveDiskPreflight:
    """Helpers for the pre-flight disk space check before archiving."""

    def _manager(self):
        """Instantiate CrawlerManager without running __init__ (avoids Redis setup)."""
        from app.core.crawler_manager import CrawlerManager
        return CrawlerManager.__new__(CrawlerManager)

    def test_estimate_returns_size_times_1_5(self, tmp_path):
        """Source dir with 1000 bytes total → estimate returns 1500 bytes."""
        (tmp_path / "a.txt").write_bytes(b"x" * 600)
        (tmp_path / "b.txt").write_bytes(b"y" * 400)
        mgr = self._manager()

        result = mgr._estimate_archive_required_bytes(str(tmp_path))

        assert result == 1500

    def test_estimate_returns_zero_when_source_missing(self, tmp_path):
        """Missing source dir → return 0 (caller applies floor)."""
        mgr = self._manager()

        result = mgr._estimate_archive_required_bytes(str(tmp_path / "does_not_exist"))

        assert result == 0

    def test_estimate_fail_open_on_exception(self):
        """If os.walk raises, return 0 and do not propagate."""
        mgr = self._manager()

        with patch("app.core.crawler_manager.os.walk", side_effect=RuntimeError("fs error")):
            with patch("app.core.crawler_manager.os.path.isdir", return_value=True):
                result = mgr._estimate_archive_required_bytes("/fake")

        assert result == 0

    def test_disk_state_returns_expected_keys(self, tmp_path):
        """Happy path: archives_dir has one .tar.gz → state dict populated."""
        (tmp_path / "abc.tar.gz").write_bytes(b"z" * 100)
        mgr = self._manager()

        state = mgr._get_archives_disk_state(str(tmp_path))

        assert set(state.keys()) == {
            "free_bytes", "total_bytes", "used_pct", "file_count", "oldest_file_age_seconds"
        }
        assert state["file_count"] == 1
        assert state["oldest_file_age_seconds"] is not None
        assert state["free_bytes"] is not None
        assert state["total_bytes"] is not None
        assert state["used_pct"] is not None

    def test_disk_state_excludes_staging_subdirectory(self, tmp_path):
        """Files in .staging/ must NOT be counted — those are in-progress tmp files."""
        staging = tmp_path / ".staging"
        staging.mkdir()
        (staging / "in_progress.tar.gz").write_bytes(b"x" * 100)
        (tmp_path / "finished.tar.gz").write_bytes(b"y" * 100)
        mgr = self._manager()

        state = mgr._get_archives_disk_state(str(tmp_path))

        assert state["file_count"] == 1  # only the top-level finished.tar.gz

    def test_disk_state_oldest_age_is_none_when_empty(self, tmp_path):
        """Empty archives_dir → oldest_file_age_seconds is None, not 0."""
        mgr = self._manager()

        state = mgr._get_archives_disk_state(str(tmp_path))

        assert state["file_count"] == 0
        assert state["oldest_file_age_seconds"] is None

    def test_disk_state_fail_open_on_shutil_error(self):
        """If shutil.disk_usage raises (e.g., bad path), return degraded dict (all None)."""
        mgr = self._manager()

        with patch("app.core.crawler_manager.shutil.disk_usage", side_effect=OSError("no such path")):
            state = mgr._get_archives_disk_state("/nonexistent")

        assert state == {
            "free_bytes": None,
            "total_bytes": None,
            "used_pct": None,
            "file_count": None,
            "oldest_file_age_seconds": None,
        }
```

- [ ] **Step 3: Run the tests and verify they all pass**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py::TestArchiveDiskPreflight -v
```

Expected: 7 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler-service): add disk space + archive diagnostics helpers"
```

---

### Task 2: Integrate pre-flight check and diagnostics into `archive_crawl`

**Goal:** Call the helpers before `_create_archive` runs. Log the disk state at start; reject with 503 when free < required; log the state again on failure.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (inside `archive_crawl`)
- Modify: `apps-microservices/crawler-service/tests/test_crawler_manager.py` (add integration-style tests via source inspection)

**Acceptance Criteria:**
- [ ] `archive_crawl` source contains `_get_archives_disk_state` call at the start of the main try-block (for baseline logging)
- [ ] `archive_crawl` source contains a call to `_estimate_archive_required_bytes`
- [ ] `archive_crawl` source contains `INSUFFICIENT_DISK_SPACE` error_code string
- [ ] `archive_crawl` source contains a second `_get_archives_disk_state` call inside the failure `except Exception` block
- [ ] A floor of `1_073_741_824` (1 GB) is applied to required bytes
- [ ] 503 is raised (not 500) when `free_bytes < required_bytes`
- [ ] All existing tests still pass (no regressions)

**Verify:** `cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v` → all tests PASS

**Steps:**

- [ ] **Step 1: Insert pre-flight check + baseline log in `archive_crawl`**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, find the block starting near line 1448-1451:

```python
            except HTTPException:
                # Archive not in GCS (502/504) — proceed with normal archiving
                logger.info(f"Archive for '{crawl_id}' not found in GCS. Proceeding with fresh archiving.")

            # Save current status snapshot before archiving (critical: dataset files will be deleted)
```

Insert the new pre-flight block **between** the `logger.info(f"Archive for '{crawl_id}' not found in GCS...")` line and the `# Save current status snapshot...` comment. The full replacement is:

**Find:**

```python
            except HTTPException:
                # Archive not in GCS (502/504) — proceed with normal archiving
                logger.info(f"Archive for '{crawl_id}' not found in GCS. Proceeding with fresh archiving.")

            # Save current status snapshot before archiving (critical: dataset files will be deleted)
```

**Replace with:**

```python
            except HTTPException:
                # Archive not in GCS (502/504) — proceed with normal archiving
                logger.info(f"Archive for '{crawl_id}' not found in GCS. Proceeding with fresh archiving.")

            # --- PRE-FLIGHT DISK SPACE CHECK ---
            # Measure the source directory, check free space on /app/archives/, reject
            # with 503 if insufficient. Fail-open if measurement itself fails.
            baseline_state = self._get_archives_disk_state(archives_dir)
            logger.info(f"Archive disk state for '{crawl_id}': {baseline_state}")

            required_bytes = self._estimate_archive_required_bytes(job_storage_path)
            required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

            if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
                logger.warning(
                    f"Rejecting archive '{crawl_id}': insufficient disk space. "
                    f"Required: {required_bytes} bytes, Available: {baseline_state['free_bytes']} bytes. "
                    f"Disk state: {baseline_state}"
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

            # Save current status snapshot before archiving (critical: dataset files will be deleted)
```

- [ ] **Step 2: Enrich the failure path with a post-failure disk state log**

In the same file, find the existing `except Exception` block (around line 1532-1535 currently, but line numbers will have shifted after Step 1):

**Find:**

```python
            except Exception as e:
                logger.error(f"Failed to archive crawl '{crawl_id}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=500, detail=f"Archiving failed: {str(e)}")
```

**Replace with:**

```python
            except Exception as e:
                logger.error(f"Failed to archive crawl '{crawl_id}': {e}", exc_info=True)
                # Log disk state at failure so we can correlate with the baseline log
                try:
                    post_failure_state = self._get_archives_disk_state(archives_dir)
                    logger.error(f"Archive disk state at failure for '{crawl_id}': {post_failure_state}")
                except Exception:
                    pass
                raise HTTPException(
                    status_code=500, detail=f"Archiving failed: {str(e)}")
```

- [ ] **Step 3: Add integration tests to `test_crawler_manager.py`**

Append the following tests to the existing `TestArchiveDiskPreflight` class in `apps-microservices/crawler-service/tests/test_crawler_manager.py`:

```python

    def test_archive_crawl_calls_get_disk_state_for_baseline(self):
        """archive_crawl must call _get_archives_disk_state early (baseline log)."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "_get_archives_disk_state" in source, (
            "archive_crawl must collect disk state for baseline logging and pre-flight"
        )
        # Must appear at least twice: once for baseline, once in the failure path
        assert source.count("_get_archives_disk_state") >= 2, (
            "archive_crawl must call _get_archives_disk_state in both baseline and failure paths"
        )

    def test_archive_crawl_applies_1gb_floor_to_required_bytes(self):
        """Required bytes must be floored at 1 GB (1_073_741_824)."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "_estimate_archive_required_bytes" in source, (
            "archive_crawl must call _estimate_archive_required_bytes"
        )
        assert "1_073_741_824" in source or "1073741824" in source, (
            "archive_crawl must apply a 1 GB floor to required bytes"
        )

    def test_archive_crawl_raises_503_on_insufficient_space(self):
        """archive_crawl must raise HTTPException with status 503 and INSUFFICIENT_DISK_SPACE error_code."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "INSUFFICIENT_DISK_SPACE" in source, (
            "archive_crawl must use the INSUFFICIENT_DISK_SPACE error_code"
        )
        assert "status_code=503" in source, (
            "archive_crawl must raise 503 (not 500) when disk space is insufficient"
        )
```

- [ ] **Step 4: Run the full test file and confirm no regressions**

```bash
cd apps-microservices/crawler-service && pytest tests/test_crawler_manager.py -v
```

Expected: all tests PASS (pre-existing + helpers from Task 1 + new integration tests from this task).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_crawler_manager.py
git commit -m "feat(crawler-service): pre-flight disk space check and diagnostic logging in archive_crawl"
```

---

### Task 3: Document the pre-flight behavior in CLAUDE.md

**Goal:** Record the new 503 contract, the fail-open policy, and the purpose of the diagnostic logs so future readers understand the behavior.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] Archiving section documents the pre-flight check and 503 response shape
- [ ] Fail-open policy is stated explicitly
- [ ] Link to the spec is included for deeper context

**Verify:** `grep -q "INSUFFICIENT_DISK_SPACE" apps-microservices/crawler-service/CLAUDE.md` → exit 0

**Steps:**

- [ ] **Step 1: Add the pre-flight section in CLAUDE.md**

Open `apps-microservices/crawler-service/CLAUDE.md`. Find the existing sub-section `### Tmp file isolation via `.staging/`` (added in the previous fix). Immediately after that sub-section's last paragraph, insert a new sub-section:

**Find:**

```markdown
### Tmp file isolation via `.staging/`

Archives are first written to `/app/archives/.staging/{crawl_id}.tar.gz` and only moved to `/app/archives/{crawl_id}.tar.gz` after size and integrity checks pass. The upload daemon (`tools/upload_daemon.sh`) uses `find -maxdepth 1`, which ignores subdirectories — so it only sees completed archives.

**Do not change the daemon to scan subdirectories** without also updating the tmp file location in `_create_archive`. Otherwise the daemon will race the tmp file and cause `FileNotFoundError` during archiving.

## robots.txt Blanket Block Bypass
```

**Replace with:**

```markdown
### Tmp file isolation via `.staging/`

Archives are first written to `/app/archives/.staging/{crawl_id}.tar.gz` and only moved to `/app/archives/{crawl_id}.tar.gz` after size and integrity checks pass. The upload daemon (`tools/upload_daemon.sh`) uses `find -maxdepth 1`, which ignores subdirectories — so it only sees completed archives.

**Do not change the daemon to scan subdirectories** without also updating the tmp file location in `_create_archive`. Otherwise the daemon will race the tmp file and cause `FileNotFoundError` during archiving.

### Pre-flight disk space check

Before creating a new archive, `archive_crawl` measures the source directory (`os.walk` + `size * 1.5` for gzip + safety margin, floored at 1 GB) and checks free space on `/app/archives/` via `shutil.disk_usage`. If free space is less than required, it responds with **503** carrying this body:

```json
{
  "detail": {
    "error_code": "INSUFFICIENT_DISK_SPACE",
    "required_bytes": 524288000,
    "available_bytes": 104857600,
    "disk_state": {
      "free_bytes": 104857600,
      "total_bytes": 21474836480,
      "used_pct": 99.51,
      "file_count": 47,
      "oldest_file_age_seconds": 7200
    }
  }
}
```

**Fail-open policy:** if the measurement helpers themselves raise (permissions, filesystem error), the check is skipped and archive creation proceeds. Broken measurement must never block archiving; the staging-dir `finally` block still cleans up partial files on disk-full.

Every archive attempt also logs a baseline disk state (`info`) and, on failure, a second disk state (`error`) so operational logs show the buffer pressure at both checkpoints.

Spec: `docs/superpowers/specs/2026-04-18-archive-disk-space-preflight-design.md`.

## robots.txt Blanket Block Bypass
```

- [ ] **Step 2: Verify the grep target succeeds**

```bash
grep -q "INSUFFICIENT_DISK_SPACE" apps-microservices/crawler-service/CLAUDE.md && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler-service): document pre-flight disk space check and 503 response"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Helper: `_estimate_archive_required_bytes` (size × 1.5, fail-open) | Task 1 |
| Helper: `_get_archives_disk_state` (free, total, used_pct, file_count, oldest_age) | Task 1 |
| `file_count` excludes `.staging/` | Task 1 (test `test_disk_state_excludes_staging_subdirectory`) |
| 1 GB floor on required bytes | Task 2 |
| Baseline disk state log (info) | Task 2 |
| 503 rejection with `INSUFFICIENT_DISK_SPACE` + detail | Task 2 |
| Post-failure disk state log (error) | Task 2 |
| Fail-open on helper errors | Task 1 (test `test_estimate_fail_open_on_exception`, `test_disk_state_fail_open_on_shutil_error`) |
| Documentation in CLAUDE.md | Task 3 |
| `_create_archive` staging logic unchanged | Confirmed — no task touches it |
| Upload daemon unchanged | Confirmed — no task touches `tools/upload_daemon.sh` |
| Redis lock / idempotency / GCS fallback unchanged | Confirmed — only pre-flight inserted between GCS fallback and snapshot |
