# GCS Archive Audit Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI `tools/gcs_archive_audit.py` that audits every archive in `gs://{bucket}/crawls/`, classifies each as OK / WRONG_NAME / CORRUPTED / MISSING_PAYLOAD / MISSING_MARKER / ROW_COUNT_MISMATCH / DUPLICATE / INSPECTION_FAILED, writes a JSON report, and optionally remediates via `--delete` or `--quarantine`.

**Architecture:** Single-module Python CLI. Shells out to `gcloud storage` for all GCS operations (no `google-cloud-storage` dependency). Uses `tarfile` module to inspect downloaded archives. Report written incrementally so partial results survive crashes. Tests use `unittest.mock` to stub subprocess calls and build in-memory tar.gz fixtures.

**Tech Stack:** Python 3 stdlib only (argparse, json, subprocess, tarfile, tempfile, signal, pathlib, datetime, unittest.mock). External: `gcloud` CLI (runtime dependency, not pip).

**Spec:** `docs/superpowers/specs/2026-04-18-gcs-archive-audit-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/gcs_archive_audit.py` | CREATE | The full CLI: gcloud shell wrappers, archive inspection, duplicate detection, remediation, argparse+main |
| `tools/tests/__init__.py` | CREATE | Empty package marker |
| `tools/tests/conftest.py` | CREATE | Adds `tools/` to `sys.path` so tests can `import gcs_archive_audit` |
| `tools/tests/test_gcs_archive_audit.py` | CREATE | pytest tests for all public functions |
| `tools/CLAUDE.md` | MODIFY | Add the tool to File Inventory and Run sections |

No changes to `tools/requirements.txt` — the tool uses only stdlib.

---

### Task 1: gcloud shell wrappers + test scaffolding

**Goal:** Create the module skeleton with thin `subprocess` wrappers around `gcloud storage` commands, plus the test infrastructure (conftest + first tests).

**Files:**
- Create: `tools/gcs_archive_audit.py`
- Create: `tools/tests/__init__.py`
- Create: `tools/tests/conftest.py`
- Create: `tools/tests/test_gcs_archive_audit.py`

