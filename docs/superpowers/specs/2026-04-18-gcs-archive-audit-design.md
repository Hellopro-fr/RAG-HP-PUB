# Design: GCS Archive Audit Tool

**Date:** 2026-04-18
**Service:** `tools/` (operational scripts for the RAG-HP-PUB monorepo)
**Status:** Approved

## Problem

Before the `.staging/` subdirectory fix (2026-04-18, spec `2026-04-18-archive-staging-subdirectory-design.md`), the upload daemon's glob `find ... -name "*.tar.gz"` matched the partially-written tmp files produced by `shutil.make_archive`. The daemon uploaded those partials to GCS before the crawler-service could rename them to their final name. Result: the bucket `gs://{bucket}/crawls/` may contain:

- **Wrongly-named files** (`{id}.tmp.tar.gz`) — partial uploads that never got renamed to `{id}.tar.gz`
- **Corrupted `.tar.gz` files** — partial uploads that happen to have ended with `.tar.gz` because the daemon raced the whole pipeline
- **Incomplete archives** — lacking `_callback_payload.json` or `_completion_marker.json` because the daemon grabbed them before Python finished writing those metadata files
- **Row-count mismatched archives** — `_callback_payload.json` declares N URLs but the dataset directory contains != N files (usually fewer, because the payload was written first and the upload preempted the dataset flush)

Currently there is no tooling to identify or remediate these bad archives.

## Decision

Build a one-shot Python CLI `tools/gcs_archive_audit.py` that enumerates every archive in `gs://{bucket}/crawls/`, classifies each into one of `{OK, WRONG_NAME, CORRUPTED, MISSING_PAYLOAD, MISSING_MARKER, ROW_COUNT_MISMATCH, DUPLICATE, INSPECTION_FAILED}`, writes a JSON report, and optionally remediates via `--delete` or `--quarantine`.

The tool shells out to `gcloud storage` — matching the existing pattern used by `upload_daemon.sh` / `download_daemon.sh` — rather than pulling in the `google-cloud-storage` Python library. No new PyPI dependencies.

## Design

### CLI Surface

```
python tools/gcs_archive_audit.py \
    --bucket <name> \
    [--prefix crawls/] \
    [--output report.json] \
    [--name-only]               # fast mode: skip downloads, only check names
    [--limit N]                 # cap number of archives processed (useful for testing)
    [--delete]                  # delete bad archives (mutually exclusive with --quarantine)
    [--quarantine <prefix>]     # move bad archives to gs://bucket/<prefix>/ (mutually exclusive with --delete)
    [--yes]                     # skip confirmation prompt for --delete / --quarantine
    [--resume <report.json>]    # skip archives already listed in the given report
```

**Default is dry-run:** no flags beyond `--bucket` means "list and inspect, produce report, touch nothing."

### Flow

```
1. Confirm `gcloud` CLI is on PATH and authenticated
2. List objects under gs://{bucket}/{prefix}/ via `gcloud storage ls -l ...`
3. For each object:
     a. Name-based classification: if ends with `.tmp.tar.gz` → WRONG_NAME
     b. If --name-only: record category, skip download
     c. Otherwise download to temp file via `gcloud storage cp`
     d. Inspect via `tarfile` module:
        - Try to open → fail: CORRUPTED
        - Read _callback_payload.json → missing: MISSING_PAYLOAD
        - Read _completion_marker.json → missing: MISSING_MARKER
        - Count *.json files in storage/datasets/{domain}/ (or storage/datasets/{sanitized_domain}/)
        - Compare count to _callback_payload.json:stored_files_count → mismatch: ROW_COUNT_MISMATCH
        - All checks pass → OK
        - Delete temp file
     e. If category != OK and --delete or --quarantine is set, remediate
4. Detect duplicates: same crawl_id appearing in multiple object names → mark both DUPLICATE
5. Write report JSON (incremental flush every 50 objects)
6. Print summary table
```

### Row-Count Check (Option A)

Only files under `storage/datasets/{domain}/` (not the `nfr-` or `error-` variants) are counted — this matches the `_callback_payload.json:stored_files_count` which refers to successful-only URLs.

