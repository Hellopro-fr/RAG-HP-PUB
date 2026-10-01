# GCS Download Path Alignment for `crawler-service`

> **Date:** 2026-05-18
> **Status:** Approved — ready for plan writing
> **Repo:** `RAG-HP-PUB`
> **Branch:** `features/poc`

---

## 1. Problem

The host-side download daemon (`tools/download_daemon.sh`), the FastAPI orchestrator (`apps-microservices/crawler-service/app/core/crawler_manager.py` via `app/core/config.py`), and `docker-compose.yml` have drifted out of agreement on the shared-volume paths used for GCS download IPC. The drift is asymmetric: only the **download** pipeline is broken; the **upload** pipeline remains aligned.

### Current state (HEAD `b19c43a7`)

| Layer | Path | Source |
|---|---|---|
| Python container default `DOWNLOAD_REQUESTS_PATH` | `/app/gcs-requests` | `app/core/config.py:34` |
| Python container default `DOWNLOAD_RESULTS_PATH` | `/app/gcs-downloads` | `app/core/config.py:35` |
| Compose bind target (in container) | `/app/download_requests`, `/app/download_results` | `docker-compose.yml:1348-1349` |
| Compose bind source (on host) | `./apps-microservices/crawler-service/crawler_download_requests`, `./apps-microservices/crawler-service/crawler_download_results` | `docker-compose.yml:1348-1349` |
| Daemon default (on host) | `<repo>/apps-microservices/crawler-service/crawler_download_requests`, `<repo>/apps-microservices/crawler-service/crawler_download_results` | `tools/download_daemon.sh:17-21` |
| Daemon env var name | `DOWNLOAD_REQUESTS_DIR`, `DOWNLOAD_RESULTS_DIR` | `tools/download_daemon.sh:18,21` |
| Python env var name | `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH` | `pydantic_settings.BaseSettings` |

### Effect

Unless `.env` overrides Python's `DOWNLOAD_REQUESTS_PATH` and `DOWNLOAD_RESULTS_PATH` to match the compose bind target inside the container, the FastAPI service writes `.request` markers to `/app/gcs-requests` (a non-mounted directory inside the container) and polls `/app/gcs-downloads` for `.done` / `.error` markers that never arrive. The host-side daemon — which polls the correctly-mounted directory `crawler_download_requests/` — never sees the requests, and every GCS download path (`get_results_archive` for archived crawls, `_restore_archived_crawl` for update-mode restoration) times out at `GCS_DOWNLOAD_TIMEOUT_SECONDS` (300s) and raises HTTP 504.

### When did this start

- **`1bb288a7`** (2026-03-17, Rindra) — `feat: Crawler-Service : Implementing Archiving and Downloading to/from Google Storage`. Original feature. Python defaults were `/app/download_requests` and `/app/download_results`, matching the compose bind target. Used `os.getenv(...)`, env-overridable. **All three layers aligned.**
- **`29918f83`** (2026-03-31, Rindra) — `fix(crawler-service): corriger les race conditions critiques, la dérive du compteur et renforcer le service`. Refactored the plain `Settings` class to `pydantic_settings.BaseSettings`. As part of the refactor, the defaults were silently renamed:
  - `DOWNLOAD_REQUESTS_PATH`: `/app/download_requests` → `/app/gcs-requests`
  - `DOWNLOAD_RESULTS_PATH`: `/app/download_results` → `/app/gcs-downloads`
  Compose was not updated. **Regression landed here, 48 days ago.**

### Bonus: env var name drift

Independent of the path drift, the daemon and Python sides use different env var names for the same concept:
- Daemon: `DOWNLOAD_REQUESTS_DIR`, `DOWNLOAD_RESULTS_DIR` (`_DIR` suffix)
- Python: `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH` (`_PATH` suffix)

An operator must set both pairs in `.env` (4 variables) to override the defaults consistently. This violates least-surprise and was not present in the original `1bb288a7` design (which used `os.getenv("DOWNLOAD_REQUESTS_PATH", ...)` on the Python side and the daemon was added in the same commit with `_DIR` suffix).

## 2. Goals

- Restore the original `1bb288a7` container path defaults so the FastAPI service writes to the correctly-mounted directory without requiring `.env` overrides.
- Unify env var names across Python and the daemon so a single `.env` entry per direction (`DOWNLOAD_REQUESTS_PATH` / `DOWNLOAD_RESULTS_PATH`) configures both layers.
- Add a regression test that asserts the three layers stay aligned, so a future pydantic-settings refactor or compose edit cannot silently re-introduce the drift.

## 3. Non-Goals

