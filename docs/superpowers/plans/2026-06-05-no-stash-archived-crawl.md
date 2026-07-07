# Auto-stash: never stash an already-archived crawl — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the auto-stash sweep from stashing a crawl whose current data is already safely in the GCS archive (`crawls/{id}.tar.gz`), by adding a lightweight GCS existence+metadata probe and healing the crawler's status when it confirms an archive.

**Architecture:** A new metadata-only daemon op (`gcloud storage ls -l`) answers "does the archive exist, how big, how old?" via the existing file-marker channel. The auto-stash sweep consults it per candidate; only when the archive **exists AND is ≥ a size floor AND is not older than the local data** does it heal `status='archived'`, free the redundant local data, and skip the stash. Every other outcome stashes normally (preserving data). A cheap belt skips the grace clock for crawls already marked `archived`.

**Tech Stack:** Python 3.10 (FastAPI orchestrator), Bash (`gcloud` download daemon), pytest, Redis (`cache_service`).

**Spec:** `docs/superpowers/specs/2026-06-05-no-stash-archived-crawl-design.md`

---

### Task 1: Daemon GCS existence+metadata op (C1)

**Goal:** `download_daemon.sh` answers `{id}.exists-request` with `{id}.exists-yes` (body `"<size>\t<create_time>"`) or `{id}.exists-no`, using a metadata-only `gcloud storage ls -l` (no bytes transferred).

**Files:**
- Modify: `tools/download_daemon.sh` (add `process_exists_requests()` next to `process_move_requests`; call it in the poll loop)
- Test: `tools/tests/test_download_daemon_exists.sh` (new; bash smoke with a `gcloud` PATH stub)

**Acceptance Criteria:**
- [ ] `{id}.exists-request` with an existing object → `{id}.exists-yes` whose body is `"<size>\t<iso8601_create_time>"`; request file removed.
- [ ] `{id}.exists-request` with a missing object (or any `gcloud` failure) → `{id}.exists-no`; request file removed (fail-safe: error folds into "no").
- [ ] `*.request` (download) markers are NOT matched by the `*.exists-request` scan and vice-versa.

**Verify:** `bash tools/tests/test_download_daemon_exists.sh` → prints `OK-yes` and `OK-no`, exit 0.

**Steps:**

- [ ] **Step 1: Add `process_exists_requests()` before the `--source-functions-only` hook**

In `tools/download_daemon.sh`, immediately after the `process_move_requests() { ... }` definition (it ends at the line `}` around line 111, before the `# Test hook:` comment at line 113), insert:

```bash
process_exists_requests() {
    # Lightweight existence+metadata probe for the auto-stash already-archived
    # guard. Consume {id}.exists-request, run a metadata-only `gcloud storage ls -l`,
    # and write {id}.exists-yes (body: "<size>\t<create_time>") or {id}.exists-no.
    # A transient gcloud failure is folded into .exists-no — the crawler treats
    # that as "not archived" and stashes normally (fail-safe). No bytes transferred.
    find "$REQUESTS_DIR" -maxdepth 1 -name "*.exists-request" -print0 | while IFS= read -r -d '' req; do
        crawl_id=$(basename "$req" .exists-request)
        url="gs://$BUCKET_NAME/$DOWNLOAD_GCS_PREFIX/$crawl_id.tar.gz"
        yes_marker="$RESULTS_DIR/$crawl_id.exists-yes"
        no_marker="$RESULTS_DIR/$crawl_id.exists-no"
        if out=$(gcloud storage ls -l "$url" 2>/dev/null) && [ -n "$out" ]; then
            line=$(echo "$out" | head -n1)
            size=$(echo "$line" | awk '{print $1}')
            ctime=$(echo "$line" | awk '{print $2}')
            printf '%s\t%s' "$size" "$ctime" > "$yes_marker"
            rm -f "$req"
            echo "[$(date)] exists=YES $crawl_id (size=$size ctime=$ctime)"
        else
            touch "$no_marker"
            rm -f "$req"
            echo "[$(date)] exists=NO $crawl_id"
        fi
    done
}
```

- [ ] **Step 2: Call it in the poll loop**

In the `while true; do ... done` loop, after the `.request` download `find ... done` block (ends ~line 152) and before the `if [ "$DELETE_AFTER_DOWNLOAD" = "true" ]` block (~line 158), insert:

