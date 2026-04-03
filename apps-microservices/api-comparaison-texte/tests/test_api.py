import pytest
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Health ---

@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"


@pytest.mark.anyio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "service" in data
    assert "docs" in data


# --- Single compare ---

@pytest.mark.anyio
async def test_compare_update(client):
    """Textes très différents → UPDATE."""
    r = await client.post("/api/v1/compare", json={
        "url": "https://example.com/p1",
        "new_content": "Texte complètement nouveau et différent",
        "old_text": "Ancien texte original du produit avec des informations totalement autres",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert data["result"]["decision"] == "UPDATE"
    assert data["result"]["similarity_ratio"] < 0.85


@pytest.mark.anyio
async def test_compare_skip(client):
    """Textes identiques → SKIP."""
    text = "Le produit X est disponible en plusieurs coloris et tailles différentes"
    r = await client.post("/api/v1/compare", json={
        "url": "https://example.com/p2",
        "new_content": text,
        "old_text": text,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["decision"] == "SKIP"
    assert data["result"]["similarity_ratio"] == 1.0


@pytest.mark.anyio
async def test_compare_html_content(client):
    """content_type=html déclenche le nettoyage HTML."""
    html = "<html><body><script>var x=1;</script><p>Texte visible du produit</p></body></html>"
    r = await client.post("/api/v1/compare", json={
        "url": "https://example.com/p3",
        "new_content": html,
        "old_text": "Texte visible du produit",
        "content_type": "html",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["decision"] == "SKIP"
    assert data["result"]["similarity_ratio"] == 1.0


@pytest.mark.anyio
async def test_compare_custom_threshold(client):
    """Un seuil élevé rend un texte légèrement modifié → UPDATE."""
    r = await client.post("/api/v1/compare", json={
        "url": "https://example.com/p4",
        "new_content": "Le produit X est disponible en plusieurs coloris",
        "old_text": "Le produit X est disponible en plusieurs couleurs",
        "threshold": 0.99,
    })
    assert r.status_code == 200
    assert r.json()["result"]["decision"] == "UPDATE"


# --- Batch ---

@pytest.mark.anyio
async def test_batch_mixed(client):
    """Batch avec un UPDATE et un SKIP."""
    same_text = "Texte identique pour les deux comparaisons de ce test"
    r = await client.post("/api/v1/compare-batch", json={
        "items": [
            {
                "url": "https://example.com/p1",
                "new_content": "Contenu totalement nouveau et différent",
                "old_text": "Ancien contenu qui ne ressemble en rien au nouveau",
            },
            {
                "url": "https://example.com/p2",
                "new_content": same_text,
                "old_text": same_text,
            },
        ]
    })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["success_count"] == 2
    assert data["error_count"] == 0
    assert "processing_time_ms" in data

    decisions = [item["decision"] for item in data["results"]]
    assert "UPDATE" in decisions
    assert "SKIP" in decisions


@pytest.mark.anyio
async def test_batch_empty_rejected(client):
    """Batch vide rejeté par validation Pydantic (422)."""
    r = await client.post("/api/v1/compare-batch", json={
        "items": []
    })
    assert r.status_code == 422


@pytest.mark.anyio
async def test_batch_with_threshold(client):
    """Seuil custom appliqué à tout le batch."""
    r = await client.post("/api/v1/compare-batch", json={
        "items": [
            {
                "url": "https://example.com/p1",
                "new_content": "Texte légèrement modifié ici",
                "old_text": "Texte légèrement modifié là",
            }
        ],
        "threshold": 0.99,
    })
    assert r.status_code == 200
    assert r.json()["results"][0]["decision"] == "UPDATE"
