# Design: GCS Audit Tool — Tar Member Prefix Fix + Quarantine Restore

**Date:** 2026-04-19
**Service:** `tools/gcs_archive_audit.py`
**Status:** Approved

## Problem

A real audit run (117 archives) produced `0 OK` classifications, with 93 archives (~80%) falsely flagged as `MISSING_PAYLOAD` and moved to `crawls-quarantine/`. The audit tool has two related bugs:

1. **`_read_json_member` uses exact-name lookup via `tarfile.TarFile.getmember()`**. Real archives produced by `shutil.make_archive(root_dir=job_storage_path)` contain members with a leading `./` prefix (e.g., `./_callback_payload.json`). The lookup `getmember("_callback_payload.json")` raises `KeyError`, so the tool concludes the payload is missing.

2. **`_count_dataset_files` compares `m.name.startswith("storage/datasets/{domain}/")`**. Same prefix issue — real members start with `./storage/datasets/...`, so the prefix comparison never matches, and row counts are all reported as `0`. This bug is currently masked by bug #1 (MISSING_PAYLOAD short-circuits before row count runs), but it would surface the moment #1 is fixed.

The audit's test suite passed because test fixtures were built via `tarfile.TarInfo(name="_callback_payload.json")` without the `./` prefix — an unrealistic layout that `shutil.make_archive` never produces.

Consequence: 93 false-positive quarantined archives need to be restored, and the tool+tests need correcting before the re-audit.

## Decision

