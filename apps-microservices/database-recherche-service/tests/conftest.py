"""Test bootstrap — stubs heavy native deps so unit tests can import
`infrastructure.grpc_server` without installing pymilvus/uvloop/etc."""
import sys
from unittest.mock import MagicMock

# Stub heavy deps that grpc_server transitively imports via MilvusClient /
# SearchUseCase but the Redis-wiring + concurrency-guard tests don't exercise.
for _name in (
    "pymilvus",
    "uvloop",
):
    sys.modules.setdefault(_name, MagicMock())
