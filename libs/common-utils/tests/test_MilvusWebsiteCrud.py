"""Tests for MilvusWebsiteCrud.insert_website schema projection and error wrapping.

pymilvus is faked when absent locally: the tests only exercise insert_website
against a mocked Collection, never a real connection.
"""

import importlib.util
import sys
import types
from unittest.mock import Mock

import pytest

if importlib.util.find_spec("pymilvus") is None:
    fake = types.ModuleType("pymilvus")

    class _FakeMilvusException(Exception):
        pass

    fake.MilvusException = _FakeMilvusException
    fake.connections = types.SimpleNamespace(
        has_connection=lambda alias: False,
        connect=lambda **kwargs: None,
        disconnect=lambda alias: None,
    )
    fake.utility = types.SimpleNamespace()
    fake.FieldSchema = object
    fake.CollectionSchema = object
    fake.DataType = types.SimpleNamespace(INT64=5, VARCHAR=21, FLOAT_VECTOR=101)
    fake.Collection = object
    sys.modules["pymilvus"] = fake

from common_utils.database.MilvusWebsiteCrud import (  # noqa: E402
    _INSERT_FIELDS,
    MilvusException,
    MilvusWebsiteCrud,
)


class _StubConfig:
    ZILLIZ_URI = "zilliz-host"
    ZILLIZ_PORT = "19530"
    ZILLIZ_USER = "user"
    ZILLIZ_PASSWORD = "password"
    RECREATE_COLLECTIONS = False


def _make_crud(insert_result=None, insert_side_effect=None):
    crud = MilvusWebsiteCrud(config=_StubConfig())
    crud._ensure_connected = lambda: None
    collection = Mock()
    collection.name = "siteweb_2"
    if insert_side_effect is not None:
        collection.insert.side_effect = insert_side_effect
    else:
        collection.insert.return_value = insert_result or Mock(primary_keys=[123])
    crud.collection = collection
    return crud


def _chunk(**overrides):
    chunk = {
        "url": "https://starkein.fr/mentions-legales/",
        "embedding": [0.1] * 4,
        "page_type": "autre",
        "domaine": "starkein.fr",
        "categorie": None,
        "id_categorie": None,
        "fournisseur": "STARKEIN",
        "id_fournisseur": "3070283",
        "etat": "Prospect",
        "affichage": "Découverte",
        "text": "Mentions légales",
        "source": "site_web",
        "fichier_source": "datasets/starkein.fr/000000032.json",
        "chunk_id": "1",
        "chunk_number": 1,
        "total_chunks": 2,
        "date_ajout": 1783130943,
        "date_maj": None,
    }
    chunk.update(overrides)
    return chunk


def test_insert_drops_fields_outside_schema():
    crud = _make_crud()
    extra = _chunk(
        commentaire_si_autre="Type non listé retourné par le LLM : 'mentions_legales_cgv_cgu'"
    )

    result = crud.insert_website([extra])

    assert result == {"ids": "123", "status": "success"}
    (batch,), _ = crud.collection.insert.call_args
    inserted = batch[0]
    assert "commentaire_si_autre" not in inserted
    assert set(inserted) <= _INSERT_FIELDS


def test_insert_sanitizes_dates_and_none_values():
    crud = _make_crud()

    crud.insert_website([_chunk()])

    (batch,), _ = crud.collection.insert.call_args
    inserted = batch[0]
    assert isinstance(inserted["date_ajout"], str)  # epoch int overwritten with isoformat
    assert inserted["date_maj"] == ""
    assert inserted["categorie"] == ""
    assert inserted["id_categorie"] == ""


def test_milvus_exception_wrapped_with_context():
    original = MilvusException("boom")
    crud = _make_crud(insert_side_effect=original)

    with pytest.raises(RuntimeError, match="boom") as excinfo:
        crud.insert_website([_chunk()])

    assert excinfo.value.__cause__ is original
    assert crud.collection is None  # forces reconnection on next call
