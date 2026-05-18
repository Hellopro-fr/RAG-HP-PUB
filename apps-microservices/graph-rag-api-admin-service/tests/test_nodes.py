"""
Unit tests for the batch routes on the /nodes/{label}/batch/* endpoints.

The router calls into NodeService — these tests mock the service layer so the
HTTP contract is exercised without needing Neo4j.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.routers import nodes as nodes_router  # noqa: E402


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(nodes_router.router, prefix="/nodes")
    return TestClient(app)


def test_batch_get_route_returns_found_and_missing(client):
    payload = {
        "found": [{"id": "1", "node": {"id": "id_produit_1", "nom": "A"}}],
        "missing": ["2"],
    }
    with patch.object(
        nodes_router.node_service,
        "batch_get_nodes",
        new=AsyncMock(return_value=payload),
    ):
        resp = client.post("/nodes/Produit/batch/get", json={"ids": ["1", "2"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] == payload["found"]
    assert body["missing"] == ["2"]


def test_batch_get_route_empty_list_returns_422(client):
    resp = client.post("/nodes/Produit/batch/get", json={"ids": []})
    assert resp.status_code == 422


def test_batch_get_route_over_cap_returns_422(client):
    ids = [str(i) for i in range(501)]
    resp = client.post("/nodes/Produit/batch/get", json={"ids": ids})
    assert resp.status_code == 422


def test_batch_update_route_returns_found_and_missing(client):
    payload = {
        "found": [{"id": "1", "node": {"id": "id_produit_1", "nom": "X"}}],
        "missing": ["2"],
    }
    with patch.object(
        nodes_router.node_service,
        "batch_update_nodes",
        new=AsyncMock(return_value=payload),
    ):
        resp = client.post(
            "/nodes/Produit/batch/update",
            json={
                "items": [
                    {"id": "1", "properties": {"nom": "X"}},
                    {"id": "2", "properties": {"nom": "Y"}},
                ]
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] == payload["found"]
    assert body["missing"] == ["2"]


def test_batch_update_route_invalid_label_returns_400(client):
    with patch.object(
        nodes_router.node_service,
        "batch_update_nodes",
        new=AsyncMock(side_effect=ValueError("Invalid node label format.")),
    ):
        resp = client.post(
            "/nodes/Produit/batch/update",
            json={"items": [{"id": "1", "properties": {}}]},
        )
    assert resp.status_code == 400
