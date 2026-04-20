# GCS Audit Prefix Fix + Quarantine Restore — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the audit tool's tar-member lookup to handle the leading `./` prefix produced by `shutil.make_archive`, replace unrealistic test fixtures with ones that match real archive layout, and add a `--restore-from-quarantine` flag to recover from the prior faulty audit run.

**Architecture:** Small surgical edits to `tools/gcs_archive_audit.py` + its test module. Add a `_normalize_member_name` helper; change `_read_json_member` to iterate + normalize instead of using exact-name `getmember`; add normalization to `_count_dataset_files`'s prefix comparison. Replace the `_build_tar` test helper with a version that uses `shutil.make_archive` — producing the real `./`-prefixed layout. Add a `restore_from_quarantine` function + `--restore-from-quarantine` CLI flag that moves all objects from a quarantine prefix back to the main prefix and exits.

**Tech Stack:** Python stdlib (`tarfile`, `shutil`, `argparse`, `subprocess`); pytest; `gcloud` CLI (runtime).

**Spec:** `docs/superpowers/specs/2026-04-19-gcs-audit-prefix-fix-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/gcs_archive_audit.py` | MODIFY | Add `_normalize_member_name`; rewrite `_read_json_member` + `_count_dataset_files` to normalize; add `restore_from_quarantine` function; add `--restore-from-quarantine` argparse option + early-exit branch in `main` |
| `tools/tests/test_gcs_archive_audit.py` | MODIFY | Replace `_build_tar` helper to use `shutil.make_archive`; add `TestPathNormalization`; add `TestRestoreFromQuarantine` |
| `tools/CLAUDE.md` | MODIFY | Add recovery workflow example under "Run"; note the tool handles `./` prefix automatically |

---

### Task 1: Fix tar member normalization in audit tool

**Goal:** Add `_normalize_member_name` helper and update `_read_json_member` + `_count_dataset_files` to compare members by normalized name, so real `./`-prefixed archives are correctly inspected.

**Files:**
- Modify: `tools/gcs_archive_audit.py:223-259` (the two helpers)
- Modify: `tools/tests/test_gcs_archive_audit.py:117-128` (replace `_build_tar` with realistic fixture)

**Acceptance Criteria:**
- [ ] `_normalize_member_name` strips leading `./`, maps standalone `.` to `""`, leaves other names unchanged
- [ ] `_read_json_member` finds `_callback_payload.json` in a tar whose members are `./_callback_payload.json`
- [ ] `_count_dataset_files` correctly counts files under `./storage/datasets/{domain}/`
- [ ] `_build_tar` helper uses `shutil.make_archive` so fixtures now match real crawler output
- [ ] All pre-existing `TestArchiveInspection` tests still pass (they exercised the old hand-crafted layout — now they exercise the real layout)

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v`

**Steps:**

- [ ] **Step 1: Replace `_read_json_member` and `_count_dataset_files` in `tools/gcs_archive_audit.py`**

Find this block (lines ~223-259):

```python
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

Replace with:

