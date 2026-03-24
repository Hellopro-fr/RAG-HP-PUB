# crawler-service-python

Pure-Python web crawler service using Crawlee and Camoufox for stealth browsing.

## Tech Stack

- **Framework:** Python 3.11, FastAPI, Uvicorn
- **Crawler:** Crawlee (Playwright integration), Camoufox (Firefox-based stealth)
- **Browser:** Playwright Chromium + Firefox (Camoufox)
- **State:** Redis (job tracking, counters)
- **HTML Parsing:** BeautifulSoup4, lxml

## Commands

| Action | Command |
|--------|---------|
| Run | `uvicorn app.main:app --host 0.0.0.0 --port 8503` |
| Deps | `pip install -r requirements.txt` |

## Docker

- Base: `python:3.11-slim`
- Installs Playwright browsers (Chromium + Firefox) and Camoufox binary
- Port: **8503**
- `PYTHONPATH=/app`

## Folder Structure

```
app/
  main.py                # FastAPI app with lifespan manager
  router/
    crawler.py           # Crawler REST endpoints (same API as crawler-service)
  core/
    config.py            # Settings
    crawler_manager.py   # Job lifecycle
    redis.py             # Redis cache service
  schemas/
    crawler.py           # Pydantic models
src/
  main.py                # Crawlee crawler entry point
  routes.py              # Page route handlers
  utils.py               # Helper functions
  state.py               # Crawler state management
  domain_fr.py           # French domain detection
  redirect_tracker.py    # Redirect tracking
tests/
requirements.txt
```

## API Endpoints

- `GET /health` -- Health check
- `POST /crawler/start` -- Start a crawl job
- `POST /crawler/stop/{crawl_id}` -- Stop a crawl
- `POST /crawler/force-finish/{crawl_id}` -- Force terminal state
- `GET /crawler/status` -- List all jobs
- `GET /crawler/status/{crawl_id}` -- Single job status
- `GET /crawler/results/{crawl_id}` -- Download results
- `GET /crawler/capacity` -- Running/max capacity
- `POST /crawler/archive/{crawl_id}` -- Archive to GCS
- `POST /crawler/reindex-storage` -- Re-index orphaned jobs
- `POST /crawler/reconcile-jobs` -- Fix counter drift
- `POST /crawler/prune-archives` -- Clean up archives

## Conventions

- Uses `asynccontextmanager` lifespan (modern FastAPI pattern)
- Background reconciliation + archive cleanup tasks
- Router prefix: `/crawler`
- API-compatible with `crawler-service` (Node.js variant)

## Dependencies

- **Redis** for job state and coordination
- **GCS** (via upload daemon) for archive storage