Fallback: if `storage/datasets/{domain}/` is not in the tar, try `storage/datasets/{sanitized_domain}/` (where `sanitized_domain = domain.replace('.', '-')`), matching the crawler-service's fallback in `_send_success_webhook`.

If `stored_files_count` is not in `_callback_payload.json` (some older payloads only have `success`), fall back to `success`.

### Duplicate Detection

After all objects are enumerated, group by extracted `crawl_id`:
- `crawls/4365.tar.gz` → crawl_id = `4365`
- `crawls/4365.tmp.tar.gz` → crawl_id = `4365`

If any `crawl_id` has more than one object, each of those objects gets `DUPLICATE` appended as a secondary tag (the primary category — e.g., `WRONG_NAME` — is preserved). The human reviewing the report decides which copy to keep.

### Report Format

```json
{
  "bucket": "hp-crawler-archives",
  "prefix": "crawls/",
  "audited_at": "2026-04-18T14:30:00Z",
  "total_objects": 1842,
  "categories": {
    "OK": 1523,
    "WRONG_NAME": 187,
    "CORRUPTED": 42,
    "MISSING_PAYLOAD": 58,
    "MISSING_MARKER": 12,
    "ROW_COUNT_MISMATCH": 15,
    "DUPLICATE": 5,
    "INSPECTION_FAILED": 0
  },
  "archives": [
    {
      "object_name": "crawls/4365.tmp.tar.gz",
      "crawl_id": "4365",
      "size_bytes": 12582912,
      "category": "WRONG_NAME",
      "secondary_tags": [],
      "actions_taken": ["quarantined to crawls-quarantine/4365.tmp.tar.gz"]
    },
    {
      "object_name": "crawls/4683.tar.gz",
      "crawl_id": "4683",
      "size_bytes": 524288000,
      "category": "ROW_COUNT_MISMATCH",
      "secondary_tags": [],
      "expected_count": 1834,
      "actual_count": 1821,
      "actions_taken": []
    }
  ]
}
```

A plain-text summary is also printed to stdout:

```
=== GCS Archive Audit ===
Bucket: hp-crawler-archives
Prefix: crawls/
Audited: 1842 archives (1520s)

Categories:
  OK                      1523  (82.7%)
  WRONG_NAME               187  (10.1%)
  CORRUPTED                 42   (2.3%)
  MISSING_PAYLOAD           58   (3.1%)
  MISSING_MARKER            12   (0.7%)
  ROW_COUNT_MISMATCH        15   (0.8%)
  DUPLICATE                  5   (0.3%)

Actions taken: none (dry-run)
Full report written to: report.json
```

### Architecture

Single module: `tools/gcs_archive_audit.py`. Organized into small pure-ish functions:

| Function | Responsibility |
|----------|----------------|
| `gcloud_ls(uri, long=False)` | Shell out to `gcloud storage ls`, return list of object URIs (or `(size, uri)` tuples if `long=True`) |
| `gcloud_download(obj_uri, local_path)` | Shell out to `gcloud storage cp` |
| `gcloud_delete(obj_uri)` | Shell out to `gcloud storage rm` |
| `gcloud_move(src_uri, dst_uri)` | Shell out to `gcloud storage mv` |
| `extract_crawl_id(object_name)` | Given `crawls/4365.tar.gz` or `crawls/4365.tmp.tar.gz`, return `"4365"` |
| `classify_by_name(object_name)` | `WRONG_NAME` if `.tmp.tar.gz`, else `None` |
| `inspect_archive(local_tar_path)` | Returns `(category, details_dict)`. Opens the tar, reads `_callback_payload.json` / `_completion_marker.json`, counts dataset files, compares row counts |
| `detect_duplicates(results)` | Second pass after all archives inspected; adds `DUPLICATE` tag |
| `remediate(obj_uri, category, action, quarantine_prefix)` | Performs `gcloud rm` or `gcloud mv` depending on action |
| `main()` | Argparse, wires it together, writes incremental report |

### Authentication & Prerequisites

- `gcloud` CLI installed and on `PATH`
- Authenticated via either:
  - `gcloud auth login` (user credentials), or
  - `gcloud auth activate-service-account --key-file=...` (service account)
