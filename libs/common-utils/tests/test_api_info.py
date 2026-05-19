from fastapi import FastAPI
from fastapi.testclient import TestClient

from common_utils.api_info import register_api_info


def test_minimal_payload():
    app = FastAPI()
    register_api_info(app, service="x", version="1.0")
    c = TestClient(app)
    r = c.get("/api-info")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "x"
    assert body["version"] == "1.0"
    assert body["rest"]["openapi_url"] == "/openapi.json"
    assert "ws" not in body
    assert "grpc" not in body


def test_full_payload():
    app = FastAPI()
    register_api_info(
        app,
        service="x",
        version="1.0",
        ws_endpoints=[{"path": "/ws/a"}],
        grpc_address="x:9000",
        grpc_reflection=True,
    )
    c = TestClient(app)
    body = c.get("/api-info").json()
    assert body["ws"]["endpoints"][0]["path"] == "/ws/a"
    assert body["grpc"]["address"] == "x:9000"
    assert body["grpc"]["reflection"] is True


def test_custom_openapi_url():
    app = FastAPI()
    register_api_info(app, service="x", openapi_url="/api/openapi.json")
    body = TestClient(app).get("/api-info").json()
    assert body["rest"]["openapi_url"] == "/api/openapi.json"