```python
def _normalize_member_name(name: str) -> str:
    """Strip leading './' or '.' from tar member names.

    shutil.make_archive passes base_dir='.' to tarfile, which produces members
    like './_callback_payload.json' (not 'foo.txt'). Normalization lets us
    compare against unprefixed expected names regardless of how the tar was
    produced.
    """
    if name.startswith("./"):
        return name[2:]
    if name == ".":
        return ""
    return name


def _read_json_member(tar: tarfile.TarFile, name: str) -> Optional[Dict]:
    """Read and parse a JSON file from the tar. Handles tars produced by
    shutil.make_archive (which prefix members with './').

    Iterates members and compares by normalized name rather than using
    getmember() — getmember() is exact-name lookup and would miss './foo'
    when asked for 'foo'.
    """
    for member in tar.getmembers():
        if _normalize_member_name(member.name) == name:
            try:
                f = tar.extractfile(member)
                if f is None:
                    return None
                return json.loads(f.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                return None
    return None


def _count_dataset_files(members: List[tarfile.TarInfo], domain: str) -> int:
    """Count .json files under storage/datasets/{domain}/ (or sanitized variant).

    Normalizes member names before prefix comparison so './storage/datasets/...'
    correctly matches 'storage/datasets/...'.

    Returns the number of JSON files directly under the dataset directory.
    Matches the crawler's convention: one JSON file per successfully crawled URL.
    """
    sanitized = domain.replace(".", "-")
    candidates = [f"storage/datasets/{domain}/", f"storage/datasets/{sanitized}/"]

    for prefix in candidates:
        count = 0
        found_dir = False
        for m in members:
            normalized = _normalize_member_name(m.name)
            if normalized.startswith(prefix):
                found_dir = True
                # Only count files (not nested directories), and only .json
                name_after_prefix = normalized[len(prefix):]
                if m.isfile() and "/" not in name_after_prefix and name_after_prefix.endswith(".json"):
                    count += 1
        if found_dir:
            return count
    return 0
```

- [ ] **Step 2: Replace `_build_tar` helper in `tools/tests/test_gcs_archive_audit.py`**

Find this block (lines ~111-128):

```python
import io
import json as _json
import tarfile as _tarfile
from typing import Dict


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
```

Replace with:

```python
import json as _json
import shutil as _shutil
import tarfile as _tarfile
from typing import Dict


def _build_tar(tmp_path: Path, files: Dict[str, bytes], name: str = "test") -> Path:
    """Helper: build a realistic tar.gz using shutil.make_archive.

    This matches the crawler's actual archiving code path (crawler_manager.py's
    `_create_archive` calls `shutil.make_archive(..., root_dir=job_storage_path)`).
    Resulting members will have './' prefix — exactly as real archives do.

    `files` is a dict of { path_in_tar: bytes_content }. The `name` parameter
    is the base name (without extension); the returned path ends in `.tar.gz`.
    """
    staging = tmp_path / f"staging_{name}"
    staging.mkdir(exist_ok=True)
    for path, content in files.items():
        full_path = staging / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
    archive_base = str(tmp_path / name)
    archive_path = _shutil.make_archive(archive_base, 'gztar', root_dir=str(staging))
    return Path(archive_path)
```

Note: `import io` is removed (no longer needed). `shutil` is added as `_shutil` to avoid colliding with any other `shutil` usage in the file.

- [ ] **Step 3: Update tests that relied on `_build_tar`'s old `name` semantics**

The old helper defaulted `name="test.tar.gz"` and placed the archive at `tmp_path / name`. The new helper defaults `name="test"` and `shutil.make_archive` appends `.tar.gz`. Net effect: same filename (`test.tar.gz`), same location. No test call-site needs adjustment — existing tests pass `tmp_path` only or `tmp_path, files` and don't depend on the extension being in `name`.

However, one existing test (`test_corrupted_archive`) writes raw bytes directly to a path without using `_build_tar`, bypassing the helper. That test still works — just verify no regression.

- [ ] **Step 4: Add a regression test in `TestPathNormalization`**

Append to `tools/tests/test_gcs_archive_audit.py` (at the end of the file):

```python


class TestPathNormalization:
    """Regression tests for tar-member '.' prefix handling.
    Real archives produced by shutil.make_archive contain './'-prefixed members."""

    def test_fixture_actually_produces_dot_slash_prefix(self, tmp_path):
        """Sanity-check the _build_tar helper matches the real crawler layout."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=1),
        })
        with _tarfile.open(str(path), 'r:gz') as t:
            names = [m.name for m in t.getmembers()]
        assert any(n.startswith("./") for n in names), (
            f"Fixture should produce './' prefixed members, got: {names}"
        )

    def test_payload_found_despite_leading_dot_slash(self, tmp_path):
        """The audit must classify a well-formed archive as OK even though
        its members have the './' prefix from shutil.make_archive."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=1),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["actual_count"] == 1

    def test_normalize_strips_dot_slash_prefix(self):
        assert ga._normalize_member_name("./_callback_payload.json") == "_callback_payload.json"

    def test_normalize_maps_bare_dot_to_empty(self):
        assert ga._normalize_member_name(".") == ""

    def test_normalize_leaves_unprefixed_names_unchanged(self):
        assert ga._normalize_member_name("foo/bar.json") == "foo/bar.json"
```

