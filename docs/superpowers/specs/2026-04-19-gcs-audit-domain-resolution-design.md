# Design: GCS Audit Tool — Multi-Source Domain Resolution

**Date:** 2026-04-19
**Service:** `tools/gcs_archive_audit.py`
**Status:** Approved

## Problem

After fixing the `./`-prefix member lookup (spec `2026-04-19-gcs-audit-prefix-fix-design.md`), the audit STILL classifies the same ~80% of archives as `MISSING_PAYLOAD` on re-run. Root cause analysis revealed the real issue: the audit extracts `domain` from `_callback_payload.json` and fails when that field is absent — **but Node.js never writes a `domain` field to the payload at all**.

The Node.js crawler writes (see `crawler/src/main.ts:843-853`):

```typescript
const payload = {
    id_domaine: id,                    // crawl_id, NOT the domain hostname
    success: finalStats?.requestsFinished || 0,
    failed: finalStats?.requestsFailed || 0,
    isFinished: isFinished,
    method: method,
    isError: isError,
    storagePath: storagePath,
    message_erreur_crawling: messageErreurCrawling || null,
    robots_txt_bypassed: context.robotsTxtBypassed,
    camoufox_used: context.camoufoxEnabled,
};
```

No `domain` field. The `id_domaine` field is the numeric crawl identifier, not the hostname.

Similarly, `stored_files_count` is NOT in the disk payload. Python adds it in-memory at webhook-send time (in `_send_success_webhook`) and never persists it back to disk. The `success` field IS on disk and is the correct count source.

The audit tool's tests masked this problem by using a handcrafted payload shape (`{"domain": ..., "stored_files_count": ...}`) that doesn't match production.

## Decision

Replace the single-source domain lookup with a **multi-source resolver** that tries several places in order, and degrades gracefully when the domain cannot be resolved. Update test fixtures so `_payload()` produces the actual Node.js output shape.

## Design

### Domain resolution priority

A new helper `_resolve_domain_name(tar, members, payload)` tries these sources in order:

1. **`payload["domain"]`** — not currently written by Node.js, but future-proof; if a future code change adds it, the audit picks it up automatically.
2. **`_status_snapshot.json["domain"]`** — written by Python's `archive_crawl` before creating the archive. The `CrawlStatus` Pydantic model has `domain` as a required field, so when the snapshot exists, domain is present.
3. **Infer from tar member structure** — scan for `storage/datasets/{X}/` where `X` does NOT start with the special prefixes `nfr-`, `error-`, or `update-`. The first match is the main dataset directory and `X` is the domain name. Matches the crawler's convention: auxiliary datasets are prefixed with `nfr-`, `error-`, or `update-`, and the primary dataset folder bears the raw domain or its sanitized variant.

If all three fail, the helper returns `None` and the audit classifies the archive as `OK` with a `details["warning"]` explaining the row-count check was skipped.

### Updated `inspect_archive` flow

1. Open tar → on failure, `CORRUPTED`
2. Read all members → on failure, `CORRUPTED`
3. Read `_callback_payload.json` → if file absent, `MISSING_PAYLOAD`
4. Read `_completion_marker.json` → if file absent, `MISSING_MARKER`
5. Resolve domain via multi-source lookup
6. Extract expected count from payload: prefer `stored_files_count` (future-proof), fall back to `success`
7. **If domain unresolved OR count field missing:** classify `OK` with a `warning` detail; skip row-count check
8. **Otherwise:** count actual files under `storage/datasets/{domain}/` and compare — `ROW_COUNT_MISMATCH` if divergent, `OK` if matching

Key shift from previous behavior: `MISSING_PAYLOAD` is now reserved for cases where the payload **file** is absent. Having a payload file but no `domain` field is no longer a failure mode; it's an expected case.

### Updated `_payload()` test helper

The test helper is realigned with Node.js's disk output:

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

### Existing test updates

| Test | Change |
|------|--------|
| `test_ok_archive` | `_payload(domain="example.com", stored=3)` → `_payload(success=3)`; domain inferred from `storage/datasets/example.com/` in tar |
| `test_missing_marker` | `_payload(stored=3)` → `_payload(success=3)` |
| `test_row_count_mismatch` | `_payload(stored=5)` → `_payload(success=5)` — still tests mismatch |
| `test_sanitized_domain_fallback` | Original scenario obsolete (tar-inference finds `foo-com` directly). Replace with a test where `_status_snapshot.json` provides a different domain from tar inference to exercise the snapshot path |
| `test_success_field_fallback` | Renamed to `test_uses_success_field_from_realistic_payload`; it's no longer a fallback case, it's the normal case |
| `test_payload_missing_domain_field` | Expectation inverts: previously expected `MISSING_PAYLOAD`, now expects `OK` (domain inferred from tar). Rename to `test_ok_when_payload_lacks_domain_field` |

