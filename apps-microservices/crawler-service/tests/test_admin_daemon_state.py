"""Tests for GET /admin/daemon-state (GCS daemon liveness/backlog view)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_dirs(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    # Point every shared dir at tmp subdirs (only some will exist).
    monkeypatch.setattr(settings, "ARCHIVES_SHARED_PATH", str(tmp_path / "archives"), raising=False)
    monkeypatch.setattr(settings, "STASH_SHARED_PATH", str(tmp_path / "stash"), raising=False)
    monkeypatch.setattr(settings, "DOWNLOAD_REQUESTS_PATH", str(tmp_path / "dlreq"), raising=False)
    monkeypatch.setattr(settings, "DOWNLOAD_RESULTS_PATH", str(tmp_path / "dlres"), raising=False)
    monkeypatch.setattr(settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(tmp_path / "sdreq"), raising=False)
    monkeypatch.setattr(settings, "STASH_DOWNLOAD_RESULTS_PATH", str(tmp_path / "sdres"), raising=False)
    monkeypatch.setattr(settings, "MOVE_REQUESTS_PATH", str(tmp_path / "mvreq"), raising=False)
    monkeypatch.setattr(settings, "MOVE_RESULTS_PATH", str(tmp_path / "mvres"), raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app), tmp_path


def test_missing_dirs_reported_not_fatal(client_and_dirs):
    client, _ = client_and_dirs
    body = client.get("/admin/daemon-state").json()
    assert body["archives"]["exists"] is False
    assert set(body.keys()) >= {"archives", "stash", "download_requests",
                                "move_requests", "archives_dead_letter"}


def test_files_heartbeat_and_error_markers(client_and_dirs):
    client, tmp = client_and_dirs
    d = tmp / "dlreq"
    d.mkdir()
    (d / "123.request").write_text("", encoding="utf-8")
    (d / "456.error").write_text("gcloud: AccessDenied", encoding="utf-8")
    (d / ".daemon-heartbeat").write_text("2026-07-04T00:00:00Z", encoding="utf-8")
    body = client.get("/admin/daemon-state").json()
    dl = body["download_requests"]
    assert dl["exists"] is True
    assert dl["file_count"] == 2  # heartbeat excluded
    assert dl["heartbeat_age_seconds"] is not None
    assert dl["error_markers"]["456.error"].startswith("gcloud")
    names = {f["name"] for f in dl["files"]}
    assert names == {"123.request", "456.error"}


def test_scan_truncated_flag(client_and_dirs, monkeypatch):
    import app.router.admin as admin_mod
    monkeypatch.setattr(admin_mod, "_DAEMON_STATE_MAX_SCAN", 1)
    client, tmp = client_and_dirs
    d = tmp / "dlreq"
    d.mkdir()
    for i in range(3):
        (d / f"{i}.request").write_text("", encoding="utf-8")
    body = client.get("/admin/daemon-state").json()
    dl = body["download_requests"]
    assert dl["scan_truncated"] is True
    assert dl["file_count"] == 1
