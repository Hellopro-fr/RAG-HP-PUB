from __future__ import annotations

import grpc

from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from unit_registry.proto_codec import unit_from_proto
from unit_registry.types import Unit


class RegistryClient:
    def __init__(self, address: str, timeout: float = 10.0):
        self._stub = pb_grpc.UnitRegistryServiceStub(grpc.insecure_channel(address))
        self._timeout = timeout

    def list_active(self) -> tuple[list[Unit], int]:
        response = self._stub.ListUnits(pb.ListUnitsRequest(status="ACTIVE", limit=0), timeout=self._timeout)
        return [unit_from_proto(u) for u in response.units], response.registry_version
