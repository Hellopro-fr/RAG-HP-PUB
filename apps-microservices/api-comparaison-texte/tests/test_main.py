from fastapi.testclient import TestClient

import main


def test_metrics_endpoint_ok():
    client = TestClient(main.app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.text is not None


def test_health_and_root_ok():
    client = TestClient(main.app)
    assert client.get("/api/v1/health").json()["status"] == "healthy"
    assert "service" in client.get("/").json()