Fix the audit tool by normalizing tar member names on every comparison, fix the test fixtures to use `shutil.make_archive` (matching the crawler's real behavior), and add a `--restore-from-quarantine` command to move falsely-quarantined archives back before re-auditing.

## Design

### Client-side changes (audit tool)

**1. Helper: `_normalize_member_name(name: str) -> str`**

Strip the leading `./` (or standalone `.`) from tar member names so unprefixed expected names match the real prefixed ones.

```python
def _normalize_member_name(name: str) -> str:
    """Strip leading './' or '.' from tar member names. shutil.make_archive
    produces members with './' prefix (because it passes base_dir='.' to tarfile);
    this normalization lets us compare against unprefixed expected names."""
    if name.startswith("./"):
        return name[2:]
    if name == ".":
        return ""
    return name
```

**2. `_read_json_member` — iterate-and-normalize**

Replace `getmember(name)` with a member iteration that compares by normalized name:

```python
def _read_json_member(tar: tarfile.TarFile, name: str) -> Optional[Dict]:
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
```

**3. `_count_dataset_files` — normalize before `startswith` comparison**

```python
def _count_dataset_files(members, domain: str) -> int:
    sanitized = domain.replace(".", "-")
    candidates = [f"storage/datasets/{domain}/", f"storage/datasets/{sanitized}/"]

    for prefix in candidates:
        count = 0
        found_dir = False
        for m in members:
            normalized = _normalize_member_name(m.name)
            if normalized.startswith(prefix):
                found_dir = True
                name_after_prefix = normalized[len(prefix):]
                if m.isfile() and "/" not in name_after_prefix and name_after_prefix.endswith(".json"):
                    count += 1
        if found_dir:
            return count
    return 0
```

### Quarantine restore

Add `restore_from_quarantine(bucket, quarantine_prefix, target_prefix)` that moves every object under `gs://{bucket}/{quarantine_prefix}/` back to `gs://{bucket}/{target_prefix}/`, preserving basenames. Used to recover after a faulty audit run.

New argparse flag:

```python
parser.add_argument(
    "--restore-from-quarantine", default=None, metavar="PREFIX",
    help="Move all objects from gs://{bucket}/<PREFIX>/ back to gs://{bucket}/<--prefix>/, "
         "then exit. Used to recover from a faulty prior audit."
)
```

In `main()`, restore runs as an alternate top-level operation — if `--restore-from-quarantine` is set, it prompts for confirmation (unless `--yes`), performs the moves, and returns before the normal audit flow. `--restore-from-quarantine` is mutually exclusive with normal audit flags (the tool exits after restoring).

### Test fixture overhaul

Replace the existing `_build_tar` helper in `tools/tests/test_gcs_archive_audit.py` with a version that uses `shutil.make_archive`, matching the crawler's real archiving code path. All existing tests continue to pass the same `files` dict argument; only the helper's internals change. This means real archives produced by tests will have the `./` prefix too — validating the normalization fix end-to-end.

Add one regression test that asserts the fixture actually produces `./`-prefixed members AND that the tool still classifies it as `OK`:

```python
class TestPathNormalization:
    def test_payload_found_despite_leading_dot_slash(self, tmp_path):
        """Regression test: real archives have './' prefix; lookup must handle it."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=1),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
        })
        # Sanity-check the fixture really uses './' prefix
        with tarfile.open(str(path), 'r:gz') as t:
            names = [m.name for m in t.getmembers()]
            assert any(n.startswith("./") for n in names), (
                f"Fixture should produce './' prefixed members, got: {names}"
            )
        # Main check
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["actual_count"] == 1
```

Add a minimal test for `restore_from_quarantine` that mocks `gcloud_ls` and `gcloud_move` to verify every quarantined object gets moved with the correct destination URI.

### Recovery workflow (what the user runs after the fix)

```bash
# 1. Restore all previously quarantined archives
python tools/gcs_archive_audit.py --bucket <name> \
    --restore-from-quarantine crawls-quarantine/ --yes

# 2. Re-audit with corrected tool
python tools/gcs_archive_audit.py --bucket <name> \
    --quarantine crawls-quarantine/ --yes --output corrected_report.json
```

Expected after re-audit:
- ~10 `WRONG_NAME` re-quarantined (legitimately bad — `.tmp.tar.gz` suffix)
- ~14 `CORRUPTED` re-quarantined (legitimately bad — broken gzip)
- ~93 previously-misclassified archives stay in `crawls/` as `OK` (or get a new category like `ROW_COUNT_MISMATCH` now that the row-count check is actually executing)

### Files to modify

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/gcs_archive_audit.py` | MODIFY | Add `_normalize_member_name`, update `_read_json_member` + `_count_dataset_files`, add `restore_from_quarantine` + `--restore-from-quarantine` flag + `main()` early-exit branch |
| `tools/tests/test_gcs_archive_audit.py` | MODIFY | Replace `_build_tar` helper with `shutil.make_archive`-based version; add `TestPathNormalization`; add `TestRestoreFromQuarantine` |
| `tools/CLAUDE.md` | MODIFY | Add recovery workflow example; note that the tool now handles the standard `./` prefix automatically |

### Edge cases

| Case | Behavior |
|------|----------|
| Archive with both `./foo` AND `foo` members (unlikely but defensive) | First match wins; `getmembers()` order is deterministic |
| Empty quarantine prefix | `restore_from_quarantine` prints "No objects" and returns 0 |
| Some restore `mv` operations fail mid-run | Logged per-object, continues; user can re-run for leftovers |
| User passes `--restore-from-quarantine` AND `--delete`/`--quarantine` | Restore runs first and exits; normal audit does not run |
| Restored `.tmp.tar.gz` files | They get re-quarantined as `WRONG_NAME` in the next audit (name-based check doesn't depend on the prefix bug) |
| Tarball member is a directory entry (e.g., `.` or `./storage`) | `_read_json_member` skips it because `extractfile()` returns None on directories; `_count_dataset_files` requires `m.isfile()` |

### What stays unchanged

- All category definitions (OK / WRONG_NAME / CORRUPTED / MISSING_PAYLOAD / MISSING_MARKER / ROW_COUNT_MISMATCH / DUPLICATE / INSPECTION_FAILED)
- Report format
- `classify_by_name` (name-based WRONG_NAME detection was always correct)
- Duplicate detection
- SIGINT handling + incremental report writing
- Crawler-service archiving code (it was always producing valid archives; the bug was purely in the audit tool)

## Alternatives Considered

### A. Change how the crawler archives (drop the `./` prefix)
Use `shutil.make_archive(base_dir=domain)` or similar to avoid the prefix.

**Rejected:** risky change to production code to work around a bug in a one-shot audit tool; would invalidate all existing GCS archives (they have `./` prefixes already); and the prefix is Python's standard tar layout — fighting it means fragile code elsewhere.

### B. Try multiple candidate names in `getmember`
Call `getmember("./_callback_payload.json")` if `getmember("_callback_payload.json")` fails.

**Rejected:** enumerating candidates is fragile. The normalize-on-iterate approach handles any prefix convention cleanly. Iterating all members once is O(n) once instead of several point lookups that still might miss unusual layouts.

### C. Selective restore based on prior report's category
Read the prior report, only move objects flagged `MISSING_PAYLOAD` back.

**Rejected:** more complex (requires the prior report file to be present and well-formed), and adds little value. Moving everything back and letting the fixed audit re-classify is cheap — re-quarantining the ~24 real-bad ones is a handful of GCS operations. Simpler wins.

## Future Extensions

Not in scope for this fix, but noted:

1. **Backfill integrity check beyond payload existence** — after the fix, we may want to validate `_completion_marker.json.final_status == "finished"` (already done informally via existence) and compare `_callback_payload.json.stored_files_count` against a more authoritative count source.
2. **Report diff tooling** — compare two audit reports to show which archives changed category between runs.
3. **Test matrix against varying `shutil.make_archive` behavior across Python versions** — the `./` prefix convention appears stable across 3.x, but a CI test against multiple Python minor versions would protect against future changes.
