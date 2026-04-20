# GCS Audit Multi-Source Domain Resolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the audit's domain-extraction bug by introducing a multi-source `_resolve_domain_name` helper that tries payload, `_status_snapshot.json`, and tar-structure inference in order — and gracefully classifies archives as `OK` (with a warning detail) when domain can't be resolved. Also realign test fixtures to match the actual Node.js payload shape.

**Architecture:** One surgical edit to `tools/gcs_archive_audit.py` (add `_resolve_domain_name`, restructure the domain+count logic in `inspect_archive`) + tightly-coupled rewrite of the `_payload()` test helper and its dependent tests. Implementation + test updates land atomically in one commit to avoid intermediate broken states.

**Tech Stack:** Python stdlib (`tarfile`, `json`), pytest.

**Spec:** `docs/superpowers/specs/2026-04-19-gcs-audit-domain-resolution-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/gcs_archive_audit.py` | MODIFY | Add `_resolve_domain_name` helper; rewrite domain+count section of `inspect_archive` |
| `tools/tests/test_gcs_archive_audit.py` | MODIFY | Rewrite `_payload()` helper; adjust 6 existing `TestArchiveInspection` + `TestPathNormalization` tests; add `TestDomainResolution` class with 5 new tests |

No CLAUDE.md changes (no new flags or user-visible behavior).

---

### Task 1: Domain resolution + aligned test fixtures (atomic)

**Goal:** Replace the failing `domain`-extraction with multi-source resolution AND update tests to use the realistic Node.js payload shape. Done atomically so no intermediate broken state exists.

**Files:**
- Modify: `tools/gcs_archive_audit.py` (add `_resolve_domain_name`; replace the domain+count block inside `inspect_archive`)
- Modify: `tools/tests/test_gcs_archive_audit.py` (rewrite `_payload`, update affected tests, add `TestDomainResolution`)

**Acceptance Criteria:**
- [ ] `_resolve_domain_name(tar, members, payload)` exists and returns the domain via priority: payload → `_status_snapshot.json` → tar-structure inference → `None`
- [ ] `inspect_archive` classifies a Node.js-shaped payload (no `domain` field, has `success`) as `OK` when the tar has dataset files under a recognizable prefix
- [ ] `inspect_archive` returns `OK` with `details["warning"]` when domain cannot be resolved (not `MISSING_PAYLOAD`)
- [ ] `inspect_archive` still returns `ROW_COUNT_MISMATCH` when expected and actual counts disagree
- [ ] `_payload()` helper emits the actual Node.js payload shape (has `id_domaine`, `success`; lacks `domain`, `stored_files_count`)
- [ ] Full test suite passes (existing + 5 new `TestDomainResolution` tests)

**Verify:** `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v`

**Steps:**

- [ ] **Step 1: Add `_resolve_domain_name` to `tools/gcs_archive_audit.py`**

Open `tools/gcs_archive_audit.py`. Find the existing `_count_dataset_files` function (around line 262). Insert the new helper **immediately AFTER** `_count_dataset_files` (before the next section heading):

**Find (this is the last line of `_count_dataset_files`):**

```python
        if found_dir:
            return count
    return 0
```

**Replace with:**

```python
        if found_dir:
            return count
    return 0


def _resolve_domain_name(
    tar: tarfile.TarFile,
    members: List[tarfile.TarInfo],
    payload: Dict,
) -> Optional[str]:
    """Resolve the crawl's domain name from multiple possible sources.

    Priority:
    1. payload['domain'] — not currently written by Node.js but future-proof
    2. _status_snapshot.json['domain'] — written by Python's archive_crawl
       (CrawlStatus model has domain as a required field)
    3. Inferred from tar structure: first 'storage/datasets/{X}/' where X does
       NOT start with a known special prefix (nfr-, error-, update-)

    Returns the domain name as a string, or None if all sources fail.
    """
    # 1. Try payload
    domain = payload.get("domain")
    if domain:
        return domain

    # 2. Try status snapshot (Python writes this before archiving)
    snapshot = _read_json_member(tar, "_status_snapshot.json")
    if snapshot:
        domain = snapshot.get("domain")
        if domain:
            return domain

    # 3. Infer from tar structure
    special_prefixes = ("nfr-", "error-", "update-")
    seen_candidates: set = set()
    for m in members:
        normalized = _normalize_member_name(m.name)
        if normalized.startswith("storage/datasets/"):
            parts = normalized.split("/", 3)  # ['storage', 'datasets', 'X', ...]
            if len(parts) >= 3 and parts[2]:
                candidate = parts[2]
                if candidate in seen_candidates:
                    continue
                seen_candidates.add(candidate)
                if not any(candidate.startswith(p) for p in special_prefixes):
                    return candidate

    return None
```

