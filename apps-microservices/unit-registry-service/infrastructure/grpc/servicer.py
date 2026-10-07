"""gRPC adapter: proto <-> application services; ServiceError -> status code."""
from __future__ import annotations

import functools
import logging

import grpc
from sqlalchemy.exc import SQLAlchemyError

from application.errors import InvalidArgument, ServiceError
from application.models import UnitType
from application.types_service import TypeService
from application.unit_service import UnitDraft, UnitService
from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from unit_registry.guards import ValidationOutcome
from unit_registry.proto_codec import sample_from_proto, unit_to_proto
from unit_registry.types import Unit, UnitStatus

logger = logging.getLogger(__name__)

_STATUS = {
    "NOT_FOUND": grpc.StatusCode.NOT_FOUND,
    "ALREADY_EXISTS": grpc.StatusCode.ALREADY_EXISTS,
    "INVALID_ARGUMENT": grpc.StatusCode.INVALID_ARGUMENT,
    "FAILED_PRECONDITION": grpc.StatusCode.FAILED_PRECONDITION,
}
_P2_ONLY = ("label_condition", "rewrite_expression", "canonical_override")
_UNIT_PATHS = ("dimension", "pint_definition", "aliases", "depends_on", "regression_sample")
_TYPE_PATHS = ("label", "description")


def _rpc(method):
    @functools.wraps(method)
    def wrapper(self, request, context):
        try:
            return method(self, request, context)
        except ServiceError as exc:
            context.abort(_STATUS.get(exc.code, grpc.StatusCode.INTERNAL), str(exc))
        except SQLAlchemyError:
            logger.exception("database error in %s", method.__name__)
            context.abort(grpc.StatusCode.UNAVAILABLE, "unit registry database unavailable")
    return wrapper


def _reject_p2_fields(spec: pb.UnitSpec) -> None:
    used = [name for name in _P2_ONLY if getattr(spec, name)]
    if spec.kind not in ("", "NORMAL"):
        used.append("kind")
    if spec.case_sensitive:
        used.append("case_sensitive")
    if used:
        raise InvalidArgument(f"not supported before P2: {', '.join(used)}")


def _sample(spec: pb.UnitSpec):
    return sample_from_proto(spec.regression_sample) if spec.HasField("regression_sample") else None


def _draft(spec: pb.UnitSpec) -> UnitDraft:
    _reject_p2_fields(spec)
    return UnitDraft(token=spec.token, dimension=spec.dimension or None,
                     pint_definition=spec.pint_definition or None, aliases=tuple(spec.aliases),
                     depends_on=tuple(spec.depends_on), regression_sample=_sample(spec))


def _iso(value) -> str:
    return value.isoformat() if value else ""


def _type_response(unit_type: UnitType) -> pb.UnitTypeResponse:
    return pb.UnitTypeResponse(
        id=unit_type.id,
        spec=pb.UnitTypeSpec(code=unit_type.code, label=unit_type.label, description=unit_type.description or ""),
        is_active=unit_type.is_active,
        dimensions=list(unit_type.dimensions),
        created_by=unit_type.created_by,
        created_at=_iso(unit_type.created_at),
        updated_at=_iso(unit_type.updated_at),
    )


def _validation_response(outcome: ValidationOutcome) -> pb.ValidationResult:
    dry = outcome.dry_run
    dry_run = pb.DryRunResult(ok=dry.ok, canonical_value=dry.canonical_value or 0.0,
                              canonical_unit=dry.canonical_unit, bypassed=dry.bypassed, error=dry.error)
    if dry.canonical_max is not None:
        dry_run.canonical_max = dry.canonical_max
    return pb.ValidationResult(
        overall_ok=outcome.ok,
        guards=[pb.GuardResult(guard=g.guard, ok=g.ok, skipped=g.skipped, message=g.message) for g in outcome.guards],
        dry_run=dry_run,
    )