### New `TestDomainResolution` class

Five new tests, one per resolution path plus edge cases:

1. `test_uses_payload_domain_if_present` — payload has `domain: "x.com"`, tar has `storage/datasets/y.com/` → resolver returns `"x.com"` (payload wins).
2. `test_falls_back_to_status_snapshot_domain` — payload has no `domain`, snapshot has `domain: "x.com"` → resolver returns `"x.com"`.
3. `test_infers_from_tar_when_no_metadata_source` — neither payload nor snapshot has `domain`, tar has `storage/datasets/example.com/a.json` → resolver returns `"example.com"`.
4. `test_skips_special_prefix_dirs_during_inference` — tar has `storage/datasets/error-foo/`, `storage/datasets/nfr-bar/`, `storage/datasets/example.com/` → resolver returns `"example.com"` (skips special prefixes).
5. `test_returns_none_when_no_source_available` — no `domain` anywhere, tar has only special-prefix datasets → resolver returns `None` (and `inspect_archive` returns `OK` with a warning).

### Edge cases

| Case | Behavior |
|------|----------|
| Archive has only `nfr-X` and `error-X` datasets (update mode with 0 new successes) | Domain unresolvable → `OK` with warning |
| Archive has `storage/datasets/` prefix but no subdirs | Domain unresolvable → `OK` with warning |
| Payload has `success: 0` AND tar has no dataset files | `actual = 0`, `expected = 0` → `OK` |
| Payload has `success: 0` but tar has 3 dataset files | `ROW_COUNT_MISMATCH` — suspicious, flagged for review |
| Both `domain` source and `storage/datasets/` missing | Domain unresolvable → `OK` with warning |
| `_status_snapshot.json` present but has no `domain` field | Fall through to tar inference |
| Multiple non-special-prefix dataset directories | First match wins (deterministic via `getmembers()` order) |

### Files to modify

| File | Action |
|------|--------|
| `tools/gcs_archive_audit.py` | Add `_resolve_domain_name`; rewrite the domain-extraction + row-count part of `inspect_archive` to use resolver and degrade gracefully |
| `tools/tests/test_gcs_archive_audit.py` | Rewrite `_payload()` helper; update 6 existing tests; add `TestDomainResolution` with 5 new tests |

### What stays unchanged

- Category constants (`OK`, `WRONG_NAME`, `CORRUPTED`, `MISSING_PAYLOAD`, `MISSING_MARKER`, `ROW_COUNT_MISMATCH`, `DUPLICATE`, `INSPECTION_FAILED`)
- `_normalize_member_name`, `_count_dataset_files`, `classify_by_name` — unchanged
- CLI flags, argparse, report format, orchestration, `restore_from_quarantine`
- No changes to crawler-service archiving code (the `archive_crawl` path was always producing the expected on-disk layout)
- No changes to `tools/CLAUDE.md` (no new flags or user-visible behavior; only internal resolver logic changed)

### Expected effect on the user's audit

When they re-run after this fix + restore from quarantine:

- Most of the 93 previously-misclassified archives should now classify as **OK** (domain inferred from tar structure, payload fields read correctly)
- Some MAY surface as **ROW_COUNT_MISMATCH** if `success` count disagrees with the actual dataset-file count — that's a real integrity issue worth investigating case-by-case
- The 10 `WRONG_NAME` classifications are unchanged (name-based, bug-free)
- The 14 `CORRUPTED` classifications are unchanged (tar-open failure path, bug-free)

## Alternatives Considered

### A. Add a new `MALFORMED_PAYLOAD` category
Distinguish "file missing" from "file lacks expected fields" by splitting the category.

**Rejected:** the user-visible outcome is the same (archive is investigated), and the new category adds report complexity without actionable value. The `details["warning"]` field already conveys the nuance when needed.

### B. Look up `id_domaine` against Redis / external DB to resolve domain
Use the numeric `id_domaine` from the payload to query Redis for the real domain name.

**Rejected:** creates a runtime dependency on Redis for what should be a one-shot audit tool. The tar-structure inference is deterministic, offline, and reliable enough.

### C. Require Node.js to write the domain field
Change the crawler code to write `domain` into the payload going forward.

**Rejected for now:** useful long-term (and the design even keeps `payload["domain"]` as the first priority in the resolver) but doesn't fix the already-uploaded 93 archives. Also invasive change to a working production path. We can do this later if desired — the audit tool will automatically benefit via priority #1.

## Future Extensions

1. **Domain-write in crawler** — later, add `domain` to the Node.js payload so new archives have the field directly. Out of scope for this fix since priority #1 already reads it when present.
2. **Count cross-checks across sources** — if `success` in payload disagrees with `update_stats.json` counts, surface that separately.
3. **Historical backfill** — for archives flagged `OK with warning` (no resolvable domain), operators could manually annotate via a separate maintenance script. Not worth building speculatively.
