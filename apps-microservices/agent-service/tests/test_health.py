from fastapi.testclient import TestClient

from main import app


def test_health_repond_ok():
    reponse = TestClient(app).get("/health")
    assert reponse.status_code == 200
    assert reponse.json()["status"] == "ok"
