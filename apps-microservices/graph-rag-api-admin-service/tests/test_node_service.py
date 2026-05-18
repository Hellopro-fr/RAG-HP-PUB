"""
Unit tests for the batch operations of NodeService.

These tests cover only the new batch_get_nodes / batch_update_nodes methods.
They mock the underlying gRPC `clients.execute_cypher` call so they can be
run locally without access to Neo4j / RabbitMQ / the rest of the platform.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Make `app.*` importable when pytest is invoked from this service dir
SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.domain.models import BatchUpdateItem  # noqa: E402
from app.services.node_service import node_service  # noqa: E402


# ---------- batch_get_nodes ----------


@pytest.mark.asyncio
async def test_batch_get_nodes_returns_found_and_missing():
    fake_results = [
        {"id": "id_produit_1", "n": {"id": "id_produit_1", "nom": "A"}},
    ]
    with patch(
        "app.services.node_service.clients.execute_cypher",
        new=AsyncMock(return_value=fake_results),
    ) as mock_exec:
        out = await node_service.batch_get_nodes("Produit", [1, 2])

    assert out["found"] == [
        {"id": 1, "node": {"id": "id_produit_1", "nom": "A"}}
    ]
    assert out["missing"] == [2]

    # Verify the query is a single batch query (not a loop)
    assert mock_exec.await_count == 1
    args, kwargs = mock_exec.await_args
    query = args[0]
    assert "WHERE n.id IN $ids" in query
    assert kwargs.get("read_only") is True


@pytest.mark.asyncio
async def test_batch_get_nodes_invalid_label_raises():
    with pytest.raises(ValueError):
        await node_service.batch_get_nodes("Bad;Label", [1])


@pytest.mark.asyncio
async def test_batch_get_nodes_empty_input():
    out = await node_service.batch_get_nodes("Produit", [])
    assert out == {"found": [], "missing": []}


# ---------- batch_update_nodes ----------


@pytest.mark.asyncio
async def test_batch_update_nodes_returns_found_and_missing():
    fake_results = [
        {"id": "id_produit_1", "n": {"id": "id_produit_1", "nom": "X"}},
    ]
    items = [
        BatchUpdateItem(id="1", properties={"nom": "X"}),
        BatchUpdateItem(id="2", properties={"nom": "Y"}),
    ]
    with patch(
        "app.services.node_service.clients.execute_cypher",
        new=AsyncMock(return_value=fake_results),
    ) as mock_exec:
        out = await node_service.batch_update_nodes("Produit", items)

    assert out["found"] == [
        {"id": "1", "node": {"id": "id_produit_1", "nom": "X"}}
    ]
    assert out["missing"] == ["2"]

    assert mock_exec.await_count == 1
    args, kwargs = mock_exec.await_args
    query = args[0]
    assert "UNWIND $updates AS u" in query
    assert "SET n += u.props" in query
    assert kwargs.get("read_only") is False


@pytest.mark.asyncio
async def test_batch_update_nodes_invalid_label_raises():
    with pytest.raises(ValueError):
        await node_service.batch_update_nodes(
            "Bad;Label", [BatchUpdateItem(id="1", properties={})]
        )


@pytest.mark.asyncio
async def test_batch_update_nodes_empty_items():
    out = await node_service.batch_update_nodes("Produit", [])
    assert out == {"found": [], "missing": []}


# ---------- batch_upsert_nodes (uniform props applied to many ids) ----------


@pytest.mark.asyncio
async def test_batch_upsert_nodes_returns_found_and_missing():
    fake_results = [
        {"id": "id_produit_1", "n": {"id": "id_produit_1", "statut": "active"}},
    ]
    with patch(
        "app.services.node_service.clients.execute_cypher",
        new=AsyncMock(return_value=fake_results),
    ) as mock_exec:
        out = await node_service.batch_upsert_nodes(
            "Produit", [1, 2], {"statut": "active"}
        )

    assert out["found"] == [
        {"id": 1, "node": {"id": "id_produit_1", "statut": "active"}}
    ]
    assert out["missing"] == [2]

    # Single Cypher call — same $props applied to every matched id
    assert mock_exec.await_count == 1
    args, kwargs = mock_exec.await_args
    query = args[0]
    assert "WHERE n.id IN $ids" in query
    assert "SET n += $props" in query
    assert kwargs.get("read_only") is False


@pytest.mark.asyncio
async def test_batch_upsert_nodes_invalid_label_raises():
    with pytest.raises(ValueError):
        await node_service.batch_upsert_nodes("Bad;Label", [1], {"x": 1})


@pytest.mark.asyncio
async def test_batch_upsert_nodes_empty_ids():
    out = await node_service.batch_upsert_nodes("Produit", [], {"x": 1})
    assert out == {"found": [], "missing": []}


@pytest.mark.asyncio
async def test_batch_upsert_nodes_empty_properties_is_noop():
    out = await node_service.batch_upsert_nodes("Produit", [1, 2], {})
    assert out == {"found": [], "missing": [1, 2]}
