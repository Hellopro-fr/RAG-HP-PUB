"""Tests for MilvusPjCrud: insert field-projection + get_pj UTF-8 query sanitize.

pymilvus is faked by conftest when absent; tests stub _ensure_connected and
inject a Mock collection, so no real Milvus connection is used.
"""

from unittest.mock import Mock

import pytest

from common_utils.database.MilvusPjCrud import _INSERT_FIELDS, MilvusPjCrud


class _StubConfig:
    ZILLIZ_URI = "zilliz-host"
    ZILLIZ_PORT = "19530"
    ZILLIZ_USER = "user"
    ZILLIZ_PASSWORD = "password"
    RECREATE_COLLECTIONS = False


def _make_crud(query_result=None):
    crud = MilvusPjCrud(config=_StubConfig())
    crud._ensure_connected = lambda: None
    collection = Mock()
    collection.name = "pjechanges"
    collection.insert.return_value = Mock(primary_keys=[42])
    collection.query.return_value = query_result if query_result is not None else []
    crud.collection = collection
    return crud


def _pj_chunk(**overrides):
    chunk = {
        "page_type": "fiche_technique",
        "id_demande": "3720412",
        "categorie": "Cabines acoustiques",
        "id_categorie": "2016899",
        "fournisseur": "J.P EMBALL",
        "id_fournisseur": "2973637",
        "etat": "Client",
        "affichage": "Complet",
        "acheteur": "Banger Music FRANCE",
        "id_acheteur": "3039999",
        "fichier_source": "mon_compte/upload_file/cabine.jpg",
        "source": "MCF",
        "text": "La cabine insonorisée",
        "embedding": [0.1] * 4,
        "chunk_id": "1",
        "chunk_number": 1,
        "total_chunks": 1,
        # extra upstream keys not in the pjechanges schema:
        "document": "https://example.com/x.pdf",
        "annnee": "2025",
        "commentaire_si_autre": "should be dropped",
    }
    chunk.update(overrides)
    return chunk


@pytest.mark.asyncio
async def test_insert_pj_projects_onto_schema_fields():
    crud = _make_crud()
    result = await crud.insert_pj([_pj_chunk()])

    assert result == {"ids": "42", "status": "success"}
    (batch,), _ = crud.collection.insert.call_args
    inserted = batch[0]
    assert "document" not in inserted
    assert "annnee" not in inserted
    assert "commentaire_si_autre" not in inserted
    assert set(inserted) <= _INSERT_FIELDS
    assert inserted["embedding"] == [0.1] * 4
    assert inserted["date_maj"] == ""  # None sanitized


@pytest.mark.asyncio
async def test_get_pj_embeds_real_nonprintable_char_not_repr_escape():
    # NBSP (U+00A0) is valid UTF-8 but non-printable: Python repr would render
    # it as the literal \xa0 escape, which Milvus decodes back into an invalid
    # byte (code 65535). The expr must carry the REAL char instead.
    crud = _make_crud()
    await crud.get_pj("mon_compte/upload_file/2025_\xa0cabine.jpg")

    _, kwargs = crud.collection.query.call_args
    expr = kwargs["expr"]
    expr.encode("utf-8")  # valid UTF-8 on the wire
    assert "\xa0" in expr  # real NBSP embedded...
    assert "\\x" not in expr  # ...not the repr \xa0 escape


@pytest.mark.asyncio
async def test_get_pj_strips_unencodable_surrogate():
    crud = _make_crud()
    # lone surrogate cannot be UTF-8 encoded at all → must be dropped
    await crud.get_pj("f_\udca0.jpg")

    _, kwargs = crud.collection.query.call_args
    expr = kwargs["expr"]
    expr.encode("utf-8")  # must not raise
    assert "\udca0" not in expr


@pytest.mark.asyncio
async def test_get_pj_escapes_double_quote_injection():
    crud = _make_crud()
    await crud.get_pj('a" or id >= 0 or "x')

    _, kwargs = crud.collection.query.call_args
    # the injected double-quote must be backslash-escaped, not break the literal
    assert '\\"' in kwargs["expr"]