class UnitRegistryServicer(pb_grpc.UnitRegistryServiceServicer):
    def __init__(self, units: UnitService, types: TypeService):
        self._units = units
        self._types = types

    def _unit(self, unit: Unit, version: int = 0) -> pb.UnitResponse:
        return unit_to_proto(unit, registry_version=version, types=self._units.types_for([unit])[unit.id])

    # --- units -----------------------------------------------------------
    @_rpc
    def RegisterUnit(self, request, context):
        unit, version = self._units.register(_draft(request.spec), request.created_by or "unknown")
        return self._unit(unit, version)

    @_rpc
    def GetUnit(self, request, context):
        return self._unit(self._units.get(unit_id=request.id or None, token=request.token or None))

    @_rpc
    def ListUnits(self, request, context):
        try:
            status = UnitStatus(request.status) if request.status else None
        except ValueError:
            raise InvalidArgument(f"unknown status {request.status!r}")
        units, version = self._units.list(status=status, dimension=request.dimension or None,
                                          type_code=request.type or None)
        start = max(request.offset, 0)
        page = units[start:] if request.limit <= 0 else units[start:start + request.limit]
        types = self._units.types_for(page)
        return pb.ListUnitsResponse(units=[unit_to_proto(u, types=types[u.id]) for u in page],
                                    total=len(units), registry_version=version)

    @_rpc
    def UpdateUnit(self, request, context):
        if not request.id:
            raise InvalidArgument("'id' is required")
        paths = list(request.update_mask.paths)
        if not paths:
            raise InvalidArgument("update_mask must name at least one field")
        spec = request.spec
        values = {
            "dimension": lambda: spec.dimension or None,
            "pint_definition": lambda: spec.pint_definition or None,
            "aliases": lambda: tuple(spec.aliases),
            "depends_on": lambda: tuple(spec.depends_on),
            "regression_sample": lambda: _sample(spec),
        }
        changes = {}
        for path in paths:
            if path in _P2_ONLY or path in ("kind", "case_sensitive"):
                raise InvalidArgument(f"not supported before P2: {path}")
            if path not in values:
                raise InvalidArgument(f"field {path!r} cannot be updated; updatable: {', '.join(_UNIT_PATHS)}")
            changes[path] = values[path]()
        unit, version = self._units.update(request.id, changes, request.updated_by or "unknown")
        return self._unit(unit, version)

    @_rpc
    def DeleteUnit(self, request, context):
        if not request.id:
            raise InvalidArgument("'id' is required")
        self._units.disable(request.id, request.deleted_by or "unknown")
        return pb.DeleteUnitResponse(success=True)

    @_rpc
    def GetRegistryStatus(self, request, context):
        version, active = self._units.registry_status()
        return pb.RegistryStatus(loaded_version=version, active_unit_count=active)

    @_rpc
    def ValidateUnit(self, request, context):
        return _validation_response(self._units.validate(_draft(request.spec), unit_id=request.id or None))

    # --- unit types (C9) -------------------------------------------------
    @_rpc
    def CreateUnitType(self, request, context):
        spec = request.spec
        return _type_response(self._types.create(spec.code, spec.label, spec.description or None,
                                                 request.created_by or "unknown"))

    @_rpc
    def UpdateUnitType(self, request, context):
        paths = list(request.update_mask.paths)
        if "code" in paths:
            raise InvalidArgument("type code is immutable")
        if not paths:
            raise InvalidArgument("update_mask must name at least one field")
        unknown = [p for p in paths if p not in _TYPE_PATHS]
        if unknown:
            raise InvalidArgument(f"field {unknown[0]!r} cannot be updated; updatable: label, description")
        changes = {p: (getattr(request.spec, p) or None) for p in paths}
        return _type_response(self._types.update(request.id, changes, request.updated_by or "unknown"))

    @_rpc
    def DeactivateUnitType(self, request, context):
        return _type_response(self._types.deactivate(request.id, request.updated_by or "unknown"))

    @_rpc
    def GetUnitType(self, request, context):
        return _type_response(self._types.get(type_id=request.id or None, code=request.code or None))

    @_rpc
    def ListUnitTypes(self, request, context):
        return pb.ListUnitTypesResponse(
            types=[_type_response(t) for t in self._types.list(include_inactive=request.include_inactive)])

    @_rpc
    def SetDimensionTypes(self, request, context):
        codes = self._types.set_dimension_types(request.dimension, list(request.type_codes),
                                                request.updated_by or "unknown")
        return pb.DimensionTypesResponse(dimension=request.dimension, type_codes=codes)
