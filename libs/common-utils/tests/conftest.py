"""Shared test bootstrap for common-utils.

Installs a minimal fake `pymilvus` when the real package is not available
locally, so the Milvus CRUD modules import and their pure logic (field
projection, UTF-8 sanitization, error wrapping) can be unit-tested without a
Milvus server. Tests stub `_ensure_connected` and inject a Mock collection, so
the fake's connection/schema helpers are never actually exercised.
"""

import importlib.machinery
import importlib.util
import sys
import types

if importlib.util.find_spec("pymilvus") is None:
    _fake = types.ModuleType("pymilvus")
    _fake.__spec__ = importlib.machinery.ModuleSpec("pymilvus", loader=None)

    class _FakeMilvusException(Exception):
        pass

    _fake.MilvusException = _FakeMilvusException
    _fake.connections = types.SimpleNamespace(
        has_connection=lambda *a, **k: False,
        connect=lambda *a, **k: None,
        disconnect=lambda *a, **k: None,
    )
    _fake.utility = types.SimpleNamespace(
        has_collection=lambda *a, **k: True,
        drop_collection=lambda *a, **k: None,
        list_collections=lambda *a, **k: [],
    )
    _fake.FieldSchema = lambda *a, **k: None
    _fake.CollectionSchema = lambda *a, **k: None
    _fake.DataType = types.SimpleNamespace(INT64=5, VARCHAR=21, FLOAT_VECTOR=101)
    _fake.Collection = lambda *a, **k: None

    sys.modules["pymilvus"] = _fake
