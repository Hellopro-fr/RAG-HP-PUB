from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api.admin as admin
import app.main as main
from app.precheck import PrecheckError

TOKEN = {"X-Admin-Token": "runner-token"}
CREDS = '{"uri":"bolt://neo4j:7687","username":"reader","password":"s3cret","database":"neo4j"}'


def _body(creds=CREDS):
    return {
        "instance_id": "i1",
        "template_slug": "neo4j",
        "stdio_command": "mcp-neo4j-cypher",
        "stdio_args": [],
        "env": {"NEO4J_READ_ONLY": "true"},
        "credentials_json": creds,
        "credentials_hash": "h",
    }


@pytest.fixture
def fake_sup():
    sup = MagicMock()
    sup.list.return_value = []
    sup.spawn = AsyncMock(return_value=MagicMock(port=15100, pid=42))
    sup.kill = AsyncMock()
    return sup


@pytest.fixture
def client(fake_sup):
    main.app.dependency_overrides[admin.get_supervisor] = lambda: fake_sup
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def test_health_no_auth(client):
    r = client.get("/admin/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_list_requires_token(client):
    assert client.get("/admin/instances").status_code == 401


def test_spawn_invalid_credentials_422(client, fake_sup):
    r = client.post("/admin/instances", json=_body(creds="{}"), headers=TOKEN)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "neo4j_invalid_credentials"
    fake_sup.spawn.assert_not_called()


def test_spawn_connection_flag_in_args_422(client, fake_sup):
    body = _body()
    body["stdio_args"] = ["--password", "x"]
    r = client.post("/admin/instances", json=body, headers=TOKEN)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "neo4j_invalid_credentials"
    fake_sup.spawn.assert_not_called()


def test_spawn_precheck_failure_422(client, fake_sup, monkeypatch):
    async def failing(creds, timeout):
        raise PrecheckError("neo4j_auth_failed", "Neo4j rejected the username or password")

    monkeypatch.setattr(admin, "verify_connection", failing)
    r = client.post("/admin/instances", json=_body(), headers=TOKEN)
    assert r.status_code == 422
    assert r.json()["detail"] == {
        "code": "neo4j_auth_failed",
        "message": "Neo4j rejected the username or password",
    }
    assert "s3cret" not in r.text
    # The running instance (if any) is untouched: spawn() never ran.
    fake_sup.spawn.assert_not_called()


def test_spawn_success(client, fake_sup, monkeypatch):
    monkeypatch.setattr(admin, "verify_connection", AsyncMock(return_value=None))
    r = client.post("/admin/instances", json=_body(), headers=TOKEN)
    assert r.status_code == 200
    assert r.json() == {"port": 15100, "pid": 42}
    fake_sup.spawn.assert_awaited_once()


def test_reconcile_endpoint_skips_precheck(client, fake_sup, monkeypatch):
    check = AsyncMock(side_effect=AssertionError("pre-check must not run on reconcile"))
    monkeypatch.setattr(admin, "verify_connection", check)
    r = client.post("/admin/reconcile", json={"desired_instances": [_body()]}, headers=TOKEN)
    assert r.status_code == 202
    assert r.json() == {"spawned": 1}
    check.assert_not_called()


def test_validation_error_does_not_echo_input(client, fake_sup):
    body = _body(creds=CREDS.replace("s3cret", "CANARY-PW"))
    del body["credentials_hash"]
    r = client.post("/admin/instances", json=body, headers=TOKEN)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert "body.credentials_hash" in detail["message"]
    assert "CANARY-PW" not in r.text
    fake_sup.spawn.assert_not_called()