```bash
    # Auto-stash already-archived guard: answer existence probes (metadata only).
    process_exists_requests
```

- [ ] **Step 3: Write the bash smoke test (with a gcloud stub)**

Create `tools/tests/test_download_daemon_exists.sh`:

```bash
#!/bin/bash
# Smoke test for process_exists_requests using a gcloud PATH stub (no real GCS).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/req" "$tmp/res" "$tmp/bin"
cat > "$tmp/bin/gcloud" <<'STUB'
#!/bin/bash
# stub: `storage ls -l <url>` -> canned line for *5957*, non-zero otherwise.
if [ "${1:-}" = "storage" ] && [ "${2:-}" = "ls" ] && [ "${3:-}" = "-l" ]; then
  case "${4:-}" in
    *5957.tar.gz) echo "      12345  2026-02-26T08:11:40Z  ${4}"; echo "TOTAL: 1 objects, 12345 bytes"; exit 0;;
    *) exit 1;;
  esac
fi
exit 1
STUB
chmod +x "$tmp/bin/gcloud"

export GCS_BUCKET_NAME="fake-bucket"
export DOWNLOAD_REQUESTS_PATH="$tmp/req"
export DOWNLOAD_RESULTS_PATH="$tmp/res"
export DOWNLOAD_GCS_PREFIX="crawls"
export PATH="$tmp/bin:$PATH"

# Import daemon functions + config without entering the loop.
source "$ROOT/tools/download_daemon.sh" --source-functions-only

touch "$tmp/req/5957.exists-request" "$tmp/req/9999.exists-request"
process_exists_requests

fail=0
if [ -f "$tmp/res/5957.exists-yes" ] && grep -qP '^12345\t2026-02-26T08:11:40Z$' "$tmp/res/5957.exists-yes"; then
  echo "OK-yes"
else
  echo "FAIL-yes"; cat "$tmp/res/5957.exists-yes" 2>/dev/null; fail=1
fi
if [ -f "$tmp/res/9999.exists-no" ]; then echo "OK-no"; else echo "FAIL-no"; fail=1; fi
# request files consumed
[ ! -f "$tmp/req/5957.exists-request" ] && [ ! -f "$tmp/req/9999.exists-request" ] || { echo "FAIL-consume"; fail=1; }
exit $fail
```

- [ ] **Step 4: Run the smoke test**

Run: `bash tools/tests/test_download_daemon_exists.sh`
Expected: prints `OK-yes` and `OK-no`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tools/download_daemon.sh tools/tests/test_download_daemon_exists.sh
git commit -m "feat(daemon): GCS exists-probe op for auto-stash archived guard"
```

---

### Task 2: Config settings + `GcsArchiveInfo` + `_gcs_archive_info` (C2)

**Goal:** A crawler-side async probe that submits `{id}.exists-request`, waits (bounded) for the daemon's verdict, and returns a parsed `GcsArchiveInfo`. Fail-safe to `exists=False` on timeout/error/garbage.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py` (2 new settings)
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (imports, `GcsArchiveInfo`, `_gcs_archive_info`, `_safe_remove`, `_parse_exists_yes`)
- Test: `apps-microservices/crawler-service/tests/test_gcs_archive_info.py` (new)

**Acceptance Criteria:**
- [ ] `.exists-yes` body `"12345\t2026-02-26T08:11:40Z"` → `GcsArchiveInfo(exists=True, size_bytes=12345, created_at=<utc dt>)`.
- [ ] `.exists-no` → `GcsArchiveInfo(exists=False)`.
- [ ] No marker within `GCS_EXISTS_TIMEOUT_SECONDS` → `GcsArchiveInfo(exists=False)`; the `.exists-request` is cleaned up.
- [ ] Garbage `.exists-yes` body → `exists=True` but `size_bytes=None`/`created_at=None`.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_gcs_archive_info.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Add config settings**

In `apps-microservices/crawler-service/app/core/config.py`, inside the `# --- Auto-stash workflow ---` block (after `STASH_MAX_PER_SWEEP: int = 5`, line ~104), add:

