from fastapi.testclient import TestClient

from app.core.admission import SyncAdmission


def test_disabled_always_admits():
    a = SyncAdmission(0)
    assert all(a.try_acquire() for _ in range(100))


def test_caps_at_max_and_releases():
    a = SyncAdmission(1)
    assert a.try_acquire() is True
    assert a.try_acquire() is False
    a.release()
    assert a.try_acquire() is True


def test_release_floors_at_zero():
    a = SyncAdmission(2)
    a.release()
    a.release()
    assert a.try_acquire() is True
    assert a.try_acquire() is True
    assert a.try_acquire() is False


def test_router_503_when_admission_full(monkeypatch):
    import app.core.admission as adm
    monkeypatch.setattr(adm.admission, "try_acquire", lambda: False)
    import main
    client = TestClient(main.app)
    r = client.post("/clean", json={"html": "<p>x</p>", "format": "text"})
    assert r.status_code == 503
    assert "Retry-After" in r.headers