- Code-reviewer findings against the download pipeline (shell injection on `crawl_id`, non-atomic `.tar.gz` visibility, orphan tar on caller timeout, `cleanup_temp_download` race with restore, missing Prometheus metrics, daemon hardening). All deferred to a separate spec.
- The symmetric upload pipeline (`ARCHIVES_DIR` daemon var vs `ARCHIVES_SHARED_PATH` Python var). The paths there are aligned; only the env var names differ. Out of scope per user choice "download only".
- Auditing the production `.env` to confirm whether the regression is masked by an explicit override. Out of scope; the fix restores the defaults so the override (if any) becomes redundant rather than load-bearing.

## 4. Architecture

No architectural change. Same shared-volume file-marker IPC between the FastAPI container and the host-side bash daemon. The fix is purely a string-rename pass to restore a single source of truth for the path.

After the fix:

| Layer | Path / Var |
|---|---|
| Python container default `DOWNLOAD_REQUESTS_PATH` | `/app/download_requests` |
| Python container default `DOWNLOAD_RESULTS_PATH` | `/app/download_results` |
| Compose bind target | `/app/download_requests`, `/app/download_results` (unchanged) |
| Compose bind source | `./apps-microservices/crawler-service/crawler_download_requests`, `./apps-microservices/crawler-service/crawler_download_results` (unchanged) |
| Daemon default | `<repo>/apps-microservices/crawler-service/crawler_download_requests`, `<repo>/apps-microservices/crawler-service/crawler_download_results` (unchanged) |
| Daemon env var name | `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH` (renamed from `_DIR`) |
| Python env var name | `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH` (unchanged) |

All three layers reach `/app/download_requests` and `/app/download_results` end-to-end without any `.env` override required.

## 5. Implementation

Two files change. Compose stays as-is.

### 5.1 `apps-microservices/crawler-service/app/core/config.py`

Lines 33-35, replace:

```python
# GCS download daemon paths
DOWNLOAD_REQUESTS_PATH: str = "/app/gcs-requests"
DOWNLOAD_RESULTS_PATH: str = "/app/gcs-downloads"
```

with:

```python
# GCS download daemon paths (must match docker-compose.yml bind target for the
# crawler-service container; daemon reads the same env var names on the host)
DOWNLOAD_REQUESTS_PATH: str = "/app/download_requests"
DOWNLOAD_RESULTS_PATH: str = "/app/download_results"
```

### 5.2 `tools/download_daemon.sh`

Lines 17-21, replace:

```bash
DEFAULT_REQUESTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_requests"
REQUESTS_DIR="${DOWNLOAD_REQUESTS_DIR:-$DEFAULT_REQUESTS_DIR}"

DEFAULT_RESULTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_results"
RESULTS_DIR="${DOWNLOAD_RESULTS_DIR:-$DEFAULT_RESULTS_DIR}"
```

with:

```bash
DEFAULT_REQUESTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_requests"
REQUESTS_DIR="${DOWNLOAD_REQUESTS_PATH:-$DEFAULT_REQUESTS_DIR}"

DEFAULT_RESULTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_results"
RESULTS_DIR="${DOWNLOAD_RESULTS_PATH:-$DEFAULT_RESULTS_DIR}"
```

Hard rename of the env var read: `DOWNLOAD_REQUESTS_DIR` → `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_DIR` → `DOWNLOAD_RESULTS_PATH`. No transitional fallback.

### 5.3 Compose

No change. `docker-compose.yml:1348-1349` already binds `/app/download_requests` and `/app/download_results`.

## 6. Migration

After deploy:

1. **Operator with `DOWNLOAD_REQUESTS_DIR=` or `DOWNLOAD_RESULTS_DIR=` set in `.env`** — rename to `DOWNLOAD_REQUESTS_PATH` / `DOWNLOAD_RESULTS_PATH`. If the value also pointed to a non-default host directory, ensure the new value matches the compose bind source (`./apps-microservices/crawler-service/crawler_download_requests` and `./apps-microservices/crawler-service/crawler_download_results`).
2. **Operator with neither set (relying on defaults)** — nothing to do. The aligned defaults take effect on next container restart and daemon restart.
3. **Operator with `DOWNLOAD_REQUESTS_PATH` / `DOWNLOAD_RESULTS_PATH` set in `.env`** (to mask the regression) — review the value. If it pointed to `/app/download_requests` / `/app/download_results`, the override is now redundant but harmless; can be removed. If it pointed elsewhere, that becomes the new authoritative value for both layers.

## 7. Verification

### 7.1 Unit test — path alignment

New file: `apps-microservices/crawler-service/tests/test_config_paths.py`.

Three test cases:

```python
def test_download_requests_path_matches_compose_bind_target():
    """settings.DOWNLOAD_REQUESTS_PATH must equal the compose bind target.

    Compose binds host crawler_download_requests/ → container /app/download_requests.
    If these drift, the FastAPI side writes .request files into a non-mounted
    directory and the host daemon never sees them — every GCS download 504s.
    """
    from app.core.config import settings
    assert settings.DOWNLOAD_REQUESTS_PATH == "/app/download_requests"


def test_download_results_path_matches_compose_bind_target():
    """settings.DOWNLOAD_RESULTS_PATH must equal the compose bind target.

    Same reasoning as DOWNLOAD_REQUESTS_PATH: drift here means the FastAPI
    poller watches a non-mounted directory and 504s on every download.
    """
    from app.core.config import settings
    assert settings.DOWNLOAD_RESULTS_PATH == "/app/download_results"


def test_download_daemon_uses_canonical_env_var_names():
    """tools/download_daemon.sh must read DOWNLOAD_REQUESTS_PATH / DOWNLOAD_RESULTS_PATH.

    Historic var names DOWNLOAD_REQUESTS_DIR / DOWNLOAD_RESULTS_DIR diverged from
    the Python side. After the alignment fix the daemon and Python both read
    the same env vars; this test catches a future regression to the _DIR names.
    """
    from pathlib import Path

    daemon = Path(__file__).resolve().parents[3] / "tools" / "download_daemon.sh"
    content = daemon.read_text(encoding="utf-8")

    assert "DOWNLOAD_REQUESTS_PATH" in content, (
        "Daemon must read DOWNLOAD_REQUESTS_PATH env var (canonical name)"
    )
    assert "DOWNLOAD_RESULTS_PATH" in content, (
        "Daemon must read DOWNLOAD_RESULTS_PATH env var (canonical name)"
    )
    assert "DOWNLOAD_REQUESTS_DIR" not in content, (
        "Daemon must not read the legacy DOWNLOAD_REQUESTS_DIR var name"
    )
    assert "DOWNLOAD_RESULTS_DIR" not in content, (
        "Daemon must not read the legacy DOWNLOAD_RESULTS_DIR var name"
    )
```

Run:
```bash
cd apps-microservices/crawler-service
python -m pytest tests/test_config_paths.py -v
```

All three pass.

### 7.2 Static scope check

Before commit, confirm no other reference to the legacy names:

```bash
git grep -nE "DOWNLOAD_REQUESTS_DIR|DOWNLOAD_RESULTS_DIR|/app/gcs-requests|/app/gcs-downloads" -- ':!docs' ':!graphify-out' ':!*.md'
```

Expected output: empty.

### 7.3 Existing crawler-service test suite

```bash
cd apps-microservices/crawler-service
python -m pytest --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py --ignore=tests/test_routes_invalid_page.py -q
```

Expected: pre-existing pass count unchanged (no regression). The three ignored test files are the pre-existing broken-locally tests documented in `~/.claude/primer.md` (cp1252/fastText/import-path issues unrelated to this fix).

### 7.4 Operator smoke (post-deploy, manual)

Documented for the operator; not part of the automated suite.

1. Deploy crawler-service to staging.
2. Restart the host-side `download_daemon.sh` so it picks up the renamed env var.
3. Identify an archived `crawl_id` on staging via `GET /status?status=archived` (returns the JSON list of archived jobs). Pick any `crawl_id` from the response.
4. `curl -fsS https://staging/crawler-service/results/<crawl_id> -o /tmp/x.tar.gz`.
5. Expected: HTTP 200, `.tar.gz` size > 0, response time < `GCS_DOWNLOAD_TIMEOUT_SECONDS` (300s).
6. Negative case: kill the daemon, retry step 4 — expected HTTP 504 with body containing "Ensure the download daemon is running". Restart daemon, retry — expected HTTP 200.

## 8. Deploy gate

- crawler-service container redeploy required (new defaults).
- Daemon restart required (renamed env var read).
- Order: redeploy container first, then restart daemon. Otherwise the daemon would still read `DOWNLOAD_REQUESTS_DIR` (legacy var) while the container writes to the new aligned path, which by coincidence still works because the daemon's default host path matches the compose bind source — but only because the operator did not override either var. Doing container first eliminates the order-dependency from the operator's mental model.

## 9. Risks

- **Operator `.env` had `DOWNLOAD_REQUESTS_DIR` pointing to a non-default host path.** After daemon rename, the legacy var is ignored; daemon falls back to default host dir (`crawler_download_requests/`). If that directory is not the compose bind source, daemon writes elsewhere and the FastAPI side 504s. Mitigation: §6 migration note tells operator to rename the var.
- **Two unrelated PRs touch `config.py` concurrently.** Pydantic-settings is a single class definition; a merge conflict is mechanical. No semantic risk.
- **Future pydantic-settings refactor re-renames the field.** §7.1 regression test catches this on the next CI run.

## 10. Open questions

None.

## 11. References

- Regression commit: `29918f83`
- Original feature commit: `1bb288a7`
- Code-reviewer findings parked for separate spec (not in scope here).
