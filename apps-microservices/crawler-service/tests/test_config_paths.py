"""Regression tests for GCS download path alignment.

These three tests pin the contract between three layers of the GCS download
pipeline:
  1. Python container default (settings.DOWNLOAD_REQUESTS_PATH / _RESULTS_PATH)
  2. docker-compose bind target (/app/download_requests, /app/download_results)
  3. Host-side daemon env var read (DOWNLOAD_REQUESTS_PATH / DOWNLOAD_RESULTS_PATH)

If any layer drifts, the FastAPI service writes .request files into a
non-mounted directory and every GCS download times out at 504.

Regression history: introduced by commit 29918f83 (2026-03-31) when the
pydantic-settings refactor silently renamed Python defaults. See
docs/superpowers/specs/2026-05-18-gcs-download-path-alignment-design.md.
"""

from pathlib import Path


def test_download_requests_path_matches_compose_bind_target():
    """settings.DOWNLOAD_REQUESTS_PATH must equal the compose bind target.

    Compose binds host crawler_download_requests/ -> container
    /app/download_requests (docker-compose.yml:1348). If this default
    drifts, the FastAPI side writes .request files into a non-mounted
    directory and the host daemon never sees them — every GCS download
    504s.
    """
    from app.core.config import settings
    assert settings.DOWNLOAD_REQUESTS_PATH == "/app/download_requests"


def test_download_results_path_matches_compose_bind_target():
    """settings.DOWNLOAD_RESULTS_PATH must equal the compose bind target.

    Compose binds host crawler_download_results/ -> container
    /app/download_results (docker-compose.yml:1349). Same reasoning as
    DOWNLOAD_REQUESTS_PATH: drift here means the FastAPI poller watches
    a non-mounted directory and 504s on every download.
    """
    from app.core.config import settings
    assert settings.DOWNLOAD_RESULTS_PATH == "/app/download_results"


def test_download_daemon_uses_canonical_env_var_names():
    """tools/download_daemon.sh must read the same env var names as Python.

    Historic daemon names DOWNLOAD_REQUESTS_DIR / DOWNLOAD_RESULTS_DIR
    diverged from the Python side (DOWNLOAD_REQUESTS_PATH /
    DOWNLOAD_RESULTS_PATH). After the alignment fix the daemon and Python
    both read the same env vars; this test catches a future regression
    back to the legacy _DIR names.
    """
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