- [ ] **Step 2: Replace the domain+count block in `inspect_archive`**

In the same file, find the existing `inspect_archive` function (around line 158). The domain-extraction block currently looks like this (inside the `try:` after `details["marker"] = marker`):

**Find:**

```python
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
```

**Replace with:**

```python
        # 4. Resolve domain via multi-source lookup (payload, snapshot, tar inference).
        domain = _resolve_domain_name(tar, members, payload)

        # 5. Get expected count. Node.js writes 'success' (the successful URL count);
        #    'stored_files_count' is added by Python in-memory at webhook-send time
        #    and NOT persisted to disk, so this is a future-proofing fallback only.
        expected = payload.get("stored_files_count")
        if expected is None:
            expected = payload.get("success")

        # 6. Row count check — best-effort. Skip (with warning) if we lack either input.
        if domain is None:
            details["warning"] = "domain could not be resolved; row count check skipped"
            if expected is not None:
                details["expected_count"] = int(expected)
            return OK, details

        if expected is None:
            details["warning"] = "payload has no count field (stored_files_count/success); row count check skipped"
            details["domain"] = domain
            return OK, details

        actual = _count_dataset_files(members, domain)
        details["domain"] = domain
        details["expected_count"] = int(expected)
        details["actual_count"] = actual

        if int(expected) != actual:
            return ROW_COUNT_MISMATCH, details

        return OK, details
```

- [ ] **Step 3: Rewrite `_payload()` helper in `tools/tests/test_gcs_archive_audit.py`**

Find the existing helper (around line 138):

**Find:**

```python
def _payload(domain: str = "example.com", stored: int = 3, success=None) -> bytes:
    data = {"domain": domain, "stored_files_count": stored}
    if success is not None:
        data["success"] = success
    return _json.dumps(data).encode()
```

**Replace with:**

```python
def _payload(success: int = 3, id_domaine: str = "4365") -> bytes:
    """Build a _callback_payload.json matching what Node.js actually writes.

    Key details:
    - Contains 'id_domaine' (the crawl_id), NOT 'domain' (hostname).
    - Contains 'success' (URL count), NOT 'stored_files_count'.
    - 'stored_files_count' is added by Python in-memory at webhook-send time
      and is NEVER persisted to disk.
    """
    return _json.dumps({
        "id_domaine": id_domaine,
        "success": success,
        "failed": 0,
        "isFinished": 1,
        "method": "auto",
        "isError": "",
        "storagePath": f"/app/storage/{id_domaine}",
        "message_erreur_crawling": None,
    }).encode()
```

- [ ] **Step 4: Add a `_snapshot()` helper (for tests that use `_status_snapshot.json`)**

Immediately after the `_marker()` helper in the same file, add:

**Find:**

```python
def _marker() -> bytes:
    return _json.dumps({"final_status": "finished", "exit_code": 0}).encode()
```

**Replace with:**

```python
def _marker() -> bytes:
    return _json.dumps({"final_status": "finished", "exit_code": 0}).encode()


def _snapshot(domain: str = "example.com") -> bytes:
    """Build a _status_snapshot.json that Python's archive_crawl writes.
    The CrawlStatus model (app/schemas/crawler.py) has `domain` as a required field."""
    return _json.dumps({
        "crawl_id": "4365",
        "status": "finished",
        "domain": domain,
        "start_url": f"https://{domain}/",
        "urls_crawled": 0,
    }).encode()
```

- [ ] **Step 5: Update existing `TestArchiveInspection` test callsites**

In the same test file, find and update each callsite.

**Find (`test_ok_archive`):**

```python
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
```

**Replace with:**

```python
    def _ok_tar(self, tmp_path: Path) -> Path:
        """Build a tar with payload, marker, and 3 dataset files — success count 3 matches 3 files."""
        return _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=3),
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
```

**Find (`test_missing_marker`):**

```python
    def test_missing_marker(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(stored=3),
            # no _completion_marker.json
            "storage/datasets/example.com/x.json": b'{}',
        })
```

**Replace with:**

```python
    def test_missing_marker(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=3),
            # no _completion_marker.json
            "storage/datasets/example.com/x.json": b'{}',
        })
```

