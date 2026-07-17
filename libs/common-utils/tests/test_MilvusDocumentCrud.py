"""Tests for MilvusDocumentCrud.get_document UTF-8 query-expr sanitize."""

from unittest.mock import Mock

import pytest

from common_utils.database.MilvusDocumentCrud import MilvusDocumentCrud


class _StubConfig:
    ZILLIZ_URI = "zilliz-host"
    ZILLIZ_PORT = "19530"
    ZILLIZ_USER = "user"
    ZILLIZ_PASSWORD = "password"
    RECREATE_COLLECTIONS = False


def _make_crud():
    crud = MilvusDocumentCrud(config=_StubConfig())
    crud._ensure_connected = lambda: None
    collection = Mock()
    collection.name = "document"
    collection.query.return_value = []
    crud.collection = collection
    return crud


@pytest.mark.asyncio
async def test_get_document_embeds_real_nonprintable_char_not_repr_escape():
    crud = _make_crud()
    await crud.get_document("docs/2025_\xa0plan.pdf")  # NBSP

    _, kwargs = crud.collection.query.call_args
    expr = kwargs["expr"]
    expr.encode("utf-8")  # valid UTF-8 on the wire
    assert "\xa0" in expr
    assert "\\x" not in expr


@pytest.mark.asyncio
async def test_get_document_strips_unencodable_surrogate():
    crud = _make_crud()
    await crud.get_document("docs/2025_\udca0plan.pdf")

    _, kwargs = crud.collection.query.call_args
    expr = kwargs["expr"]
    expr.encode("utf-8")  # must not raise
    assert "\udca0" not in expr
