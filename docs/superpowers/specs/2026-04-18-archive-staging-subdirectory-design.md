# Design: Archive Staging Subdirectory (Fix for Tmp File Race)

**Date:** 2026-04-18
**Service:** crawler-service
**Status:** Approved

## Problem

Archiving a finished crawl via `POST /archive/{crawl_id}` intermittently fails with:

```
FileNotFoundError: [Errno 2] No such file or directory: '/app/archives/4365.tmp.tar.gz'
```

The error originates from `os.path.getsize(tmp_path)` at [crawler_manager.py:1478](apps-microservices/crawler-service/app/core/crawler_manager.py#L1478), immediately after `shutil.make_archive` at line 1477 successfully returned that path.

### Root Cause

The Python code creates a tmp file named `{crawl_id}.tmp.tar.gz` with the intent that the upload daemon ignore it. A code comment states:

> *daemon only watches `*.tar.gz`, not `*.tmp.tar.gz`*

This assumption is wrong. The daemon uses:

```bash
find "$ARCHIVES_DIR" -maxdepth 1 -name "*.tar.gz" -print0
```

The glob `*.tar.gz` matches any filename ending in `.tar.gz` — **including** `4365.tmp.tar.gz`. So the daemon:

1. Finds the tmp file before the Python code renames it
2. Uploads it to GCS (possibly partial)
3. Deletes the local file (`rm "$file"` at [upload_daemon.sh:55](tools/upload_daemon.sh#L55))
4. Python's `os.path.getsize(tmp_path)` fails with `FileNotFoundError`

Timing matches the observed 60-66 second gap between archive start and error (daemon polls every 60s).

## Decision

Move tmp files into a **hidden staging subdirectory** (`/app/archives/.staging/`) during creation. The daemon already uses `find -maxdepth 1`, so it never descends into subdirectories. After the archive is verified, atomically rename into `/app/archives/` for the daemon to pick up.

This is a **Python-only change**. The upload daemon is not modified.

## Design

### Directory Layout

```
/app/archives/
├── .staging/              ← tmp files (hidden from daemon, maxdepth 1)
│   └── 4365.tar.gz       ← being written by shutil.make_archive
├── 4365.tar.gz            ← completed, daemon will upload
└── 4683.tar.gz            ← completed, daemon will upload
```

### Code Changes

**File:** `apps-microservices/crawler-service/app/core/crawler_manager.py`

Replace the `_create_archive` inner function (lines 1468-1494) with:

```python
def _create_archive():
    """Create tar.gz archive in a staging subdirectory, then atomically move
    to the final location. The daemon uses maxdepth 1, so it never sees the
    staging dir — preventing the race where the daemon uploads a partial file."""
    staging_dir = os.path.join(archives_dir, ".staging")
    os.makedirs(staging_dir, exist_ok=True)
    os.makedirs(archives_dir, exist_ok=True)
    
    staging_base = os.path.join(staging_dir, crawl_id)
    final_target = os.path.join(archives_dir, f"{crawl_id}.tar.gz")
    staging_path = None
    
    try:
        # Create archive in staging dir (hidden from daemon)
        staging_path = shutil.make_archive(staging_base, 'gztar', root_dir=job_storage_path)
        archive_size = os.path.getsize(staging_path)
        if archive_size == 0:
            raise RuntimeError(f"Archive at '{staging_path}' is empty (0 bytes).")
        
        # Verify archive is readable
        with tarfile.open(staging_path, 'r:gz') as t:
            t.getnames()  # Force read of the archive index
        
        # Atomic rename to final path — same filesystem, always atomic
        os.rename(staging_path, final_target)
        staging_path = None  # Successfully moved; skip cleanup
        
        return final_target, archive_size
    finally:
        # Clean up staging file on any failure (disk full, corrupt, 0 bytes, etc.)
        if staging_path and os.path.exists(staging_path):
            try:
                os.remove(staging_path)
            except OSError:
                pass
```

### Key Differences from Current Code

| Aspect | Current | New |
|--------|---------|-----|
| Tmp location | `/app/archives/{id}.tmp.tar.gz` | `/app/archives/.staging/{id}.tar.gz` |
| Daemon sees tmp? | **Yes** (`*.tar.gz` glob matches `*.tmp.tar.gz`) | **No** (daemon uses `maxdepth 1`, ignores subdirs) |
| Cleanup on error | Manual `os.remove` in 2 places | Single `finally` block covers all failure modes |
| Atomic move | `os.rename` (already atomic) | `os.rename` (unchanged, same filesystem) |

### Edge Cases

| Case | Behavior |
|------|----------|
| `.staging` dir missing | `os.makedirs(exist_ok=True)` creates it |
| Stale file from previous crash | `shutil.make_archive` overwrites on next attempt |
| Disk full during `make_archive` | `finally` block removes the partial file (prevents accumulation) |
| Crash between `make_archive` and `os.rename` | Next call overwrites the staging file; no impact |
| Concurrent archive of same crawl_id | Already prevented by Redis `archive_lock:{crawl_id}` |
| Daemon upgrade to scan subdirs in future | Would break this fix — daemon contract is explicit in shared `/app/archives` documentation |

### What Stays Unchanged

- Upload daemon (`tools/upload_daemon.sh`) — zero changes
- Redis lock logic (`archive_lock:{crawl_id}`) — unchanged
- Idempotency check (existing `/app/archives/{id}.tar.gz` → skip re-generation) — unchanged
- GCS fallback (`_retrieve_from_gcs_daemon` for legacy crawls) — unchanged
- `_cleanup_local_data` (deletes files from `/app/storage/{id}/`) — unchanged
- `_mark_as_archived` — unchanged
- API response payload structure — unchanged

### What's NOT in This Design

Deferred to a separate brainstorming session:

- **Disk space management** (Error 2: `No space left on device`)
- Pre-flight disk space checks before archiving
- Back-pressure on concurrent archives across replicas
- Archive retention/rotation policy for the shared volume

## Alternatives Considered

### B: Rename daemon glob to exclude tmp files
Change `find -name "*.tar.gz"` to `find -name "*.tar.gz" ! -name "*.tmp.tar.gz"`, keep tmp files in `/app/archives/`.

**Rejected:** requires two coordinated changes (Python + bash). If either drifts, bugs resurface. The convention is subtle — future readers might break it unknowingly.

### C: Different tmp directory entirely (`/tmp/{id}.tar.gz`)
Write to `/tmp/`, then move to `/app/archives/`.

**Rejected:** `/tmp` may be a different mount than `/app/archives`. Cross-filesystem `os.rename` fails with `EXDEV` and falls back to copy-then-delete, losing atomicity and doubling I/O. Staging on the same volume is cleaner.