- [ ] **Step 5: Run tests**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v
```

Expected: all pre-existing tests still pass + 5 new `TestPathNormalization` tests pass. Total test count goes up by 5.

- [ ] **Step 6: Commit (English only — do not ask)**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "fix(tools): handle './' prefix in tar member names for gcs audit"
```

---

### Task 2: Add `restore_from_quarantine` function and `--restore-from-quarantine` CLI flag

**Goal:** Allow users to move all objects from a quarantine prefix back to the main prefix in one command, so the fixed audit can re-classify them.

**Files:**
- Modify: `tools/gcs_archive_audit.py` — add `restore_from_quarantine` function; add argparse flag; route in `main()`
- Modify: `tools/tests/test_gcs_archive_audit.py` — add `TestRestoreFromQuarantine`

**Acceptance Criteria:**
- [ ] `restore_from_quarantine(bucket, quarantine_prefix, target_prefix)` calls `gcloud_ls` on the quarantine URI, then `gcloud_move` each object to the target prefix with preserved basename
- [ ] Returns the integer count of successfully-moved objects
- [ ] Handles empty quarantine cleanly (logs, returns 0, no errors)
- [ ] Argparse accepts `--restore-from-quarantine PREFIX` (nullable)
- [ ] When `--restore-from-quarantine` is set, `main()` prompts for confirmation (unless `--yes`), calls `restore_from_quarantine`, prints the count, and exits with 0 — the normal audit flow is skipped
- [ ] 3 unit tests pass

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py::TestRestoreFromQuarantine -v` → all tests pass; `python tools/gcs_archive_audit.py --help` lists the new flag

**Steps:**

- [ ] **Step 1: Add `restore_from_quarantine` function to `tools/gcs_archive_audit.py`**

Find the existing `remediate` function (search for `def remediate(`). Immediately after `remediate`, add the new function:

**Find:**

```python
def remediate(obj_uri: str, category: str, action: str, quarantine_prefix: Optional[str], bucket: str) -> str:
```

Leave that function alone. Scroll to its end (the line after `return ""`). Insert AFTER `remediate` ends:

```python


def restore_from_quarantine(bucket: str, quarantine_prefix: str, target_prefix: str = "crawls/") -> int:
    """Move all objects from gs://{bucket}/{quarantine_prefix}/ back to
    gs://{bucket}/{target_prefix}/, preserving basenames.

    Used to recover from a faulty prior audit that quarantined false positives.
    Returns the count of successfully-moved objects. Individual failures are
    logged but do not abort the whole operation.
    """
    quarantine_uri = f"gs://{bucket}/{quarantine_prefix.rstrip('/')}/"
    listing = gcloud_ls(quarantine_uri)
    if not listing:
        print(f"No objects under {quarantine_uri}")
        return 0

    count = 0
    for obj_uri in listing:
        if not isinstance(obj_uri, str):
            # gcloud_ls called without long=True returns List[str]; defensive guard
            continue
        basename = obj_uri.rsplit("/", 1)[-1]
        dst = f"gs://{bucket}/{target_prefix.rstrip('/')}/{basename}"
        try:
            gcloud_move(obj_uri, dst)
            print(f"Restored: {basename}")
            count += 1
        except subprocess.CalledProcessError as e:
            stderr = e.stderr if hasattr(e, 'stderr') else str(e)
            print(f"Failed to restore {basename}: {stderr}", file=sys.stderr)
    return count
```

- [ ] **Step 2: Add the argparse flag and early-exit branch in `main()`**

In `tools/gcs_archive_audit.py`, find `parse_args` (search for `def parse_args`). Add the flag in the same location as the other flags:

**Find:**

```python
    parser.add_argument("--resume", default=None,
                        help="Skip archives already present in the given prior report")
```

**Replace with:**

```python
    parser.add_argument("--resume", default=None,
                        help="Skip archives already present in the given prior report")
    parser.add_argument("--restore-from-quarantine", default=None, metavar="PREFIX",
                        help="Move all objects from gs://<bucket>/<PREFIX>/ back to "
                             "gs://<bucket>/<--prefix>/, then exit. Used to recover from "
                             "a faulty prior audit run.")
```

Now find the start of `main` (search for `def main(`). Immediately after the `args = parse_args(argv)` line and the `check_gcloud_auth()` call, add the early-exit branch.

**Find:**

```python
def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    check_gcloud_auth()

    action: Optional[str] = None
```

**Replace with:**

```python
def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    check_gcloud_auth()

    # Early exit: restore-from-quarantine is a separate top-level operation.
    # It does not run the normal audit flow.
    if args.restore_from_quarantine:
        if not args.yes:
            _confirm_or_exit(
                f"restore from quarantine '{args.restore_from_quarantine}'",
                quarantine_prefix=None,
            )
        count = restore_from_quarantine(
            args.bucket, args.restore_from_quarantine, args.prefix
        )
        print(f"\nRestored {count} objects.")
        return 0

    action: Optional[str] = None
```

- [ ] **Step 3: Add `TestRestoreFromQuarantine` to `tools/tests/test_gcs_archive_audit.py`**

Append at the end of the file:

```python


class TestRestoreFromQuarantine:
    def test_moves_every_quarantined_object_to_target_prefix(self):
        quarantined = [
            "gs://b/crawls-quarantine/4365.tar.gz",
            "gs://b/crawls-quarantine/4683.tar.gz",
        ]
        with patch("gcs_archive_audit.gcloud_ls", return_value=quarantined) as mock_ls, \
             patch("gcs_archive_audit.gcloud_move") as mock_mv:
            count = ga.restore_from_quarantine("b", "crawls-quarantine/", "crawls/")

        assert count == 2
        mock_ls.assert_called_once_with("gs://b/crawls-quarantine/")
        # Each object moved to gs://b/crawls/{basename}
        assert mock_mv.call_args_list == [
            (("gs://b/crawls-quarantine/4365.tar.gz", "gs://b/crawls/4365.tar.gz"),),
            (("gs://b/crawls-quarantine/4683.tar.gz", "gs://b/crawls/4683.tar.gz"),),
        ]

    def test_returns_zero_when_quarantine_is_empty(self, capsys):
        with patch("gcs_archive_audit.gcloud_ls", return_value=[]):
            count = ga.restore_from_quarantine("b", "crawls-quarantine/", "crawls/")

        assert count == 0
        out = capsys.readouterr().out
        assert "No objects under" in out

    def test_continues_after_individual_move_failure(self, capsys):
        quarantined = [
            "gs://b/crawls-quarantine/ok.tar.gz",
            "gs://b/crawls-quarantine/fail.tar.gz",
            "gs://b/crawls-quarantine/another.tar.gz",
        ]
        err = subprocess.CalledProcessError(1, "gcloud", stderr="permission denied")

        def _move(src, dst):
            if "fail" in src:
                raise err

        with patch("gcs_archive_audit.gcloud_ls", return_value=quarantined), \
             patch("gcs_archive_audit.gcloud_move", side_effect=_move):
            count = ga.restore_from_quarantine("b", "crawls-quarantine/", "crawls/")

        # 2 succeed, 1 fails
        assert count == 2
        err_out = capsys.readouterr().err
        assert "Failed to restore fail.tar.gz" in err_out
```

- [ ] **Step 4: Run tests**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v
```

Expected: all pre-existing tests still pass + 3 new `TestRestoreFromQuarantine` tests pass.

- [ ] **Step 5: Verify `--help` shows the new flag**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && python tools/gcs_archive_audit.py --help
```

Expected: `--restore-from-quarantine PREFIX` appears in the usage output.

- [ ] **Step 6: Commit (English only — do not ask)**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "feat(tools): add --restore-from-quarantine flag to gcs audit"
```

---

### Task 3: Document the recovery workflow in tools/CLAUDE.md

**Goal:** Add the post-fix recovery workflow (restore + re-audit) to the Run section of `tools/CLAUDE.md` so future readers know how to use the new flag.

**Files:**
- Modify: `tools/CLAUDE.md`

**Acceptance Criteria:**
- [ ] New Run example shows the restore command
- [ ] Brief explanation notes that this recovers from a prior faulty audit
- [ ] `grep -q "restore-from-quarantine" tools/CLAUDE.md` succeeds

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && grep -q "restore-from-quarantine" tools/CLAUDE.md && echo OK`

**Steps:**

- [ ] **Step 1: Add the recovery example to `tools/CLAUDE.md`**

Find the existing block that lists the gcs_archive_audit.py invocations:

**Find:**

```markdown
# GCS Archive Audit (one-shot, requires gcloud auth login first)
python tools/gcs_archive_audit.py --bucket <name> --output report.json
python tools/gcs_archive_audit.py --bucket <name> --name-only            # fast mode: names only
python tools/gcs_archive_audit.py --bucket <name> --quarantine quarantine/ --yes   # move bad archives
python tools/gcs_archive_audit.py --bucket <name> --delete --yes                    # delete bad archives
```

**Replace with:**

```markdown
# GCS Archive Audit (one-shot, requires gcloud auth login first)
python tools/gcs_archive_audit.py --bucket <name> --output report.json
python tools/gcs_archive_audit.py --bucket <name> --name-only            # fast mode: names only
python tools/gcs_archive_audit.py --bucket <name> --quarantine quarantine/ --yes   # move bad archives
python tools/gcs_archive_audit.py --bucket <name> --delete --yes                    # delete bad archives

# Recover from a faulty prior audit (move quarantined archives back to crawls/):
python tools/gcs_archive_audit.py --bucket <name> --restore-from-quarantine crawls-quarantine/ --yes
# Then re-audit so the fixed classifier re-quarantines only the real bad ones:
python tools/gcs_archive_audit.py --bucket <name> --quarantine crawls-quarantine/ --yes --output corrected_report.json
```

- [ ] **Step 2: Verify**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && grep -q "restore-from-quarantine" tools/CLAUDE.md && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit (English only — do not ask)**

```bash
git add tools/CLAUDE.md
git commit -m "docs(tools): document gcs audit restore-from-quarantine workflow"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| `_normalize_member_name` helper strips `./` and maps `.` to `""` | Task 1 |
| `_read_json_member` iterates members, compares by normalized name | Task 1 |
| `_count_dataset_files` normalizes before `startswith` comparison | Task 1 |
| `_build_tar` test helper uses `shutil.make_archive` | Task 1 |
| Regression test asserts fixture produces `./`-prefixed members | Task 1 (test `test_fixture_actually_produces_dot_slash_prefix`) |
| `restore_from_quarantine` function in tool module | Task 2 |
| `--restore-from-quarantine PREFIX` argparse flag | Task 2 |
| `main()` early-exit branch when flag is set | Task 2 |
| Confirmation prompt unless `--yes` | Task 2 |
| Empty quarantine handled gracefully | Task 2 (test `test_returns_zero_when_quarantine_is_empty`) |
| Partial move failures logged but don't abort | Task 2 (test `test_continues_after_individual_move_failure`) |
| Recovery workflow documented | Task 3 |
| No changes to crawler-service archiving code | Confirmed — no files outside `tools/` are modified |
| Category definitions, report format, duplicate detection unchanged | Confirmed — no changes to these |