**Find (`test_row_count_mismatch`):**

```python
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
```

**Replace with:**

```python
    def test_row_count_mismatch(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=5),  # claims 5
            "_completion_marker.json": _marker(),
            # but only 2 dataset files
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.ROW_COUNT_MISMATCH
        assert details["expected_count"] == 5
        assert details["actual_count"] == 2
```

**Find (`test_sanitized_domain_fallback` — obsolete scenario; replace with snapshot-path test):**

```python
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
```

**Replace with:**

```python
    def test_uses_status_snapshot_domain_when_payload_lacks_it(self, tmp_path):
        """When payload has no 'domain' but _status_snapshot.json does, the snapshot
        provides the domain for row counting. This exercises the second resolver
        priority (after payload, before tar inference)."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "_status_snapshot.json": _snapshot(domain="foo.com"),
            # Tar has sanitized dir name; snapshot resolves the real domain 'foo.com',
            # which _count_dataset_files matches via its sanitized fallback.
            "storage/datasets/foo-com/only.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["domain"] == "foo.com"
        assert details["actual_count"] == 1
```

**Find (`test_success_field_fallback`):**

```python
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
```

**Replace with:**

```python
    def test_uses_success_field_from_realistic_payload(self, tmp_path):
        """The Node.js payload has 'success' (not 'stored_files_count'). The audit
        must pick up the count from 'success' and classify as OK when the count matches."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=2),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["expected_count"] == 2
```

**Find (`test_payload_missing_domain_field` — expectation inverts):**

```python
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

**Replace with:**

```python
    def test_ok_when_payload_lacks_domain_field(self, tmp_path):
        """The Node.js payload doesn't have a 'domain' field — that's normal, not a failure.
        When the tar contains dataset files, the resolver infers the domain from tar structure
        and the audit classifies as OK."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),  # no 'domain' field — realistic
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["domain"] == "example.com"
        assert details["actual_count"] == 1
```

- [ ] **Step 6: Update `TestPathNormalization` callsites (they currently use `_payload(domain=..., stored=...)`)**

**Find (`test_fixture_actually_produces_dot_slash_prefix`):**

```python
    def test_fixture_actually_produces_dot_slash_prefix(self, tmp_path):
        """Sanity-check the _build_tar helper matches the real crawler layout."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=1),
        })
```

**Replace with:**

```python
    def test_fixture_actually_produces_dot_slash_prefix(self, tmp_path):
        """Sanity-check the _build_tar helper matches the real crawler layout."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
        })
```

**Find (`test_payload_found_despite_leading_dot_slash`):**

```python
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
```

**Replace with:**

```python
    def test_payload_found_despite_leading_dot_slash(self, tmp_path):
        """The audit must classify a well-formed archive as OK even though
        its members have the './' prefix from shutil.make_archive."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["actual_count"] == 1
```

- [ ] **Step 7: Add `TestDomainResolution` class to the end of `tools/tests/test_gcs_archive_audit.py`**

Append at the end of the file (after the last existing test class):

```python