```python
    # --- Already-archived guard (spec 2026-06-05) ---
    # Max wait for the daemon's {id}.exists-yes/.exists-no verdict before the
    # lightweight GCS-exists probe fails safe (-> treated as "not archived").
    GCS_EXISTS_TIMEOUT_SECONDS: int = 30
    # Minimum size (bytes) of a GCS archive to trust it as a complete copy worth
    # deleting local data against. Below this = truncated/corrupt -> stash normally.
    GCS_ARCHIVE_MIN_BYTES: int = 1024
```

- [ ] **Step 2: Add imports + `GcsArchiveInfo` in `crawler_manager.py`**

Ensure these imports exist near the top of `crawler_manager.py` (add only the missing ones — `datetime` is already imported; add `timezone` to its import line, and add `dataclass`/`Optional` if absent):

```python
from dataclasses import dataclass
from datetime import datetime, timezone  # add `timezone` to the existing datetime import
from typing import Optional              # already imported in most modules; ensure present
```

Add the dataclass at module level (near the top, after imports):

```python
@dataclass
class GcsArchiveInfo:
    """Result of the lightweight GCS archive existence probe (C2)."""
    exists: bool
    size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None  # timezone-aware UTC
```

- [ ] **Step 3: Write the failing test**

Create `apps-microservices/crawler-service/tests/test_gcs_archive_info.py`:

```python
"""Lightweight GCS archive existence probe (already-archived guard, C2)."""
import asyncio
import os
from datetime import timezone

import pytest

from app.core.crawler_manager import CrawlerManager, GcsArchiveInfo
from app.core import config


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    req = tmp_path / "req"
    res = tmp_path / "res"
    req.mkdir()
    res.mkdir()
    monkeypatch.setattr(config.settings, "DOWNLOAD_REQUESTS_PATH", str(req))
    monkeypatch.setattr(config.settings, "DOWNLOAD_RESULTS_PATH", str(res))
    monkeypatch.setattr(config.settings, "GCS_EXISTS_TIMEOUT_SECONDS", 2)
    m = CrawlerManager()
    return m, str(req), str(res)


def test_exists_yes_parsed(mgr):
    m, _req, res = mgr
    with open(os.path.join(res, "5957.exists-yes"), "w") as f:
        f.write("12345\t2026-02-26T08:11:40Z")
    info = asyncio.run(m._gcs_archive_info("5957"))
    assert info.exists is True
    assert info.size_bytes == 12345
    assert info.created_at is not None
    assert info.created_at.tzinfo is not None
    assert info.created_at.astimezone(timezone.utc).year == 2026


def test_exists_no(mgr):
    m, _req, res = mgr
    open(os.path.join(res, "5957.exists-no"), "w").close()
    info = asyncio.run(m._gcs_archive_info("5957"))
    assert info.exists is False


def test_timeout_fails_safe(mgr):
    m, req, _res = mgr
    info = asyncio.run(m._gcs_archive_info("5957"))  # no marker ever written
    assert info.exists is False
    assert not os.path.exists(os.path.join(req, "5957.exists-request"))  # cleaned up


def test_garbage_yes_body_not_confident(mgr):
    m, _req, res = mgr
    with open(os.path.join(res, "5957.exists-yes"), "w") as f:
        f.write("not-a-size\tnot-a-date")
    info = asyncio.run(m._gcs_archive_info("5957"))
    assert info.exists is True
    assert info.size_bytes is None
    assert info.created_at is None
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_gcs_archive_info.py -v`
Expected: FAIL (ImportError: `_gcs_archive_info` not defined).

- [ ] **Step 5: Implement `_gcs_archive_info` + helpers**

In `crawler_manager.py`, add these methods to the `CrawlerManager` class (place near `_retrieve_from_gcs_daemon`):

