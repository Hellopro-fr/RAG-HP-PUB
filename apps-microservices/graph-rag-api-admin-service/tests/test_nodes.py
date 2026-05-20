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
        "found": [{"id": 1, "node": {"id": "id_produit_1", "id_produit": "1"}}],
        "missing": [2],
    }
    with patch.object(
        nodes_router.node_service,
        "batch_get_nodes",
        new=AsyncMock(return_value=payload),
    ) as mock_svc:
        resp = client.post("/nodes/Produit/batch/get", json={"ids": [1, 2]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] == payload["found"]
    assert body["missing"] == [2]
    # Default fields forwarded to service
    args, _ = mock_svc.await_args
    assert args[2] == ["id_produit", "id"]


def test_batch_get_route_custom_fields_forwarded(client):
    payload = {"found": [], "missing": [1]}
    with patch.object(
        nodes_router.node_service,
        "batch_get_nodes",
        new=AsyncMock(return_value=payload),
    ) as mock_svc:
        resp = client.post(
            "/nodes/Produit/batch/get",
            json={"ids": [1], "fields": ["nom_produit"]},
        )

    assert resp.status_code == 200
    args, _ = mock_svc.await_args
    assert args[2] == ["nom_produit"]


def test_batch_get_route_empty_list_returns_422(client):
    resp = client.post("/nodes/Produit/batch/get", json={"ids": []})
    assert resp.status_code == 422


def test_batch_get_route_over_cap_returns_422(client):
    ids = list(range(501))
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


def test_batch_upsert_route_returns_found_and_missing(client):
    # Service returns only changed keys (not the full node)
    payload = {
        "found": [
            {"id": 1, "node": {"statut": "active"}},
        ],
        "missing": [2],
    }
    with patch.object(
        nodes_router.node_service,
        "batch_upsert_nodes",
        new=AsyncMock(return_value=payload),
    ):
        resp = client.post(
            "/nodes/Produit/batch/upsert",
            json={"ids": [1, 2], "properties": {"statut": "active"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] == payload["found"]
    assert body["missing"] == [2]


def test_batch_upsert_route_empty_ids_returns_422(client):
    resp = client.post(
        "/nodes/Produit/batch/upsert",
        json={"ids": [], "properties": {"statut": "active"}},
    )
    assert resp.status_code == 422


def test_batch_upsert_route_over_cap_returns_422(client):
    ids = list(range(501))
    resp = client.post(
        "/nodes/Produit/batch/upsert",
        json={"ids": ids, "properties": {"x": 1}},
    )
    assert resp.status_code == 422
