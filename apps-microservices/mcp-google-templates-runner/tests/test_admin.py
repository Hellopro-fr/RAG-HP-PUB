import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://localhost:0")
    monkeypatch.setenv("MCP_GATEWAY_ADMIN_TOKEN", "t")
    monkeypatch.setenv("RUNNER_ADMIN_TOKEN", "t")
    # Reload app.config and app.main so settings picks up the monkeypatched env.
    # Option A from Task 18 plan notes: reload settings module after monkeypatch.
    import importlib

    import app.config

    importlib.reload(app.config)
    # Rebind the settings reference in modules that imported it by name.
    import app.auth
    import app.main

    importlib.reload(app.auth)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def test_health_no_auth(client):
    r = client.get("/admin/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_requires_token(client):
    r = client.get("/admin/instances")
    assert r.status_code == 401


def test_list_with_token(client):
    r = client.get("/admin/instances", headers={"X-Admin-Token": "t"})
    assert r.status_code == 200
    assert r.json() == {"instances": []}