```python
    @staticmethod
    def _safe_remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _parse_exists_yes(body: str) -> "GcsArchiveInfo":
        """Body = '<size_bytes>\\t<iso8601_create_time>'. Missing/garbage fields
        leave that piece None (the caller treats None as 'not confident')."""
        size_bytes = None
        created_at = None
        parts = body.split("\t") if body else []
        if len(parts) >= 1 and parts[0].strip().isdigit():
            size_bytes = int(parts[0].strip())
        if len(parts) >= 2 and parts[1].strip():
            raw = parts[1].strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(raw)
                created_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                created_at = None
        return GcsArchiveInfo(exists=True, size_bytes=size_bytes, created_at=created_at)

    async def _gcs_archive_info(self, crawl_id: str) -> "GcsArchiveInfo":
        """Lightweight 'does crawls/{id}.tar.gz exist (size/create-time)?' via the
        download daemon's metadata op. Fail-safe: any timeout/error/parse failure
        returns GcsArchiveInfo(exists=False). Never raises."""
        requests_dir = settings.DOWNLOAD_REQUESTS_PATH
        results_dir = settings.DOWNLOAD_RESULTS_PATH
        request_path = os.path.join(requests_dir, f"{crawl_id}.exists-request")
        yes_path = os.path.join(results_dir, f"{crawl_id}.exists-yes")
        no_path = os.path.join(results_dir, f"{crawl_id}.exists-no")
        try:
            # Clear stale prior verdicts so we read a fresh one.
            self._safe_remove(yes_path)
            self._safe_remove(no_path)
            os.makedirs(requests_dir, exist_ok=True)
            async with aiofiles.open(request_path, "w") as f:
                await f.write(crawl_id)

            deadline = time.monotonic() + settings.GCS_EXISTS_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if os.path.exists(yes_path):
                    body = ""
                    try:
                        async with aiofiles.open(yes_path, "r") as f:
                            body = (await f.read()).strip()
                    finally:
                        self._safe_remove(yes_path)
                    return self._parse_exists_yes(body)
                if os.path.exists(no_path):
                    self._safe_remove(no_path)
                    return GcsArchiveInfo(exists=False)
                await asyncio.sleep(1)

            self._safe_remove(request_path)  # don't leave a stale request for the daemon
            logger.info(f"_gcs_archive_info timeout for '{crawl_id}' -> treat as not archived")
            return GcsArchiveInfo(exists=False)
        except Exception as e:
            logger.warning(f"_gcs_archive_info error for '{crawl_id}': {e}")
            return GcsArchiveInfo(exists=False)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_gcs_archive_info.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/crawler-service/app/core/config.py apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_gcs_archive_info.py
git commit -m "feat(crawler): _gcs_archive_info GCS existence probe + config"
```

---

### Task 3: Decision + local-free helpers (`_local_data_mtime`, `_is_confidently_archived`, `_free_local_crawl_data`)

**Goal:** The pure decision logic (§6 table) and a reusable local-data delete, with `archive_crawl`'s nested cleanup delegating to the shared method (DRY).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (3 methods + refactor `_cleanup_local_data` in `archive_crawl` to delegate)
- Test: `apps-microservices/crawler-service/tests/test_archived_guard_decision.py` (new)

**Acceptance Criteria:**
- [ ] `_is_confidently_archived` returns True only when `exists` AND `size_bytes ≥ GCS_ARCHIVE_MIN_BYTES` AND `created_at ≥ local_mtime`.
- [ ] Returns False on: not-exists, size below floor, missing `created_at`/`local_mtime`, or stale (`created_at < local_mtime`).
- [ ] `_free_local_crawl_data` removes data files but keeps logs/markers (`crawler.log`, `_completion_marker.json`, …); no-op on missing path.
- [ ] `archive_crawl`'s existing behavior is unchanged (its cleanup now calls the shared method).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_archived_guard_decision.py tests/test_archive_mock_e2e.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/crawler-service/tests/test_archived_guard_decision.py`:

