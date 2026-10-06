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


def test_compare_logs_summary_not_full_text(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="app.api.routes")
    client = TestClient(main.app)
    long_old = "ancien " + "a" * 5000
    r = client.post("/api/v1/compare", json={"url": "https://ex.com/p1", "new_content": "Nouveau\ntexte  court", "old_text": long_old})
    assert r.status_code == 200
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "app.api.routes"]
    assert len(lines) == 1
    line = lines[0]
    assert "url=https://ex.com/p1" in line and "decision=" in line and "ratio=" in line
    assert f"len={len(long_old)}" in line
    assert "Nouveau texte court" in line          # extrait sur une ligne, espaces normalises
    assert "a" * 200 not in line                  # jamais le texte entier


def test_batch_logs_one_line_per_item(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="app.api.routes")
    client = TestClient(main.app)
    r = client.post("/api/v1/compare-batch", json={"items": [
        {"url": "u1", "new_content": "<p>Bonjour</p>", "old_text": "Bonjour", "content_type": "html"},
        {"url": "u2", "new_content": "abc", "old_text": "xyz"},
    ]})
    assert r.status_code == 200
    lines = [rec.getMessage() for rec in caplog.records if rec.name == "app.api.routes"]
    assert len(lines) == 2
    assert any("url=u1 type=html" in x for x in lines) and any("url=u2 type=text" in x for x in lines)


def test_preview_disabled(monkeypatch):
    from app.api import routes
    monkeypatch.setattr(routes.settings, "LOG_PREVIEW_CHARS", 0)
    assert routes._summary("secret text") == "len=11"
