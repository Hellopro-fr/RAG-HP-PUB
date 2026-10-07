import grpc
import pytest
from google.protobuf.field_mask_pb2 import FieldMask

from application.types_service import TypeService
from application.unit_service import UnitService
from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from infrastructure.grpc.server import build_server

from .conftest import NOW

KEY = "test-admin-key-0123456789"
AUTH = (("authorization", f"Bearer {KEY}"),)


@pytest.fixture
def stub(seeded):
    server, port = build_server(UnitService(seeded, clock=lambda: NOW), TypeService(seeded, clock=lambda: NOW),
                                admin_key=KEY, port=0)
    server.start()
    channel = grpc.insecure_channel(f"localhost:{port}")
    yield pb_grpc.UnitRegistryServiceStub(channel)
    channel.close()
    server.stop(None)


def sac_spec(**overrides):
    spec = pb.UnitSpec(token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
                       regression_sample=pb.RegressionSample(label="Poids", value="2",
                                                             expected_canonical_value=50.0,
                                                             expected_canonical_unit="kilogram"))
    for key, value in overrides.items():
        setattr(spec, key, value)
    return spec


def code_of(call):
    with pytest.raises(grpc.RpcError) as info:
        call()
    return info.value.code(), info.value.details()


def test_writes_require_the_admin_bearer(stub):
    assert code_of(lambda: stub.RegisterUnit(pb.RegisterUnitRequest(spec=sac_spec())))[0] == grpc.StatusCode.UNAUTHENTICATED
    bad = (("authorization", "Bearer wrong"),)
    assert code_of(lambda: stub.RegisterUnit(pb.RegisterUnitRequest(spec=sac_spec()), metadata=bad))[0] == grpc.StatusCode.UNAUTHENTICATED


def test_reads_are_open(stub):
    assert stub.GetUnit(pb.GetUnitRequest(token="kg")).spec.dimension == "mass"


def test_register_get_update_delete_round_trip(stub):
    # An alias must normalize like the token (G2), so pint learns it in the definition first.
    created = stub.RegisterUnit(pb.RegisterUnitRequest(
        spec=sac_spec(pint_definition="sac_ciment = 25 * kilogram = sacs"), created_by="mcp:test"), metadata=AUTH)
    assert created.registry_version == 2 and created.status == "ACTIVE" and created.created_by == "mcp:test"
    # The stored sample is re-run by G4, so an alias-only update needs no new sample.
    updated = stub.UpdateUnit(pb.UpdateUnitRequest(id=created.id, spec=pb.UnitSpec(aliases=["sacs"]),
                                                   update_mask=FieldMask(paths=["aliases"])), metadata=AUTH)
    assert list(updated.spec.aliases) == ["sacs"] and updated.registry_version == 3
    assert stub.DeleteUnit(pb.DeleteUnitRequest(id=created.id), metadata=AUTH).success
    assert stub.GetUnit(pb.GetUnitRequest(id=created.id)).status == "DISABLED"


def test_guard_failures_map_to_status_codes(stub):
    code, details = code_of(lambda: stub.RegisterUnit(
        pb.RegisterUnitRequest(spec=sac_spec(token="kg", pint_definition="")), metadata=AUTH))
    assert code == grpc.StatusCode.ALREADY_EXISTS and "kg" in details
    code, details = code_of(lambda: stub.RegisterUnit(pb.RegisterUnitRequest(
        spec=sac_spec(pint_definition="sac_ciment = 3 * nonexistent_y")), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT and "G1" in details


def test_p2_only_fields_are_rejected(stub):
    code, details = code_of(lambda: stub.RegisterUnit(
        pb.RegisterUnitRequest(spec=sac_spec(kind="PASSTHROUGH")), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT and "P2" in details
    code, _ = code_of(lambda: stub.RegisterUnit(
        pb.RegisterUnitRequest(spec=sac_spec(case_sensitive=True)), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT


def test_update_mask_is_validated(stub):
    kg = stub.GetUnit(pb.GetUnitRequest(token="kg"))
    code, details = code_of(lambda: stub.UpdateUnit(
        pb.UpdateUnitRequest(id=kg.id, update_mask=FieldMask(paths=["token"])), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT and "token" in details
    code, _ = code_of(lambda: stub.UpdateUnit(pb.UpdateUnitRequest(id=kg.id), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT


def test_list_units_returns_everything_with_limit_zero_and_the_version(stub):
    response = stub.ListUnits(pb.ListUnitsRequest(status="ACTIVE", limit=0))
    assert response.total == len(response.units) > 200 and response.registry_version == 1
    page = stub.ListUnits(pb.ListUnitsRequest(status="ACTIVE", limit=10, offset=5))
    assert len(page.units) == 10 and page.total == response.total


def test_disable_with_dependents_is_failed_precondition(stub):
    cheval_vapeur = stub.GetUnit(pb.GetUnitRequest(token="cheval_vapeur"))
    code, details = code_of(lambda: stub.DeleteUnit(pb.DeleteUnitRequest(id=cheval_vapeur.id), metadata=AUTH))
    assert code == grpc.StatusCode.FAILED_PRECONDITION and "CV" in details


def test_validate_unit_is_open_and_reports_six_guards(stub):
    result = stub.ValidateUnit(pb.ValidateUnitRequest(spec=sac_spec()))
    assert result.overall_ok and [g.guard for g in result.guards] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert result.dry_run.canonical_value == 50.0


def test_unit_type_rpcs_and_inherited_types(stub):
    created = stub.CreateUnitType(pb.CreateUnitTypeRequest(spec=pb.UnitTypeSpec(code="POIDS", label="Poids")),
                                  metadata=AUTH)
    assert created.is_active and created.spec.code == "POIDS"
    linked = stub.SetDimensionTypes(pb.SetDimensionTypesRequest(dimension="mass", type_codes=["POIDS"]),
                                    metadata=AUTH)
    assert list(linked.type_codes) == ["POIDS"]
    assert list(stub.GetUnit(pb.GetUnitRequest(token="kg")).types) == ["POIDS"]
    codes = [t.spec.code for t in stub.ListUnitTypes(pb.ListUnitTypesRequest()).types]
    assert codes == ["CAPACITY", "DIMENSION", "POIDS"]
    code, _ = code_of(lambda: stub.UpdateUnitType(
        pb.UpdateUnitTypeRequest(id=created.id, update_mask=FieldMask(paths=["code"])), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT
    deactivated = stub.DeactivateUnitType(pb.DeactivateUnitTypeRequest(id=created.id), metadata=AUTH)
    assert not deactivated.is_active
    assert list(stub.GetUnitType(pb.GetUnitTypeRequest(code="POIDS")).dimensions) == ["mass"]
    code, _ = code_of(lambda: stub.SetDimensionTypes(
        pb.SetDimensionTypesRequest(dimension="mass", type_codes=["POIDS"]), metadata=AUTH))
    assert code == grpc.StatusCode.FAILED_PRECONDITION


def test_type_writes_require_the_bearer(stub):
    code, _ = code_of(lambda: stub.CreateUnitType(
        pb.CreateUnitTypeRequest(spec=pb.UnitTypeSpec(code="POIDS", label="Poids"))))
    assert code == grpc.StatusCode.UNAUTHENTICATED