```python
"""Decision (§6) + local-free helpers for the already-archived guard (Task 3)."""
import asyncio
import os
from datetime import datetime, timezone, timedelta

import pytest

from app.core.crawler_manager import CrawlerManager, GcsArchiveInfo
from app.core import config


@pytest.fixture
def mgr(monkeypatch):
    monkeypatch.setattr(config.settings, "GCS_ARCHIVE_MIN_BYTES", 1024)
    return CrawlerManager()


def _dt(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _run_confident(mgr, info, local_mtime, storage_path="/x"):
    async def fake_info(_cid):
        return info
    mgr._gcs_archive_info = fake_info
    mgr._local_data_mtime = lambda _p: local_mtime
    return asyncio.run(mgr._is_confidently_archived({"crawl_id": "5957", "storage_path": storage_path}))


def test_confident_when_exists_big_and_fresh(mgr):
    info = GcsArchiveInfo(exists=True, size_bytes=999999, created_at=_dt("2026-03-01T00:00:00"))
    assert _run_confident(mgr, info, _dt("2026-02-26T00:00:00")) is True


def test_not_confident_when_absent(mgr):
    assert _run_confident(mgr, GcsArchiveInfo(exists=False), _dt("2026-02-26T00:00:00")) is False


def test_not_confident_when_truncated(mgr):
    info = GcsArchiveInfo(exists=True, size_bytes=10, created_at=_dt("2026-03-01T00:00:00"))
    assert _run_confident(mgr, info, _dt("2026-02-26T00:00:00")) is False


def test_not_confident_when_stale(mgr):
    info = GcsArchiveInfo(exists=True, size_bytes=999999, created_at=_dt("2026-01-01T00:00:00"))
    assert _run_confident(mgr, info, _dt("2026-02-26T00:00:00")) is False


def test_not_confident_when_metadata_missing(mgr):
    info = GcsArchiveInfo(exists=True, size_bytes=999999, created_at=None)
    assert _run_confident(mgr, info, _dt("2026-02-26T00:00:00")) is False
    info2 = GcsArchiveInfo(exists=True, size_bytes=999999, created_at=_dt("2026-03-01T00:00:00"))
    assert _run_confident(mgr, info2, None) is False


def test_free_local_keeps_logs_removes_data(tmp_path, mgr):
    sp = tmp_path / "storage"
    (sp / "storage" / "datasets" / "d").mkdir(parents=True)
    (sp / "storage" / "datasets" / "d" / "000001.json").write_text("{}")
    (sp / "crawler.log").write_text("log")
    (sp / "_completion_marker.json").write_text("{}")
    mgr._free_local_crawl_data(str(sp))
    assert (sp / "crawler.log").exists()
    assert (sp / "_completion_marker.json").exists()
    assert not (sp / "storage" / "datasets" / "d" / "000001.json").exists()


def test_free_local_noop_on_missing_path(mgr):
    mgr._free_local_crawl_data(None)
    mgr._free_local_crawl_data("/nonexistent/path/xyz")


def test_local_data_mtime_none_when_missing(mgr):
    assert mgr._local_data_mtime(None) is None
    assert mgr._local_data_mtime("/nonexistent/path/xyz") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_archived_guard_decision.py -v`
Expected: FAIL (AttributeError: `_is_confidently_archived` / `_free_local_crawl_data` / `_local_data_mtime`).

- [ ] **Step 3: Implement the three methods**

In `crawler_manager.py`, add to `CrawlerManager` (near `_select_stash_candidates`):

```python
    def _local_data_mtime(self, storage_path: Optional[str]) -> Optional[datetime]:
        """Newest mtime under the crawl's storage dir, as tz-aware UTC. None when
        the path is missing/empty/unreadable (caller treats None as 'unknown')."""
        if not storage_path or not os.path.isdir(storage_path):
            return None
        newest = None
        try:
            for root, _dirs, files in os.walk(storage_path):
                for name in files:
                    try:
                        m = os.path.getmtime(os.path.join(root, name))
                    except OSError:
                        continue
                    if newest is None or m > newest:
                        newest = m
        except OSError:
            return None
        if newest is None:
            return None
        return datetime.fromtimestamp(newest, tz=timezone.utc)

    async def _is_confidently_archived(self, job_data: dict) -> bool:
        """True only when the GCS archive exists, is large enough to not be
        truncated, and is not older than the local data (rejects a stale archive
        left by a reused crawl_id). Fail-safe: any uncertainty -> False (the sweep
        then stashes normally, preserving local data)."""
        crawl_id = job_data.get("crawl_id")
        if not crawl_id:
            return False
        info = await self._gcs_archive_info(crawl_id)
        if not info.exists:
            return False
        if info.size_bytes is None or info.size_bytes < settings.GCS_ARCHIVE_MIN_BYTES:
            return False
        local_mtime = self._local_data_mtime(job_data.get("storage_path"))
        if info.created_at is None or local_mtime is None:
            return False
        return info.created_at >= local_mtime

    def _free_local_crawl_data(self, storage_path: Optional[str]) -> None:
        """Remove crawl data files under storage_path, keeping only logs and
        markers. Shared by archive_crawl's post-archive cleanup and the auto-stash
        already-archived skip path. No-op on missing path."""
        if not storage_path or not os.path.isdir(storage_path):
            return
        files_to_keep = {'crawler.log', '_callback_payload.json',
                         '_completion_marker.json', '_status_snapshot.json',
                         '_exit_reason.json', '_update_report.json',
                         'update_stats.json',
                         'timing.jsonl', 'timing-summary.json'}
        for root, dirs, files in os.walk(storage_path, topdown=False):
            for name in files:
                if name not in files_to_keep:
                    os.remove(os.path.join(root, name))
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
```

