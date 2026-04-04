# crawler-service

Scalable web crawling service with FastAPI orchestrator and Node.js/Crawlee crawler engine.

## Tech Stack

- **Orchestrator:** Python 3.x, FastAPI, Uvicorn
- **Crawler Engine:** Node.js 22, TypeScript, Crawlee 3, Playwright 1.56.1
- **Browser:** Playwright (Chromium) + Camoufox (Firefox) for stealth
- **State:** Redis (job tracking, heartbeats, counters)
- **Shared lib:** `common-utils` (Python)

## Commands

### Python (orchestrator)
| Action | Command |
|--------|---------|
| Run | `uvicorn main:app --host 0.0.0.0 --port 8503` |
| Deps | `pip install -r requirements.txt` |

### Crawler (`crawler/`)
| Action | Command |
|--------|---------|
| Build | `npm run build` (tsc) |
| Dev | `npm run dev` (tsx) |
| Start | `npm run start` (node dist/main.js) |

## Docker

Multi-stage build (Node.js 22 + Playwright). Port **8503**. `NODE_OPTIONS="--max-old-space-size=5000 --expose-gc"`.

## Folder Structure

```
main.py                  # FastAPI app, startup/shutdown, background tasks
app/
  router/
    crawler.py           # Crawler REST endpoints
    migration.py         # Temporary migration routes
  core/
    config.py            # Settings (env vars)
    crawler_manager.py   # Job lifecycle management
  schemas/
    crawler.py           # Pydantic request/response models
    migration.py
crawler/
  src/
    main.ts              # Crawlee entry point
    routes.ts            # Playwright route handlers
    functions.ts         # Utility functions
    context.ts           # Crawlee context setup
    class/               # StatsManager, DedupManager, JsonlWriter, etc.
    interfaces/
  package.json, tsconfig.json
tests/
requirements.txt
```

## API Endpoints

- `POST /start` -- Start or resume a crawl job
- `POST /stop/{crawl_id}` -- Stop a running crawl
- `POST /force-finish/{crawl_id}` -- Force a stuck job to terminal state
- `GET /status` -- List all jobs (optional `?status=` filter)
- `GET /status/{crawl_id}` -- Single job status
- `GET /results/{crawl_id}` -- Download crawl results archive
- `GET /capacity` -- Current running/max capacity
- `POST /archive/{crawl_id}` -- Archive finished job to GCS
- `POST /reindex-storage` -- Re-index orphaned jobs from disk
- `POST /reconcile-jobs` -- Fix counter drift
- `POST /prune-archives` -- Clean up old archives

## Update Mode (Archived Previous Crawl Handling)

When `crawl_mode=update`, the service validates and restores data from the previous crawl:

1. **Pre-flight validation** (`start_crawl`): Checks `previous_crawl_id` exists, is not `failed`, and has dataset files on disk.
2. **Auto-restore from GCS** (`_restore_archived_crawl`): If previous crawl is `archived` (data deleted), downloads the archive from GCS via the download daemon and extracts it. Uses a Redis lock (`restore_lock:{id}`) to prevent concurrent restorations.
3. **Node.js safety net** (`main.ts`): If URL consolidation produces 0 URLs in update mode, exits with code 4 (mapped to failure webhook).
4. **Post-crawl cleanup** (`_monitor_process`): Deletes restored data for archived previous crawls after the update crawl completes.

## Archiving — GCS Fallback

`POST /archive/{crawl_id}` checks three locations in order:
1. **Local `/app/archives/`** — if `.tar.gz` exists, skip re-generation, mark as `archived`.
2. **GCS via download daemon** — if archive was already uploaded, fix status to `archived` without re-archiving.
3. **Fresh archive** — create new `.tar.gz` from local data, mark as `archived`, upload daemon handles GCS.

The GCS fallback (step 2) handles legacy crawls stuck at `finished` due to a previous bug where `_mark_as_archived` was never called.

## Exit Codes (Node.js → Python)

| Code | Meaning | Python Behavior |
|------|---------|-----------------|
| 0 | Success | Status: `finished`, success webhook |
| 2 | Partial success | Status: `finished`, success webhook |
| 3 | OOM relaunch | Status: `restarting_oom`, auto-relaunch (up to `MAX_OOM_RESTARTS`) |
| 4 | Update mode no data | Status: `failed`, failure webhook with descriptive message |
| Other | Failure | Status: `failed`, failure webhook |

## Conventions

- Nginx handles path stripping; routers have no prefix. Crawler spawned as child process by `crawler_manager`.

## Dependencies

Redis (state/counters), GCS (archive + restore), `common-utils`, `api-detection-langue-fr`.