**Acceptance Criteria:**
- [ ] `gcloud_ls(uri, long=False)` returns list of URIs (or (size, uri) tuples when `long=True`)
- [ ] `gcloud_download(obj_uri, local_path)`, `gcloud_delete(obj_uri)`, `gcloud_move(src_uri, dst_uri)` wrap `gcloud storage cp|rm|mv` via `subprocess.run(check=True)`
- [ ] `check_gcloud_auth()` exits with clear error message if `gcloud auth list --filter=status:ACTIVE` returns no active account
- [ ] `extract_crawl_id(object_name)` parses `"crawls/4365.tar.gz"` → `"4365"` and `"crawls/4365.tmp.tar.gz"` → `"4365"`
- [ ] 6 tests pass (one per function above, including edge cases for the parser)

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v`

**Steps:**

- [ ] **Step 1: Create the module skeleton `tools/gcs_archive_audit.py`**

Write the following to `tools/gcs_archive_audit.py`:

```python
"""GCS Archive Audit Tool.

Audits every archive in gs://{bucket}/crawls/, classifies each, writes a
JSON report, and optionally remediates via --delete or --quarantine.

Shells out to `gcloud storage` — no google-cloud-storage Python dependency.
Authentication is whatever gcloud is configured with on the host.

Run:
    python tools/gcs_archive_audit.py --bucket <name> [--output report.json]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union


def _run_gcloud(args: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a gcloud command via subprocess. Centralized so tests can patch a single point."""
    cmd = ["gcloud"] + args
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def check_gcloud_auth() -> None:
    """Ensure gcloud has an active authenticated account. Exit with a helpful message if not."""
    try:
        result = _run_gcloud(["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
    except FileNotFoundError:
        print("ERROR: `gcloud` CLI not found on PATH. Install Google Cloud SDK.", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: `gcloud auth list` failed: {e.stderr}", file=sys.stderr)
        sys.exit(2)

    active = (result.stdout or "").strip()
    if not active:
        print(
            "ERROR: No active gcloud account. Run one of:\n"
            "  gcloud auth login\n"
            "  gcloud auth activate-service-account --key-file=<path>",
            file=sys.stderr,
        )
        sys.exit(2)


def gcloud_ls(uri: str, long: bool = False) -> List[Union[str, Tuple[int, str]]]:
    """List objects under a GCS URI.

    When long=False: returns a list of URIs (strings).
    When long=True: returns a list of (size_bytes, uri) tuples. Non-parseable
    lines are skipped (e.g., the trailing 'TOTAL:' summary line).
    """
    args = ["storage", "ls"]
    if long:
        args.append("-l")
    args.append(uri)
    try:
        result = _run_gcloud(args)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: gcloud storage ls failed for '{uri}': {e.stderr}", file=sys.stderr)
        return []

    lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    if not long:
        return [line for line in lines if line.startswith("gs://")]

    # Long format:
    #   <size>  <YYYY-MM-DDTHH:MM:SSZ>  gs://bucket/path
    # We want (size, uri) tuples, skipping any line that doesn't parse.
    out: List[Tuple[int, str]] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        if not parts[-1].startswith("gs://"):
            continue
        try:
            size = int(parts[0])
        except ValueError:
            continue
        out.append((size, parts[-1]))
    return out


def gcloud_download(obj_uri: str, local_path: Path) -> None:
    """Download a GCS object to a local path. Raises on failure."""
    _run_gcloud(["storage", "cp", obj_uri, str(local_path)])


def gcloud_delete(obj_uri: str) -> None:
    """Delete a GCS object. Raises on failure."""
    _run_gcloud(["storage", "rm", obj_uri])


def gcloud_move(src_uri: str, dst_uri: str) -> None:
    """Move (rename) a GCS object. Server-side where possible. Raises on failure."""
    _run_gcloud(["storage", "mv", src_uri, dst_uri])


def extract_crawl_id(object_name: str) -> Optional[str]:
    """Given `crawls/4365.tar.gz` or `crawls/4365.tmp.tar.gz` or a full gs:// URI,
    return the crawl_id component. Returns None if the name doesn't match.

    Examples:
        'crawls/4365.tar.gz'         -> '4365'
        'crawls/4365.tmp.tar.gz'     -> '4365'
        'gs://b/crawls/4365.tar.gz'  -> '4365'
        'gs://b/crawls/weird'        -> None
    """
    # Strip gs://bucket/ prefix if present
    path = object_name
    if path.startswith("gs://"):
        # gs://bucket/rest/of/path → rest/of/path
        parts = path.split("/", 3)
        path = parts[3] if len(parts) >= 4 else ""

    # Take the basename and strip known suffixes
    base = path.rsplit("/", 1)[-1]
    for suffix in (".tmp.tar.gz", ".tar.gz"):
        if base.endswith(suffix):
            crawl_id = base[: -len(suffix)]
            if crawl_id:
                return crawl_id
    return None
```

- [ ] **Step 2: Create test scaffolding**

Write `tools/tests/__init__.py` as an empty file (one newline is fine).

Write `tools/tests/conftest.py`:

```python
"""Pytest conftest for tools/ tests.

Adds the tools/ directory to sys.path so tests can import modules like
`import gcs_archive_audit` directly (same pattern as running the scripts
with `python tools/gcs_archive_audit.py`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 3: Create the test file with tests for all Task 1 functions**

Write `tools/tests/test_gcs_archive_audit.py`:

```python
"""Tests for tools/gcs_archive_audit.py."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import gcs_archive_audit as ga


class TestExtractCrawlId:
    def test_plain_tar_gz(self):
        assert ga.extract_crawl_id("crawls/4365.tar.gz") == "4365"

    def test_tmp_tar_gz(self):
        assert ga.extract_crawl_id("crawls/4365.tmp.tar.gz") == "4365"

    def test_full_gs_uri(self):
        assert ga.extract_crawl_id("gs://my-bucket/crawls/4365.tar.gz") == "4365"

    def test_unrecognized_name(self):
        assert ga.extract_crawl_id("gs://my-bucket/crawls/weird") is None

    def test_empty_crawl_id(self):
        # `.tar.gz` alone should not produce an empty string crawl_id
        assert ga.extract_crawl_id("crawls/.tar.gz") is None


class TestCheckGcloudAuth:
    def test_exits_when_gcloud_not_installed(self, capsys):
        with patch("gcs_archive_audit._run_gcloud", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc:
                ga.check_gcloud_auth()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "gcloud" in err.lower()

    def test_exits_when_no_active_account(self, capsys):
        mock_result = MagicMock(stdout="", stderr="")
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            with pytest.raises(SystemExit) as exc:
                ga.check_gcloud_auth()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "No active gcloud account" in err

    def test_passes_when_account_active(self):
        mock_result = MagicMock(stdout="user@example.com\n", stderr="")
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            # Should not raise
            ga.check_gcloud_auth()


class TestGcloudLs:
    def test_short_listing(self):
        mock_result = MagicMock(
            stdout="gs://bucket/crawls/a.tar.gz\ngs://bucket/crawls/b.tar.gz\n",
            stderr="",
        )
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            result = ga.gcloud_ls("gs://bucket/crawls/")
        assert result == [
            "gs://bucket/crawls/a.tar.gz",
            "gs://bucket/crawls/b.tar.gz",
        ]

    def test_long_listing_parses_size(self):
        mock_result = MagicMock(
            stdout=(
                "12582912  2026-04-01T10:00:00Z  gs://bucket/crawls/a.tar.gz\n"
                "524288  2026-04-01T11:00:00Z  gs://bucket/crawls/b.tar.gz\n"
                "TOTAL: 2 objects, 13107200 bytes\n"
            ),
            stderr="",
        )
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            result = ga.gcloud_ls("gs://bucket/crawls/", long=True)
        assert result == [
            (12582912, "gs://bucket/crawls/a.tar.gz"),
            (524288, "gs://bucket/crawls/b.tar.gz"),
        ]

    def test_returns_empty_on_error(self, capsys):
        err = subprocess.CalledProcessError(1, "gcloud", stderr="permission denied")
        with patch("gcs_archive_audit._run_gcloud", side_effect=err):
            result = ga.gcloud_ls("gs://bucket/crawls/")
        assert result == []


class TestGcloudOperations:
    def test_download_shells_out(self, tmp_path):
        with patch("gcs_archive_audit._run_gcloud") as mock_run:
            ga.gcloud_download("gs://bucket/obj.tar.gz", tmp_path / "x.tar.gz")
        mock_run.assert_called_once_with(
            ["storage", "cp", "gs://bucket/obj.tar.gz", str(tmp_path / "x.tar.gz")]
        )

    def test_delete_shells_out(self):
        with patch("gcs_archive_audit._run_gcloud") as mock_run:
            ga.gcloud_delete("gs://bucket/obj.tar.gz")
        mock_run.assert_called_once_with(["storage", "rm", "gs://bucket/obj.tar.gz"])

    def test_move_shells_out(self):
        with patch("gcs_archive_audit._run_gcloud") as mock_run:
            ga.gcloud_move("gs://bucket/a", "gs://bucket/b")
        mock_run.assert_called_once_with(["storage", "mv", "gs://bucket/a", "gs://bucket/b"])
```

- [ ] **Step 4: Run the tests**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v
```

Expected: all tests PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/gcs_archive_audit.py tools/tests/
git commit -m "feat(tools): add gcs archive audit tool scaffolding — gcloud wrappers + auth check"
```

---

### Task 2: Archive inspection and classification

**Goal:** Add `classify_by_name` and `inspect_archive` functions that categorize each archive. Tests build real in-memory `.tar.gz` fixtures covering all 5 categories (OK, CORRUPTED, MISSING_PAYLOAD, MISSING_MARKER, ROW_COUNT_MISMATCH).

**Files:**
- Modify: `tools/gcs_archive_audit.py` (append new functions)
- Modify: `tools/tests/test_gcs_archive_audit.py` (append `TestArchiveInspection`)

**Acceptance Criteria:**
- [ ] `Category` string constants defined: `OK`, `WRONG_NAME`, `CORRUPTED`, `MISSING_PAYLOAD`, `MISSING_MARKER`, `ROW_COUNT_MISMATCH`, `DUPLICATE`, `INSPECTION_FAILED`
- [ ] `classify_by_name(object_name)` returns `WRONG_NAME` iff the object name ends in `.tmp.tar.gz`, else `None`
- [ ] `inspect_archive(local_tar_path)` returns `(category, details)` where details is a dict
- [ ] Fallback: if `storage/datasets/{domain}/` isn't in the tar, try `storage/datasets/{sanitized_domain}/` where `sanitized_domain = domain.replace('.', '-')`
- [ ] Fallback: if `stored_files_count` isn't in `_callback_payload.json`, use `success` field
- [ ] `domain` is read from `_callback_payload.json` — if missing, try the `crawler.log`'s `--domain=` arg (best effort). If neither found, category is `MISSING_PAYLOAD`.
- [ ] 8 new tests pass (OK, WRONG_NAME, CORRUPTED, MISSING_PAYLOAD, MISSING_MARKER, ROW_COUNT_MISMATCH, sanitized-domain fallback, success-field fallback)

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v`

**Steps:**

- [ ] **Step 1: Append the inspection functions to `tools/gcs_archive_audit.py`**

Add these to `tools/gcs_archive_audit.py` (after the existing functions, before end of file). Add `import json`, `import tarfile` at the top of the file if not already present.

Add to the imports at the top:

**Find:**

```python
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union
```

**Replace with:**

```python
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
```

Then append the following to the bottom of the file:

```python


# ---- Categories ----

OK = "OK"
WRONG_NAME = "WRONG_NAME"
CORRUPTED = "CORRUPTED"
MISSING_PAYLOAD = "MISSING_PAYLOAD"
MISSING_MARKER = "MISSING_MARKER"
ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
DUPLICATE = "DUPLICATE"
INSPECTION_FAILED = "INSPECTION_FAILED"


def classify_by_name(object_name: str) -> Optional[str]:
    """Return WRONG_NAME if the object name ends in `.tmp.tar.gz`, else None.

    Name-only screening — does not download or open the archive.
    """
    base = object_name.rsplit("/", 1)[-1]
    if base.endswith(".tmp.tar.gz"):
        return WRONG_NAME
    return None


def inspect_archive(local_tar_path: Path) -> Tuple[str, Dict]:
    """Open a .tar.gz and classify it.

    Returns (category, details). `details` always includes the callback-payload
    and marker read state; when row count is checked, it also includes
    `expected_count` and `actual_count`.
    """
    details: Dict = {}

    # 1. Integrity — can we open the tar at all?
    try:
        tar = tarfile.open(str(local_tar_path), "r:gz")
    except (tarfile.TarError, OSError, EOFError) as e:
        details["error"] = f"{type(e).__name__}: {e}"
        return CORRUPTED, details

    try:
        members = tar.getmembers()  # forces reading the full index; may raise on truncated tars
    except (tarfile.TarError, OSError, EOFError) as e:
        tar.close()
        details["error"] = f"{type(e).__name__}: {e}"
        return CORRUPTED, details

    try:
        # 2. Extract _callback_payload.json
        payload = _read_json_member(tar, "_callback_payload.json")
        if payload is None:
            details["missing"] = "_callback_payload.json"
            return MISSING_PAYLOAD, details
        details["payload"] = payload

        # 3. Extract _completion_marker.json
        marker = _read_json_member(tar, "_completion_marker.json")
        if marker is None:
            details["missing"] = "_completion_marker.json"
            return MISSING_MARKER, details
        details["marker"] = marker

        # 4. Row count check
        domain = payload.get("domain")
        if not domain:
            # Payload exists but lacks domain — treat as malformed payload
            details["missing"] = "domain field in _callback_payload.json"
            return MISSING_PAYLOAD, details

        expected = payload.get("stored_files_count")
        if expected is None:
            expected = payload.get("success")
        if expected is None:
            # Payload lacks any count field — treat as malformed
            details["missing"] = "stored_files_count/success field in _callback_payload.json"
            return MISSING_PAYLOAD, details

        actual = _count_dataset_files(members, domain)
        details["expected_count"] = int(expected)
        details["actual_count"] = actual

        if int(expected) != actual:
            return ROW_COUNT_MISMATCH, details

        return OK, details
    finally:
        tar.close()


def _read_json_member(tar: tarfile.TarFile, name: str) -> Optional[Dict]:
    """Read and parse a JSON file from the tar by exact member name. Returns None if absent."""
    try:
        member = tar.getmember(name)
    except KeyError:
        return None
    try:
        f = tar.extractfile(member)
        if f is None:
            return None
        return json.loads(f.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _count_dataset_files(members: List[tarfile.TarInfo], domain: str) -> int:
    """Count .json files under storage/datasets/{domain}/ (or sanitized variant).

    Returns the number of JSON files directly under the dataset directory.
    Matches the crawler's convention: one JSON file per successfully crawled URL.
    """
    sanitized = domain.replace(".", "-")
    candidates = [f"storage/datasets/{domain}/", f"storage/datasets/{sanitized}/"]

    for prefix in candidates:
        count = 0
        found_dir = False
        for m in members:
            if m.name.startswith(prefix):
                found_dir = True
                # Only count files (not nested directories), and only .json
                name_after_prefix = m.name[len(prefix):]
                if m.isfile() and "/" not in name_after_prefix and name_after_prefix.endswith(".json"):
                    count += 1
        if found_dir:
            return count
    return 0
```

- [ ] **Step 2: Append tests to `tools/tests/test_gcs_archive_audit.py`**

Append the following at the end of the file:

```python


import io
import json as _json
import tarfile as _tarfile


def _build_tar(tmp_path: Path, files: Dict[str, bytes], name: str = "test.tar.gz") -> Path:
    """Helper: build an in-memory tar.gz with the given files at the given paths.

    `files` is a dict of { path_in_tar: bytes_content }.
    """
    path = tmp_path / name
    with _tarfile.open(str(path), "w:gz") as tar:
        for p, content in files.items():
            info = _tarfile.TarInfo(name=p)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return path


def _payload(domain: str = "example.com", stored: int = 3, success: int | None = None) -> bytes:
    data = {"domain": domain, "stored_files_count": stored}
    if success is not None:
        data["success"] = success
    return _json.dumps(data).encode()


def _marker() -> bytes:
    return _json.dumps({"final_status": "finished", "exit_code": 0}).encode()


class TestClassifyByName:
    def test_tmp_tar_gz_is_wrong_name(self):
        assert ga.classify_by_name("crawls/4365.tmp.tar.gz") == ga.WRONG_NAME

    def test_plain_tar_gz_is_none(self):
        assert ga.classify_by_name("crawls/4365.tar.gz") is None

    def test_full_gs_uri(self):
        assert ga.classify_by_name("gs://b/crawls/4365.tmp.tar.gz") == ga.WRONG_NAME


from typing import Dict  # already imported above in the module; add at top of test file if missing


class TestArchiveInspection:
    def _ok_tar(self, tmp_path: Path) -> Path:
        """Build a tar with payload, marker, and 3 dataset files — matches stored_files_count=3."""
        return _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=3),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/url1.json": b'{"url": "a"}',
            "storage/datasets/example.com/url2.json": b'{"url": "b"}',
            "storage/datasets/example.com/url3.json": b'{"url": "c"}',
        })

    def test_ok_archive(self, tmp_path):
        path = self._ok_tar(tmp_path)
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["expected_count"] == 3
        assert details["actual_count"] == 3

    def test_corrupted_archive(self, tmp_path):
        # Write random bytes that are not a valid gzip
        path = tmp_path / "bad.tar.gz"
        path.write_bytes(b"this is not a gzip file at all")
        category, details = ga.inspect_archive(path)
        assert category == ga.CORRUPTED
        assert "error" in details

    def test_missing_payload(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_completion_marker.json": _marker(),
            # no _callback_payload.json
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_PAYLOAD
        assert "_callback_payload.json" in details.get("missing", "")

    def test_missing_marker(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(stored=3),
            # no _completion_marker.json
            "storage/datasets/example.com/x.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_MARKER
        assert "_completion_marker.json" in details.get("missing", "")

    def test_row_count_mismatch(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(stored=5),  # claims 5
            "_completion_marker.json": _marker(),
            # but only 2 dataset files
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.ROW_COUNT_MISMATCH
        assert details["expected_count"] == 5
        assert details["actual_count"] == 2

    def test_sanitized_domain_fallback(self, tmp_path):
        """If storage/datasets/{domain}/ is missing but the sanitized variant exists, use it."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="foo.com", stored=1),
            "_completion_marker.json": _marker(),
            # Only sanitized variant exists (foo-com not foo.com)
            "storage/datasets/foo-com/only.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["actual_count"] == 1

    def test_success_field_fallback(self, tmp_path):
        """If stored_files_count is absent but success is present, use success."""
        payload = _json.dumps({"domain": "example.com", "success": 2}).encode()
        path = _build_tar(tmp_path, {
            "_callback_payload.json": payload,
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["expected_count"] == 2

    def test_payload_missing_domain_field(self, tmp_path):
        payload = _json.dumps({"stored_files_count": 3}).encode()  # no domain
        path = _build_tar(tmp_path, {
            "_callback_payload.json": payload,
            "_completion_marker.json": _marker(),
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_PAYLOAD
        assert "domain" in details.get("missing", "")
```

- [ ] **Step 3: Run tests**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v
```

Expected: all tests PASS (11 from Task 1 + 3 `TestClassifyByName` + 8 `TestArchiveInspection` = 22 tests).

- [ ] **Step 4: Commit**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "feat(tools): add archive inspection and classification logic"
```

---

### Task 3: CLI + orchestration + remediation + duplicate detection

**Goal:** Add the `main()` function with argparse, the orchestration loop that audits every archive, duplicate detection, remediation (delete/quarantine), incremental report writing, and signal handling for graceful Ctrl+C.

**Files:**
- Modify: `tools/gcs_archive_audit.py` (append orchestration + main)
- Modify: `tools/tests/test_gcs_archive_audit.py` (append `TestOrchestration`)

**Acceptance Criteria:**
- [ ] `detect_duplicates(results)` tags each result with `DUPLICATE` as a secondary tag when any crawl_id appears more than once
- [ ] `remediate(obj_uri, category, action, quarantine_prefix)` performs `gcloud_delete` or `gcloud_move` depending on `action in {"delete", "quarantine"}`
- [ ] `write_report(path, report)` serializes the report dict to JSON with indent=2
- [ ] `main()` supports: `--bucket`, `--prefix`, `--output`, `--name-only`, `--limit`, `--delete`, `--quarantine`, `--yes`, `--resume`
- [ ] `--delete` and `--quarantine` are mutually exclusive (argparse error)
- [ ] Interactive confirmation prompt for `--delete`/`--quarantine` unless `--yes` passed
- [ ] SIGINT handler writes the partial report before exiting
- [ ] 6 orchestration tests pass

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v`

**Steps:**

- [ ] **Step 1: Append orchestration + main to `tools/gcs_archive_audit.py`**

Add `import argparse`, `import signal`, `import tempfile`, `from datetime import datetime, timezone` to the imports at the top.

**Find:**

```python
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
```

**Replace with:**

```python
import argparse
import json
import signal
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
```

Then append the following to the bottom of the file:

```python


# ---- Orchestration ----

REPORT_FLUSH_INTERVAL = 50  # write partial report every N archives


def detect_duplicates(archives: List[Dict]) -> None:
    """Mutates `archives` in place. Adds 'DUPLICATE' to the `secondary_tags` list
    of any archive whose crawl_id appears in more than one object."""
    counts: Dict[str, int] = {}
    for a in archives:
        cid = a.get("crawl_id")
        if cid:
            counts[cid] = counts.get(cid, 0) + 1

    for a in archives:
        cid = a.get("crawl_id")
        if cid and counts.get(cid, 0) > 1:
            a.setdefault("secondary_tags", [])
            if "DUPLICATE" not in a["secondary_tags"]:
                a["secondary_tags"].append("DUPLICATE")


def remediate(obj_uri: str, category: str, action: str, quarantine_prefix: Optional[str], bucket: str) -> str:
    """Perform delete or quarantine for a bad archive. Returns a human-readable
    description of what was done. Does nothing when category == OK."""
    if category == OK:
        return ""
    if action == "delete":
        gcloud_delete(obj_uri)
        return f"deleted {obj_uri}"
    if action == "quarantine":
        assert quarantine_prefix is not None
        # Object name relative to bucket, e.g. "crawls/4365.tar.gz" → "<quarantine_prefix>/4365.tar.gz"
        rel = obj_uri.replace(f"gs://{bucket}/", "", 1)
        base = rel.rsplit("/", 1)[-1]
        dst = f"gs://{bucket}/{quarantine_prefix.rstrip('/')}/{base}"
        gcloud_move(obj_uri, dst)
        return f"quarantined to {dst}"
    return ""


def write_report(path: Path, report: Dict) -> None:
    """Write the audit report to a JSON file with pretty formatting.
    Re-tallies the 'categories' counter from the archives list before writing."""
    # Refresh the categories counter so partial reports reflect actual state
    counts: Dict[str, int] = {}
    for a in report.get("archives", []):
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    report["categories"] = counts
    report["total_objects"] = len(report.get("archives", []))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)


def _confirm_or_exit(action: str, quarantine_prefix: Optional[str]) -> None:
    msg = f"About to {action} bad archives" + (
        f" (quarantine prefix: {quarantine_prefix})" if action == "quarantine" else ""
    ) + ". Continue? [y/N] "
    try:
        reply = input(msg).strip().lower()
    except EOFError:
        reply = ""
    if reply not in ("y", "yes"):
        print("Aborted.", file=sys.stderr)
        sys.exit(1)


def _print_summary(report: Dict) -> None:
    print("\n=== GCS Archive Audit ===")
    print(f"Bucket: {report['bucket']}")
    print(f"Prefix: {report['prefix']}")
    print(f"Audited: {report['total_objects']} archives\n")
    print("Categories:")
    for cat in (OK, WRONG_NAME, CORRUPTED, MISSING_PAYLOAD, MISSING_MARKER,
                ROW_COUNT_MISMATCH, DUPLICATE, INSPECTION_FAILED):
        count = report["categories"].get(cat, 0)
        if count:
            pct = (100.0 * count / report["total_objects"]) if report["total_objects"] else 0
            print(f"  {cat:<24} {count:>5}  ({pct:.1f}%)")


def _load_resume_set(resume_path: Optional[str]) -> set:
    """Load previously-audited object names from a prior report so we can skip them."""
    if not resume_path:
        return set()
    p = Path(resume_path)
    if not p.exists():
        return set()
    try:
        with open(p, "r", encoding="utf-8") as f:
            prior = json.load(f)
        return {a["object_name"] for a in prior.get("archives", [])}
    except (json.JSONDecodeError, KeyError, OSError):
        return set()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit GCS archives for corruption, incompleteness, and name issues."
    )
    parser.add_argument("--bucket", required=True, help="GCS bucket name (no gs:// prefix)")
    parser.add_argument("--prefix", default="crawls/", help="Object name prefix to scan (default: crawls/)")
    parser.add_argument("--output", default="gcs_archive_audit_report.json", help="Report output path")
    parser.add_argument("--name-only", action="store_true",
                        help="Fast mode: skip download/inspection, only check names")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of archives to audit (for testing)")
    parser.add_argument("--delete", action="store_true",
                        help="Delete bad archives (mutually exclusive with --quarantine)")
    parser.add_argument("--quarantine", default=None,
                        help="Prefix inside bucket to move bad archives to (mutually exclusive with --delete)")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation prompt for --delete/--quarantine")
    parser.add_argument("--resume", default=None,
                        help="Skip archives already present in the given prior report")
    args = parser.parse_args(argv)

    if args.delete and args.quarantine:
        parser.error("--delete and --quarantine are mutually exclusive")
    return args


def _inspect_one(obj_uri: str, size_bytes: int, name_only: bool) -> Tuple[str, Dict]:
    """Inspect a single archive. Returns (category, details)."""
    # Name-based screening first — cheap and catches WRONG_NAME without download.
    name_cat = classify_by_name(obj_uri)
    if name_cat is not None:
        return name_cat, {}
    if name_only:
        return OK, {}

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        try:
            gcloud_download(obj_uri, tmp_path)
        except subprocess.CalledProcessError as e:
            return INSPECTION_FAILED, {"error": f"download failed: {e.stderr}"}
        return inspect_archive(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    check_gcloud_auth()

    action: Optional[str] = None
    if args.delete:
        action = "delete"
    elif args.quarantine:
        action = "quarantine"
    if action and not args.yes:
        _confirm_or_exit(action, args.quarantine)

    # Build initial report skeleton
    report: Dict = {
        "bucket": args.bucket,
        "prefix": args.prefix,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "total_objects": 0,
        "categories": {},
        "archives": [],
    }
    report_path = Path(args.output)

    # SIGINT handler to write partial report before exiting
    def _on_sigint(signum, frame):
        print("\nInterrupted — writing partial report...", file=sys.stderr)
        detect_duplicates(report["archives"])
        write_report(report_path, report)
        sys.exit(130)

    signal.signal(signal.SIGINT, _on_sigint)

    skip_set = _load_resume_set(args.resume)

    # List
    uri = f"gs://{args.bucket}/{args.prefix}"
    listing = gcloud_ls(uri, long=True)
    total = len(listing)
    print(f"Found {total} objects under {uri}. Beginning audit...")

    processed = 0
    for size_bytes, obj_uri in listing:
        if obj_uri in skip_set:
            continue
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        entry: Dict = {
            "object_name": obj_uri.replace(f"gs://{args.bucket}/", "", 1),
            "crawl_id": extract_crawl_id(obj_uri),
            "size_bytes": size_bytes,
            "category": OK,
            "secondary_tags": [],
            "actions_taken": [],
        }

        category, details = _inspect_one(obj_uri, size_bytes, args.name_only)
        entry["category"] = category
        if details.get("expected_count") is not None:
            entry["expected_count"] = details["expected_count"]
            entry["actual_count"] = details["actual_count"]
        if details.get("error"):
            entry["error"] = details["error"]

        if action and category != OK:
            try:
                note = remediate(obj_uri, category, action, args.quarantine, args.bucket)
                if note:
                    entry["actions_taken"].append(note)
            except subprocess.CalledProcessError as e:
                entry["actions_taken"].append(f"remediation failed: {e.stderr}")

        report["archives"].append(entry)

        if processed % REPORT_FLUSH_INTERVAL == 0:
            detect_duplicates(report["archives"])
            write_report(report_path, report)
            print(f"  ...audited {processed}/{total}")

    # Final duplicate detection + write
    detect_duplicates(report["archives"])
    write_report(report_path, report)
    _print_summary(report)
    print(f"\nFull report written to: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Append orchestration tests to `tools/tests/test_gcs_archive_audit.py`**

```python


class TestDetectDuplicates:
    def test_tags_duplicate_crawl_ids(self):
        archives = [
            {"object_name": "crawls/4365.tar.gz", "crawl_id": "4365", "category": ga.OK, "secondary_tags": []},
            {"object_name": "crawls/4365.tmp.tar.gz", "crawl_id": "4365", "category": ga.WRONG_NAME, "secondary_tags": []},
            {"object_name": "crawls/5000.tar.gz", "crawl_id": "5000", "category": ga.OK, "secondary_tags": []},
        ]
        ga.detect_duplicates(archives)
        assert "DUPLICATE" in archives[0]["secondary_tags"]
        assert "DUPLICATE" in archives[1]["secondary_tags"]
        assert "DUPLICATE" not in archives[2]["secondary_tags"]

    def test_no_duplicates_when_all_unique(self):
        archives = [
            {"crawl_id": "1", "category": ga.OK, "secondary_tags": []},
            {"crawl_id": "2", "category": ga.OK, "secondary_tags": []},
        ]
        ga.detect_duplicates(archives)
        assert all("DUPLICATE" not in a["secondary_tags"] for a in archives)


class TestRemediate:
    def test_delete(self):
        with patch("gcs_archive_audit.gcloud_delete") as mock_del:
            note = ga.remediate("gs://b/crawls/4365.tmp.tar.gz", ga.WRONG_NAME, "delete", None, "b")
        mock_del.assert_called_once_with("gs://b/crawls/4365.tmp.tar.gz")
        assert "deleted" in note

    def test_quarantine(self):
        with patch("gcs_archive_audit.gcloud_move") as mock_mv:
            note = ga.remediate("gs://b/crawls/4365.tmp.tar.gz", ga.WRONG_NAME, "quarantine", "quarantine/", "b")
        mock_mv.assert_called_once_with(
            "gs://b/crawls/4365.tmp.tar.gz",
            "gs://b/quarantine/4365.tmp.tar.gz",
        )
        assert "quarantined" in note

    def test_ok_skips_action(self):
        with patch("gcs_archive_audit.gcloud_delete") as mock_del:
            note = ga.remediate("gs://b/crawls/x.tar.gz", ga.OK, "delete", None, "b")
        mock_del.assert_not_called()
        assert note == ""


class TestArgs:
    def test_delete_and_quarantine_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            ga.parse_args(["--bucket", "b", "--delete", "--quarantine", "q/"])

    def test_bucket_is_required(self):
        with pytest.raises(SystemExit):
            ga.parse_args([])

    def test_defaults(self):
        args = ga.parse_args(["--bucket", "b"])
        assert args.bucket == "b"
        assert args.prefix == "crawls/"
        assert args.delete is False
        assert args.quarantine is None
        assert args.name_only is False
```

- [ ] **Step 3: Run tests**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v
```

Expected: all tests PASS (22 from Tasks 1+2 + 8 new = 30 tests).

- [ ] **Step 4: Sanity-check the CLI parses without a real bucket**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && python tools/gcs_archive_audit.py --help
```

Expected: argparse prints the usage and exits 0.

- [ ] **Step 5: Commit**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "feat(tools): add gcs audit CLI with duplicate detection and remediation"
```

---

### Task 4: Update tools/CLAUDE.md

**Goal:** Document the new script in the existing `tools/CLAUDE.md` so future readers know it exists, what it does, and how to invoke it.

**Files:**
- Modify: `tools/CLAUDE.md`

**Acceptance Criteria:**
- [ ] `gcs_archive_audit.py` appears in the File Inventory with a one-line description
- [ ] A new entry appears in the Run section showing a minimal invocation
- [ ] Authentication prerequisites (`gcloud auth login`) are mentioned in the Conventions or Run section

**Verify:** `grep -q "gcs_archive_audit" tools/CLAUDE.md && echo OK`

**Steps:**

- [ ] **Step 1: Update the Run section**

Open `tools/CLAUDE.md`. Find the `## Run` section and add a new code-fenced block after the existing GCS daemons block.

**Find:**

```markdown
# GCS daemons
bash tools/upload_daemon.sh
bash tools/download_daemon.sh
```

**Replace with:**

```markdown
# GCS daemons
bash tools/upload_daemon.sh
bash tools/download_daemon.sh

# GCS Archive Audit (one-shot, requires gcloud auth login first)
python tools/gcs_archive_audit.py --bucket <name> --output report.json
python tools/gcs_archive_audit.py --bucket <name> --name-only            # fast mode: names only
python tools/gcs_archive_audit.py --bucket <name> --quarantine quarantine/ --yes   # move bad archives
python tools/gcs_archive_audit.py --bucket <name> --delete --yes                    # delete bad archives
```

- [ ] **Step 2: Update the File Inventory section**

**Find:**

```markdown
download_daemon.sh   # Polls for .request files, downloads from GCS, writes .done marker
```

**Replace with:**

```markdown
download_daemon.sh     # Polls for .request files, downloads from GCS, writes .done marker
gcs_archive_audit.py   # Audits GCS archives for corruption/incompleteness, optional --delete/--quarantine
```

- [ ] **Step 3: Update Conventions section**

**Find:**

```markdown
- GCS daemons use file-based signaling (.request/.done/.error markers).
```

**Replace with:**

```markdown
- GCS daemons use file-based signaling (.request/.done/.error markers).
- `gcs_archive_audit.py` uses `gcloud storage` CLI (no Python GCS library). Run `gcloud auth login` or activate a service account key before invoking.
```

- [ ] **Step 4: Verify and commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && grep -q "gcs_archive_audit" tools/CLAUDE.md && echo OK
```

Expected: `OK`.

```bash
git add tools/CLAUDE.md
git commit -m "docs(tools): document gcs archive audit tool"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Shell out to `gcloud storage` (no Python GCS library) | Task 1 |
| `gcloud_ls`, `gcloud_download`, `gcloud_delete`, `gcloud_move` wrappers | Task 1 |
| `check_gcloud_auth` startup guard | Task 1 |
| `extract_crawl_id` parser (handles `.tar.gz` and `.tmp.tar.gz`) | Task 1 |
| Categories: OK/WRONG_NAME/CORRUPTED/MISSING_PAYLOAD/MISSING_MARKER/ROW_COUNT_MISMATCH/DUPLICATE/INSPECTION_FAILED | Task 2 (+ Task 3 for DUPLICATE) |
| `classify_by_name` name-only screening | Task 2 |
| `inspect_archive` tar open + payload + marker + row count | Task 2 |
| Fallback `{domain}` ↔ `{sanitized_domain}` | Task 2 |
| Fallback `stored_files_count` ↔ `success` | Task 2 |
| Option A: count main `{domain}/` only | Task 2 |
| `detect_duplicates` secondary tagging | Task 3 |
| `remediate` with delete + quarantine | Task 3 |
| `write_report` with incremental flush | Task 3 |
| Argparse: `--bucket`, `--prefix`, `--output`, `--name-only`, `--limit`, `--delete`, `--quarantine`, `--yes`, `--resume` | Task 3 |
| `--delete` and `--quarantine` mutually exclusive | Task 3 |
| Interactive confirmation unless `--yes` | Task 3 |
| SIGINT partial report flush | Task 3 |
| JSON report format per spec | Task 3 (write_report) |
| Summary table to stdout | Task 3 (_print_summary) |
| Documentation in tools/CLAUDE.md | Task 4 |
