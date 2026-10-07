from concurrent import futures

import grpc

from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from infrastructure.registry_client import RegistryClient
from unit_registry.proto_codec import unit_to_proto
from unit_registry.types import Unit

SAC = Unit(id="sac", token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
           sort_order=10_000)


class Servicer(pb_grpc.UnitRegistryServiceServicer):
    def __init__(self):
        self.requests = []

    def ListUnits(self, request, context):
        self.requests.append(request)
        return pb.ListUnitsResponse(units=[unit_to_proto(SAC)], total=1, registry_version=7)


def test_list_active_asks_for_every_active_unit():
    servicer = Servicer()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_UnitRegistryServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    try:
        units, version = RegistryClient(f"localhost:{port}").list_active()
    finally:
        server.stop(None)
    assert units == [SAC] and version == 7
    assert servicer.requests[0].status == "ACTIVE" and servicer.requests[0].limit == 0
