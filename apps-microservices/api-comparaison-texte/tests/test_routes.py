import asyncio

from fastapi.testclient import TestClient

import main
from app.api.routes import compare_batch
from app.models.schemas import BatchComparisonRequest


def test_batch_offload_does_not_block_loop():
    big = [{"url": f"u{i}", "new_content": "x" * 4000, "old_text": "y" * 4000} for i in range(40)]
    req = BatchComparisonRequest(items=big)

    async def scenario():
        ticked = {"n": 0}

        async def ticker():
            for _ in range(5):
                await asyncio.sleep(0.001)
                ticked["n"] += 1

        await asyncio.gather(compare_batch(req), ticker())
        return ticked["n"]

    assert asyncio.run(scenario()) == 5


def test_admission_503_when_full(monkeypatch):
    import app.core.admission as adm
    monkeypatch.setattr(adm.admission, "try_acquire", lambda: False)
    client = TestClient(main.app)
    r = client.post("/api/v1/compare", json={"url": "u", "new_content": "a", "old_text": "b"})
    assert r.status_code == 503
    assert "Retry-After" in r.headers


def test_batch_behaviour_preserved():
    client = TestClient(main.app)
    same = "Texte identique de ce test precis"
    r = client.post("/api/v1/compare-batch", json={"items": [
        {"url": "u1", "new_content": "Contenu totalement different ici", "old_text": "Ancien sans rapport"},
        {"url": "u2", "new_content": same, "old_text": same},
    ]})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2 and data["error_count"] == 0
    decisions = [x["decision"] for x in data["results"]]
    assert "UPDATE" in decisions and "SKIP" in decisions