- [ ] **Step 4: Refactor `archive_crawl`'s nested cleanup to delegate (DRY)**

In `archive_crawl` (`crawler_manager.py` ~line 2214), replace the nested `_cleanup_local_data` body so it delegates to the shared method (behavior-preserving — same files_to_keep, same walk):

```python
                    def _cleanup_local_data():
                        """Remove crawl data files, keeping only logs and markers."""
                        self._free_local_crawl_data(job_storage_path)
```

- [ ] **Step 5: Run tests (new + archive regression) to verify they pass**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_archived_guard_decision.py tests/test_archive_mock_e2e.py -v`
Expected: PASS (new decision/helper tests + existing archive e2e unchanged).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_archived_guard_decision.py
git commit -m "feat(crawler): archived-guard decision + shared local-free helper"
```

---

### Task 4: Wire the guard into the auto-stash sweep (C3)

**Goal:** `_auto_stash_one` consults `_is_confidently_archived` before stashing; on confirmation it heals `status='archived'`, frees local data, and skips the stash.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`_auto_stash_one`, ~line 3018)
- Test: `apps-microservices/crawler-service/tests/test_auto_stash_archived_skip.py` (new)

**Acceptance Criteria:**
- [ ] confidently-archived → `_mark_as_archived` called, `_free_local_crawl_data` called, `stash_crawl` NOT called.
- [ ] not-confidently-archived → `stash_crawl` called, `_mark_as_archived` NOT called.
- [ ] In-flight set is always discarded (existing `finally`).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archived_skip.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/crawler-service/tests/test_auto_stash_archived_skip.py`:

```python
"""C3: auto-stash skips + heals an already-archived crawl (Task 4)."""
import asyncio
from app.core.crawler_manager import CrawlerManager


def _wire(mgr, confident):
    calls = {"mark": 0, "free": 0, "stash": 0}

    async def fake_confident(_job):
        return confident

    async def fake_mark(_cid):
        calls["mark"] += 1

    def fake_free(_sp):
        calls["free"] += 1

    async def fake_stash(_job):
        calls["stash"] += 1

    mgr._is_confidently_archived = fake_confident
    mgr._mark_as_archived = fake_mark
    mgr._free_local_crawl_data = fake_free
    mgr.stash_crawl = fake_stash
    return calls


def test_archived_skips_stash_and_heals():
    mgr = CrawlerManager()
    calls = _wire(mgr, confident=True)
    asyncio.run(mgr._auto_stash_one({"crawl_id": "5957", "storage_path": "/x"}, "grace"))
    assert calls["mark"] == 1
    assert calls["free"] == 1
    assert calls["stash"] == 0
    assert "5957" not in mgr._auto_stash_inflight