class TestDomainResolution:
    """Tests for the multi-source _resolve_domain_name helper.
    Priority: payload.domain > _status_snapshot.json.domain > tar inference."""

    def _open_tar(self, path: Path):
        return _tarfile.open(str(path), 'r:gz')

    def test_uses_payload_domain_if_present(self, tmp_path):
        """Priority 1: if payload has 'domain', use it even if the tar layout
        suggests a different domain."""
        payload_bytes = _json.dumps({"id_domaine": "4365", "domain": "x.com", "success": 1}).encode()
        path = _build_tar(tmp_path, {
            "_callback_payload.json": payload_bytes,
            "_completion_marker.json": _marker(),
            # Tar has y.com but payload says x.com — payload wins
            "storage/datasets/y.com/a.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "x.com"

    def test_falls_back_to_status_snapshot_domain(self, tmp_path):
        """Priority 2: when payload lacks 'domain', read it from _status_snapshot.json."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "_status_snapshot.json": _snapshot(domain="x.com"),
            # No dataset dir to infer from — resolver must use the snapshot
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "x.com"

    def test_infers_from_tar_when_no_metadata_source(self, tmp_path):
        """Priority 3: neither payload nor snapshot has domain — infer from tar."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            # No snapshot; tar has a dataset dir
            "storage/datasets/example.com/a.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "example.com"

    def test_skips_special_prefix_dirs_during_inference(self, tmp_path):
        """When tar has nfr-/error-/update- dirs AND a main domain dir,
        the resolver must skip the special-prefix ones and pick the main domain."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "storage/datasets/error-foo.com/e.json": b'{}',
            "storage/datasets/nfr-bar.com/n.json": b'{}',
            "storage/datasets/update-baz.com/u.json": b'{}',
            "storage/datasets/example.com/a.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "example.com"

    def test_returns_none_when_no_source_available(self, tmp_path):
        """Edge case: no payload.domain, no snapshot, only special-prefix dataset dirs.
        Resolver returns None; inspect_archive classifies as OK with a warning."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=0),
            "_completion_marker.json": _marker(),
            # Only special-prefix dataset dirs — resolver can't infer a main domain
            "storage/datasets/error-foo.com/e.json": b'{}',
            "storage/datasets/nfr-bar.com/n.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result is None

        # And inspect_archive must classify this as OK with a warning (not MISSING_PAYLOAD)
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert "warning" in details
        assert "domain could not be resolved" in details["warning"]
```

- [ ] **Step 8: Run full test suite and confirm everything passes**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && pytest tools/tests/test_gcs_archive_audit.py -v
```

Expected: all tests PASS (pre-existing updated + 5 new `TestDomainResolution` = ~46 tests total; exact number depends on count of pre-existing tests, but all should be green).

- [ ] **Step 9: Verify the fix against a realistic payload (optional quick check)**

Sanity-check via ad-hoc Python:

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && python3 -c "
import json, shutil, tempfile, os
from pathlib import Path
import sys
sys.path.insert(0, 'tools')
import gcs_archive_audit as ga

nodejs_payload = {
    'id_domaine': '4365', 'success': 1, 'failed': 0,
    'isFinished': 1, 'storagePath': '/app/storage/4365',
}
with tempfile.TemporaryDirectory() as job_path:
    job_path = Path(job_path)
    (job_path / '_callback_payload.json').write_text(json.dumps(nodejs_payload))
    (job_path / '_completion_marker.json').write_text(json.dumps({'final_status': 'finished'}))
    (job_path / 'storage' / 'datasets' / 'duba-container.com').mkdir(parents=True)
    (job_path / 'storage' / 'datasets' / 'duba-container.com' / 'url1.json').write_text('{}')
    with tempfile.TemporaryDirectory() as archives_dir:
        staging_base = os.path.join(archives_dir, 'real_test')
        archive_path = shutil.make_archive(staging_base, 'gztar', root_dir=str(job_path))
        category, details = ga.inspect_archive(Path(archive_path))
        print(f'Category: {category}')
        print(f'Domain: {details.get(\"domain\")}')
        print(f'Expected: {details.get(\"expected_count\")}, Actual: {details.get(\"actual_count\")}')
"
```

Expected output:
```
Category: OK
Domain: duba-container.com
Expected: 1, Actual: 1
```

- [ ] **Step 10: Commit (English only — do not ask)**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "fix(tools): resolve domain from multiple sources in gcs audit"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| `_resolve_domain_name(tar, members, payload)` with 3-source priority | Task 1 (Step 1) |
| Priority order: payload.domain → _status_snapshot.json.domain → tar inference | Task 1 (Step 1) + tests in Step 7 |
| Skip special prefixes (nfr-, error-, update-) in tar inference | Task 1 (Step 1) + test in Step 7 |
| Return None when all sources fail | Task 1 (Step 1) + test in Step 7 |
| `inspect_archive` returns OK+warning when domain unresolved | Task 1 (Step 2) + test in Step 7 |
| `inspect_archive` returns OK+warning when count field missing | Task 1 (Step 2) |
| MISSING_PAYLOAD reserved for missing payload FILE only (not missing field) | Task 1 (Step 2) — removed the "missing domain" MISSING_PAYLOAD path |
| `_payload()` matches Node.js disk output (`id_domaine`, `success`; no `domain`, no `stored_files_count`) | Task 1 (Step 3) |
| Existing tests updated: `test_ok_archive`, `test_missing_marker`, `test_row_count_mismatch`, `test_sanitized_domain_fallback` replaced, `test_success_field_fallback` renamed, `test_payload_missing_domain_field` expectation flipped | Task 1 (Steps 5-6) |
| `TestDomainResolution` class with 5 tests (one per resolution path + edge case) | Task 1 (Step 7) |
| No CLI, category, or report format changes | Confirmed — none touched |
| No crawler-service archiving code changes | Confirmed — only tools/ files touched |