- The authenticated principal must have `storage.objects.list`, `storage.objects.get`, `storage.objects.delete` (for `--delete`), and `storage.objects.create` (for `--quarantine`)

The tool checks `gcloud auth list --filter=status:ACTIVE` at startup. If no active account, it prints a clear error referencing these commands.

### Edge Cases

| Case | Behavior |
|------|----------|
| Bucket with 10,000+ objects | Streams one object at a time; writes partial report every 50 objects so a crash leaves usable data |
| Archive is 10 GB | Downloaded to `tempfile.NamedTemporaryFile`; inspected; explicitly deleted before moving to the next |
| Network failure during download | Caught; archive marked `INSPECTION_FAILED` in report; tool continues |
| `gcloud` command fails (non-zero exit) | Captured as `INSPECTION_FAILED` with stderr in details |
| User presses Ctrl+C | Signal handler writes the current partial report before exiting |
| `--resume <report.json>` | Read the prior report, build a set of already-audited `object_name`s, skip those during listing |
| `--delete` and `--quarantine` both passed | argparse error, tool exits before any work |
| Archive has multiple `storage/datasets/*` subdirs (main + nfr + error) | Only main `{domain}/` or `{sanitized_domain}/` counted for row check. Others recorded informationally under `extra_counts` for visibility. |
| `_callback_payload.json` has `success` but not `stored_files_count` (older payload schema) | Fall back to `success` for the expected count |
| `crawl_id` can't be parsed from object name (unexpected naming) | Use object name as-is for duplicate detection; record parse warning in report |
| Disk full during download | Caught; `INSPECTION_FAILED` for that archive; tool continues with next |

### Files

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/gcs_archive_audit.py` | CREATE | The audit CLI + all helpers |
| `tools/CLAUDE.md` | MODIFY | Add this tool to the File Inventory and Run sections |

No changes to `tools/requirements.txt` — the tool uses only Python stdlib (`argparse`, `json`, `subprocess`, `tarfile`, `tempfile`, `signal`, `datetime`, `pathlib`).

### What's NOT in this design

- **No re-archiving from local disk.** By now, most crawls' source data in `/app/storage/{id}/` has been cleaned up. A "regenerate a clean archive" mode would need extensive cross-checks we're not attempting here.
- **No integration with Redis / crawler-service state.** The tool treats the GCS bucket as a standalone truth source. Cross-referencing which crawls are still "archived" status in Redis is a separate concern.
- **No automatic dedup of duplicate objects.** The report flags them; the human reviewing the report decides which copy to keep. Automating that decision requires judgement about which is "better" (larger? more complete? newer?).
- **No scheduled/recurring run.** One-shot tool, invoked manually when needed.
- **No streaming / partial inspection.** Gzip doesn't support random access; we must download the full archive. Accepted cost.

## Alternatives Considered

### Using the `google-cloud-storage` Python library
Rejected because the user's environment only has `gcloud` CLI access, not Python GCS credentials. Shelling out to `gcloud` adds subprocess overhead but avoids auth-management complexity and new dependencies.

### Bash-only implementation
Rejected because tar.gz inspection, JSON parsing, row-counting across tar members, and structured report generation are painful in bash. Python is the right tool for the inspection logic; bash is fine for the thin subprocess wrappers we call inside Python.

### Metadata-only audit (no download)
Rejected because the row-count check and payload-presence check require reading the tar contents. A metadata-only audit catches only the `WRONG_NAME` case — useful as a fast first pass, but incomplete on its own. Exposed as `--name-only` for users who want just the quick scan.

### Re-archiving from local disk (Option D from earlier brainstorm)
Deferred. Would require `/app/storage/{id}/` to still exist locally, which is rare after post-archive cleanup. Could be added as a follow-up tool if needed.

## Future Extensions

1. **Scheduled audit job** — periodic re-audit (monthly?) to catch any new corruption; emit metrics.
2. **Automatic dedup policy** — heuristic-driven "keep largest / most-recent / most-complete" when duplicates are found.
3. **Cross-reference with Redis** — if a crawl's object is bad AND the crawl is still in Redis with `status: "archived"`, revert status to `finished` so operators can re-archive.
4. **Progress bar** — `tqdm`-style progress during large-bucket runs (stdlib only — tracking count and elapsed time is enough).