def test_not_archived_stashes_normally():
    mgr = CrawlerManager()
    calls = _wire(mgr, confident=False)
    asyncio.run(mgr._auto_stash_one({"crawl_id": "6000", "storage_path": "/x"}, "grace"))
    assert calls["stash"] == 1
    assert calls["mark"] == 0
    assert calls["free"] == 0
    assert "6000" not in mgr._auto_stash_inflight
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archived_skip.py -v`
Expected: FAIL (`mark`/`free` are 0 — guard not wired; `stash` called even when archived).

- [ ] **Step 3: Wire the guard into `_auto_stash_one`**

Replace the body of `_auto_stash_one` (`crawler_manager.py` ~line 3018) with:

```python
    async def _auto_stash_one(self, job_data: dict, reason: str) -> None:
        """Stash one crawl on behalf of the sweep. First guards against stashing a
        crawl whose current data is already in the GCS archive (heal status + free
        local + skip). Swallows 409; logs other failures. Never raises."""
        crawl_id = job_data.get("crawl_id")
        try:
            # Already-archived guard (spec 2026-06-05): never stash a crawl whose
            # current data is the canonical GCS copy. Confident archive -> heal
            # status, free the redundant local data, and skip the stash.
            if await self._is_confidently_archived(job_data):
                await self._mark_as_archived(crawl_id)
                logger.info(f"AUTO_STASH skip crawl_id={crawl_id} reason=already_archived")
                try:
                    await anyio.to_thread.run_sync(
                        self._free_local_crawl_data, job_data.get("storage_path")
                    )
                    logger.info(f"AUTO_STASH local_freed crawl_id={crawl_id}")
                except Exception as e:
                    logger.warning(f"AUTO_STASH local_free failed crawl_id={crawl_id}: {e}")
                return

            logger.info(f"AUTO_STASH crawl_id={crawl_id} reason={reason}")
            await self.stash_crawl(job_data)
        except HTTPException as e:
            if e.status_code == 409:
                logger.debug(f"AUTO_STASH skip crawl_id={crawl_id}: {e.detail}")
            else:
                logger.warning(f"AUTO_STASH failed crawl_id={crawl_id}: {e.detail}")
        except Exception as e:
            logger.warning(f"AUTO_STASH error crawl_id={crawl_id}: {e}")
        finally:
            # Release the in-flight slot so the next sweep can re-select this crawl.
            self._auto_stash_inflight.discard(crawl_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_auto_stash_archived_skip.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_auto_stash_archived_skip.py
git commit -m "feat(crawler): auto-stash skips+heals already-archived crawls"
```

---

### Task 5: Belt — don't start the grace clock for archived crawls (C4)

**Goal:** `_record_downloaded_at` skips stamping `downloaded_at` when the crawl is already `status='archived'`, so a correctly-archived crawl never enters the auto-stash grace window.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/crawler.py` (`_record_downloaded_at`, ~line 23-39)
- Test: `apps-microservices/crawler-service/tests/test_record_downloaded_at_guard.py` (new)

**Acceptance Criteria:**
- [ ] `status='archived'` → `set_json` NOT called (no `downloaded_at` written).
- [ ] `status='finished'` → `set_json` called with a `downloaded_at` field.
- [ ] Job vanished (`get_json` → None) → no write, no raise (unchanged).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_record_downloaded_at_guard.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/crawler-service/tests/test_record_downloaded_at_guard.py`:

```python
"""C4: _record_downloaded_at must not start grace for archived crawls (Task 5)."""
import asyncio
import pytest
from app.router import crawler as crawler_router


class _FakeCache:
    def __init__(self, job):
        self._job = job
        self.set_calls = []

    async def get_json(self, _key):
        return self._job

    async def set_json(self, _key, value):
        self.set_calls.append(value)


def _run(monkeypatch, job):
    fake = _FakeCache(job)
    monkeypatch.setattr(crawler_router, "cache_service", fake)
    asyncio.run(crawler_router._record_downloaded_at({"crawl_id": "5957"}))
    return fake


def test_archived_does_not_stamp(monkeypatch):
    fake = _run(monkeypatch, {"crawl_id": "5957", "status": "archived"})
    assert fake.set_calls == []


def test_finished_stamps(monkeypatch):
    fake = _run(monkeypatch, {"crawl_id": "5957", "status": "finished"})
    assert len(fake.set_calls) == 1
    assert "downloaded_at" in fake.set_calls[0]


def test_vanished_job_no_write(monkeypatch):
    fake = _run(monkeypatch, None)
    assert fake.set_calls == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_record_downloaded_at_guard.py -v`
Expected: FAIL on `test_archived_does_not_stamp` (current code stamps regardless of status).

- [ ] **Step 3: Add the guard**

In `app/router/crawler.py`, in `_record_downloaded_at`, after the `if fresh is None: return` line (~line 34) and before `fresh["downloaded_at"] = ...`, add:

```python
        if fresh.get("status") == "archived":
            # An archived crawl's data is the canonical GCS copy; do not start the
            # auto-stash grace clock for it (it must never be stashed).
            return
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_record_downloaded_at_guard.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/router/crawler.py apps-microservices/crawler-service/tests/test_record_downloaded_at_guard.py
git commit -m "feat(crawler): skip downloaded_at grace clock for archived crawls"
```

---

### Task 6: Documentation

**Goal:** Document the new marker family + the auto-stash already-archived guard so operators and future contributors understand both layers.

**Files:**
- Modify: `tools/CLAUDE.md` (daemon `.exists-request/.exists-yes/.exists-no` marker family)
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (Auto-Stash Workflow → already-archived guard)

**Acceptance Criteria:**
- [ ] `tools/CLAUDE.md` documents the exists-probe markers + that a gcloud failure folds into `.exists-no` (fail-safe).
- [ ] `crawler-service/CLAUDE.md` documents the §6 decision (heal+free+skip only when exists & size≥floor & not-stale) and the two new settings.

**Verify:** `git diff --stat` shows both CLAUDE.md files changed; manual read-through.

**Steps:**

- [ ] **Step 1: Update `tools/CLAUDE.md`**

In the `## Conventions` bullet about GCS daemons / marker families, add:

```markdown
  - Exists-probe (auto-stash already-archived guard): `{id}.exists-request` → daemon runs metadata-only `gcloud storage ls -l {prefix}/{id}.tar.gz` and writes `{id}.exists-yes` (body `"<size>\t<create_time>"`) or `{id}.exists-no`. A transient gcloud failure folds into `.exists-no` (the crawler treats it as "not archived" and stashes normally — fail-safe). No bytes transferred. Function: `process_exists_requests` in `download_daemon.sh`. Spec: `docs/superpowers/specs/2026-06-05-no-stash-archived-crawl-design.md`.
```

- [ ] **Step 2: Update `apps-microservices/crawler-service/CLAUDE.md`**

In the `## Auto-Stash Workflow` section, add a subsection:

```markdown
### Already-archived guard (spec 2026-06-05)

The sweep must never stash a crawl whose current data is already in the GCS archive (`crawls/`). Before stashing a candidate, `_auto_stash_one` calls `_is_confidently_archived`: a lightweight daemon `gcloud storage ls -l` (`_gcs_archive_info`) returns existence + size + create-time. Only when the archive **exists AND size ≥ `GCS_ARCHIVE_MIN_BYTES` AND its create-time ≥ the local data's mtime** does the sweep heal `status='archived'` (`_mark_as_archived`), free the redundant local data (`_free_local_crawl_data`), and skip the stash. Every other outcome (absent / truncated / stale / metadata-missing / probe timeout) stashes normally — which always preserves data. Fixes the disconnect where a legacy crawl archived to GCS still showed `status='finished'` and was auto-stashed after download (crawl 5957). Belt: `_record_downloaded_at` skips stamping `downloaded_at` for `status='archived'`.

Tunables (`app/core/config.py`): `GCS_EXISTS_TIMEOUT_SECONDS` (30), `GCS_ARCHIVE_MIN_BYTES` (1024).
```

- [ ] **Step 3: Commit**

```bash
git add tools/CLAUDE.md apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler): document auto-stash already-archived guard + exists-probe markers"
```

---

## Open items / assumptions to verify during implementation

- **`gcloud storage ls -l` output format** on the deployed gcloud version: confirm column 1 = size, column 2 = ISO-8601 create time on the first line. The crawler parse is defensive (garbage → `size/created None` → not confident → stash), so a format drift fails safe, but a correct parse is needed for the guard to actually fire.
- **`job_data['storage_path']` presence** in legacy Redis records (e.g. 5957). If absent → `_local_data_mtime` returns None → not confident → stash normally (safe). Acceptable; note it.
- **`crawl_id == id_domaine` reuse** on re-crawl is the reason for the freshness guard. Confirm during impl; the guard is harmless either way.
- **`pytest` asyncio**: new async tests use `asyncio.run(...)` (no `pytest.mark.asyncio` dependency) to stay runnable regardless of asyncio-mode config.
- **`anyio` import** already present in `crawler_manager.py` (used by `archive_crawl` via `anyio.to_thread.run_sync`).

## Out of scope (per spec §4)

- Bulk migration of the ~3925 `est_archiver=1` crawls (trigger is download-driven; guard self-heals on access).
- Deep archive integrity validation (`tools/gcs_archive_audit.py`'s job).
- One-off cleanup of crawl 5957's already-created `stash/` copy.
