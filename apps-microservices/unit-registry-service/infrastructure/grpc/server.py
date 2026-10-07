from __future__ import annotations

from concurrent import futures

import grpc

from application.types_service import TypeService
from application.unit_service import UnitService
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc

from .auth import AdminKeyInterceptor
from .servicer import UnitRegistryServicer


def build_server(units: UnitService, types: TypeService, *, admin_key: str, port: int,
                 max_workers: int = 10) -> tuple[grpc.Server, int]:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers),
                         interceptors=[AdminKeyInterceptor(admin_key)])
    pb_grpc.add_UnitRegistryServiceServicer_to_server(UnitRegistryServicer(units, types), server)
    bound = server.add_insecure_port(f"[::]:{port}")
    return server, bound
